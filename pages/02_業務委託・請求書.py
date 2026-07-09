from datetime import date as _date

import pandas as pd
import streamlit as st

from common import invoice_excel
from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, section_export

apply_app_style()
st.title("📄 業務委託/報告書兼請求書作成")

dists = {d["name"]: d["id"] for d in store.list_distributors(only_active=True)}
projs = {p["name"]: p["id"] for p in store.list_projects(only_active=True)}

if not dists:
    st.warning("先に『マスタ管理』で配布委託先(配布員)を登録してください。")
    st.stop()

dist_name = st.selectbox("配布員", list(dists.keys()))
c1, c2, c3 = st.columns(3)
issue = c1.date_input("発行日", value=_date.today())
pfrom = c2.date_input("配布業務期間(開始)")
pto = c3.date_input("配布業務期間(終了)")

st.markdown("**明細**（案件・報告数・単価・備考）")
editor = st.data_editor(
    pd.DataFrame([{"案件": "", "報告数": 0, "単価": 0, "備考": "配布"}]),
    num_rows="dynamic",
    column_config={
        "案件": st.column_config.SelectboxColumn(options=list(projs.keys())),
        "備考": st.column_config.SelectboxColumn(
            options=["配布", "挟み込み", "交通費", "手当", "その他"]),
    },
    use_container_width=True, key="line_editor")

lines = []
for _, row in editor.iterrows():
    if not row["案件"] or pd.isna(row["案件"]):
        continue
    qty = int(row["報告数"]) if pd.notna(row["報告数"]) else 0
    price = int(row["単価"]) if pd.notna(row["単価"]) else 0
    lines.append({"project_id": projs.get(row["案件"]), "project_name": row["案件"],
                  "report_qty": qty, "unit_price": price, "amount": qty * price,
                  "remark": row["備考"]})

if lines:
    st.metric("ご請求金額(税込)", f"¥{posting_logic.invoice_total(lines):,}")
    st.metric("配布部数(配布+挟み込み)", f"{posting_logic.delivered_copies(lines):,} 部")

col_save, col_dl = st.columns(2)
if col_save.button("この請求を登録", type="primary", disabled=not lines):
    store.add_contract_invoice(
        dists[dist_name], str(issue), str(pfrom), str(pto),
        [{"project_id": l["project_id"], "report_qty": l["report_qty"],
          "unit_price": l["unit_price"], "remark": l["remark"]} for l in lines])
    st.success("登録しました")

if lines:
    if len(lines) > 6:
        st.warning("明細は6行までです。案件ごとに集約してください。")
    else:
        xlsx = invoice_excel.build_invoice_xlsx(
            distributor_name=dist_name,
            issue_date=str(issue), period_from=str(pfrom), period_to=str(pto), lines=lines)
        col_dl.download_button(
            "完了報告書兼請求書をダウンロード", data=xlsx,
            file_name=f"業務完了報告書兼請求書_{dist_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.divider()
st.subheader("登録済みの請求 / 配布員別報酬")
invoices = store.list_contract_invoices()
if invoices:
    id2name = {d["id"]: d["name"] for d in store.list_distributors()}
    summary = {}
    rows = []
    for inv in invoices:
        detail = store.get_contract_invoice(inv["id"])
        total = posting_logic.invoice_total(detail["lines"])
        name = id2name.get(inv["distributor_id"], "?")
        summary[name] = summary.get(name, 0) + total
        rows.append({"ID": inv["id"], "配布員": name, "発行日": inv["issue_date"],
                     "期間": f'{inv["period_from"]}〜{inv["period_to"]}', "請求額": total})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    section_export(rows, "業務委託費一覧", key="contract")
    st.markdown("**配布員別 報酬合計**")
    st.dataframe([{"配布員": k, "報酬合計": v} for k, v in summary.items()],
                 use_container_width=True, hide_index=True)
