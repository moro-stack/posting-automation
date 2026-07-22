import io
import openpyxl
from common import atehagi as A


def test_read_uploaded_csv_cp932():
    text = "配送管理表,,,\n担当地区,ぱどんな,配送物,配布部数,チラシサイズ\n10101,太郎,01 ぱど,224,\n"
    data = text.encode("cp932")
    table = A.read_uploaded("x.csv", data)
    rows = A.rows_from_table(table)
    assert rows[0]["chiku"] == "10101"
    assert rows[0]["padonna"] == "太郎"


def test_read_uploaded_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["配送管理表", None, None])
    ws.append(["担当地区", "ぱどんな", "配送物", "配布部数", "チラシサイズ"])
    ws.append([10101, "太郎", "01 ぱど", 224, None])
    buf = io.BytesIO(); wb.save(buf)
    table = A.read_uploaded("x.xlsx", buf.getvalue())
    rows = A.rows_from_table(table)
    assert rows[0]["chiku"] == 10101
