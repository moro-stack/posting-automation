"""配布コストの集計ロジック(純粋関数)。DB非依存でテスト可能。"""

_DELIVERY_REMARKS = ("配布", "挟み込み")


def delivered_copies(lines) -> int:
    return sum(int(l.get("report_qty") or 0)
               for l in lines if l.get("remark") in _DELIVERY_REMARKS)


def invoice_total(lines) -> int:
    return sum(int(l.get("amount") or 0) for l in lines)


def _sum_for_project(rows, project_id) -> int:
    return sum(int(r.get("amount") or 0) for r in rows
               if r.get("project_id") == project_id)


def aggregate_issue(project_id, *, petty, payables, contract_lines, manual) -> dict:
    p = _sum_for_project(petty, project_id)
    pay = _sum_for_project(payables, project_id)
    con = _sum_for_project(contract_lines, project_id)
    man = _sum_for_project(manual, project_id)
    return {"petty": p, "payables": pay, "contract": con, "manual": man,
            "total": p + pay + con + man}


def issue_balance(cost_total, receivable_total) -> int:
    return int(receivable_total) - int(cost_total)
