# デモ共有（Streamlit Cloud 常設・共有パスワード・サンプルデータ）実装計画

> TDD。ブランチ feature/demo-share（feature/revisions-6 から分岐）。ローカル通常利用(8502)は無変更（パスワード不要）＝ゲートは APP_PASSWORD がある時だけ。

**Goal:** posting-automation を Streamlit Community Cloud に常設できるようにする。①secrets→env橋渡し ②共有パスワードのログインゲート(APP_PASSWORDがある時だけ) ③DEMO_MODEで**架空データ**を投入(実名presetは使わない)。OCRは既に安全(未設定でも落ちない)＝変更不要。

## Global Constraints
- ブランチ feature/demo-share。データ層(store)のスキーマ不変。
- **デモは実名を出さない**: `seed_masters` は `_PRESET_*` に実在顧客名(関西ぱど等)を含むため、DEMO_MODE では **seed_masters を呼ばず** `demo_seed.seed_demo_if_empty()` で架空マスタ＋取引のみ投入。
- ログインゲートは `os.environ.get("APP_PASSWORD")` がある時だけ有効(=ローカルはパスワード不要のまま)。
- pytestはリポジトリルートから。全体 `python -m pytest -q` 緑。

---

### Task B: 架空デモデータのseed（common/demo_seed.py）

**Files:** Create `common/demo_seed.py`, `tests/test_demo_seed.py`

**Interface:** `seed_demo_if_empty(*, db_path=None) -> bool`（何か取引が既にあれば False で何もしない＝冪等。空なら架空マスタ＋取引を入れて True）。

- [ ] Step1: 失敗するテスト
```python
# tests/test_demo_seed.py
import os
from common import demo_seed
from common import posting_store as store


def test_seed_demo_populates_and_is_idempotent(tmp_path):
    db = os.path.join(tmp_path, "demo.db")
    store.init_db(db)
    assert demo_seed.seed_demo_if_empty(db_path=db) is True
    projs = store.list_projects(db_path=db)
    assert projs                              # 案件が入る
    assert store.list_distributors(db_path=db)  # 配布員(業務委託)が入る
    assert store.list_contract_invoices(db_path=db)  # 業務委託請求が入る
    assert store.list_petty_cash(db_path=db)     # 小口
    assert store.list_payables(db_path=db)       # 買掛
    assert store.list_receivables(db_path=db)    # 売掛
    # 実名presetを使っていない(架空名)
    names = " ".join(p["name"] for p in projs)
    assert "関西ぱど" not in names and "進和" not in names
    # 冪等: 2回目は何もしない
    before = len(store.list_contract_invoices(db_path=db))
    assert demo_seed.seed_demo_if_empty(db_path=db) is False
    assert len(store.list_contract_invoices(db_path=db)) == before
```

- [ ] Step2: 失敗確認 `python -m pytest tests/test_demo_seed.py -v` → FAIL

- [ ] Step3: 実装（`common/demo_seed.py`）。実storeのシグネチャに合わせる（add_project(name)/add_distributor(name,pay_type=)/add_expense_category(name)/add_payables_vendor(name)/add_receivables_client(name)/add_petty_cash(date,category_id,amount,project_id=,memo=)/add_payable(month,vendor_id,amount,date=,project_id=)/add_receivable(month,client_id,amount,project_id=)/add_contract_invoice(distributor_id,issue_date,period_from,period_to,lines,pay_type=)/add_issue_manual_cost(project_id,content,amount,work_date=)）。架空名のみ。例:
```python
from common import posting_store as store


def seed_demo_if_empty(*, db_path=None) -> bool:
    """デモ用の架空データを投入する。既に取引があれば何もしない(冪等)。実名は使わない。"""
    if (store.list_contract_invoices(db_path=db_path)
            or store.list_petty_cash(db_path=db_path)
            or store.list_receivables(db_path=db_path)
            or store.list_payables(db_path=db_path)):
        return False

    # --- 架空マスタ ---
    projA = store.add_project("デモ配布A号", db_path=db_path)
    projB = store.add_project("デモ配布B号", db_path=db_path)
    catP = store.add_expense_category("駐車場代", db_path=db_path)
    catD = store.add_expense_category("飲み物代", db_path=db_path)
    venR = store.add_payables_vendor("デモ不動産（家賃）", db_path=db_path)
    venE = store.add_payables_vendor("デモ電力", db_path=db_path)
    cliX = store.add_receivables_client("デモ広告主X", db_path=db_path)
    cliY = store.add_receivables_client("デモ広告主Y", db_path=db_path)
    dTaro = store.add_distributor("デモ太郎", pay_type="歩合", db_path=db_path)
    dHana = store.add_distributor("デモ花子", pay_type="日当", db_path=db_path)

    # --- 架空取引 ---
    # 売上(売掛)
    store.add_receivable("2026-07", cliX, 180000, project_id=projA, db_path=db_path)
    store.add_receivable("2026-07", cliY, 120000, project_id=projB, db_path=db_path)
    # 買掛(共通費)
    store.add_payable("2026-07", venR, 80000, date="2026-07-05", project_id=projA, db_path=db_path)
    store.add_payable("2026-07", venE, 15000, date="2026-07-06", project_id=projB, db_path=db_path)
    # 小口
    store.add_petty_cash("2026-07-03", catP, 2000, project_id=projA, memo="現場駐車", db_path=db_path)
    store.add_petty_cash("2026-07-04", catD, 1500, project_id=projA, memo="お茶", db_path=db_path)
    # 業務委託(配布員代)
    store.add_contract_invoice(dTaro, "2026-07-08", "2026-07-01", "2026-07-05",
        [{"project_id": projA, "report_qty": 3000, "unit_price": 3.5, "remark": "配布",
          "other_label": None, "copies": 3000}], pay_type="歩合", db_path=db_path)
    store.add_contract_invoice(dHana, "2026-07-09", "2026-07-02", "2026-07-03",
        [{"project_id": projB, "report_qty": 2, "unit_price": 8000, "remark": "配布",
          "other_label": None, "copies": 1800}], pay_type="日当", db_path=db_path)
    # 直接入力(配布員代)
    store.add_issue_manual_cost(projA, "丁合作業", 12000, work_date="2026-07-07", db_path=db_path)
    return True
```
（金額・件数は目安。add_* の戻り値がidであることを実storeで確認して使う。）

- [ ] Step4: パス確認 `python -m pytest tests/test_demo_seed.py -v` → PASS。全体 `python -m pytest -q` 緑。
- [ ] Step5: Commit `git add -A && git commit -m "feat: デモ用の架空データseed(実名preset不使用・冪等)"`

---

### Task A: app.py に secrets橋渡し＋ログインゲート＋DEMO_MODE分岐

**Files:** Modify `app.py`; Create `tests/test_app_gate.py`

- [ ] Step1: 失敗するテスト
```python
# tests/test_app_gate.py
import os
from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")


def test_login_gate_blocks_when_password_set_and_not_authenticated(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", os.path.join(tmp_path, "a.db"))
    monkeypatch.setenv("APP_PASSWORD", "demo123")
    monkeypatch.setenv("DEMO_MODE", "1")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    # 未認証: パスワード入力が出る
    assert any(getattr(i, "type", "") == "password" or i.label == "パスワード" for i in at.text_input)


def test_login_gate_absent_without_password(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", os.path.join(tmp_path, "b.db"))
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    # APP_PASSWORD無し=ログイン不要(パスワード入力は出ない)
    assert not any(i.label == "パスワード" for i in at.text_input)
```
> 注意: AppTest が st.navigation を扱えない場合は、ゲートのみを検証できる形にテストを調整してよい（アサーションの意味＝「APP_PASSWORD有り+未認証でパスワード入力が出る／無しで出ない」は保つ）。demo_seedを呼ぶDEMO_MODEでも例外なく描画されること。

- [ ] Step2: 失敗確認 → FAIL

- [ ] Step3: 実装（`app.py` を次の形に）:
```python
import os
import time
import streamlit as st

from common import posting_store as store
from common import auth
from common.ui import apply_app_style

# Streamlit Cloud の secrets を環境変数へ橋渡し(既存の os.environ ベースのコードがそのまま動く)
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:  # secrets 未設定でも落ちない
    pass

st.set_page_config(page_title="配布コスト管理", page_icon="📮", layout="wide")
apply_app_style()


@st.cache_resource
def _bootstrap_db():
    store.sync_from_remote()
    store.init_db()
    if os.environ.get("DEMO_MODE"):
        from common import demo_seed
        demo_seed.seed_demo_if_empty()   # 架空データ(実名presetは入れない)
    else:
        store.seed_masters()
    return True


_bootstrap_db()


def _render_login():
    st.markdown("## 📮 配布コスト管理")
    st.caption("共有パスワードを入力してください。")
    if auth.is_locked_out(st.session_state, time.time()):
        st.error("試行が続いたため一時的にロックしています。30秒ほど待って再度お試しください。")
    st.text_input("パスワード", type="password", key="login_pw")
    if st.button("ログイン", type="primary"):
        if not auth.is_locked_out(st.session_state, time.time()) and \
                auth.attempt_login(st.session_state.get("login_pw", ""), st.session_state, time.time()):
            st.rerun()
        else:
            st.error("パスワードが違います。")


if os.environ.get("APP_PASSWORD") and not auth.is_authenticated(st.session_state):
    _render_login()
    st.stop()

pages = [
    st.Page("pages/06_原価・売上まとめ.py", title="原価・売上まとめ", icon=":material/summarize:"),
    st.Page("pages/03_号別明細.py", title="号別明細", icon=":material/table_chart:", default=True),
    st.Page("pages/01_経費・買掛・売掛.py", title="小口・買掛・売掛", icon=":material/receipt_long:"),
    st.Page("pages/02_業務委託登録.py", title="業務委託登録", icon=":material/description:"),
    st.Page("pages/05_マスタ管理.py", title="マスタ管理", icon=":material/settings:"),
]
st.navigation(pages).run()
```
> ※ pages リストは現行(第6弾で原価・売上まとめを先頭に挿入済み)を維持すること。実ファイルを読んで現行のリストをそのまま使い、上の import/bridge/bootstrap/gate だけを足す形にする。

- [ ] Step4: パス確認 `python -m pytest tests/test_app_gate.py -v`。全体 `python -m pytest -q` 緑。
- [ ] Step5: Commit `git add -A && git commit -m "feat: secrets橋渡し＋共有パスワードのログインゲート＋DEMO_MODEで架空データ"`

---

### Task C: 公開手順書（私=コントローラが作成）
- `.streamlit/secrets.toml.example`（APP_PASSWORD / DEMO_MODE のテンプレ）
- `DEPLOY_DEMO.md`（GitHub push → share.streamlit.io 連携 → secrets設定 → デプロイ の手順）

## Self-Review
- 実名preset回避=DEMO_MODEでseed_mastersを呼ばない(TaskA)＋demo_seedは架空名(TaskB・テストで"関西ぱど"不在を検証)。
- ローカル無影響=ゲートはAPP_PASSWORD時のみ(TaskAテストで有/無を検証)。
- OCRは既存の握り(_ocr_files)で安全=変更不要。
