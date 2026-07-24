import io

import openpyxl

from common import atehagi as A
from tests.test_atehagi import _sample_table


def _groups():
    return A.group_by_chiku(A.rows_from_table(_sample_table()))


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


def test_md_from():
    assert A._md_from("2026-06-26") == "6/26"
    import datetime
    assert A._md_from(datetime.date(2026, 6, 26)) == "6/26"
    assert A._md_from("") == ""


def test_build_daishi_title_and_first_course():
    groups = A.group_by_chiku(A.rows_from_table(_sample_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1248,
                                           haifubi="2026-06-26")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "6/26 ／ 1248号　京阪北版"
    assert ws["A2"].value == "010101 枚方・交野"          # ヘッダー(コース名)
    assert ws["A3"].value == "サンプル生協\n（サイン）"     # 本文(案件名+サイン)
    assert ws["B3"].value == "224"                        # 本文(枚数)
    assert ws.page_setup.orientation == "landscape"


def test_build_daishi_wrapping_4_per_row():
    # 5コース → 2行目(grp1)に5コース目が来る（行2-3がgrp0、行4-5がgrp1）
    courses = [
        {"code": f"01010{i}", "chiku_name": "枚方・交野",
         "course_name": f"01010{i} 枚方・交野",
         "flyers": [{"name": "A", "count": 100}]}
        for i in range(1, 6)
    ]
    data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1,
                                           haifubi="2026-06-26")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    # 4コース目は grp0 の col3 → 案件名列 = 1+3*2 = 7 (G列) の行2
    assert ws["G2"].value == "010104 枚方・交野"
    # 5コース目は grp1 の col0 → A列 の行4
    assert ws["A4"].value == "010105 枚方・交野"
