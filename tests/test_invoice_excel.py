import io
import openpyxl
import pytest
from common import invoice_excel


def _load(data):
    return openpyxl.load_workbook(io.BytesIO(data)).active


def test_build_invoice_fills_lines_and_total():
    lines = [
        {"project_name": "関西ぱど：京阪北版", "report_qty": 3713, "unit_price": 3,
         "amount": 11139, "remark": "配布"},
        {"project_name": "関西ぱど：京阪北版", "report_qty": 1, "unit_price": 540,
         "amount": 540, "remark": "交通費"},
    ]
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="時野", issue_date="2026年6月30日",
        period_from="2026年6月19日", period_to="2026年6月27日", lines=lines)
    ws = _load(data)
    # 明細1行目(13行) の案件名・数量・単価・計
    assert ws["B13"].value == "関西ぱど：京阪北版"
    assert ws["D13"].value == 3713
    assert ws["E13"].value == 3
    assert ws["F13"].value == 11139
    # ご請求金額(A7)に合計 11679 が含まれる(カンマ区切り表記を許容)
    assert "11679" in str(ws["A7"].value).replace(",", "")
    # 配布部数(F20)= 配布のみ 3713(交通費は除外、単位「部」・カンマ区切りを許容)
    assert "3713" in str(ws["F20"].value).replace(",", "")


def test_build_invoice_returns_bytes():
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="黒瀬", issue_date="2026年6月30日",
        period_from="", period_to="",
        lines=[{"project_name": "その他", "report_qty": 10, "unit_price": 5,
                "amount": 50, "remark": "配布"}])
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0


def test_build_invoice_rejects_more_than_max_line_rows():
    lines = [{"project_name": "その他", "report_qty": 1, "unit_price": 1,
              "amount": 1, "remark": "配布"} for _ in range(7)]
    with pytest.raises(ValueError):
        invoice_excel.build_invoice_xlsx(
            distributor_name="黒瀬", issue_date="2026年6月30日",
            period_from="", period_to="", lines=lines)
