import hashlib
import io

import openpyxl

from common import proceed_atehagi as P


def _row(pairs, width=16):
    r = [None] * width
    for idx, val in pairs:
        r[idx] = val
    return r


def _sample_irai():
    """配布依頼書兼終了報告書の構造を模した合成テーブル（実在名なし）。
    excel行 = リスト index+1。列 A=0,B=1,...F=5,G=6,H=7,...P=15。
    パーサはヘッダー語（チラシ名/チラシ枚数/サイズ/配布エリア/媒体部数）で列を検出する。"""
    return [
        _row([(8, "配布依頼書　兼　配布終了報告書【サンプル市】")]),          # 1: I1 タイトル
        _row([(0, "2025年09月26日号\n※納期は…"), (5, "チラシ名\n（広告主）"),
              (6, "サンプル広告主A/企画"), (7, "サンプル広告主B/企画"),
              (15, "チラシ\n枚数")]),                                          # 2: 広告主ヘッダー行
        _row([]),                                                              # 3
        _row([]),                                                              # 4
        _row([(5, "サイズ"), (6, "B4"), (7, "A4")]),                          # 5: サイズ行
        _row([]),                                                              # 6
        _row([]),                                                              # 7
        _row([(0, "件数"), (1, "配布エリア"), (2, "ページ数"),
              (3, "各戸ﾎﾟｽﾄ"), (4, "集合ﾎﾟｽﾄ"), (5, "媒体部数")]),           # 8: 明細ヘッダー
        _row([(0, 1), (1, "サンプル-1-1"), (5, 300), (6, 300), (7, 0)]),      # 9: エリア1
        _row([(1, "サンプル町1")]),                                            # 10: 町名
        _row([(0, 2), (1, "サンプル-1-2"), (5, 500), (6, 500), (7, 200)]),    # 11: エリア2
        _row([(1, "サンプル町2")]),                                            # 12: 町名
        _row([(0, "合 計")]),                                                  # 13: 合計→終了
    ]


def test_parse_haifu_irai():
    p = P.parse_haifu_irai(_sample_irai())
    assert p["group"] == "サンプル市"
    assert p["gou"] == "2025年09月26日号"
    assert [a["name"] for a in p["advertisers"]] == ["サンプル広告主A/企画", "サンプル広告主B/企画"]
    assert [a["size"] for a in p["advertisers"]] == ["B4", "A4"]
    assert len(p["areas"]) == 2
    assert p["areas"][0] == {"code": "サンプル-1-1", "media_busuu": 300,
                             "town": "サンプル町1", "ads": [300, 0]}
    assert p["areas"][1]["ads"] == [500, 200]


def test_build_proceed_atehagi_cells():
    p = P.parse_haifu_irai(_sample_irai())
    data = P.build_proceed_atehagi_workbook(p)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["サンプル-1-1", "サンプル-1-2"]

    s = wb["サンプル-1-1"]
    assert s["B1"].value == "リビング新聞"
    assert s["F3"].value == "サンプル市"
    assert str(s["C4"].value).startswith("担当地区")
    assert s["E4"].value == "サンプル-1-1"
    assert s["G2"].value == 300
    assert s["C6"].value == "リビング"
    assert s["H6"].value == "ﾀﾌﾞﾛｲﾄﾞ"
    assert s["I6"].value == 300
    # 部数>0の広告主だけ（Aのみ、Bは0なので載らない）
    assert s["C7"].value == "サンプル広告主A/企画"
    assert s["H7"].value == "B4"
    assert s["I7"].value == 300
    assert s["C8"].value in (None, "")
    assert s["I48"].value == 1              # チラシ数

    s2 = wb["サンプル-1-2"]
    assert s2["G2"].value == 500
    assert s2["C7"].value == "サンプル広告主A/企画"
    assert s2["I7"].value == 500
    assert s2["C8"].value == "サンプル広告主B/企画"
    assert s2["I8"].value == 200
    assert s2["I48"].value == 2


def test_build_proceed_is_deterministic():
    p = P.parse_haifu_irai(_sample_irai())
    a = P.build_proceed_atehagi_workbook(p)
    b = P.build_proceed_atehagi_workbook(P.parse_haifu_irai(_sample_irai()))
    assert hashlib.md5(a).hexdigest() == hashlib.md5(b).hexdigest()


def test_proceed_filename():
    p = P.parse_haifu_irai(_sample_irai())
    name = P.proceed_atehagi_filename(p)
    assert name.startswith("リビングプロシード_あて紙_サンプル市_")
    assert name.endswith(".xlsx")
