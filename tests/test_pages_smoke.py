"""画面のスモークテスト。Streamlit AppTest でページが例外なく描画されることを見る。
実DBを触らないよう、各テストで POSTING_DB_PATH に一時DBを指す。"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = os.path.join(tmp_path, "smoke.db")
    monkeypatch.setenv("POSTING_DB_PATH", path)
    store.init_db(path)
    store.seed_masters(db_path=path)
    return path


def _run(page):
    at = AppTest.from_file(os.path.join(ROOT, "pages", page), default_timeout=30)
    at.run()
    return at


def _rendered_text(at):
    """描画された要素の中身を文字列で集める。表示内容のassertにはこれを使う。
    ⚠️ str(at) は AppTest.__repr__ が _script_path / default_timeout / session_state しか
    返さないため、何をassertしても通ってしまう。表示の検証には絶対に使わないこと。"""
    parts = []
    for el in at.table:
        parts.append(el.value.to_string())
    for el in at.dataframe:      # st.dataframe / st.data_editor の中身
        parts.append(str(el.value))
    for el in at.markdown:
        parts.append(str(el.value))
    for el in at.caption:
        parts.append(str(el.value))
    return "\n".join(parts)


def test_master_page_renders(db):
    at = _run("05_マスタ管理.py")
    assert not at.exception


def test_master_page_tab_is_renamed_to_gyomu_itaku(db):
    at = _run("05_マスタ管理.py")
    labels = [t.label for t in at.tabs]
    assert "業務委託" in labels
    assert "配布委託先" not in labels


def test_master_page_hides_inactive_from_main_list(db):
    """停止中のマスタは通常の一覧に出さない。"""
    alive = store.add_distributor("現役の人", db_path=db)
    gone = store.add_distributor("辞めた人", active=0, db_path=db)
    at = _run("05_マスタ管理.py")

    # 有効な人は一覧に出て、削除(or 停止中)ボタンが並ぶ
    body = " ".join(m.value for m in at.markdown)
    assert "現役の人" in body
    # 停止中の人は一覧の削除ボタンを持たず、「有効に戻す」だけを持つ
    keys = {b.key for b in at.button}
    assert f"del_distributor_{alive}_btn" in keys
    assert f"del_distributor_{gone}_btn" not in keys
    assert f"off_distributor_{gone}_btn" not in keys
    assert f"on_distributor_{gone}" in keys


def test_master_page_reactivates_from_expander(db):
    """停止中の折りたたみから「有効に戻す」で復帰できる。"""
    gone = store.add_distributor("戻る人", active=0, db_path=db)
    at = _run("05_マスタ管理.py")
    at.button(key=f"on_distributor_{gone}").click().run()

    assert not at.exception
    rows = {r["id"]: r for r in store.list_distributors(db_path=db)}
    assert rows[gone]["active"]


def test_master_page_delete_distributor_also_clears_daily_rates(db):
    """使用実績0の配布員を物理削除するとき、日当金額も一緒に消す
    (count_master_usage は distributor_daily_rates を数えないため、
     消さないと孤立行が残る)。"""
    did = store.add_distributor("日当の人", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "ポスティング", "amount": 8000}],
                              db_path=db)
    assert store.list_daily_rates(did, db_path=db)

    at = _run("05_マスタ管理.py")
    at.button(key=f"del_distributor_{did}_btn").click().run()
    at.button(key=f"del_distributor_{did}_ok").click().run()

    assert not at.exception
    assert all(r["name"] != "日当の人" for r in store.list_distributors(db_path=db))
    assert store.list_daily_rates(did, db_path=db) == []


def test_master_page_deactivates_distributor_in_use(db):
    """使用実績がある配布員は物理削除せず停止中にする(過去データを守るため)。"""
    did = store.add_distributor("使用中の人", db_path=db)
    store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-31",
        [{"report_qty": 10, "unit_price": 100}], db_path=db)
    assert store.count_master_usage("distributor", did, db_path=db) > 0

    at = _run("05_マスタ管理.py")
    at.button(key=f"off_distributor_{did}_btn").click().run()
    at.button(key=f"off_distributor_{did}_ok").click().run()

    assert not at.exception
    rows = {r["name"]: r for r in store.list_distributors(db_path=db)}
    assert "使用中の人" in rows  # 過去データのために残っている
    assert not rows["使用中の人"]["active"]


def test_confirm_delete_shows_confirmation_before_running(db):
    """confirm_delete は押しただけでは実行せず、確認を出す。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("called", 0)
        ui.confirm_delete(key="t1", detail="7/17 ／ 駐車場代 ／ ¥1,500",
                          on_confirm=lambda: st.session_state.__setitem__(
                              "called", st.session_state["called"] + 1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert any(b.label == "削除" for b in at.button)
    at.button(key="t1_btn").click().run()
    # 確認が出て、まだ実行されていない
    assert at.session_state["called"] == 0
    assert len(at.warning) == 1
    assert any(b.label == "はい、削除する" for b in at.button)
    assert any(c.value == "7/17 ／ 駐車場代 ／ ¥1,500" for c in at.caption)


def test_confirm_delete_runs_on_confirm(db):
    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("called", 0)
        ui.confirm_delete(key="t2", detail="対象",
                          on_confirm=lambda: st.session_state.__setitem__(
                              "called", st.session_state["called"] + 1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t2_btn").click().run()
    at.button(key="t2_ok").click().run()
    assert at.session_state["called"] == 1


def test_confirm_delete_cancel_does_not_run(db):
    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("called", 0)
        ui.confirm_delete(key="t3", detail="対象",
                          on_confirm=lambda: st.session_state.__setitem__(
                              "called", st.session_state["called"] + 1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t3_btn").click().run()
    at.button(key="t3_no").click().run()
    assert at.session_state["called"] == 0
    assert len(at.warning) == 0


def test_confirm_delete_multiple_rows_do_not_interfere(db):
    """1つの画面に confirm_delete を3行分並べたとき、1行だけ操作しても他行に影響しないこと。

    2026-07-14に実際に起きたCriticalバグ（固定keyでsession_stateが保持され、
    編集フォームが別の行を上書きした）と同型のリグレッションを防ぐ。
    confirm_delete内部の `pending = f"_del_pending_{key}"` を固定値
    `"_del_pending"` に変えると、このテストが落ちることを確認済み。
    """

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        st.session_state.setdefault("deleted", [])
        for rid in (1, 2, 3):
            ui.confirm_delete(
                key=f"del_{rid}", detail=f"行{rid}",
                on_confirm=(lambda rid=rid: st.session_state["deleted"].append(rid)),
            )

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()

    # 2行目だけ削除ボタンを押す
    at.button(key="del_2_btn").click().run()

    # 2行目の確認UIだけが出て、1行目・3行目は元の削除ボタンのままであること
    assert len(at.warning) == 1
    assert at.button(key="del_1_btn").label == "削除"
    assert at.button(key="del_3_btn").label == "削除"
    assert not any(b.key == "del_1_ok" for b in at.button)
    assert not any(b.key == "del_3_ok" for b in at.button)
    assert any(b.key == "del_2_ok" for b in at.button)

    # 2行目を確定する
    at.button(key="del_2_ok").click().run()

    # 消えたのは2行目だけ
    assert at.session_state["deleted"] == [2]
    # 1行目・3行目は未確定のまま(削除ボタンに戻っている)
    assert at.button(key="del_1_btn").label == "削除"
    assert at.button(key="del_3_btn").label == "削除"


def test_confirm_delete_flashes_success_message_on_confirm(db):
    """確定後にflash(success)で「削除しました」を出す(オーナー要望のアナウンス)。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        ui.confirm_delete(key="t4", detail="対象", on_confirm=lambda: None)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t4_btn").click().run()
    at.button(key="t4_ok").click().run()
    assert at.session_state["_flash"] == "削除しました"


def test_confirm_delete_flashes_custom_success_message(db):
    """successを渡した場合はそのメッセージがflashされること
    (Task 10のマスタで「停止中にしました」を使うため)。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        ui.confirm_delete(key="t5", detail="対象", on_confirm=lambda: None,
                          success="停止中にしました")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t5_btn").click().run()
    at.button(key="t5_ok").click().run()
    assert at.session_state["_flash"] == "停止中にしました"


def test_master_page_announces_in_the_tab_that_was_operated(db):
    """業務委託タブで操作したアナウンスは業務委託タブに出て、案件タブに漏れないこと。

    Streamlitのタブは1回の実行で全タブの本体を描画するため、flash/show_flash が
    共有の1枠だと最初に呼ばれる案件タブの show_flash() がメッセージを奪ってしまい、
    操作した業務委託タブには何も出ない(＝押せたのか分からない)。
    """
    gone = store.add_distributor("戻る人", active=0, db_path=db)
    at = _run("05_マスタ管理.py")
    at.button(key=f"on_distributor_{gone}").click().run()
    assert not at.exception

    labels = [t.label for t in at.tabs]
    dist = at.tabs[labels.index("業務委託")]
    proj = at.tabs[labels.index("案件")]

    assert [s.value for s in dist.success] == ["有効に戻しました"]
    assert [s.value for s in proj.success] == []


def test_master_page_delete_announces_in_the_tab_that_was_operated(db):
    """confirm_delete 経由の「削除しました」も操作したタブに出ること。
    section を落とすと案件タブ(最初に描画されるタブ)に横取りされるため、
    このテストが flash(success, section) の section 伝播を守る。"""
    did = store.add_distributor("消す人", db_path=db)
    at = _run("05_マスタ管理.py")
    at.button(key=f"del_distributor_{did}_btn").click().run()
    at.button(key=f"del_distributor_{did}_ok").click().run()
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert [s.value for s in at.tabs[labels.index("業務委託")].success] == ["削除しました"]
    assert [s.value for s in at.tabs[labels.index("案件")].success] == []


def test_master_page_deactivate_announces_in_the_tab_that_was_operated(db):
    """使用実績のある配布員を「停止中にする」経路でも、アナウンスは操作したタブに出て
    他タブに漏れないこと(delete側と同じ confirm_delete の section を通る)。"""
    did = store.add_distributor("使用中の人2", db_path=db)
    store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-31",
        [{"report_qty": 10, "unit_price": 100}], db_path=db)
    at = _run("05_マスタ管理.py")
    at.button(key=f"off_distributor_{did}_btn").click().run()
    at.button(key=f"off_distributor_{did}_ok").click().run()
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert [s.value for s in at.tabs[labels.index("業務委託")].success] == ["停止中にしました"]
    assert [s.value for s in at.tabs[labels.index("案件")].success] == []


def test_master_page_flash_sections_do_not_leak_between_tabs(db):
    """別セクション宛のflashは、そのセクションのshow_flashだけが消費すること。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        ui.flash("Aしました", "sec_a")
        ui.flash("Bしました", "sec_b")
        t1, t2 = st.tabs(["A", "B"])
        with t1:
            ui.show_flash("sec_a")
        with t2:
            ui.show_flash("sec_b")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert [s.value for s in at.tabs[0].success] == ["Aしました"]
    assert [s.value for s in at.tabs[1].success] == ["Bしました"]


def test_flash_without_section_keeps_old_behaviour(db):
    """section を省略した既存の呼び出し(01/02/03ページ)は今まで通り動くこと。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        ui.flash("登録しました")
        ui.show_flash()

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert [s.value for s in at.success] == ["登録しました"]
    assert "_flash" not in at.session_state


def test_confirm_delete_button_container_keeps_confirmation_full_width(db):
    """button_container を渡すと、削除ボタンだけがその狭い列に入り、
    確認UI(警告文・詳細・はい/やめる)は列の外＝全幅に出ること。

    以前は行を c1, c2 = st.columns([4, 1]) で描き、c2(幅20%)の中で confirm_delete を
    呼んでいたため、確認文が画面幅の約3%に潰れて読めなかった。
    """

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        c1, c2 = st.columns([4, 1])
        c1.write("使用中の人")
        ui.confirm_delete(key="row1", label="停止中にする",
                          warning="⚠️ 「使用中の人」は 3件のデータで使用中です。",
                          detail="過去データを残すため、削除ではなく停止中にします。",
                          on_confirm=lambda: None, button_container=c2)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    # 削除ボタンは狭い列(c2)の中にある
    assert [b.label for b in at.columns[1].button] == ["停止中にする"]
    assert [b.label for b in at.columns[0].button] == []

    at.button(key="row1_btn").click().run()

    # 確認UIは列の中ではなく全幅に出ている
    # (先頭の⚠️は Streamlit がアイコンとして切り出すため value には入らない)
    assert [w.value for w in at.warning] == ["「使用中の人」は 3件のデータで使用中です。"]
    assert not at.columns[1].warning
    assert not at.columns[1].caption
    assert not any(b.key == "row1_ok" for b in at.columns[1].button)
    assert any(b.key == "row1_ok" for b in at.button)


# ===== Task 11: 経費・買掛・売掛ページ =====

_EXPENSE_PAGE = "01_経費・買掛・売掛.py"


def _sel(at, label):
    """ラベルで selectbox を1つ引く。無ければ None。"""
    for s in at.selectbox:
        if s.label == label:
            return s
    return None


def test_expense_page_renders(db):
    at = _run(_EXPENSE_PAGE)
    assert not at.exception


def test_petty_form_has_distributor_select(db):
    store.add_distributor("山田太郎", db_path=db)
    at = _run(_EXPENSE_PAGE)
    labels = [s.label for s in at.selectbox]
    assert "配布員(任意)" in labels


def test_petty_form_distributor_select_offers_active_masters_only(db):
    """登録の選択肢は有効な配布員だけ(停止中は選ばせない)。"""
    store.add_distributor("現役の人", db_path=db)
    store.add_distributor("辞めた人", active=0, db_path=db)
    at = _run(_EXPENSE_PAGE)
    opts = _sel(at, "配布員(任意)").options
    assert "現役の人" in opts
    assert "辞めた人" not in opts


def test_petty_list_shows_distributor_name(db):
    did = store.add_distributor("山田太郎", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    at = _run(_EXPENSE_PAGE)
    assert "山田太郎" in _rendered_text(at)


def test_petty_list_shows_distributor_name_even_if_deactivated(db):
    """停止中になった配布員でも、過去の小口には名前が出ること
    (一覧の名前引きは only_active を付けない = 停止中方式の肝)。"""
    did = store.add_distributor("辞めた人", active=0, db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    at = _run(_EXPENSE_PAGE)
    assert "辞めた人" in _rendered_text(at)


def test_petty_registration_saves_distributor(db):
    did = store.add_distributor("山田太郎", db_path=db)
    at = _run(_EXPENSE_PAGE)
    _sel(at, "配布員(任意)").set_value("山田太郎")
    at.number_input[0].set_value(1500)
    at.button[0].click().run()

    assert not at.exception
    rows = store.list_petty_cash(db_path=db)
    assert len(rows) == 1
    assert rows[0]["distributor_id"] == did


def test_petty_list_has_delete_button_and_deletes_the_right_row(db):
    a = store.add_petty_cash("2026-07-10", None, 1000, memo="A", db_path=db)
    b = store.add_petty_cash("2026-07-11", None, 2000, memo="B", db_path=db)
    at = _run(_EXPENSE_PAGE)
    keys = {btn.key for btn in at.button}
    assert f"del_petty_{a}_btn" in keys
    assert f"del_petty_{b}_btn" in keys

    at.button(key=f"del_petty_{b}_btn").click().run()
    at.button(key=f"del_petty_{b}_ok").click().run()

    assert not at.exception
    ids = [r["id"] for r in store.list_petty_cash(db_path=db)]
    assert ids == [a]


def test_petty_delete_announces_in_the_list_tab(db):
    """削除のアナウンスは一覧タブに出て、登録タブに奪われないこと。
    (タブは1回の実行で全部描画されるため、section を付けないと先に描かれる
     登録タブの show_flash() がメッセージを消費してしまう)"""
    rid = store.add_petty_cash("2026-07-10", None, 1000, db_path=db)
    at = _run(_EXPENSE_PAGE)
    at.button(key=f"del_petty_{rid}_btn").click().run()
    at.button(key=f"del_petty_{rid}_ok").click().run()

    assert not at.exception
    assert [s.value for s in at.tabs[1].success] == ["削除しました"]
    assert [s.value for s in at.tabs[0].success] == []


def _payable_page(db):
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.run()
    at.radio[0].set_value("買掛").run()
    return at


def test_payable_original_status_autoset_from_vendor_master(db):
    """取引先名がマスタと一致したら、原本区分に既定が入っていること。"""
    store.add_payables_vendor("ABC商事", default_original_status="本社", db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.session_state["pay_draft"] = {"vendor": "ABC商事", "amount": 5000,
                                     "date": "2026-07-17", "note": None}
    at.run()
    at.radio[0].set_value("買掛").run()

    assert not at.exception
    assert _sel(at, "原本区分").value == "本社"


def test_payable_original_status_autoset_works_for_inactive_vendor(db):
    """停止中の買掛先でも、名前が一致すれば既定を返す(意図的に active を見ない)。"""
    store.add_payables_vendor("旧商事", default_original_status="クレジット",
                              active=0, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.session_state["pay_draft"] = {"vendor": "旧商事", "amount": 5000,
                                     "date": "2026-07-17", "note": None}
    at.run()
    at.radio[0].set_value("買掛").run()

    assert not at.exception
    assert _sel(at, "原本区分").value == "クレジット"


def test_payable_original_status_defaults_when_vendor_unknown(db):
    """マスタに無い取引先なら既定値(先頭)のまま。"""
    at = _payable_page(db)
    assert _sel(at, "原本区分").value == "原本あり"


def test_payable_list_deletes_the_right_row_and_announces(db):
    a = store.add_payable(None, None, 1000, date="2026-07-10", vendor_name="A社", db_path=db)
    b = store.add_payable(None, None, 2000, date="2026-07-11", vendor_name="B社", db_path=db)
    at = _payable_page(db)
    at.button(key=f"del_pay_{b}_btn").click().run()
    at.button(key=f"del_pay_{b}_ok").click().run()

    assert not at.exception
    assert [r["id"] for r in store.list_payables(db_path=db)] == [a]
    assert [s.value for s in at.tabs[1].success] == ["削除しました"]
    assert [s.value for s in at.tabs[0].success] == []


def test_receivable_list_deletes_the_right_row_and_announces(db):
    cid = store.add_receivables_client("得意先", db_path=db)
    a = store.add_receivable("2026-07", cid, 1000, db_path=db)
    b = store.add_receivable("2026-07", cid, 2000, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.run()
    at.radio[0].set_value("売掛").run()
    at.button(key=f"del_recv_{b}_btn").click().run()
    at.button(key=f"del_recv_{b}_ok").click().run()

    assert not at.exception
    assert [r["id"] for r in store.list_receivables(db_path=db)] == [a]
    assert [s.value for s in at.tabs[1].success] == ["削除しました"]
    assert [s.value for s in at.tabs[0].success] == []


# ============================================================ 業務委託登録
_CONTRACT_PAGE = "02_業務委託登録.py"


def _seed_invoice(db, pay_type="歩合", copies=None, name="山田太郎"):
    did = store.add_distributor(name, pay_type=pay_type, db_path=db)
    pid = store.add_project("案件A", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3, "unit_price": 8000, "remark": "配布",
          "copies": copies}],
        pay_type=pay_type, db_path=db)
    return did, pid, iid


def test_contract_page_renders(db):
    store.add_distributor("山田太郎", pay_type="歩合", db_path=db)
    at = _run(_CONTRACT_PAGE)
    assert not at.exception


def test_contract_page_warns_with_new_master_tab_name(db):
    """配布員が居ないときの案内は、新しいタブ名『業務委託』を指すこと。"""
    at = _run(_CONTRACT_PAGE)
    msgs = [w.value for w in at.warning]
    assert msgs == ["先に『マスタ管理』の「業務委託」タブで配布員を登録してください。"]


def test_contract_page_shows_pay_type_of_selected_distributor(db):
    store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    at = _run(_CONTRACT_PAGE)
    assert "日当" in _rendered_text(at)


def test_contract_list_shows_nichito_qty_in_days(db):
    """日当で登録した請求は、一覧で数量が「日」で出る(枚ではない)。"""
    _seed_invoice(db, pay_type="日当", copies=3713)
    at = _run(_CONTRACT_PAGE)
    assert "山田太郎" in _rendered_text(at)


def test_contract_list_nichito_shows_days_not_mai(db):
    """🔴 このタスクの主眼。日当の請求の数量が「3 日」で出て、「枚」が出ないこと。"""
    _seed_invoice(db, pay_type="日当", copies=3713)
    at = _run(_CONTRACT_PAGE)
    text = _rendered_text(at)
    assert "3 日" in text
    assert "3 枚" not in text


def test_contract_list_houbai_still_shows_mai(db):
    """🔴 後方互換。歩合(と pay_type なしの既存請求)は今まで通り「枚」のまま。"""
    _seed_invoice(db, pay_type=None)      # pay_type NULL = 既存データと同じ状態
    at = _run(_CONTRACT_PAGE)
    text = _rendered_text(at)
    assert "3 枚" in text
    assert "3 日" not in text


def test_contract_list_uses_saved_pay_type_not_current_master(db):
    """🔴 請求ヘッダに焼き付けた pay_type を使うこと。
    配布員の支払形態を後から歩合に変えても、日当で登録した過去の請求は「3 日」のまま。"""
    did, _, _ = _seed_invoice(db, pay_type="日当", copies=3713)
    store.update_distributor(did, pay_type="歩合", db_path=db)
    at = _run(_CONTRACT_PAGE)
    text = _rendered_text(at)
    assert "3 日" in text
    assert "3 枚" not in text


def _contract_page_with_lines(db, pay_type, edits):
    """明細エディタに入力がある状態のページ。AppTest は data_editor を操作できないので、
    ウィジェットの状態(edited_rows)を直接セットして入力を再現する。"""
    at = AppTest.from_file(os.path.join(ROOT, "pages", _CONTRACT_PAGE), default_timeout=30)
    at.session_state[f"line_editor_{pay_type}"] = {
        "edited_rows": {0: edits}, "added_rows": [], "deleted_rows": []}
    at.run()
    return at


def _click(at, label):
    [b for b in at.button if b.label == label][0].click().run()


def test_contract_registration_bakes_in_pay_type(db):
    """🔴 登録時の支払形態を請求ヘッダに焼き付けること(後でマスタが変わっても化けない)。"""
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.add_project("案件A", db_path=db)
    at = _contract_page_with_lines(db, "日当", {"案件": "案件A", "数量": 3.0, "部数": 3713})
    _click(at, "この請求を登録")

    assert not at.exception
    invs = store.list_contract_invoices(db_path=db)
    assert len(invs) == 1
    assert invs[0]["distributor_id"] == did
    assert invs[0]["pay_type"] == "日当"


def test_contract_registration_nichito_fills_unit_price_from_master(db):
    """日当は、業務名を選ぶとマスタの日当額が単価に入る(単価は手入力で上書きできる)。"""
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "ポスティング", "amount": 12000}],
                              db_path=db)
    store.add_project("案件A", db_path=db)
    at = _contract_page_with_lines(
        db, "日当", {"案件": "案件A", "業務": "ポスティング", "数量": 3.0, "部数": 3713})
    _click(at, "この請求を登録")

    assert not at.exception
    detail = store.get_contract_invoice(
        store.list_contract_invoices(db_path=db)[0]["id"], db_path=db)
    assert detail["lines"][0]["unit_price"] == 12000
    assert detail["lines"][0]["amount"] == 36000
    assert detail["lines"][0]["copies"] == 3713


def test_contract_registration_houbai_does_not_send_copies(db):
    """歩合は部数の列を出さない(数量がそのまま部数)。copies は NULL のまま。"""
    store.add_distributor("山田太郎", pay_type="歩合", db_path=db)
    store.add_project("案件A", db_path=db)
    at = _contract_page_with_lines(db, "歩合", {"案件": "案件A", "数量": 3713.0, "単価": 3.5})
    _click(at, "この請求を登録")

    assert not at.exception
    detail = store.get_contract_invoice(
        store.list_contract_invoices(db_path=db)[0]["id"], db_path=db)
    assert detail["lines"][0]["copies"] is None
    assert detail["lines"][0]["amount"] == 3713 * 3.5


def test_contract_list_deletes_the_right_row(db):
    _, pid, a = _seed_invoice(db, pay_type="歩合", name="A太郎")
    did_b = store.add_distributor("B太郎", pay_type="歩合", db_path=db)
    b = store.add_contract_invoice(did_b, "2026-07-16", "2026-07-01", "2026-07-15",
                                   [{"project_id": pid, "report_qty": 1, "unit_price": 100,
                                     "remark": "配布"}], db_path=db)
    at = _run(_CONTRACT_PAGE)
    keys = {btn.key for btn in at.button}
    assert f"del_inv_{a}_btn" in keys
    assert f"del_inv_{b}_btn" in keys

    at.button(key=f"del_inv_{b}_btn").click().run()
    at.button(key=f"del_inv_{b}_ok").click().run()

    assert not at.exception
    assert [i["id"] for i in store.list_contract_invoices(db_path=db)] == [a]


def test_contract_delete_announces_in_the_list_tab(db):
    """削除のアナウンスは一覧タブに出て、先に描画される登録タブに奪われないこと。"""
    _, _, iid = _seed_invoice(db, pay_type="歩合")
    at = _run(_CONTRACT_PAGE)
    at.button(key=f"del_inv_{iid}_btn").click().run()
    at.button(key=f"del_inv_{iid}_ok").click().run()

    assert not at.exception
    assert [s.value for s in at.tabs[1].success] == ["削除しました"]
    assert [s.value for s in at.tabs[0].success] == []
