import os
from common import demo_seed
from common import posting_store as store


def test_seed_demo_populates_and_is_idempotent(tmp_path):
    db = os.path.join(tmp_path, "demo.db")
    store.init_db(db)
    assert demo_seed.seed_demo_if_empty(db_path=db) is True
    projs = store.list_projects(db_path=db)
    assert projs                              # 案件が入る
    assert store.list_distributors(db_path=db)  # 配布員(業務委託)が入る
    assert store.list_contract_invoices(db_path=db)  # 業務委託請求が入る
    assert store.list_petty_cash(db_path=db)     # 小口
    assert store.list_payables(db_path=db)       # 買掛
    assert store.list_receivables(db_path=db)    # 売掛
    # 実名presetを使っていない(架空名)
    names = " ".join(p["name"] for p in projs)
    assert "関西ぱど" not in names and "進和" not in names
    # 冪等: 2回目は何もしない
    before = len(store.list_contract_invoices(db_path=db))
    assert demo_seed.seed_demo_if_empty(db_path=db) is False
    assert len(store.list_contract_invoices(db_path=db)) == before
