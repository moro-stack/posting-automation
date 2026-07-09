import streamlit as st

from common import ocr
from common import posting_store as store
from common.ui import apply_app_style, section_export

apply_app_style()
st.title("🧾 小口/買掛/売掛登録")

mode = st.radio("入力の種類", ["小口", "買掛", "売掛"],
                horizontal=True)


def _project_options():
    return {p["name"]: p["id"] for p in store.list_projects(only_active=True)}


if mode == "小口":
    st.subheader("小口経費（レシートOCR / 手入力）")
    up = st.file_uploader("レシート画像（任意・AIが下書き抽出）", type=["jpg", "jpeg", "png"])
    draft = {"date": None, "amount": None, "item": None}
    if up is not None and st.button("画像をAIで読み取る"):
        media = "image/png" if up.name.lower().endswith("png") else "image/jpeg"
        draft = ocr.extract_receipt(up.getvalue(), media, client=None)
        st.session_state["petty_draft"] = draft
    draft = st.session_state.get("petty_draft", draft)
    with st.form("petty", clear_on_submit=True):
        date = st.text_input("日付(YYYY-MM-DD)", value=draft.get("date") or "")
        cats = {c["name"]: c["id"] for c in store.list_expense_categories(only_active=True)}
        cat = st.selectbox("費目", list(cats.keys()) or ["(費目マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0,
                                 value=int(draft.get("amount") or 0), step=1)
        projs = _project_options()
        proj = st.selectbox("案件(任意)", ["(なし)"] + list(projs.keys()))
        memo = st.text_input("メモ", value=draft.get("item") or "")
        if st.form_submit_button("登録") and amount > 0:
            store.add_petty_cash(
                date or None, cats.get(cat), int(amount),
                project_id=projs.get(proj), memo=memo or None,
                source="ocr" if up is not None else "manual")
            st.session_state.pop("petty_draft", None)
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_petty_cash(), use_container_width=True, hide_index=True)
    section_export(store.list_petty_cash(), "小口一覧", key="petty")

elif mode == "買掛":
    st.subheader("買掛（固定費・法人業者）")
    up = st.file_uploader("請求書画像（任意・AIが金額を下書き抽出）",
                          type=["jpg", "jpeg", "png"])
    draft = {"vendor": None, "amount": None, "note": None}
    if up is not None and st.button("画像をAIで読み取る"):
        media = "image/png" if up.name.lower().endswith("png") else "image/jpeg"
        draft = ocr.extract_invoice(up.getvalue(), media, client=None)
        st.session_state["pay_draft"] = draft
    draft = st.session_state.get("pay_draft", draft)
    with st.form("payable", clear_on_submit=True):
        month = st.text_input("月度(YYYY-MM)")
        vendors = {v["name"]: v["id"] for v in store.list_payables_vendors(only_active=True)}
        vendor = st.selectbox("取引先", list(vendors.keys()) or ["(買掛先マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0,
                                 value=int(draft.get("amount") or 0), step=1)
        original = st.selectbox("原本区分",
                                ["原本あり", "本社", "クレジット", "振込用紙", "なし"])
        note = st.text_input("備考", value=draft.get("note") or "")
        projs = _project_options()
        proj = st.selectbox("案件(任意・配布業者なら号)", ["(なし)"] + list(projs.keys()))
        if st.form_submit_button("登録") and amount > 0:
            store.add_payable(month or None, vendors.get(vendor), int(amount),
                              original_status=original, note=note or None,
                              project_id=projs.get(proj),
                              source="ocr" if up is not None else "manual")
            st.session_state.pop("pay_draft", None)
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_payables(), use_container_width=True, hide_index=True)
    section_export(store.list_payables(), "買掛一覧", key="pay")

else:  # 売掛
    st.subheader("売掛（売上）")
    with st.form("receivable", clear_on_submit=True):
        month = st.text_input("月度(YYYY-MM)")
        clients = {c["name"]: c["id"] for c in store.list_receivables_clients(only_active=True)}
        client = st.selectbox("売掛先", list(clients.keys()) or ["(売掛先マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0, step=1)
        note = st.text_input("備考(号)")
        projs = _project_options()
        proj = st.selectbox("案件(任意)", ["(なし)"] + list(projs.keys()))
        if st.form_submit_button("登録") and amount > 0:
            store.add_receivable(month or None, clients.get(client), int(amount),
                                 note=note or None, project_id=projs.get(proj))
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_receivables(), use_container_width=True, hide_index=True)
    section_export(store.list_receivables(), "売掛一覧", key="recv")
