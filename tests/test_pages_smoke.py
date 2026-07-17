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
