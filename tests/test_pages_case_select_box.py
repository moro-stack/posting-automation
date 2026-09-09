"""小口・買掛・売上の「案件」選択も、車両登録と同じ見やすいデザインにする
（2026-09-09大橋様ご依頼）。

・ラベルは「案件(任意)」ではなく「案件」
・週選択／案件区分欄は案件のすぐ下に表示する(車両と同じ・formの奥に埋めない)
"""
import os

from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _page(db, monkeypatch, mode):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"),
                           default_timeout=60)
    at.session_state["entry_mode"] = mode
    at.run()
    assert not at.exception
    return at


def test_petty_project_label_has_no_annai_suffix(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    assert at.selectbox(key="petty_proj").label == "案件"


def test_pay_project_label_has_no_annai_suffix(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "買掛")
    assert at.selectbox(key="pay_proj").label == "案件"


def test_recv_project_label_has_no_annai_suffix(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "売上")
    assert at.selectbox(key="recv_proj").label == "案件"


def test_petty_week_select_appears_right_below_the_project_dropdown(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    at.selectbox(key="petty_proj").set_value("アドバリュー").run()
    keys_in_order = [w.key for w in at.selectbox]
    assert keys_in_order.index("petty_week") == keys_in_order.index("petty_proj") + 1


def test_pay_week_select_appears_right_below_the_project_dropdown(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "買掛")
    at.selectbox(key="pay_proj").set_value("アドバリュー").run()
    keys_in_order = [w.key for w in at.selectbox]
    assert keys_in_order.index("pay_week") == keys_in_order.index("pay_proj") + 1


def test_recv_week_select_appears_right_below_the_project_dropdown(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "売上")
    at.selectbox(key="recv_proj").set_value("アドバリュー").run()
    keys_in_order = [w.key for w in at.selectbox]
    assert keys_in_order.index("recv_week") == keys_in_order.index("recv_proj") + 1
