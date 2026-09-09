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
    assert s["D4"].value == "010101"          # 6桁ゼロ埋め（関西ぱど 2026-07-23）
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
    assert s["C4"].value is None               # 固定の0は消す（D4が6桁になったため）
    # 結合セルは維持
    assert {"A3:E3", "D4:G4", "G2:I2"} <= {str(m) for m in s.merged_cells.ranges}

    s2 = wb["46501"]
    assert s2["A1"].value == "寝屋川・枚方"
    assert s2["I18"].value == 0


# ===== 通し番号（依頼①・2026-09-04大橋様ご依頼: 挟み込み実績表と一致させる） =====


def test_build_atehagi_prints_the_course_number_next_to_busuu():
    """挟み込みチラシがある地区(=実績表に載る)には、H1セルに通し番号を数字だけ
    (例: 1)で入れる。実績表と同じ assign_course_numbers() の番号と一致すること。
    (2026-09-09大橋様ご依頼: F2だと見にくい→H1へ／"No."表記は無くし数字のみに)"""
    data = A.build_atehagi_workbook(_groups(), A.KEIHAN_KITA)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb["10101"]["H1"].value == 1


def test_build_atehagi_course_number_font_matches_the_other_big_labels():
    """🔴 2026-09-09大橋様ご指摘: H1のテンプレ既定フォントサイズ(11)は他の見出し
    (地区名A1・ぱどんな名A3・担当地区D4・部数G2＝いずれもサイズ48)に比べて小さすぎる。
    同じ48サイズ・太字に揃える。"""
    data = A.build_atehagi_workbook(_groups(), A.KEIHAN_KITA)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    font = wb["10101"]["H1"].font
    assert font.sz == 48
    assert font.b is True


def test_build_atehagi_pado_only_area_has_no_course_number():
    """ぱどのみ地区(実績表に対応する枠が無い)には番号を振らない。"""
    data = A.build_atehagi_workbook(_groups(), A.KEIHAN_KITA)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb["46501"]["H1"].value is None


def test_build_atehagi_and_jisseki_numbers_match_for_a_large_leader_group():
    """🔴 2026-09-04大橋様ご確認: 「実績表は1〜100まで通し番号があるのに、
    あて紙は10までしかない」という報告の再現・原因切り分け用の回帰テスト。
    100コース(同一リーダー)＋別リーダーの地区20件を混ぜても、あて紙の
    F2("No.n")と実績表のヘッダー番号が1〜100まで過不足なく一致することを確認する
    (=numbers計算そのものにはズレが無い。あて紙のシート並びは担当地区コード順で
    通し番号順ではないため、タブを順番に流し見ただけでは連番に見えないだけの
    可能性が高い、という説明の裏付け)。"""
    import re

    header = ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所",
              "電話番号", "担当地区", "チラシコード", "配送物", "配布部数", "配送備考",
              "町界名", "街区（番地）名称", "受注種別", "チラシサイズ"]
    table = [["配送管理表", "2026-06-26", "(1248号)", "作成日:2026/06/18"], header]
    for i in range(1, 101):
        code = 10000 + i
        table.append(["2026-06-26", 1248, 0, None, None, "フィールドサービス", None, None,
                      code, None, "01 ぱど", 100, " ", f"町{i}", "1丁目", None, None])
        table.append(["2026-06-26", 1248, 0, None, None, "フィールドサービス", None, None,
                      code, 50, "チラシA", 100, " ", f"町{i}", "1丁目",
                      "全戸配布(チラシ)", "Ｂ４"])
    for i in range(1, 21):
        code = 20000 + i
        table.append(["2026-06-26", 1248, 0, None, None, "別リーダー", None, None,
                      code, None, "01 ぱど", 200, " ", f"町{i}", "1丁目", None, None])

    groups = A.group_by_chiku(A.rows_from_table(table))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    fs_codes = {c["code"] for c in courses if c["leader"] == "フィールドサービス"}
    assert len(fs_codes) == 100

    jisseki_data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1248,
                                                    haifubi="2026-06-26")
    ws_j = openpyxl.load_workbook(io.BytesIO(jisseki_data))["フィールドサービス"]
    jisseki_numbers = set()
    for row in ws_j.iter_rows():
        for c in row:
            if isinstance(c.value, str):
                m = re.match(r"^(\d+)\n", c.value)
                if m:
                    jisseki_numbers.add(int(m.group(1)))
    assert jisseki_numbers == set(range(1, 101))

    # 別リーダーの20地区はぱどのみ(チラシ無し)なので numbers に入らず H1 は空のまま。
    # あて紙全シートのH1値を集めても、フィールドサービスの100件しか出てこないはず。
    atehagi_data = A.build_atehagi_workbook(groups, A.KEIHAN_KITA)
    wb_a = openpyxl.load_workbook(io.BytesIO(atehagi_data))
    assert len(wb_a.sheetnames) == 120   # 100(フィールドサービス) + 20(別リーダー)
    atehagi_numbers = set()
    for sheetname in wb_a.sheetnames:
        h1 = wb_a[sheetname]["H1"].value
        if h1:
            atehagi_numbers.add(int(h1))
    assert atehagi_numbers == jisseki_numbers == set(range(1, 101))


def test_build_atehagi_reprint_keeps_the_original_numbering():
    """🔴 単票の刷り直しで numbers を渡さないと、部分集合から番号が振り直されて
    実績表とズレる。明示的に渡した numbers がそのまま使われること。"""
    groups = _groups()
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    numbers = A.assign_course_numbers(courses)   # {"010101": 1}
    sel = {"10101": groups["10101"]}              # 1件だけの単票刷り直し
    data = A.build_atehagi_workbook(sel, A.KEIHAN_KITA, numbers=numbers)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb["10101"]["H1"].value == 1


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
