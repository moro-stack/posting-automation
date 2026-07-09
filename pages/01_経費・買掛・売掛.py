from datetime import date as _date

import pandas as pd
import streamlit as st

from common import ocr
from common import posting_store as store
from common.ui import apply_app_style, section_export, nice_table

apply_app_style()
st.title("小口／買掛／売掛の登録")

mode = st.radio("入力の種類", ["小口", "買掛", "売掛"], horizontal=True)

_UPLOAD_TYPES = ["pdf", "jpg", "jpeg", "png"]


def _project_options():
    return {p["name"]: p["id"] for p in store.list_projects(only_active=True)}


def _yen(v):
    try:
        return f"¥{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return v


def _names(list_fn):
    return {r["id"]: r["name"] for r in list_fn()}


def _ocr_files(files, reader):
    """複数ファイルをAIで読み取り、下書きリストを返す。失敗しても止めない(#7の保険)。"""
    drafts = []
    prog = st.progress(0.0)
    for i, f in enumerate(files):
        try:
            d = reader(f.getvalue(), ocr.media_type_for(f.name), client=None)
        except Exception as e:  # noqa: BLE001
            d = {"amount": None, "_error": str(e)}
        d["_file"] = f.name
        drafts.append(d)
        prog.progress((i + 1) / len(files))
    prog.empty()
    n_ok = sum(1 for d in drafts if d.get("amount"))
    if n_ok < len(drafts):
        st.warning(f"{len(drafts)}件中 {n_ok}件のみ金額を取得できました。"
                   "（AI未設定/読取失敗分は手入力できます）")
    else:
        st.success(f"{len(drafts)}件を読み取りました。内容を確認・修正して登録してください。")
    return drafts


if mode == "小口":
    st.subheader("小口経費（レシートOCR / 手入力）")
    ups = st.file_uploader("レシート画像・PDF（複数可・AIが下書き抽出）",
                           type=_UPLOAD_TYPES, accept_multiple_files=True)
    if ups and st.button("画像/PDFをAIで読み取る"):
        drafts = _ocr_files(ups, ocr.extract_receipt)
        st.session_state.pop("petty_draft", None)
        st.session_state.pop("petty_bulk", None)
        if len(drafts) == 1 and drafts[0].get("amount"):
            st.session_state["petty_draft"] = {"date": drafts[0].get("date"),
                                               "amount": drafts[0].get("amount"),
                                               "item": drafts[0].get("item")}
        else:
            st.session_state["petty_bulk"] = drafts

    # 複数レシートの一括登録レビュー(#9)
    if "petty_bulk" in st.session_state:
        st.markdown("**複数レシートの下書き（確認・修正して一括登録）**")
        cats = {c["name"]: c["id"] for c in store.list_expense_categories(only_active=True)}
        cat_names = list(cats.keys())
        bulk_df = pd.DataFrame([{
            "日付": d.get("date") or "",
            "費目": cat_names[0] if cat_names else "",
            "金額": int(d.get("amount") or 0),
            "メモ": d.get("item") or d.get("_file", ""),
        } for d in st.session_state["petty_bulk"]])
        edited = st.data_editor(
            bulk_df, num_rows="dynamic", use_container_width=True, key="petty_bulk_editor",
            column_config={"費目": st.column_config.SelectboxColumn(options=cat_names),
                           "金額": st.column_config.NumberColumn(min_value=0, step=1)})
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("全部登録", type="primary", key="petty_bulk_add"):
            cnt = 0
            for _, r in edited.iterrows():
                amt = int(r["金額"]) if pd.notna(r["金額"]) else 0
                if amt <= 0:
                    continue
                store.add_petty_cash(str(r["日付"]) or None, cats.get(r["費目"]), amt,
                                     memo=str(r["メモ"]) or None, source="ocr")
                cnt += 1
            del st.session_state["petty_bulk"]
            st.success(f"{cnt}件を登録しました")
            st.rerun()
        if b2.button("やめる", key="petty_bulk_cancel"):
            del st.session_state["petty_bulk"]
            st.rerun()

    draft = st.session_state.get("petty_draft", {"date": None, "amount": None, "item": None})
    if st.session_state.get("petty_draft"):
        st.caption("✏️ AIが読み取った値は下のフォームで自由に修正できます。")

    # 重複の確認待ち(#11)
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
        date = st.text_input("日付（例：2026-07-05）", value=draft.get("date") or "")
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
                       "source": "ocr" if ups else "manual"}
            if store.find_duplicate_petty(payload["date"], payload["category_id"], payload["amount"]):
                st.session_state["petty_pending"] = payload
                st.rerun()
            store.add_petty_cash(payload["date"], payload["category_id"], payload["amount"],
                                 project_id=payload["project_id"], memo=payload["memo"],
                                 source=payload["source"])
            st.session_state.pop("petty_draft", None)
            st.success("登録しました")
            st.rerun()
    st.divider()
    st.markdown("**登録済みの小口一覧**")
    _cats, _projs = _names(store.list_expense_categories), _names(store.list_projects)
    _disp = [{"日付": r["date"] or "", "費目": _cats.get(r["category_id"], ""),
              "金額": _yen(r["amount"]), "案件": _projs.get(r["project_id"], ""),
              "メモ": r["memo"] or ""} for r in store.list_petty_cash()]
    nice_table(_disp, "小口の登録はまだありません。")
    section_export(_disp, "小口一覧", key="petty")

elif mode == "買掛":
    st.subheader("買掛（固定費・法人業者）")
    ups = st.file_uploader("請求書画像・PDF（複数可・AIが金額を下書き抽出）",
                           type=_UPLOAD_TYPES, accept_multiple_files=True)
    if ups and st.button("画像/PDFをAIで読み取る"):
        drafts = _ocr_files(ups, ocr.extract_invoice)
        st.session_state.pop("pay_draft", None)
        st.session_state.pop("pay_bulk", None)
        if len(drafts) == 1 and drafts[0].get("amount"):
            st.session_state["pay_draft"] = {"vendor": drafts[0].get("vendor"),
                                             "amount": drafts[0].get("amount"),
                                             "note": drafts[0].get("note")}
        else:
            st.session_state["pay_bulk"] = drafts

    # 複数請求書の一括登録レビュー(#9)
    if "pay_bulk" in st.session_state:
        st.markdown("**複数請求書の下書き（確認・修正して一括登録）**")
        vendors = {v["name"]: v["id"] for v in store.list_payables_vendors(only_active=True)}
        vnames = list(vendors.keys())
        bulk_df = pd.DataFrame([{
            "請求書の日付": d.get("date") or str(_date.today()),
            "取引先": vnames[0] if vnames else "",
            "金額": int(d.get("amount") or 0),
            "備考": d.get("note") or d.get("_file", ""),
        } for d in st.session_state["pay_bulk"]])
        edited = st.data_editor(
            bulk_df, num_rows="dynamic", use_container_width=True, key="pay_bulk_editor",
            column_config={"取引先": st.column_config.SelectboxColumn(options=vnames),
                           "金額": st.column_config.NumberColumn(min_value=0, step=1)})
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("全部登録", type="primary", key="pay_bulk_add"):
            cnt = 0
            for _, r in edited.iterrows():
                amt = int(r["金額"]) if pd.notna(r["金額"]) else 0
                if amt <= 0:
                    continue
                store.add_payable(None, vendors.get(r["取引先"]), amt,
                                  date=str(r["請求書の日付"]), note=str(r["備考"]) or None,
                                  source="ocr")
                cnt += 1
            del st.session_state["pay_bulk"]
            st.success(f"{cnt}件を登録しました")
            st.rerun()
        if b2.button("やめる", key="pay_bulk_cancel"):
            del st.session_state["pay_bulk"]
            st.rerun()

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
                       "project_id": projs.get(proj), "source": "ocr" if ups else "manual"}
            if store.find_duplicate_payable(payload["date"], payload["vendor_id"], payload["amount"]):
                st.session_state["pay_pending"] = payload
                st.rerun()
            store.add_payable(None, payload["vendor_id"], payload["amount"], date=payload["date"],
                              original_status=payload["original_status"], note=payload["note"],
                              project_id=payload["project_id"], source=payload["source"])
            st.session_state.pop("pay_draft", None)
            st.success("登録しました")
            st.rerun()
    st.divider()
    st.markdown("**登録済みの買掛一覧**")
    _vends, _projs = _names(store.list_payables_vendors), _names(store.list_projects)
    _disp = [{"請求書の日付": r.get("date") or r.get("month") or "",
              "取引先": _vends.get(r["vendor_id"], ""), "金額": _yen(r["amount"]),
              "原本区分": r.get("original_status") or "", "備考": r.get("note") or "",
              "案件": _projs.get(r["project_id"], "")} for r in store.list_payables()]
    nice_table(_disp, "買掛の登録はまだありません。")
    section_export(_disp, "買掛一覧", key="pay")

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
        month = st.text_input("月度（例：2026-07）")
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
    st.divider()
    st.markdown("**登録済みの売掛一覧**")
    _clients, _projs = _names(store.list_receivables_clients), _names(store.list_projects)
    _disp = [{"月度": r.get("month") or "", "売掛先": _clients.get(r["client_id"], ""),
              "金額": _yen(r["amount"]), "備考": r.get("note") or "",
              "案件": _projs.get(r["project_id"], "")} for r in store.list_receivables()]
    nice_table(_disp, "売掛の登録はまだありません。")
    section_export(_disp, "売掛一覧", key="recv")
