import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, period_picker

apply_app_style()
st.title("⬇️ 経理提出用データ出力")

kind = st.selectbox("データ種別", ["小口一覧", "買掛一覧", "売掛一覧", "業務委託費一覧"])
# 🔴 2026-08-28 オーナー指示: 日付の手入力をやめる。
# ここは「期間 開始/終了(YYYY-MM-DD もしくは 空)」の自由入力だったが、
# 他の画面と同じ共通の期間フィルタ(全期間/今月/今週/期間指定＝カレンダー)に揃える。
# 既定の「全期間」は、これまでの「空欄＝絞り込みなし」と同じ動き。
d_from, d_to, _period_note = period_picker(key="export_period")
st.caption(f"対象期間: {_period_note}")


def _within(value, lo, hi):
    if value is None:
        return False
    if lo and str(value) < lo:
        return False
    if hi and str(value) > hi:
        return False
    return True


if kind == "小口一覧":
    rows = store.list_petty_cash(date_from=(d_from or None), date_to=(d_to or None))
    df = pd.DataFrame(rows)
elif kind == "買掛一覧":
    rows = [r for r in store.list_payables() if _within(r.get("month"), d_from[:7], d_to[:7])] \
        if (d_from or d_to) else store.list_payables()
    df = pd.DataFrame(rows)
elif kind == "売掛一覧":
    rows = [r for r in store.list_receivables() if _within(r.get("month"), d_from[:7], d_to[:7])] \
        if (d_from or d_to) else store.list_receivables()
    df = pd.DataFrame(rows)  # noqa: E501 - 月度は YYYY-MM なので先頭7文字で比較する
else:  # 業務委託費一覧
    flat = []
    id2name = {d["id"]: d["name"] for d in store.list_distributors()}
    for inv in store.list_contract_invoices():
        if not _within(inv.get("issue_date"), d_from, d_to) and (d_from or d_to):
            continue
        detail = store.get_contract_invoice(inv["id"])
        flat.append({"ID": inv["id"], "配布員": id2name.get(inv["distributor_id"]),
                     "発行日": inv["issue_date"],
                     "期間": f'{inv["period_from"]}〜{inv["period_to"]}',
                     "請求額": posting_logic.invoice_total(detail["lines"])})
    df = pd.DataFrame(flat)

st.dataframe(df, use_container_width=True, hide_index=True)

if not df.empty:
    csv = "﻿" + df.to_csv(index=False)
    st.download_button("CSVダウンロード", data=csv.encode("utf-8"),
                       file_name=f"{kind}.csv", mime="text/csv")
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=kind)
    st.download_button("Excelダウンロード", data=buf.getvalue(),
                       file_name=f"{kind}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
