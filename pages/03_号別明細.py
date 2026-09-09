import re
from datetime import date as _date, datetime as _datetime
import io

import pandas as pd
import streamlit as st

from common import advalue
from common import posting_logic
from common import posting_store as store
from common.excel_io import freeze_xlsx_bytes
from common.ui import (apply_app_style, nice_table, period_picker, flash, show_flash,
                       selectable_list, list_action_bar, PERIOD_ORDER_MONTH_FIRST)

apply_app_style()
show_flash()

_WD = ["月", "火", "水", "木", "金", "土", "日"]


def _yen(v):
    return f"¥{posting_logic.fmt_num(v)}"


def _weekday(ds):
    try:
        return _WD[_datetime.strptime(str(ds)[:10], "%Y-%m-%d").weekday()]
    except (ValueError, TypeError):
        return ""


def _parse_int(s):
    """手打ち金額(カンマ・円記号など混じってもOK)を整数に。空なら0。"""
    digits = re.sub(r"[^\d]", "", str(s or ""))
    return int(digits) if digits else 0


# 停止中も含めて引く。号別明細は「登録の選択肢」ではなく「過去データの表示」なので、
# 案件を停止中にしても号は出し続ける(配布員の名前引きと同じ扱い)。
projs = store.list_projects()
if not projs:
    st.warning("案件マスタが空です。『マスタ管理』で登録してください。")
    st.stop()

# ===== 号(案件)選択 → 案件名を大きく表示 =====
name2id = {p["name"]: p["id"] for p in projs}
names = list(name2id.keys())
sel = st.pills("案件(号)", names, selection_mode="single",
               default=names[0], label_visibility="collapsed", key="proj_pills")
if not sel:
    sel = names[0]
pid = name2id[sel]
st.markdown(
    f'<div style="font-size:1.9rem;font-weight:800;color:#0f87b8;margin:.1rem 0 .5rem">{sel}</div>',
    unsafe_allow_html=True)

# ===== アドバリューだけ、週(1週目〜5週目)でさらに絞れるようにする =====
# 🔴 依頼①(2026-08-19大橋様→2026-08-20詳細確認): アドバリューは週ごとに案件が来て
# 区分して管理している。号別明細でも週ごとに集計を見られるようにする。
# 🔴 2026-09-04 大橋様ご依頼: 選択肢は月に依存する生の区分("8-1"等)ではなく
# 「1週目〜5週目」の固定表示に統一する(月をまたいでも選択肢を作り直さない)。
selected_week = None
if sel == "アドバリュー":
    _week_sel = st.pills("週", ["全体"] + list(advalue.WEEK_CHOICES), selection_mode="single",
                         default="全体", key="adv_sub_pills")
    selected_week = advalue.week_index(_week_sel) if _week_sel and _week_sel != "全体" else None
    if selected_week is not None:
        st.caption(f"表示中の週：{_week_sel}（月を問わずこの週のデータをまとめて表示）")

# ===== 期間指定：全期間 / 今月 / 今週 / 期間指定 を同じ並びのボタンで =====
# 🔴 2026-09-04 大橋様ご依頼: アドバリューは週(1週目〜5週目)で絞るのが基本なので、
# 全期間/今月/今週のボタンは無くし「期間指定」だけにする(週選択と役割が重なるため)。
# キーを分けて、他の案件から切り替えても選択状態が衝突しないようにする。
if sel == "アドバリュー":
    lo, hi, period_note = period_picker(key="issue_period_adv", only=["期間指定"])
else:
    # 並び順は大阪支社売上ページに合わせて今月/今週/全期間/期間指定
    # (2026-09-09大橋様ご依頼)。
    lo, hi, period_note = period_picker(key="issue_period", order=PERIOD_ORDER_MONTH_FIRST)
st.caption(f"表示期間: {period_note}")

# ===== コストを集める =====
petty = posting_logic.filter_rows_by_period(
    store.list_petty_cash(project_id=pid), "date", lo, hi)
petty = posting_logic.filter_rows_by_week(petty, selected_week)
receivables = posting_logic.filter_rows_by_period(
    store.list_receivables(project_id=pid), "month", lo, hi)
receivables = posting_logic.filter_rows_by_week(receivables, selected_week)

_dist_names = {d["id"]: d["name"] for d in store.list_distributors()}  # 停止中も含めて引く

contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    for ln in detail["lines"]:
        ln = dict(ln)
        ln["issue_date"] = inv.get("issue_date")   # その他の案件内訳で発行日を出すため
        ln["distributor_name"] = _dist_names.get(inv.get("distributor_id"), "")
        ln["pay_type"] = inv.get("pay_type")       # 登録時点の支払形態(マスタの現在値は使わない)
        contract_lines.append(ln)
contract_lines = posting_logic.filter_rows_by_week(contract_lines, selected_week)

# 直接入力(配布員代): work_date で期間絞り込み。日付なしは常に計上。
all_manual = store.list_issue_manual_costs(project_id=pid)
manual = [r for r in all_manual
          if r.get("work_date") is None or posting_logic.in_period(r.get("work_date"), lo, hi)]
manual = posting_logic.filter_rows_by_week(manual, selected_week)

agg = posting_logic.aggregate_issue(
    pid, petty=petty, payables=[], contract_lines=contract_lines, manual=manual)
groups = posting_logic.cost_groups(agg)
petty_total = sum(posting_logic._num(r.get("amount")) for r in petty)
receivable_total = sum(posting_logic._num(r.get("amount")) for r in receivables)
profit = receivable_total - groups["genka"]

# ===== 上部サマリー：配布原価 / 売上 / 利益 の3項目（配布原価を大きく） =====
s1, s2, s3 = st.columns([1.5, 1, 1])
with s1:
    st.markdown(
        f'''<div class="metric-lines" style="line-height:1.12">
  <div style="color:#67788a;font-weight:700;font-size:.9rem">配布原価（税込）</div>
  <div style="color:#1f2d3a;font-weight:800;font-size:2.6rem;letter-spacing:-.01em">{_yen(groups["genka"])}</div>
  <div style="color:#67788a;font-size:.86rem;margin-top:.15rem">内訳：配布員代 <b style="color:#0f87b8">{_yen(groups["labor"])}</b> ／ 雑費 <b style="color:#0f87b8">{_yen(groups["misc"])}</b></div>
</div>''',
        unsafe_allow_html=True)
_profit_color = "#0f87b8" if profit >= 0 else "#c0392b"
with s2:
    st.markdown(
        f'''<div class="metric-lines" style="line-height:1.12">
  <div style="color:#67788a;font-weight:700;font-size:.9rem">売上</div>
  <div style="color:#1f2d3a;font-weight:800;font-size:1.9rem">{_yen(receivable_total)}</div>
</div>''',
        unsafe_allow_html=True)
with s3:
    st.markdown(
        f'''<div class="metric-lines" style="line-height:1.12">
  <div style="color:#67788a;font-weight:700;font-size:.9rem">利益</div>
  <div style="color:{_profit_color};font-weight:800;font-size:1.9rem">{_yen(profit)}</div>
</div>''',
        unsafe_allow_html=True)

st.divider()

# 案件=「その他」「アドバリュー」の号のときだけ、内訳表の左端に「案件名」
# (登録時に手入力した other_label)を出す。「その他」に何の案件で入れたか・
# アドバリューのどの区分(8-1等)かを、配布員代・雑費の内訳の中でそのまま確認できるようにする。
_show_label = sel in ("その他", "アドバリュー")


def _with_label(row, other_label):
    """内訳表示行の左端に『案件名』列を差し込む(その他号のときだけ)。"""
    if not _show_label:
        return row
    return {"案件名": other_label or "", **row}


# ===== 配布員代（詳細は折りたたみ） =====
issue_contract = [l for l in contract_lines if l.get("project_id") == pid]
_con_disp = [_with_label({"支払日": l.get("issue_date") or "",
                          "配布員": l.get("distributor_name") or "",
                          "種別": l.get("remark") or "",
                          "数量": posting_logic.qty_label(l.get("report_qty"), l.get("remark"),
                                                        l.get("pay_type")),
                          "単価": _yen(l.get("unit_price")), "合計": _yen(l.get("amount"))},
                         l.get("other_label"))
             for l in issue_contract]
_man_disp = [{"日付": r.get("work_date") or "（日付なし）",
              "曜日": _weekday(r.get("work_date")),
              "作業": r.get("content") or "",
              "金額": _yen(r.get("amount"))} for r in manual]

with st.expander(f":material/groups: 配布員代の内訳（業務委託＋直接入力）　—　小計 {_yen(groups['labor'])}",
                 expanded=False):
    st.markdown("**業務委託（配布員別・報告書/請求書ページで計算）**")
    nice_table(_con_disp, "この号の業務委託はありません。")

    st.markdown("**直接入力（日ごと・作業別）**")
    nice_table(_man_disp, "直接入力の配布員代はありません。")

    with st.form("add_labor", clear_on_submit=True):
        st.caption("配布員代を直接追加（日給の人・後からの追加もここで）"
                   + (f"　※現在選んでいる「{advalue.WEEK_CHOICES[selected_week - 1]}」"
                      "と、下で入力する日付の月を組み合わせた区分で登録されます"
                      if selected_week else ""))
        a1, a2, a3 = st.columns([1, 2, 1])
        w = a1.date_input("日付", value=_date.today(), format="YYYY/MM/DD")
        work = a2.text_input("作業", placeholder="例：配布 / 丁合・配布")
        amt_str = a3.text_input("金額", placeholder="例：50000")
        if st.form_submit_button("追加") and _parse_int(amt_str) > 0:
            _manual_label = advalue.week_label(w.month, selected_week) if selected_week else None
            store.add_issue_manual_cost(pid, work.strip() or "配布",
                                        _parse_int(amt_str), work_date=str(w),
                                        other_label=_manual_label)
            flash("配布員代を追加しました")
            st.rerun()

    if manual:
        st.caption("入力済みの直接入力を修正・削除")
        # 行idをラベルに含めて一意化（同一日付・作業・金額の行が複数あっても取り違えない）
        opt = {f'{(r.get("work_date") or "日付なし")}｜{r.get("content") or ""}｜{_yen(r.get("amount"))}｜No.{r.get("id")}': r
               for r in manual}
        pick = st.selectbox("対象の行", list(opt.keys()), key="edit_pick")
        target = opt[pick]
        with st.form("edit_labor"):
            e1, e2, e3 = st.columns([1, 2, 1])
            cur_date = (_datetime.strptime(target["work_date"][:10], "%Y-%m-%d").date()
                        if target.get("work_date") else _date.today())
            # key は行idごとに変える。固定keyだと session_state が保持され、対象行を
            # 切り替えても前の行の値が残り、更新時に別の行へ誤って書き込む(Streamlit仕様)。
            _rid = target["id"]
            ew = e1.date_input("日付", value=cur_date, key=f"edit_date_{_rid}",
                               format="YYYY/MM/DD")
            ework = e2.text_input("作業", value=target.get("content") or "",
                                  key=f"edit_work_{_rid}")
            eamt_str = e3.text_input("金額", value=str(target.get("amount") or ""),
                                     key=f"edit_amt_{_rid}")
            eamt = _parse_int(eamt_str)
            u1, u2, _ = st.columns([1, 1, 4])
            if u1.form_submit_button("更新") and eamt > 0:
                store.update_issue_manual_cost(target["id"], work_date=str(ew),
                                               content=ework.strip() or "配布", amount=eamt)
                flash("更新しました")
                st.rerun()
            if u2.form_submit_button("削除"):
                store.delete_issue_manual_cost(target["id"])
                flash("削除しました")
                st.rerun()

    _lab_edited, _ = selectable_list(_man_disp, key="issue_labor", id_col=None)
    list_action_bar(_lab_edited, key="issue_labor", title=f"配布員代 直接入力（{sel}）",
                    filename=f"配布員代直接入力_{sel}", id_col=None, delete_fn=None,
                    delete_note="この一覧の削除は上の編集フォームから行ってください。")

# ===== 雑費（詳細は折りたたみ） =====
_cats = {c["id"]: c["name"] for c in store.list_expense_categories()}
_misc = []
for r in petty:
    item = _cats.get(r.get("category_id"), "")
    if r.get("memo"):
        item = f'{item}（{r["memo"]}）' if item else r["memo"]
    _misc.append(_with_label(
        {"配布員": _dist_names.get(r.get("distributor_id"), ""),
         "項目": item or "小口", "金額": _yen(r.get("amount")),
         "支払方法": posting_logic.payment_method("petty", r),
         "日付": r.get("date") or ""}, r.get("other_label")))

with st.expander(f":material/receipt_long: 雑費の内訳（小口）　—　小計 {_yen(groups['misc'])}",
                 expanded=False):
    st.caption(f"雑費 ＝ 小口 {_yen(petty_total)}")
    _misc_edited, _ = selectable_list(_misc, key="issue_misc", id_col=None)
    list_action_bar(_misc_edited, key="issue_misc", title=f"雑費（{sel}）",
                    filename=f"雑費_{sel}", id_col=None, delete_fn=None,
                    delete_note="雑費の元データは『小口／買掛／売上』の小口から削除してください。")

# ===== 車両使用履歴（2026-09-04大橋様ご依頼・参考情報。金額集計には含めない） =====
_vehicle_rows = posting_logic.filter_rows_by_period(
    store.list_vehicle_logs(project_id=pid), "date", lo, hi)
_vehicle_rows = posting_logic.filter_rows_by_week(_vehicle_rows, selected_week)
if _vehicle_rows:
    with st.expander(f":material/directions_car: 車両使用履歴（{len(_vehicle_rows)}件）",
                     expanded=False):
        st.caption("この案件で使われた車両の記録です。金額の集計には含まれません。")
        _veh_disp = [{"日付": r.get("date") or "", "車両": r.get("vehicle") or "",
                      "ドライバー": r.get("driver") or "",
                      "走行距離": f'{r["distance"]}km' if r.get("distance") is not None else "",
                      "使用用途": r.get("purpose") or ""} for r in _vehicle_rows]
        nice_table(_veh_disp, "")

# ===== 号原価まとめ 出力 =====
_buf = io.BytesIO()
with pd.ExcelWriter(_buf, engine="openpyxl") as writer:
    (pd.DataFrame(_con_disp) if _con_disp
     else pd.DataFrame(columns=["支払日", "配布員", "種別", "数量", "単価", "合計"])).to_excel(
        writer, index=False, sheet_name="業務委託")
    (pd.DataFrame(_man_disp) if _man_disp
     else pd.DataFrame(columns=["日付", "曜日", "作業", "金額"])).to_excel(
        writer, index=False, sheet_name="直接入力")
    (pd.DataFrame(_misc) if _misc
     else pd.DataFrame(columns=["配布員", "項目", "金額", "支払方法", "日付"])).to_excel(
        writer, index=False, sheet_name="雑費")
    pd.DataFrame([{"項目": "配布員代", "金額": groups["labor"]},
                  {"項目": "雑費", "金額": groups["misc"]},
                  {"項目": "配布原価(税込)", "金額": groups["genka"]}]).to_excel(
        writer, index=False, sheet_name="合計")
st.download_button("号原価まとめをExcelで保存", data=freeze_xlsx_bytes(_buf.getvalue()),
                   file_name=f"号原価まとめ_{sel}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   icon=":material/download:", key="dl_genka")
