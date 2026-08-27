"""車両使用履歴を車種ごとのタブに分ける（2026-08-27・大橋様ご指摘）。

「ハイエース」「軽バン」「レンタカー」で見るところを分け、
どのタブにも表示期間の絞り込みを付ける。
"""
import os

from streamlit.testing.v1 import AppTest

from common import posting_logic
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    store.add_vehicle_log("2026-08-03", "ハイエース", "山田", 1000, 1080, db_path=db)
    store.add_vehicle_log("2026-08-04", "軽バン", "鈴木", 500, 540, db_path=db)
    store.add_vehicle_log("2026-08-05", "レンタカー", "佐藤", 10, 90, db_path=db)
    store.add_vehicle_log("2026-08-06", "軽トラ", "田中", 0, 30, db_path=db)


def _run(monkeypatch, db):
    _seed(db, monkeypatch)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"),
                           default_timeout=60)
    at.session_state["entry_mode"] = "車両"
    at.run()
    assert not at.exception
    return at


def _text(at):
    parts = []
    for el in at.markdown:
        parts.append(str(el.value))
    for el in at.caption:
        parts.append(str(el.value))
    for el in at.dataframe:
        parts.append(str(el.value))
    return "\n".join(parts)


def test_vehicle_list_has_one_tab_per_kind(tmp_path, monkeypatch):
    at = _run(monkeypatch, os.path.join(tmp_path, "t.db"))
    labels = [t.label for t in at.tabs]
    for kind in posting_logic.VEHICLE_KINDS:
        assert kind in labels, f"{kind} のタブが無い（タブ: {labels}）"


def test_vehicle_list_shows_a_sonota_tab_when_an_unlisted_vehicle_exists(tmp_path, monkeypatch):
    """🔴 3車種に当てはまらない車が「どのタブにも出ない」を防ぐ。"""
    at = _run(monkeypatch, os.path.join(tmp_path, "t.db"))
    labels = [t.label for t in at.tabs]
    assert "その他" in labels
    assert "軽トラ" in _text(at)


def test_every_vehicle_tab_has_its_own_period_picker(tmp_path, monkeypatch):
    """依頼どおり、どの車種のタブでも表示期間を絞り込めること。
    期間フィルタは pills の key で見分ける(共通部品 period_picker が付ける)。"""
    at = _run(monkeypatch, os.path.join(tmp_path, "t.db"))
    keys = {str(p.key) for p in at.pills}
    for kind in posting_logic.VEHICLE_KINDS:
        assert f"vehicle_period_{kind}_pills" in keys, \
            f"{kind} のタブに期間フィルタが無い（pills: {keys}）"
    # 車種ごとに別々の状態であること(1つを絞ると全部動く、を防ぐ)
    assert len({k for k in keys if k.startswith("vehicle_period_")}) >= 3


def test_each_vehicle_tab_shows_only_its_own_rows(tmp_path, monkeypatch):
    """タブごとに一覧の中身が分かれていること(全部同じ一覧を4回出さない)。"""
    at = _run(monkeypatch, os.path.join(tmp_path, "t.db"))
    frames = [el.value for el in at.dataframe]
    # data_editor が車種ごとに1つずつ出る。各表の「車両」列は1種類だけ。
    kinds_per_frame = []
    for df in frames:
        if df is None or getattr(df, "empty", True) or "車両" not in df.columns:
            continue
        kinds_per_frame.append(set(df["車両"].tolist()))
    assert kinds_per_frame, "車両の一覧が1つも描かれていない"
    for kinds in kinds_per_frame:
        assert len(kinds) == 1, f"1つのタブに複数の車種が混ざっている: {kinds}"
    assert {next(iter(k)) for k in kinds_per_frame} == {
        "ハイエース", "軽バン", "レンタカー", "軽トラ"}
