"""ページ名の変更と「大阪支社売上」ページの新設計（依頼⑧・2026-08-27 大橋様）。

・01 は「原価・売上登録」、06 は「大阪支社売上」
・06 は開いたら今月の売上がまずトップに出る
・売上/原価/利益/利益率に加えて 配布部数・挟み込み数 を小さく出す
・案件別の並びは 関西ぱど → アドバリュー → リビング → その他 → 空白
"""
import datetime as _dt
import os

from streamlit.testing.v1 import AppTest

from common import posting_logic
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(page, db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", page), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _text(at):
    parts = [str(m.value) for m in at.markdown]
    parts += [str(c.value) for c in at.caption]
    parts += [str(t.value) for t in at.title]
    for el in at.table:
        parts.append(el.value.to_string())
    return "\n".join(parts)


# ===== ページ名 =====


def test_page_01_is_renamed_to_genka_uriage_touroku(tmp_path, monkeypatch):
    at = _run("01_経費・買掛・売掛.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    assert [str(t.value) for t in at.title] == ["原価・売上登録"]


def test_page_06_is_renamed_to_osaka_shisha_uriage(tmp_path, monkeypatch):
    at = _run("06_原価・売上まとめ.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    assert [str(t.value) for t in at.title] == ["大阪支社売上"]


def test_sidebar_names_match_the_new_page_titles():
    """サイドバーの表示名は app.py の st.Page(title=...) が決める
    (ファイル名ではないので、ページのファイル名は据え置きでよい)。"""
    import re

    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    titles = re.findall(r'title="([^"]+)"', src)
    assert "大阪支社売上" in titles
    assert "原価・売上登録" in titles
    # 旧名がサイドバーに残っていないこと
    assert "原価・売上まとめ" not in titles
    assert "小口・買掛・売掛" not in titles


# ===== 開いたら今月 =====


def test_osaka_page_defaults_to_this_month(tmp_path, monkeypatch):
    """🔴 依頼⑧-3: 開いたら今月の売上がまずトップに出ること。"""
    at = _run("06_原価・売上まとめ.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    assert at.pills(key="summary_period_pills").value == "今月"
    lo, hi = posting_logic.period_range("month")
    assert f"{lo} 〜 {hi}" in _text(at)


def test_osaka_page_shows_this_months_numbers_not_everything(tmp_path, monkeypatch):
    """先月の売上が今月の数字に混ざらないこと（既定が全期間のままだと混ざる）。"""
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    today = _dt.date.today()
    last = (today.replace(day=1) - _dt.timedelta(days=1))
    store.add_receivable(f"{today:%Y-%m}", None, 111111, db_path=db)
    store.add_receivable(f"{last:%Y-%m}", None, 999999, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception
    text = _text(at)
    assert f"¥{posting_logic.fmt_num(111111)}" in text
    assert f"¥{posting_logic.fmt_num(111111 + 999999)}" not in text


# ===== 配布部数・挟み込み数 =====


def _seed_delivery(db):
    pid = next(p["id"] for p in store.list_projects(db_path=db)
               if p["name"] == "関西ぱど：京阪北版")
    did = store.add_distributor("山田", pay_type="歩合", db_path=db)
    today = _dt.date.today().isoformat()
    store.add_contract_invoice(
        did, today, today, today,
        [{"project_id": pid, "report_qty": 3000, "unit_price": 3, "remark": "配布",
          "other_label": None, "copies": None},
         {"project_id": pid, "report_qty": 800, "unit_price": 1, "remark": "挟み込み",
          "other_label": None, "copies": None},
         {"project_id": pid, "report_qty": 1, "unit_price": 500, "remark": "交通費",
          "other_label": None, "copies": None}],
        pay_type="歩合", db_path=db)


def test_osaka_page_shows_delivery_and_insert_counts(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    _seed_delivery(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception
    text = _text(at)
    assert "配布部数（冊子・チラシ）" in text
    assert "挟み込み数" in text
    assert "3,000 部" in text
    assert "800 部" in text


def test_delivery_counts_are_shown_smaller_than_the_money_figures(tmp_path, monkeypatch):
    """🔴 依頼⑧-4: 部数はモチベーション向けの副次情報。売上・原価・利益・利益率
    より小さい文字で出すこと(同じ大きさだと主役が入れ替わって見える)。"""
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    _seed_delivery(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"),
                           default_timeout=60)
    at.run()
    import re

    def _value_font_size(block):
        sizes = [float(x) for x in re.findall(r"font-size:([\d.]+)rem", block)]
        return max(sizes) if sizes else 0.0

    money = [str(m.value) for m in at.markdown if "売上（税込）" in str(m.value)]
    counts = [str(m.value) for m in at.markdown if "挟み込み数" in str(m.value)]
    assert money and counts
    assert _value_font_size(counts[0]) < _value_font_size(money[0])


def test_osaka_page_shows_profit_rate(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    today = _dt.date.today()
    store.add_receivable(f"{today:%Y-%m}", None, 100000, db_path=db)
    store.add_petty_cash(today.isoformat(), None, 25000, db_path=db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"),
                           default_timeout=60)
    at.run()
    text = _text(at)
    assert "利益率" in text
    assert "75.0%" in text


def test_profit_rate_does_not_crash_when_there_are_no_sales(tmp_path, monkeypatch):
    """🔴 売上0で割り算すると落ちる。0%とも書かない(意味が変わるため)。"""
    at = _run("06_原価・売上まとめ.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    text = _text(at)
    assert "利益率" in text
    assert "—" in text


# ===== 案件別の並び順 =====


def test_project_table_is_ordered_the_way_ohashi_san_asked(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db")
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db)
    store.seed_masters(db_path=db)
    ids = {p["name"]: p["id"] for p in store.list_projects(db_path=db)}
    month = f"{_dt.date.today():%Y-%m}"
    store.add_receivable(month, None, 10, project_id=ids["その他"],
                         other_label="買取専科", db_path=db)
    store.add_receivable(month, None, 20, project_id=ids["リビングプロシード"], db_path=db)
    store.add_receivable(month, None, 30, project_id=ids["アドバリュー"],
                         other_label="8-1", db_path=db)
    store.add_receivable(month, None, 40, project_id=ids["関西ぱど：京阪北版"], db_path=db)
    store.add_receivable(month, None, 50, db_path=db)          # 案件未設定＝空白
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception
    table = next(t for t in at.table if "案件" in t.value.columns)
    names = [str(v) for v in table.value["案件"].tolist()]
    order = [next(i for i, n in enumerate(names) if n.startswith(head))
             for head in ("関西ぱど", "アドバリュー", "リビング", "その他")]
    assert order == sorted(order), f"並びが依頼どおりでない: {names}"
    assert names[-1].strip() == "", f"区分未設定の行が最後に来ていない: {names}"


# ===== 追加依頼1: 期間選択の並び順（2026-08-28） =====


def test_period_filter_order_is_month_week_all_custom(tmp_path, monkeypatch):
    """開いたとき一番上（先頭）に見えるのが「今月」であること。"""
    at = _run("06_原価・売上まとめ.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    assert list(at.pills(key="summary_period_pills").options) == [
        "今月", "今週", "全期間", "期間指定"]


def test_period_filter_order_elsewhere_is_unchanged(tmp_path, monkeypatch):
    """並び替えたのは大阪支社売上ページだけ。他の画面は今までどおり全期間が先頭。"""
    at = _run("01_経費・買掛・売掛.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    assert list(at.pills(key="petty_period_pills").options)[0] == "全期間"


# ===== 追加依頼2: 一括生成の位置（2026-08-28） =====


def test_bulk_export_sits_right_below_the_project_table(tmp_path, monkeypatch):
    """🔴 ページの一番下だと気づかれない（大橋様）。案件別 原価・売上の表のすぐ下に置く。

    描画順は AppTest の要素リストからは取れないため、ページの記述順で固定する
    （Streamlit は上から順に描くので記述順＝表示順）。
    """
    src = open(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"), encoding="utf-8").read()
    i_proj = src.index("案件別 原価・売上")
    i_bulk = src.index("月次の会議用売上表を一括生成")
    i_tabs = src.index('st.tabs(["原価", "売上"])')
    assert i_proj < i_bulk < i_tabs, "一括生成が案件別の表の直下に無い"

    # 実際に描かれてもいること（記述順だけ直して壊すのを防ぐ）
    at = _run("06_原価・売上まとめ.py", os.path.join(tmp_path, "t.db"), monkeypatch)
    labels = [str(e.label) for e in at.get("expander")]
    assert any("月次の会議用売上表" in l for l in labels)
    assert [t.label for t in at.tabs][:2] == ["原価", "売上"]
