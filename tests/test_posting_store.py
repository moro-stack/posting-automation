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
