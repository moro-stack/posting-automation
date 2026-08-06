"""業務完了報告書兼請求書テンプレートへの流し込み。様式・数式は保持し値だけ入れる。"""
import datetime
import io
import os

import openpyxl
from openpyxl.worksheet.properties import PageSetupProperties

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


def build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines,
                       pay_type=None) -> bytes:
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
        # 数量: 数を数える種別は数値。数えないもの(交通費・手当・その他、月給の行)は『一式』と書く。
        unit = posting_logic.unit_for(ln.get("remark"), pay_type)
        _set(ws, f"D{r}", "一式" if unit == "一式"
             else posting_logic._num(ln.get("report_qty")))
        _set(ws, f"E{r}", posting_logic._num(ln.get("unit_price")))
        _set(ws, f"F{r}", posting_logic._num(ln.get("amount")))
        # 備考(G列)には種別(配布/挟み込み/交通費/手当/その他)を入れる。歩合以外は数量セルの
        # 数字が部数でない(日数・時間)ため、何の数なのかが分かるよう単位を併記する。
        # 例: 配布（3 日）
        remark = ln.get("remark")
        if unit not in ("一式", "枚"):
            remark = f"{remark}（{posting_logic.qty_label(ln.get('report_qty'), remark, pay_type)}）"
        _set(ws, f"G{r}", remark)

    # 配布部数(F20)= 配布/挟み込みの報告数合計。ラベルE20は「報告数」に寄せる
    _set(ws, "E20", "報告数")
    _set(ws, "F20", f"{posting_logic.fmt_num(posting_logic.delivered_copies(lines, pay_type))}部")

    # 🔴 テンプレートの印刷範囲は A1:F27 で、備考(G列)が範囲の外にあった。
    # そのままA4印刷すると備考だけ紙に載らない(幅不足ではない。A〜G合計 約99.6文字幅で
    # A4縦の使用可能幅に収まる)。ここで毎回設定し直すことで、テンプレートを
    # 差し替えても効くようにする。
    # fitToWidth=1 にすると横は必ず1ページに収まる(このとき page_setup.scale は無視される)。
    ws.print_area = "A1:G27"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0     # 縦は成り行き(明細が増えても縮めすぎない)

    # 作成日時を固定(更新日時は openpyxl が save 内で「今」に上書きするため freeze 側で潰す)
    wb.properties.created = _FIXED_DT
    wb.properties.modified = _FIXED_DT

    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())
