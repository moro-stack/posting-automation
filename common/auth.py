import os

SESSION_KEY_AUTHENTICATED = "authenticated"
SESSION_KEY_FAILED_ATTEMPTS = "failed_attempts"
SESSION_KEY_LOCKED_UNTIL = "locked_until"

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30


def get_app_password() -> str:
    password = os.environ.get("APP_PASSWORD")
    if not password:
        raise RuntimeError("APP_PASSWORD環境変数が設定されていません")
    return password


def is_locked_out(session_state: dict, now: float) -> bool:
    locked_until = session_state.get(SESSION_KEY_LOCKED_UNTIL, 0)
    return now < locked_until


def check_password(input_password: str, correct_password: str, session_state: dict, now: float) -> bool:
    if input_password == correct_password:
        session_state[SESSION_KEY_AUTHENTICATED] = True
        session_state[SESSION_KEY_FAILED_ATTEMPTS] = 0
        return True

    failed_attempts = session_state.get(SESSION_KEY_FAILED_ATTEMPTS, 0) + 1
    session_state[SESSION_KEY_FAILED_ATTEMPTS] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        session_state[SESSION_KEY_LOCKED_UNTIL] = now + LOCKOUT_SECONDS
        session_state[SESSION_KEY_FAILED_ATTEMPTS] = 0
    return False


def is_authenticated(session_state: dict) -> bool:
    return bool(session_state.get(SESSION_KEY_AUTHENTICATED, False))


def attempt_login(input_password: str, session_state: dict, now: float) -> bool:
    """環境変数のパスワードと照合してログインを試みる。成功で True。"""
    return check_password(input_password, get_app_password(), session_state, now)


def require_auth() -> None:
    import streamlit as st

    if not is_authenticated(st.session_state):
        st.error("ログインが必要です。トップページからログインしてください。")
        st.stop()
