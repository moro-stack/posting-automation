import io
import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import (apply_app_style, nice_table, period_picker, show_flash,
                       selectable_list, list_action_bar)

apply_app_style()
show_flash()
st.title("原価・売上まとめ（KPS大阪支社）")


def _yen(v):
    return f"¥{posting_logic.fmt_num(v)}"


lo, hi, note = period_picker(key="summary_period")
st.caption(f"表示期間: {note}")

# 全案件横断で集める（project_id 指定なし＝全件）
receivables = [r for r in store.list_receivables() if posting_logic.in_period(r.get("month"), lo, hi)]
payables = [r for r in store.list_payables()
            if posting_logic.in_period(r.get("date") or r.get("month"), lo, hi)]
petty = [r for r in store.list_petty_cash() if posting_logic.in_period(r.get("date"), lo, hi)]
manual = [r for r in store.list_issue_manual_costs()
          if r.get("work_date") is None or posting_logic.in_period(r.get("work_date"), lo, hi)]
contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    for ln in detail["lines"]:
        ln = dict(ln)
        ln["issue_date"] = inv.get("issue_date")
        ln["distributor_id"] = inv.get("distributor_id")
        contract_lines.append(ln)

id2proj = {p["id"]: p["name"] for p in store.list_projects()}
id2vendor = {v["id"]: v["name"] for v in store.list_payables_vendors()}
id2cat = {c["id"]: c["name"] for c in store.list_expense_categories()}
id2client = {c["id"]: c["name"] for c in store.list_receivables_clients()}
id2dist = {d["id"]: d["name"] for d in store.list_distributors()}

totals = posting_logic.company_summary_totals(
    receivables=receivables, payables=payables, petty=petty,
    contract_lines=contract_lines, manual=manual)
rows = posting_logic.company_summary_rows(
    receivables=receivables, payables=payables, petty=petty,
    contract_lines=contract_lines, manual=manual,
    id2proj=id2proj, id2vendor=id2vendor, id2cat=id2cat,
    id2client=id2client, id2dist=id2dist)

s1, s2, s3 = st.columns(3)
s1.markdown(f'<div style="color:#67788a;font-weight:700;font-size:.9rem">売上（税込）</div>'
            f'<div style="color:#1f2d3a;font-weight:800;font-size:2.2rem">{_yen(totals["sales"])}</div>',
            unsafe_allow_html=True)
s2.markdown(f'<div style="color:#67788a;font-weight:700;font-size:.9rem">原価（税込）</div>'
            f'<div style="color:#1f2d3a;font-weight:800;font-size:2.2rem">{_yen(totals["cost"])}</div>',
            unsafe_allow_html=True)
_pc = "#0f87b8" if totals["profit"] >= 0 else "#c0392b"
s3.markdown(f'<div style="color:#67788a;font-weight:700;font-size:.9rem">利益</div>'
            f'<div style="color:{_pc};font-weight:800;font-size:2.2rem">{_yen(totals["profit"])}</div>',
            unsafe_allow_html=True)

st.divider()

# 原価と売上が1つの一覧に混ざっていると、どちらを見ているのか分からない。
# 区分→タブの対応は posting_logic に集約してある（区分が増えたときに
# 「どちらのタブにも出ない行」が静かに生まれるのを防ぐため）。
cost_rows, sales_rows = posting_logic.split_summary_rows(rows)


def _render_tab(tab_rows, *, key, title, filename):
    """1つのタブの中身。件数と小計を出してから一覧を描く。

    集計を見るだけの画面なので、削除は灰色のまま(delete_fn=None)。
    ここから消しても 01・02 の元データは消えない。
    """
    st.caption(f"{len(tab_rows)}件 ／ 小計 {_yen(sum(r['金額'] for r in tab_rows))}")
    # 日付で並べ替え（空は末尾）
    disp = sorted(tab_rows, key=lambda r: (r["日付"] == "", r["日付"]))
    disp = [{"日付": r["日付"], "区分": r["区分"], "項目": r["項目"],
             "案件": r["案件"], "金額": _yen(r["金額"])} for r in disp]
    edited, _ = selectable_list(disp, key=key, id_col=None)
    list_action_bar(edited, key=key, title=title, filename=filename, id_col=None,
                    delete_fn=None,
                    delete_note="この画面は集計を見るためのものです。"
                                "元のデータは『小口／買掛／売掛』『業務委託登録』から"
                                "削除してください。")


tab_cost, tab_sales = st.tabs(["原価", "売上"])
with tab_cost:
    _render_tab(cost_rows, key="summary_cost", title="原価明細", filename="原価明細")
with tab_sales:
    _render_tab(sales_rows, key="summary_sales", title="売上明細", filename="売上明細")
