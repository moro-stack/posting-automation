"""pills/segmented_control の選択中・非選択の見た目のコントラストを固定する。

2026-08-20 オーナー指摘: 号別明細の案件切り替え(pills)や小口/買掛/売掛の
モード切り替え(segmented_control)が、隣のボタンを押し間違えそうなくらい
見分けにくい。未選択をグレーに沈め、選択中を色+影ではっきり浮かせる。
"""
from common.ui import _STYLE


def test_segmented_control_unselected_is_greyed_out():
    assert 'stBaseButton-segmented_control"]{' in _STYLE
    assert "#eef1f4" in _STYLE  # 未選択のグレー地


def test_segmented_control_active_is_emphasized():
    assert 'stBaseButton-segmented_controlActive"]{' in _STYLE
    assert "box-shadow" in _STYLE


def test_pills_unselected_is_greyed_out():
    assert 'stBaseButton-pills"]{' in _STYLE
    assert "#eef1f4" in _STYLE


def test_pills_active_is_emphasized():
    assert 'stBaseButton-pillsActive"]{' in _STYLE
