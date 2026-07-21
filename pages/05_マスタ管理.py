import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, nice_table, flash, show_flash, confirm_delete

apply_app_style()
st.title("マスタ管理")

_ORIGINAL_STATUSES = posting_logic.ORIGINAL_STATUSES
_PAY_TYPES = ["歩合", "日当", "時給", "月給"]
_KINDS = ["業務委託", "自社社員", "アルバイト"]


def _index_of(options, value):
    """selectbox の初期選択位置。今の値が選択肢に無ければ先頭に落とす(既存データの保険)。"""
    return options.index(value) if value in options else 0


def _split_active(rows):
    """有効な行と停止中の行に分ける。一覧は有効だけを出し、停止中は折りたたみへ。"""
    return ([r for r in rows if r.get("active", 1)],
            [r for r in rows if not r.get("active", 1)])


def _remove_ui(master, row, *, label_name, update_fn, button_container=None):
    """削除ボタン。使用実績があれば物理削除でなく停止中にする(過去データを守るため)。
    button_container を渡すと、ボタンだけをそこ(行の右端の狭い列)に置き、
    確認UIは呼び出した場所＝全幅に出す。section は master 名＝タブごとに分ける。"""
    n = store.count_master_usage(master, row["id"])
    if posting_logic.master_delete_action(n) == "delete":
        confirm_delete(
            key=f"del_{master}_{row['id']}", label="削除",
            detail=f"{label_name}「{row['name']}」を削除します。使用実績はありません。",
            on_confirm=lambda: _delete_master(master, row["id"]),
            success="削除しました", section=master, button_container=button_container)
    else:
        confirm_delete(
            key=f"off_{master}_{row['id']}", label="停止中にする",
            warning=f"⚠️ 「{row['name']}」は {n}件のデータで使用中です。",
            detail="過去データを残すため、削除ではなく停止中にします"
                   "（登録の選択肢から消えるだけで、一覧・報告書の表示は変わりません）。",
            on_confirm=lambda: update_fn(row["id"], active=0),
            success="停止中にしました", section=master, button_container=button_container)


_DELETE_FNS = {
    "project": store.delete_project,
    "expense_category": store.delete_expense_category,
    "payables_vendor": store.delete_payables_vendor,
    "receivables_client": store.delete_receivables_client,
    "distributor": store.delete_distributor,
}


def _delete_master(master, row_id):
    if master == "distributor":
        # count_master_usage は日当金額(distributor_daily_rates)を「使用実績」として
        # 数えない(配布員の付随設定という位置づけのため)。そのため日当金額だけを持つ
        # 配布員も物理削除の対象になり、掃除しないと孤立行が残る。一緒に消しておく。
        store.replace_daily_rates(row_id, [])
    _DELETE_FNS[master](row_id)


def _inactive_ui(master, inactive, *, update_fn):
    """停止中のマスタは折りたたみの中に。ここから有効に戻せる。"""
    if not inactive:
        return
    with st.expander(f"停止中（{len(inactive)}件）", expanded=False):
        for r in inactive:
            c1, c2 = st.columns([3, 1])
            c1.write(r["name"])
            if c2.button("有効に戻す", key=f"on_{master}_{r['id']}"):
                update_fn(r["id"], active=1)
                flash("有効に戻しました", master)
                st.rerun()


@st.dialog("編集")
def _edit_dialog(master, row, *, update_fn, fields_fn, with_daily=False):
    """編集ボタン→別窓(st.dialog)でその行の項目を直す。

    st.form は使わず素のウィジェット＋「更新／やめる」ボタン(st.data_editor を
    form 内に入れる不確実性を避けるため)。業務委託で支払形態＝日当のときだけ、
    同じ窓に業務名×金額の日当金額の設定を出し、更新時に replace_daily_rates で保存する。

    fields_fn(row) が入力欄を描き、update_fn に渡す kwargs の dict を返す。

    ⚠️ fields_fn の中のウィジェット key には必ず行idを入れること。固定keyだと
    Streamlit が session_state を保持し、編集する行を切り替えても前の行に入力した値が
    残ったまま描画され、更新時に別の行へ誤って書き込む(2026-07-14に実際に起きた事故)。
    """
    st.markdown(f"**「{row['name']}」を編集**")
    kwargs = fields_fn(row)   # 素のウィジェット。key に行idを含む(既存 _*_fields のまま)
    edited_rates = None
    if with_daily and kwargs.get("pay_type") == "日当":
        st.markdown("**日当金額の設定**")
        rates = store.list_daily_rates(row["id"])
        base = pd.DataFrame(
            [{"業務名": r["work_name"], "金額": int(r["amount"])} for r in rates]
            or [{"業務名": "", "金額": 0}])
        edited_rates = st.data_editor(
            base, num_rows="dynamic", use_container_width=True,
            column_config={"金額": st.column_config.NumberColumn(min_value=0, step=1,
                                                                format="localized")},
            key=f"edit_rates_{row['id']}")
        st.caption("ここで登録した業務名と金額が、業務委託登録の明細で選べるようになります。")
    c1, c2 = st.columns(2)
    if c1.button("更新", key=f"edit_submit_{master}_{row['id']}", type="primary"):
        if str(kwargs.get("name") or "").strip():
            update_fn(row["id"], **kwargs)
            if edited_rates is not None:
                store.replace_daily_rates(row["id"], [
                    {"work_name": str(r["業務名"]), "amount": int(r["金額"] or 0)}
                    for _, r in edited_rates.iterrows() if str(r["業務名"] or "").strip()])
            # section(=master)を付けないと、最初に描画される案件タブの show_flash() が
            # メッセージを奪い、操作したタブには何も出ない。
            flash("更新しました", master)
            st.rerun()
    if c2.button("やめる", key=f"edit_cancel_{master}_{row['id']}"):
        st.rerun()


def _name_fields(master, label_name):
    """名前だけを直すマスタ(案件・費目・売掛先)の入力欄。"""
    def _fields(row):
        name = st.text_input(f"{label_name}名", value=row["name"],
                             key=f"edit_name_{master}_{row['id']}")
        return {"name": name.strip()}
    return _fields


def _vendor_fields(row):
    rid = row["id"]
    n = st.text_input("取引先名", value=row["name"], key=f"edit_name_payables_vendor_{rid}")
    c = st.text_input("既定の費目（家賃・電気 など）", value=row.get("default_category") or "",
                      key=f"edit_cat_payables_vendor_{rid}")
    opts = ["(なし)"] + _ORIGINAL_STATUSES
    o = st.selectbox("既定の原本区分", opts,
                     index=_index_of(opts, row.get("default_original_status")),
                     key=f"edit_orig_payables_vendor_{rid}")
    return {"name": n.strip(), "default_category": (c.strip() or None),
            "default_original_status": (None if o == "(なし)" else o)}


def _distributor_fields(row):
    rid = row["id"]
    n = st.text_input("氏名", value=row["name"], key=f"edit_name_distributor_{rid}")
    kind = st.selectbox("区分（雇用形態）", _KINDS, index=_index_of(_KINDS, row.get("kind")),
                        key=f"edit_kind_distributor_{rid}")
    pay_type = st.selectbox("支払形態（報酬の計算方法）", _PAY_TYPES,
                            index=_index_of(_PAY_TYPES, row.get("pay_type")),
                            key=f"edit_pay_distributor_{rid}")
    bank = st.text_area("振込先", value=row.get("bank_info") or "",
                        key=f"edit_bank_distributor_{rid}")
    h1, h2 = st.columns(2)
    # st.form の中では「支払形態を選んだ瞬間に出し分ける」ができない(Streamlitの仕様)ため、
    # 時給額・月額は両方出して caption で補う(登録フォームと同じ形)。
    hourly = h1.number_input("時給額", min_value=0, step=1,
                             value=int(row.get("hourly_rate") or 0),
                             key=f"edit_hourly_distributor_{rid}")
    monthly = h2.number_input("月額", min_value=0, step=1,
                              value=int(row.get("monthly_rate") or 0),
                              key=f"edit_monthly_distributor_{rid}")
    st.caption("時給額は支払形態が「時給」のとき、月額は「月給」のときだけ使います。"
               "日当の金額は下の「日当金額の設定」で入れてください。")
    return {"name": n.strip(), "kind": kind, "pay_type": pay_type,
            "bank_info": (bank.strip() or None),
            "hourly_rate": (int(hourly) or None),
            "monthly_rate": (int(monthly) or None)}


def _row_ui(master, row, *, update_fn, label_name, fields_fn, with_daily=False):
    """有効な行1つ。右端に編集・削除(or 停止中)ボタンを置く。
    編集は別窓(st.dialog)、確認UIは列の外＝全幅に出す(狭い列に押し込むと読めないため)。"""
    c1, c2, c3 = st.columns([4, 1, 1])
    c1.write(row["name"])
    if c2.button("編集", key=f"edit_{master}_{row['id']}"):
        _edit_dialog(master, row, update_fn=update_fn, fields_fn=fields_fn, with_daily=with_daily)
    _remove_ui(master, row, label_name=label_name, update_fn=update_fn,
               button_container=c3)


def _rows_ui(master, rows, *, update_fn, label_name, fields_fn):
    if not rows:
        st.caption(f"{label_name}はまだ登録されていません。")
        return
    for r in rows:
        _row_ui(master, r, update_fn=update_fn, label_name=label_name,
                fields_fn=fields_fn)


@st.dialog("新規登録")
def _add_simple_dialog(label, master, add_fn):
    name = st.text_input(f"{label}名", key=f"add_name_{master}")
    c1, c2 = st.columns(2)
    if c1.button("追加", key=f"add_submit_{master}", type="primary"):
        if name.strip():
            add_fn(name.strip())
            flash(f"{label}を追加しました", master)
            st.rerun()
    if c2.button("やめる", key=f"add_cancel_{master}"):
        st.rerun()


@st.dialog("買掛先を新規登録")
def _add_vendor_dialog():
    master = "payables_vendor"
    n = st.text_input("取引先名", key="add_name_payables_vendor")
    c = st.text_input("既定の費目（家賃・電気 など）", key="add_cat_payables_vendor")
    o = st.selectbox("既定の原本区分", ["(なし)"] + _ORIGINAL_STATUSES, key="add_orig_payables_vendor")
    c1, c2 = st.columns(2)
    if c1.button("追加", key="add_submit_payables_vendor", type="primary"):
        if n.strip():
            store.add_payables_vendor(n.strip(), default_category=(c.strip() or None),
                                      default_original_status=(None if o == "(なし)" else o))
            flash("買掛先を追加しました", master)
            st.rerun()
    if c2.button("やめる", key="add_cancel_payables_vendor"):
        st.rerun()


@st.dialog("業務委託を新規登録")
def _add_distributor_dialog():
    master = "distributor"
    n = st.text_input("配布員 氏名", key="add_name_distributor")
    kind = st.selectbox("区分（雇用形態）", _KINDS, key="add_kind_distributor")
    pay_type = st.selectbox("支払形態（報酬の計算方法）", _PAY_TYPES, key="add_pay_distributor")
    bank = st.text_area("振込先", key="add_bank_distributor",
                        placeholder="例：三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ")
    h1, h2 = st.columns(2)
    hourly = h1.number_input("時給額", min_value=0, step=1, key="add_hourly_distributor")
    monthly = h2.number_input("月額", min_value=0, step=1, key="add_monthly_distributor")
    st.caption("時給額は支払形態が「時給」、月額は「月給」のときだけ使います。"
               "日当の金額は登録後、その人の「編集」から設定できます。")
    c1, c2 = st.columns(2)
    if c1.button("追加", key="add_submit_distributor", type="primary"):
        if n.strip():
            store.add_distributor(n.strip(), kind=kind, pay_type=pay_type,
                                  bank_info=(bank.strip() or None),
                                  hourly_rate=(int(hourly) or None),
                                  monthly_rate=(int(monthly) or None))
            flash("業務委託を追加しました", master)
            st.rerun()
    if c2.button("やめる", key="add_cancel_distributor"):
        st.rerun()


def _simple_master(label, master, list_fn, add_fn, update_fn):
    show_flash(master)
    if st.button("＋ 新規登録", key=f"add_open_{master}"):
        _add_simple_dialog(label, master, add_fn)
    active, inactive = _split_active(list_fn())
    _rows_ui(master, active, update_fn=update_fn, label_name=label,
             fields_fn=_name_fields(master, label))
    _inactive_ui(master, inactive, update_fn=update_fn)   # ← Task 5 で廃止


tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["案件", "費目（小口）", "買掛先", "売掛先", "業務委託"])

with tab1:
    _simple_master("案件", "project", store.list_projects,
                   store.add_project, store.update_project)
with tab2:
    _simple_master("費目", "expense_category", store.list_expense_categories,
                   store.add_expense_category, store.update_expense_category)

with tab3:
    master = "payables_vendor"
    show_flash(master)
    if st.button("＋ 新規登録", key="add_open_payables_vendor"):
        _add_vendor_dialog()
    active, inactive = _split_active(store.list_payables_vendors())
    disp = [{"取引先": r["name"], "既定の費目": r.get("default_category") or "",
             "既定の原本区分": r.get("default_original_status") or ""} for r in active]
    nice_table(disp, "買掛先はまだ登録されていません。")
    st.caption("既定の原本区分を入れておくと、買掛登録で取引先名が一致したときに自動で入ります。")
    for r in active:
        _row_ui(master, r, update_fn=store.update_payables_vendor,
                label_name="買掛先", fields_fn=_vendor_fields)
    _inactive_ui(master, inactive, update_fn=store.update_payables_vendor)

with tab4:
    _simple_master("売掛先", "receivables_client", store.list_receivables_clients,
                   store.add_receivables_client, store.update_receivables_client)

with tab5:
    master = "distributor"
    show_flash(master)
    if st.button("＋ 新規登録", key="add_open_distributor"):
        _add_distributor_dialog()
    active, inactive = _split_active(store.list_distributors())
    disp = [{"配布員 氏名": r["name"], "区分": r.get("kind") or "",
             "支払形態": r.get("pay_type") or "",
             "時給額": r.get("hourly_rate") or "", "月額": r.get("monthly_rate") or "",
             "振込先": r.get("bank_info") or ""} for r in active]
    nice_table(disp, "業務委託はまだ登録されていません。")
    for r in active:
        _row_ui(master, r, update_fn=store.update_distributor,
                label_name="業務委託", fields_fn=_distributor_fields, with_daily=True)
    _inactive_ui(master, inactive, update_fn=store.update_distributor)
