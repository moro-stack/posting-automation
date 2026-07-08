import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("📮 配布コスト管理")

projs = store.list_projects(only_active=True)
contract_lines = []
for inv in store.list_contract_invoices():
    contract_lines.extend(store.get_contract_invoice(inv["id"])["lines"])
petty, pays, manual = store.list_petty_cash(), store.list_payables(), store.list_issue_manual_costs()

rows = []
for p in projs:
    agg = posting_logic.aggregate_issue(p["id"], petty=petty, payables=pays,
                                        contract_lines=contract_lines, manual=manual)
    rev = sum(int(r["amount"]) for r in store.list_receivables(project_id=p["id"]))
    rows.append({"案件": p["name"], "コスト合計": agg["total"], "売上": rev,
                 "収支": posting_logic.issue_balance(agg["total"], rev)})
st.dataframe(rows, use_container_width=True, hide_index=True)
st.caption("左メニュー: 経費・買掛・売掛 / 業務委託・請求書 / 号別明細 / 経理提出出力 / マスタ管理")
