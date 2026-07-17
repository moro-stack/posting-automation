"""画面のスモークテスト。Streamlit AppTest でページが例外なく描画されることを見る。
実DBを触らないよう、各テストで POSTING_DB_PATH に一時DBを指す。"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = os.path.join(tmp_path, "smoke.db")
    monkeypatch.setenv("POSTING_DB_PATH", path)
    store.init_db(path)
    store.seed_masters(db_path=path)
    return path


def _run(page):
    at = AppTest.from_file(os.path.join(ROOT, "pages", page), default_timeout=30)
    at.run()
    return at


def test_confirm_delete_shows_confirmation_before_running(db):
    """confirm_delete は押しただけでは実行せず、確認を出す。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("called", 0)
        ui.confirm_delete(key="t1", detail="7/17 ／ 駐車場代 ／ ¥1,500",
                          on_confirm=lambda: st.session_state.__setitem__(
                              "called", st.session_state["called"] + 1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert any(b.label == "削除" for b in at.button)
    at.button(key="t1_btn").click().run()
    # 確認が出て、まだ実行されていない
    assert at.session_state["called"] == 0
    assert len(at.warning) == 1
    assert any(b.label == "はい、削除する" for b in at.button)
    assert any(c.value == "7/17 ／ 駐車場代 ／ ¥1,500" for c in at.caption)


def test_confirm_delete_runs_on_confirm(db):
    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("called", 0)
        ui.confirm_delete(key="t2", detail="対象",
                          on_confirm=lambda: st.session_state.__setitem__(
                              "called", st.session_state["called"] + 1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t2_btn").click().run()
    at.button(key="t2_ok").click().run()
    assert at.session_state["called"] == 1


def test_confirm_delete_cancel_does_not_run(db):
    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("called", 0)
        ui.confirm_delete(key="t3", detail="対象",
                          on_confirm=lambda: st.session_state.__setitem__(
                              "called", st.session_state["called"] + 1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t3_btn").click().run()
    at.button(key="t3_no").click().run()
    assert at.session_state["called"] == 0
    assert len(at.warning) == 0


def test_confirm_delete_multiple_rows_do_not_interfere(db):
    """1つの画面に confirm_delete を3行分並べたとき、1行だけ操作しても他行に影響しないこと。

    2026-07-14に実際に起きたCriticalバグ（固定keyでsession_stateが保持され、
    編集フォームが別の行を上書きした）と同型のリグレッションを防ぐ。
    confirm_delete内部の `pending = f"_del_pending_{key}"` を固定値
    `"_del_pending"` に変えると、このテストが落ちることを確認済み。
    """

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("deleted", [])
        for rid in (1, 2, 3):
            ui.confirm_delete(
                key=f"del_{rid}", detail=f"行{rid}",
                on_confirm=(lambda rid=rid: st.session_state["deleted"].append(rid)),
            )

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()

    # 2行目だけ削除ボタンを押す
    at.button(key="del_2_btn").click().run()

    # 2行目の確認UIだけが出て、1行目・3行目は元の削除ボタンのままであること
    assert len(at.warning) == 1
    assert at.button(key="del_1_btn").label == "削除"
    assert at.button(key="del_3_btn").label == "削除"
    assert not any(b.key == "del_1_ok" for b in at.button)
    assert not any(b.key == "del_3_ok" for b in at.button)
    assert any(b.key == "del_2_ok" for b in at.button)

    # 2行目を確定する
    at.button(key="del_2_ok").click().run()

    # 消えたのは2行目だけ
    assert at.session_state["deleted"] == [2]
    # 1行目・3行目は未確定のまま(削除ボタンに戻っている)
    assert at.button(key="del_1_btn").label == "削除"
    assert at.button(key="del_3_btn").label == "削除"


def test_confirm_delete_flashes_success_message_on_confirm(db):
    """確定後にflash(success)で「削除しました」を出す(オーナー要望のアナウンス)。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        ui.confirm_delete(key="t4", detail="対象", on_confirm=lambda: None)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t4_btn").click().run()
    at.button(key="t4_ok").click().run()
    assert at.session_state["_flash"] == "削除しました"


def test_confirm_delete_flashes_custom_success_message(db):
    """successを渡した場合はそのメッセージがflashされること
    (Task 10のマスタで「停止中にしました」を使うため)。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        ui.confirm_delete(key="t5", detail="対象", on_confirm=lambda: None,
                          success="停止中にしました")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t5_btn").click().run()
    at.button(key="t5_ok").click().run()
    assert at.session_state["_flash"] == "停止中にしました"
