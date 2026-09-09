"""日付はすべてアプリ内カレンダー（st.date_input）で入れる（2026-08-28 オーナー指示）。

手入力だと必ず表記がズレる。実DBには "2026-07/06"(小口の日付)、
"2026/8/28"(売掛の月度) が入っており、期間の絞り込みは文字列比較なので
静かに範囲から外れる事故が起きうる状態だった。
自由入力の余地を残さず、保存はISO(YYYY-MM-DD / 月度は YYYY-MM)に揃える。
"""
import datetime as _dt
import os
import re

from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(ROOT, "pages")

# 日付を受け取っている入力に付いていそうなラベル。
# 「登録日」「配布日」など、画面に出る日付語をひととおり並べる。
_DATE_WORDS = ("日付", "月度", "年月日", "発行日", "配布日", "期間 開始", "期間 終了",
               "請求書の日")


def _page(db, monkeypatch, mode=None, page="01_経費・買掛・売掛.py"):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    at = AppTest.from_file(os.path.join(PAGES, page), default_timeout=60)
    if mode:
        at.session_state["entry_mode"] = mode
    at.run()
    assert not at.exception
    return at


# ===== 自由入力が残っていないこと（全ページの網羅チェック） =====


def test_no_page_takes_a_date_as_free_text():
    """🔴 これが依頼の本体。日付らしいラベルの text_input が1つも無いこと。
    新しい画面を足したときに手入力へ戻ってしまうのも、ここで気づける。"""
    offenders = []
    for name in sorted(os.listdir(PAGES)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(PAGES, name), encoding="utf-8").read()
        # st.text_input(...) / c1.text_input(...) の第1引数(ラベル)を拾う
        for label in re.findall(r"\.text_input\(\s*\n?\s*[\"']([^\"']+)[\"']", src):
            if any(w in label for w in _DATE_WORDS):
                offenders.append(f"{name}: {label}")
    assert not offenders, "日付が手入力のままの欄がある: " + " / ".join(offenders)


def test_every_page_still_imports_and_runs(tmp_path, monkeypatch):
    """置き換えでどのページも壊れていないこと。"""
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    store.add_distributor("山田", pay_type="歩合", db_path=db)
    for name in sorted(os.listdir(PAGES)):
        if not name.endswith(".py"):
            continue
        at = AppTest.from_file(os.path.join(PAGES, name), default_timeout=60)
        at.run()
        assert not at.exception, f"{name}: {at.exception}"


# ===== 小口 =====


def test_petty_date_is_a_calendar(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    assert at.date_input(key="petty_date").value == _dt.date.today()


def test_petty_saves_an_iso_date(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "小口")
    at.date_input(key="petty_date").set_value(_dt.date(2026, 8, 3))
    at.number_input(key="petty_amount").set_value(500)
    at.button(key="FormSubmitter:petty-登録").click().run()
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-03"


def test_petty_ocr_draft_still_reaches_the_calendar(tmp_path, monkeypatch):
    """🔴 2026-08-28 に直した「AIの下書きがフォームに入らない」を維持すること。
    カレンダーでも読み取った日付が初期値として入る。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    at.session_state["petty_draft"] = {"date": "2015-02-12", "amount": 900,
                                       "item": "駐車場"}
    at.run()
    assert at.date_input(key="petty_date").value == _dt.date(2015, 2, 12)
    assert at.number_input(key="petty_amount").value == 900


def test_petty_ocr_draft_without_a_date_falls_back_to_today(tmp_path, monkeypatch):
    """AIが日付を読めなかったときは今日のまま(カレンダーは空にできない)。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    at.session_state["petty_draft"] = {"date": None, "amount": 900, "item": "駐車場"}
    at.run()
    assert at.date_input(key="petty_date").value == _dt.date.today()
    assert at.number_input(key="petty_amount").value == 900


def test_petty_advalue_week_uses_the_picked_date(tmp_path, monkeypatch):
    """アドバリューの週の月は、カレンダーで選んだ日付から決まること
    (2026-08-27 の依頼⑥の動きを保つ)。"""
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "小口")
    # 案件選択は st.form の外にあり、選んだ直後に画面を再描画してはじめて
    # 「アドバリューの週」欄が現れる(常時表示しない・2026-09-04)。
    at.selectbox(key="petty_proj").set_value("アドバリュー").run()
    at.date_input(key="petty_date").set_value(_dt.date(2026, 10, 2))
    at.number_input(key="petty_amount").set_value(500)
    at.selectbox(key="petty_week").set_value("1週目")
    at.button(key="FormSubmitter:petty-登録").click().run()
    assert store.list_petty_cash(db_path=db)[0]["other_label"] == "10-1"


# ===== 売上（月度） =====


def test_receivable_month_is_a_calendar(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "売上")
    assert at.date_input(key="recv_month").value == _dt.date.today()


def test_receivable_saves_the_month_in_iso(tmp_path, monkeypatch):
    """🔴 実DBに "2026/8/28" が入っていた欄。月度は YYYY-MM で保存する。"""
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "売上")
    at.date_input(key="recv_month").set_value(_dt.date(2026, 8, 28))
    at.number_input(key="recv_amount").set_value(50000)
    at.button(key="FormSubmitter:receivable-登録").click().run()
    rows = store.list_receivables(db_path=db)
    assert len(rows) == 1
    assert rows[0]["month"] == "2026-08"


def test_receivable_advalue_week_uses_the_picked_month(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "売上")
    # 案件選択は st.form の外にあり、選んだ直後に再描画してはじめて週欄が現れる。
    at.selectbox(key="recv_proj").set_value("アドバリュー").run()
    at.date_input(key="recv_month").set_value(_dt.date(2026, 9, 15))
    at.number_input(key="recv_amount").set_value(1000)
    at.selectbox(key="recv_week").set_value("3週目")
    at.button(key="FormSubmitter:receivable-登録").click().run()
    assert store.list_receivables(db_path=db)[0]["other_label"] == "9-3"


# ===== 車両使用履歴 =====


def test_vehicle_date_is_a_calendar(tmp_path, monkeypatch):
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, "車両")
    assert at.date_input(key="vehicle_date").value == _dt.date.today()


def test_vehicle_saves_an_iso_date(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "車両")
    at.date_input(key="vehicle_date").set_value(_dt.date(2026, 8, 3))
    at.button(key="FormSubmitter:vehicle-登録").click().run()
    rows = store.list_vehicle_logs(db_path=db)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-03"


# ===== 買掛（もともとカレンダー。壊していないこと） =====


def test_payable_saves_an_iso_date(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _page(db, monkeypatch, "買掛")
    at.date_input(key="pay_date").set_value(_dt.date(2026, 8, 3))
    at.number_input(key="pay_amount").set_value(1000)
    at.button(key="FormSubmitter:payable-登録").click().run()
    rows = store.list_payables(db_path=db)
    assert rows[0]["date"] == "2026-08-03"
    assert rows[0]["month"] == "2026-08"


# ===== 経理提出出力の期間 =====


def test_accounting_export_period_is_not_free_text(tmp_path, monkeypatch):
    """期間の開始・終了が手入力だった画面。共通の期間フィルタに置き換える。"""
    at = _page(os.path.join(tmp_path, "t.db"), monkeypatch, page="04_経理提出出力.py")
    assert any(p.key == "export_period_pills" for p in at.pills), \
        "経理提出出力に共通の期間フィルタが無い"
    labels = [str(t.label) for t in at.text_input]
    assert not any("期間" in l for l in labels), f"期間の手入力が残っている: {labels}"


def test_accounting_export_defaults_to_everything(tmp_path, monkeypatch):
    """既定は全期間(これまでの「空欄＝絞り込みなし」と同じ)。"""
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    store.add_petty_cash("2020-01-01", None, 100, db_path=db)
    store.add_petty_cash("2026-08-03", None, 200, db_path=db)
    at = AppTest.from_file(os.path.join(PAGES, "04_経理提出出力.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 2


def test_accounting_export_period_filters_rows(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    store.add_petty_cash("2020-01-01", None, 100, db_path=db)
    store.add_petty_cash(_dt.date.today(), None, 200, db_path=db)
    at = AppTest.from_file(os.path.join(PAGES, "04_経理提出出力.py"), default_timeout=60)
    at.session_state["export_period_pills"] = "今月"
    at.run()
    assert not at.exception
    df = at.dataframe[0].value
    assert len(df) == 1 and int(df.iloc[0]["amount"]) == 200
