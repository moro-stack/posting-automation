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


# ===== 内訳列を売上登録から反映する（2026-09-04大橋様ご依頼） =====


def test_build_row_uses_the_breakdown_when_given():
    """渡された分はそのまま列に入る(渡さなければ従来どおり空欄。上のテストで確認済み)。"""
    row = U.build_row(hakko_gou="8/21", ban_mei="京阪南",
                      uriage_zeikomi=847502, genka_goukei_zeikomi=324505,
                      pado_busuu=69443, pado_uriage=590266,
                      chirashi_busuu=74404, chirashi_uriage=171129,
                      shiwake_busuu=15897, shiwake_uriage=9061,
                      sonota_uriage=None, bikou="南版チラシ総受注　90,301部")
    assert row["ぱど部数"] == 69443
    assert row["ぱど売上（税抜）"] == 590266
    assert row["チラシ部数"] == 74404
    assert row["チラシ売上（税抜）"] == 171129
    assert row["仕分け部数"] == 15897
    assert row["仕分け売上（税抜）"] == 9061
    assert row["その他"] is None
    assert row["備考"] == "南版チラシ総受注　90,301部"


def test_ban_mei_of_derives_from_project_name():
    """版名は案件から自動で決まる。単独/アドバリューは空欄のまま。"""
    assert U._ban_mei_of("関西ぱど：京阪北版") == "京阪北"
    assert U._ban_mei_of("関西ぱど：京阪南版") == "京阪南"
    assert U._ban_mei_of("リビングプロシード") == "リビング"
    assert U._ban_mei_of("アドバリュー") is None
    assert U._ban_mei_of("その他") is None
    assert U._ban_mei_of("知らない案件") is None


def test_build_bulk_rows_fills_ban_mei_and_breakdown_from_receivables():
    rows = U.build_bulk_rows(
        receivables=[{"project_id": 1, "amount": 847502, "hakko_gou": "8/21",
                     "pado_busuu": 69443, "pado_uriage": 590266,
                     "chirashi_busuu": 74404, "chirashi_uriage": 171129,
                     "note": "南版チラシ総受注　90,301部"}],
        petty=[], payables=[], contract_lines=[], manual=[],
        id2proj={1: "関西ぱど：京阪南版"}, id2cat={})
    label, row = rows[0]
    assert row["版名"] == "京阪南"
    assert row["発行号"] == "8/21"
    assert row["ぱど部数"] == 69443
    assert row["チラシ売上（税抜）"] == 171129
    assert row["備考"] == "南版チラシ総受注　90,301部"


def test_build_bulk_rows_joins_multiple_hakko_gou_with_slash():
    """同じ案件区分に複数の号が登録されていたら、発行号を「／」でつなぐ。"""
    rows = U.build_bulk_rows(
        receivables=[{"project_id": 1, "amount": 100000, "hakko_gou": "8/21"},
                    {"project_id": 1, "amount": 50000, "hakko_gou": "8/28"}],
        petty=[], payables=[], contract_lines=[], manual=[],
        id2proj={1: "その他"}, id2cat={})
    label, row = rows[0]
    assert row["発行号"] == "8/21／8/28"


# ===== 月次一括生成（依頼②・2026-08-20） =====


def test_build_bulk_rows_one_row_per_project():
    rows = U.build_bulk_rows(
        receivables=[{"project_id": 1, "amount": 847502}],
        petty=[], payables=[], contract_lines=[], manual=[],
        id2proj={1: "京阪南"}, id2cat={})
    assert len(rows) == 1
    label, row = rows[0]
    assert label == "京阪南"
    assert row["売上合計（税込）"] == 847502


def test_build_bulk_rows_splits_advalue_and_labels_each_row():
    rows = U.build_bulk_rows(
        receivables=[{"project_id": 9, "other_label": "8-1", "amount": 544970},
                    {"project_id": 9, "other_label": "8-2", "amount": 214466}],
        petty=[{"project_id": 9, "other_label": "8-1", "category_id": 1, "amount": 6260}],
        payables=[], contract_lines=[], manual=[],
        id2proj={9: "アドバリュー"}, id2cat={1: "駐車場代"})
    labels = {label for label, _ in rows}
    assert labels == {"アドバリュー　8-1", "アドバリュー　8-2"}
    row_81 = next(row for label, row in rows if label == "アドバリュー　8-1")
    assert row_81["交通費（駐車場代含）"] == 6260
    row_82 = next(row for label, row in rows if label == "アドバリュー　8-2")
    assert row_82["交通費（駐車場代含）"] is None
