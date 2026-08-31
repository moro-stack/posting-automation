"""資料作成・変換表のダウンロードボタンを目立たせる（2026-08-31 オーナー指示）。

「白地に青文字でわかりにくい」とのご指摘。既定（secondary）のままだと
テーマの primaryColor（#14a4dc）が塗られず気づきにくいので、
生成ボタン（type="primary"）と同じ扱いに揃える。
"""
import os
import re

from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "pages", "07_資料作成・変換表.py")

_HEADER = "配布日,号数,ぱどんな,担当地区,配送物,配布部数,チラシサイズ"
_KITA_CSV = (
    "配送管理表,,,\n" + _HEADER + "\n"
    "2026-06-26,1248,ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ,10101,01 ぱど,224,\n"
).encode("cp932")


def _download_button_calls(src):
    """`.download_button(` から対応する閉じ括弧までのテキストを1呼び出しぶんずつ返す。"""
    calls = []
    for m in re.finditer(r"\.download_button\(", src):
        i = m.end()
        depth = 1
        while depth and i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        calls.append(src[m.end():i])
    return calls


def test_every_download_button_is_type_primary():
    """🔴 本体：ソース上の download_button 呼び出し全件が type="primary" であること。
    新しいタブ・ボタンが増えたときも、ここで漏れに気づける（網羅チェック）。"""
    src = open(PAGE, encoding="utf-8").read()
    calls = _download_button_calls(src)
    assert len(calls) == 5, f"download_button の呼び出し数が想定(5件)と違う: {len(calls)}件"
    offenders = [c for c in calls if 'type="primary"' not in c]
    assert not offenders, "type=\"primary\" が付いていないダウンロードボタンがある: " + \
        " / ".join(offenders)


def test_keihan_download_button_is_actually_rendered_as_primary(tmp_path, monkeypatch):
    """実際に生成→ダウンロードボタンが描かれた状態で、type="primary"がStreamlit側に
    渡っていること（ソースにtype="primary"と書いてあるだけで満足しない）。"""
    db = os.path.join(tmp_path, "smoke.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.run()
    at.segmented_control[0].set_value("京阪北版")
    at.run()
    at.file_uploader[0].set_value(("配送管理表.csv", _KITA_CSV, "text/csv"))
    at.run()
    at.button(key="keihan_atehagi").click().run()

    downloads = list(at.get("download_button"))
    assert downloads, "生成後にダウンロードボタンが描かれていない"
    assert downloads[0].proto.type == "primary", \
        f"ダウンロードボタンが primary 色になっていない（実際: {downloads[0].proto.type!r}）"
