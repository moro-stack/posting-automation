import io
import zipfile
from datetime import date as _date

import pandas as pd
import streamlit as st

from common import invoice_excel
from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, section_export, nice_table, period_picker
from common.excel_io import freeze_xlsx_bytes

apply_app_style()
st.title("業務委託登録")

dists = {d["name"]: d["id"] for d in store.list_distributors(only_active=True)}
projs = {p["name"]: p["id"] for p in store.list_projects(only_active=True)}

if not dists:
    st.warning("先に『マスタ管理』で配布委託先(配布員)を登録してください。")
    st.stop()

tab_reg, tab_list = st.tabs(["✒️ 登録", "📋 登録済み一覧"])

# ============================================================ 登録タブ
with tab_reg:
    dist_name = st.selectbox("配布員", list(dists.keys()),
                             help="配布員名を入力すると絞り込めます。新規は『マスタ管理』で登録してください。")
    c1, c2, c3 = st.columns(3)
    issue = c1.date_input("発行日", value=_date.today())
    pfrom = c2.date_input("配布業務期間(開始)")
    pto = c3.date_input("配布業務期間(終了)")

    st.markdown("**明細**（案件・種別・数量・単価）｜数量と単価は小数点も入力できます")
    st.caption("案件を「その他」にした行は、右の『その他の案件名』に何の案件か入力してください"
               "（号別明細の『その他』で確認できます）。")
    editor = st.data_editor(
        pd.DataFrame([{"案件": "", "種別": "配布", "数量": 0.0, "単価": 0.0, "その他の案件名": ""}]),
        num_rows="dynamic",
        column_config={
            "案件": st.column_config.SelectboxColumn(options=list(projs.keys())),
            "種別": st.column_config.SelectboxColumn(
                options=["配布", "挟み込み", "交通費", "手当", "その他"]),
            "数量": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%g"),
            "単価": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%g"),
            "その他の案件名": st.column_config.TextColumn(
                help="案件を『その他』にしたとき、何の案件か"),
        },
        column_order=["案件", "種別", "数量", "単価", "その他の案件名"],
        use_container_width=True, key="line_editor")

    lines = []
    for _, row in editor.iterrows():
        if not row["案件"] or pd.isna(row["案件"]):
            continue
        qty = posting_logic._num(row["数量"]) if pd.notna(row["数量"]) else 0
        price = posting_logic._num(row["単価"]) if pd.notna(row["単価"]) else 0
        remark = row["種別"] if pd.notna(row["種別"]) else "配布"
        olabel = row.get("その他の案件名") if "その他の案件名" in row else None
        olabel = (str(olabel).strip() or None) if (pd.notna(olabel) and row["案件"] == "その他") else None
        lines.append({"project_id": projs.get(row["案件"]), "project_name": row["案件"],
                      "report_qty": qty, "unit_price": price, "amount": qty * price,
                      "remark": remark, "other_label": olabel})

    if lines:
        st.markdown("**明細（確認）**")
        preview = [{
            "案件": l["project_name"],
            "種別": l["remark"],
            "数量": posting_logic.qty_label(l["report_qty"], l["remark"]),
            "単価": f'¥{posting_logic.fmt_num(l["unit_price"])}',
            "合計": f'¥{posting_logic.fmt_num(l["amount"])}',
        } for l in lines]
        nice_table(preview)

        m1, m2 = st.columns(2)
        m1.metric("ご請求金額(税込)", f"¥{posting_logic.fmt_num(posting_logic.invoice_total(lines))}")
        m2.metric("配布部数(配布+挟み込み)",
                  f"{posting_logic.fmt_num(posting_logic.delivered_copies(lines))} 部")

    col_save, col_dl = st.columns(2)
    if col_save.button("この請求を登録", type="primary", disabled=not lines):
        store.add_contract_invoice(
            dists[dist_name], str(issue), str(pfrom), str(pto),
            [{"project_id": l["project_id"], "report_qty": l["report_qty"],
              "unit_price": l["unit_price"], "remark": l["remark"],
              "other_label": l.get("other_label")} for l in lines])
        st.success("登録しました")

    if lines:
        if len(lines) > 6:
            st.warning("明細は6行までです。案件ごとに集約してください。")
        else:
            xlsx = invoice_excel.build_invoice_xlsx(
                distributor_name=dist_name,
                issue_date=str(issue), period_from=str(pfrom), period_to=str(pto), lines=lines)
            col_dl.download_button(
                "報告書兼請求書をExcelでダウンロード", data=xlsx,
                file_name=f"業務完了報告書兼請求書_{dist_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:", key="dl_invoice")


# ============================================================ 登録済み一覧タブ
def _invoice_out_lines(detail, id2proj):
    """保存済み請求の明細を報告書生成用の行に整える。"""
    return [{"project_name": id2proj.get(l.get("project_id"), ""),
             "report_qty": l.get("report_qty"), "unit_price": l.get("unit_price"),
             "amount": l.get("amount"), "remark": l.get("remark")}
            for l in detail["lines"]]


def _export_status(inv, today):
    """『N日前に出力済み』の注意ラベル。未出力なら空。"""
    n = posting_logic.days_since(inv.get("last_exported_at"), today=today)
    if n is None:
        return ""
    if n == 0:
        return "⚠️ 本日出力済み"
    return f"⚠️ {n}日前（{str(inv.get('last_exported_at'))[:10]}）に出力済み"


with tab_list:
    invoices = store.list_contract_invoices()
    if not invoices:
        st.caption("登録済みの請求はまだありません。")
        st.stop()

    id2name = {d["id"]: d["name"] for d in store.list_distributors()}
    id2proj = {p["id"]: p["name"] for p in store.list_projects()}
    today = _date.today().isoformat()

    # --- 期間フィルタ（左）＋ 配布員フィルタ（右）を横並びで ---
    col_period, col_dist = st.columns([2, 1])
    with col_period:
        lo, hi, note = period_picker(key="contract_period")
        st.caption(f"表示期間: {note}")
    with col_dist:
        # 実際に請求のある配布員だけを候補に出す
        names_in_use = sorted({id2name.get(i["distributor_id"], "?") for i in invoices})
        dist_filter = st.selectbox("配布員で絞り込み", ["全員"] + names_in_use,
                                   key="contract_dist_filter",
                                   help="選んだ配布員の明細だけ表示します。")

    invoices = [i for i in invoices if posting_logic.in_period(i.get("issue_date"), lo, hi)]
    if dist_filter != "全員":
        invoices = [i for i in invoices if id2name.get(i["distributor_id"], "?") == dist_filter]
    # 既定は発行日の新しい順（並び順の切替は廃止）
    invoices = sorted(invoices, key=lambda i: i.get("issue_date") or "", reverse=True)

    if not invoices:
        st.caption("表示期間・配布員の条件に合う請求はありません。")
        st.stop()

    # --- 一覧（チェックで複数選択） ---
    detail_by_id = {inv["id"]: store.get_contract_invoice(inv["id"]) for inv in invoices}
    disp_rows = []
    for inv in invoices:
        total = posting_logic.invoice_total(detail_by_id[inv["id"]]["lines"])
        disp_rows.append({
            "選択": False,
            "No.": inv["id"],
            "配布員": id2name.get(inv["distributor_id"], "?"),
            "発行日": inv.get("issue_date") or "",
            "配布業務期間": f'{inv.get("period_from")}〜{inv.get("period_to")}',
            "請求額": f"¥{posting_logic.fmt_num(total)}",
            "出力状況": _export_status(inv, today),
        })

    st.caption("チェックを付けた請求を、下のボタンでまとめて出力できます。")
    edited = st.data_editor(
        pd.DataFrame(disp_rows), hide_index=True, use_container_width=True,
        column_config={"選択": st.column_config.CheckboxColumn("選択", default=False)},
        disabled=["No.", "配布員", "発行日", "配布業務期間", "請求額", "出力状況"],
        key="contract_list_editor")
    selected_ids = [int(r["No."]) for _, r in edited.iterrows() if r["選択"]]

    st.caption(f"選択中：{len(selected_ids)}件")
    b1, b2 = st.columns(2)

    # --- 報告書をまとめてZIP ---
    zip_buf, skipped = io.BytesIO(), []
    if selected_ids:
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for iid in selected_ids:
                detail = detail_by_id.get(iid) or store.get_contract_invoice(iid)
                head = detail["invoice"]
                out_lines = _invoice_out_lines(detail, id2proj)
                if len(out_lines) > 6:
                    skipped.append(iid)
                    continue
                name = id2name.get(head["distributor_id"], "")
                xlsx = invoice_excel.build_invoice_xlsx(
                    distributor_name=name, issue_date=head["issue_date"],
                    period_from=head["period_from"], period_to=head["period_to"],
                    lines=out_lines)
                zf.writestr(f'業務完了報告書兼請求書_{name}_{head["issue_date"]}.xlsx', xlsx)
    exported_ids = [i for i in selected_ids if i not in skipped]
    if skipped:
        st.warning("次の請求は明細が6行を超えるためスキップしました（案件ごとに集約してください）："
                   + "、".join(f"No.{i}" for i in skipped))

    if b1.download_button(
            f"選択した請求の報告書をまとめてダウンロード（ZIP・{len(exported_ids)}件）",
            data=zip_buf.getvalue(),
            file_name=f"業務完了報告書_選択{len(exported_ids)}件.zip",
            mime="application/zip", disabled=not exported_ids, key="dl_zip"):
        for iid in exported_ids:
            store.mark_contract_invoice_exported(iid)
        st.rerun()

    # --- 選択した行を一覧Excelで ---
    if selected_ids:
        sel_rows = [{k: v for k, v in r.items() if k != "選択"}
                    for _, r in edited.iterrows() if r["選択"]]
        _buf = io.BytesIO()
        with pd.ExcelWriter(_buf, engine="openpyxl") as w:
            pd.DataFrame(sel_rows).to_excel(w, index=False, sheet_name="選択した請求")
        b2.download_button(
            f"選択した行を一覧Excelで保存（{len(selected_ids)}件）",
            data=freeze_xlsx_bytes(_buf.getvalue()),
            file_name=f"業務委託_選択一覧_{len(selected_ids)}件.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:", key="dl_sel_list")

    # --- 配布員別 報酬合計（表示期間内） ---
    st.divider()
    st.markdown("**配布員別 報酬合計（表示期間内）**")
    summary = {}
    for inv in invoices:
        total = posting_logic.invoice_total(detail_by_id[inv["id"]]["lines"])
        name = id2name.get(inv["distributor_id"], "?")
        summary[name] = summary.get(name, 0) + total
    nice_table([{"配布員": k, "報酬合計": f"¥{posting_logic.fmt_num(v)}"}
                for k, v in summary.items()])
