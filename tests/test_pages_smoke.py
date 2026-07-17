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
