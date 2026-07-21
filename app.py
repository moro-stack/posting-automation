import os
import time
import streamlit as st

from common import posting_store as store
from common import auth
from common.ui import apply_app_style

# Streamlit Cloud の secrets を環境変数へ橋渡し(既存の os.environ ベースのコードがそのまま動く)
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:  # secrets 未設定でも落ちない
    pass

st.set_page_config(page_title="配布コスト管理", page_icon="📮", layout="wide")
apply_app_style()


@st.cache_resource
def _bootstrap_db():
    store.sync_from_remote()
    store.init_db()
    from common import demo_seed
    demo_seed.seed_for_boot()   # DEMO_MODEなら架空データ、そうでなければ実マスタpreset(分岐はdemo_seed側で保護)
    return True


_bootstrap_db()


def _render_login():
    st.markdown("## 📮 配布コスト管理")
    st.caption("共有パスワードを入力してください。")
    if auth.is_locked_out(st.session_state, time.time()):
        st.error("試行が続いたため一時的にロックしています。30秒ほど待って再度お試しください。")
    st.text_input("パスワード", type="password", key="login_pw")
    if st.button("ログイン", type="primary"):
        if not auth.is_locked_out(st.session_state, time.time()) and \
                auth.attempt_login(st.session_state.get("login_pw", ""), st.session_state, time.time()):
            st.rerun()
        else:
            st.error("パスワードが違います。")


if os.environ.get("APP_PASSWORD") and not auth.is_authenticated(st.session_state):
    _render_login()
    st.stop()

pages = [
    st.Page("pages/06_原価・売上まとめ.py", title="原価・売上まとめ", icon=":material/summarize:"),
    st.Page("pages/03_号別明細.py", title="号別明細", icon=":material/table_chart:", default=True),
    st.Page("pages/01_経費・買掛・売掛.py", title="小口・買掛・売掛", icon=":material/receipt_long:"),
    st.Page("pages/02_業務委託登録.py", title="業務委託登録", icon=":material/description:"),
    st.Page("pages/05_マスタ管理.py", title="マスタ管理", icon=":material/settings:"),
]
st.navigation(pages).run()
