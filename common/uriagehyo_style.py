"""会議用売上表(大阪支社が今使っている「KPS（大阪）売上表.xlsx」)と全く同じ
デザインで、月次の売上表を生成する(依頼②・2026-08-20)。

実物のフォント・罫線・列幅・見出しの結合セルをテンプレートからそのまま複写し、
数字と文字列だけをアプリの集計値に差し替える。「区分(ぱど/チラシ/仕分け)の無い
案件はA:B列を結合して案件名(区分)を1つだけ書く」実物のパターン
(買取専科・アドバリュー各週の行)を、生成する全行に使う。

2026-08-20 オーナー判断＝実ファイル(19シートの財務台帳)への直接書き込みは
せず、都度エクスポートしたものをコピー＆ペーストしてもらう運用にする。
"""
import io
from copy import copy
from pathlib import Path

import openpyxl

from common import excel_io
from common.uriagehyo import HEADERS

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "売上表テンプレート_大阪支社.xlsx"

TITLE_ROW = 1
HEADER_ROWS = (2, 3)
FIRST_DATA_ROW = 4
DATA_ROW_STYLE = 9   # 「ｱﾄﾞ・バリュー　8-1」行＝A:B結合1本の見本にする
LAST_COL = 17        # A〜Q列(見出しの実在範囲)
HEADER_MERGES = (
    "A2:A3", "B2:B3", "C2:D2", "E2:F2", "G2:H2",
    "I2:I3", "J2:J3", "K2:K3", "L2:L3", "M2:M3", "N2:N3", "Q2:Q3",
)
TITLE_MERGE_END_COL = 15  # 実物は A1:O1


class UriagehyoTemplate:
    """テンプレートを読んで、書式(フォント・罫線・列幅・行高・結合)を引けるようにする。"""

    def __init__(self, path=TEMPLATE_PATH):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"売上表テンプレートがありません: {self.path}")
        self._wb = openpyxl.load_workbook(self.path)
        self._ws = self._wb[self._wb.sheetnames[0]]

    @property
    def ws(self):
        return self._ws

    def copy_column_widths(self, ws):
        for key, dim in self._ws.column_dimensions.items():
            if dim.width:
                ws.column_dimensions[key].width = dim.width

    def row_height(self, row):
        dim = self._ws.row_dimensions.get(row)
        return dim.height if dim else None


def _copy_cell_style(src, dst):
    """openpyxl のセル書式を複写する。Font/Border/Alignment は共有すると
    片方の変更が他方に及ぶため、必ず copy() してから代入する。"""
    dst.font = copy(src.font)
    dst.border = copy(src.border)
    dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format
    if src.fill is not None and src.fill.fill_type == "solid":
        dst.fill = copy(src.fill)


def build_monthly_workbook(bulk_rows, year, month, *, tpl=None) -> bytes:
    """bulk_rows: uriagehyo.build_bulk_rows() の戻り値
    [(見出しラベル, build_row()の戻り値), ...]。
    実物と同じ列見出し・書式・列幅で1シートに書き出す。
    """
    tpl = tpl or UriagehyoTemplate()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{year}年{month}月度 売上"

    tpl.copy_column_widths(ws)

    # ---- タイトル行 ----
    title_src = tpl.ws.cell(TITLE_ROW, 1)
    t = ws.cell(TITLE_ROW, 1, f"㈱ケイピーエス　大阪支社　　{year}年 {month}月度 売上表")
    _copy_cell_style(title_src, t)
    ws.merge_cells(start_row=TITLE_ROW, start_column=1,
                   end_row=TITLE_ROW, end_column=TITLE_MERGE_END_COL)
    th = tpl.row_height(TITLE_ROW)
    if th:
        ws.row_dimensions[TITLE_ROW].height = th

    # ---- 見出し2行(結合セル込み) ----
    for r in HEADER_ROWS:
        for c in range(1, LAST_COL + 1):
            src = tpl.ws.cell(r, c)
            dst = ws.cell(r, c, src.value)
            _copy_cell_style(src, dst)
        hh = tpl.row_height(r)
        if hh:
            ws.row_dimensions[r].height = hh
    for rng in HEADER_MERGES:
        ws.merge_cells(rng)

    # ---- データ行 ----
    # 区分(ぱど/チラシ/仕分け)の無い案件はA:B列を結合して案件名を1つだけ書く、
    # という実物のパターン(買取専科・アドバリュー各週)を全行に使う。
    style_row = [tpl.ws.cell(DATA_ROW_STYLE, c) for c in range(1, LAST_COL + 1)]
    rh = tpl.row_height(DATA_ROW_STYLE)
    for i, (label, row) in enumerate(bulk_rows):
        r = FIRST_DATA_ROW + i
        for col, header in enumerate(HEADERS, start=1):
            if col in (1, 2):
                continue
            dst = ws.cell(r, col, row.get(header))
            _copy_cell_style(style_row[col - 1], dst)
        label_cell = ws.cell(r, 1, label)
        _copy_cell_style(style_row[0], label_cell)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        if rh:
            ws.row_dimensions[r].height = rh

    buf = io.BytesIO()
    wb.save(buf)
    return excel_io.freeze_xlsx_bytes(buf.getvalue())


def monthly_filename(year, month) -> str:
    return f"{year}年{month}月度_売上表.xlsx"
