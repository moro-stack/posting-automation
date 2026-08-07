from common import posting_logic as L


def test_company_summary_totals():
    r = L.company_summary_totals(
        receivables=[{"amount": 1000}, {"amount": 500}],
        payables=[{"amount": 300}], petty=[{"amount": 200}],
        contract_lines=[{"amount": 400}], manual=[{"amount": 100}])
    assert r["sales"] == 1500
    assert r["cost"] == 1000          # 300+200+400+100
    assert r["profit"] == 500


def test_company_summary_rows_classifies_and_resolves_names():
    rows = L.company_summary_rows(
        receivables=[{"month": "2026-07", "client_id": 1, "project_id": 9, "amount": 1000}],
        payables=[{"date": "2026-07-03", "vendor_name": "大家", "project_id": 9, "amount": 300}],
        petty=[{"date": "2026-07-04", "category_id": 2, "project_id": 9, "amount": 200, "memo": "茶"}],
        contract_lines=[{"issue_date": "2026-07-05", "distributor_id": 3, "project_id": 9, "amount": 400}],
        manual=[{"work_date": "2026-07-06", "content": "配布", "project_id": 9, "amount": 100}],
        id2proj={9: "A号"}, id2vendor={}, id2cat={2: "飲料"}, id2client={1: "クライアントX"},
        id2dist={3: "山田"})
    kinds = {row["区分"] for row in rows}
    assert kinds == {"売上", "買掛", "小口", "業務委託", "直接入力"}
    sales = [r for r in rows if r["区分"] == "売上"][0]
    assert sales["項目"] == "クライアントX" and sales["案件"] == "A号" and sales["金額"] == 1000
    pay = [r for r in rows if r["区分"] == "買掛"][0]
    assert pay["項目"] == "大家" and pay["日付"] == "2026-07-03"
    dist = [r for r in rows if r["区分"] == "業務委託"][0]
    assert dist["項目"] == "山田" and dist["日付"] == "2026-07-05"


# ===== 原価/売上のタブ分け(2026-08-07) =====


def _all_kinds_rows():
    """company_summary_rows が返しうる区分を全種類ぶん作る。"""
    return L.company_summary_rows(
        receivables=[{"month": "2026-08", "client_id": 1, "amount": 1000}],
        payables=[{"date": "2026-08-01", "vendor_id": 1, "amount": 200}],
        petty=[{"date": "2026-08-02", "category_id": 1, "amount": 30}],
        contract_lines=[{"issue_date": "2026-08-03", "distributor_id": 1, "amount": 4}],
        manual=[{"work_date": "2026-08-04", "content": "直接", "amount": 5}],
        id2proj={}, id2vendor={1: "仕入先"}, id2cat={1: "駐車場代"},
        id2client={1: "得意先"}, id2dist={1: "配布員"})


def test_split_summary_rows_separates_cost_and_sales():
    cost, sales = L.split_summary_rows(_all_kinds_rows())
    assert [r["区分"] for r in sales] == ["売上"]
    assert set(r["区分"] for r in cost) == {"買掛", "小口", "業務委託", "直接入力"}


def test_split_summary_rows_loses_no_row():
    rows = _all_kinds_rows()
    cost, sales = L.split_summary_rows(rows)
    assert len(cost) + len(sales) == len(rows)


def test_every_kind_is_covered_by_a_tab():
    """🔴 取りこぼしゼロ。区分が増えたとき「どちらのタブにも出ない行」を防ぐ。"""
    kinds = {r["区分"] for r in _all_kinds_rows()}
    assert kinds <= set(L.SALES_KINDS) | set(L.COST_KINDS)


def test_sales_and_cost_kinds_do_not_overlap():
    assert not (set(L.SALES_KINDS) & set(L.COST_KINDS))


def test_split_summary_rows_totals_match_company_summary_totals():
    """タブの小計が KPI の数字と一致すること。"""
    receivables = [{"month": "2026-08", "client_id": 1, "amount": 1000}]
    payables = [{"date": "2026-08-01", "vendor_id": 1, "amount": 200}]
    petty = [{"date": "2026-08-02", "category_id": 1, "amount": 30}]
    contract_lines = [{"issue_date": "2026-08-03", "distributor_id": 1, "amount": 4}]
    manual = [{"work_date": "2026-08-04", "content": "直接", "amount": 5}]
    totals = L.company_summary_totals(
        receivables=receivables, payables=payables, petty=petty,
        contract_lines=contract_lines, manual=manual)
    rows = L.company_summary_rows(
        receivables=receivables, payables=payables, petty=petty,
        contract_lines=contract_lines, manual=manual,
        id2proj={}, id2vendor={1: "仕入先"}, id2cat={1: "駐車場代"},
        id2client={1: "得意先"}, id2dist={1: "配布員"})
    cost, sales = L.split_summary_rows(rows)
    assert sum(r["金額"] for r in sales) == totals["sales"]
    assert sum(r["金額"] for r in cost) == totals["cost"]


def test_split_summary_rows_keeps_original_order():
    """並び順は元のまま(タブ内の並べ替えはページ側の責任)。"""
    rows = _all_kinds_rows()
    cost, _ = L.split_summary_rows(rows)
    assert [r["区分"] for r in cost] == [r["区分"] for r in rows if r["区分"] != "売上"]
