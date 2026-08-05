"""一覧の共通操作部品(selectable_list / list_action_bar)のテスト。
実DBに触れないよう、AppTest.from_function で部品だけを描画して見る。"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# ⚠️ AppTest.from_function は渡した関数を新しいモジュールの名前空間で実行するため、
# このファイルのモジュール変数は関数の中から見えない(NameError になる)。
# 画面関数の中で使う値は、必ずその関数の内側で作ること。
_ROWS = [
    {"No.": 11, "日付": "2026-08-01", "費目": "消耗品", "金額": "¥3,200"},
    {"No.": 12, "日付": "2026-08-02", "費目": "交通費", "金額": "¥980"},
    {"No.": 13, "日付": "2026-08-03", "費目": "雑費", "金額": "¥1,500"},
]


def _rows():
    """画面関数の内側で使う行データ(モジュール変数は参照できないため関数内で作る)。"""
    return [
        {"No.": 11, "日付": "2026-08-01", "費目": "消耗品", "金額": "¥3,200"},
        {"No.": 12, "日付": "2026-08-02", "費目": "交通費", "金額": "¥980"},
        {"No.": 13, "日付": "2026-08-03", "費目": "雑費", "金額": "¥1,500"},
    ]


def _list_page():
    import streamlit as st  # noqa: F401
    from common import ui

    rows = [
        {"No.": 11, "日付": "2026-08-01", "費目": "消耗品", "金額": "¥3,200"},
        {"No.": 12, "日付": "2026-08-02", "費目": "交通費", "金額": "¥980"},
        {"No.": 13, "日付": "2026-08-03", "費目": "雑費", "金額": "¥1,500"},
    ]
    edited, ids = ui.selectable_list(rows, key="t")
    st.session_state["_ids"] = ids


def test_selectable_list_starts_with_nothing_selected():
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state["_ids"] == []


def test_selectable_list_has_select_all_checkbox():
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    assert "t_all" in {c.key for c in at.checkbox}


def test_selectable_list_select_all_selects_every_row():
    """🔴 「すべて選択」を押すと全行のidが返ること。"""
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    assert not at.exception
    assert at.session_state["_ids"] == [11, 12, 13]


def test_selectable_list_unselect_all_clears_selection():
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.checkbox(key="t_all").uncheck().run()
    assert at.session_state["_ids"] == []


def test_selectable_list_individual_checkbox_selects_one_row():
    """チェック列で1行だけ選べること(data_editorの状態を直接セットして再現)。"""
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    at.session_state["t_select_0"] = {
        "edited_rows": {1: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.run()
    assert at.session_state["_ids"] == [12]


def test_selectable_list_editor_key_changes_with_select_all():
    """🔴 全選択の反映は data_editor の key を切り替えて再初期化することで行う。
    key が固定だと、前回の編集状態が残って「すべて選択」が効かない。"""
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    assert "t_select_0" in at.session_state
    at.checkbox(key="t_all").check().run()
    assert "t_select_1" in at.session_state


def test_selectable_list_without_id_column_returns_empty_ids():
    """03・06の集計行はid列を持たない。id_col=None で呼べて、選択idは空になる。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"日付": "2026-08-01", "区分": "原価", "金額": "¥100"}]
        edited, ids = ui.selectable_list(rows, key="n", id_col=None)
        st.session_state["_ids"] = ids
        st.session_state["_cols"] = list(edited.columns)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="n_all").check().run()
    assert not at.exception
    assert at.session_state["_ids"] == []
    assert at.session_state["_cols"][0] == "選択"


def test_selectable_list_empty_rows_does_not_crash():
    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        edited, ids = ui.selectable_list([], key="e")
        st.session_state["_ids"] = ids
        st.session_state["_empty"] = bool(edited.empty)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state["_ids"] == []
    assert at.session_state["_empty"] is True
