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
    """停止中のマスタも同じ一覧にインライン表示する(折りたたみ・別セクションは無い)。"""
    alive = store.add_distributor("現役の人", db_path=db)
    gone = store.add_distributor("辞めた人", active=0, db_path=db)
    at = _run("05_マスタ管理.py")

    # 有効な人は運用中トグル(確認あり→停止中)を持つ
    body = " ".join(m.value for m in at.markdown)
    assert "現役の人" in body
    keys = {b.key for b in at.button}
    assert f"deact_distributor_{alive}_btn" in keys
    # 停止中の人は同じ一覧に出て、確認なしの「停止中」トグル(→有効化)を持つ
    assert f"deact_distributor_{gone}_btn" not in keys
    assert f"react_distributor_{gone}" in keys


def test_master_page_reactivates_inline(db):
    """一覧にインライン表示された「停止中」トグルから復帰できる(折りたたみは無い)。"""
    gone = store.add_distributor("戻る人", active=0, db_path=db)
    at = _run("05_マスタ管理.py")
    at.button(key=f"react_distributor_{gone}").click().run()

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
    at.button(key=f"deact_distributor_{did}_btn").click().run()
    at.button(key=f"deact_distributor_{did}_ok").click().run()

    assert not at.exception
    rows = {r["name"]: r for r in store.list_distributors(db_path=db)}
    assert "使用中の人" in rows  # 過去データのために残っている
    assert not rows["使用中の人"]["active"]


# ===== マスタの編集 =====
_MASTER_PAGE = "05_マスタ管理.py"


def _edit_widget(seq, prefix):
    """開いている編集ダイアログの入力欄を、ウィジェットkeyの先頭一致で取る。
    行idまでは指定しない＝固定キーへの退行後も同じように取れるので、テストの判定は
    「DBの中身がどうなったか」だけに依存する(keyの形を変えただけでは通ってしまわない)。
    登録フォーム側の同名ラベル(振込先・時給額など)は key を持たないので混ざらない。"""
    hits = [w for w in seq if (w.key or "").startswith(prefix)]
    assert len(hits) == 1, f"{prefix}: {len(hits)}件(編集ダイアログは1つだけ開くはず)"
    return hits[0]


def _submit_edit(at, open_key):
    """開いている編集ダイアログの「更新」を押す。

    🟡 AppTestの制約に注意(test_new_distributor_via_dialog と同じ理由)。st.dialog は
    内部で st.fragment を使っており、本物のブラウザでは「ダイアログ内のウィジェット操作
    ＝そのダイアログだけの部分再実行」になるため、開くボタン(`if st.button(...): dialog()`)
    を押し直さなくてもダイアログは開いたままになる。しかしAppTestの .run() は常にフル
    スクリプトの再実行であり、fragment単位の再実行を再現しないため、開くボタンを
    再クリックしないまま .run() すると外側の if が再び False になってダイアログの中身
    (「更新」ボタンごと)が消えてしまう(実際に確認済み)。そのため、フィールドの変更・
    「更新」クリックは、開くボタンをもう一度「押した」ことにしたのと同じ1回の .run() に
    まとめて送る(ページの実装・本番動作には問題無い＝これはテストハーネス側の制約)。"""
    at.button(key=open_key).click()
    [b for b in at.button if b.label == "更新"][0].click()
    at.run()


def _cancel_edit(at, open_key):
    """開いている編集ダイアログの「やめる」を押す。_submit_edit と同じ理由で、開くボタンの
    再クリックと同じ1回の .run() にまとめて送る。"""
    at.button(key=open_key).click()
    [b for b in at.button if b.label == "やめる"][0].click()
    at.run()


def test_master_page_edit_distributor_updates_all_fields(db):
    """業務委託の編集で、行そのものの項目(氏名・区分・支払形態・振込先・時給額・月額)が
    DBに反映されること。振込先の打ち間違いを直せない、が今回の改修の動機。"""
    did = store.add_distributor("山田太郎", kind="業務委託", pay_type="日当",
                                bank_info="三井住友 1111111", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_distributor_{did}").click().run()
    assert not at.exception

    _edit_widget(at.text_input, "edit_name_distributor").set_value("山田太郎改")
    _edit_widget(at.selectbox, "edit_kind_distributor").set_value("アルバイト")
    _edit_widget(at.selectbox, "edit_pay_distributor").set_value("時給")
    _edit_widget(at.text_area, "edit_bank_distributor").set_value("三井住友 2222222")
    _edit_widget(at.number_input, "edit_hourly_distributor").set_value(1500)
    _edit_widget(at.number_input, "edit_monthly_distributor").set_value(250000)
    _submit_edit(at, f"edit_distributor_{did}")

    assert not at.exception
    row = {r["id"]: r for r in store.list_distributors(db_path=db)}[did]
    assert row["name"] == "山田太郎改"
    assert row["kind"] == "アルバイト"
    assert row["pay_type"] == "時給"
    assert row["bank_info"] == "三井住友 2222222"
    assert row["hourly_rate"] == 1500
    assert row["monthly_rate"] == 250000
    assert row["active"]      # 編集で停止中に落ちない


def test_master_page_edit_payables_vendor_updates_fields(db):
    """買掛先の編集で、取引先名・既定の費目・既定の原本区分が反映されること。"""
    from common import posting_logic

    vid = store.add_payables_vendor("ABC商事", default_category="家賃",
                                    default_original_status=None, db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_payables_vendor_{vid}").click().run()
    assert not at.exception

    _edit_widget(at.text_input, "edit_name_payables_vendor").set_value("ABC商事株式会社")
    _edit_widget(at.text_input, "edit_cat_payables_vendor").set_value("電気")
    _edit_widget(at.selectbox, "edit_orig_payables_vendor").set_value(
        posting_logic.ORIGINAL_STATUSES[-1])
    _submit_edit(at, f"edit_payables_vendor_{vid}")

    assert not at.exception
    row = {r["id"]: r for r in store.list_payables_vendors(db_path=db)}[vid]
    assert row["name"] == "ABC商事株式会社"
    assert row["default_category"] == "電気"
    assert row["default_original_status"] == posting_logic.ORIGINAL_STATUSES[-1]


def test_master_page_edit_project_updates_name(db):
    pid = store.add_project("案件A", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_project_{pid}").click().run()
    _edit_widget(at.text_input, "edit_name_project").set_value("案件A改")
    _submit_edit(at, f"edit_project_{pid}")

    assert not at.exception
    assert {r["id"]: r for r in store.list_projects(db_path=db)}[pid]["name"] == "案件A改"


def test_master_page_edit_widget_keys_are_per_row(db):
    """🔴 編集フォームのウィジェットkeyに行idが入っていること。
    固定keyだと Streamlit が session_state を保持し、対象行を切り替えても前の行の値が
    残る(＝別の行を上書きする。2026-07-14の事故)。下の
    test_master_page_edit_updates_only_the_target_row が本命だが、key の形そのものも
    ここで固定しておく。"""
    a = store.add_distributor("Aさん", db_path=db)
    b = store.add_distributor("Bさん", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_distributor_{a}").click().run()
    keys = {w.key for w in at.text_input} | {w.key for w in at.text_area}
    assert f"edit_name_distributor_{a}" in keys
    assert f"edit_bank_distributor_{a}" in keys
    assert "edit_name_distributor" not in keys       # 固定キーへの退行
    assert f"edit_name_distributor_{b}" not in keys  # 開いていない行の欄は出さない


def test_master_page_edit_updates_only_the_target_row(db):
    """🔴🔴 このタスクで一番大事なテスト(2026-07-14の事故の再発防止)。
    Aさんを編集して振込先を直したあと、Bさんを編集して氏名だけを直す。
    Bさんの振込先・月額は元のまま、Aさんも氏名は元のままであること。

    編集フォームのウィジェットkeyが固定(行idを含まない)だと、Bさんのフォームに
    Aさんで入力した値が残ったまま描画され、更新でBさんの振込先がAさんの値に化ける。"""
    a = store.add_distributor("山田太郎", kind="業務委託", pay_type="時給",
                              bank_info="A銀行 1111111", hourly_rate=1000, db_path=db)
    b = store.add_distributor("佐藤花子", kind="自社社員", pay_type="月給",
                              bank_info="B銀行 2222222", monthly_rate=200000, db_path=db)

    at = _run(_MASTER_PAGE)
    # 1) Aさんの編集を開いて振込先を打ち直す
    at.button(key=f"edit_distributor_{a}").click().run()
    _edit_widget(at.text_area, "edit_bank_distributor").set_value("A銀行 9999999")
    # 2) 更新せずにBさんの編集へ切り替え、Bさんは氏名だけ直す
    #    (振込先・月額・区分・支払形態には触らない)
    at.button(key=f"edit_distributor_{b}").click().run()
    _edit_widget(at.text_input, "edit_name_distributor").set_value("佐藤花")
    _submit_edit(at, f"edit_distributor_{b}")
    assert not at.exception

    rows = {r["id"]: r for r in store.list_distributors(db_path=db)}
    # Bさんは触っていない項目が元のまま。
    # 固定キーだと 1) でAさんの欄に入力した "A銀行 9999999" がBさんのフォームに残り、
    # Bさんの振込先がAさんの口座に化ける(＝2026-07-14の事故)。
    assert rows[b]["name"] == "佐藤花"
    assert rows[b]["bank_info"] == "B銀行 2222222"
    assert rows[b]["kind"] == "自社社員"
    assert rows[b]["pay_type"] == "月給"
    assert rows[b]["monthly_rate"] == 200000
    assert rows[b]["hourly_rate"] is None   # 使わない項目は空のまま(0を書かない)
    # Aさんは1行たりとも変わっていない(更新していないので入力は捨てられる)
    assert rows[a]["name"] == "山田太郎"
    assert rows[a]["bank_info"] == "A銀行 1111111"
    assert rows[a]["hourly_rate"] == 1000


def test_master_page_edit_announces_in_the_tab_that_was_operated(db):
    """🔴 更新のアナウンスは操作したタブに出ること。
    flash に section を付けないと、最初に描画される案件タブの show_flash() が
    メッセージを奪い、業務委託タブには何も出ない(＝更新できたのか分からない)。"""
    did = store.add_distributor("山田太郎", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_distributor_{did}").click().run()
    _edit_widget(at.text_input, "edit_name_distributor").set_value("山田太郎改")
    _submit_edit(at, f"edit_distributor_{did}")

    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert [s.value for s in at.tabs[labels.index("業務委託")].success] == ["更新しました"]
    assert [s.value for s in at.tabs[labels.index("案件")].success] == []


def test_master_page_edit_closes_the_form_after_updating(db):
    """更新したら編集ダイアログは閉じること(開きっぱなしだと、直した後もダイアログが残って
    「まだ保存できていないのか」と迷う)。
    ※ st.rerun をまたぐと AppTest の要素ツリーに前の実行の残骸(閉じたダイアログの
      ウィジェット)が残ることがある(既知のAppTestの制約。要素は残るが中身は
      session_state から既に消えている)ため、「閉じたこと」は画面ではなく
      session_state にそのウィジェットkeyが無いことで見る。"""
    did = store.add_distributor("山田太郎", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_distributor_{did}").click().run()
    assert f"edit_name_distributor_{did}" in at.session_state
    _edit_widget(at.text_input, "edit_name_distributor").set_value("山田太郎改")
    _submit_edit(at, f"edit_distributor_{did}")

    assert not at.exception
    assert f"edit_name_distributor_{did}" not in at.session_state


def test_master_page_edit_form_is_not_shown_until_button_is_pressed(db):
    """編集フォームは押すまで出さない(一覧が縦に伸びない)。"""
    did = store.add_distributor("山田太郎", db_path=db)
    at = _run(_MASTER_PAGE)
    assert f"edit_distributor_{did}" in {b.key for b in at.button}
    assert not [w for w in at.text_input if (w.key or "").startswith("edit_name_")]


def test_master_page_edit_cancel_does_not_update(db):
    """「やめる」で閉じるだけ。入力した値はDBに入らない。
    ※ 閉じたことの見方は test_master_page_edit_closes_the_form_after_updating と同じ理由で
    session_state にウィジェットkeyが無いことで見る(要素ツリーはAppTestの制約で残骸が残る)。"""
    did = store.add_distributor("山田太郎", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_distributor_{did}").click().run()
    _edit_widget(at.text_input, "edit_name_distributor").set_value("押し間違え")
    _cancel_edit(at, f"edit_distributor_{did}")

    assert not at.exception
    assert {r["id"]: r for r in store.list_distributors(db_path=db)}[did]["name"] == "山田太郎"
    # 閉じているのでフォームは消えている
    assert f"edit_name_distributor_{did}" not in at.session_state


def test_master_page_edit_vendor_name_only_keeps_other_fields(db):
    """買掛先の氏名だけを直したとき、既定の費目・既定の原本区分が消えないこと。
    編集フォームが今の値を初期選択しない(いつも先頭＝「(なし)」に落ちる)と、
    名前を直しただけで既定の原本区分が黙って消え、買掛登録の自動入力が効かなくなる。"""
    from common import posting_logic

    keep = posting_logic.ORIGINAL_STATUSES[-1]
    vid = store.add_payables_vendor("ABC商事", default_category="家賃",
                                    default_original_status=keep, db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_payables_vendor_{vid}").click().run()
    _edit_widget(at.text_input, "edit_name_payables_vendor").set_value("ABC商事株式会社")
    _submit_edit(at, f"edit_payables_vendor_{vid}")

    assert not at.exception
    row = {r["id"]: r for r in store.list_payables_vendors(db_path=db)}[vid]
    assert row["name"] == "ABC商事株式会社"
    assert row["default_category"] == "家賃"
    assert row["default_original_status"] == keep


def test_master_page_edit_vendor_can_clear_original_status(db):
    """既定の原本区分を「(なし)」に戻すと、空(NULL)で保存されること。
    見た目の「(なし)」をそのまま文字列で保存すると、買掛登録の原本区分に
    選択肢に無い「(なし)」が既定として流れ込む。"""
    from common import posting_logic

    vid = store.add_payables_vendor(
        "ABC商事", default_original_status=posting_logic.ORIGINAL_STATUSES[0], db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_payables_vendor_{vid}").click().run()
    _edit_widget(at.selectbox, "edit_orig_payables_vendor").set_value("(なし)")
    _submit_edit(at, f"edit_payables_vendor_{vid}")

    assert not at.exception
    row = {r["id"]: r for r in store.list_payables_vendors(db_path=db)}[vid]
    assert row["default_original_status"] is None


def test_master_page_edit_strips_whitespace_from_name(db):
    """名前の前後の空白は保存時に取り除かれること(_name_fields / _distributor_fields の
    .strip()が退行して外れても、DBに空白付きの名前が入ってしまうことに気付けるように)。"""
    pid = store.add_project("案件A", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_project_{pid}").click().run()
    _edit_widget(at.text_input, "edit_name_project").set_value("  新しい名前  ")
    _submit_edit(at, f"edit_project_{pid}")

    assert not at.exception
    row = {r["id"]: r for r in store.list_projects(db_path=db)}[pid]
    assert row["name"] == "新しい名前"


def test_master_page_edit_vendor_can_clear_default_category(db):
    """既定の費目を空にすると、空文字でなく None(NULL) で保存されること。
    edit_vendor_can_clear_original_status と同じ考え方(原本区分だけでなく費目にも
    同じ保険が要る。(c.strip() or None) が退行して素の c.strip() に戻ると、
    空文字が既定の費目としてDBに残ってしまう)。"""
    vid = store.add_payables_vendor("ABC商事", default_category="家賃", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_payables_vendor_{vid}").click().run()
    _edit_widget(at.text_input, "edit_cat_payables_vendor").set_value("   ")
    _submit_edit(at, f"edit_payables_vendor_{vid}")

    assert not at.exception
    row = {r["id"]: r for r in store.list_payables_vendors(db_path=db)}[vid]
    assert row["default_category"] is None


def test_master_page_edit_ignores_empty_name(db):
    """名前を空にして「更新」を押しても、名前無しのマスタは作らない(登録フォームと同じ)。
    空名を通すと、一覧・報告書に名前の無い行ができる。"""
    did = store.add_distributor("山田太郎", db_path=db)
    at = _run(_MASTER_PAGE)
    at.button(key=f"edit_distributor_{did}").click().run()
    _edit_widget(at.text_input, "edit_name_distributor").set_value("   ")
    _submit_edit(at, f"edit_distributor_{did}")

    assert not at.exception
    assert {r["id"]: r for r in store.list_distributors(db_path=db)}[did]["name"] == "山田太郎"


def test_master_page_edit_button_for_active_and_inactive_rows(db):
    """編集は有効・停止中どちらの行にも出る(停止中も同じ一覧にインライン表示のため)。"""
    alive = store.add_distributor("現役の人", db_path=db)
    gone = store.add_distributor("辞めた人", active=0, db_path=db)
    at = _run(_MASTER_PAGE)
    keys = {b.key for b in at.button}
    assert f"edit_distributor_{alive}" in keys
    assert f"edit_distributor_{gone}" in keys


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
    assert any(b.label == "はい" for b in at.button)
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
    at.button(key=f"react_distributor_{gone}").click().run()
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
    at.button(key=f"deact_distributor_{did}_btn").click().run()
    at.button(key=f"deact_distributor_{did}_ok").click().run()
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
    """行ごとの削除ボタンはもう無い。チェックで選んだ行だけを一括削除で消せること。"""
    a = store.add_petty_cash("2026-07-10", None, 1000, memo="A", db_path=db)
    b = store.add_petty_cash("2026-07-11", None, 2000, memo="B", db_path=db)
    at = _run(_EXPENSE_PAGE)
    keys = {btn.key for btn in at.button}
    assert not any(k and k.startswith("del_petty_") for k in keys)

    rows = store.list_petty_cash(db_path=db)
    idx_b = next(i for i, r in enumerate(rows) if r["id"] == b)
    # AppTest の data_editor は edited_rows を渡した直後の1回の run() でしか反映されない
    # ため、選択のセットとボタンのクリック予約を同じ run() にまとめて渡す。
    at.session_state["petty_select"] = {
        "edited_rows": {idx_b: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="petty_bulk_del_btn").click()
    at.run()
    at.button(key="petty_bulk_del_ok").click().run()

    assert not at.exception
    ids = [r["id"] for r in store.list_petty_cash(db_path=db)]
    assert ids == [a]


def test_petty_delete_announces_in_the_list_tab(db):
    """削除のアナウンスは一覧タブに出て、登録タブに奪われないこと。
    (タブは1回の実行で全部描画されるため、section を付けないと先に描かれる
     登録タブの show_flash() がメッセージを消費してしまう)"""
    rid = store.add_petty_cash("2026-07-10", None, 1000, db_path=db)
    at = _run(_EXPENSE_PAGE)
    at.session_state["petty_select"] = {
        "edited_rows": {0: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="petty_bulk_del_btn").click()
    at.run()
    at.button(key="petty_bulk_del_ok").click().run()

    assert not at.exception
    assert [s.value for s in at.tabs[1].success] == ["1件を削除しました"]
    assert [s.value for s in at.tabs[0].success] == []


def _seed_petty(db):
    cat = store.add_expense_category("消耗品", db_path=db)
    store.add_petty_cash(date="2026-07-01", category_id=cat, amount=100, memo="A", db_path=db)
    store.add_petty_cash(date="2026-07-02", category_id=cat, amount=200, memo="B", db_path=db)
    return [r["id"] for r in store.list_petty_cash(db_path=db)]


def test_petty_bulk_delete_removes_only_selected(db):
    _seed_petty(db)
    # mode の radio は key 無し＝既定で先頭「小口」。Streamlit の tabs は1実行で全内容を
    # 描画するので、一覧タブの中身は既定状態で描画される（mode を触る必要はない）。
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"), default_timeout=30)
    at.run()
    # 先頭行(index 0)だけ選択。AppTest の data_editor は edited_rows を渡した直後の1回の
    # run() でしか反映されないため、選択のセットとボタンのクリック予約を同じ run() にまとめる。
    at.session_state["petty_select"] = {
        "edited_rows": {0: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="petty_bulk_del_btn").click()
    at.run()
    at.button(key="petty_bulk_del_ok").click().run()
    remaining = [r["id"] for r in store.list_petty_cash(db_path=db)]
    assert len(remaining) == 1  # 1件だけ消えた


def test_petty_per_row_delete_gone(db):
    _seed_petty(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"), default_timeout=30)
    at.run()
    keys = [b.key for b in at.button]
    assert not any(k and k.startswith("del_petty_") for k in keys)  # 行ごと削除は無い


def test_petty_whole_list_export_kept(db):
    _seed_petty(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"), default_timeout=30)
    at.run()
    # このstreamlitバージョンのAppTestには download_button ショートカットが無いため get() で拾う。
    # また download_button ノードは .key が None を返すため .id（key を含む内部ID）で見る。
    ids = [b.id for b in at.get("download_button")]
    assert any("petty_xlsx" in i for i in ids)  # section_export の全件Excelが残る


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


def test_original_statuses_come_from_common(db):
    """🟡 原本区分の選択肢は common(posting_logic.ORIGINAL_STATUSES)に一本化する。
    pages/01 と pages/05 に同じリストを二重定義すると、区分を1つ足したときに片方だけ
    増え、もう片方では「選べない値が既定になる」＝黙って先頭(原本あり)に落ちる。
    両ページが common の定数をそのまま使っていることを固定し、ハードコードへの
    退行(＝common に足しても追随しないページ)をここで捕まえる。"""
    from common import posting_logic

    at = _payable_page(db)
    assert _sel(at, "原本区分").options == posting_logic.ORIGINAL_STATUSES

    # 買掛先の「既定の原本区分」は新規登録ダイアログの中にある(Task 3で別窓化)ため、
    # ダイアログを開いてから selectbox を見る。
    at5 = _run("05_マスタ管理.py")
    at5.button(key="add_open_payables_vendor").click().run()
    opts = [s.options for s in at5.selectbox if s.label == "既定の原本区分"]
    assert opts and opts[0] == ["(なし)"] + posting_logic.ORIGINAL_STATUSES


def test_payable_no_caption_when_master_default_is_not_selectable(db):
    """🟡 caption と選択値を食い違わせないこと。
    マスタの既定が選択肢(ORIGINAL_STATUSES)に無い値のとき、selectbox は先頭
    「原本あり」に落ちる。caption の条件を `if _auto:` にすると、実際は「原本あり」が
    選ばれているのに「既定『謎の区分』を反映しました」と嘘の案内を出す。
    区分を1つ足したときに黙って壊れる型なので、caption 側も index と同じ条件で守る。"""
    store.add_payables_vendor("謎商事", default_original_status="謎の区分", db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.session_state["pay_draft"] = {"vendor": "謎商事", "amount": 5000,
                                     "date": "2026-07-17", "note": None}
    at.run()
    at.radio[0].set_value("買掛").run()

    assert not at.exception
    # 選択肢に無いので先頭に落ちる。そのときは「反映しました」と言ってはいけない。
    assert _sel(at, "原本区分").value == "原本あり"
    assert not any("反映しました" in c.value for c in at.caption)


def test_payable_list_deletes_the_right_row_and_announces(db):
    """行ごとの削除ボタンはもう無い。チェックで選んだ行だけを一括削除で消せること。"""
    a = store.add_payable(None, None, 1000, date="2026-07-10", vendor_name="A社", db_path=db)
    b = store.add_payable(None, None, 2000, date="2026-07-11", vendor_name="B社", db_path=db)
    at = _payable_page(db)
    keys = {btn.key for btn in at.button}
    assert not any(k and k.startswith("del_pay_") for k in keys)

    rows = store.list_payables(db_path=db)
    idx_b = next(i for i, r in enumerate(rows) if r["id"] == b)
    at.session_state["pay_select"] = {
        "edited_rows": {idx_b: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="pay_bulk_del_btn").click()
    at.run()
    at.button(key="pay_bulk_del_ok").click().run()

    assert not at.exception
    assert [r["id"] for r in store.list_payables(db_path=db)] == [a]
    assert [s.value for s in at.tabs[1].success] == ["1件を削除しました"]
    assert [s.value for s in at.tabs[0].success] == []


def test_receivable_list_deletes_the_right_row_and_announces(db):
    """行ごとの削除ボタンはもう無い。チェックで選んだ行だけを一括削除で消せること。"""
    cid = store.add_receivables_client("得意先", db_path=db)
    a = store.add_receivable("2026-07", cid, 1000, db_path=db)
    b = store.add_receivable("2026-07", cid, 2000, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.run()
    at.radio[0].set_value("売掛").run()
    keys = {btn.key for btn in at.button}
    assert not any(k and k.startswith("del_recv_") for k in keys)

    rows = store.list_receivables(db_path=db)
    idx_b = next(i for i, r in enumerate(rows) if r["id"] == b)
    at.session_state["recv_select"] = {
        "edited_rows": {idx_b: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="recv_bulk_del_btn").click()
    at.run()
    at.button(key="recv_bulk_del_ok").click().run()

    assert not at.exception
    assert [r["id"] for r in store.list_receivables(db_path=db)] == [a]
    assert [s.value for s in at.tabs[1].success] == ["1件を削除しました"]
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


def test_contract_list_shows_name_of_deactivated_distributor(db):
    """🔴 停止中方式の要(業務委託の一覧・ZIP出力)。停止中にした配布員でも、過去の請求の
    一覧には名前が出続けること。一覧の名前引き(id2name)は only_active を付けない。

    ここが only_active=True に退行すると、一覧の配布員が「?」になるだけでなく、
    ZIP出力のExcelの distributor_name が空文字になり、ファイル名も
    「業務完了報告書兼請求書__2026-07-17.xlsx」に化ける＝配布員名の無い報告書が本人に渡る。
    「配布員は移り変わりが激しい」が停止中方式の動機なので、辞めた配布員の過去請求は
    必ず通る経路。"""
    did, _, _ = _seed_invoice(db, pay_type="歩合", name="辞めた太郎")
    # 登録タブが「配布員が居ません」で st.stop しないよう、有効な配布員を1人残す
    store.add_distributor("現役の人", pay_type="歩合", db_path=db)
    store.update_distributor(did, active=0, db_path=db)   # 停止中にする

    at = _run(_CONTRACT_PAGE)
    assert not at.exception
    text = _rendered_text(at)
    assert "辞めた太郎" in text
    # 一覧の配布員列そのものが名前になっていること(「?」に落ちていない)
    listed = [df.value for df in at.dataframe if "配布員" in list(df.value.columns)]
    assert listed and list(listed[0]["配布員"]) == ["辞めた太郎"]


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


def test_contract_registration_jikyu_fills_unit_price_from_master(db):
    """🔴 時給は、マスタの時給額が単価に自動で入る(数量=時間 × 時給額)。"""
    store.add_distributor("時給の人", pay_type="時給", hourly_rate=1200, db_path=db)
    store.add_project("案件A", db_path=db)
    at = _contract_page_with_lines(db, "時給", {"案件": "案件A", "数量": 8.0, "部数": 1200})
    _click(at, "この請求を登録")

    assert not at.exception
    detail = store.get_contract_invoice(
        store.list_contract_invoices(db_path=db)[0]["id"], db_path=db)
    assert detail["lines"][0]["unit_price"] == 1200
    assert detail["lines"][0]["report_qty"] == 8
    assert detail["lines"][0]["amount"] == 9600
    assert detail["lines"][0]["copies"] == 1200


def test_contract_registration_getkyu_fills_monthly_rate_and_qty_one(db):
    """🔴 月給は、マスタの月額が単価に自動で入り、数量は1固定(月額をそのまま請求)。"""
    store.add_distributor("月給の人", pay_type="月給", monthly_rate=300000, db_path=db)
    store.add_project("案件A", db_path=db)
    # 数量は既定の1固定のまま。案件と部数だけ入れる。
    at = _contract_page_with_lines(db, "月給", {"案件": "案件A", "部数": 5000})
    _click(at, "この請求を登録")

    assert not at.exception
    detail = store.get_contract_invoice(
        store.list_contract_invoices(db_path=db)[0]["id"], db_path=db)
    assert detail["lines"][0]["unit_price"] == 300000
    assert detail["lines"][0]["report_qty"] == 1
    assert detail["lines"][0]["amount"] == 300000
    assert detail["lines"][0]["copies"] == 5000


def test_contract_zip_export_uses_saved_pay_type(db, monkeypatch):
    """🔴 ZIP出力は、マスタの現在値ではなく請求に焼き付けた支払形態で報告書を作ること。
    現在値を使うと、支払形態を変えた瞬間に過去の報告書の単位が化ける。"""
    from common import invoice_excel

    seen = []
    real = invoice_excel.build_invoice_xlsx

    def spy(**kw):
        seen.append(kw.get("pay_type"))
        return real(**kw)

    monkeypatch.setattr(invoice_excel, "build_invoice_xlsx", spy)

    did, _, iid = _seed_invoice(db, pay_type="日当", copies=3713)
    store.update_distributor(did, pay_type="歩合", db_path=db)   # マスタを後から変更

    at = AppTest.from_file(os.path.join(ROOT, "pages", _CONTRACT_PAGE), default_timeout=30)
    at.session_state["contract_list_editor"] = {
        "edited_rows": {0: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.run()

    assert not at.exception
    assert seen == ["日当"]


def test_contract_registration_download_uses_selected_pay_type(db, monkeypatch):
    """🔴 登録タブ。build_invoice_xlsx(..., pay_type=pay_type) の配線を守る。
    ZIP出力側(test_contract_zip_export_uses_saved_pay_type)と同型のスパイで、
    ダウンロード用の報告書生成に選択中の配布員の支払形態が渡っていることを確認する。
    ここは保存前のプレビューなので pay_type=None にすり替えられても他の172件は誰も気づかない
    (coverage gap)。ZIP側にはスパイがあるのに登録タブ側には無かった穴を塞ぐテスト。"""
    from common import invoice_excel

    seen = []
    real = invoice_excel.build_invoice_xlsx

    def spy(**kw):
        seen.append(kw.get("pay_type"))
        return real(**kw)

    monkeypatch.setattr(invoice_excel, "build_invoice_xlsx", spy)

    store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.add_project("案件A", db_path=db)
    at = _contract_page_with_lines(
        db, "日当", {"案件": "案件A", "数量": 3.0, "部数": 3713})

    assert not at.exception
    assert seen == ["日当"]


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
    """一覧は発行日の新しい順。a(07-17)が0行目、b(07-16)が1行目に来るので、
    1行目だけ選択してbだけが消えることを確かめる。"""
    _, pid, a = _seed_invoice(db, pay_type="歩合", name="A太郎")
    did_b = store.add_distributor("B太郎", pay_type="歩合", db_path=db)
    b = store.add_contract_invoice(did_b, "2026-07-16", "2026-07-01", "2026-07-15",
                                   [{"project_id": pid, "report_qty": 1, "unit_price": 100,
                                     "remark": "配布"}], db_path=db)
    at = _run(_CONTRACT_PAGE)
    keys = {btn.key for btn in at.button}
    assert not any(k and k.startswith("del_inv_") for k in keys)  # 行ごと削除は無い
    assert "invoice_bulk_del_btn" in keys

    at.session_state["contract_list_editor"] = {
        "edited_rows": {1: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="invoice_bulk_del_btn").click().run()
    at.button(key="invoice_bulk_del_ok").click().run()

    assert not at.exception
    assert [i["id"] for i in store.list_contract_invoices(db_path=db)] == [a]


def test_contract_delete_announces_in_the_list_tab(db):
    """削除のアナウンスは一覧タブに出て、先に描画される登録タブに奪われないこと。"""
    _, _, iid = _seed_invoice(db, pay_type="歩合")
    at = _run(_CONTRACT_PAGE)
    at.session_state["contract_list_editor"] = {
        "edited_rows": {0: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="invoice_bulk_del_btn").click().run()
    at.button(key="invoice_bulk_del_ok").click().run()

    assert not at.exception
    assert [s.value for s in at.tabs[1].success] == ["1件を削除しました"]
    assert [s.value for s in at.tabs[0].success] == []
    assert [i["id"] for i in store.list_contract_invoices(db_path=db)] == []


# ============================================================ Task 14: 号別明細
_ISSUE_PAGE = "03_号別明細.py"


def _issue_page(db, project="案件A"):
    """号(案件)を選んだ状態の号別明細ページ。既定の pills はプリセットの先頭案件を
    選ぶため、テストで作った案件を見るには session_state で選択を差し込む必要がある。"""
    at = AppTest.from_file(os.path.join(ROOT, "pages", _ISSUE_PAGE), default_timeout=30)
    at.session_state["proj_pills"] = project
    at.run()
    return at


def test_issue_page_renders(db):
    at = _run(_ISSUE_PAGE)
    assert not at.exception


def test_issue_page_shows_distributor_in_contract_breakdown(db):
    """業務委託の内訳に、誰の分の費用かが分かるよう配布員名が出ること。"""
    _seed_invoice(db, pay_type="歩合")
    at = _issue_page(db)
    assert not at.exception
    assert "山田太郎" in _rendered_text(at)


def test_issue_page_shows_distributor_for_petty(db):
    """雑費の内訳(小口行)に配布員名が出ること。"""
    did = store.add_distributor("佐藤花子", db_path=db)
    pid = store.add_project("案件A", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, project_id=pid,
                         distributor_id=did, db_path=db)
    at = _issue_page(db)
    assert not at.exception
    assert "佐藤花子" in _rendered_text(at)


def test_issue_page_shows_name_of_deactivated_distributor(db):
    """🔴 停止中方式の要。停止中にした配布員でも、過去の号別明細では名前が出続けること。
    登録の選択肢は only_active=True で引く一方、過去データの名前は停止中も含めて引く、
    という非対称性が守られているかを検証する。ここが壊れると過去データから名前が消える。"""
    did, pid, iid = _seed_invoice(db, pay_type="歩合")
    store.update_distributor(did, active=0, db_path=db)   # 停止中にする
    at = _issue_page(db)
    assert not at.exception
    assert "山田太郎" in _rendered_text(at)


def test_issue_page_shows_name_of_deactivated_distributor_for_petty(db):
    """🔴 停止中方式の要(雑費側)。小口の配布員名も停止中で消えないこと。
    _dist_names は業務委託と雑費で共有だが、片方だけ only_active を付ける改変も
    ここで捕まえる。"""
    did = store.add_distributor("辞めた花子", active=0, db_path=db)
    pid = store.add_project("案件A", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, project_id=pid,
                         distributor_id=did, db_path=db)
    at = _issue_page(db)
    assert not at.exception
    assert "辞めた花子" in _rendered_text(at)


def test_issue_page_payable_row_has_empty_distributor_cell(db):
    """買掛は配布員を持たない(オーナー判断で小口のみ)ため、雑費の内訳の配布員列は
    空欄になる。列自体は存在すること(小口行と列がずれないため)。"""
    pid = store.add_project("案件A", db_path=db)
    store.add_payable(None, None, 3000, date="2026-07-17", vendor_name="ABC商事",
                      project_id=pid, db_path=db)
    at = _issue_page(db)
    assert not at.exception
    misc = [t.value for t in at.table if "支払方法" in list(t.value.columns)]
    assert len(misc) == 1
    df = misc[0]
    assert list(df.columns) == ["配布員", "項目", "金額", "支払方法", "日付"]
    assert list(df["配布員"]) == [""]


def test_issue_page_contract_breakdown_column_order(db):
    """配布員は種別の左に置くこと(オーナー要望の並び)。"""
    _seed_invoice(db, pay_type="歩合")
    at = _issue_page(db)
    con = [t.value for t in at.table if "種別" in list(t.value.columns)]
    assert len(con) == 1
    assert list(con[0].columns) == ["配布員", "種別", "数量", "単価", "合計"]


def test_issue_page_nichito_qty_uses_saved_pay_type(db):
    """🔴 号別明細の数量も、請求に保存した支払形態で出すこと。
    マスタの現在値を使うと、配布員が日当→歩合に変わった瞬間に過去の号別明細の
    「3 日」が「3 枚」に化ける。"""
    did, _, _ = _seed_invoice(db, pay_type="日当", copies=3713)
    store.update_distributor(did, pay_type="歩合", db_path=db)   # マスタを後から変更
    at = _issue_page(db)
    text = _rendered_text(at)
    assert "3 日" in text
    assert "3 枚" not in text


def _spy_xlsx(monkeypatch):
    """出力されたExcelのバイト列を集めるスパイ。download_button の proto はバイト列を
    持たず(メディアURLだけ)、AppTest はrun後にランタイムを畳んでしまうため、
    出力の直前に必ず通る freeze_xlsx_bytes を覗いてバイト列を得る。
    ページは実行のたびに import し直されるので、run前に元モジュールを差し替えれば効く。"""
    from common import excel_io

    seen = []
    real = excel_io.freeze_xlsx_bytes

    def spy(data):
        out = real(data)
        seen.append(out)
        return out

    monkeypatch.setattr(excel_io, "freeze_xlsx_bytes", spy)
    return seen


def _genka_xlsx(seen):
    """集めたExcelのうち、号原価まとめ(業務委託シートを持つもの)を返す。
    freeze_xlsx_bytes を通さない実装に変わるとここで見つからず落ちる
    (＝内容が同じでもバイト列が変わりDL URLが404になる既知の地雷を守る)。"""
    import io

    import pandas as pd

    hits = [b for b in seen if "業務委託" in pd.ExcelFile(io.BytesIO(b)).sheet_names]
    assert len(hits) == 1
    return pd.ExcelFile(io.BytesIO(hits[0]))


def test_issue_page_genka_xlsx_has_distributor_column(db, monkeypatch):
    """号原価まとめExcelも画面と同じ列構成で、配布員名が中身に入っていること。"""
    import pandas as pd

    did, pid, _ = _seed_invoice(db, pay_type="歩合")
    store.add_petty_cash("2026-07-17", None, 1500, project_id=pid,
                         distributor_id=did, db_path=db)
    seen = _spy_xlsx(monkeypatch)
    at = _issue_page(db)
    assert not at.exception
    xls = _genka_xlsx(seen)
    con = pd.read_excel(xls, "業務委託")
    misc = pd.read_excel(xls, "雑費")
    assert list(con.columns) == ["配布員", "種別", "数量", "単価", "合計"]
    assert list(con["配布員"]) == ["山田太郎"]
    assert list(misc.columns) == ["配布員", "項目", "金額", "支払方法", "日付"]
    assert list(misc["配布員"]) == ["山田太郎"]


def test_issue_page_genka_xlsx_columns_when_empty(db, monkeypatch):
    """データが1件も無い号でも、Excelの列見出しは新しい構成のままであること
    (空のときだけ通る分岐なので、ここを直し忘れると経理側の取り込みで列がずれる)。"""
    import pandas as pd

    store.add_project("案件A", db_path=db)
    seen = _spy_xlsx(monkeypatch)
    at = _issue_page(db)
    assert not at.exception
    xls = _genka_xlsx(seen)
    assert list(pd.read_excel(xls, "業務委託").columns) == ["配布員", "種別", "数量", "単価", "合計"]
    assert list(pd.read_excel(xls, "雑費").columns) == ["配布員", "項目", "金額", "支払方法", "日付"]


def test_issue_page_houbai_still_shows_mai(db):
    """🔴 後方互換。pay_type が NULL の既存請求は今まで通り「枚」のまま。"""
    _seed_invoice(db, pay_type=None)
    at = _issue_page(db)
    text = _rendered_text(at)
    assert "3 枚" in text
    assert "3 日" not in text


def test_issue_page_keeps_deactivated_project(db):
    """🔴 案件を停止中にしても、号別明細から号が消えないこと。
    マスタ画面は「過去データを残すため、削除ではなく停止中にします（登録の選択肢から
    消えるだけで、一覧・報告書の表示は変わりません）」と案内している。号別明細は
    「登録の選択肢」ではなく「過去データの表示」なので、停止中も含めて引くのが正しい側。
    ここを only_active=True に戻すと、オーナーが古い号を整理した瞬間にページごと号が消える。"""
    _, pid, _ = _seed_invoice(db, pay_type="歩合")
    store.update_project(pid, active=0, db_path=db)   # 停止中にする
    at = _issue_page(db)
    assert not at.exception
    assert "案件A" in _rendered_text(at)


# ============================================================ ホーム
def _home_page():
    at = AppTest.from_file(os.path.join(ROOT, "home.py"), default_timeout=30)
    at.run()
    return at


def test_home_renders(db):
    at = _home_page()
    assert not at.exception


def test_home_keeps_deactivated_project(db):
    """🔴 ホームの号一覧も「過去データの表示」。停止中にした案件も出し続けること。
    only_active=True に戻すと、停止中にした瞬間にホームから号が消え、その号の
    コスト・売上・収支が誰からも見えなくなる。"""
    _, pid, _ = _seed_invoice(db, pay_type="歩合")
    store.update_project(pid, active=0, db_path=db)   # 停止中にする
    at = _home_page()
    assert not at.exception
    names = list(at.dataframe[0].value["案件"])
    assert "案件A" in names


def test_status_toggle_css_present():
    # 運用中の脈打ちアニメ・停止中のグレー・スコープ用クラスが CSS に入っている
    from common import ui as _ui
    assert "mstatpulse" in _ui._STYLE
    assert "st-key-mstat-on-" in _ui._STYLE
    assert "st-key-mstat-off-" in _ui._STYLE


# ============================================================ Task 3: 新規登録の別窓化
def test_each_tab_has_new_register_button(db):
    at = _run("05_マスタ管理.py")
    labels = [b.label for b in at.button]
    # 5タブぶんの「＋ 新規登録」ボタンが描画されている
    assert sum(1 for L in labels if "新規登録" in L) >= 5


def test_new_distributor_via_dialog(db):
    """🟡 AppTestの制約に注意。st.dialog は内部で st.fragment を使っており、本物の
    ブラウザでは「ダイアログ内のウィジェット操作＝そのダイアログだけの部分再実行」に
    なるため、"if st.button(open): dialog_fn()" の外側ボタンを押し直さなくても
    ダイアログは開いたままになる。しかしAppTestの .run() は常にフルスクリプトの
    再実行であり、fragment単位の再実行を再現しない。そのため
    「開くボタンを押す→.run()→中の入力欄をset_value()→.run()」のように
    開くボタンを押していない状態でrunすると、外側のif文が再びFalseになって
    dialog_fn() が呼ばれず、ダイアログの中身（追加ボタンごと）が消えてしまう
    （実際に確認済み。ページの実装・本番動作には問題無い＝これはテストハーネス側の
    制約）。そのため、氏名の入力と「追加」ボタンのクリックは、開くボタンを
    もう一度クリックしたのと同じ1回の .run() にまとめて送る。"""
    at = _run("05_マスタ管理.py")
    # 業務委託タブの新規登録を開く
    at.button(key="add_open_distributor").click().run()
    # ダイアログ内の氏名を入れる（この時点ではまだ送信しない）
    at.text_input(key="add_name_distributor").set_value("テスト太郎")
    # 開くボタンを再度「押した」ことにして、氏名入力・追加クリックと同じ1回の
    # 再実行でダイアログを再度呼び出す（フラグメント単位の再実行が無いための代替）。
    at.button(key="add_open_distributor").click()
    at.button(key="add_submit_distributor").click()
    at.run()
    names = [r["name"] for r in store.list_distributors(db_path=db)]
    assert "テスト太郎" in names


def test_edit_distributor_via_dialog(db):
    """🟡 AppTestの制約に注意(_submit_edit と同じ理由)。st.dialog は内部で st.fragment を
    使っており、本物のブラウザでは「ダイアログ内のウィジェット操作＝そのダイアログだけの
    部分再実行」になるため、開くボタンを押し直さなくてもダイアログは開いたままになる。
    しかしAppTestの .run() は常にフルスクリプトの再実行であり、fragment単位の再実行を
    再現しないため、氏名の入力と「更新」クリックは、開くボタンをもう一度「押した」ことに
    したのと同じ1回の .run() にまとめて送る(ページの実装・本番動作には問題無い＝これは
    テストハーネス側の制約。test_new_distributor_via_dialog と同じパターン)。"""
    store.add_distributor("編集前", kind="業務委託", pay_type="歩合", db_path=db)
    at = _run("05_マスタ管理.py")
    rid = [r["id"] for r in store.list_distributors(db_path=db) if r["name"] == "編集前"][0]
    at.button(key=f"edit_distributor_{rid}").click().run()
    at.text_input(key=f"edit_name_distributor_{rid}").set_value("編集後")
    at.button(key=f"edit_distributor_{rid}").click()
    at.button(key=f"edit_submit_distributor_{rid}").click()
    at.run()
    names = [r["name"] for r in store.list_distributors(db_path=db)]
    assert "編集後" in names and "編集前" not in names


def test_no_bottom_daily_section_label(db):
    # 日当金額の設定は編集窓に移り、ページ下部の独立セクションは無い
    store.add_distributor("日当さん", kind="業務委託", pay_type="日当", db_path=db)
    at = _run("05_マスタ管理.py")
    text = _rendered_text(at)
    assert "日当金額の設定" not in text


def test_status_toggle_deactivates(db):
    store.add_distributor("運用中さん", kind="業務委託", pay_type="歩合", db_path=db)
    at = _run("05_マスタ管理.py")
    rid = [r["id"] for r in store.list_distributors(db_path=db) if r["name"] == "運用中さん"][0]
    # 運用中トグル→確認→はい で停止中になる
    at.button(key=f"deact_distributor_{rid}_btn").click().run()
    at.button(key=f"deact_distributor_{rid}_ok").click().run()
    row = [r for r in store.list_distributors(db_path=db) if r["id"] == rid][0]
    assert not row["active"]


def test_inactive_shown_inline_and_reactivates(db):
    store.add_distributor("停止さん", kind="業務委託", pay_type="歩合", db_path=db)
    rid = [r["id"] for r in store.list_distributors(db_path=db) if r["name"] == "停止さん"][0]
    store.update_distributor(rid, active=0, db_path=db)
    at = _run("05_マスタ管理.py")
    # 折りたたみでなく同じ一覧に「停止中」トグルとして出る → 押すと有効に戻る
    at.button(key=f"react_distributor_{rid}").click().run()
    row = [r for r in store.list_distributors(db_path=db) if r["id"] == rid][0]
    assert row["active"]


def test_trash_only_for_unused(db):
    # 未使用の配布員には🗑(削除)、使用中には出ない
    store.add_distributor("未使用さん", kind="業務委託", pay_type="歩合", db_path=db)

    used_id = store.add_distributor("使用中さん", db_path=db)
    store.add_contract_invoice(
        used_id, "2026-07-17", "2026-07-01", "2026-07-31",
        [{"report_qty": 10, "unit_price": 100}], db_path=db)
    assert store.count_master_usage("distributor", used_id, db_path=db) > 0

    at = _run("05_マスタ管理.py")
    rid = [r["id"] for r in store.list_distributors(db_path=db) if r["name"] == "未使用さん"][0]
    keys = [b.key for b in at.button]
    assert f"del_distributor_{rid}_btn" in keys  # 未使用は🗑あり
    assert f"del_distributor_{used_id}_btn" not in keys  # 使用中には🗑が出ない(過去データを守るため)


def test_no_readonly_table_header(db):
    # 読み取り専用テーブルの見出し「配布員 氏名」等が本文に出ない（行リストに一本化）
    at = _run("05_マスタ管理.py")
    text = _rendered_text(at)
    assert "停止中（" not in text  # 折りたたみの見出しが無い


def test_bulk_delete_action_confirms_then_deletes():
    def _page():
        import streamlit as st
        from common.ui import bulk_delete_action, apply_app_style
        apply_app_style()
        # 削除された id を session_state に記録（AppTest.from_function はクロージャ不可のため）
        st.session_state.setdefault("_deleted", [])
        bulk_delete_action(
            [10, 20], delete_fn=lambda i: st.session_state["_deleted"].append(i),
            section="t", key="bd")

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_page).run()
    # 最初は削除ボタンのみ・まだ消えていない
    assert at.session_state["_deleted"] == []
    at.button(key="bd_btn").click().run()          # 削除ボタン→確認待ち
    assert at.session_state["_deleted"] == []      # 確認前は消えない
    at.button(key="bd_ok").click().run()           # はい
    assert at.session_state["_deleted"] == [10, 20]


def test_bulk_delete_action_cancel_does_not_delete():
    def _page():
        import streamlit as st
        from common.ui import bulk_delete_action, apply_app_style
        apply_app_style()
        st.session_state.setdefault("_deleted", [])
        bulk_delete_action([10], delete_fn=lambda i: st.session_state["_deleted"].append(i),
                           section="t", key="bd")

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_page).run()
    at.button(key="bd_btn").click().run()
    at.button(key="bd_no").click().run()           # やめる
    assert at.session_state["_deleted"] == []


def _seed_contract(db):
    did = store.add_distributor("配布太郎", kind="業務委託", pay_type="歩合", db_path=db)
    pid = store.add_project("A社チラシ", db_path=db)
    for d in ("2026-07-01", "2026-07-02"):
        store.add_contract_invoice(did, d, d, d,
            [{"project_id": pid, "report_qty": 1, "unit_price": 100,
              "remark": "配布", "other_label": None, "copies": None}],
            pay_type="歩合", db_path=db)
    return [i["id"] for i in store.list_contract_invoices(db_path=db)]


def test_contract_per_row_delete_gone(db):
    _seed_contract(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "02_業務委託登録.py"), default_timeout=30)
    at.run()
    keys = [b.key for b in at.button]
    assert not any(k and k.startswith("del_inv_") for k in keys)   # 行ごと削除は無い
    assert "invoice_bulk_del_btn" in keys                          # 選択削除がある


def test_contract_bulk_delete_removes_selected(db):
    _seed_contract(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "02_業務委託登録.py"), default_timeout=30)
    at.run()
    at.session_state["contract_list_editor"] = {
        "edited_rows": {0: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.button(key="invoice_bulk_del_btn").click().run()
    at.button(key="invoice_bulk_del_ok").click().run()
    assert len(store.list_contract_invoices(db_path=db)) == 1
