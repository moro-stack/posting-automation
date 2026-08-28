"""配布コストの集計ロジック(純粋関数)。DB非依存でテスト可能。"""
import calendar
import re
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


# 支払形態ごとの、配布・挟み込み行の数量の単位。
# 歩合(と未設定)は数量がそのまま部数なので「枚」＝これまでの動き。
# 月給は数量を数えない(月額×1)ので「一式」。
_PAY_TYPE_UNITS = {"日当": "日", "時給": "時間", "月給": "一式", "歩合": "枚"}


def unit_for(remark, pay_type=None) -> str:
    """数量の単位。交通費・手当・その他は数を数えないので『一式』(支払形態によらない)。
    配布・挟み込みのときだけ支払形態で単位が変わる(日当=日 / 時給=時間 / 月給=一式 / 歩合=枚)。"""
    if not is_delivery(remark):
        return "一式"
    return _PAY_TYPE_UNITS.get(pay_type, "枚")


def qty_label(qty, remark, pay_type=None) -> str:
    """明細の数量表示。歩合の配布なら『3,713 枚』、日当なら『3 日』。
    単位が『一式』のものは数を数えないので『一式』だけを出す(「1 一式」とは出さない)。"""
    unit = unit_for(remark, pay_type)
    if unit == "一式":
        return unit
    return f"{fmt_num(qty)} {unit}"


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


# ===== 日付の表記をISO(YYYY-MM-DD)に揃える =====
# 🔴 2026-08-28 オーナー指示: 手入力だと必ず表記がズレる。実DBには
#   ・小口の日付   "2026-07/06"
#   ・売掛の月度   "2026/8/28"
# が入っていた。期間の絞り込みは文字列比較なので、揺れると静かに範囲から外れる
# （"2026/8/28" > "2026-09-01" になり、8月のデータが9月より後ろに並ぶ）。
# 画面はカレンダー入力に統一したが、保存の直前でもここで正規化して二重に守る。
_DATE_PARTS_RE = re.compile(r"^\s*(\d{4})\D+(\d{1,2})(?:\D+(\d{1,2}))?")


def _date_parts(value):
    """年・月・日を取り出す。読めなければ None。日が無ければ day は None。"""
    if isinstance(value, (datetime, date)):
        return (value.year, value.month, value.day)
    m = _DATE_PARTS_RE.match(str(value or ""))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    day = int(m.group(3)) if m.group(3) else None
    if not 1 <= month <= 12 or (day is not None and not 1 <= day <= 31):
        return None
    return (year, month, day)


def iso_date(value):
    """日付を 'YYYY-MM-DD' に揃える。

    None・空文字は None。読めない値(「不明」など)はそのまま返す
    ＝過去データを勝手に壊さない(新規登録はカレンダー入力なのでここには来ない)。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    parts = _date_parts(value)
    if parts is None or parts[2] is None:
        return value
    year, month, day = parts
    return f"{year:04d}-{month:02d}-{day:02d}"


def iso_month(value):
    """月度を 'YYYY-MM' に揃える。日まで入っていても月に丸める。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    parts = _date_parts(value)
    if parts is None:
        return value
    return f"{parts[0]:04d}-{parts[1]:02d}"


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


def distinct_other_labels(*row_lists):
    """複数の行リストから案件区分(other_label)の値を集め、重複無しで昇順に返す。

    アドバリューの「8-1」「8-2」等のように、案件をさらに区分して号別明細で
    見られるようにするため(2026-08-20)。空値は含めない。
    """
    values = set()
    for rows in row_lists:
        for r in rows:
            v = str(r.get("other_label") or "").strip()
            if v:
                values.add(v)
    return sorted(values)


# 区分(other_label)が入っていない行を選ぶための印。
# 🔴 2026-08-28: アドバリューの配布員代が区分なしで登録されていて、どの週にも
# 表示されず「1週目しか無い」ように見えた。未設定の行にも画面から辿り着けるよう、
# 「未設定」という選択肢を作れるようにする(消えた行を人が見つけられる状態にする)。
LABEL_UNSET = "（未設定）"


def filter_rows_by_label(rows, label):
    """label が指定されていれば other_label が一致する行だけに絞る。未指定ならそのまま。
    label に LABEL_UNSET を渡すと、区分が入っていない行だけを返す。"""
    if not label:
        return rows
    if label == LABEL_UNSET:
        return [r for r in rows if not str(r.get("other_label") or "").strip()]
    return [r for r in rows if str(r.get("other_label") or "").strip() == label]


def has_unlabeled_rows(*row_lists) -> bool:
    """区分(other_label)が入っていない行が1つでもあるか。"""
    return any(not str(r.get("other_label") or "").strip()
               for rows in row_lists for r in rows)


def line_copies(line, pay_type=None):
    """その明細行の配布部数。歩合(と未設定・未知の値)は数量がそのまま部数＝これまでの動き。
    日当・時給・月給は数量が日数/時間なので、別列の copies を使う。
    配布・挟み込み以外の行は部数を数えない。

    未知の pay_type を歩合に倒すのは unit_for と解釈を揃えるため。片方だけ非歩合に倒れると
    「3,713 枚と表示しているのに報告数は0部」という静かな食い違いが起きる。"""
    if not is_delivery((line or {}).get("remark")):
        return 0
    if pay_type not in ("日当", "時給", "月給"):
        return _num((line or {}).get("report_qty"))
    return _num((line or {}).get("copies"))


def delivered_copies(lines, pay_type=None):
    return sum(line_copies(l, pay_type) for l in lines)


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


# 原本区分の選択肢。買掛の登録(pages/01)とマスタの既定値(pages/05)で同じものを使う。
# 二重定義にすると、区分を足したときに片方だけ増えて「選べない値が既定になる」＝
# 黙って先頭(原本あり)に落ちる、という壊れ方をするのでここに一本化する。
ORIGINAL_STATUSES = ["原本あり", "本社", "クレジット", "振込用紙", "なし"]


def resolve_original_status(vendor_name, vendors):
    """取引先名(自由入力)が買掛先マスタと一致したら、その既定の原本区分を返す。
    一致しない・マスタに既定が無い場合は None(＝画面は既定値のまま)。"""
    key = str(vendor_name or "").strip()
    if not key:
        return None
    for v in vendors or []:
        if str(v.get("name") or "").strip() == key:
            return v.get("default_original_status") or None
    return None


def master_delete_action(usage_count) -> str:
    """マスタの行を消すときの動き。
    使用実績が「非負整数として明確に0」であるときだけ物理削除("delete")。
    それ以外(None・型不正・負値を含む)はすべて停止中("deactivate"、＝安全側)にする。

    なぜ安全側に倒すか: 配布員は入れ替わりが激しく、使用中のマスタを物理削除すると
    過去の号別明細・報告書からその配布員の名前が消えてしまう(それを防ぐのが停止中方式の
    目的そのもの)。使用件数が不明(None)の値を安易に0とみなして「削除可」と判定するのは、
    この目的の裏を突く挙動になるため避ける。判定できない入力に対しても例外は投げず、
    消えない側(deactivate)を返すことで、画面が落ちるより実害を小さくする。"""
    if isinstance(usage_count, bool):
        return "deactivate"
    if isinstance(usage_count, int) and usage_count == 0:
        return "delete"
    return "deactivate"


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


def master_row_subtitle(master, row) -> str:
    """一覧の各行で名前の右に薄字で出す補助情報。中身が空なら空文字。
    業務委託=「区分・支払形態」、買掛先=「既定費目 / 原本区分」、他マスタは無し。"""
    if master == "distributor":
        parts = [p for p in [row.get("kind"), row.get("pay_type")] if p]
        return "・".join(parts)
    if master == "payables_vendor":
        parts = [p for p in [row.get("default_category"), row.get("default_original_status")] if p]
        return " / ".join(parts)
    return ""


def selected_ids_from_editor(edited_df, *, id_col="No.", select_col="選択"):
    """data_editor の編集結果から、選択された行の id を int のリストで返す。"""
    ids = []
    for _, row in edited_df.iterrows():
        if row.get(select_col):
            ids.append(int(row[id_col]))
    return ids


def rows_for_excel(edited_df, *, select_col="選択"):
    """選択された行から選択列を除いた dict のリスト（選択行のExcel出力用）。"""
    out = []
    for _, row in edited_df.iterrows():
        if row.get(select_col):
            out.append({k: v for k, v in row.items() if k != select_col})
    return out


_PRINT_AMOUNT_KEYS = ("金額", "請求額", "合計")


def print_total(rows):
    """印刷用の合計。金額らしき列があり、全行が数値として読めるときだけ (列名, 合計) を返す。

    一覧の値は表示用に整形済みの文字列(「¥1,234」)。1行でも読めない値(「—」など)が
    混ざったまま合計すると、その行を無かったことにした嘘の合計を紙に載せてしまう。
    そのため「全行読めるとき以外は合計を出さない」を明示的な仕様にしている。
    """
    if not rows:
        return None
    col = next((c for c in rows[0] if any(k in str(c) for k in _PRINT_AMOUNT_KEYS)), None)
    if col is None:
        return None
    total = 0.0
    for r in rows:
        raw = (str(r.get(col, "")).replace("¥", "").replace(",", "")
               .replace("円", "").strip())
        if not raw:
            return None
        try:
            total += float(raw)
        except ValueError:
            return None
    return (col, total)


def company_summary_totals(*, receivables, payables, petty, contract_lines, manual):
    """全社の売上(売掛)・原価(買掛+小口+業務委託+直接入力)・利益。"""
    s = sum(_num(r.get("amount")) for r in receivables)
    c = (sum(_num(r.get("amount")) for r in payables)
         + sum(_num(r.get("amount")) for r in petty)
         + sum(_num(r.get("amount")) for r in contract_lines)
         + sum(_num(r.get("amount")) for r in manual))
    return {"sales": s, "cost": c, "profit": s - c}


# 原価・売上まとめの明細をタブに振り分けるための区分。
# ページ側に if 区分 == "売上" と直接書くと、区分が増えたときに
# 「どちらのタブにも出ない行」が静かに生まれるため、ここに集約する。
# company_summary_rows が新しい区分を足したら、必ずどちらかに加えること
# (tests/test_rev6_summary_logic.py の test_every_kind_is_covered_by_a_tab が守る)。
SALES_KINDS = ("売上",)
COST_KINDS = ("買掛", "小口", "業務委託", "直接入力")


def split_summary_rows(rows):
    """明細行を (原価の行, 売上の行) に分ける。並び順は元のまま保つ。"""
    sales = [r for r in rows if r.get("区分") in SALES_KINDS]
    cost = [r for r in rows if r.get("区分") in COST_KINDS]
    return cost, sales


# 案件別集計で「区分(other_label)ごとに行を分ける」案件。
# 既定はアドバリューだけ＝画面(06 大阪支社売上)の案件別表は今までどおりの見え方。
# 会議用売上表(依頼⑦)は「その他」も案件ごとに行を分けたいので、呼び出し側で
# split_labels_for=("アドバリュー", "その他") を渡す。
SPLIT_LABEL_PROJECTS = ("アドバリュー",)


def project_group_key(project_name, other_label, split_labels_for=SPLIT_LABEL_PROJECTS):
    """案件別集計のグループキー (案件名, 区分)。

    🔴 集計側と、小口の交通費/飲み物の振り分け側でこの規則が食い違うと、
    「行はあるのに交通費だけ別の行に付く」という静かなズレが起きる。
    必ずこの関数を通すこと。
    """
    name = project_name or ""
    label = str(other_label or "").strip() or None
    return (name, label if name in (split_labels_for or ()) else None)


def company_summary_by_project(*, receivables, payables, petty, contract_lines, manual, id2proj,
                               split_labels_for=SPLIT_LABEL_PROJECTS):
    """案件別(アドバリューだけ号別明細と同じく区分ごと)に、売上・原価・利益を集計する。

    依頼②(2026-08-20): 原価・売上まとめで「細かい内訳は号別明細で見る、こちらは
    案件別の売上・原価だけで良い」というオーナー方針に沿った、シンプルな案件別集計。
    会議用売上表の一括出力も、この集計を土台にする。

    split_labels_for に案件名を足すと、その案件も区分ごとに行を分ける
    (依頼⑦・2026-08-27＝単独チラシ「その他」が複数あるとき行を増やすため)。
    """
    def _proj(pid):
        return id2proj.get(pid, "") if pid is not None else ""

    def _key(pid, other_label):
        return project_group_key(_proj(pid), other_label, split_labels_for)

    agg = {}

    def _add(pid, other_label, kind, amount):
        k = _key(pid, other_label)
        d = agg.setdefault(k, {"sales": 0, "cost": 0})
        d[kind] += _num(amount)

    for r in receivables:
        _add(r.get("project_id"), r.get("other_label"), "sales", r.get("amount"))
    for r in payables:
        _add(r.get("project_id"), r.get("other_label"), "cost", r.get("amount"))
    for r in petty:
        _add(r.get("project_id"), r.get("other_label"), "cost", r.get("amount"))
    for r in contract_lines:
        _add(r.get("project_id"), r.get("other_label"), "cost", r.get("amount"))
    for r in manual:
        _add(r.get("project_id"), r.get("other_label"), "cost", r.get("amount"))

    out = [{"案件": name, "区分": label, "売上": d["sales"], "原価": d["cost"],
           "利益": d["sales"] - d["cost"]}
          for (name, label), d in agg.items()]
    out.sort(key=lambda r: (r["案件"], r["区分"] or ""))
    return out


# 車両使用履歴を見るときの車種の分け方(2026-08-27 大橋様ご指摘＝
# 「ハイエース」「軽バン」「レンタカー」でページを分けたい)。
# 登録画面(pages/01)の _VEHICLE_PRESETS と同じ並び。
VEHICLE_KINDS = ("ハイエース", "軽バン", "レンタカー")
VEHICLE_OTHER = "その他"


def split_vehicle_logs(rows):
    """車両使用履歴を車種ごとに分けて [(車種, 行), ...] で返す。

    ・3車種はまだ登録が無くても必ず出す(タブが消えて「どこに入れるんだ」に
      ならないように)。
    ・3車種に当てはまらない車両名(登録画面の「その他」で自由入力したもの・
      未入力)は「その他」にまとめ、行数が0のときだけ出さない。
      🔴 ここで捨てると、登録したのにどのタブにも出ない行が静かに生まれる。
    ・各車種の中の並びは元のまま(並べ替えは呼び出し側の責任)。
    """
    buckets = {k: [] for k in VEHICLE_KINDS}
    other = []
    for r in rows or []:
        name = str((r or {}).get("vehicle") or "").strip()
        if name in buckets:
            buckets[name].append(r)
        else:
            other.append(r)
    out = [(k, buckets[k]) for k in VEHICLE_KINDS]
    if other:
        out.append((VEHICLE_OTHER, other))
    return out


# 🔴 依頼⑧(2026-08-27 大橋様): 大阪支社売上ページの案件別表示は、
# 「関西ぱど → アドバリュー → リビング → その他 → 空白(区分未設定)」の順に固定する。
# 案件名の前方一致で判定する(マスタ名は「関西ぱど：京阪北版」のように版が付くため)。
_PROJECT_ORDER_PREFIXES = ("関西ぱど", "アドバリュー", "リビング", "その他")
_PROJECT_ORDER_UNKNOWN = len(_PROJECT_ORDER_PREFIXES)        # 知らない案件はその他の後
_PROJECT_ORDER_BLANK = _PROJECT_ORDER_UNKNOWN + 1            # 案件未設定は最後


def _project_order(name) -> int:
    n = str(name or "").strip()
    if not n:
        return _PROJECT_ORDER_BLANK
    for i, prefix in enumerate(_PROJECT_ORDER_PREFIXES):
        if n.startswith(prefix):
            return i
    return _PROJECT_ORDER_UNKNOWN


def sort_project_summary_rows(rows):
    """案件別の集計行を、大阪支社の見たい順に並べ替える。

    知らない案件名は捨てずに「その他」と「空白」のあいだに置く
    (案件マスタが増えたときに行が消えないように)。
    同じ案件の中はアドバリューの週(8-1→8-2→9-1→10-1)を月→週の順に並べる
    (素の文字列順だと 10-1 が 8-1 より前に来てしまう)。
    """
    from common import advalue

    def _key(r):
        label = r.get("区分") or ""
        week = advalue.parse_week_label(label)
        return (_project_order(r.get("案件")), str(r.get("案件") or ""),
                (0, week[0], week[1], "") if week else (1, 0, 0, label))

    return sorted(rows or [], key=_key)


def delivery_counts(contract_lines) -> dict:
    """配布部数（冊子・チラシ）と挟み込み数を、種別ごとに合算する。

    依頼⑧(2026-08-27 大橋様)＝売上・原価・利益に加えて、どれだけ配ったかも
    出したい(モチベーション向上のための副次的な情報)。
    交通費・手当・その他は部数を数えない。日当・時給・月給は数量が日数/時間なので
    line_copies が copies 列を見る(3日を3部と数えない)。
    """
    out = {"配布": 0.0, "挟み込み": 0.0}
    for ln in contract_lines or []:
        remark = (ln or {}).get("remark")
        if remark in out:
            out[remark] += line_copies(ln, (ln or {}).get("pay_type"))
    return {k: (int(v) if v == int(v) else v) for k, v in out.items()}


def company_summary_rows(*, receivables, payables, petty, contract_lines, manual,
                         id2proj, id2vendor, id2cat, id2client, id2dist):
    """区分・日付・項目・案件・金額 に正規化した明細行のリスト（原価・売上まとめ用）。"""
    def _proj(pid):
        return id2proj.get(pid, "") if pid is not None else ""
    rows = []
    for r in receivables:
        rows.append({"区分": "売上", "日付": r.get("month") or "",
                     "項目": id2client.get(r.get("client_id"), ""),
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in payables:
        rows.append({"区分": "買掛", "日付": r.get("date") or r.get("month") or "",
                     "項目": r.get("vendor_name") or id2vendor.get(r.get("vendor_id"), ""),
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in petty:
        item = id2cat.get(r.get("category_id"), "")
        if r.get("memo"):
            item = f"{item}（{r['memo']}）" if item else r["memo"]
        rows.append({"区分": "小口", "日付": r.get("date") or "", "項目": item or "小口",
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in contract_lines:
        rows.append({"区分": "業務委託", "日付": r.get("issue_date") or "",
                     "項目": id2dist.get(r.get("distributor_id"), ""),
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in manual:
        rows.append({"区分": "直接入力", "日付": r.get("work_date") or "",
                     "項目": r.get("content") or "",
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    return rows
