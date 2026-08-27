import os
from streamlit.testing.v1 import AppTest
from common import posting_logic
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed(db, monkeypatch):
    """④: 原価が「買掛+小口+業務委託+直接入力」全部の和になること、かつ
    project_id=None の売掛(全案件横断)も売上に数えられることを1つのケースで検証できる形。
    receivable 5000(案件A) + receivable 2000(案件なし) + payable 3000
    + petty 1000 + contract line 400
    => 売上=7000, 原価=3000+1000+400=4400, 利益=2600"""
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db); store.seed_masters(db_path=db)
    pid = store.add_project("A号", db_path=db)
    cli = store.add_receivables_client("クライアントX", db_path=db)
    store.add_receivable("2026-07", cli, 5000, project_id=pid, db_path=db)
    store.add_receivable("2026-07", cli, 2000, project_id=None, db_path=db)  # 全案件横断
    ven = store.add_payables_vendor("大家", db_path=db)
    store.add_payable(None, ven, 3000, date="2026-07-02", project_id=pid, db_path=db)
    cat_id = store.list_expense_categories(db_path=db)[0]["id"]
    store.add_petty_cash("2026-07-03", cat_id, 1000, project_id=pid, db_path=db)
    did = store.add_distributor("山田", kind="業務委託", pay_type="歩合", db_path=db)
    store.add_contract_invoice(did, "2026-07-05", "2026-07-01", "2026-07-03",
        [{"project_id": pid, "report_qty": 1, "unit_price": 400, "remark": "配布",
          "other_label": None, "copies": None}], pay_type="歩合", db_path=db)
    return pid


def test_summary_page_shows_sales_cost_profit_and_payable_as_cost(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"), default_timeout=30)
    # 🔴 依頼⑧(2026-08-27)で既定の期間が「今月」になった。このテストのデータは
    # 2026-07 固定なので、明示的に全期間へ切り替えてから見る。
    at.session_state["summary_period_pills"] = "全期間"
    at.run()
    assert not at.exception
    parts = []
    for el in at.markdown: parts.append(str(el.value))
    for el in at.table: parts.append(el.value.to_string())
    for el in at.dataframe: parts.append(str(el.value))
    text = "\n".join(parts)
    assert "売上" in text and "原価" in text and "利益" in text
    # 実数で検証(売上=7000は project_id=None の2000も合算=全案件横断が効いている証拠。
    # 原価=4400は 買掛3000+小口1000+業務委託400 の全ソースが合算されている証拠)。
    assert f"¥{posting_logic.fmt_num(7000)}" in text   # 売上 = 5000 + 2000(案件なし)
    assert f"¥{posting_logic.fmt_num(4400)}" in text   # 原価 = 3000 + 1000 + 400
    assert f"¥{posting_logic.fmt_num(2600)}" in text   # 利益 = 7000 - 4400
    assert "大家" in text             # 買掛が原価明細に出る


def test_app_nav_lists_summary_before_issue():
    import re
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    i_sum = src.find("原価・売上まとめ")
    i_iss = src.find("号別明細")
    assert i_sum != -1 and i_sum < i_iss   # ナビで号別明細より前
