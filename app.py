import streamlit as st

from common import posting_store as store
from common.ui import apply_app_style

st.set_page_config(page_title="配布コスト管理", page_icon="📮", layout="wide")
apply_app_style()


@st.cache_resource
def _bootstrap_db():
    store.sync_from_remote()
    store.init_db()
    store.seed_masters()
    return True


_bootstrap_db()

pages = [
    st.Page("pages/03_号別明細.py", title="号別明細", icon=":material/table_chart:", default=True),
    st.Page("pages/01_経費・買掛・売掛.py", title="小口・買掛・売掛", icon=":material/receipt_long:"),
    st.Page("pages/02_業務委託・請求書.py", title="報告書・請求書", icon=":material/description:"),
    st.Page("pages/05_マスタ管理.py", title="マスタ管理", icon=":material/settings:"),
]
st.navigation(pages).run()
