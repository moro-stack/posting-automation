import io

import openpyxl

from common import advalue as V


def test_parse_choume_edge_cases():
    # 現行マクロが取りこぼしていたケースを含む
    assert V.parse_choume_from_gaiku("1丁目1～21") == {1}
    assert V.parse_choume_from_gaiku("2・3丁目") == {2, 3}
    assert V.parse_choume_from_gaiku("4・5丁目") == {4, 5}
    assert V.parse_choume_from_gaiku("6丁目51～57・7丁目") == {6, 7}     # 番地57を丁目に誤認しない
    assert V.parse_choume_from_gaiku("1丁目・2丁目11～34") == {1, 2}      # 2丁目を落とさない
    assert V.parse_choume_from_gaiku("１丁目") == {1}                     # 全角
    assert V.parse_choume_from_gaiku("") == set()                        # 丁目なし=ワイルドカード


def test_split_town_choume():
    assert V.split_town_choume("大久保町1") == ("大久保町", 1)
    assert V.split_town_choume("大久保町1丁目") == ("大久保町", 1)
    assert V.split_town_choume("宮前町") == ("宮前町", None)


def test_match_area_with_choume_range():
    # 大久保町1丁目が 913101(1～21) と 913102(22～52) に分かれている → 依頼表「大久保町1」は両方に被り
    index = V.build_minami_index([
        ["配送管理表"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
        [None, None, None, None, None, None, None, None, "913101", None, "91 ぱど",
         438, None, "大久保町", "1丁目1～21"],
        [None, None, None, None, None, None, None, None, "913102", None, "91 ぱど",
         438, None, "大久保町", "1丁目22～52"],
        [None, None, None, None, None, None, None, None, "923301", None, "91 ぱど",
         110, None, "大庭町", "1・2丁目"],
    ])
    assert V.match_area("大久保町", 1, index) == ["913101", "913102"]
    assert V.match_area("大庭町", 1, index) == ["923301"]
    assert V.match_area("大庭町", 2, index) == ["923301"]
    assert V.match_area("存在しない町", 1, index) == []     # 未マッチ


def test_build_report_rows_and_summary():
    index = V.build_minami_index([
        ["配送管理表"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
        [None] * 8 + ["913101", None, "x", 1, None, "大久保町", "1丁目"],
    ])
    irai = [
        {"geocode": "27209001001", "shiku": "守口市", "choume_name": "大久保町1",
         "setai": 840, "kyodo_setai": 134, "zantei": 570, "client1": "×", "client2": "○",
         "haifubi_memo": "6月9日", "heihai": 570, "biko": "サンプル店", "toukin": "なし",
         "haifubi": "6/8-6/14"},
        {"geocode": "27209099999", "shiku": "守口市", "choume_name": "被らない町9",
         "setai": 100, "kyodo_setai": 10, "zantei": 100, "client1": "×", "client2": "○",
         "haifubi_memo": "", "heihai": 100, "biko": "店", "toukin": "なし",
         "haifubi": "6/8-6/14"},
    ]
    rows = V.build_report_rows(irai, index)
    assert rows[0]["担当地区(被り)"] == "913101"
    assert rows[0]["被り"] == "被り"
    assert rows[0]["世帯数15"] == 840
    assert rows[1]["担当地区(被り)"] == "未マッチ"
    assert rows[1]["被り"] == "非被り"
    assert V.overlap_summary(rows) == {"total": 2, "overlap": 1, "non_overlap": 1}


def test_build_report_workbook():
    rows = [{"町丁目名": "サンプル町1", "市区名": "サンプル市", "担当地区(被り)": "913101",
             "被り": "被り", "世帯数15": 840, "暫定部数": 570, "クライアント①": "×",
             "クライアント②": "○", "配布日メモ": "6月9日", "併配部数": 570, "店舗名": "サンプル店",
             "投禁物件": "なし", "配布日": "6/8-6/14"}]
    data = V.build_advalue_report_workbook(rows)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "町丁目名"
    assert ws["C1"].value == "担当地区(被り)"
    assert ws["G1"].value == "クライアント①"
    assert ws["A2"].value == "サンプル町1"
    assert ws["C2"].value == "913101"
    assert ws["D2"].value == "被り"
