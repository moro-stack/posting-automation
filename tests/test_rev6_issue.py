import os
from streamlit.testing.v1 import AppTest
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(db):
    # 既定の pills はプリセットの先頭案件を選ぶため、テストで作った案件(A号)を
    # 見るには session_state で選択を差し込む必要がある(既存 test_pages_smoke.py と同様)。
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"), default_timeout=30)
    at.session_state["proj_pills"] = "A号"
    at.run()
    return at


def _rendered(at):
    parts = []
    for el in at.table: parts.append(el.value.to_string())
    for el in at.dataframe: parts.append(str(el.value))
    for el in at.markdown: parts.append(str(el.value))
    for el in at.caption: parts.append(str(el.value))
    return "\n".join(parts)


def _seed(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db); store.seed_masters(db_path=db)
    pid = store.add_project("A号", db_path=db)
    did = store.add_distributor("山田", kind="業務委託", pay_type="歩合", db_path=db)
    store.add_contract_invoice(did, "2026-07-05", "2026-07-01", "2026-07-03",
        [{"project_id": pid, "report_qty": 1, "unit_price": 100, "remark": "配布",
          "other_label": None, "copies": None}], pay_type="歩合", db_path=db)
    ven = store.add_payables_vendor("大家", db_path=db)
    store.add_payable(None, ven, 9999, date="2026-07-02", project_id=pid, db_path=db)
    return pid


def test_issue_shows_payment_date_for_contract(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = _run(db)
    text = _rendered(at)
    assert "支払日" in text            # 業務委託内訳に支払日列
    assert "2026-07-05" in text        # 発行日が支払日として出る


def test_issue_excludes_payable_from_cost(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = _run(db)
    text = _rendered(at)
    # 買掛9999は配布原価にも雑費にも出ない
    assert "9999" not in text
    assert "大家" not in text
