"""車両登録に「どの案件で使ったか」を追加する（2026-09-04大橋様ご依頼）。

・案件はプルダウン(ぱど：京阪北版／ぱど：京阪南版／リビングプロシード／アドバリュー／その他)
・週選択・案件区分欄は、他のフォーム(小口・買掛・売掛)と同じく
  「アドバリュー」「その他」を選んだときだけ出す(常時表示しない)
・登録したデータは号別明細ページでも見られる

登録フォームのウィジェット(車両・車両名・ドライバー・使用用途)はkeyを持たないため、
既存の test_pages_smoke.py と同じくラベル/インデックスで拾う。
"""
import datetime as _dt
import os

from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _vehicle_page(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"),
                           default_timeout=60)
    at.session_state["entry_mode"] = "車両"
    at.run()
    assert not at.exception
    return at


def _fill_required_fields(at):
    """ドライバー・開始/終了メーターだけ埋める(車両名は既定のハイエースのまま)。"""
    at.text_input[1].set_value("時野")             # 0=車両名 1=ドライバー
    at.number_input[0].set_value(100)               # 開始メーター
    at.number_input[1].set_value(150)                # 終了メーター
    return at


def _submit_vehicle(at):
    at.button(key="FormSubmitter:vehicle-登録").click().run()
    return at


def test_vehicle_week_select_is_hidden_until_advalue_is_chosen(tmp_path, monkeypatch):
    at = _vehicle_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    assert not any(s.key == "vehicle_week" for s in at.selectbox)
    assert not any(t.key == "vehicle_other_label" for t in at.text_input)


def test_vehicle_registration_offers_the_project_dropdown(tmp_path, monkeypatch):
    at = _vehicle_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    proj = at.selectbox(key="vehicle_proj")
    for name in ("関西ぱど：京阪北版", "関西ぱど：京阪南版", "リビングプロシード",
                 "アドバリュー", "その他"):
        assert name in proj.options


def test_vehicle_project_label_has_no_annai_suffix(tmp_path, monkeypatch):
    """🔴 2026-09-04追加ご依頼: 「案件(任意)」→「案件」に短縮。"""
    at = _vehicle_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    assert at.selectbox(key="vehicle_proj").label == "案件"


def test_vehicle_week_select_appears_right_below_the_project_dropdown(tmp_path, monkeypatch):
    """🔴 2026-09-04追加ご依頼: 週選択は案件のすぐ下に表示する(formの奥に埋めない)。"""
    at = _vehicle_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    at.selectbox(key="vehicle_proj").set_value("アドバリュー").run()
    keys_in_order = [w.key for w in at.selectbox]
    assert keys_in_order.index("vehicle_week") == keys_in_order.index("vehicle_proj") + 1


def test_vehicle_advalue_without_a_week_is_refused(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _vehicle_page(db, monkeypatch)
    at.selectbox(key="vehicle_proj").set_value("アドバリュー").run()
    _fill_required_fields(at)
    _submit_vehicle(at)
    assert any("週" in str(e.value) for e in at.error), "週の未選択が知らされていない"
    assert store.list_vehicle_logs(db_path=db) == []


def test_vehicle_advalue_with_a_week_saves_project_and_label(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _vehicle_page(db, monkeypatch)
    at.selectbox(key="vehicle_proj").set_value("アドバリュー").run()
    at.date_input(key="vehicle_date").set_value(_dt.date(2026, 8, 4))
    _fill_required_fields(at)
    at.selectbox(key="vehicle_week").set_value("1週目")
    _submit_vehicle(at)
    rows = store.list_vehicle_logs(db_path=db)
    assert len(rows) == 1
    assert rows[0]["other_label"] == "8-1"
    pid = next(p["id"] for p in store.list_projects(db_path=db) if p["name"] == "アドバリュー")
    assert rows[0]["project_id"] == pid


def test_vehicle_non_advalue_project_needs_no_week(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _vehicle_page(db, monkeypatch)
    at.selectbox(key="vehicle_proj").set_value("関西ぱど：京阪北版").run()
    _fill_required_fields(at)
    _submit_vehicle(at)
    rows = store.list_vehicle_logs(db_path=db)
    assert len(rows) == 1 and rows[0]["other_label"] is None
    pid = next(p["id"] for p in store.list_projects(db_path=db)
               if p["name"] == "関西ぱど：京阪北版")
    assert rows[0]["project_id"] == pid


def test_vehicle_logs_appear_on_the_issue_detail_page(tmp_path, monkeypatch):
    """🔴 登録したデータが号別明細ページでも見られること。"""
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    pid = next(p["id"] for p in store.list_projects(db_path=db)
               if p["name"] == "関西ぱど：京阪北版")
    store.add_vehicle_log("2026-08-04", "ハイエース", "時野", 100, 150,
                          purpose="配布", project_id=pid, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"), default_timeout=60)
    at.session_state["proj_pills"] = "関西ぱど：京阪北版"
    at.run()
    assert not at.exception
    text = "\n".join(t.value.to_string() for t in at.table)
    assert "ハイエース" in text and "時野" in text
