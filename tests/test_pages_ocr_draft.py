"""AIが読み取った値が登録フォームに入らないバグ（2026-08-28・大橋様ご報告）。

現象: 駐車場の領収証をカメラ/アップロードでAI読み取りしたのに、
金額が0円のまま・日付も空のままだった。

真因: 2026-08-27 の依頼⑥対応で、テストから触れるようにフォームの各ウィジェットへ
`key=` を付けた。Streamlit はキー付きウィジェットの値を session_state で持ち、
**一度描画されたあとは `value=` 引数を無視して session_state の値を使う**。
そのため「AIの下書きを value= に渡す」という元の作りが黙って効かなくなった。
（AIの読み取り自体は正常。common/ocr.py は 900円/2015-02-12 を返せている）

対策: 下書きは value= ではなく session_state に直接書く。
"""
import datetime as _dt
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


# ===== 小口（レシート） =====


def test_petty_ocr_draft_lands_in_the_form(tmp_path, monkeypatch):
    """🔴 再現ケースそのもの（駐車場ジャンボ1000の領収証）。
    AIが 900円 / 2015-02-12 を読めたら、フォームにその値が入っていること。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    # 一度描画されたあとに読み取り結果が届く＝実際の操作順(アップロード→ボタン)
    at.session_state["petty_draft"] = {"date": "2015-02-12", "amount": 900,
                                       "item": "駐車場"}
    at.run()
    assert at.date_input(key="petty_date").value == _dt.date(2015, 2, 12)
    assert at.number_input(key="petty_amount").value == 900
    assert at.text_input(key="petty_memo").value == "駐車場"


def test_petty_ocr_draft_can_be_registered_as_read(tmp_path, monkeypatch):
    """読み取った値のまま登録ボタンを押したら、その金額で保存されること
    (画面には出ているのに0円で登録される、を防ぐ)。"""
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "小口")
    at.session_state["petty_draft"] = {"date": "2015-02-12", "amount": 900,
                                       "item": "駐車場"}
    at.run()
    at.button(key="FormSubmitter:petty-登録").click().run()
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1
    assert rows[0]["amount"] == 900
    assert rows[0]["date"] == "2015-02-12"


def test_petty_user_edit_wins_over_the_draft(tmp_path, monkeypatch):
    """AIの値は下書き。人が直したらそちらが優先されること。"""
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "小口")
    at.session_state["petty_draft"] = {"date": "2015-02-12", "amount": 900,
                                       "item": "駐車場"}
    at.run()
    at.number_input(key="petty_amount").set_value(1200)
    at.button(key="FormSubmitter:petty-登録").click().run()
    assert store.list_petty_cash(db_path=db)[0]["amount"] == 1200


def test_petty_form_is_empty_before_any_ocr(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    assert at.date_input(key="petty_date").value == _dt.date.today()
    assert at.number_input(key="petty_amount").value == 0


def test_petty_second_ocr_overwrites_the_first_draft(tmp_path, monkeypatch):
    """🔴 2枚目を読み取ったのに1枚目の金額が残る、を防ぐ。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    at.session_state["petty_draft"] = {"date": "2015-02-12", "amount": 900, "item": "駐車場"}
    at.run()
    at.session_state["petty_draft"] = {"date": "2026-08-01", "amount": 1500, "item": "飲み物"}
    at.run()
    assert at.number_input(key="petty_amount").value == 1500
    assert at.date_input(key="petty_date").value == _dt.date(2026, 8, 1)


# ===== 買掛（請求書） =====


def test_payable_ocr_draft_lands_in_the_form(tmp_path, monkeypatch):
    """買掛も同じ作りなので同じバグを踏んでいる。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "買掛")
    at.session_state["pay_draft"] = {"vendor": "関西電力株式会社", "amount": 16216,
                                     "date": "2026-06-16", "note": "電気代"}
    at.run()
    assert at.text_input(key="pay_vendor").value == "関西電力株式会社"
    assert at.number_input(key="pay_amount").value == 16216
    assert at.date_input(key="pay_date").value == _dt.date(2026, 6, 16)
    assert at.text_input(key="pay_note").value == "電気代"


def test_payable_ocr_draft_can_be_registered_as_read(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "買掛")
    at.session_state["pay_draft"] = {"vendor": "関西電力株式会社", "amount": 16216,
                                     "date": "2026-06-16", "note": "電気代"}
    at.run()
    at.button(key="FormSubmitter:payable-登録").click().run()
    rows = store.list_payables(db_path=db)
    assert len(rows) == 1
    assert rows[0]["amount"] == 16216
    assert rows[0]["vendor_name"] == "関西電力株式会社"
    assert rows[0]["date"] == "2026-06-16"


def test_payable_draft_without_a_date_keeps_today(tmp_path, monkeypatch):
    """AIが日付を読めなかったときは今日のまま(空にして落とさない)。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "買掛")
    at.session_state["pay_draft"] = {"vendor": "取引先", "amount": 100,
                                     "date": None, "note": None}
    at.run()
    assert at.date_input(key="pay_date").value == _dt.date.today()
