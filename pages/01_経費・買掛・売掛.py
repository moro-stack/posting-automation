from datetime import date as _date

import streamlit as st

from common import ocr
from common import posting_store as store
from common.ui import apply_app_style, section_export

apply_app_style()
st.title("🧾 小口/買掛/売掛登録")

mode = st.radio("入力の種類", ["小口", "買掛", "売掛"], horizontal=True)


def _project_options():
    return {p["name"]: p["id"] for p in store.list_projects(only_active=True)}


def _ai_read(reader, image_bytes, name, state_key):
    """AIでの下書き抽出。失敗してもページを落とさずメッセージ表示(#7の保険)。"""
    media = "image/png" if name.lower().endswith("png") else "image/jpeg"
    try:
        st.session_state[state_key] = reader(image_bytes, media, client=None)
        st.success("AIが読み取りました。下のフォームで内容を確認・修正して登録してください。")
    except Exception as e:  # noqa: BLE001
        st.error(f"AI読み取りに失敗しました（手入力で登録できます）: {e}")


if mode == "小口":
    st.subheader("小口経費（レシートOCR / 手入力）")
    up = st.file_uploader("レシート画像（任意・AIが下書き抽出）", type=["jpg", "jpeg", "png"])
    if up is not None and st.button("画像をAIで読み取る"):
        _ai_read(ocr.extract_receipt, up.getvalue(), up.name, "petty_draft")
    draft = st.session_state.get("petty_draft", {"date": None, "amount": None, "item": None})
    if st.session_state.get("petty_draft"):
        st.caption("✏️ AIが読み取った値は下のフォームで自由に修正できます。")

    # 重複の確認待ち
    if "petty_pending" in st.session_state:
        p = st.session_state["petty_pending"]
        st.warning("⚠️ 同様の内容が登録済みです。それでも登録しますか？")
        st.caption(f"日付 {p['date'] or '—'} ／ 金額 ¥{p['amount']:,}")
        cc1, cc2, _ = st.columns([1, 1, 4])
        if cc1.button("はい、登録する", type="primary", key="petty_ok"):
            store.add_petty_cash(p["date"], p["category_id"], p["amount"],
                                 project_id=p["project_id"], memo=p["memo"], source=p["source"])
            del st.session_state["petty_pending"]
            st.success("登録しました")
            st.rerun()
        if cc2.button("やめる", key="petty_no"):
            del st.session_state["petty_pending"]
            st.rerun()

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
            payload = {"date": date or None, "category_id": cats.get(cat), "amount": int(amount),
                       "project_id": projs.get(proj), "memo": memo or None,
                       "source": "ocr" if up is not None else "manual"}
            if store.find_duplicate_petty(payload["date"], payload["category_id"], payload["amount"]):
                st.session_state["petty_pending"] = payload
                st.rerun()
            store.add_petty_cash(payload["date"], payload["category_id"], payload["amount"],
                                 project_id=payload["project_id"], memo=payload["memo"],
                                 source=payload["source"])
            st.session_state.pop("petty_draft", None)
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_petty_cash(), use_container_width=True, hide_index=True)
    section_export(store.list_petty_cash(), "小口一覧", key="petty")

elif mode == "買掛":
    st.subheader("買掛（固定費・法人業者）")
    up = st.file_uploader("請求書画像（任意・AIが金額を下書き抽出）",
                          type=["jpg", "jpeg", "png"])
    if up is not None and st.button("画像をAIで読み取る"):
        _ai_read(ocr.extract_invoice, up.getvalue(), up.name, "pay_draft")
    draft = st.session_state.get("pay_draft", {"vendor": None, "amount": None, "note": None})
    if st.session_state.get("pay_draft"):
        st.caption("✏️ AIが読み取った値は下のフォームで自由に修正できます。")

    if "pay_pending" in st.session_state:
        p = st.session_state["pay_pending"]
        st.warning("⚠️ 同様の内容が登録済みです。それでも登録しますか？")
        st.caption(f"請求書の日付 {p['date'] or '—'} ／ 金額 ¥{p['amount']:,}")
        cc1, cc2, _ = st.columns([1, 1, 4])
        if cc1.button("はい、登録する", type="primary", key="pay_ok"):
            store.add_payable(None, p["vendor_id"], p["amount"], date=p["date"],
                              original_status=p["original_status"], note=p["note"],
                              project_id=p["project_id"], source=p["source"])
            del st.session_state["pay_pending"]
            st.success("登録しました")
            st.rerun()
        if cc2.button("やめる", key="pay_no"):
            del st.session_state["pay_pending"]
            st.rerun()

    with st.form("payable", clear_on_submit=True):
        inv_date = st.date_input("請求書の日付", value=_date.today())
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
            payload = {"date": str(inv_date), "vendor_id": vendors.get(vendor),
                       "amount": int(amount), "original_status": original, "note": note or None,
                       "project_id": projs.get(proj), "source": "ocr" if up is not None else "manual"}
            if store.find_duplicate_payable(payload["date"], payload["vendor_id"], payload["amount"]):
                st.session_state["pay_pending"] = payload
                st.rerun()
            store.add_payable(None, payload["vendor_id"], payload["amount"], date=payload["date"],
                              original_status=payload["original_status"], note=payload["note"],
                              project_id=payload["project_id"], source=payload["source"])
            st.session_state.pop("pay_draft", None)
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_payables(), use_container_width=True, hide_index=True)
    section_export(store.list_payables(), "買掛一覧", key="pay")

else:  # 売掛
    st.subheader("売掛（売上）")
    if "recv_pending" in st.session_state:
        p = st.session_state["recv_pending"]
        st.warning("⚠️ 同様の内容が登録済みです。それでも登録しますか？")
        st.caption(f"月度 {p['month'] or '—'} ／ 金額 ¥{p['amount']:,}")
        cc1, cc2, _ = st.columns([1, 1, 4])
        if cc1.button("はい、登録する", type="primary", key="recv_ok"):
            store.add_receivable(p["month"], p["client_id"], p["amount"],
                                 note=p["note"], project_id=p["project_id"])
            del st.session_state["recv_pending"]
            st.success("登録しました")
            st.rerun()
        if cc2.button("やめる", key="recv_no"):
            del st.session_state["recv_pending"]
            st.rerun()

    with st.form("receivable", clear_on_submit=True):
        month = st.text_input("月度(YYYY-MM)")
        clients = {c["name"]: c["id"] for c in store.list_receivables_clients(only_active=True)}
        client = st.selectbox("売掛先", list(clients.keys()) or ["(売掛先マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0, step=1)
        note = st.text_input("備考(号)")
        projs = _project_options()
        proj = st.selectbox("案件(任意)", ["(なし)"] + list(projs.keys()))
        if st.form_submit_button("登録") and amount > 0:
            payload = {"month": month or None, "client_id": clients.get(client),
                       "amount": int(amount), "note": note or None, "project_id": projs.get(proj)}
            if store.find_duplicate_receivable(payload["month"], payload["client_id"], payload["amount"]):
                st.session_state["recv_pending"] = payload
                st.rerun()
            store.add_receivable(payload["month"], payload["client_id"], payload["amount"],
                                 note=payload["note"], project_id=payload["project_id"])
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_receivables(), use_container_width=True, hide_index=True)
    section_export(store.list_receivables(), "売掛一覧", key="recv")
