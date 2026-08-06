"""資料作成・変換表【京阪 あて紙】タブのUI受け入れテスト（関西ぱど指摘 2026-07-23）。

設計書: docs/superpowers/specs/2026-07-23-atehagi-kansai-pado-fix-design.md
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from common import atehagi as A
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "pages", "07_資料作成・変換表.py")

_HEADER = "配布日,号数,ぱどんな,担当地区,配送物,配布部数,チラシサイズ"


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = os.path.join(tmp_path, "smoke.db")
    monkeypatch.setenv("POSTING_DB_PATH", path)
    store.init_db(path)
    store.seed_masters(db_path=path)
    return path


def _csv(rows):
    body = "\n".join(",".join(str(c) for c in r) for r in rows)
    return ("配送管理表,,,\n" + _HEADER + "\n" + body + "\n").encode("cp932")


_KITA_CSV = _csv([
    ["2026-06-26", 1248, "ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ", 10101, "01 ぱど", 224, ""],
    ["2026-06-26", 1248, "ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ", 10101, "京都生協", 224, "Ｂ４"],
    ["2026-06-26", 1248, "枡田", 46501, "04 ぱど", 436, ""],
])

_MINAMI_CSV = _csv([
    ["2026-06-19", 1211, "ケイピーエス", 911001, "91 ぱど", 180, ""],
    ["2026-06-19", 1211, "ケイピーエス", 911001, "サンプルチラシ", 180, "Ａ４"],
])

_OVERFLOW_CSV = _csv(
    [["2026-06-26", 1248, "太郎", 10101, "01 ぱど", 224, ""]]
    + [["2026-06-26", 1248, "太郎", 10101, f"チラシ{i}", 224, "Ａ４"] for i in range(1, 16)]
)


def _open(upload=None, version=None):
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.run()
    if version:
        at.segmented_control[0].set_value(version)
        at.run()
    if upload is not None:
        at.file_uploader[0].set_value(("配送管理表.csv", upload, "text/csv"))
        at.run()
    return at


def _labels(at):
    return [b.label for b in at.button]


def _downloads(at):
    # このstreamlitバージョンの download_button proto はファイル名を持たないため、
    # ダウンロードボタンのラベルにファイル名を出し、そこで検証する。
    return list(at.get("download_button"))


def _download_labels(at):
    return [d.label for d in _downloads(at)]


def test_minami_can_generate_instead_of_warning(db):
    """南版の地区名ルールが入ったので、警告ではなく生成できること。"""
    at = _open(_MINAMI_CSV, "京阪南版")
    assert not at.exception
    warnings = " ".join(str(w.value) for w in at.warning)
    assert "地区名ルール" not in warnings
    assert "あて紙を生成" in _labels(at)


def test_download_button_survives_rerun(db):
    """生成→ダウンロードの間に再実行が入ってもダウンロードボタンが消えないこと。"""
    at = _open(_KITA_CSV, "京阪北版")
    at.button(key="keihan_atehagi").click().run()
    assert _downloads(at), "生成直後にダウンロードボタンが出ていない"
    at.run()          # 何もせず再実行（＝ダウンロード押下後に相当）
    assert _downloads(at), "再実行でダウンロードボタンが消えた"


def test_single_area_reoutput_by_code(db):
    """担当地区コードを入力すると、その地区だけのあて紙を出せること。"""
    at = _open(_KITA_CSV, "京阪北版")
    at.text_input(key="keihan_area_codes").set_value("10101").run()
    at.button(key="keihan_single").click().run()
    assert not at.exception
    names = _download_labels(at)
    assert any("010101" in n for n in names), f"地区コード入りのファイル名が無い: {names}"


def test_single_area_reoutput_accepts_zero_padded_code(db):
    """0付きで入力しても同じ地区として扱われること。"""
    at = _open(_KITA_CSV, "京阪北版")
    at.text_input(key="keihan_area_codes").set_value("010101").run()
    at.button(key="keihan_single").click().run()
    assert not at.exception
    names = _download_labels(at)
    assert any("010101" in n for n in names)


def test_unknown_area_code_is_reported(db):
    """存在しない地区コードを入れたら、黙って空を出さずに知らせること。"""
    at = _open(_KITA_CSV, "京阪北版")
    at.text_input(key="keihan_area_codes").set_value("99999").run()
    at.button(key="keihan_single").click().run()
    assert not at.exception
    msg = " ".join(str(e.value) for e in at.error) + " ".join(str(w.value) for w in at.warning)
    # ⚠️ `or "見つかり" in msg` のような常に真になる条件にしないこと。
    #    入力は6桁ゼロ埋めに正規化されるので "099999" が出るのが正しい。
    assert "099999" in msg, msg


def test_overflow_area_is_warned(db):
    """明細が13件を超える地区があると警告が出ること（無警告の欠落を防ぐ）。"""
    at = _open(_OVERFLOW_CSV, "京阪北版")
    assert not at.exception
    warnings = " ".join(str(w.value) for w in at.warning)
    # 上限値は実装の定数と連動させる（画面のベタ書き文字列を見るだけにしない）
    assert str(A._MAX_DETAIL_ROWS) in warnings and "10101" in warnings


# ---------------------------------------------------------------------------
# 敵対的レビュー（2026-07-23）で実UI再現が確認された指摘への回帰テスト
# ---------------------------------------------------------------------------

_KITA_CSV_EDITED = _csv([          # _KITA_CSV と同名・同バイト数で中身だけ違う
    ["2026-06-26", 1248, "ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ", 10101, "01 ぱど", 324, ""],
    ["2026-06-26", 1248, "ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ", 10101, "京都生協", 324, "Ｂ４"],
    ["2026-06-26", 1248, "枡田", 46501, "04 ぱど", 436, ""],
])

_EMPTY_CSV = ("配送管理表,,,\n" + _HEADER + "\n").encode("cp932")


def test_version_mismatch_is_blocked(db):
    """北版のデータを南版で出そうとしたら止めること（全枚数の地区名が誤る事故の防止）。"""
    at = _open(_KITA_CSV, "京阪南版")
    assert not at.exception
    msgs = " ".join(str(e.value) for e in at.error)
    assert "版" in msgs, f"版の取り違えが警告されていない: {msgs}"
    assert "あて紙を生成" not in _labels(at), "取り違えたまま生成できてしまう"


def test_matching_version_is_not_blocked(db):
    """正しい組み合わせは邪魔しないこと。"""
    for csv_bytes, ver in ((_KITA_CSV, "京阪北版"), (_MINAMI_CSV, "京阪南版")):
        at = _open(csv_bytes, ver)
        assert not at.exception
        assert "あて紙を生成" in _labels(at)
        assert not [e for e in at.error]


def test_minami_can_actually_generate(db):
    """南版で実際に生成ボタンを押してダウンロードまで到達すること。"""
    at = _open(_MINAMI_CSV, "京阪南版")
    at.button(key="keihan_atehagi").click().run()
    assert not at.exception
    assert any("京阪南版" in n for n in _download_labels(at)), _download_labels(at)


def test_stale_output_discarded_when_file_content_changes(db):
    """同じ名前・同じサイズで中身だけ直したファイルに差し替えたら、前の生成物を捨てること。"""
    at = _open(_KITA_CSV, "京阪北版")
    at.button(key="keihan_atehagi").click().run()
    assert _downloads(at)
    assert len(_KITA_CSV) == len(_KITA_CSV_EDITED)      # 同サイズであることが前提の検証
    at.file_uploader[0].set_value(("配送管理表.csv", _KITA_CSV_EDITED, "text/csv"))
    at.run()
    assert not _downloads(at), "中身を直したのに古い生成物のダウンロードが残っている"


def test_failed_single_output_clears_previous_download(db):
    """単票の再出力に失敗したら、前に作った別地区のダウンロードを残さないこと。"""
    at = _open(_KITA_CSV, "京阪北版")
    at.text_input(key="keihan_area_codes").set_value("10101").run()
    at.button(key="keihan_single").click().run()
    assert _downloads(at)
    at.text_input(key="keihan_area_codes").set_value("99999").run()
    at.button(key="keihan_single").click().run()
    assert not _downloads(at), "失敗したのに前の地区のダウンロードボタンが残っている"


def test_empty_data_gives_feedback(db):
    """データが0件のファイルでも、無反応にせず知らせること。

    ⚠️ 他タブにも st.info があるため、要素の有無だけを見ると常に通ってしまう。
    「0件」に言及した文言が出ていることまで確かめる。
    """
    at = _open(_EMPTY_CSV, "京阪北版")
    assert not at.exception
    msgs = " ".join(str(x.value) for x in list(at.warning) + list(at.info) + list(at.error))
    assert "0件" in msgs, f"データ0件であることが画面に出ていない: {msgs}"
