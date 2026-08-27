"""アドバリューの週次区分を登録画面で必須にする（依頼⑥・2026-08-27 大橋様）。

・案件が「アドバリュー」なら週(1週目〜5週目)を選ばないと登録できない
・保存される区分は伝票の日付の月と組み合わせた "8-1" 形式(過去データと同じ形)
・9月の伝票なら "9-1"、10月なら "10-1"(月をまたぐと自動で繰り上がる)
"""
import os

from streamlit.testing.v1 import AppTest

from common import advalue
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _at(db, monkeypatch, mode):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"),
                           default_timeout=60)
    at.session_state["entry_mode"] = mode
    at.run()
    assert not at.exception
    return at


def _submit(at, form="petty"):
    """フォームの登録ボタンを押す。AppTest では key が
    "FormSubmitter:<フォーム名>-<ラベル>" になる。"""
    at.button(key=f"FormSubmitter:{form}-登録").click().run()
    return at


# ===== 小口 =====


def _petty(at, *, date, proj, week=None, amount=1000):
    at.text_input(key="petty_date").set_value(date)
    at.selectbox(key="petty_proj").set_value(proj)
    at.number_input(key="petty_amount").set_value(amount)
    if week is not None:
        at.selectbox(key="petty_week").set_value(week)
    return at


def test_petty_advalue_without_a_week_is_refused(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date="2026-08-04", proj="アドバリュー")
    _submit(at)
    assert any("週" in str(e.value) for e in at.error), "週の未選択が知らされていない"
    assert store.list_petty_cash(db_path=db) == [], "週を選ばずに登録されてしまった"


def test_petty_advalue_with_a_week_saves_the_month_dash_week_label(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date="2026-08-04", proj="アドバリュー", week="1週目")
    _submit(at)
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1
    assert rows[0]["other_label"] == "8-1"


def test_petty_advalue_rolls_the_month_over_automatically(tmp_path, monkeypatch):
    """🔴 依頼の肝: 9月の伝票なら 9-1、10月なら 10-1。選択肢を作り直さなくても
    伝票の日付から月が決まる。"""
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date="2026-10-02", proj="アドバリュー", week="1週目")
    _submit(at)
    assert store.list_petty_cash(db_path=db)[0]["other_label"] == "10-1"


def test_petty_non_advalue_project_is_unaffected_by_the_week(tmp_path, monkeypatch):
    """他の案件は週を選んでいなくても今までどおり登録できる。"""
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date="2026-08-04", proj="関西ぱど：京阪北版")
    _submit(at)
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1 and rows[0]["other_label"] is None


def test_petty_sonota_still_uses_the_free_text(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date="2026-08-04", proj="その他")
    at.text_input(key="petty_other").set_value("買取専科")
    _submit(at)
    assert store.list_petty_cash(db_path=db)[0]["other_label"] == "買取専科"


# ===== 売掛（売上）=====


def test_receivable_advalue_without_a_week_is_refused(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "売掛")
    at.text_input(key="recv_month").set_value("2026-09")
    at.selectbox(key="recv_proj").set_value("アドバリュー")
    at.number_input(key="recv_amount").set_value(50000)
    _submit(at, "receivable")
    assert any("週" in str(e.value) for e in at.error)
    assert store.list_receivables(db_path=db) == []


def test_receivable_advalue_uses_the_month_of_the_gedo(tmp_path, monkeypatch):
    """売掛は日付ではなく月度(2026-09)を持つ。そこから月を取ること。"""
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "売掛")
    at.text_input(key="recv_month").set_value("2026-09")
    at.selectbox(key="recv_proj").set_value("アドバリュー")
    at.number_input(key="recv_amount").set_value(50000)
    at.selectbox(key="recv_week").set_value("3週目")
    _submit(at, "receivable")
    assert store.list_receivables(db_path=db)[0]["other_label"] == "9-3"


# ===== 買掛 =====


def test_payable_advalue_without_a_week_is_refused(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "買掛")
    at.selectbox(key="pay_proj").set_value("アドバリュー")
    at.number_input(key="pay_amount").set_value(3000)
    _submit(at, "payable")
    assert any("週" in str(e.value) for e in at.error)
    assert store.list_payables(db_path=db) == []


def test_the_week_options_offered_on_screen_are_month_independent(tmp_path, monkeypatch):
    """選択肢そのものは月を持たない(だから9月・10月になっても作り直しが要らない)。"""
    at = _at(os.path.join(tmp_path, "t.db"), monkeypatch, "小口")
    options = list(at.selectbox(key="petty_week").options)
    assert options == [advalue.WEEK_PLACEHOLDER] + list(advalue.WEEK_CHOICES)


# ===== 号別明細で週ごとに見る（依頼⑥の後半） =====


def _seed_advalue_weeks(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    pid = next(p["id"] for p in store.list_projects(db_path=db)
               if p["name"] == "アドバリュー")
    cat = store.list_expense_categories(db_path=db)[0]["id"]
    # わざと月をまたいだ順序で入れる(並べ替えが効いているか見るため)
    for label, amount in [("10-1", 100), ("8-2", 200), ("9-1", 300), ("8-1", 400)]:
        store.add_petty_cash("2026-08-04", cat, amount, project_id=pid,
                             other_label=label, db_path=db)
    return pid


def _issue_page(db):
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"),
                           default_timeout=60)
    at.session_state["proj_pills"] = "アドバリュー"
    at.run()
    assert not at.exception
    return at


def test_issue_page_lists_advalue_weeks_in_month_then_week_order(tmp_path, monkeypatch):
    """🔴 文字列順のままだと 10-1 が 8-1 より前に来る。月→週で並べ直すこと。"""
    db = os.path.join(tmp_path, "t.db")
    _seed_advalue_weeks(db, monkeypatch)
    at = _issue_page(db)
    pills = at.pills(key="adv_sub_pills")
    assert list(pills.options) == ["全体", "8-1", "8-2", "9-1", "10-1"]


def test_issue_page_shows_the_selected_week_in_readable_form(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    _seed_advalue_weeks(db, monkeypatch)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"),
                           default_timeout=60)
    at.session_state["proj_pills"] = "アドバリュー"
    at.session_state["adv_sub_pills"] = "9-1"
    at.run()
    assert not at.exception
    text = "\n".join(str(c.value) for c in at.caption)
    assert "9月 1週目" in text


def test_issue_page_shows_only_the_selected_weeks_numbers(tmp_path, monkeypatch):
    """週を選んだら、その週の原価だけが集計されること(他の週が混ざらない)。"""
    from common import posting_logic

    db = os.path.join(tmp_path, "t.db")
    _seed_advalue_weeks(db, monkeypatch)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"),
                           default_timeout=60)
    at.session_state["proj_pills"] = "アドバリュー"
    at.session_state["adv_sub_pills"] = "8-1"
    at.run()
    text = "\n".join(str(m.value) for m in at.markdown)
    assert f"¥{posting_logic.fmt_num(400)}" in text          # 8-1 の 400 だけ
    assert f"¥{posting_logic.fmt_num(1000)}" not in text     # 全週の合計にはならない
