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


# ===== 案件別 原価・売上（依頼②・2026-08-20） =====


def test_company_summary_by_project_groups_by_project():
    rows = L.company_summary_by_project(
        receivables=[{"project_id": 1, "amount": 1000}, {"project_id": 2, "amount": 500}],
        payables=[], petty=[{"project_id": 1, "amount": 300}],
        contract_lines=[], manual=[],
        id2proj={1: "京阪南", 2: "京阪北"})
    by_name = {r["案件"]: r for r in rows}
    assert by_name["京阪南"] == {"案件": "京阪南", "区分": None, "売上": 1000,
                               "原価": 300, "利益": 700}
    assert by_name["京阪北"] == {"案件": "京阪北", "区分": None, "売上": 500,
                               "原価": 0, "利益": 500}


def test_company_summary_by_project_splits_advalue_by_other_label():
    """アドバリューだけは、号別明細と同じく案件区分(8-1等)ごとに分けて出す。"""
    rows = L.company_summary_by_project(
        receivables=[{"project_id": 9, "other_label": "8-1", "amount": 495427},
                    {"project_id": 9, "other_label": "8-2", "amount": 194969}],
        payables=[], petty=[{"project_id": 9, "other_label": "8-1", "amount": 177540}],
        contract_lines=[], manual=[],
        id2proj={9: "アドバリュー"})
    assert len(rows) == 2
    by_label = {r["区分"]: r for r in rows}
    assert by_label["8-1"]["売上"] == 495427 and by_label["8-1"]["原価"] == 177540
    assert by_label["8-2"]["売上"] == 194969 and by_label["8-2"]["原価"] == 0
    assert all(r["案件"] == "アドバリュー" for r in rows)


def test_company_summary_by_project_other_projects_ignore_other_label():
    """アドバリュー以外は区分を持っていても無視し、案件単位で合算する
    (『その他』のother_labelは"何の案件か"という別の意味で使われているため)。"""
    rows = L.company_summary_by_project(
        receivables=[{"project_id": 5, "other_label": "配夢", "amount": 1000},
                    {"project_id": 5, "other_label": "買取専科", "amount": 2000}],
        payables=[], petty=[], contract_lines=[], manual=[],
        id2proj={5: "その他"})
    assert len(rows) == 1
    assert rows[0] == {"案件": "その他", "区分": None, "売上": 3000, "原価": 0, "利益": 3000}


def test_company_summary_by_project_is_sorted_by_project_then_label():
    rows = L.company_summary_by_project(
        receivables=[{"project_id": 9, "other_label": "8-2", "amount": 1},
                    {"project_id": 9, "other_label": "8-1", "amount": 1},
                    {"project_id": 1, "amount": 1}],
        payables=[], petty=[], contract_lines=[], manual=[],
        id2proj={9: "アドバリュー", 1: "京阪南"})
    assert [(r["案件"], r["区分"]) for r in rows] == [
        ("アドバリュー", "8-1"), ("アドバリュー", "8-2"), ("京阪南", None)]


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


# ===== 大阪支社売上ページ（依頼⑧・2026-08-27 大橋様） =====


def test_delivery_counts_sums_haifu_and_hasamikomi_separately():
    """配布部数（冊子・チラシ）と挟み込み数を分けて数える。"""
    lines = [
        {"remark": "配布", "report_qty": 3000, "pay_type": "歩合"},
        {"remark": "配布", "report_qty": 1500, "pay_type": "歩合"},
        {"remark": "挟み込み", "report_qty": 800, "pay_type": "歩合"},
    ]
    assert L.delivery_counts(lines) == {"配布": 4500, "挟み込み": 800}


def test_delivery_counts_ignores_rows_that_are_not_deliveries():
    """交通費・手当・その他は部数ではないので数えない。"""
    lines = [
        {"remark": "配布", "report_qty": 100, "pay_type": "歩合"},
        {"remark": "交通費", "report_qty": 5, "pay_type": "歩合"},
        {"remark": "手当", "report_qty": 3, "pay_type": "歩合"},
        {"remark": "その他", "report_qty": 9, "pay_type": "歩合"},
    ]
    assert L.delivery_counts(lines) == {"配布": 100, "挟み込み": 0}


def test_delivery_counts_uses_copies_for_non_commission_pay_types():
    """🔴 日当・時給・月給は数量が日数/時間なので、部数は copies 列を使う。
    ここを report_qty のまま数えると「3日＝3部」という嘘の部数になる。"""
    lines = [{"remark": "配布", "report_qty": 3, "copies": 1800, "pay_type": "日当"}]
    assert L.delivery_counts(lines)["配布"] == 1800


def test_delivery_counts_on_empty_input():
    assert L.delivery_counts([]) == {"配布": 0, "挟み込み": 0}
    assert L.delivery_counts(None) == {"配布": 0, "挟み込み": 0}


def _rows(*pairs):
    return [{"案件": name, "区分": label, "売上": 0, "原価": 0, "利益": 0}
            for name, label in pairs]


def test_sort_project_summary_rows_uses_the_order_ohashi_san_asked_for():
    """関西ぱど → アドバリュー → リビング → その他 → 空白（区分未設定）。"""
    rows = _rows(("その他", None), ("リビングプロシード", None),
                 ("アドバリュー", "8-1"), ("関西ぱど：京阪北版", None), ("", None))
    got = [r["案件"] for r in L.sort_project_summary_rows(rows)]
    assert got == ["関西ぱど：京阪北版", "アドバリュー", "リビングプロシード", "その他", ""]


def test_sort_project_summary_rows_keeps_kansai_pado_versions_together():
    rows = _rows(("関西ぱど：京阪南版", None), ("アドバリュー", "8-1"),
                 ("関西ぱど：京阪北版", None))
    got = [r["案件"] for r in L.sort_project_summary_rows(rows)]
    assert got[:2] == ["関西ぱど：京阪北版", "関西ぱど：京阪南版"]


def test_sort_project_summary_rows_orders_advalue_weeks_by_month_then_week():
    """🔴 文字列順だと 10-1 が 8-1 より前に来る。"""
    rows = _rows(("アドバリュー", "10-1"), ("アドバリュー", "8-2"),
                 ("アドバリュー", "9-1"), ("アドバリュー", "8-1"))
    got = [r["区分"] for r in L.sort_project_summary_rows(rows)]
    assert got == ["8-1", "8-2", "9-1", "10-1"]


def test_sort_project_summary_rows_puts_unknown_projects_before_the_blank_one():
    """🔴 取りこぼしゼロ。案件マスタが増えても行が消えない。"""
    rows = _rows(("", None), ("新しい案件", None), ("その他", None))
    got = [r["案件"] for r in L.sort_project_summary_rows(rows)]
    assert got == ["その他", "新しい案件", ""]


def test_sort_project_summary_rows_loses_no_row():
    rows = _rows(("その他", None), ("", None), ("アドバリュー", "8-1"),
                 ("関西ぱど：京阪北版", None), ("知らない", None))
    assert len(L.sort_project_summary_rows(rows)) == len(rows)
