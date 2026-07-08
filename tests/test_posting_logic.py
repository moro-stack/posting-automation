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
