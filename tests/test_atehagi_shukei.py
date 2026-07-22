import io

import openpyxl

from common import atehagi as A
from tests.test_atehagi import _sample_table


def _groups():
    return A.group_by_chiku(A.rows_from_table(_sample_table()))


def test_shukei_data_totals_and_by_type():
    d = A.shukei_data(_groups(), A.KEIHAN_KITA)
    assert d["total_chiku"] == 2
    assert d["total_busuu"] == 660          # 224 + 436
    assert d["chirashi_sou"] == 224         # サンプル生協 のみ
    assert d["pado_only_busuu"] == 436      # 46501 は ぱどのみ
    assert d["area_busuu"] == {"1": 224, "4": 436}
    assert d["area_chiku"] == {"1": 1, "4": 1}
    assert d["sashikomi_busuu"] == 224       # 挿込=チラシ有り地区(10101)の部数
    assert d["choai_busuu"] == 0             # 帳合=2種以上の地区は無し
    assert d["type_dist"] == {1: [1, 224], 0: [1, 436]}
    p1 = d["per"][("1", "テスト太郎")]
    assert p1["chiku"] == 1 and p1["busuu"] == 224
    assert dict(p1["by_type"]) == {1: [1, 224]}       # チラシ1種の地区が1つ・224部
    p4 = d["per"][("4", "テスト花子")]
    assert dict(p4["by_type"]) == {0: [1, 436]}       # ぱどのみ(0種)


def test_build_shukei_workbook():
    d = A.shukei_data(_groups(), A.KEIHAN_KITA)
    data = A.build_shukei_workbook(d, A.KEIHAN_KITA)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "京阪 集計表"
    text = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
    assert "エリア" in text and "リーダー" in text
    assert "総地区数" in text and "チラシ総数(全チラシ部数)" in text


def test_shukei_filename():
    rows = A.rows_from_table(_sample_table())
    name = A.shukei_filename(A.KEIHAN_KITA, rows)
    assert name.startswith("京阪北版_集計表_1248号_")
    assert name.endswith(".xlsx")
