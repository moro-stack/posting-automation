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


def test_seed_for_boot_demo_uses_fake_not_real_presets(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "d.db")
    store.init_db(db)
    monkeypatch.setenv("DEMO_MODE", "1")
    demo_seed.seed_for_boot(db_path=db)
    names = " ".join(p["name"] for p in store.list_projects(db_path=db))
    clients = " ".join(c["name"] for c in store.list_receivables_clients(db_path=db))
    assert "関西ぱど" not in names and "関西ぱど" not in clients   # 実名が漏れない
    assert "進和" not in clients
    assert "デモ" in names                                        # 架空データが入る


def test_seed_for_boot_normal_uses_real_presets(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "n.db")
    store.init_db(db)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    demo_seed.seed_for_boot(db_path=db)
    names = " ".join(p["name"] for p in store.list_projects(db_path=db))
    assert "関西ぱど" in names                                    # 非DEMOは実マスタpreset
