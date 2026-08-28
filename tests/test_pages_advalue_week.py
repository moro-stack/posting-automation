"""アドバリューの週次区分を登録画面で必須にする（依頼⑥・2026-08-27 大橋様）。

・案件が「アドバリュー」なら週(1週目〜5週目)を選ばないと登録できない
・保存される区分は伝票の日付の月と組み合わせた "8-1" 形式(過去データと同じ形)
・9月の伝票なら "9-1"、10月なら "10-1"(月をまたぐと自動で繰り上がる)
"""
import datetime as _dt
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
    """date は datetime.date（2026-08-28 にカレンダー入力へ統一）。"""
    at.date_input(key="petty_date").set_value(date)
    at.selectbox(key="petty_proj").set_value(proj)
    at.number_input(key="petty_amount").set_value(amount)
    if week is not None:
        at.selectbox(key="petty_week").set_value(week)
    return at


def test_petty_advalue_without_a_week_is_refused(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date=_dt.date(2026, 8, 4), proj="アドバリュー")
    _submit(at)
    assert any("週" in str(e.value) for e in at.error), "週の未選択が知らされていない"
    assert store.list_petty_cash(db_path=db) == [], "週を選ばずに登録されてしまった"


def test_petty_advalue_with_a_week_saves_the_month_dash_week_label(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date=_dt.date(2026, 8, 4), proj="アドバリュー", week="1週目")
    _submit(at)
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1
    assert rows[0]["other_label"] == "8-1"


def test_petty_advalue_rolls_the_month_over_automatically(tmp_path, monkeypatch):
    """🔴 依頼の肝: 9月の伝票なら 9-1、10月なら 10-1。選択肢を作り直さなくても
    伝票の日付から月が決まる。"""
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date=_dt.date(2026, 10, 2), proj="アドバリュー", week="1週目")
    _submit(at)
    assert store.list_petty_cash(db_path=db)[0]["other_label"] == "10-1"


def test_petty_non_advalue_project_is_unaffected_by_the_week(tmp_path, monkeypatch):
    """他の案件は週を選んでいなくても今までどおり登録できる。"""
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date=_dt.date(2026, 8, 4), proj="関西ぱど：京阪北版")
    _submit(at)
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1 and rows[0]["other_label"] is None


def test_petty_sonota_still_uses_the_free_text(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "小口")
    _petty(at, date=_dt.date(2026, 8, 4), proj="その他")
    at.text_input(key="petty_other").set_value("買取専科")
    _submit(at)
    assert store.list_petty_cash(db_path=db)[0]["other_label"] == "買取専科"


# ===== 売掛（売上）=====


def test_receivable_advalue_without_a_week_is_refused(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "売掛")
    at.date_input(key="recv_month").set_value(_dt.date(2026, 9, 15))
    at.selectbox(key="recv_proj").set_value("アドバリュー")
    at.number_input(key="recv_amount").set_value(50000)
    _submit(at, "receivable")
    assert any("週" in str(e.value) for e in at.error)
    assert store.list_receivables(db_path=db) == []


def test_receivable_advalue_uses_the_month_of_the_gedo(tmp_path, monkeypatch):
    """売掛は日付ではなく月度(2026-09)を持つ。そこから月を取ること。"""
    db = os.path.join(tmp_path, "t.db")
    at = _at(db, monkeypatch, "売掛")
    at.date_input(key="recv_month").set_value(_dt.date(2026, 9, 15))
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


# ===== 【バグ】1周目しか表示されない（2026-08-28・大橋様ご報告） =====
# 実データを調べたところ、アドバリューの配布員代(業務委託)は other_label が
# すべて None だった。業務委託登録の週欄が自由入力で空のまま登録できたため。
# 区分なしの行はどの週にも出ないので「8-1しか無い」ように見えていた。


def _contract_page(db, monkeypatch, edits=None, pay_type="歩合"):
    """業務委託登録のページ。AppTest は data_editor を直接操作できないので、
    ウィジェットの状態(edited_rows)をセットして入力を再現する
    (tests/test_pages_smoke.py の _contract_page_with_lines と同じやり方)。"""
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    if not store.list_distributors(db_path=db):
        store.add_distributor("山田", pay_type=pay_type, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "02_業務委託登録.py"),
                           default_timeout=60)
    if edits is not None:
        at.session_state[f"line_editor_{pay_type}"] = {
            "edited_rows": {0: edits}, "added_rows": [], "deleted_rows": []}
    at.run()
    assert not at.exception
    return at


def _line(project, week="", qty=1000.0, price=3.0):
    return {"案件": project, "数量": qty, "単価": price, "アドバリューの週": week}


def test_contract_page_offers_the_week_as_a_dropdown(tmp_path, monkeypatch):
    """🔴 自由入力だと空のまま登録できてしまう。選択式にする。"""
    at = _contract_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    frames = [d.value for d in at.dataframe if "案件" in list(d.value.columns)]
    assert frames, "明細エディタが描かれていない"
    assert "アドバリューの週" in list(frames[0].columns)


def test_contract_page_week_options_follow_the_month(tmp_path, monkeypatch):
    """月は配布業務期間から決まる。9月なら 9-1〜9-5 が出る。"""
    from common import advalue as V

    month = _dt.date.today().month
    at = _contract_page(os.path.join(tmp_path, "t.db"), monkeypatch)
    src = open(os.path.join(ROOT, "pages", "02_業務委託登録.py"), encoding="utf-8").read()
    assert "week_labels_for_month" in src
    assert V.week_labels_for_month(month)[0] == f"{month}-1"


def test_contract_advalue_line_without_a_week_cannot_be_registered(tmp_path, monkeypatch):
    """🔴 再発防止の中心。週が空のアドバリュー行は登録させない。"""
    db = os.path.join(tmp_path, "t.db")
    at = _contract_page(db, monkeypatch, edits=_line("アドバリュー", week=""))
    assert any("週" in str(e.value) for e in at.error), "週の入れ忘れが知らされていない"
    save = next(b for b in at.button if b.label == "この請求を登録")
    assert save.disabled is True
    assert store.list_contract_invoices(db_path=db) == []


def test_contract_advalue_line_with_a_week_is_saved_with_that_label(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    month = _dt.date.today().month
    at = _contract_page(db, monkeypatch, edits=_line("アドバリュー", week=f"{month}-3"))
    assert not [e for e in at.error]
    next(b for b in at.button if b.label == "この請求を登録").click().run()
    invs = store.list_contract_invoices(db_path=db)
    assert len(invs) == 1
    lines = store.get_contract_invoice(invs[0]["id"], db_path=db)["lines"]
    assert [l["other_label"] for l in lines] == [f"{month}-3"]


def test_contract_non_advalue_line_needs_no_week(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    at = _contract_page(db, monkeypatch, edits=_line("関西ぱど：京阪北版", week=""))
    assert not [e for e in at.error]
    next(b for b in at.button if b.label == "この請求を登録").click().run()
    invs = store.list_contract_invoices(db_path=db)
    assert len(invs) == 1


def _seed_all_weeks(db, monkeypatch):
    """5週ぶんの売上と原価(配布員代)を、週の区分付きで入れる。"""
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    pid = next(p["id"] for p in store.list_projects(db_path=db) if p["name"] == "アドバリュー")
    did = store.add_distributor("山田", pay_type="歩合", db_path=db)
    for w in range(1, 6):
        store.add_receivable("2026-08", None, w * 10000, project_id=pid,
                             other_label=f"8-{w}", db_path=db)
        store.add_contract_invoice(
            did, "2026-08-10", "2026-08-01", "2026-08-07",
            [{"project_id": pid, "report_qty": 100, "unit_price": w,
              "remark": "配布", "other_label": f"8-{w}", "copies": None}],
            pay_type="歩合", db_path=db)
    return pid


def _issue(db, sub=None):
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"), default_timeout=60)
    at.session_state["proj_pills"] = "アドバリュー"
    if sub is not None:
        at.session_state["adv_sub_pills"] = sub
    at.run()
    assert not at.exception
    return at, "\n".join(str(m.value) for m in at.markdown)


def test_issue_page_lists_every_week_that_has_data(tmp_path, monkeypatch):
    """🔴 報告そのもの: 2〜5週目も選べること。"""
    db = os.path.join(tmp_path, "t.db")
    _seed_all_weeks(db, monkeypatch)
    at, _ = _issue(db)
    assert list(at.pills(key="adv_sub_pills").options) == [
        "全体", "8-1", "8-2", "8-3", "8-4", "8-5"]


def test_issue_page_aggregates_each_week_separately(tmp_path, monkeypatch):
    """各週で売上・原価が集計されること(1週目の値が他の週にも出る、を防ぐ)。"""
    from common import posting_logic

    db = os.path.join(tmp_path, "t.db")
    _seed_all_weeks(db, monkeypatch)
    for w in range(1, 6):
        _, text = _issue(db, f"8-{w}")
        assert f"¥{posting_logic.fmt_num(w * 10000)}" in text, f"8-{w} の売上が出ていない"
        assert f"¥{posting_logic.fmt_num(w * 100)}" in text, f"8-{w} の原価が出ていない"


def test_issue_page_total_of_all_weeks_matches_the_sum(tmp_path, monkeypatch):
    from common import posting_logic

    db = os.path.join(tmp_path, "t.db")
    _seed_all_weeks(db, monkeypatch)
    _, text = _issue(db)
    assert f"¥{posting_logic.fmt_num(150000)}" in text     # 売上 1〜5週の合計
    assert f"¥{posting_logic.fmt_num(1500)}" in text       # 原価 1〜5週の合計


def test_issue_page_surfaces_rows_that_have_no_week(tmp_path, monkeypatch):
    """🔴 週なしで登録された既存データが画面から消えないこと。
    実データではここに配布員代が丸ごと隠れていた。"""
    from common import posting_logic

    db = os.path.join(tmp_path, "t.db")
    pid = _seed_all_weeks(db, monkeypatch)
    did = store.list_distributors(db_path=db)[0]["id"]
    store.add_contract_invoice(
        did, "2026-08-10", "2026-08-01", "2026-08-07",
        [{"project_id": pid, "report_qty": 1, "unit_price": 7777,
          "remark": "配布", "other_label": None, "copies": None}],
        pay_type="歩合", db_path=db)
    at, _ = _issue(db)
    assert posting_logic.LABEL_UNSET in list(at.pills(key="adv_sub_pills").options)
    _, text = _issue(db, posting_logic.LABEL_UNSET)
    assert f"¥{posting_logic.fmt_num(7777)}" in text


def test_no_unset_choice_when_every_row_has_a_week(tmp_path, monkeypatch):
    from common import posting_logic

    db = os.path.join(tmp_path, "t.db")
    _seed_all_weeks(db, monkeypatch)
    at, _ = _issue(db)
    assert posting_logic.LABEL_UNSET not in list(at.pills(key="adv_sub_pills").options)


def test_no_unset_choice_when_weeks_are_not_used_at_all(tmp_path, monkeypatch):
    """週を1つも使っていない段階では「（未設定）」を出さない。
    「全体」と同じ意味にしかならず、選択肢が増えて紛らわしいだけのため。"""
    from common import posting_logic

    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    pid = next(p["id"] for p in store.list_projects(db_path=db) if p["name"] == "アドバリュー")
    store.add_receivable("2026-08", None, 100000, project_id=pid, db_path=db)
    at, _ = _issue(db)
    assert not any(p.key == "adv_sub_pills" for p in at.pills)
