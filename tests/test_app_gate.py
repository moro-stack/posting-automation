import os
from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")


def test_login_gate_blocks_when_password_set_and_not_authenticated(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", os.path.join(tmp_path, "a.db"))
    monkeypatch.setenv("APP_PASSWORD", "demo123")
    monkeypatch.setenv("DEMO_MODE", "1")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    # 未認証: パスワード入力が出る
    assert any(getattr(i, "type", "") == "password" or i.label == "パスワード" for i in at.text_input)


def test_login_gate_absent_without_password(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", os.path.join(tmp_path, "b.db"))
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    # APP_PASSWORD無し=ログイン不要(パスワード入力は出ない)
    assert not any(i.label == "パスワード" for i in at.text_input)
