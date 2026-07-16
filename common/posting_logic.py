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


def days_since(iso_str, *, today=None):
    """iso_str(YYYY-MM-DD もしくは ISO日時)から today まで何日経ったかを返す。
    空・不正な日付は None。today 省略時は当日。"""
    if not iso_str:
        return None
    try:
        d = datetime.strptime(str(iso_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (_today(today) - d).days


def issue_breakdown_rows(project_id, *, petty, payables, receivables,
                         contract_lines, manual, category_names=None, vendor_names=None):
    """号(案件)の中身を1データ=1行に正規化した内訳を返す。
    「その他」号に何を入れたか(内容ラベル)を一覧で見えるようにするのが目的。
    各行 = {区分, 内容, 金額, 日付}。並び順は 売上 → 原価(小口→買掛→業務委託→直接入力)。
    金額は数値(表示整形は呼び出し側)。DB非依存の純関数。"""
    cats = category_names or {}
    vends = vendor_names or {}
    rows = []

    def _match(r):
        return r.get("project_id") == project_id

    # 売上(売掛)
    for r in receivables:
        if _match(r):
            rows.append({"区分": "売上", "内容": r.get("note") or "（内容なし）",
                         "金額": _num(r.get("amount")), "日付": r.get("month") or ""})
    # 原価・小口(内容 = メモ。費目名があれば接頭に付す)
    for r in petty:
        if not _match(r):
            continue
        cat = cats.get(r.get("category_id"), "")
        memo = r.get("memo") or ""
        label = f"{cat}（{memo}）" if cat and memo else (memo or cat or "小口")
        rows.append({"区分": "原価・小口", "内容": label,
                     "金額": _num(r.get("amount")), "日付": r.get("date") or ""})
    # 原価・買掛(内容 = 備考、無ければ取引先名)
    for r in payables:
        if not _match(r):
            continue
        label = r.get("note") or r.get("vendor_name") or vends.get(r.get("vendor_id"), "") or "買掛"
        rows.append({"区分": "原価・買掛", "内容": label,
                     "金額": _num(r.get("amount")), "日付": r.get("date") or r.get("month") or ""})
    # 原価・業務委託(内容 = 種別。日付は請求の発行日=issue_date を呼び出し側で付与)
    for l in contract_lines:
        if not _match(l):
            continue
        rows.append({"区分": "原価・業務委託", "内容": l.get("remark") or "業務委託",
                     "金額": _num(l.get("amount")), "日付": l.get("issue_date") or ""})
    # 原価・直接入力(内容 = 作業内容)
    for r in manual:
        if not _match(r):
            continue
        rows.append({"区分": "原価・直接入力", "内容": r.get("content") or "配布",
                     "金額": _num(r.get("amount")), "日付": r.get("work_date") or ""})
    return rows
