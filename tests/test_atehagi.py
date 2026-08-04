import pytest
from common import atehagi as A


def test_area_code_normalizes_digits():
    assert A.area_code(10101) == "10101"
    assert A.area_code("10101") == "10101"
    assert A.area_code("X-44408") == "44408"      # 数字以外を除去
    assert A.area_code("  46501 ") == "46501"
    assert A.area_code("911001") == "911001"      # 南版6桁は落とさない
    assert A.area_code("1234567") == "234567"     # 7桁以上の異常値のみ末尾6桁


def test_chiku_name_kita_rule():
    assert A.chiku_name(A.KEIHAN_KITA, "10101") == "枚方・交野"   # 先頭1
    assert A.chiku_name(A.KEIHAN_KITA, "30101") == "枚方・交野"   # 先頭3
    assert A.chiku_name(A.KEIHAN_KITA, "44408") == "寝屋川・枚方"  # 先頭4
    assert A.chiku_name(A.KEIHAN_KITA, 46501) == "寝屋川・枚方"    # 先頭5扱いでなく4


def test_chiku_name_minami_is_fixed():
    # 南版は担当地区コードによらず「守口・門真」で固定（関西ぱど 2026-07-23）
    assert A.chiku_name(A.KEIHAN_MINAMI, "911001") == "守口・門真"


def test_chiku_name_unknown_version_raises():
    with pytest.raises(ValueError):
        A.chiku_name("西", "10101")


def _sample_table():
    # 実データを模した最小の合成テーブル（表題行＋ヘッダー行＋データ4行）
    header = ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所",
              "電話番号", "担当地区", "チラシコード", "配送物", "配布部数", "配送備考",
              "町界名", "街区（番地）名称", "受注種別", "チラシサイズ"]
    return [
        ["配送管理表", "2026-06-26", "(1248号)", "作成日:2026/06/18"],
        header,
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, None,
         "01 ぱど", 224, " ", "大住ヶ丘", "1丁目", None, None],
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, 28,
         "サンプル生協", 224, " ", "大住ヶ丘", "1丁目", "全戸配布(チラシ)", "Ｂ４(折済)"],
        ["2026-06-26", 1248, 0, None, None, "テスト花子", None, None, 46501, None,
         "04 ぱど", 436, " ", "香里園", "1丁目", None, None],
        [None] * 17,  # 空行は無視される
    ]


def test_rows_from_table_normalizes():
    rows = A.rows_from_table(_sample_table())
    assert len(rows) == 3
    assert rows[0] == {
        "padonna": "テスト太郎", "chiku": 10101, "haisoubutsu": "01 ぱど",
        "busuu": 224, "size": "", "gou": 1248, "haifubi": "2026-06-26",
    }
    assert rows[1]["size"] == "Ｂ４(折済)"
    assert rows[1]["busuu"] == 224
    assert rows[2]["chiku"] == 46501


def test_rows_from_table_no_header_raises():
    with pytest.raises(ValueError):
        A.rows_from_table([["a", "b"], ["c", "d"]])


def test_group_by_chiku_preserves_order_and_counts():
    rows = A.rows_from_table(_sample_table())
    groups = A.group_by_chiku(rows)
    assert list(groups.keys()) == ["10101", "46501"]     # 出現順
    assert len(groups["10101"]) == 2
    assert A.chirashi_count(groups["10101"]) == 1        # サンプル生協のみサイズ有り
    assert A.chirashi_count(groups["46501"]) == 0        # 04 ぱど のみ・サイズ無し
