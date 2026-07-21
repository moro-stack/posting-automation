import os

from common import posting_store as store


def seed_for_boot(*, db_path=None) -> bool:
    """起動時のseed。DEMO_MODE なら架空データ(実名を出さない)、そうでなければ実マスタpreset。
    実名preset(関西ぱど等)がデモに漏れないための分岐をここに集約し、テストで守る。"""
    if os.environ.get("DEMO_MODE"):
        return seed_demo_if_empty(db_path=db_path)
    store.seed_masters(db_path=db_path)
    return False


def seed_demo_if_empty(*, db_path=None) -> bool:
    """デモ用の架空データを投入する。既に取引があれば何もしない(冪等)。実名は使わない。"""
    if (store.list_contract_invoices(db_path=db_path)
            or store.list_petty_cash(db_path=db_path)
            or store.list_receivables(db_path=db_path)
            or store.list_payables(db_path=db_path)):
        return False

    # --- 架空マスタ ---
    projA = store.add_project("デモ配布A号", db_path=db_path)
    projB = store.add_project("デモ配布B号", db_path=db_path)
    catP = store.add_expense_category("駐車場代", db_path=db_path)
    catD = store.add_expense_category("飲み物代", db_path=db_path)
    venR = store.add_payables_vendor("デモ不動産（家賃）", db_path=db_path)
    venE = store.add_payables_vendor("デモ電力", db_path=db_path)
    cliX = store.add_receivables_client("デモ広告主X", db_path=db_path)
    cliY = store.add_receivables_client("デモ広告主Y", db_path=db_path)
    dTaro = store.add_distributor("デモ太郎", pay_type="歩合", db_path=db_path)
    dHana = store.add_distributor("デモ花子", pay_type="日当", db_path=db_path)

    # --- 架空取引 ---
    # 売上(売掛)
    store.add_receivable("2026-07", cliX, 180000, project_id=projA, db_path=db_path)
    store.add_receivable("2026-07", cliY, 120000, project_id=projB, db_path=db_path)
    # 買掛(共通費)
    store.add_payable("2026-07", venR, 80000, date="2026-07-05", project_id=projA, db_path=db_path)
    store.add_payable("2026-07", venE, 15000, date="2026-07-06", project_id=projB, db_path=db_path)
    # 小口
    store.add_petty_cash("2026-07-03", catP, 2000, project_id=projA, memo="現場駐車", db_path=db_path)
    store.add_petty_cash("2026-07-04", catD, 1500, project_id=projA, memo="お茶", db_path=db_path)
    # 業務委託(配布員代)
    store.add_contract_invoice(dTaro, "2026-07-08", "2026-07-01", "2026-07-05",
        [{"project_id": projA, "report_qty": 3000, "unit_price": 3.5, "remark": "配布",
          "other_label": None, "copies": 3000}], pay_type="歩合", db_path=db_path)
    store.add_contract_invoice(dHana, "2026-07-09", "2026-07-02", "2026-07-03",
        [{"project_id": projB, "report_qty": 2, "unit_price": 8000, "remark": "配布",
          "other_label": None, "copies": 1800}], pay_type="日当", db_path=db_path)
    # 直接入力(配布員代)
    store.add_issue_manual_cost(projA, "丁合作業", 12000, work_date="2026-07-07", db_path=db_path)
    return True
