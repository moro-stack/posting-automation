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


def test_shukei_filename():
    rows = A.rows_from_table(_sample_table())
    name = A.shukei_filename(A.KEIHAN_KITA, rows)
    assert name.startswith("京阪北版_集計表_1248号_")
    assert name.endswith(".xlsx")


def _sample_shukei_data():
    return {
        "per": {
            ("1", "aim"): {"chiku": 3, "busuu": 300, "by_type": {2: [2, 200], 1: [1, 100]}},
            ("1", "fs"): {"chiku": 1, "busuu": 50, "by_type": {0: [1, 50]}},
            ("2", "x"): {"chiku": 2, "busuu": 150, "by_type": {3: [2, 150]}},
        },
        "area_busuu": {"1": 350, "2": 150},
        "area_chiku": {"1": 4, "2": 2},
        "type_dist": {0: [1, 50], 1: [1, 100], 2: [2, 200], 3: [2, 150]},
        "total_chiku": 6, "total_busuu": 500, "chirashi_sou": 9999,
        "pado_only_busuu": 50, "choai_busuu": 200, "sashikomi_busuu": 450,
    }


def test_shukei_layout_orders_area_leader_type():
    layout = A._shukei_layout(_sample_shukei_data())
    assert [b["area"] for b in layout] == ["1", "2"]           # エリア昇順
    a1 = layout[0]["leaders"]
    assert [l["name"] for l in a1] == ["aim", "fs"]            # 部数降順
    assert a1[0]["types"] == [(1, 1, 100), (2, 2, 200)]        # 種類数昇順
    assert a1[0]["busuu"] == 300 and a1[0]["chiku"] == 3


def test_build_shukei_daishi_layout():
    data = _sample_shukei_data()
    out = A.build_shukei_daishi_workbook(data, A.KEIHAN_KITA, gou=1248, haifubi="2026-06-26")
    wb = openpyxl.load_workbook(io.BytesIO(out))
    ws = wb.active
    # タイトル・ヘッダー
    assert ws["A1"].value == "京阪北版"
    assert ws["A3"].value == "エリア" and ws["B3"].value == "リーダー"
    assert ws["C3"].value == "チラシ種類" and ws["E3"].value == "コース数"
    assert ws["AG3"].value == "配布部数" and ws["AH3"].value == "地区数"
    # 上部マトリクス: area1 aim(row4) → 種類数1,2 が C,H ブロック
    assert ws["A4"].value == 1 and ws["B4"].value == "aim"
    assert ws["C4"].value == 1 and ws["D4"].value == "-" and ws["E4"].value == 1 and ws["F4"].value == 100
    assert ws["H4"].value == 2 and ws["K4"].value == 200
    assert ws["AG4"].value == 300 and ws["AH4"].value == 3
    # fs(row5), area2 x(row7・区切り空行あり)
    assert ws["B5"].value == "fs" and ws["C5"].value == 0 and ws["F5"].value == 50
    assert ws["A7"].value == 2 and ws["B7"].value == "x" and ws["C7"].value == 3 and ws["F7"].value == 150
    # 下部: チラシ種類数別(5→0)＋総計。br = 上部末尾+2 = 10
    # 実物帳票の枠は 5〜0 の6行。使われていない 11〜6 の空枠は出さない（2026-08-06 大橋さん要望）
    assert ws["B10"].value == 5 and ws["D10"].value == 0             # 種類数5=データ無し→0
    assert ws["B15"].value == 0 and ws["D15"].value == 1 and ws["F15"].value == 50   # 種類数0
    assert ws["B16"].value == 6 and ws["F16"].value == 500          # 総計
    # 集計指標(M列ラベル/Q列値)・折チラシ空
    assert ws["M10"].value == "帳合" and ws["Q10"].value == 200
    assert ws["M13"].value == "折チラシ（B3,B4）" and ws["Q13"].value == "—"
    assert ws["M14"].value == "チラシ総数" and ws["Q14"].value == 9999
    # エリア別部数
    assert ws["M18"].value == "エリア1" and ws["P18"].value == 350
    assert ws.page_setup.orientation == "landscape"
    assert "1248号" in ws["G1"].value          # 号数がタイトルに入る
    assert ws["A1"].font.color.rgb == "FFFF0000"        # 版名は赤字
    assert ws["C4"].font.color.rgb == "FFFF0000"        # チラシ種類数は赤字
    assert ws["H4"].font.color.rgb == "FFFF0000"
    assert ws["E4"].font.color is None or ws["E4"].font.color.rgb != "FFFF0000"  # コース数は赤でない
    assert ws["F4"].font.color is None or ws["F4"].font.color.rgb != "FFFF0000"  # 部数は赤でない


def test_build_shukei_daishi_print_area_scales_with_areas():
    data = dict(_sample_shukei_data())
    data["area_busuu"] = {str(i): 100 for i in range(1, 7)}   # 6エリア
    out = A.build_shukei_daishi_workbook(data, A.KEIHAN_KITA, gou=1, haifubi="2026-06-26")
    ws = openpyxl.load_workbook(io.BytesIO(out)).active
    tail = ws.print_area.split(":")[1]
    last = int("".join(ch for ch in tail if ch.isdigit()))
    assert last >= 23           # 6番目のエリア行(br+8+5=23)が印刷範囲に入る


def _shukei_ws(type_dist):
    data = dict(_sample_shukei_data())
    data["type_dist"] = type_dist
    out = A.build_shukei_daishi_workbook(data, A.KEIHAN_KITA, gou=1, haifubi="2026-06-26")
    return openpyxl.load_workbook(io.BytesIO(out)).active


def _type_rows(ws, br=10):
    """下部集計の「チラシ種類数」列(B)を上から読む。総計行の手前まで。"""
    out = []
    r = br
    while ws.cell(r, 3).value == "-":      # C列が "-" の行が種類数行
        out.append(ws.cell(r, 2).value)
        r += 1
    return out


def test_shukei_type_frame_is_six_rows_when_types_are_few():
    """使われていない空枠は出さない。実物帳票と同じ 5〜0 の6行にする（2026-08-06 大橋さん要望）。"""
    ws = _shukei_ws({0: [1, 50], 1: [1, 100], 2: [2, 200], 3: [2, 150]})
    assert _type_rows(ws) == [5, 4, 3, 2, 1, 0]


def test_shukei_type_frame_extends_so_data_is_never_dropped():
    """5種を超えるデータがあるときは枠を伸ばす（詰めたせいで数字が消えないこと）。"""
    ws = _shukei_ws({0: [1, 50], 7: [3, 900]})
    assert _type_rows(ws) == [7, 6, 5, 4, 3, 2, 1, 0]
    assert ws.cell(10, 2).value == 7 and ws.cell(10, 4).value == 3 and ws.cell(10, 6).value == 900


def test_shukei_type_frame_never_exceeds_the_fixed_max():
    """枠は SHUKEI_TYPE_MAX(11) まで. それを超える種類は overflow 警告側で拾う。"""
    ws = _shukei_ws({0: [1, 50], 13: [1, 500]})
    assert _type_rows(ws)[0] == A.SHUKEI_TYPE_MAX


def test_shukei_overflow_types_empty_when_all_within_frame():
    # 下部集計は 0〜11種の固定枠。枠内に収まっていれば警告対象は無い
    data = {"type_dist": {0: [5, 100], 9: [1, 20], 11: [2, 30]}}
    assert A.shukei_overflow_types(data) == []


def test_shukei_overflow_types_reports_types_beyond_the_frame():
    # 12種以上は下部集計の枠に載らない → 種類数の昇順で(種類数, 地区数, 部数)を返す。
    # 挿入順を昇順(12→13)にしておくことで、並べ替えを外すと順序が崩れて落ちる。
    data = {"type_dist": {0: [5, 100], 12: [2, 300], 13: [1, 500], 11: [2, 30]}}
    assert A.shukei_overflow_types(data) == [(12, 2, 300), (13, 1, 500)]
