import io

import openpyxl

from common import atehagi as A
from tests.test_atehagi import _sample_table


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
    assert ws["A2"].value == "テスト太郎"              # リーダー名の見出し行
    assert ws["A3"].value == "010101 枚方・交野"     # ヘッダー(コース名)
    assert ws["A4"].value == "サンプル生協"           # 本文(案件名)
    assert ws["B4"].value == "224"                    # 本文(枚数)
    assert ws["A5"].value == "サイン："                # サイン行
    assert ws["A5"].border.bottom.style is not None    # 署名用の横線
    assert ws.page_setup.orientation == "landscape"


# ===== リーダー名・外注先ごとの分割表示（依頼④・2026-08-19 大橋様ご指摘） =====


def test_jisseki_courses_includes_leader():
    groups = A.group_by_chiku(A.rows_from_table(_sample_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    assert courses[0]["leader"] == "テスト太郎"


def test_build_daishi_groups_courses_by_leader_with_header_row():
    """リーダー(または外注先)が変わったら、その名前の見出し行を挟んで
    グループごとに表示する。実物の手書き台帳(CJ/時野/竹島/宇田/枡田…)と
    同じく、名前ごとにひとまとまりで見えること。"""
    courses = [
        {"code": "010101", "chiku_name": "A地区", "course_name": "010101 A地区",
         "flyers": [{"name": "f1", "count": 100}], "leader": "山田"},
        {"code": "010102", "chiku_name": "B地区", "course_name": "010102 B地区",
         "flyers": [{"name": "f2", "count": 200}], "leader": "外注先会社"},
        {"code": "010103", "chiku_name": "C地区", "course_name": "010103 C地区",
         "flyers": [{"name": "f3", "count": 300}], "leader": "山田"},
    ]
    data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1,
                                           haifubi="2026-06-26")
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    # グループ1: 山田(010101と010103。離れて出てきても同じグループにまとまり、
    # per_row=4以内なので同じ行ブロックの隣の列に並ぶ)
    assert ws["A2"].value == "山田"
    assert ws["A3"].value == "010101 A地区"
    assert ws["C3"].value == "010103 C地区"      # 山田グループの2件目(2列目)
    # グループ2: 外注先会社(新しい行ブロックから、A列に戻って始まる)
    assert ws["A6"].value == "外注先会社"
    assert ws["A7"].value == "010102 B地区"


def test_build_daishi_without_leader_key_has_no_header_row():
    """leader を持たないコース(既存の呼び出し方)は、以前どおり見出し行を出さない。"""
    courses = [
        {"code": "010101", "chiku_name": "A地区", "course_name": "010101 A地区",
         "flyers": [{"name": "f1", "count": 100}]},
    ]
    data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1,
                                           haifubi="2026-06-26")
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A2"].value == "010101 A地区"


def test_build_daishi_wrapping_4_per_row():
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
    # 4コース目 grp0 col3 → 案件名列 G, ヘッダー行2
    assert ws["G2"].value == "010104 枚方・交野"
    # 5コース目 grp1 col0 → A列, ヘッダー行 = 2 + 1*3 = 5
    assert ws["A5"].value == "010105 枚方・交野"
