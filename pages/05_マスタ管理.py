import streamlit as st

from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("⚙️ マスタ管理")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["案件", "費目(小口)", "買掛先", "売掛先", "配布委託先"])


def _simple_master(label, list_fn, add_fn, update_fn):
    rows = list_fn()
    st.dataframe(rows, use_container_width=True, hide_index=True)
    with st.form(f"add_{label}", clear_on_submit=True):
        name = st.text_input(f"{label}名を追加")
        if st.form_submit_button("追加") and name.strip():
            add_fn(name.strip())
            st.rerun()


with tab1:
    _simple_master("案件", store.list_projects, store.add_project, store.update_project)
with tab2:
    _simple_master("費目", store.list_expense_categories,
                   store.add_expense_category, store.update_expense_category)
with tab3:
    st.dataframe(store.list_payables_vendors(), use_container_width=True, hide_index=True)
    with st.form("add_vendor", clear_on_submit=True):
        n = st.text_input("取引先名")
        c = st.text_input("既定の費目(家賃・電気 等)")
        if st.form_submit_button("追加") and n.strip():
            store.add_payables_vendor(n.strip(), default_category=(c.strip() or None))
            st.rerun()
with tab4:
    _simple_master("売掛先", store.list_receivables_clients,
                   store.add_receivables_client, store.update_receivables_client)
with tab5:
    st.dataframe(store.list_distributors(), use_container_width=True, hide_index=True)
    with st.form("add_dist", clear_on_submit=True):
        n = st.text_input("配布員 氏名")
        kind = st.selectbox("区分", ["業務委託", "自社社員", "アルバイト"])
        if st.form_submit_button("追加") and n.strip():
            store.add_distributor(n.strip(), kind=kind)
            st.rerun()
