"""売上登録に会議用売上表の内訳(発行号・ぱど/チラシ/仕分けの部数・売上税抜・その他)を
追加する（2026-09-04大橋様ご依頼）。分かる分だけ入れれば良い任意項目で、
月次売上表の一括生成時にそのまま反映される。
"""
import datetime as _dt
import os

from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _receivable_page(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"),
                           default_timeout=60)
    at.session_state["entry_mode"] = "売上"
    at.run()
    assert not at.exception
    return at


def test_receivable_form_offers_the_breakdown_fields(tmp_path, monkeypatch):
    at = _receivable_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    keys = {t.key for t in at.text_input} | {n.key for n in at.number_input}
    for key in ("recv_hakko_gou", "recv_pado_busuu", "recv_pado_uriage",
               "recv_chirashi_busuu", "recv_chirashi_uriage",
               "recv_shiwake_busuu", "recv_shiwake_uriage", "recv_sonota_uriage"):
        assert key in keys, f"{key} が無い"


def test_receivable_registration_saves_the_breakdown(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _receivable_page(db, monkeypatch)
    at.date_input(key="recv_month").set_value(_dt.date(2026, 8, 21))
    at.number_input(key="recv_amount").set_value(847502)
    at.text_input(key="recv_hakko_gou").set_value("8/21")
    at.number_input(key="recv_pado_busuu").set_value(69443)
    at.number_input(key="recv_pado_uriage").set_value(590266)
    at.number_input(key="recv_chirashi_busuu").set_value(74404)
    at.number_input(key="recv_chirashi_uriage").set_value(171129)
    at.number_input(key="recv_shiwake_busuu").set_value(15897)
    at.number_input(key="recv_shiwake_uriage").set_value(9061)
    at.button(key="FormSubmitter:receivable-登録").click().run()
    assert not at.exception
    row = store.list_receivables(db_path=db)[0]
    assert row["hakko_gou"] == "8/21"
    assert row["pado_busuu"] == 69443
    assert row["pado_uriage"] == 590266
    assert row["chirashi_busuu"] == 74404
    assert row["chirashi_uriage"] == 171129
    assert row["shiwake_busuu"] == 15897
    assert row["shiwake_uriage"] == 9061


def test_receivable_registration_without_breakdown_leaves_it_blank(tmp_path, monkeypatch):
    """内訳を入れなくても今までどおり登録できる(全部任意項目)。"""
    db = os.path.join(tmp_path, "t.db")
    at = _receivable_page(db, monkeypatch)
    at.number_input(key="recv_amount").set_value(1000)
    at.button(key="FormSubmitter:receivable-登録").click().run()
    assert not at.exception
    row = store.list_receivables(db_path=db)[0]
    assert row["hakko_gou"] is None
    assert row["pado_busuu"] is None
