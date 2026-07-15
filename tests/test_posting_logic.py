from common import posting_logic as L


def test_delivered_copies_counts_only_haifu_and_hasamikomi():
    lines = [
        {"report_qty": 3713, "remark": "配布"},
        {"report_qty": 500, "remark": "挟み込み"},
        {"report_qty": 1, "remark": "交通費"},
        {"report_qty": 9, "remark": "手当"},
    ]
    assert L.delivered_copies(lines) == 3713 + 500


def test_invoice_total_sums_amount():
    lines = [{"amount": 11139}, {"amount": 540}, {"amount": 2000}]
    assert L.invoice_total(lines) == 13679


def test_aggregate_issue_sums_each_source():
    result = L.aggregate_issue(
        1,
        petty=[{"project_id": 1, "amount": 1200}, {"project_id": 2, "amount": 999}],
        payables=[{"project_id": 1, "amount": 183342}],
        contract_lines=[{"project_id": 1, "amount": 11139}, {"project_id": 1, "amount": 540}],
        manual=[{"project_id": 1, "amount": 8000}],
    )
    assert result["petty"] == 1200
    assert result["payables"] == 183342
    assert result["contract"] == 11139 + 540
    assert result["manual"] == 8000
    assert result["total"] == 1200 + 183342 + 11139 + 540 + 8000


def test_issue_balance():
    assert L.issue_balance(cost_total=200000, receivable_total=290703) == 90703


# ---- 期間フィルタ ----
def test_period_range_all_is_open():
    assert L.period_range("all", today="2026-07-09") == (None, None)


def test_period_range_year():
    assert L.period_range("year", today="2026-07-09") == ("2026-01-01", "2026-12-31")


def test_period_range_month():
    assert L.period_range("month", today="2026-07-09") == ("2026-07-01", "2026-07-31")


def test_period_range_month_february_leap():
    assert L.period_range("month", today="2024-02-15") == ("2024-02-01", "2024-02-29")


def test_period_range_week_is_monday_to_sunday():
    # 2026-07-09 は木曜 → 週は 07-06(月)〜07-12(日)
    assert L.period_range("week", today="2026-07-09") == ("2026-07-06", "2026-07-12")


def test_in_period_full_date_within_and_outside():
    assert L.in_period("2026-07-08", "2026-07-06", "2026-07-12") is True
    assert L.in_period("2026-07-20", "2026-07-06", "2026-07-12") is False


def test_in_period_open_range_includes_everything():
    assert L.in_period("2026-07-08", None, None) is True
    assert L.in_period(None, None, None) is True


def test_in_period_none_value_excluded_when_range_set():
    assert L.in_period(None, "2026-07-01", "2026-07-31") is False


def test_in_period_month_value_overlaps_range():
    # 月度 "2026-07" は 7月のどこかと重なれば含む
    assert L.in_period("2026-07", "2026-07-01", "2026-07-31") is True
    assert L.in_period("2026-07", "2026-06-01", "2026-06-30") is False
    assert L.in_period("2026-07", "2026-07-15", "2026-08-15") is True


# ---- 単位・小数点・整形 ----
def test_unit_for_delivery_is_mai_others_isshiki():
    assert L.unit_for("配布") == "枚"
    assert L.unit_for("挟み込み") == "枚"
    assert L.unit_for("交通費") == "一式"
    assert L.unit_for("手当") == "一式"
    assert L.unit_for("その他") == "一式"


def test_qty_label_shows_count_only_for_delivery():
    """配布・挟み込みは『数量＋枚』。数を数えないものは『一式』だけ(「1 一式」にしない)。"""
    assert L.qty_label(3713, "配布") == "3,713 枚"
    assert L.qty_label(300, "挟み込み") == "300 枚"
    assert L.qty_label(1, "交通費") == "一式"
    assert L.qty_label(1, "手当") == "一式"
    assert L.qty_label(1, "その他") == "一式"


def test_qty_label_isshiki_ignores_quantity():
    """一式ものは数量が1以外でも『一式』のみ。"""
    assert L.qty_label(2, "交通費") == "一式"
    assert L.qty_label(0, "手当") == "一式"


def test_invoice_total_handles_decimals():
    assert L.invoice_total([{"amount": 3.5}, {"amount": 2.25}]) == 5.75


def test_delivered_copies_handles_decimals():
    assert L.delivered_copies([{"report_qty": 3713.5, "remark": "配布"}]) == 3713.5


def test_fmt_num_drops_trailing_zeros_and_adds_commas():
    assert L.fmt_num(3713) == "3,713"
    assert L.fmt_num(3713.0) == "3,713"
    assert L.fmt_num(3.5) == "3.5"
    assert L.fmt_num(1234.5) == "1,234.5"
    assert L.fmt_num(1000000) == "1,000,000"


def test_filter_rows_by_period():
    rows = [
        {"date": "2026-07-08", "amount": 100},
        {"date": "2026-06-30", "amount": 200},
        {"date": None, "amount": 300},
    ]
    got = L.filter_rows_by_period(rows, "date", "2026-07-01", "2026-07-31")
    assert got == [{"date": "2026-07-08", "amount": 100}]
    # 全期間は全件(None日付も含む)
    assert L.filter_rows_by_period(rows, "date", None, None) == rows


def test_payment_method_petty_is_cash():
    assert L.payment_method("petty", {}) == "現金"


def test_payment_method_payable_from_original_status():
    assert L.payment_method("payable", {"original_status": "クレジット"}) == "クレジット"
    assert L.payment_method("payable", {"original_status": "振込用紙"}) == "振込"
    assert L.payment_method("payable", {"original_status": "原本あり"}) == "買掛"
    assert L.payment_method("payable", {}) == "買掛"


def test_cost_groups_regroups_totals():
    agg = {"petty": 1200, "payables": 183342, "contract": 11679, "manual": 8000,
           "total": 1200 + 183342 + 11679 + 8000}
    g = L.cost_groups(agg)
    assert g["labor"] == 11679 + 8000       # 配布員代=業務委託+直接入力
    assert g["misc"] == 1200 + 183342        # 雑費=小口+買掛
    assert g["genka"] == agg["total"]        # 配布原価=総額(不変)
