import io
import hashlib
import openpyxl
from common import atehagi as A


def _groups():
    from tests.test_atehagi import _sample_table
    return A.group_by_chiku(A.rows_from_table(_sample_table()))


def test_build_atehagi_cells_match_layout():
    data = A.build_atehagi_workbook(_groups(), A.KEIHAN_KITA)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["10101", "46501"]

    s = wb["10101"]
    assert s["A1"].value == "枚方・交野"
    assert s["A3"].value == "テスト太郎"
    assert s["D4"].value == 10101
    assert s["G2"].value == 224
    assert s["B5"].value == "01 ぱど"
    assert s["I5"].value in (None, "")          # 先頭行はサイズ無し
    assert s["J5"].value == 224
    assert s["B6"].value == "サンプル生協"
    assert s["I6"].value == "Ｂ４(折済)"
    assert s["J6"].value == 224
    assert s["I18"].value == 1                   # チラシ数
    # 固定ラベルは保持
    assert str(s["A4"].value).startswith("担当地区")
    assert s["C4"].value == 0
    # 結合セルは維持
    assert {"A3:E3", "D4:G4", "G2:I2"} <= {str(m) for m in s.merged_cells.ranges}

    s2 = wb["46501"]
    assert s2["A1"].value == "寝屋川・枚方"
    assert s2["I18"].value == 0


def test_build_atehagi_is_deterministic():
    g = _groups()
    a = A.build_atehagi_workbook(g, A.KEIHAN_KITA)
    b = A.build_atehagi_workbook(A.group_by_chiku(
        A.rows_from_table(__import__("tests.test_atehagi", fromlist=["_sample_table"])._sample_table())),
        A.KEIHAN_KITA)
    assert hashlib.md5(a).hexdigest() == hashlib.md5(b).hexdigest()


def test_atehagi_filename():
    rows = A.rows_from_table(__import__("tests.test_atehagi", fromlist=["_sample_table"])._sample_table())
    name = A.atehagi_filename(A.KEIHAN_KITA, rows)
    assert name.startswith("京阪北版_あて紙_1248号_")
    assert name.endswith(".xlsx")
