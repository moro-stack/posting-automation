import os
from streamlit.testing.v1 import AppTest
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db); store.seed_masters(db_path=db)
    pid = store.add_project("A号", db_path=db)
    cli = store.add_receivables_client("クライアントX", db_path=db)
    store.add_receivable("2026-07", cli, 5000, project_id=pid, db_path=db)
    ven = store.add_payables_vendor("大家", db_path=db)
    store.add_payable(None, ven, 3000, date="2026-07-02", project_id=pid, db_path=db)
    return pid


def test_summary_page_shows_sales_cost_profit_and_payable_as_cost(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"), default_timeout=30)
    at.run()
    assert not at.exception
    parts = []
    for el in at.markdown: parts.append(str(el.value))
    for el in at.table: parts.append(el.value.to_string())
    for el in at.dataframe: parts.append(str(el.value))
    text = "\n".join(parts)
    assert "売上" in text and "原価" in text and "利益" in text
    assert "5,000" in text            # 売上
    assert "大家" in text             # 買掛が原価明細に出る
    assert "3,000" in text            # 買掛の金額


def test_app_nav_lists_summary_before_issue():
    import re
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    i_sum = src.find("原価・売上まとめ")
    i_iss = src.find("号別明細")
    assert i_sum != -1 and i_sum < i_iss   # ナビで号別明細より前
