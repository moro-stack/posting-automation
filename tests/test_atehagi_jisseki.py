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


def test_jisseki_courses_basic():
    groups = A.group_by_chiku(A.rows_from_table(_sample_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    # 10101 は チラシ有り→載る。46501 は ぱどのみ→除外。
    assert len(courses) == 1
    c = courses[0]
    assert c["code"] == "010101"
    assert c["chiku_name"] == "枚方・交野"
    assert c["course_name"] == "010101 枚方・交野"
    assert c["flyers"] == [{"name": "サンプル生協", "count": 224}]


def _multi_flyer_table():
    header = ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所",
              "電話番号", "担当地区", "チラシコード", "配送物", "配布部数", "配送備考",
              "町界名", "街区（番地）名称", "受注種別", "チラシサイズ"]
    return [
        ["配送管理表", "2026-06-26", "(1248号)", "作成日:2026/06/18"],
        header,
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, None,
         "01 ぱど", 400, " ", "大住ヶ丘", "1丁目", None, None],
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, 400,
         "SUUMO/注文住宅", 400, " ", "大住ヶ丘", "1丁目", "全戸配布(チラシ)", "Ｂ４"],
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, 400,
         "ECC/宮野", 400, " ", "大住ヶ丘", "1丁目", "全戸配布(チラシ)", "Ｂ４"],
    ]


def test_jisseki_courses_multi_flyer_keeps_order():
    groups = A.group_by_chiku(A.rows_from_table(_multi_flyer_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    assert len(courses) == 1
    assert courses[0]["flyers"] == [
        {"name": "SUUMO/注文住宅", "count": 400},
        {"name": "ECC/宮野", "count": 400},
    ]
