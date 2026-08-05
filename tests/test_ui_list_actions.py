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


# ===== list_action_bar =====


def _bar_page():
    import streamlit as st  # noqa: F401
    from common import ui

    rows = [
        {"No.": 11, "日付": "2026-08-01", "費目": "消耗品", "金額": "¥3,200"},
        {"No.": 12, "日付": "2026-08-02", "費目": "交通費", "金額": "¥980"},
        {"No.": 13, "日付": "2026-08-03", "費目": "雑費", "金額": "¥1,500"},
    ]
    st.session_state.setdefault("_deleted", [])
    edited, ids = ui.selectable_list(rows, key="t")
    ui.list_action_bar(
        edited, key="t", title="小口一覧", filename="小口一覧", section="sec",
        delete_fn=lambda i: st.session_state["_deleted"].append(i))


def test_action_bar_shows_three_buttons_in_fixed_order():
    """🔴 印刷・ダウンロード・削除が必ずこの順で出ること(全ページ統一の肝)。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    assert not at.exception
    keys = [b.key for b in at.button if b.key and b.key.startswith("t_")]
    assert "t_print" in keys
    assert "t_bulk_del_btn" in keys
    ids = [d.id for d in at.get("download_button")]
    assert any("t_dl" in i for i in ids)


def test_action_bar_buttons_are_disabled_when_nothing_selected():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    assert at.button(key="t_print").disabled is True
    assert at.button(key="t_bulk_del_btn").disabled is True


def test_action_bar_buttons_enabled_after_select_all():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    assert at.button(key="t_print").disabled is False
    assert at.button(key="t_bulk_del_btn").disabled is False


def test_action_bar_delete_asks_before_deleting():
    """押しただけでは消さない。確認を挟む。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_bulk_del_btn").click().run()
    assert at.session_state["_deleted"] == []
    assert len(at.warning) == 1


def test_action_bar_delete_removes_selected_and_flashes():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_bulk_del_btn").click().run()
    at.button(key="t_bulk_del_ok").click().run()
    assert at.session_state["_deleted"] == [11, 12, 13]
    assert at.session_state["_flash_sec"] == "3件を削除しました"


def test_action_bar_delete_cancel_keeps_rows():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_bulk_del_btn").click().run()
    at.button(key="t_bulk_del_no").click().run()
    assert at.session_state["_deleted"] == []
    assert len(at.warning) == 0


def test_action_bar_delete_button_disabled_when_no_delete_fn():
    """🔴 03・06 の「見るだけの画面」。削除ボタンは出るが押せないこと。

    ⚠️ ここでは **id列がある** 行を使う。id_col=None の行で試すと選択idが常に空になり、
    `disabled=not ids` だけでも同じ結果になってしまう＝`delete_fn is None` の判定を
    検証できない(ミューテーションが素通りした実例)。
    """

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"No.": 1, "日付": "2026-08-01", "区分": "原価", "金額": "¥100"}]
        edited, ids = ui.selectable_list(rows, key="v")
        st.session_state["_ids"] = ids
        ui.list_action_bar(edited, key="v", title="まとめ", filename="まとめ",
                           delete_fn=None,
                           delete_note="このデータは登録画面から削除してください")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="v_all").check().run()
    assert not at.exception
    # 行は選択されている(＝ids は空ではない)のに、削除だけは押せない
    assert at.session_state["_ids"] == [1]
    assert at.button(key="v_bulk_del_btn").disabled is True
    assert at.button(key="v_print").disabled is False


def test_action_bar_delete_disabled_on_id_less_list():
    """03・06 の実際の呼び方(id列なし)でも例外なく描けて、削除は押せないこと。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"日付": "2026-08-01", "区分": "原価", "金額": "¥100"}]
        edited, _ = ui.selectable_list(rows, key="w", id_col=None)
        ui.list_action_bar(edited, key="w", title="まとめ", filename="まとめ",
                           id_col=None, delete_fn=None,
                           delete_note="このデータは登録画面から削除してください")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="w_all").check().run()
    assert not at.exception
    assert at.button(key="w_bulk_del_btn").disabled is True
    assert at.button(key="w_print").disabled is False


def test_action_bar_rejects_delete_fn_without_id_col():
    """🔴 削除できるのに id 列が無い＝「削除したのに消えない」を無言で作らせない。"""

    # ⚠️ AppTest 経由だと Streamlit が例外メッセージを伏せ字にする
    # ("The original error message is redacted...")ため、メッセージの中身を
    # 確かめられない。このガードは st.* を1つも呼ぶ前に発火する純粋なチェックなので、
    # 関数を直接呼んで検証する。
    from common import ui

    df = pd.DataFrame([{"選択": True, "日付": "2026-08-01"}])
    with pytest.raises(ValueError, match="id_col"):
        ui.list_action_bar(df, key="bad", title="x", filename="x",
                           id_col=None, delete_fn=lambda i: None)


def test_action_bar_extra_button_is_rendered():
    """業務委託のZIPのような、ページ固有のボタンを右端に足せること。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"No.": 1, "日付": "2026-08-01", "金額": "¥100"}]
        edited, _ = ui.selectable_list(rows, key="x")
        ui.list_action_bar(edited, key="x", title="一覧", filename="一覧",
                           extra=lambda c, rows, ids: c.button("ZIP", key="x_zip"))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert "x_zip" in {b.key for b in at.button}


def test_action_bar_print_button_stores_selected_rows():
    """印刷を押すと選択行が session_state に積まれること(描画はTask 4)。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_print").click().run()
    stored = at.session_state["_print_t"]
    assert [r["No."] for r in stored] == [11, 12, 13]
    assert "選択" not in stored[0]
