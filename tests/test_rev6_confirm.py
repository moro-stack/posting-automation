from streamlit.testing.v1 import AppTest


def _confirm_page():
    import streamlit as st
    from common.ui import confirm_delete, apply_app_style
    apply_app_style()
    st.session_state.setdefault("_c", 0)
    confirm_delete(key="t", detail="x",
                   on_confirm=lambda: st.session_state.__setitem__("_c", 1))


def test_confirm_delete_uses_hai_iie():
    at = AppTest.from_function(_confirm_page).run()
    at.button(key="t_btn").click().run()          # 確認を出す
    labels = [b.label for b in at.button]
    assert "はい" in labels and "いいえ" in labels
    assert "はい、削除する" not in labels and "やめる" not in labels


def _bulk_page():
    import streamlit as st
    from common.ui import bulk_delete_action, apply_app_style
    apply_app_style()
    st.session_state.setdefault("_d", [])
    bulk_delete_action([1], delete_fn=lambda i: st.session_state["_d"].append(i),
                       section="t", key="bd")


def test_bulk_delete_uses_hai_iie():
    at = AppTest.from_function(_bulk_page).run()
    at.button(key="bd_btn").click().run()
    labels = [b.label for b in at.button]
    assert "はい" in labels and "いいえ" in labels
