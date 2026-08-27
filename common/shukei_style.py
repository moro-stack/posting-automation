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
import math
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

    def apply_name(self, cell, role, col):
        """リーダー名セルに書式を当てる。罫線・揃えは役割どおり複写するが、
        フォント(サイズ・太字)だけは area_first の見本で統一する。

        🔴 2026-08-19 大橋様ご指摘: 実物テンプレートは名前欄のフォントが
        area_first(16pt太字)と area_middle/area_last(11pt細字)でバラバラ
        (人が手で作った帳票で、たまたま名前が書かれていた行とそうでない行の
        違いがそのまま残っている)。統一しないと、エリア内で1人目のリーダー
        だけ大きく、2人目以降が小さく見えてしまう。

        🔴 2026-08-27 大橋様ご指摘: フォントを統一したら、今度は
        「フィールドサービス」「クローバージャパン」のような長い外注先名が
        B列(幅10.7≒全角5文字)からはみ出して読めなくなった。テンプレートは
        area_first にだけ折り返しが付いていて middle/last には付いていないため、
        複写しただけでは2人目以降が切れる。名前欄は役割によらず必ず折り返す。
        罫線・揃え・フォントはそのまま(折り返しだけを足す)。
        """
        self.apply(cell, role, col)
        cell.font = copy(self._ws.cell(ROLE_ROWS["area_first"], col).font)
        alignment = copy(cell.alignment)
        alignment.wrap_text = True
        cell.alignment = alignment
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


# 名前欄(B列)の折り返し計算。
# Excel の列幅は「標準フォントの半角0の幅」が1。日本語は全角なので1文字＝幅2で数える。
_CHAR_WIDTH = 2
# 1行あたりの高さ(pt)は フォントサイズ×この係数。Excelの既定の行送りにほぼ一致する。
_LINE_HEIGHT_RATIO = 1.35


def name_line_count(name, col_width) -> int:
    """その名前が col_width の列で何行に折り返されるか(最低1行)。"""
    text = "" if name is None else str(name)
    per_line = max(1, int(float(col_width or 0) // _CHAR_WIDTH))
    lines = 0
    for part in text.split("\n"):
        lines += max(1, math.ceil(len(part) / per_line))
    return max(1, lines)


def wrapped_name_height(name, *, col_width, font_size, base_height=None) -> float:
    """折り返した名前が全部見える行高(pt)を返す。

    テンプレートの行高(base_height)で足りるならそのまま返す＝短い名前のときは
    見た目を一切変えない。足りないときだけ必要な高さまで伸ばす。

    縦結合している下の行の高さは足し込まない(既定の行高がいくつになるかは
    Excelの設定・フォントで変わるため)。先頭行だけで確実に収まる高さを返す。
    """
    lines = name_line_count(name, col_width)
    need = lines * float(font_size or 11) * _LINE_HEIGHT_RATIO
    return max(float(base_height or 0), need)


def leader_role(index, count):
    """エリア内での位置から役割名を決める。

    1人だけのエリアは area_first(＝上が二重線・下が閉じている見本)を使う。
    """
    if count <= 1 or index == 0:
        return "area_first"
    if index == count - 1:
        return "area_last"
    return "area_middle"
