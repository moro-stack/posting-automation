"""会議用売上表の書式が実物テンプレートと一致することを機械で確かめる。

依頼②(2026-08-20)。目視で「合っている」と言わないための土台
(集計表のtest_shukei_style.pyと同じ考え方)。
"""
import io

import openpyxl
import pytest

from common import uriagehyo as U
from common import uriagehyo_style as S


@pytest.fixture(scope="module")
def tpl():
    return S.UriagehyoTemplate()


def test_template_exists_and_has_a_month_sheet(tpl):
    assert tpl.ws.max_row >= 4


def test_template_has_column_widths(tpl):
    widths = {k: d.width for k, d in tpl.ws.column_dimensions.items() if d.width}
    assert "A" in widths and "L" in widths


def _build(rows=None):
    bulk = rows if rows is not None else [
        ("京阪南", U.build_row(hakko_gou=None, ban_mei=None,
                             uriage_zeikomi=847502, genka_goukei_zeikomi=324505)),
        ("アドバリュー　8-1", U.build_row(hakko_gou=None, ban_mei=None,
                                       uriage_zeikomi=544970, genka_goukei_zeikomi=177540,
                                       koutsuhi=6260)),
    ]
    data = S.build_monthly_workbook(bulk, 2026, 8)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    return wb, wb.active


def test_sheet_title_matches_month():
    wb, ws = _build()
    assert ws.title == "2026年8月度 売上"


def test_title_row_text_and_merge():
    wb, ws = _build()
    assert ws["A1"].value == "㈱ケイピーエス　大阪支社　　2026年 8月度 売上表"
    assert any(str(r) == "A1:O1" for r in ws.merged_cells.ranges)


def test_header_row_text_matches_real_sheet(tpl):
    wb, ws = _build()
    assert ws["A2"].value == "発行号"
    assert ws["B2"].value == "版名"
    assert ws["I2"].value == "その他"
    assert ws["O2"].value == "配布原価"
    assert ws["O3"].value == "（税込）"
    assert ws["C3"].value == "部数"
    assert ws["D3"].value == "売上（税抜）"


def test_header_merges_match_real_sheet():
    wb, ws = _build()
    ranges = {str(r) for r in ws.merged_cells.ranges}
    for rng in S.HEADER_MERGES:
        assert rng in ranges, f"{rng} が結合されていない"
    # O2:O3 / P2:P3 は実物どおり結合しない(2行それぞれ別テキスト)
    assert "O2:O3" not in ranges
    assert "P2:P3" not in ranges


def test_data_rows_are_merged_a_to_b_and_show_label():
    wb, ws = _build()
    assert ws["A4"].value == "京阪南"
    assert ws["B4"].value is None
    assert any(str(r) == "A4:B4" for r in ws.merged_cells.ranges)
    assert ws["A5"].value == "アドバリュー　8-1"
    assert any(str(r) == "A5:B5" for r in ws.merged_cells.ranges)


def test_data_row_values_match_bulk_rows():
    wb, ws = _build()
    assert ws["K4"].value == 847502    # 京阪南 売上合計(税込)
    assert ws["O4"].value == 324505    # 京阪南 配布原価(税込)
    assert ws["M5"].value == 6260      # アドバリュー8-1 交通費
    assert ws["O5"].value == 171280    # アドバリュー8-1 配布原価(税込)＝177540-6260
    assert ws["P5"].value == 177540    # 原価合計(税込)


def test_unsplit_columns_are_blank_on_generated_rows():
    wb, ws = _build()
    for col in ("C", "D", "E", "F", "G", "H", "I", "L"):
        assert ws[f"{col}4"].value is None, f"{col}4 が空欄でない: {ws[f'{col}4'].value!r}"


def test_data_row_font_matches_template_style_row(tpl):
    wb, ws = _build()
    src = tpl.ws.cell(S.DATA_ROW_STYLE, 11)  # K列(売上合計税込)の見本
    assert ws["K4"].font.name == src.font.name
    assert ws["K4"].font.sz == src.font.sz


def test_column_widths_are_copied_from_template(tpl):
    wb, ws = _build()
    for col in ("A", "B", "L"):
        assert ws.column_dimensions[col].width == pytest.approx(
            tpl.ws.column_dimensions[col].width, abs=0.05)


def test_monthly_filename():
    assert S.monthly_filename(2026, 8) == "2026年8月度_売上表.xlsx"


def test_build_monthly_workbook_with_no_rows_still_has_header():
    wb, ws = _build(rows=[])
    assert ws["A2"].value == "発行号"
    assert ws["A4"].value is None
