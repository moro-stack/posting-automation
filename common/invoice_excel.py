"""業務完了報告書兼請求書テンプレートへの流し込み。様式・数式は保持し値だけ入れる。"""
import datetime
import io
import os

import openpyxl

from common import posting_logic
from common.excel_io import freeze_xlsx_bytes

_TEMPLATE = os.path.join("templates", "業務完了報告書兼請求書テンプレート.xlsx")
_FIRST_LINE_ROW = 13   # 明細開始行
_MAX_LINE_ROWS = 6     # 13〜18

# 出力を毎回同じバイト列にするための固定日時(詳細は excel_io.freeze_xlsx_bytes を参照)。
# バイト列が毎回変わるとStreamlitのダウンロードURLが毎回変わり、取得中の古いURLが
# 破棄されて404になる(＝「Excelがダウンロードされない」)ため、内容を安定させる。
_FIXED_DT = datetime.datetime(2020, 1, 1)


def _set(ws, coord, value):
    ws[coord] = value


def build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines) -> bytes:
    if len(lines) > _MAX_LINE_ROWS:
        raise ValueError(f"明細は最大{_MAX_LINE_ROWS}行までです（{len(lines)}行が指定されました）。案件ごとに集約してください。")

    wb = openpyxl.load_workbook(_TEMPLATE)
    ws = wb.active

    _set(ws, "F3", issue_date)
    # 発行者(配布員)名は宛名の下(B8 但し欄)に併記
    _set(ws, "B8", f"但し：{distributor_name} 配布業務分")
    _set(ws, "A7", f"ご請求金額　　　　{posting_logic.fmt_num(posting_logic.invoice_total(lines))}　円（税込）")
    _set(ws, "A10", f"配布業務期間　：　{period_from}　～　{period_to}")

    for i, ln in enumerate(lines[:_MAX_LINE_ROWS]):
        r = _FIRST_LINE_ROW + i
        _set(ws, f"B{r}", ln.get("project_name"))
        # 数量: 配布・挟み込みは部数を数えるので数値。交通費・手当・その他は『一式』と書く。
        _set(ws, f"D{r}", posting_logic._num(ln.get("report_qty"))
             if posting_logic.is_delivery(ln.get("remark"))
             else posting_logic.unit_for(ln.get("remark")))
        _set(ws, f"E{r}", posting_logic._num(ln.get("unit_price")))
        _set(ws, f"F{r}", posting_logic._num(ln.get("amount")))
        # 備考(G列)には種別(配布/挟み込み/交通費/手当/その他)を入れる
        _set(ws, f"G{r}", ln.get("remark"))

    # 配布部数(F20)= 配布/挟み込みの報告数合計。ラベルE20は「報告数」に寄せる
    _set(ws, "E20", "報告数")
    _set(ws, "F20", f"{posting_logic.fmt_num(posting_logic.delivered_copies(lines))}部")

    # 作成日時を固定(更新日時は openpyxl が save 内で「今」に上書きするため freeze 側で潰す)
    wb.properties.created = _FIXED_DT
    wb.properties.modified = _FIXED_DT

    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())
