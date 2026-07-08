import os
from common import posting_store as store

TABLES = {
    "projects", "expense_categories", "payables_vendors",
    "receivables_clients", "distributors",
    "petty_cash", "payables", "receivables",
    "contract_invoices", "contract_invoice_lines", "issue_manual_costs",
}


def _table_names(db_path):
    conn = store._connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def test_init_db_creates_all_tables(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.init_db(db)
    assert TABLES.issubset(_table_names(db))


def test_add_and_list_project(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("関西ぱど：京阪北版", db_path=db)
    rows = store.list_projects(db_path=db)
    assert any(r["id"] == pid and r["name"] == "関西ぱど：京阪北版" for r in rows)


def test_update_and_soft_delete_project(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("旧名", db_path=db)
    store.update_project(pid, name="新名", db_path=db)
    store.update_project(pid, active=0, db_path=db)
    active = store.list_projects(only_active=True, db_path=db)
    assert all(r["id"] != pid for r in active)
    allrows = store.list_projects(db_path=db)
    assert any(r["id"] == pid and r["name"] == "新名" for r in allrows)


def test_distributor_kind_stored(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("黒瀬", kind="自社社員", db_path=db)
    rows = store.list_distributors(db_path=db)
    assert any(r["id"] == did and r["kind"] == "自社社員" for r in rows)


def test_seed_masters_is_idempotent(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.seed_masters(db_path=db)
    store.seed_masters(db_path=db)
    names = {r["name"] for r in store.list_projects(db_path=db)}
    assert "アドバリュー" in names
    vendors = {r["name"] for r in store.list_payables_vendors(db_path=db)}
    assert "大東建託パートナーズ株式会社" in vendors
    clients = {r["name"] for r in store.list_receivables_clients(db_path=db)}
    assert "株式会社アド・バリュー" in clients
    # 2回呼んでも重複しない
    assert len(store.list_receivables_clients(db_path=db)) == len(set(clients))


def test_petty_cash_roundtrip_and_filter(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    a = store.add_petty_cash("2026-06-19", 1, 1200, project_id=3, memo="駐車場", db_path=db, now="T")
    store.add_petty_cash("2026-06-25", 1, 500, db_path=db, now="T")
    assert len(store.list_petty_cash(db_path=db)) == 2
    only = store.list_petty_cash(project_id=3, db_path=db)
    assert len(only) == 1 and only[0]["id"] == a
    ranged = store.list_petty_cash(date_from="2026-06-20", date_to="2026-06-30", db_path=db)
    assert len(ranged) == 1 and ranged[0]["amount"] == 500


def test_payable_with_original_status(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_payable("2026-06", 2, 245300, original_status="本社",
                            note="web請求書 家賃", db_path=db, now="T")
    rows = store.list_payables(month="2026-06", db_path=db)
    assert rows[0]["id"] == pid and rows[0]["original_status"] == "本社"


def test_receivable_roundtrip(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_receivable("2026-06", 1, 3184799, note="6/26号", db_path=db, now="T")
    rows = store.list_receivables(month="2026-06", db_path=db)
    assert rows[0]["amount"] == 3184799


def test_contract_invoice_roundtrip_and_amount(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    lines = [
        {"project_id": 1, "report_qty": 3713, "unit_price": 3, "remark": "配布"},
        {"project_id": 1, "report_qty": 1, "unit_price": 540, "remark": "交通費"},
    ]
    inv = store.add_contract_invoice(5, "2026-06-30", "2026-06-19", "2026-06-27",
                                     lines, db_path=db, now="T")
    got = store.get_contract_invoice(inv, db_path=db)
    assert got["invoice"]["distributor_id"] == 5
    assert len(got["lines"]) == 2
    # amount = report_qty * unit_price
    assert got["lines"][0]["amount"] == 3713 * 3
    assert got["lines"][1]["amount"] == 540


def test_delete_contract_invoice_removes_lines(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    inv = store.add_contract_invoice(1, "2026-06-30", "2026-06-01", "2026-06-05",
                                     [{"project_id": 1, "report_qty": 10, "unit_price": 5,
                                       "remark": "配布"}], db_path=db, now="T")
    store.delete_contract_invoice(inv, db_path=db)
    assert store.get_contract_invoice(inv, db_path=db) is None
    # 明細行が実際に消えたことを独立に検証（get_contract_invoice はヘッダ欠如で早期 None を返すため）
    conn = store._connect(db)
    try:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM contract_invoice_lines WHERE invoice_id=?", (inv,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert cnt == 0
