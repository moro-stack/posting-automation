from datetime import date as _date

import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, section_export

apply_app_style()
st.title("📊 号別明細")

projs = store.list_projects(only_active=True)
if not projs:
    st.warning("案件マスタが空です。『マスタ管理』で登録してください。")
    st.stop()

# --- 案件(号)を水色のボタンで選ぶ ---
name2id = {p["name"]: p["id"] for p in projs}
names = list(name2id.keys())
st.markdown("**案件(号)**")
sel = st.pills("案件(号)", names, selection_mode="single",
               default=names[0], label_visibility="collapsed", key="proj_pills")
if not sel:
    sel = names[0]
pid = name2id[sel]

# --- 期間指定を水色のボタンで選ぶ(案件の下) ---
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

# --- 期間で絞り込んだ各コストを集める ---
petty = posting_logic.filter_rows_by_period(
    store.list_petty_cash(project_id=pid), "date", lo, hi)
payables = posting_logic.filter_rows_by_period(
    store.list_payables(project_id=pid), "month", lo, hi)
receivables = posting_logic.filter_rows_by_period(
    store.list_receivables(project_id=pid), "month", lo, hi)

# 業務委託は請求書の発行日で期間判定し、期間内の請求の明細だけを集める
contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    contract_lines.extend(detail["lines"])

# 手入力は日付を持たないため全期間のときのみ計上(期間指定時は0)
manual = store.list_issue_manual_costs(project_id=pid) if (lo is None and hi is None) else []

agg = posting_logic.aggregate_issue(
    pid, petty=petty, payables=payables, contract_lines=contract_lines, manual=manual)

# 内訳は2列×2行にして金額が切れないようにする
_yen = lambda v: f"¥{posting_logic.fmt_num(v)}"
r1c1, r1c2 = st.columns(2)
r1c1.metric("小口", _yen(agg['petty']))
r1c2.metric("買掛", _yen(agg['payables']))
r2c1, r2c2 = st.columns(2)
r2c1.metric("業務委託", _yen(agg['contract']))
r2c2.metric("手入力", _yen(agg['manual']))
st.metric("コスト合計", _yen(agg['total']))

receivable_total = sum(posting_logic._num(r["amount"]) for r in receivables)
if receivable_total:
    bal = posting_logic.issue_balance(agg["total"], receivable_total)
    st.metric("収支(売上−コスト)", _yen(bal), delta=f"売上 {_yen(receivable_total)}")

st.divider()
st.subheader("内訳")
st.markdown("**小口**")
st.dataframe(petty, use_container_width=True, hide_index=True)
section_export(petty, f"小口_{sel}", key="issue_petty")
st.markdown("**買掛**")
st.dataframe(payables, use_container_width=True, hide_index=True)
section_export(payables, f"買掛_{sel}", key="issue_pay")
st.markdown("**業務委託(この号の行)**")
issue_contract = [l for l in contract_lines if l.get("project_id") == pid]
st.dataframe(issue_contract, use_container_width=True, hide_index=True)
section_export(issue_contract, f"業務委託_{sel}", key="issue_contract")

st.divider()
st.subheader("この号に手入力でコストを足す（自社社員配布分 等）")
with st.form("manual_cost", clear_on_submit=True):
    content = st.text_input("内容")
    amount = st.number_input("金額", min_value=0, step=1)
    if st.form_submit_button("追加") and amount > 0 and content.strip():
        store.add_issue_manual_cost(pid, content.strip(), int(amount))
        st.rerun()
st.dataframe(store.list_issue_manual_costs(project_id=pid),
             use_container_width=True, hide_index=True)
