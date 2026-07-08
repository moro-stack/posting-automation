"""業務完了報告書兼請求書テンプレートへの流し込み。様式・数式は保持し値だけ入れる。"""
import io
import os

import openpyxl

from common import posting_logic

_TEMPLATE = os.path.join("templates", "業務完了報告書兼請求書テンプレート.xlsx")
_FIRST_LINE_ROW = 13   # 明細開始行
_MAX_LINE_ROWS = 6     # 13〜18


def _set(ws, coord, value):
    ws[coord] = value


def build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines) -> bytes:
    wb = openpyxl.load_workbook(_TEMPLATE)
    ws = wb.active

    _set(ws, "F3", issue_date)
    # 発行者(配布員)名は宛名の下(B8 但し欄)に併記
    _set(ws, "B8", f"但し：{distributor_name} 配布業務分")
    _set(ws, "A7", f"ご請求金額　　　　{posting_logic.invoice_total(lines)}　円（税込）")
    _set(ws, "A10", f"配布業務期間　：　{period_from}　～　{period_to}")

    for i, ln in enumerate(lines[:_MAX_LINE_ROWS]):
        r = _FIRST_LINE_ROW + i
        _set(ws, f"B{r}", ln.get("project_name"))
        _set(ws, f"D{r}", int(ln.get("report_qty") or 0))
        _set(ws, f"E{r}", int(ln.get("unit_price") or 0))
        _set(ws, f"F{r}", int(ln.get("amount") or 0))

    # 配布部数(F20)= 配布/挟み込みの報告数合計。ラベルE20は「報告数」に寄せる
    _set(ws, "E20", "報告数")
    _set(ws, "F20", posting_logic.delivered_copies(lines))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
