"""配布コストの集計ロジック(純粋関数)。DB非依存でテスト可能。"""
import calendar
from datetime import date, datetime, timedelta

_DELIVERY_REMARKS = ("配布", "挟み込み")


def _num(value):
    """None/空を0にしつつ、小数はそのまま保持する数値化。"""
    if value is None or value == "":
        return 0
    return float(value)


def is_delivery(remark) -> bool:
    """部数を数える種別(配布・挟み込み)か。交通費・手当・その他は数えないので False。"""
    return remark in _DELIVERY_REMARKS


def unit_for(remark) -> str:
    """種別に応じた数量の単位。配布・挟み込みは『枚』、それ以外は『一式』。"""
    return "枚" if is_delivery(remark) else "一式"


def qty_label(qty, remark) -> str:
    """明細の数量表示。配布・挟み込みは『3,713 枚』。
    交通費・手当・その他は数を数えないので『一式』だけを出す(「1 一式」とは出さない)。"""
    if is_delivery(remark):
        return f"{fmt_num(qty)} {unit_for(remark)}"
    return unit_for(remark)


def fmt_num(value) -> str:
    """数値を3桁区切りで整形。小数は末尾の0を落とす(3713.0→3,713、3.5→3.5)。"""
    f = float(value or 0)
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.2f}".rstrip("0").rstrip(".")


def _today(today):
    if today is None:
        return date.today()
    if isinstance(today, str):
        return datetime.strptime(today[:10], "%Y-%m-%d").date()
    return today


def period_range(preset, *, today=None):
    """期間プリセット名から (開始, 終了) の YYYY-MM-DD 文字列を返す。全期間は (None, None)。"""
    t = _today(today)
    if preset == "all":
        return (None, None)
    if preset == "year":
        return (f"{t.year}-01-01", f"{t.year}-12-31")
    if preset == "month":
        last = calendar.monthrange(t.year, t.month)[1]
        return (f"{t.year}-{t.month:02d}-01", f"{t.year}-{t.month:02d}-{last:02d}")
    if preset == "week":
        monday = t - timedelta(days=t.weekday())
        sunday = monday + timedelta(days=6)
        return (monday.isoformat(), sunday.isoformat())
    raise ValueError(f"unknown preset: {preset}")


def in_period(value, lo, hi) -> bool:
    """value(YYYY-MM-DD もしくは月度 YYYY-MM もしくは None)が [lo, hi] と重なるか。
    lo/hi がどちらも None(全期間)なら常に True。範囲指定時、value が None なら False。"""
    if not lo and not hi:
        return True
    if not value:
        return False
    v = str(value)
    start = v if len(v) >= 10 else f"{v}-01"        # 月度は月初
    end = v if len(v) >= 10 else f"{v}-31"          # 月度は月末(31で上限比較)
    if lo and end < lo:
        return False
    if hi and start > hi:
        return False
    return True


def filter_rows_by_period(rows, key, lo, hi):
    """rows のうち row[key] の日付が [lo, hi] と重なる行だけ返す。"""
    return [r for r in rows if in_period(r.get(key), lo, hi)]


def delivered_copies(lines):
    return sum(_num(l.get("report_qty"))
               for l in lines if l.get("remark") in _DELIVERY_REMARKS)


def invoice_total(lines):
    return sum(_num(l.get("amount")) for l in lines)


def _sum_for_project(rows, project_id):
    return sum(_num(r.get("amount")) for r in rows
               if r.get("project_id") == project_id)


def aggregate_issue(project_id, *, petty, payables, contract_lines, manual) -> dict:
    p = _sum_for_project(petty, project_id)
    pay = _sum_for_project(payables, project_id)
    con = _sum_for_project(contract_lines, project_id)
    man = _sum_for_project(manual, project_id)
    return {"petty": p, "payables": pay, "contract": con, "manual": man,
            "total": p + pay + con + man}


def issue_balance(cost_total, receivable_total):
    return _num(receivable_total) - _num(cost_total)


def payment_method(kind, row) -> str:
    """雑費の支払方法ラベル。kind: 'petty'(小口=現金) / 'payable'(買掛=原本区分から判定)。"""
    if kind == "petty":
        return "現金"
    status = str((row or {}).get("original_status") or "")
    if "クレジット" in status:
        return "クレジット"
    if "振込" in status:
        return "振込"
    return "買掛"


def cost_groups(agg) -> dict:
    """aggregate_issue の結果を新レイアウトへ再編。
    配布員代=業務委託+直接入力(manual)、雑費=小口+買掛、配布原価=両者の和(=total)。"""
    labor = _num(agg.get("contract")) + _num(agg.get("manual"))
    misc = _num(agg.get("petty")) + _num(agg.get("payables"))
    return {"labor": labor, "misc": misc, "genka": labor + misc}
