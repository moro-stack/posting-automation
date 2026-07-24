import io

import openpyxl

from common import atehagi as A
from tests.test_atehagi import _sample_table


def _groups():
    return A.group_by_chiku(A.rows_from_table(_sample_table()))


def test_jisseki_rows_skips_pado_only_area():
    rows = A.jisseki_rows(_groups(), A.KEIHAN_KITA)
    # 10101 は チラシ(サンプル生協)有り→載る。46501 は 04 ぱど のみ→飛ばす。
    assert len(rows) == 1
    r = rows[0]
    assert r["No."] == 1
    assert r["エリア"] == "枚方・交野"
    assert r["担当地区"] == "010101"     # あて紙と同じ6桁ゼロ埋め（関西ぱど 2026-07-23）
    assert r["リーダー"] == "テスト太郎"
    assert r["チラシ種類数"] == 1
    assert r["チラシ内容"] == "サンプル生協"
    assert r["部数"] == 224
    assert r["サイン"] == ""


def test_build_jisseki_workbook():
    rows = A.jisseki_rows(_groups(), A.KEIHAN_KITA)
    data = A.build_jisseki_workbook(rows)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A2"].value == "No."
    assert ws["B2"].value == "エリア"
    assert ws["H2"].value == "サイン"
    assert ws["A3"].value == 1
    assert ws["B3"].value == "枚方・交野"
    assert ws["F3"].value == "サンプル生協"


def test_jisseki_filename():
    rows = A.rows_from_table(_sample_table())
    name = A.jisseki_filename(A.KEIHAN_KITA, rows)
    assert name.startswith("京阪北版_挟み込み実績表_1248号_")
    assert name.endswith(".xlsx")
