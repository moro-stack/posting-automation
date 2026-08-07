"""集計表の書式がテンプレート（実物）と一致することを機械で確かめる。

設計: docs/superpowers/specs/2026-08-07-shukei-design-fidelity-design.md
目視で「合っている」と言わないための土台。
"""
import io

import openpyxl
import pytest

from common import atehagi as A
from common import shukei_style as S


@pytest.fixture(scope="module")
def tpl():
    return S.ShukeiTemplate()


# ===== テンプレートそのものの前提を固定する =====


def test_template_exists_and_has_shukei_sheet(tpl):
    assert tpl.ws.title == "集計表"
    assert tpl.ws.max_row >= 39


def test_template_font_is_yu_gothic_everywhere(tpl):
    """🔴 実物は游ゴシックのみ。ここが崩れると全体の見た目が変わる。"""
    names = {c.font.name for row in tpl.ws.iter_rows() for c in row
             if c.value is not None}
    assert names == {"游ゴシック"}


def test_template_uses_five_border_styles(tpl):
    """実物は dotted/double/hair/medium/thin の5種を使い分けている。"""
    styles = set()
    for row in tpl.ws.iter_rows():
        for c in row:
            for side in ("left", "right", "top", "bottom"):
                st = getattr(c.border, side).style
                if st:
                    styles.add(st)
    assert styles == {"dotted", "double", "hair", "medium", "thin"}


def test_template_has_column_widths(tpl):
    widths = {k: d.width for k, d in tpl.ws.column_dimensions.items() if d.width}
    assert widths["A"] == pytest.approx(6.2, abs=0.05)
    assert widths["B"] == pytest.approx(10.7, abs=0.05)
    assert widths["AG"] == pytest.approx(10.6, abs=0.05)


# ===== 複写のふるまい =====


def test_copy_style_copies_font_border_and_format(tpl):
    wb = openpyxl.Workbook()
    ws = wb.active
    cell = ws.cell(1, 1, 123)
    src = tpl.ws.cell(4, 6)          # 上部マトリクスの部数セル
    S.copy_style(src, cell)
    assert cell.font.name == src.font.name
    assert cell.font.sz == src.font.sz
    assert cell.font.b == src.font.b
    assert cell.border.top.style == src.border.top.style
    assert cell.border.bottom.style == src.border.bottom.style
    assert cell.number_format == src.number_format


def test_copy_style_does_not_share_objects(tpl):
    """🔴 Font/Border を共有すると、片方を変えたとき他方も変わる。

    openpyxl は代入で参照を共有してしまうので copy() が要る。
    ここが壊れると「1セル直したら別のセルまで変わる」事故になる。
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    a = ws.cell(1, 1, 1)
    b = ws.cell(2, 1, 2)
    src = tpl.ws.cell(4, 3)
    S.copy_style(src, a)
    S.copy_style(src, b)
    assert a.font is not b.font
    assert a.border is not b.border


def test_apply_uses_the_role_row(tpl):
    wb = openpyxl.Workbook()
    ws = wb.active
    cell = ws.cell(5, 1)
    tpl.apply(cell, "header", 1)
    src = tpl.ws.cell(S.ROLE_ROWS["header"], 1)
    assert cell.font.sz == src.font.sz
    assert cell.border.top.style == src.border.top.style


def test_copy_column_widths(tpl):
    wb = openpyxl.Workbook()
    ws = wb.active
    tpl.copy_column_widths(ws)
    assert ws.column_dimensions["A"].width == pytest.approx(6.2, abs=0.05)
    assert ws.column_dimensions["B"].width == pytest.approx(10.7, abs=0.05)


@pytest.mark.parametrize("index,count,expected", [
    (0, 1, "area_first"),
    (0, 3, "area_first"),
    (1, 3, "area_middle"),
    (2, 3, "area_last"),
])
def test_leader_role(index, count, expected):
    assert S.leader_role(index, count) == expected


# ===== 生成物がテンプレートの書式を持っていること =====


def _build_from_real_like_data():
    """小さな作りデータで集計表を生成する。"""
    table = [
        ["配送管理表", "2026/08/21", "(1213号)"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
    ]
    # 🔴 部数は必ず4桁以上にする。3桁だと「1000以上のセル」が0件になり、
    # 桁区切りのテストが空集合を検査するだけの無意味なものになる(2026-08-07に踏んだ)。
    for chiku, name, code, butsu, bu in [
        ("911001", "ケイピーエス", None, "91 ぱど", 4380),
        ("911001", "ケイピーエス", 3, "丸源ラーメン", 4380),
        ("911003", "ケイピーエス", None, "91 ぱど", 3080),
        ("921001", "フィールドサービス", None, "92 ぱど", 2000),
    ]:
        table.append(["2026/08/21", "1213", 0, "", "", name, "", None, chiku,
                      code, butsu, bu, "", "", "", "", ""])
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    version = A.detect_version(groups)
    data = A.shukei_data(groups, version)
    raw = A.build_shukei_daishi_workbook(data, version, "1213", "2026/08/21")
    return openpyxl.load_workbook(io.BytesIO(raw))


def test_generated_sheet_uses_yu_gothic(tpl):
    """🔴 生成物のフォントが游ゴシックであること(既定のCalibriのままにしない)。"""
    ws = _build_from_real_like_data()["集計表"]
    names = {c.font.name for row in ws.iter_rows() for c in row
             if c.value is not None}
    assert names == {"游ゴシック"}, f"游ゴシック以外が混ざっている: {names}"


def test_generated_sheet_has_template_column_widths(tpl):
    """🔴 列幅が実物どおりであること(指定なしだと全列同じ幅になる)。"""
    ws = _build_from_real_like_data()["集計表"]
    assert ws.column_dimensions["A"].width == pytest.approx(6.2, abs=0.05)
    assert ws.column_dimensions["B"].width == pytest.approx(10.7, abs=0.05)
    assert ws.column_dimensions["AG"].width == pytest.approx(10.6, abs=0.05)


def test_generated_sheet_uses_more_than_one_border_style(tpl):
    """🔴 罫線が1種類(thin)だけになっていないこと。

    以前は全セル4辺 thin で、実物(5種を使い分け)と別物になっていた。
    """
    ws = _build_from_real_like_data()["集計表"]
    styles = set()
    for row in ws.iter_rows():
        for c in row:
            for side in ("left", "right", "top", "bottom"):
                st = getattr(c.border, side).style
                if st:
                    styles.add(st)
    assert len(styles) >= 3, f"罫線が {styles} しか使われていない"
    assert "medium" in styles


def test_generated_numbers_have_thousands_separator(tpl):
    """🔴 部数に桁区切りが付くこと(実物は #,##0 形式)。"""
    ws = _build_from_real_like_data()["集計表"]
    fmts = {c.number_format for row in ws.iter_rows() for c in row
            if isinstance(c.value, int) and c.value >= 1000}
    assert any("#,##0" in f for f in fmts), f"桁区切りが無い: {fmts}"
