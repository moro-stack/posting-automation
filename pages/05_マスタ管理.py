import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, nice_table, flash, show_flash, confirm_delete

apply_app_style()
st.title("マスタ管理")

_ORIGINAL_STATUSES = posting_logic.ORIGINAL_STATUSES
_PAY_TYPES = ["歩合", "日当", "時給", "月給"]


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


def _rows_ui(master, rows, *, update_fn, label_name):
    """有効な行を1行ずつ出し、右端に削除(or 停止中)ボタンを置く。
    確認UIは列の外＝全幅に出す(狭い列に押し込むと確認文が読めないため)。"""
    if not rows:
        st.caption(f"{label_name}はまだ登録されていません。")
        return
    for r in rows:
        c1, c2 = st.columns([4, 1])
        c1.write(r["name"])
        _remove_ui(master, r, label_name=label_name, update_fn=update_fn,
                   button_container=c2)


def _simple_master(label, master, list_fn, add_fn, update_fn):
    show_flash(master)
    active, inactive = _split_active(list_fn())
    _rows_ui(master, active, update_fn=update_fn, label_name=label)
    _inactive_ui(master, inactive, update_fn=update_fn)
    with st.form(f"add_{label}", clear_on_submit=True):
        name = st.text_input(f"{label}名を追加")
        if st.form_submit_button("追加") and name.strip():
            add_fn(name.strip())
            flash(f"{label}を追加しました", master)
            st.rerun()


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
    active, inactive = _split_active(store.list_payables_vendors())
    disp = [{"取引先": r["name"], "既定の費目": r.get("default_category") or "",
             "既定の原本区分": r.get("default_original_status") or ""} for r in active]
    nice_table(disp, "買掛先はまだ登録されていません。")
    st.caption("既定の原本区分を入れておくと、買掛登録で取引先名が一致したときに自動で入ります。")
    for r in active:
        c1, c2 = st.columns([4, 1])
        c1.write(r["name"])
        _remove_ui(master, r, label_name="買掛先",
                   update_fn=store.update_payables_vendor, button_container=c2)
    _inactive_ui(master, inactive, update_fn=store.update_payables_vendor)
    with st.form("add_vendor", clear_on_submit=True):
        n = st.text_input("取引先名")
        c = st.text_input("既定の費目（家賃・電気 など）")
        o = st.selectbox("既定の原本区分", ["(なし)"] + _ORIGINAL_STATUSES)
        if st.form_submit_button("追加") and n.strip():
            store.add_payables_vendor(
                n.strip(), default_category=(c.strip() or None),
                default_original_status=(None if o == "(なし)" else o))
            flash("買掛先を追加しました", master)
            st.rerun()

with tab4:
    _simple_master("売掛先", "receivables_client", store.list_receivables_clients,
                   store.add_receivables_client, store.update_receivables_client)

with tab5:
    master = "distributor"
    show_flash(master)
    active, inactive = _split_active(store.list_distributors())
    disp = [{"配布員 氏名": r["name"], "区分": r.get("kind") or "",
             "支払形態": r.get("pay_type") or "",
             "時給額": r.get("hourly_rate") or "", "月額": r.get("monthly_rate") or "",
             "振込先": r.get("bank_info") or ""} for r in active]
    nice_table(disp, "業務委託はまだ登録されていません。")
    for r in active:
        c1, c2 = st.columns([4, 1])
        c1.write(r["name"])
        _remove_ui(master, r, label_name="業務委託",
                   update_fn=store.update_distributor, button_container=c2)
    _inactive_ui(master, inactive, update_fn=store.update_distributor)

    with st.form("add_dist", clear_on_submit=True):
        n = st.text_input("配布員 氏名")
        kind = st.selectbox("区分（雇用形態）", ["業務委託", "自社社員", "アルバイト"])
        pay_type = st.selectbox("支払形態（報酬の計算方法）", _PAY_TYPES)
        bank = st.text_area("振込先", placeholder="例：三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ")
        h1, h2 = st.columns(2)
        hourly = h1.number_input("時給額", min_value=0, step=1)
        monthly = h2.number_input("月額", min_value=0, step=1)
        st.caption("時給額は支払形態が「時給」のとき、月額は「月給」のときだけ使います。"
                   "日当の金額は、登録した後に下の「日当金額の設定」で入れてください。")
        if st.form_submit_button("追加") and n.strip():
            store.add_distributor(n.strip(), kind=kind, pay_type=pay_type,
                                  bank_info=(bank.strip() or None),
                                  hourly_rate=(int(hourly) or None),
                                  monthly_rate=(int(monthly) or None))
            flash("業務委託を追加しました", master)
            st.rerun()

    # --- 日当金額の設定（支払形態=日当の人だけ）---
    # st.form の中では「日当を選んだ瞬間に表を出す」ができない(Streamlitの仕様)ため、
    # 登録フォームとは別のセクションに置く。
    st.divider()
    st.markdown("**日当金額の設定**")
    nichito = [r for r in active if r.get("pay_type") == "日当"]
    if not nichito:
        st.caption("支払形態が「日当」の業務委託がいません。上で登録してください。")
    else:
        name2id = {r["name"]: r["id"] for r in nichito}
        pick = st.selectbox("配布員", list(name2id.keys()), key="rate_pick")
        did = name2id[pick]
        rates = store.list_daily_rates(did)
        base = pd.DataFrame(
            [{"業務名": r["work_name"], "金額": int(r["amount"])} for r in rates]
            or [{"業務名": "", "金額": 0}])
        edited = st.data_editor(
            base, num_rows="dynamic", use_container_width=True,
            column_config={"金額": st.column_config.NumberColumn(min_value=0, step=1,
                                                                format="localized")},
            key=f"rate_editor_{did}")
        st.caption("ここで登録した業務名と金額が、業務委託登録の明細で選べるようになります。")
        if st.button("日当金額を保存", key="rate_save"):
            store.replace_daily_rates(did, [
                {"work_name": str(r["業務名"]), "amount": int(r["金額"] or 0)}
                for _, r in edited.iterrows() if str(r["業務名"] or "").strip()])
            flash("日当金額を保存しました", master)
            st.rerun()
