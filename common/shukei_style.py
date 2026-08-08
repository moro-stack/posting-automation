"""集計表の書式を、実物のテンプレートから読み取って複写する。

設計: docs/superpowers/specs/2026-08-07-shukei-design-fidelity-design.md

実物(`templates/集計表テンプレート_京阪.xlsx`)を全セル走査したところ、
游ゴシック7サイズ・罫線5種(dotted/double/hair/medium/thin)で**146通り**の
組み合わせが使われていた。人が手で作った帳票なので、これをルールとして
コードに書き起こすのは無理がある。

そこで「どの役割の行か」を決めて、テンプレートの対応する行から
**フォント・罫線・揃え・表示形式をそのまま複写**する。
書式はコードではなくテンプレート側にあるので、デザインが変わったら
テンプレートを差し替えるだけで追随する。

行数は号によって 5〜32行 と変わる(実データで確認済み)ため、
テンプレートの行を「役割ごとの見本」として使い回す。
"""
from copy import copy
from pathlib import Path

import openpyxl

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "集計表テンプレート_京阪.xlsx"

# テンプレートのどの行を、どの役割の見本にするか。
# 参照シートの構造: 1=表題 / 3=見出し / 4..25=上部マトリクス / 27..39=下部集計
# 上部は A4:A5, A7:A10, A12:A14, A16:A19, A21:A25 がエリアの縦結合で、
# 6,11,15,20 がエリア区切りの空行。
ROLE_ROWS = {
    "title": 1,          # 版名・号・配布期間
    "header": 3,         # エリア/リーダー/チラシ種類/コース数/配布部数/地区数
    "area_first": 4,     # エリアの先頭のリーダー行
    "area_middle": 8,    # エリアの途中のリーダー行
    "area_last": 10,     # エリアの末尾のリーダー行
    "separator": 6,      # エリアとエリアのあいだの空行
}

# 下部集計はテンプレートの 27〜39 行を相対位置でそのまま使う
BOTTOM_FIRST_ROW = 27
BOTTOM_LAST_ROW = 39


class ShukeiTemplate:
    """テンプレートを読んで、役割と列から書式を引けるようにする。"""

    def __init__(self, path=TEMPLATE_PATH):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"集計表テンプレートがありません: {self.path}")
        self._wb = openpyxl.load_workbook(self.path)
        self._ws = self._wb["集計表"]

    @property
    def ws(self):
        return self._ws

    def style_of(self, row, col):
        """テンプレートの (row, col) の書式を返す。"""
        return self._ws.cell(row, col)

    def apply(self, cell, role, col):
        """役割と列に対応するテンプレートの書式を cell へ複写する。

        値は変えない。フォント・罫線・揃え・表示形式だけを写す。
        """
        src_row = ROLE_ROWS[role] if isinstance(role, str) else int(role)
        src = self._ws.cell(src_row, col)
        copy_style(src, cell)
        return cell

    def apply_bottom(self, cell, rel_row, col):
        """下部集計の相対位置(0始まり)に対応する書式を複写する。"""
        src_row = min(BOTTOM_FIRST_ROW + rel_row, BOTTOM_LAST_ROW)
        copy_style(self._ws.cell(src_row, col), cell)
        return cell

    def copy_column_widths(self, ws):
        """列幅をテンプレートからそのまま写す。"""
        for key, dim in self._ws.column_dimensions.items():
            if dim.width:
                ws.column_dimensions[key].width = dim.width

    def row_height(self, role):
        """役割に対応する行高を返す(無ければ None)。"""
        src_row = ROLE_ROWS[role] if isinstance(role, str) else int(role)
        dim = self._ws.row_dimensions.get(src_row)
        return dim.height if dim else None


def copy_style(src, dst):
    """openpyxl のセル書式を複写する。

    ⚠️ Font/Border/Alignment はセル間で共有すると片方の変更が他方に及ぶため、
    必ず copy() してから代入する。
    """
    dst.font = copy(src.font)
    dst.border = copy(src.border)
    dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format
    if src.fill is not None and src.fill.fill_type == "solid":
        dst.fill = copy(src.fill)
    return dst


def leader_role(index, count):
    """エリア内での位置から役割名を決める。

    1人だけのエリアは area_first(＝上が二重線・下が閉じている見本)を使う。
    """
    if count <= 1 or index == 0:
        return "area_first"
    if index == count - 1:
        return "area_last"
    return "area_middle"
