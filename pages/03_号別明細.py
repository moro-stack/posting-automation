import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("📊 号別明細")

projs = store.list_projects(only_active=True)
if not projs:
    st.warning("案件マスタが空です。『マスタ管理』で登録してください。")
    st.stop()

name2id = {p["name"]: p["id"] for p in projs}
sel = st.selectbox("案件(号)", list(name2id.keys()))
pid = name2id[sel]

# 全委託明細行を集める(案件でひもづけ)
contract_lines = []
for inv in store.list_contract_invoices():
    detail = store.get_contract_invoice(inv["id"])
    contract_lines.extend(detail["lines"])

agg = posting_logic.aggregate_issue(
    pid,
    petty=store.list_petty_cash(),
    payables=store.list_payables(),
    contract_lines=contract_lines,
    manual=store.list_issue_manual_costs(),
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("小口", f"¥{agg['petty']:,}")
c2.metric("買掛", f"¥{agg['payables']:,}")
c3.metric("業務委託", f"¥{agg['contract']:,}")
c4.metric("手入力", f"¥{agg['manual']:,}")
st.metric("コスト合計", f"¥{agg['total']:,}")

receivable_total = sum(int(r["amount"]) for r in store.list_receivables(project_id=pid))
if receivable_total:
    bal = posting_logic.issue_balance(agg["total"], receivable_total)
    st.metric("収支(売上−コスト)", f"¥{bal:,}", delta=f"売上 ¥{receivable_total:,}")

st.divider()
st.subheader("内訳")
st.markdown("**小口**"); st.dataframe(store.list_petty_cash(project_id=pid),
                                     use_container_width=True, hide_index=True)
st.markdown("**買掛**"); st.dataframe(store.list_payables(project_id=pid),
                                     use_container_width=True, hide_index=True)
st.markdown("**業務委託(この号の行)**")
st.dataframe([l for l in contract_lines if l.get("project_id") == pid],
             use_container_width=True, hide_index=True)

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
