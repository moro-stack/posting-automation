from datetime import date as _date, datetime as _datetime
import io

import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, section_export, nice_table

apply_app_style()
st.title("号別の明細・収支")

_WD = ["月", "火", "水", "木", "金", "土", "日"]


def _yen(v):
    return f"¥{posting_logic.fmt_num(v)}"


def _weekday(ds):
    try:
        return _WD[_datetime.strptime(str(ds)[:10], "%Y-%m-%d").weekday()]
    except (ValueError, TypeError):
        return ""


projs = store.list_projects(only_active=True)
if not projs:
    st.warning("案件マスタが空です。『マスタ管理』で登録してください。")
    st.stop()

name2id = {p["name"]: p["id"] for p in projs}
names = list(name2id.keys())
st.markdown("**案件(号)**")
sel = st.pills("案件(号)", names, selection_mode="single",
               default=names[0], label_visibility="collapsed", key="proj_pills")
if not sel:
    sel = names[0]
pid = name2id[sel]

st.markdown("**期間指定**")
_PRESETS = {"全期間": "all", "今年": "year", "今月": "month", "今週": "week"}
period_label = st.pills("期間指定", list(_PRESETS.keys()) + ["期間を指定"],
                        selection_mode="single", default="全期間",
                        label_visibility="collapsed", key="period_pills")
if not period_label:
    period_label = "全期間"
if period_label == "期間を指定":
    c1, c2 = st.columns(2)
    d_from = c1.date_input("開始日", value=_date.today().replace(day=1))
    d_to = c2.date_input("終了日", value=_date.today())
    lo, hi = str(d_from), str(d_to)
else:
    lo, hi = posting_logic.period_range(_PRESETS[period_label])
period_note = "全期間" if (lo is None and hi is None) else f"{lo} 〜 {hi}"
st.caption(f"表示期間: {period_note}")

# --- コストを集める ---
petty = posting_logic.filter_rows_by_period(
    store.list_petty_cash(project_id=pid), "date", lo, hi)
payables = posting_logic.filter_rows_by_period(
    store.list_payables(project_id=pid), "month", lo, hi)
receivables = posting_logic.filter_rows_by_period(
    store.list_receivables(project_id=pid), "month", lo, hi)

contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    contract_lines.extend(detail["lines"])

# 直接入力(配布員代): work_date で期間絞り込み。日付なしは常に計上。
all_manual = store.list_issue_manual_costs(project_id=pid)
manual = [r for r in all_manual
          if r.get("work_date") is None or posting_logic.in_period(r.get("work_date"), lo, hi)]

agg = posting_logic.aggregate_issue(
    pid, petty=petty, payables=payables, contract_lines=contract_lines, manual=manual)
groups = posting_logic.cost_groups(agg)

# --- 上部サマリー ---
mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("配布原価(税込)", _yen(groups["genka"]))
mcol2.metric("配布員代", _yen(groups["labor"]))
mcol3.metric("雑費", _yen(groups["misc"]))

receivable_total = sum(posting_logic._num(r["amount"]) for r in receivables)
if receivable_total:
    bal = posting_logic.issue_balance(groups["genka"], receivable_total)
    st.metric("収支(売上−配布原価)", _yen(bal), delta=f"売上 {_yen(receivable_total)}")

st.divider()

# ===== 配布員代 =====
st.subheader("配布員代")

st.markdown("**業務委託（配布員別・報告書/請求書ページで計算）**")
issue_contract = [l for l in contract_lines if l.get("project_id") == pid]
_con_disp = [{"種別": l.get("remark") or "",
              "数量": f'{posting_logic.fmt_num(l.get("report_qty"))} {posting_logic.unit_for(l.get("remark"))}',
              "単価": _yen(l.get("unit_price")), "合計": _yen(l.get("amount"))}
             for l in issue_contract]
nice_table(_con_disp, "この号の業務委託はありません。")

st.markdown("**直接入力（日ごと・作業別）**")
_man_disp = [{"日付": r.get("work_date") or "（日付なし）",
              "曜日": _weekday(r.get("work_date")),
              "作業": r.get("content") or "",
              "金額": _yen(r.get("amount"))} for r in manual]
nice_table(_man_disp, "直接入力の配布員代はありません。")

with st.form("add_labor", clear_on_submit=True):
    st.caption("配布員代を直接追加（日給の人・後からの追加もここで）")
    a1, a2, a3 = st.columns([1, 2, 1])
    w = a1.date_input("日付", value=_date.today())
    work = a2.text_input("作業", placeholder="例：配布 / 丁合・配布")
    amt = a3.number_input("金額", min_value=0, step=1)
    if st.form_submit_button("追加") and amt > 0:
        store.add_issue_manual_cost(pid, work.strip() or "配布", int(amt), work_date=str(w))
        st.rerun()

if manual:
    st.caption("入力済みの直接入力を修正・削除")
    # 行idをラベルに含めて一意化（同一日付・作業・金額の行が複数あっても取り違えない）
    opt = {f'{(r.get("work_date") or "日付なし")}｜{r.get("content") or ""}｜{_yen(r.get("amount"))}｜No.{r.get("id")}': r
           for r in manual}
    pick = st.selectbox("対象の行", list(opt.keys()), key="edit_pick")
    target = opt[pick]
    with st.form("edit_labor"):
        e1, e2, e3 = st.columns([1, 2, 1])
        cur_date = (_datetime.strptime(target["work_date"][:10], "%Y-%m-%d").date()
                    if target.get("work_date") else _date.today())
        # key は行idごとに変える。固定keyだと session_state が保持され、対象行を
        # 切り替えても前の行の値が残り、更新時に別の行へ誤って書き込む(Streamlit仕様)。
        _rid = target["id"]
        ew = e1.date_input("日付", value=cur_date, key=f"edit_date_{_rid}")
        ework = e2.text_input("作業", value=target.get("content") or "", key=f"edit_work_{_rid}")
        eamt = e3.number_input("金額", min_value=0, step=1,
                               value=int(target.get("amount") or 0), key=f"edit_amt_{_rid}")
        u1, u2, _ = st.columns([1, 1, 4])
        if u1.form_submit_button("更新") and eamt > 0:
            store.update_issue_manual_cost(target["id"], work_date=str(ew),
                                           content=ework.strip() or "配布", amount=int(eamt))
            st.rerun()
        if u2.form_submit_button("削除"):
            store.delete_issue_manual_cost(target["id"])
            st.rerun()

st.metric("配布員代 小計", _yen(groups["labor"]))
section_export(_man_disp, f"配布員代直接入力_{sel}", key="issue_labor")

st.divider()

# ===== 雑費 =====
st.subheader("雑費（小口・買掛から自動集計）")
_cats = {c["id"]: c["name"] for c in store.list_expense_categories()}
_vends = {v["id"]: v["name"] for v in store.list_payables_vendors()}
_misc = []
for r in petty:
    item = _cats.get(r.get("category_id"), "")
    if r.get("memo"):
        item = f'{item}（{r["memo"]}）' if item else r["memo"]
    _misc.append({"項目": item or "小口", "金額": _yen(r.get("amount")),
                  "支払方法": posting_logic.payment_method("petty", r),
                  "日付": r.get("date") or ""})
for r in payables:
    item = r.get("vendor_name") or _vends.get(r.get("vendor_id"), "")
    _misc.append({"項目": item or "買掛", "金額": _yen(r.get("amount")),
                  "支払方法": posting_logic.payment_method("payable", r),
                  "日付": r.get("date") or r.get("month") or ""})
nice_table(_misc, "この号の雑費（小口・買掛）はありません。")
st.metric("雑費 小計", _yen(groups["misc"]))
section_export(_misc, f"雑費_{sel}", key="issue_misc")

st.divider()

# ===== 号原価まとめ 出力 =====
st.subheader("号原価まとめの出力")
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    (pd.DataFrame(_con_disp) if _con_disp
     else pd.DataFrame(columns=["種別", "数量", "単価", "合計"])).to_excel(
        writer, index=False, sheet_name="業務委託")
    (pd.DataFrame(_man_disp) if _man_disp
     else pd.DataFrame(columns=["日付", "曜日", "作業", "金額"])).to_excel(
        writer, index=False, sheet_name="直接入力")
    (pd.DataFrame(_misc) if _misc
     else pd.DataFrame(columns=["項目", "金額", "支払方法", "日付"])).to_excel(
        writer, index=False, sheet_name="雑費")
    pd.DataFrame([{"項目": "配布員代", "金額": groups["labor"]},
                  {"項目": "雑費", "金額": groups["misc"]},
                  {"項目": "配布原価(税込)", "金額": groups["genka"]}]).to_excel(
        writer, index=False, sheet_name="合計")
st.download_button("⬇️ 号原価まとめをExcelで保存", data=buf.getvalue(),
                   file_name=f"号原価まとめ_{sel}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   key="dl_genka")
