import os
from streamlit.testing.v1 import AppTest
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE01 = os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py")


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
    from common.ui import selectable_list, list_action_bar, apply_app_style
    apply_app_style()
    st.session_state.setdefault("_d", [])
    edited, _ = selectable_list([{"No.": 1, "金額": "¥100"}], key="bd")
    list_action_bar(edited, key="bd", title="一覧", filename="一覧", section="t",
                    delete_fn=lambda i: st.session_state["_d"].append(i))


def test_bulk_delete_uses_hai_iie():
    """まとめて削除の確認も「はい/いいえ」で揃えること(統一部品 list_action_bar 側)。"""
    at = AppTest.from_function(_bulk_page).run()
    at.checkbox(key="bd_all").check().run()
    at.button(key="bd_bulk_del_btn").click().run()
    labels = [b.label for b in at.button]
    assert "はい" in labels and "いいえ" in labels


# ===== ①: pages/01 の重複チェック確認(petty_ok/petty_no, pay_ok/pay_no, recv_ok/recv_no) =====
# 「はい、登録する」等への先祖返りをここで捕まえる(revert すると本テストが落ちることを確認済み)。

def _seed(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)


def test_petty_pending_confirm_uses_hai_iie(tmp_path, monkeypatch):
    """小口の重複確認(petty_pending)は既定モード(小口)のまま出せるので radio 操作は不要。"""
    db = os.path.join(tmp_path, "t.db")
    _seed(db, monkeypatch)
    at = AppTest.from_file(PAGE01, default_timeout=30)
    at.session_state["petty_pending"] = {
        "date": "2026-07-01", "category_id": None, "amount": 500,
        "project_id": None, "memo": "test", "source": "manual",
        "other_label": None, "distributor_id": None,
    }
    at.run()
    assert not at.exception
    assert at.button(key="petty_ok").label == "はい"
    assert at.button(key="petty_no").label == "いいえ"


def test_pay_pending_confirm_uses_hai_iie(tmp_path, monkeypatch):
    """買掛の重複確認(pay_pending)。mode の radio を「買掛」に切り替えてから出す。"""
    db = os.path.join(tmp_path, "t.db")
    _seed(db, monkeypatch)
    at = AppTest.from_file(PAGE01, default_timeout=30)
    at.run()
    at.segmented_control[0].set_value("買掛").run()
    at.session_state["pay_pending"] = {
        "date": "2026-07-01", "vendor_name": "テスト商事", "amount": 1000,
        "original_status": "原本あり", "note": None, "source": "manual",
        "project_id": None, "other_label": None,
    }
    at.run()
    assert not at.exception
    assert at.button(key="pay_ok").label == "はい"
    assert at.button(key="pay_no").label == "いいえ"


def test_recv_pending_confirm_uses_hai_iie(tmp_path, monkeypatch):
    """売上の重複確認(recv_pending)。mode の radio を「売上」に切り替えてから出す。"""
    db = os.path.join(tmp_path, "t.db")
    _seed(db, monkeypatch)
    at = AppTest.from_file(PAGE01, default_timeout=30)
    at.run()
    at.segmented_control[0].set_value("売上").run()
    at.session_state["recv_pending"] = {
        "month": "2026-07", "client_id": None, "amount": 2000,
        "note": None, "project_id": None, "other_label": None,
    }
    at.run()
    assert not at.exception
    assert at.button(key="recv_ok").label == "はい"
    assert at.button(key="recv_no").label == "いいえ"
