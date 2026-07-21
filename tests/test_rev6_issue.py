import os
from streamlit.testing.v1 import AppTest
from common import posting_logic
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(db):
    # 既定の pills はプリセットの先頭案件を選ぶため、テストで作った案件(A号)を
    # 見るには session_state で選択を差し込む必要がある(既存 test_pages_smoke.py と同様)。
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"), default_timeout=30)
    at.session_state["proj_pills"] = "A号"
    at.run()
    return at


def _rendered(at):
    parts = []
    for el in at.table: parts.append(el.value.to_string())
    for el in at.dataframe: parts.append(str(el.value))
    for el in at.markdown: parts.append(str(el.value))
    for el in at.caption: parts.append(str(el.value))
    return "\n".join(parts)


def _seed(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db); store.seed_masters(db_path=db)
    pid = store.add_project("A号", db_path=db)
    did = store.add_distributor("山田", kind="業務委託", pay_type="歩合", db_path=db)
    store.add_contract_invoice(did, "2026-07-05", "2026-07-01", "2026-07-03",
        [{"project_id": pid, "report_qty": 1, "unit_price": 100, "remark": "配布",
          "other_label": None, "copies": None}], pay_type="歩合", db_path=db)
    # 雑費(小口)を混ぜておく。配布原価(genka)=labor(100)+misc(50)=150 になるはずで、
    # これに買掛9999が混入すると150ではなく10149になる(数値で検証するため必須)。
    cat_id = store.list_expense_categories(db_path=db)[0]["id"]
    store.add_petty_cash("2026-07-03", cat_id, 50, project_id=pid, db_path=db)
    ven = store.add_payables_vendor("大家", db_path=db)
    store.add_payable(None, ven, 9999, date="2026-07-02", project_id=pid, db_path=db)
    return pid


def test_issue_shows_payment_date_for_contract(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = _run(db)
    text = _rendered(at)
    assert "支払日" in text            # 業務委託内訳に支払日列
    assert "2026-07-05" in text        # 発行日が支払日として出る


def test_issue_excludes_payable_from_cost(tmp_path, monkeypatch):
    """③: 買掛(9999)を配布原価に含めないこと。fmt_num はカンマ区切りで出すため、
    文字列 "9999" 不在だけの確認だと "9,999" 表記で素通りしてしまう(実際に発生した抜け)。
    ここでは配布原価(税込)の実数(150 = labor100+misc50)を、買掛混入時の値(10149)と
    区別できる形でyen表記ごと検証する。"""
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = _run(db)
    text = _rendered(at)
    genka_excluding_payable = f"¥{posting_logic.fmt_num(150)}"
    genka_including_payable = f"¥{posting_logic.fmt_num(150 + 9999)}"
    assert genka_excluding_payable in text        # 配布原価(税込) = 150(買掛を含めない)
    assert genka_including_payable not in text    # 買掛9999が混ざった10,149ではない
    assert "大家" not in text
