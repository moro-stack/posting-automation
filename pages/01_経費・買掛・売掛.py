from datetime import date as _date, datetime as _datetime

import pandas as pd
import streamlit as st

from common import ocr
from common import posting_logic
from common import posting_store as store
from common.ui import (apply_app_style, nice_table, period_picker,
                       flash, show_flash,
                       selectable_list, list_action_bar)

apply_app_style()
st.title("小口／買掛／売掛の登録")

# 🔴 segmented_control は選択を解除でき、そのとき None を返す。None のまま下の
# if/elif/else に流すと else に落ちて「売掛」の画面が開いてしまうため、
# 明示的に既定へ戻す。
_MODES = ["小口", "買掛", "売掛", "車両"]

# 🔴 依頼①(2026-08-19大橋様→2026-08-20詳細確認): アドバリューは週ごとに案件が来て
# 「8-1」「8-2」「8-3」のように区分して管理している。「その他」向けに元々あった
# 案件区分の自由入力欄(other_label)を、アドバリューでも使えるようにする。
_OTHER_LABEL_PROJECTS = ("その他", "アドバリュー")
mode = st.segmented_control("入力の種類", _MODES, default=_MODES[0],
                            key="entry_mode") or _MODES[0]

_UPLOAD_TYPES = ["pdf", "jpg", "jpeg", "png"]
_REG_TAB = "✒️ 登録"
_LIST_TAB = "📋 登録済み一覧"
_ORIGINAL_STATUSES = posting_logic.ORIGINAL_STATUSES


def _project_options():
    return {p["name"]: p["id"] for p in store.list_projects(only_active=True)}


def _distributor_options():
    return {d["name"]: d["id"] for d in store.list_distributors(only_active=True)}


def _yen(v):
    try:
        return f"¥{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return v


def _to_date(s):
    """AIが読み取った日付文字列(YYYY-MM-DD)を date に。年月のみ/不正なら None。"""
    try:
        return _datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _names(list_fn):
    return {r["id"]: r["name"] for r in list_fn()}


def _period_filter(rows, date_key, key, label):
    """号別明細と同じ「全期間/今月/今週/期間指定」で rows を絞り、期間の合計を上に表示する。
    date_key は日付が入っている列名('date' もしくは 'month')。絞った rows を返す。"""
    lo, hi, note = period_picker(key=key)
    rows = posting_logic.filter_rows_by_period(rows, date_key, lo, hi)
    total = sum(posting_logic._num(r.get("amount")) for r in rows)
    st.markdown(
        f'''<div style="line-height:1.15;margin:.3rem 0 .8rem">
  <div style="color:#67788a;font-weight:700;font-size:.86rem">{label}の合計（{note}）</div>
  <div style="color:#1f2d3a;font-weight:800;font-size:1.8rem">¥{posting_logic.fmt_num(total)}</div>
  <div style="color:#67788a;font-size:.82rem">{len(rows)}件</div>
</div>''',
        unsafe_allow_html=True)
    return rows


def _ocr_files(files, reader, media_type=None):
    """複数ファイルをAIで読み取り、下書きリストを返す。失敗しても止めない(#7の保険)。

    media_type を渡すと拡張子からの判定を使わない。カメラ撮影(st.camera_input)は
    戻り値のファイル名が固定で拡張子を持たないため、image/jpeg を明示して渡す。
    """
    drafts = []
    prog = st.progress(0.0)
    for i, f in enumerate(files):
        name = getattr(f, "name", "") or "camera.jpg"
        try:
            mt = media_type or ocr.media_type_for(name)
            d = reader(f.getvalue(), mt, client=None)
        except Exception as e:  # noqa: BLE001
            d = {"amount": None, "_error": str(e)}
        d["_file"] = name
        drafts.append(d)
        prog.progress((i + 1) / len(files))
    prog.empty()
    n_ok = sum(1 for d in drafts if d.get("amount"))
    if n_ok < len(drafts):
        st.warning(f"{len(drafts)}件中 {n_ok}件のみ金額を取得できました。"
                   "（AI未設定/読取失敗分は手入力できます）")
    else:
        st.success(f"{len(drafts)}件を読み取りました。内容を確認・修正して登録してください。")

    # 🔴 エラーの中身を必ず画面に出す。ここを出していなかったせいで 2026-08-07 に
    # 「0件しか読めない」の原因究明に50分かかった(真因はIAMポリシーの付け忘れ)。
    # 折りたたまない。1クリック隠すと、また誰も気づかない。
    fails = ocr.failed_reads(drafts)
    if fails:
        st.error(f"{len(fails)}件でエラーが出ました。原因は下のとおりです。"
                 "（解決しない場合は、この文面をそのまま毛呂までお送りください）")
        for fname, reason in fails:
            st.code(f"{fname}\n{reason}", language=None)
    return drafts


if mode == "小口":
    st.subheader("小口経費（レシートOCR / 手入力）")
    tab_reg, tab_list = st.tabs([_REG_TAB, _LIST_TAB])

    with tab_reg:
        show_flash()
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

        # その場で撮って登録できるようにする(スマホ・PC共通)。
        # ⚠️ st.camera_input は「描画された時点で」ブラウザにカメラ許可を要求する。
        # 無条件に描くとページを開いただけで内カメラが点きっぱなしになるため、
        # 描画自体をボタンで出し分ける。
        st.session_state.setdefault("petty_camera_on", False)
        st.session_state.setdefault("petty_camera_gen", 0)

        if not st.session_state["petty_camera_on"]:
            if st.button("📷 カメラを起動", key="petty_camera_open"):
                st.session_state["petty_camera_on"] = True
                st.rerun()
        else:
            # 閉じるたびに gen を上げて key を変える。同じ key のままだと前回の写真が
            # 残り、撮り直したつもりで古い写真を読み取ってしまう。
            shot = st.camera_input(
                "その場で撮る",
                key=f"petty_camera_{st.session_state['petty_camera_gen']}")
            c_ocr, c_close = st.columns(2)
            if shot is not None and c_ocr.button("撮った写真をAIで読み取る",
                                                 key="petty_camera_ocr"):
                # camera_input はファイル名から拡張子を取れず、実体がPNGのこともある。
                # 撮影データ自身が持つ type を優先して決める(嘘のMIMEで送らないため)。
                drafts = _ocr_files([shot], ocr.extract_receipt,
                                    media_type=ocr.media_type_for_upload(shot))
                st.session_state.pop("petty_draft", None)
                st.session_state.pop("petty_bulk", None)
                if len(drafts) == 1 and drafts[0].get("amount"):
                    st.session_state["petty_draft"] = {"date": drafts[0].get("date"),
                                                       "amount": drafts[0].get("amount"),
                                                       "item": drafts[0].get("item")}
                else:
                    st.session_state["petty_bulk"] = drafts
            if c_close.button("カメラを閉じる", key="petty_camera_close"):
                st.session_state["petty_camera_on"] = False
                st.session_state["petty_camera_gen"] += 1
                st.rerun()

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
                               "金額": st.column_config.NumberColumn(min_value=0, step=1,
                                                                    format="localized")})
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
                flash(f"{cnt}件を登録しました")
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
            if cc1.button("はい", type="primary", key="petty_ok"):
                store.add_petty_cash(p["date"], p["category_id"], p["amount"],
                                     project_id=p["project_id"], memo=p["memo"],
                                     source=p["source"], other_label=p.get("other_label"),
                                     distributor_id=p.get("distributor_id"))
                del st.session_state["petty_pending"]
                flash("登録しました")
                st.rerun()
            if cc2.button("いいえ", key="petty_no"):
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
            dists = _distributor_options()
            dist = st.selectbox("配布員(任意)", ["(なし)"] + list(dists.keys()),
                                help="この費用が誰の分か。号別明細の雑費の内訳に出ます。")
            other_label = st.text_input(
                "案件区分", placeholder="「その他」なら何の案件か／「アドバリュー」なら8-1等の区分",
                help="案件を『その他』『アドバリュー』にしたときだけ使われます。"
                     "号別明細の内訳・案件切り替えで確認できます。")
            memo = st.text_input("メモ", value=draft.get("item") or "")
            if st.form_submit_button("登録") and amount > 0:
                payload = {"date": date or None, "category_id": cats.get(cat), "amount": int(amount),
                           "project_id": projs.get(proj), "memo": memo or None,
                           "source": "ocr" if ups else "manual",
                           "distributor_id": dists.get(dist),
                           "other_label": (other_label.strip() or None)
                                          if proj in _OTHER_LABEL_PROJECTS else None}
                if store.find_duplicate_petty(payload["date"], payload["category_id"], payload["amount"]):
                    st.session_state["petty_pending"] = payload
                    st.rerun()
                store.add_petty_cash(payload["date"], payload["category_id"], payload["amount"],
                                     project_id=payload["project_id"], memo=payload["memo"],
                                     source=payload["source"], other_label=payload["other_label"],
                                     distributor_id=payload["distributor_id"])
                st.session_state.pop("petty_draft", None)
                flash("登録しました")
                st.rerun()

    with tab_list:
        show_flash("petty")
        st.markdown("**登録済みの小口一覧**")
        _cats, _projs = _names(store.list_expense_categories), _names(store.list_projects)
        _dists = _names(store.list_distributors)
        _rows = _period_filter(store.list_petty_cash(), "date", "petty_period", "小口")
        _disp = [{"No.": r["id"], "日付": r["date"] or "",
                  "配布員": _dists.get(r.get("distributor_id"), ""),
                  "費目": _cats.get(r["category_id"], ""),
                  "金額": _yen(r["amount"]), "案件": _projs.get(r["project_id"], ""),
                  "メモ": r["memo"] or "",
                  "登録日": (r.get("created_at") or "")[:10]} for r in _rows]
        if not _disp:
            st.caption("小口の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="petty")
            list_action_bar(edited, key="petty", title="小口一覧",
                            filename="小口_選択一覧", section="petty",
                            delete_fn=store.delete_petty_cash)

elif mode == "買掛":
    st.subheader("買掛（固定費・法人業者）")
    tab_reg, tab_list = st.tabs([_REG_TAB, _LIST_TAB])

    with tab_reg:
        show_flash()
        ups = st.file_uploader("請求書画像・PDF（複数可・AIが取引先・金額・請求日を下書き抽出）",
                               type=_UPLOAD_TYPES, accept_multiple_files=True)
        if ups and st.button("画像/PDFをAIで読み取る"):
            drafts = _ocr_files(ups, ocr.extract_invoice)
            st.session_state.pop("pay_draft", None)
            st.session_state.pop("pay_bulk", None)
            if len(drafts) == 1 and drafts[0].get("amount"):
                st.session_state["pay_draft"] = {"vendor": drafts[0].get("vendor"),
                                                 "amount": drafts[0].get("amount"),
                                                 "date": drafts[0].get("date"),
                                                 "note": drafts[0].get("note")}
            else:
                st.session_state["pay_bulk"] = drafts

        # 複数請求書の一括登録レビュー(#9)。取引先・請求日もAI読み取り値を下書きに。
        if "pay_bulk" in st.session_state:
            st.markdown("**複数請求書の下書き（確認・修正して一括登録）**")
            bulk_df = pd.DataFrame([{
                "請求書の日付": d.get("date") or str(_date.today()),
                "取引先": d.get("vendor") or "",
                "金額": int(d.get("amount") or 0),
                "備考": d.get("note") or d.get("_file", ""),
            } for d in st.session_state["pay_bulk"]])
            edited = st.data_editor(
                bulk_df, num_rows="dynamic", use_container_width=True, key="pay_bulk_editor",
                column_config={"取引先": st.column_config.TextColumn(width="medium"),
                               "金額": st.column_config.NumberColumn(min_value=0, step=1,
                                                                    format="localized")})
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("全部登録", type="primary", key="pay_bulk_add"):
                cnt = 0
                for _, r in edited.iterrows():
                    amt = int(r["金額"]) if pd.notna(r["金額"]) else 0
                    if amt <= 0:
                        continue
                    store.add_payable(None, None, amt, date=str(r["請求書の日付"]),
                                      vendor_name=str(r["取引先"]) or None,
                                      note=str(r["備考"]) or None, source="ocr")
                    cnt += 1
                del st.session_state["pay_bulk"]
                flash(f"{cnt}件を登録しました")
                st.rerun()
            if b2.button("やめる", key="pay_bulk_cancel"):
                del st.session_state["pay_bulk"]
                st.rerun()

        draft = st.session_state.get("pay_draft",
                                     {"vendor": None, "amount": None, "date": None, "note": None})
        if st.session_state.get("pay_draft"):
            st.caption("✏️ AIが読み取った値は下のフォームで自由に修正できます。")

        if "pay_pending" in st.session_state:
            p = st.session_state["pay_pending"]
            st.warning("⚠️ 同様の内容が登録済みです。それでも登録しますか？")
            st.caption(f"請求書の日付 {p['date'] or '—'} ／ 金額 ¥{p['amount']:,}")
            cc1, cc2, _ = st.columns([1, 1, 4])
            if cc1.button("はい", type="primary", key="pay_ok"):
                store.add_payable(None, None, p["amount"], date=p["date"],
                                  vendor_name=p["vendor_name"], original_status=p["original_status"],
                                  note=p["note"], source=p["source"],
                                  project_id=p.get("project_id"), other_label=p.get("other_label"))
                del st.session_state["pay_pending"]
                flash("登録しました")
                st.rerun()
            if cc2.button("いいえ", key="pay_no"):
                del st.session_state["pay_pending"]
                st.rerun()

        with st.form("payable", clear_on_submit=True):
            inv_date = st.date_input("請求書の日付",
                                     value=_to_date(draft.get("date")) or _date.today())
            vendor = st.text_input("取引先（請求元の会社名）", value=draft.get("vendor") or "")
            amount = st.number_input("金額(税込)", min_value=0,
                                     value=int(draft.get("amount") or 0), step=1)
            _vendors = store.list_payables_vendors()
            _auto = posting_logic.resolve_original_status(vendor, _vendors)
            original = st.selectbox(
                "原本区分", _ORIGINAL_STATUSES,
                index=(_ORIGINAL_STATUSES.index(_auto) if _auto in _ORIGINAL_STATUSES else 0))
            # caption の条件は selectbox の index と必ず揃えること。`if _auto:` だけにすると
            # 選択肢に無い値のとき、実際は先頭(原本あり)が選ばれているのに
            # 「既定『◯◯』を反映しました」と嘘の案内が出る。
            if _auto in _ORIGINAL_STATUSES:
                st.caption(f"✔️ 買掛先マスタの既定「{_auto}」を反映しました（変更できます）。")
            pay_projs = _project_options()
            pay_proj = st.selectbox("案件(任意)", ["(なし)"] + list(pay_projs.keys()))
            pay_other = st.text_input(
                "案件区分", placeholder="「その他」なら何の案件か／「アドバリュー」なら8-1等の区分",
                help="案件を『その他』『アドバリュー』にしたときだけ使われます。"
                     "号別明細の内訳・案件切り替えで確認できます。")
            note = st.text_input("備考", value=draft.get("note") or "")
            if st.form_submit_button("登録") and amount > 0:
                payload = {"date": str(inv_date), "vendor_name": vendor or None,
                           "amount": int(amount), "original_status": original, "note": note or None,
                           "source": "ocr" if ups else "manual",
                           "project_id": pay_projs.get(pay_proj),
                           "other_label": (pay_other.strip() or None)
                                          if pay_proj in _OTHER_LABEL_PROJECTS else None}
                if store.find_duplicate_payable(payload["date"], None, payload["amount"],
                                                vendor_name=payload["vendor_name"]):
                    st.session_state["pay_pending"] = payload
                    st.rerun()
                store.add_payable(None, None, payload["amount"], date=payload["date"],
                                  vendor_name=payload["vendor_name"],
                                  original_status=payload["original_status"], note=payload["note"],
                                  source=payload["source"], project_id=payload["project_id"],
                                  other_label=payload["other_label"])
                st.session_state.pop("pay_draft", None)
                flash("登録しました")
                st.rerun()

    with tab_list:
        show_flash("payable")
        st.markdown("**登録済みの買掛一覧**")
        _vends = _names(store.list_payables_vendors)
        _rows = _period_filter(store.list_payables(), "month", "pay_period", "買掛")
        _disp = [{"No.": r["id"], "請求月度": r.get("month") or "",
                  "請求書の日付": r.get("date") or "",
                  "取引先": r.get("vendor_name") or _vends.get(r.get("vendor_id"), ""),
                  "金額": _yen(r["amount"]),
                  "原本区分": r.get("original_status") or "",
                  "備考": r.get("note") or "",
                  "登録日": (r.get("created_at") or "")[:10]} for r in _rows]
        if not _disp:
            st.caption("買掛の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="pay")
            list_action_bar(edited, key="pay", title="買掛一覧",
                            filename="買掛_選択一覧", section="payable",
                            delete_fn=store.delete_payable)

elif mode == "売掛":
    st.subheader("売掛（売上）")
    tab_reg, tab_list = st.tabs([_REG_TAB, _LIST_TAB])

    with tab_reg:
        show_flash()
        if "recv_pending" in st.session_state:
            p = st.session_state["recv_pending"]
            st.warning("⚠️ 同様の内容が登録済みです。それでも登録しますか？")
            st.caption(f"月度 {p['month'] or '—'} ／ 金額 ¥{p['amount']:,}")
            cc1, cc2, _ = st.columns([1, 1, 4])
            if cc1.button("はい", type="primary", key="recv_ok"):
                store.add_receivable(p["month"], p["client_id"], p["amount"],
                                     note=p["note"], project_id=p["project_id"],
                                     other_label=p.get("other_label"))
                del st.session_state["recv_pending"]
                flash("登録しました")
                st.rerun()
            if cc2.button("いいえ", key="recv_no"):
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
            recv_other = st.text_input(
                "案件区分", placeholder="「その他」なら何の案件か／「アドバリュー」なら8-1等の区分",
                help="案件を『その他』『アドバリュー』にしたときだけ使われます。"
                     "号別明細の内訳・案件切り替えで確認できます。")
            if st.form_submit_button("登録") and amount > 0:
                payload = {"month": month or None, "client_id": clients.get(client),
                           "amount": int(amount), "note": note or None, "project_id": projs.get(proj),
                           "other_label": (recv_other.strip() or None)
                                          if proj in _OTHER_LABEL_PROJECTS else None}
                if store.find_duplicate_receivable(payload["month"], payload["client_id"], payload["amount"]):
                    st.session_state["recv_pending"] = payload
                    st.rerun()
                store.add_receivable(payload["month"], payload["client_id"], payload["amount"],
                                     note=payload["note"], project_id=payload["project_id"],
                                     other_label=payload["other_label"])
                flash("登録しました")
                st.rerun()

    with tab_list:
        show_flash("receivable")
        st.markdown("**登録済みの売掛一覧**")
        _clients, _projs = _names(store.list_receivables_clients), _names(store.list_projects)
        _rows = _period_filter(store.list_receivables(), "month", "recv_period", "売掛")
        _disp = [{"No.": r["id"], "月度": r.get("month") or "",
                  "売掛先": _clients.get(r["client_id"], ""),
                  "金額": _yen(r["amount"]), "備考": r.get("note") or "",
                  "案件": _projs.get(r["project_id"], ""),
                  "登録日": (r.get("created_at") or "")[:10]} for r in _rows]
        if not _disp:
            st.caption("売掛の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="recv")
            list_action_bar(edited, key="recv", title="売掛一覧",
                            filename="売掛_選択一覧", section="receivable",
                            delete_fn=store.delete_receivable)

else:  # 車両
    st.subheader("車両使用履歴")
    tab_reg, tab_list = st.tabs([_REG_TAB, _LIST_TAB])

    _VEHICLE_PRESETS = ["ハイエース", "軽バン", "レンタカー", "その他"]

    with tab_reg:
        show_flash()
        with st.form("vehicle", clear_on_submit=True):
            v_date = st.text_input("日付（例：2026-07-05）")
            v_kind = st.selectbox("車両", _VEHICLE_PRESETS)
            v_other = st.text_input(
                "車両名", placeholder="「その他」を選んだときだけ入力（例：新しく借りた軽トラ等）",
                help="車両が『その他』のときだけ使われます。")
            driver = st.text_input("ドライバー")
            oc1, oc2 = st.columns(2)
            odo_start = oc1.number_input("開始時の走行距離メーター", min_value=0, step=1, value=0)
            odo_end = oc2.number_input("終了時の走行距離メーター", min_value=0, step=1, value=0)
            purpose = st.text_input("使用用途")
            fuel = st.number_input("給油量(L・任意)", min_value=0.0, step=0.1, value=0.0, format="%.2f")
            if st.form_submit_button("登録"):
                vehicle_name = (v_other.strip() if v_kind == "その他" else v_kind)
                if not vehicle_name:
                    st.error("車両名を入力してください。")
                else:
                    store.add_vehicle_log(
                        v_date or None, vehicle_name, driver.strip() or None,
                        odo_start or None, odo_end or None,
                        purpose=purpose.strip() or None,
                        fuel_liters=fuel or None)
                    flash("登録しました")
                    st.rerun()

    with tab_list:
        show_flash("vehicle")
        st.markdown("**登録済みの車両使用履歴**")
        lo, hi, note = period_picker(key="vehicle_period")
        _rows = posting_logic.filter_rows_by_period(store.list_vehicle_logs(), "date", lo, hi)
        st.caption(f"表示期間: {note}（{len(_rows)}件）")
        _disp = [{"No.": r["id"], "日付": r.get("date") or "",
                  "車両": r.get("vehicle") or "",
                  "ドライバー": r.get("driver") or "",
                  "走行距離": f'{r["distance"]}km' if r.get("distance") is not None else "",
                  "使用用途": r.get("purpose") or "",
                  "給油量": f'{r["fuel_liters"]}L' if r.get("fuel_liters") is not None else "",
                  "登録日": (r.get("created_at") or "")[:10]} for r in _rows]
        if not _disp:
            st.caption("車両使用履歴の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="vehicle")
            list_action_bar(edited, key="vehicle", title="車両使用履歴",
                            filename="車両使用履歴_選択一覧", section="vehicle",
                            delete_fn=store.delete_vehicle_log)
