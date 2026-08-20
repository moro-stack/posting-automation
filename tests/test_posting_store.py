import os
from common import posting_store as store

TABLES = {
    "projects", "expense_categories", "payables_vendors",
    "receivables_clients", "distributors",
    "petty_cash", "payables", "receivables",
    "contract_invoices", "contract_invoice_lines", "issue_manual_costs",
    "distributor_daily_rates", "vehicle_logs",
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


def test_payables_vendor_default_original_status(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    vid = store.add_payables_vendor("関西電力株式会社", default_category="電気",
                                    default_original_status="振込用紙", db_path=db)
    row = next(r for r in store.list_payables_vendors(db_path=db) if r["id"] == vid)
    assert row["default_original_status"] == "振込用紙"


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


def test_payable_stores_invoice_date_and_derives_month(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_payable(None, 2, 50000, date="2026-07-15", db_path=db, now="T")
    row = [r for r in store.list_payables(db_path=db) if r["id"] == pid][0]
    assert row["date"] == "2026-07-15"
    assert row["month"] == "2026-07"   # 日付から月度を導出


def test_find_duplicate_petty(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_petty_cash("2026-07-01", 1, 1200, db_path=db, now="T")
    assert store.find_duplicate_petty("2026-07-01", 1, 1200, db_path=db)
    assert not store.find_duplicate_petty("2026-07-02", 1, 1200, db_path=db)
    assert not store.find_duplicate_petty("2026-07-01", 1, 999, db_path=db)


def test_find_duplicate_payable(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_payable(None, 2, 50000, date="2026-07-10", db_path=db, now="T")
    assert store.find_duplicate_payable("2026-07-10", 2, 50000, db_path=db)
    assert not store.find_duplicate_payable("2026-07-10", 2, 999, db_path=db)


def test_payable_stores_vendor_name_free_text(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_payable(None, None, 1848, date="2026-06-16",
                            vendor_name="NTTドコモビジネス株式会社", db_path=db, now="T")
    row = [r for r in store.list_payables(db_path=db) if r["id"] == pid][0]
    assert row["vendor_name"] == "NTTドコモビジネス株式会社"
    assert row["vendor_id"] is None
    assert row["month"] == "2026-06"   # 請求日から月度を導出


def test_find_duplicate_payable_by_vendor_name(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_payable(None, None, 1848, date="2026-06-16",
                      vendor_name="NTTドコモ", db_path=db, now="T")
    assert store.find_duplicate_payable("2026-06-16", None, 1848,
                                        vendor_name="NTTドコモ", db_path=db)
    assert not store.find_duplicate_payable("2026-06-16", None, 1848,
                                            vendor_name="別の会社", db_path=db)


def test_find_duplicate_receivable(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_receivable("2026-07", 1, 300000, db_path=db, now="T")
    assert store.find_duplicate_receivable("2026-07", 1, 300000, db_path=db)
    assert not store.find_duplicate_receivable("2026-08", 1, 300000, db_path=db)


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


def test_issue_manual_cost_roundtrip(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_issue_manual_cost(1, "自社社員配布分", 8000, db_path=db, now="T")
    rows = store.list_issue_manual_costs(project_id=1, db_path=db)
    assert rows[0]["amount"] == 8000 and rows[0]["content"] == "自社社員配布分"


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


def test_issue_manual_cost_work_date_add_and_ordering(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("6/26号", db_path=db)
    a = store.add_issue_manual_cost(pid, "配布", 104700, work_date="2026-06-22", db_path=db)
    b = store.add_issue_manual_cost(pid, "挟みこみ", 32250, work_date="2026-06-23", db_path=db)
    c = store.add_issue_manual_cost(pid, "日付なし", 8000, db_path=db)
    rows = store.list_issue_manual_costs(project_id=pid, db_path=db)
    assert [r["id"] for r in rows] == [a, b, c]           # 日付あり昇順→None末尾
    assert rows[0]["work_date"] == "2026-06-22"
    assert rows[2]["work_date"] is None


def test_issue_manual_cost_update_and_delete(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("号", db_path=db)
    rid = store.add_issue_manual_cost(pid, "配布", 100, work_date="2026-06-01", db_path=db)
    store.update_issue_manual_cost(rid, work_date="2026-06-22", content="丁合・配布",
                                   amount=136950, db_path=db)
    row = [r for r in store.list_issue_manual_costs(project_id=pid, db_path=db) if r["id"] == rid][0]
    assert row["work_date"] == "2026-06-22" and row["content"] == "丁合・配布" and row["amount"] == 136950
    store.delete_issue_manual_cost(rid, db_path=db)
    assert all(r["id"] != rid for r in store.list_issue_manual_costs(project_id=pid, db_path=db))


def test_issue_manual_cost_migrates_old_db(tmp_path):
    import sqlite3
    db = os.path.join(tmp_path, "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE issue_manual_costs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " project_id INTEGER, content TEXT, amount INTEGER NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO issue_manual_costs (project_id, content, amount, created_at)"
                 " VALUES (1, '旧行', 5000, '2026-06-01T00:00:00')")
    conn.commit()
    conn.close()
    rows = store.list_issue_manual_costs(project_id=1, db_path=db)  # 接続時に自動ALTER
    assert rows and rows[0]["content"] == "旧行" and rows[0]["work_date"] is None


def test_contract_invoice_export_mark(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    inv = store.add_contract_invoice(1, "2026-06-30", "2026-06-01", "2026-06-05",
                                     [{"project_id": 1, "report_qty": 10, "unit_price": 5,
                                       "remark": "配布"}], db_path=db, now="T")
    # 初期は未出力
    got = [i for i in store.list_contract_invoices(db_path=db) if i["id"] == inv][0]
    assert got["last_exported_at"] is None
    # 出力印を付ける
    store.mark_contract_invoice_exported(inv, db_path=db, now="2026-07-16T09:00:00")
    got = [i for i in store.list_contract_invoices(db_path=db) if i["id"] == inv][0]
    assert got["last_exported_at"] == "2026-07-16T09:00:00"


def test_petty_cash_stores_other_label(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_petty_cash("2026-07-05", 1, 3000, project_id=5,
                         other_label="A社折込チラシ", db_path=db)
    rows = store.list_petty_cash(project_id=5, db_path=db)
    assert rows[0]["other_label"] == "A社折込チラシ"


def test_petty_cash_stores_distributor(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", db_path=db)
    rid = store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    row = next(r for r in store.list_petty_cash(db_path=db) if r["id"] == rid)
    assert row["distributor_id"] == did


def test_petty_cash_distributor_is_optional(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    rid = store.add_petty_cash("2026-07-17", None, 1500, db_path=db)
    row = next(r for r in store.list_petty_cash(db_path=db) if r["id"] == rid)
    assert row["distributor_id"] is None


# ===== 車両使用履歴（依頼⑤・2026-08-19 大橋様ご指摘） =====
# 現在Excelで手管理している「社用車 使用履歴」（車両/日付/ドライバー/
# 開始・終了の走行距離メーター/使用用途/給油量）をアプリで記録できるようにする。


def test_add_vehicle_log_computes_distance_from_odometer(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    rid = store.add_vehicle_log("2026-06-19", "ハイエース", "時野",
                                55876, 55908, purpose="DOMOぱどポスト",
                                db_path=db, now="T")
    row = next(r for r in store.list_vehicle_logs(db_path=db) if r["id"] == rid)
    assert row["odo_start"] == 55876
    assert row["odo_end"] == 55908
    assert row["distance"] == 32           # 実データ(社用車使用履歴.xlsx)と同じ引き算
    assert row["purpose"] == "DOMOぱどポスト"
    assert row["driver"] == "時野"
    assert row["vehicle"] == "ハイエース"


def test_add_vehicle_log_without_odometer_has_no_distance(tmp_path):
    """開始/終了のどちらかが未入力なら距離は計算しない(0kmと決めつけない)。"""
    db = os.path.join(tmp_path, "t.db")
    rid = store.add_vehicle_log("2026-06-19", "軽バン", "黒瀬", None, None, db_path=db)
    row = next(r for r in store.list_vehicle_logs(db_path=db) if r["id"] == rid)
    assert row["distance"] is None


def test_add_vehicle_log_stores_fuel_liters(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    rid = store.add_vehicle_log("2026-06-19", "ハイエース", "時野", 100, 149,
                                fuel_liters=49.04, db_path=db)
    row = next(r for r in store.list_vehicle_logs(db_path=db) if r["id"] == rid)
    assert row["fuel_liters"] == 49.04


def test_list_vehicle_logs_filters_by_vehicle_and_date(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_vehicle_log("2026-06-01", "ハイエース", "時野", 100, 150, db_path=db)
    store.add_vehicle_log("2026-06-10", "軽バン", "黒瀬", 200, 235, db_path=db)
    store.add_vehicle_log("2026-07-01", "ハイエース", "枡田", 150, 180, db_path=db)
    only_haiace = store.list_vehicle_logs(vehicle="ハイエース", db_path=db)
    assert {r["driver"] for r in only_haiace} == {"時野", "枡田"}
    ranged = store.list_vehicle_logs(date_from="2026-06-05", date_to="2026-06-30", db_path=db)
    assert len(ranged) == 1 and ranged[0]["driver"] == "黒瀬"


def test_delete_vehicle_log(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    rid = store.add_vehicle_log("2026-06-01", "ハイエース", "時野", 100, 150, db_path=db)
    store.delete_vehicle_log(rid, db_path=db)
    assert store.list_vehicle_logs(db_path=db) == []


def test_payable_and_receivable_store_other_label(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_payable(None, None, 12000, date="2026-07-08", vendor_name="配夢",
                      project_id=5, other_label="B商店DM印刷", db_path=db)
    store.add_receivable("2026-07", 1, 50000, project_id=5,
                         other_label="C社スポット売上", db_path=db)
    assert store.list_payables(project_id=5, db_path=db)[0]["other_label"] == "B商店DM印刷"
    assert store.list_receivables(project_id=5, db_path=db)[0]["other_label"] == "C社スポット売上"


def test_contract_invoice_line_stores_other_label(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    inv = store.add_contract_invoice(
        1, "2026-07-10", "2026-07-01", "2026-07-05",
        [{"project_id": 5, "report_qty": 100, "unit_price": 5, "remark": "配布",
          "other_label": "臨時ポスティング"}], db_path=db, now="T")
    lines = store.get_contract_invoice(inv, db_path=db)["lines"]
    assert lines[0]["other_label"] == "臨時ポスティング"


def test_other_label_migrates_old_db(tmp_path):
    import sqlite3
    db = os.path.join(tmp_path, "t.db")
    conn = sqlite3.connect(db)
    # other_label 列を持たない旧スキーマ（petty_cash）
    conn.execute("CREATE TABLE petty_cash (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " date TEXT, category_id INTEGER, amount INTEGER NOT NULL,"
                 " project_id INTEGER, memo TEXT, source TEXT, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO petty_cash (amount, project_id, created_at)"
                 " VALUES (100, 5, 'T')")
    conn.commit()
    conn.close()
    rows = store.list_petty_cash(project_id=5, db_path=db)  # 接続時に自動ALTER
    assert rows and rows[0]["other_label"] is None


def test_contract_invoice_migrates_old_db_without_last_exported(tmp_path):
    import sqlite3
    db = os.path.join(tmp_path, "t.db")
    conn = sqlite3.connect(db)
    # last_exported_at 列を持たない旧スキーマ
    conn.execute("CREATE TABLE contract_invoices (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " distributor_id INTEGER, issue_date TEXT, period_from TEXT,"
                 " period_to TEXT, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO contract_invoices (distributor_id, issue_date, period_from,"
                 " period_to, created_at) VALUES (1,'2026-06-30','2026-06-01','2026-06-05','T')")
    conn.commit()
    conn.close()
    rows = store.list_contract_invoices(db_path=db)  # 接続時に自動ALTER
    assert rows and rows[0]["last_exported_at"] is None
    # マイグレーション後もマークできる
    store.mark_contract_invoice_exported(rows[0]["id"], db_path=db, now="2026-07-16T10:00:00")
    rows = store.list_contract_invoices(db_path=db)
    assert rows[0]["last_exported_at"] == "2026-07-16T10:00:00"


def test_contract_invoice_stores_pay_type_snapshot(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    pid = store.add_project("関西ぱど：京阪北版", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3, "unit_price": 8000, "remark": "配布",
          "copies": 3713}],
        pay_type="日当", db_path=db)
    detail = store.get_contract_invoice(iid, db_path=db)
    assert detail["invoice"]["pay_type"] == "日当"
    assert detail["lines"][0]["copies"] == 3713
    assert detail["lines"][0]["amount"] == 3 * 8000


def test_contract_invoice_pay_type_survives_master_change(tmp_path):
    """登録後にマスタの支払形態を変えても、過去の請求の支払形態は変わらない。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    pid = store.add_project("案件", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3, "unit_price": 8000, "remark": "配布"}],
        pay_type="日当", db_path=db)
    store.update_distributor(did, pay_type="歩合", db_path=db)
    assert store.get_contract_invoice(iid, db_path=db)["invoice"]["pay_type"] == "日当"


def test_contract_invoice_without_pay_type_is_null(tmp_path):
    """pay_type を渡さない既存の呼び出しは NULL のまま(=歩合扱い・後方互換)。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", db_path=db)
    pid = store.add_project("案件", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3713, "unit_price": 2.5, "remark": "配布"}],
        db_path=db)
    detail = store.get_contract_invoice(iid, db_path=db)
    assert detail["invoice"]["pay_type"] is None
    assert detail["lines"][0]["copies"] is None


def test_distributor_stores_bank_and_pay_type(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor(
        "山田太郎", kind="業務委託",
        bank_info="三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ",
        pay_type="日当", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["bank_info"] == "三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ"
    assert row["pay_type"] == "日当"
    assert row["kind"] == "業務委託"


def test_distributor_hourly_and_monthly_rate(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    h = store.add_distributor("時給の人", pay_type="時給", hourly_rate=1200, db_path=db)
    m = store.add_distributor("月給の人", pay_type="月給", monthly_rate=250000, db_path=db)
    rows = {r["id"]: r for r in store.list_distributors(db_path=db)}
    assert rows[h]["hourly_rate"] == 1200
    assert rows[m]["monthly_rate"] == 250000


def test_update_distributor_changes_pay_type_and_bank(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.update_distributor(did, pay_type="歩合", bank_info="ゆうちょ 12345", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["pay_type"] == "歩合"
    assert row["bank_info"] == "ゆうちょ 12345"


def test_old_distributors_table_gets_new_columns(tmp_path):
    """第2弾までの列しかない旧DBを開いても壊れず、新しい列が足されること。"""
    import sqlite3
    db = os.path.join(tmp_path, "old.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE distributors (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '業務委託',"
                 " active INTEGER NOT NULL DEFAULT 1)")
    conn.execute("INSERT INTO distributors (name) VALUES ('既存の人')")
    conn.commit()
    conn.close()
    rows = store.list_distributors(db_path=db)
    assert rows[0]["name"] == "既存の人"
    assert rows[0]["pay_type"] is None
    assert rows[0]["bank_info"] is None
    assert rows[0]["hourly_rate"] is None
    assert rows[0]["monthly_rate"] is None


def test_update_distributor_normalizes_hourly_and_monthly_rate(tmp_path):
    """add_distributor 同様、update_distributor でも文字列の数値を int に正規化すること。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="時給", hourly_rate=1000, db_path=db)
    store.update_distributor(did, hourly_rate="1500", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["hourly_rate"] == 1500
    assert isinstance(row["hourly_rate"], int)


def test_update_distributor_leaves_rate_unchanged_when_not_passed(tmp_path):
    """_UNSET の番兵が効いていること。他のフィールドだけ更新しても hourly_rate は変わらない。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="時給", hourly_rate=1200, db_path=db)
    store.update_distributor(did, name="別名", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["name"] == "別名"
    assert row["hourly_rate"] == 1200


def test_daily_rates_replace_and_list(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "丁合・配布", "amount": 8000},
                                    {"work_name": "ポスティング", "amount": 7500}], db_path=db)
    rows = store.list_daily_rates(did, db_path=db)
    assert [(r["work_name"], r["amount"]) for r in rows] == [
        ("丁合・配布", 8000), ("ポスティング", 7500)]


def test_daily_rates_replace_overwrites_previous(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "丁合・配布", "amount": 8000}], db_path=db)
    store.replace_daily_rates(did, [{"work_name": "丁合・配布", "amount": 9000}], db_path=db)
    rows = store.list_daily_rates(did, db_path=db)
    assert len(rows) == 1
    assert rows[0]["amount"] == 9000


def test_daily_rates_are_per_distributor(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    a = store.add_distributor("Aさん", pay_type="日当", db_path=db)
    b = store.add_distributor("Bさん", pay_type="日当", db_path=db)
    store.replace_daily_rates(a, [{"work_name": "配布", "amount": 8000}], db_path=db)
    store.replace_daily_rates(b, [{"work_name": "配布", "amount": 6000}], db_path=db)
    assert store.list_daily_rates(a, db_path=db)[0]["amount"] == 8000
    assert store.list_daily_rates(b, db_path=db)[0]["amount"] == 6000


def test_replace_daily_rates_with_empty_clears(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "配布", "amount": 8000}], db_path=db)
    store.replace_daily_rates(did, [], db_path=db)
    assert store.list_daily_rates(did, db_path=db) == []


def test_count_master_usage_project_counts_all_sources(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("案件", db_path=db)
    did = store.add_distributor("山田太郎", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, project_id=pid, db_path=db)
    store.add_payable(None, None, 8000, date="2026-07-17", project_id=pid, db_path=db)
    store.add_receivable("2026-07", None, 90000, project_id=pid, db_path=db)
    store.add_issue_manual_cost(pid, "配布", 50000, db_path=db)
    store.add_contract_invoice(did, "2026-07-17", "2026-07-01", "2026-07-15",
                               [{"project_id": pid, "report_qty": 1, "unit_price": 100,
                                 "remark": "配布"}], db_path=db)
    assert store.count_master_usage("project", pid, db_path=db) == 5


def test_count_master_usage_zero_for_unused(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("使っていない案件", db_path=db)
    did = store.add_distributor("使っていない人", db_path=db)
    cid = store.add_expense_category("使っていない費目", db_path=db)
    assert store.count_master_usage("project", pid, db_path=db) == 0
    assert store.count_master_usage("distributor", did, db_path=db) == 0
    assert store.count_master_usage("expense_category", cid, db_path=db) == 0


def test_count_master_usage_distributor_counts_invoices_and_petty(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", db_path=db)
    pid = store.add_project("案件", db_path=db)
    store.add_contract_invoice(did, "2026-07-17", "2026-07-01", "2026-07-15",
                               [{"project_id": pid, "report_qty": 1, "unit_price": 100,
                                 "remark": "配布"}], db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    assert store.count_master_usage("distributor", did, db_path=db) == 2


def test_count_master_usage_category_and_client(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    cid = store.add_expense_category("駐車場代", db_path=db)
    clid = store.add_receivables_client("株式会社アド・バリュー", db_path=db)
    vid = store.add_payables_vendor("関西電力株式会社", db_path=db)
    store.add_petty_cash("2026-07-17", cid, 1500, db_path=db)
    store.add_receivable("2026-07", clid, 90000, db_path=db)
    store.add_payable("2026-07", vid, 8000, db_path=db)
    assert store.count_master_usage("expense_category", cid, db_path=db) == 1
    assert store.count_master_usage("receivables_client", clid, db_path=db) == 1
    assert store.count_master_usage("payables_vendor", vid, db_path=db) == 1


def test_count_master_usage_rejects_unknown_master(tmp_path):
    import pytest
    db = os.path.join(tmp_path, "t.db")
    with pytest.raises(ValueError):
        store.count_master_usage("知らないマスタ", 1, db_path=db)
