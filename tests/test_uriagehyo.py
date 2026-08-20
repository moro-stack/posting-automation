import io

import openpyxl

from common import uriagehyo as U


def test_build_row_computes_zeinuki_and_genka_goukei():
    """実データ(2026年8月度売上表 京阪南版)と同じ入力で、同じ結果になること。"""
    row = U.build_row(hakko_gou="8/21", ban_mei="京阪南",
                      uriage_zeikomi=847502, genka_goukei_zeikomi=324505)
    assert row["売上合計（税込）"] == 847502
    assert row["売上合計（税抜）"] == 770456     # 847502 / 1.1 を四捨五入
    assert row["配布原価（税込）"] == 324505
    assert row["原価合計（税込）"] == 324505      # 交通費・飲み物が無ければ配布原価と同じ


def test_build_row_splits_genka_goukei_into_haifu_genka_and_extras():
    """実データ(アドバリュー8-1)と同じ入力で、実物の表と同じ列の値になること。

    アプリの原価集計(号別明細の「配布原価(税込)」)は小口の交通費・飲み物代も
    含んだ総額なので、これを genka_goukei_zeikomi として渡す。実物の表は
    「配布原価」列をそこから交通費・飲み物を除いた額にしているため、
    ここで差し引く(配布原価＝総額－交通費－飲み物、原価合計＝総額のまま)。
    """
    row = U.build_row(hakko_gou="8-1", ban_mei="ｱﾄﾞ・バリュー",
                      uriage_zeikomi=544970, genka_goukei_zeikomi=177540,
                      koutsuhi=6260, nomimono=0)
    assert row["交通費（駐車場代含）"] == 6260
    assert row["配布原価（税込）"] == 171280      # 実データと一致(177540-6260)
    assert row["原価合計（税込）"] == 177540      # 実データと一致(渡した総額のまま)


def test_build_row_leaves_unsplit_columns_blank():
    """ぱど/チラシ/仕分け/その他/備考はアプリに区分の記録が無いため空欄のまま。"""
    row = U.build_row(hakko_gou="8/21", ban_mei="京阪南",
                      uriage_zeikomi=847502, genka_goukei_zeikomi=324505)
    for col in ("ぱど部数", "ぱど売上（税抜）", "チラシ部数", "チラシ売上（税抜）",
                "仕分け部数", "仕分け売上（税抜）", "その他", "備考"):
        assert row[col] is None, f"{col} が空欄でない: {row[col]}"


def test_build_row_zero_koutsuhi_and_nomimono_are_blank_not_zero():
    """0円は「無い」のと同じなので、実物の表と同じく空欄(0を書かない)にする。"""
    row = U.build_row(hakko_gou="8/21", ban_mei="京阪南",
                      uriage_zeikomi=847502, genka_goukei_zeikomi=324505,
                      koutsuhi=0, nomimono=0)
    assert row["交通費（駐車場代含）"] is None
    assert row["飲み物"] is None


def test_build_workbook_headers_match_the_real_sheet():
    rows = [U.build_row(hakko_gou="8/21", ban_mei="京阪南",
                        uriage_zeikomi=847502, genka_goukei_zeikomi=324505)]
    data = U.build_workbook(rows)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "発行号"
    assert ws["B1"].value == "版名"
    assert ws["J1"].value == "売上合計（税抜）"
    assert ws["K1"].value == "売上合計（税込）"
    assert ws["O1"].value == "配布原価（税込）"
    assert ws["P1"].value == "原価合計（税込）"
    assert ws["A2"].value == "8/21"
    assert ws["B2"].value == "京阪南"
    assert ws["K2"].value == 847502


def test_uriagehyo_filename():
    assert U.uriagehyo_filename() == "会議用売上表_出力.xlsx"
