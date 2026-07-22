import pytest
from common import atehagi as A


def test_area5_extracts_last5_digits():
    assert A.area5(10101) == "10101"
    assert A.area5("10101") == "10101"
    assert A.area5("X-44408") == "44408"      # 数字以外を除去
    assert A.area5("  46501 ") == "46501"


def test_chiku_name_kita_rule():
    assert A.chiku_name(A.KEIHAN_KITA, "10101") == "枚方・交野"   # 先頭1
    assert A.chiku_name(A.KEIHAN_KITA, "30101") == "枚方・交野"   # 先頭3
    assert A.chiku_name(A.KEIHAN_KITA, "44408") == "寝屋川・枚方"  # 先頭4
    assert A.chiku_name(A.KEIHAN_KITA, 46501) == "寝屋川・枚方"    # 先頭5扱いでなく4


def test_chiku_name_minami_not_configured():
    with pytest.raises(NotImplementedError):
        A.chiku_name(A.KEIHAN_MINAMI, "10101")
