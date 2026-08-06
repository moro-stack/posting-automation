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


# ---- 支払形態に応じた単位 ----
def test_unit_for_without_pay_type_keeps_current_behavior():
    """既存の呼び出し(pay_type なし)は今までと同じ。"""
    assert L.unit_for("配布") == "枚"
    assert L.unit_for("挟み込み") == "枚"
    assert L.unit_for("交通費") == "一式"
    assert L.unit_for("手当") == "一式"
    assert L.unit_for("その他") == "一式"


def test_unit_for_by_pay_type_on_delivery_rows():
    assert L.unit_for("配布", "日当") == "日"
    assert L.unit_for("配布", "時給") == "時間"
    assert L.unit_for("配布", "月給") == "一式"
    assert L.unit_for("配布", "歩合") == "枚"
    assert L.unit_for("挟み込み", "日当") == "日"


def test_unit_for_non_delivery_rows_ignore_pay_type():
    """日当の人でも交通費・手当の行は「一式」。支払形態で一律に上書きしない。"""
    for pt in ("日当", "時給", "月給", "歩合", None):
        assert L.unit_for("交通費", pt) == "一式"
        assert L.unit_for("手当", pt) == "一式"
        assert L.unit_for("その他", pt) == "一式"


def test_qty_label_with_pay_type():
    assert L.qty_label(3, "配布", "日当") == "3 日"
    assert L.qty_label(6.5, "配布", "時給") == "6.5 時間"
    assert L.qty_label(1, "配布", "月給") == "一式"
    assert L.qty_label(3713, "配布", "歩合") == "3,713 枚"


def test_qty_label_without_pay_type_keeps_current_behavior():
    assert L.qty_label(3713, "配布") == "3,713 枚"
    assert L.qty_label(1, "交通費") == "一式"


# ---- 配布部数 ----
def test_line_copies_uses_qty_for_houbai_and_none():
    line = {"report_qty": 3713, "copies": 999, "remark": "配布"}
    assert L.line_copies(line, "歩合") == 3713
    assert L.line_copies(line, None) == 3713


def test_line_copies_uses_copies_column_for_other_pay_types():
    line = {"report_qty": 3, "copies": 3713, "remark": "配布"}
    assert L.line_copies(line, "日当") == 3713
    assert L.line_copies(line, "時給") == 3713
    assert L.line_copies(line, "月給") == 3713


def test_line_copies_is_zero_when_copies_missing():
    assert L.line_copies({"report_qty": 3, "remark": "配布"}, "日当") == 0
    assert L.line_copies({"report_qty": 3, "copies": None, "remark": "配布"}, "日当") == 0


def test_line_copies_is_zero_for_non_delivery_rows():
    assert L.line_copies({"report_qty": 1, "copies": 500, "remark": "交通費"}, "日当") == 0
    assert L.line_copies({"report_qty": 1, "remark": "手当"}, "歩合") == 0


def test_delivered_copies_without_pay_type_keeps_current_behavior():
    lines = [
        {"report_qty": 3713, "remark": "配布"},
        {"report_qty": 500, "remark": "挟み込み"},
        {"report_qty": 1, "remark": "交通費"},
    ]
    assert L.delivered_copies(lines) == 3713 + 500


def test_delivered_copies_for_nichito_uses_copies_column():
    lines = [
        {"report_qty": 3, "copies": 3713, "remark": "配布"},
        {"report_qty": 1, "copies": 500, "remark": "挟み込み"},
        {"report_qty": 1, "copies": 99, "remark": "交通費"},
    ]
    assert L.delivered_copies(lines, "日当") == 3713 + 500


# ---- unit_for と line_copies で未知の pay_type の解釈を揃える(レビュー指摘の回帰防止) ----
def test_line_copies_treats_unknown_pay_type_as_houbai():
    """空文字・未知の文字列は歩合扱い(=report_qty をそのまま部数にする)。
    unit_for 側も同じ未知の値で「枚」に倒れるので、ここが逆(copies列)に倒れると
    画面表示(枚数)と報告部数が食い違う。"""
    line = {"report_qty": 3713, "copies": 999, "remark": "配布"}
    assert L.line_copies(line, "") == 3713
    assert L.line_copies(line, "未知の形態") == 3713


def test_unit_for_agrees_with_line_copies_on_unknown_pay_type():
    """unit_for と line_copies が同じ pay_type に対して逆の解釈をしないことの確認。"""
    line = {"report_qty": 3713, "copies": 999, "remark": "配布"}
    for pay_type in ("", "未知の形態"):
        assert L.unit_for("配布", pay_type) == "枚"
        assert L.line_copies(line, pay_type) == 3713


def test_delivered_copies_empty_string_pay_type_keeps_current_behavior():
    """画面から来がちな空文字の pay_type でも delivered_copies は歩合(現行動作)のまま。"""
    lines = [
        {"report_qty": 3713, "copies": 999, "remark": "配布"},
        {"report_qty": 500, "copies": 1, "remark": "挟み込み"},
        {"report_qty": 1, "copies": 500, "remark": "交通費"},
    ]
    assert L.delivered_copies(lines, "") == 3713 + 500


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


def test_days_since_today_and_past_and_none():
    assert L.days_since("2026-07-16", today="2026-07-16") == 0
    assert L.days_since("2026-07-13", today="2026-07-16") == 3
    assert L.days_since("2026-07-16T09:00:00", today="2026-07-16") == 0   # ISO日時もOK
    assert L.days_since(None, today="2026-07-16") is None
    assert L.days_since("", today="2026-07-16") is None
    assert L.days_since("こわれた日付", today="2026-07-16") is None


# ---- 買掛の原本区分オートセット ----
_VENDORS = [
    {"name": "関西電力株式会社", "default_original_status": "振込用紙"},
    {"name": "株式会社スペースリーダー", "default_original_status": "クレジット"},
    {"name": "既定なしの会社", "default_original_status": None},
]


def test_resolve_original_status_matches_by_name():
    assert L.resolve_original_status("関西電力株式会社", _VENDORS) == "振込用紙"
    assert L.resolve_original_status("株式会社スペースリーダー", _VENDORS) == "クレジット"


def test_resolve_original_status_trims_whitespace():
    assert L.resolve_original_status("  関西電力株式会社 ", _VENDORS) == "振込用紙"


def test_resolve_original_status_returns_none_when_no_match():
    assert L.resolve_original_status("知らない会社", _VENDORS) is None
    assert L.resolve_original_status("", _VENDORS) is None
    assert L.resolve_original_status(None, _VENDORS) is None


def test_resolve_original_status_returns_none_when_master_has_no_default():
    assert L.resolve_original_status("既定なしの会社", _VENDORS) is None


# ---- マスタ削除 or 停止中 ----
def test_master_delete_action_deletes_when_unused():
    assert L.master_delete_action(0) == "delete"


def test_master_delete_action_deactivates_when_used():
    assert L.master_delete_action(1) == "deactivate"
    assert L.master_delete_action(12) == "deactivate"


def test_master_delete_action_deactivates_when_usage_count_is_none():
    """使用件数が不明(None)なときに安易に0とみなして削除可にしてはいけない(安全側)。"""
    assert L.master_delete_action(None) == "deactivate"


def test_master_delete_action_deactivates_on_invalid_type():
    """型不正の値も安全側(消さない)に倒す。"""
    assert L.master_delete_action("abc") == "deactivate"


def test_master_delete_action_deactivates_on_negative_value():
    """ありえない負値も安全側(消さない)に倒す。"""
    assert L.master_delete_action(-1) == "deactivate"


def test_master_row_subtitle_distributor():
    row = {"kind": "業務委託", "pay_type": "歩合"}
    assert L.master_row_subtitle("distributor", row) == "業務委託・歩合"


def test_master_row_subtitle_distributor_partial():
    assert L.master_row_subtitle("distributor", {"kind": "自社社員", "pay_type": None}) == "自社社員"


def test_master_row_subtitle_vendor():
    row = {"default_category": "家賃", "default_original_status": "本社"}
    assert L.master_row_subtitle("payables_vendor", row) == "家賃 / 本社"


def test_master_row_subtitle_vendor_empty():
    assert L.master_row_subtitle("payables_vendor", {"default_category": None, "default_original_status": None}) == ""


def test_master_row_subtitle_other_master():
    assert L.master_row_subtitle("project", {"name": "A社チラシ"}) == ""


# ---- 選択行のid抽出・Excel用行 ----
import pandas as pd


def test_selected_ids_from_editor():
    df = pd.DataFrame([
        {"選択": True, "No.": 3, "金額": "¥1"},
        {"選択": False, "No.": 2, "金額": "¥2"},
        {"選択": True, "No.": 5, "金額": "¥3"},
    ])
    assert L.selected_ids_from_editor(df) == [3, 5]


def test_selected_ids_empty_when_none_checked():
    df = pd.DataFrame([{"選択": False, "No.": 1}])
    assert L.selected_ids_from_editor(df) == []


def test_rows_for_excel_drops_select_col():
    df = pd.DataFrame([
        {"選択": True, "No.": 3, "金額": "¥1"},
        {"選択": False, "No.": 2, "金額": "¥2"},
    ])
    rows = L.rows_for_excel(df)
    assert rows == [{"No.": 3, "金額": "¥1"}]


def test_print_total_sums_yen_formatted_amounts():
    """印刷の合計。表示用の「¥1,234」形式をパースして合計する。"""
    rows = [{"No.": 1, "金額": "¥3,200"}, {"No.": 2, "金額": "¥980"}]
    assert L.print_total(rows) == ("金額", 4180)


def test_print_total_uses_seikyugaku_column_too():
    rows = [{"No.": 1, "請求額": "¥1,000"}, {"No.": 2, "請求額": "¥2,000"}]
    assert L.print_total(rows) == ("請求額", 3000)


def test_print_total_returns_none_without_amount_column():
    assert L.print_total([{"No.": 1, "日付": "2026-08-01"}]) is None


def test_print_total_returns_none_if_any_row_is_unparsable():
    """🔴 1行でも読めなければ合計を出さない。嘘の数字を紙に載せないため。"""
    rows = [{"金額": "¥1,000"}, {"金額": "—"}, {"金額": "¥2,000"}]
    assert L.print_total(rows) is None


def test_print_total_returns_none_for_empty_rows():
    assert L.print_total([]) is None
