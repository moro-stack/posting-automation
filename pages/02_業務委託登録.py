import io
import zipfile
from datetime import date as _date

import pandas as pd
import streamlit as st

from common import invoice_excel
from common import posting_logic
from common import posting_store as store
from common.ui import (apply_app_style, nice_table, period_picker,
                       flash, show_flash, selectable_list, list_action_bar)

apply_app_style()
st.title("業務委託登録")

dist_rows = {d["name"]: d for d in store.list_distributors(only_active=True)}
dists = {name: d["id"] for name, d in dist_rows.items()}
projs = {p["name"]: p["id"] for p in store.list_projects(only_active=True)}

# 🔴 依頼①(2026-08-19大橋様→2026-08-20詳細確認): アドバリューは週ごとに案件が来て
# 「8-1」「8-2」「8-3」のように区分して管理している。「その他」向けに元々あった
# 案件区分の自由入力欄(other_label)を、アドバリューでも使えるようにする。
_OTHER_LABEL_PROJECTS = ("その他", "アドバリュー")

if not dists:
    st.warning("先に『マスタ管理』の「業務委託」タブで配布員を登録してください。")
    st.stop()

tab_reg, tab_list = st.tabs(["✒️ 登録", "📋 登録済み一覧"])

# ============================================================ 登録タブ
with tab_reg:
    show_flash()
    dist_name = st.selectbox("配布員", list(dists.keys()),
                             help="配布員名を入力すると絞り込めます。新規は『マスタ管理』で登録してください。")
    c1, c2, c3 = st.columns(3)
    issue = c1.date_input("発行日", value=_date.today())
    pfrom = c2.date_input("配布業務期間(開始)")
    pto = c3.date_input("配布業務期間(終了)")

    _dist = dist_rows[dist_name]
    pay_type = _dist.get("pay_type") or "歩合"
    st.caption(f"支払形態: **{pay_type}**　"
               f"{'（数量は日数を入れてください）' if pay_type == '日当' else ''}"
               f"{'（数量は時間を入れてください）' if pay_type == '時給' else ''}"
               f"{'（数量は1固定・月額をそのまま請求します）' if pay_type == '月給' else ''}"
               f"{'（数量は部数を入れてください）' if pay_type == '歩合' else ''}")

    # 支払形態ごとの単価の既定値。歩合だけは号ごとに違うのでマスタに持たず 0 のまま。
    _rates = {r["work_name"]: int(r["amount"]) for r in store.list_daily_rates(_dist["id"])} \
        if pay_type == "日当" else {}
    _default_price = 0.0
    if pay_type == "時給":
        _default_price = float(_dist.get("hourly_rate") or 0)
    elif pay_type == "月給":
        _default_price = float(_dist.get("monthly_rate") or 0)

    _qty_label = {"日当": "数量(日)", "時給": "数量(時間)", "月給": "数量(1固定)"}.get(
        pay_type, "数量(枚)")
    _needs_copies = pay_type != "歩合"

    _base = {"案件": "", "種別": "配布", "単価": _default_price,
             "数量": 1.0 if pay_type == "月給" else 0.0, "その他の案件名": ""}
    _cols = ["案件", "種別", "単価", "数量", "その他の案件名"]
    _conf = {
        "案件": st.column_config.SelectboxColumn(options=list(projs.keys())),
        "種別": st.column_config.SelectboxColumn(
            options=["配布", "挟み込み", "交通費", "手当", "その他"]),
        "単価": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%g"),
        "数量": st.column_config.NumberColumn(_qty_label, min_value=0.0, step=0.5,
                                             format="%g"),
        "その他の案件名": st.column_config.TextColumn(
            help="案件が『その他』なら何の案件か、『アドバリュー』なら8-1等の区分"),
    }
    if pay_type == "日当":
        _base = {"案件": "", "種別": "配布", "業務": "", "単価": 0.0, "数量": 0.0,
                 "部数": 0, "その他の案件名": ""}
        _cols = ["案件", "種別", "業務", "単価", "数量", "部数", "その他の案件名"]
        _conf["業務"] = st.column_config.SelectboxColumn(
            options=list(_rates.keys()),
            help="マスタに登録した業務名。選ぶと単価に日当額が入ります。")
    if _needs_copies and "部数" not in _cols:
        _cols.insert(_cols.index("数量") + 1, "部数")
        _base["部数"] = 0
    if _needs_copies:
        _conf["部数"] = st.column_config.NumberColumn(
            "部数", min_value=0, step=1, format="localized",
            help="報告書の報告数に使います。報酬の計算には使いません。")

    st.markdown(f"**明細**（案件・種別・単価・{_qty_label}）｜数量と単価は小数点も入力できます")
    st.caption("案件を「その他」「アドバリュー」にした行は、右の『その他の案件名』に"
               "何の案件か・8-1等の区分を入力してください（号別明細で確認できます）。")
    editor = st.data_editor(
        pd.DataFrame([_base]), num_rows="dynamic", column_config=_conf,
        column_order=_cols, use_container_width=True, key=f"line_editor_{pay_type}")

    lines = []
    for _, row in editor.iterrows():
        if not row["案件"] or pd.isna(row["案件"]):
            continue
        qty = posting_logic._num(row["数量"]) if pd.notna(row["数量"]) else 0
        price = posting_logic._num(row["単価"]) if pd.notna(row["単価"]) else 0
        # 日当: 業務を選んで単価が空(0)なら、マスタの日当額を入れる。
        # 単価が手で入っていればそちらを優先する(その回だけ違う金額にできる)。
        if pay_type == "日当" and not price:
            work = row.get("業務") if "業務" in row else None
            if pd.notna(work):
                price = _rates.get(str(work), 0)
        remark = row["種別"] if pd.notna(row["種別"]) else "配布"
        olabel = row.get("その他の案件名") if "その他の案件名" in row else None
        olabel = (str(olabel).strip() or None) if (
            pd.notna(olabel) and row["案件"] in _OTHER_LABEL_PROJECTS) else None
        copies = None
        if _needs_copies and "部数" in row and pd.notna(row["部数"]):
            copies = int(row["部数"] or 0)
        lines.append({"project_id": projs.get(row["案件"]), "project_name": row["案件"],
                      "report_qty": qty, "unit_price": price, "amount": qty * price,
                      "remark": remark, "other_label": olabel, "copies": copies})

    if lines:
        st.markdown("**明細（確認）**")
        preview = [{
            "案件": l["project_name"],
            "種別": l["remark"],
            "数量": posting_logic.qty_label(l["report_qty"], l["remark"], pay_type),
            "単価": f'¥{posting_logic.fmt_num(l["unit_price"])}',
            "合計": f'¥{posting_logic.fmt_num(l["amount"])}',
        } for l in lines]
        nice_table(preview)

        m1, m2 = st.columns(2)
        m1.metric("ご請求金額(税込)", f"¥{posting_logic.fmt_num(posting_logic.invoice_total(lines))}")
        m2.metric("配布部数(配布+挟み込み)",
                  f"{posting_logic.fmt_num(posting_logic.delivered_copies(lines, pay_type))} 部")

    col_save, col_dl = st.columns(2)
    if col_save.button("この請求を登録", type="primary", disabled=not lines):
        store.add_contract_invoice(
            dists[dist_name], str(issue), str(pfrom), str(pto),
            [{"project_id": l["project_id"], "report_qty": l["report_qty"],
              "unit_price": l["unit_price"], "remark": l["remark"],
              "other_label": l.get("other_label"), "copies": l.get("copies")}
             for l in lines],
            pay_type=pay_type)
        # 明細エディタを空に戻して次の登録をしやすく（登録しましたは再実行後に表示）
        st.session_state.pop(f"line_editor_{pay_type}", None)
        flash("登録しました")
        st.rerun()

    if lines:
        if len(lines) > 6:
            st.warning("明細は6行までです。案件ごとに集約してください。")
        else:
            xlsx = invoice_excel.build_invoice_xlsx(
                distributor_name=dist_name,
                issue_date=str(issue), period_from=str(pfrom), period_to=str(pto), lines=lines,
                pay_type=pay_type)
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
             "amount": l.get("amount"), "remark": l.get("remark"),
             "copies": l.get("copies")}
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
    show_flash("invoice_list")
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
        _lines = detail_by_id[inv["id"]]["lines"]
        total = posting_logic.invoice_total(_lines)
        # 数量の単位は「登録時に焼き付けた支払形態」で決める。
        # マスタの現在値を使うと、配布員が日当→歩合に変わった瞬間に過去の「3 日」が
        # 「3 枚」に化けてしまう。
        disp_rows.append({
            # 「選択」列は selectable_list が付けるので、ここでは持たせない
            "No.": inv["id"],
            "配布員": id2name.get(inv["distributor_id"], "?"),
            "発行日": inv.get("issue_date") or "",
            "配布業務期間": f'{inv.get("period_from")}〜{inv.get("period_to")}',
            "数量": "／".join(posting_logic.qty_label(l.get("report_qty"), l.get("remark"),
                                                    inv.get("pay_type")) for l in _lines),
            "請求額": f"¥{posting_logic.fmt_num(total)}",
            "出力状況": _export_status(inv, today),
        })

    st.caption("チェックを付けた請求を、下のボタンでまとめて出力できます。")
    edited, selected_ids = selectable_list(disp_rows, key="contract")

    def _zip_button(container, rows, ids):
        """報告書をまとめてZIPで出す(このページ固有)。

        ⚠️ 押した時だけ作る。以前は毎回の再描画で選択分の報告書を全部作り直していたため、
        選択が多いほど画面操作のたびに重くなっていた。
        """
        zip_buf, skipped = io.BytesIO(), []
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for iid in ids:
                detail = detail_by_id.get(iid) or store.get_contract_invoice(iid)
                head = detail["invoice"]
                out_lines = _invoice_out_lines(detail, id2proj)
                if len(out_lines) > 6:
                    skipped.append(iid)
                    continue
                name = id2name.get(head["distributor_id"], "")
                zf.writestr(
                    f'業務完了報告書兼請求書_{name}_{head["issue_date"]}.xlsx',
                    invoice_excel.build_invoice_xlsx(
                        distributor_name=name, issue_date=head["issue_date"],
                        period_from=head["period_from"], period_to=head["period_to"],
                        lines=out_lines,
                        # マスタの現在値ではなく請求に焼き付けた支払形態を使う。現在値を使うと
                        # 支払形態を変えた瞬間に過去の報告書の単位が化ける。
                        pay_type=head.get("pay_type")))
        exported = [i for i in ids if i not in skipped]
        if skipped:
            st.warning("次の請求は明細が6行を超えるためスキップしました（案件ごとに集約してください）："
                       + "、".join(f"No.{i}" for i in skipped))
        if container.download_button(
                f"報告書ZIP（{len(exported)}件）", data=zip_buf.getvalue(),
                file_name=f"業務完了報告書_選択{len(exported)}件.zip",
                mime="application/zip", icon=":material/folder_zip:",
                disabled=not exported, key="dl_zip", use_container_width=True):
            for iid in exported:
                store.mark_contract_invoice_exported(iid)
            st.rerun()

    list_action_bar(edited, key="contract", title="業務委託 請求一覧",
                    filename=f"業務委託_選択一覧_{len(selected_ids)}件",
                    section="invoice_list",
                    delete_fn=store.delete_contract_invoice, extra=_zip_button)

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
