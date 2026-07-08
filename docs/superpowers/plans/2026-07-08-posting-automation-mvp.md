# ポスティング部門 業務自動化アプリ（第1弾MVP）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 配布（ポスティング）部門の経費・買掛・売掛の登録、業務委託費→完了報告書兼請求書のExcel生成、号別コスト集約、経理提出出力を1つのStreamlitアプリで行えるようにする。

**Architecture:** テレアポアプリ(`telapo-automation`)の実証済み `common/` 資産（ui/db_sync/auth/excel_io/bedrock_client）を流用した独立アプリ。データはSQLite(`data/posting.db`)に蓄積し、すべて「案件名(号)」で串刺しして③号別・④経理へ自動集約する。ロジックは純粋関数に分離してTDDで検証、UIページは実機(Playwright)で確認する。

**Tech Stack:** Python 3.11 / Streamlit / pandas / openpyxl / boto3(Bedrock Claude Vision) / pytest

## Global Constraints

- Python 3.11。既存テレアポアプリと同じ流儀に従う（勝手に別構造へ再編しない）。
- 金額は**税込・整数（円）**を基本とする。列名・区分値は本plan記載の文字列を**そのまま**使う。
- store系の全公開関数は `db_path=None`（テスト用DB差し替え）と、書込関数は `now=None`（決定的タイムスタンプ）を受け取る。書込後は `_push_remote(db_path)` を呼ぶ（S3未設定なら no-op）。
- CSV出力は先頭にBOM(`﻿`)を付け、Excelで文字化けしないようにする。
- テストは `pytest`。SQLite系テストは必ず一時ファイルの `db_path` を渡し、実DB(`data/posting.db`)を汚さない。
- 配布委託先の区分値は `業務委託 / 自社社員 / アルバイト`。委託明細の備考値は `配布 / 挟み込み / 交通費 / 手当 / その他`。買掛の原本区分値は `原本あり / 本社 / クレジット / 振込用紙 / なし`。
- 秘密情報・実DBはコミットしない（`.gitignore`済）。テンプレxlsxは追跡する。

---

## File Structure

```
posting-automation/
├── app.py                       ← st.navigation。MVPはログインゲート無し
├── home.py                      ← ホーム(号別コスト概況カード)
├── conftest.py                  ← import path 用(telapoと同型)
├── requirements.txt
├── common/
│   ├── __init__.py
│   ├── ui.py                    ← telapoから流用(そのままコピー)
│   ├── db_sync.py               ← telapoから流用(そのままコピー)
│   ├── auth.py                  ← telapoから流用(MVPは未使用)
│   ├── excel_io.py              ← telapoから流用(read_table_bytes等)
│   ├── bedrock_client.py        ← telapoから流用+画像対応を追加
│   ├── posting_store.py         ← 新規: SQLite読み書き
│   ├── posting_logic.py         ← 新規: 集計・部数・収支の純粋関数
│   ├── ocr.py                   ← 新規: レシート/請求書 画像→項目抽出
│   └── invoice_excel.py         ← 新規: 完了報告書兼請求書テンプレ流し込み
├── pages/
│   ├── 01_経費・買掛・売掛.py
│   ├── 02_業務委託・請求書.py
│   ├── 03_号別明細.py
│   ├── 04_経理提出出力.py
│   └── 05_マスタ管理.py
├── templates/業務完了報告書兼請求書テンプレート.xlsx
├── data/posting.db              ← .gitignore
└── tests/
    ├── test_posting_store.py
    ├── test_posting_logic.py
    ├── test_invoice_excel.py
    └── test_ocr.py
```

---

### Task 1: プロジェクト雛形とcommon資産の流用

**Files:**
- Create: `requirements.txt`, `conftest.py`, `common/__init__.py`, `app.py`, `home.py`
- Create(copy): `common/ui.py`, `common/db_sync.py`, `common/auth.py`, `common/excel_io.py`, `common/bedrock_client.py`（`telapo-automation/common/` からコピー）
- Create(copy): `templates/業務完了報告書兼請求書テンプレート.xlsx`（`Downloads/業務完了報告書　兼　請求書 (1).xlsx` からコピー）
- Create: `common/posting_store.py`（スキーマのみ）
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces: `posting_store.init_db(db_path=None) -> None`、`posting_store._connect(db_path=None)`、SQLiteスキーマ（全マスタ・データ表）。

- [ ] **Step 1: common資産とテンプレをコピー**

```bash
cd "C:/Users/moro/posting-automation"
mkdir -p common pages templates tests data
cp "C:/Users/moro/telapo-automation/common/__init__.py" common/
cp "C:/Users/moro/telapo-automation/common/ui.py" common/
cp "C:/Users/moro/telapo-automation/common/db_sync.py" common/
cp "C:/Users/moro/telapo-automation/common/auth.py" common/
cp "C:/Users/moro/telapo-automation/common/excel_io.py" common/
cp "C:/Users/moro/telapo-automation/common/bedrock_client.py" common/
cp "C:/Users/moro/telapo-automation/conftest.py" conftest.py
cp "C:/Users/moro/Downloads/業務完了報告書　兼　請求書 (1).xlsx" "templates/業務完了報告書兼請求書テンプレート.xlsx"
```

- [ ] **Step 2: requirements.txt を作成**

```
streamlit>=1.40
pandas>=2.0
openpyxl>=3.1
boto3>=1.34
pytest>=8.0
Pillow>=10.0
```

- [ ] **Step 3: 失敗するテストを書く（スキーマ作成の確認）**

`tests/test_posting_store.py`:

```python
import os
from common import posting_store as store

TABLES = {
    "projects", "expense_categories", "payables_vendors",
    "receivables_clients", "distributors",
    "petty_cash", "payables", "receivables",
    "contract_invoices", "contract_invoice_lines", "issue_manual_costs",
}


def _table_names(db_path):
    conn = store._connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def test_init_db_creates_all_tables(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.init_db(db)
    assert TABLES.issubset(_table_names(db))
```

- [ ] **Step 4: テスト失敗を確認**

Run: `cd "C:/Users/moro/posting-automation" && python -m pytest tests/test_posting_store.py -v`
Expected: FAIL（`common.posting_store` が無い / テーブル未定義）

- [ ] **Step 5: posting_store.py にスキーマを実装**

`common/posting_store.py`:

```python
import csv
import io
import os
import sqlite3
from datetime import datetime

from common import db_sync

DEFAULT_DB_PATH = os.path.join("data", "posting.db")
_UNSET = object()


def _resolve_db_path(db_path=None) -> str:
    return db_path or os.environ.get("POSTING_DB_PATH") or DEFAULT_DB_PATH


def _push_remote(db_path=None) -> None:
    db_sync.push_db(_resolve_db_path(db_path))


def sync_from_remote(*, db_path=None) -> bool:
    return db_sync.pull_db(_resolve_db_path(db_path))


def _connect(db_path=None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _now(now):
    return now if now is not None else datetime.now().isoformat(timespec="seconds")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS expense_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS payables_vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, default_category TEXT, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS receivables_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS distributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '業務委託',
            active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS petty_cash (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, category_id INTEGER, amount INTEGER NOT NULL,
            project_id INTEGER, memo TEXT, source TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS payables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT, vendor_id INTEGER, amount INTEGER NOT NULL,
            original_status TEXT, note TEXT, project_id INTEGER,
            source TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receivables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT, client_id INTEGER, amount INTEGER NOT NULL,
            note TEXT, project_id INTEGER, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contract_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distributor_id INTEGER, issue_date TEXT,
            period_from TEXT, period_to TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contract_invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL, project_id INTEGER,
            report_qty INTEGER NOT NULL DEFAULT 0, unit_price INTEGER NOT NULL DEFAULT 0,
            amount INTEGER NOT NULL DEFAULT 0, remark TEXT);
        CREATE TABLE IF NOT EXISTS issue_manual_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER, content TEXT, amount INTEGER NOT NULL,
            created_at TEXT NOT NULL);
        """
    )
    conn.commit()


def init_db(db_path=None) -> None:
    _connect(db_path).close()
```

- [ ] **Step 6: テスト成功を確認**

Run: `cd "C:/Users/moro/posting-automation" && python -m pytest tests/test_posting_store.py -v`
Expected: PASS

- [ ] **Step 7: app.py / home.py を作成（ログインゲート無し）**

`app.py`:

```python
import streamlit as st

from common import posting_store as store
from common.ui import apply_app_style

st.set_page_config(page_title="配布コスト管理", page_icon="📮", layout="wide")
apply_app_style()


@st.cache_resource
def _bootstrap_db():
    store.sync_from_remote()
    store.init_db()
    return True


_bootstrap_db()

pages = [
    st.Page("home.py", title="配布コスト管理", icon=":material/dashboard:", default=True),
    st.Page("pages/01_経費・買掛・売掛.py", title="経費・買掛・売掛", icon=":material/receipt_long:"),
    st.Page("pages/02_業務委託・請求書.py", title="業務委託・請求書", icon=":material/description:"),
    st.Page("pages/03_号別明細.py", title="号別明細", icon=":material/table_chart:"),
    st.Page("pages/04_経理提出出力.py", title="経理提出出力", icon=":material/download:"),
    st.Page("pages/05_マスタ管理.py", title="マスタ管理", icon=":material/settings:"),
]
st.navigation(pages).run()
```

`home.py`（この時点ではプレースホルダのページ。集計は Task 6 で差し替え）:

```python
import streamlit as st

st.title("📮 配布コスト管理")
st.caption("経費・買掛・売掛、業務委託請求書、号別コストを一元管理します。")
st.info("左のメニューから各機能を開いてください。")
```

Task 8〜12 で各 `pages/*.py` を作るまで `app.py` は起動しない（存在しないページ参照でエラー）。**そのため Step 7 では app.py/home.py の作成のみ行い、起動確認は Task 8 以降で行う。**

- [ ] **Step 8: コミット**

```bash
cd "C:/Users/moro/posting-automation"
git add -A
git commit -m "feat: プロジェクト雛形・common流用・SQLiteスキーマ"
```

---

### Task 2: マスタCRUDとプリセット投入

**Files:**
- Modify: `common/posting_store.py`（マスタ関数を追記）
- Test: `tests/test_posting_store.py`（追記）

**Interfaces:**
- Produces:
  - `add_master(table, **fields) -> int`（内部）／各公開関数:
  - `add_project(name, *, active=1, db_path=None) -> int` / `list_projects(*, only_active=False, db_path=None) -> list[dict]` / `update_project(id, *, name=_UNSET, active=_UNSET, db_path=None)` / `delete_project(id, *, db_path=None)`
  - 同型で `expense_category`(name)、`payables_vendor`(name, default_category)、`receivables_client`(name)、`distributor`(name, kind)
  - `seed_masters(*, db_path=None) -> None`（空のとき既定値を投入。冪等）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_posting_store.py` に追記:

```python
def test_add_and_list_project(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("関西ぱど：京阪北版", db_path=db)
    rows = store.list_projects(db_path=db)
    assert any(r["id"] == pid and r["name"] == "関西ぱど：京阪北版" for r in rows)


def test_update_and_soft_delete_project(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("旧名", db_path=db)
    store.update_project(pid, name="新名", db_path=db)
    store.update_project(pid, active=0, db_path=db)
    active = store.list_projects(only_active=True, db_path=db)
    assert all(r["id"] != pid for r in active)
    allrows = store.list_projects(db_path=db)
    assert any(r["id"] == pid and r["name"] == "新名" for r in allrows)


def test_distributor_kind_stored(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("黒瀬", kind="自社社員", db_path=db)
    rows = store.list_distributors(db_path=db)
    assert any(r["id"] == did and r["kind"] == "自社社員" for r in rows)


def test_seed_masters_is_idempotent(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.seed_masters(db_path=db)
    store.seed_masters(db_path=db)
    names = {r["name"] for r in store.list_projects(db_path=db)}
    assert "アドバリュー" in names
    vendors = {r["name"] for r in store.list_payables_vendors(db_path=db)}
    assert "大東建託パートナーズ株式会社" in vendors
    clients = {r["name"] for r in store.list_receivables_clients(db_path=db)}
    assert "株式会社アド・バリュー" in clients
    # 2回呼んでも重複しない
    assert len(store.list_receivables_clients(db_path=db)) == len(set(clients))
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/test_posting_store.py -k "project or distributor or seed" -v`
Expected: FAIL（関数未定義）

- [ ] **Step 3: マスタ関数を実装**

`common/posting_store.py` に追記:

```python
def _add(table, columns, values, db_path):
    conn = _connect(db_path)
    try:
        cols = ", ".join(columns)
        ph = ", ".join("?" for _ in columns)
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", values)
        conn.commit()
        new_id = int(cur.lastrowid)
    finally:
        conn.close()
    _push_remote(db_path)
    return new_id


def _list(table, only_active, db_path):
    conn = _connect(db_path)
    try:
        sql = f"SELECT * FROM {table}"
        if only_active:
            sql += " WHERE active=1"
        sql += " ORDER BY id"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _update(table, row_id, fields, db_path):
    sets = {k: v for k, v in fields.items() if v is not _UNSET}
    if not sets:
        return
    assignments = ", ".join(f"{k}=?" for k in sets)
    conn = _connect(db_path)
    try:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?",
                     (*sets.values(), int(row_id)))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)


def _delete(table, row_id, db_path):
    conn = _connect(db_path)
    try:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (int(row_id),))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)


# --- projects ---
def add_project(name, *, active=1, db_path=None):
    return _add("projects", ["name", "active"], [name, int(active)], db_path)
def list_projects(*, only_active=False, db_path=None):
    return _list("projects", only_active, db_path)
def update_project(row_id, *, name=_UNSET, active=_UNSET, db_path=None):
    _update("projects", row_id, {"name": name, "active": active}, db_path)
def delete_project(row_id, *, db_path=None):
    _delete("projects", row_id, db_path)

# --- expense_categories ---
def add_expense_category(name, *, active=1, db_path=None):
    return _add("expense_categories", ["name", "active"], [name, int(active)], db_path)
def list_expense_categories(*, only_active=False, db_path=None):
    return _list("expense_categories", only_active, db_path)
def update_expense_category(row_id, *, name=_UNSET, active=_UNSET, db_path=None):
    _update("expense_categories", row_id, {"name": name, "active": active}, db_path)
def delete_expense_category(row_id, *, db_path=None):
    _delete("expense_categories", row_id, db_path)

# --- payables_vendors ---
def add_payables_vendor(name, *, default_category=None, active=1, db_path=None):
    return _add("payables_vendors", ["name", "default_category", "active"],
                [name, default_category, int(active)], db_path)
def list_payables_vendors(*, only_active=False, db_path=None):
    return _list("payables_vendors", only_active, db_path)
def update_payables_vendor(row_id, *, name=_UNSET, default_category=_UNSET, active=_UNSET, db_path=None):
    _update("payables_vendors", row_id,
            {"name": name, "default_category": default_category, "active": active}, db_path)
def delete_payables_vendor(row_id, *, db_path=None):
    _delete("payables_vendors", row_id, db_path)

# --- receivables_clients ---
def add_receivables_client(name, *, active=1, db_path=None):
    return _add("receivables_clients", ["name", "active"], [name, int(active)], db_path)
def list_receivables_clients(*, only_active=False, db_path=None):
    return _list("receivables_clients", only_active, db_path)
def update_receivables_client(row_id, *, name=_UNSET, active=_UNSET, db_path=None):
    _update("receivables_clients", row_id, {"name": name, "active": active}, db_path)
def delete_receivables_client(row_id, *, db_path=None):
    _delete("receivables_clients", row_id, db_path)

# --- distributors ---
def add_distributor(name, *, kind="業務委託", active=1, db_path=None):
    return _add("distributors", ["name", "kind", "active"], [name, kind, int(active)], db_path)
def list_distributors(*, only_active=False, db_path=None):
    return _list("distributors", only_active, db_path)
def update_distributor(row_id, *, name=_UNSET, kind=_UNSET, active=_UNSET, db_path=None):
    _update("distributors", row_id, {"name": name, "kind": kind, "active": active}, db_path)
def delete_distributor(row_id, *, db_path=None):
    _delete("distributors", row_id, db_path)


_PRESET_PROJECTS = ["関西ぱど：京阪北版", "関西ぱど：京阪南版", "アドバリュー",
                    "リビングプロシード", "その他"]
_PRESET_CATEGORIES = ["駐車場代", "飲み物代", "その他"]
_PRESET_VENDORS = [
    ("京阪総合サービス株式会社", "ゴミ収集"),
    ("大東建託パートナーズ株式会社", "家賃"),
    ("NTTファイナンス株式会社", "電話"),
    ("NTTコミュニケーション株式会社", "プロバイダ"),
    ("関西電力株式会社", "電気"),
    ("株式会社スペースリーダー", "機械警備"),
    ("株式会社トヨタレンタリース大阪", "リース"),
    ("株式会社ネクストレベル", "派遣"),
    ("キャノンマーケティングジャパン株式会社", "コピー代"),
    ("株式会社 CLOVER JAPAN", "配布"),
    ("配夢株式会社", "配布"),
]
_PRESET_CLIENTS = ["株式会社関西ぱど　北大阪営業部", "株式会社進和プロモーション 大阪支社",
                   "株式会社アド・バリュー", "株式会社リビングプロシード"]


def seed_masters(*, db_path=None) -> None:
    if not list_projects(db_path=db_path):
        for n in _PRESET_PROJECTS:
            add_project(n, db_path=db_path)
    if not list_expense_categories(db_path=db_path):
        for n in _PRESET_CATEGORIES:
            add_expense_category(n, db_path=db_path)
    if not list_payables_vendors(db_path=db_path):
        for n, c in _PRESET_VENDORS:
            add_payables_vendor(n, default_category=c, db_path=db_path)
    if not list_receivables_clients(db_path=db_path):
        for n in _PRESET_CLIENTS:
            add_receivables_client(n, db_path=db_path)
```

- [ ] **Step 4: テスト成功を確認**

Run: `python -m pytest tests/test_posting_store.py -v`
Expected: PASS（全件）

- [ ] **Step 5: app.py起動時に seed を呼ぶ**

`app.py` の `_bootstrap_db()` の `store.init_db()` の直後に `store.seed_masters()` を追加する:

```python
    store.sync_from_remote()
    store.init_db()
    store.seed_masters()
    return True
```

- [ ] **Step 6: コミット**

```bash
git add -A && git commit -m "feat: マスタCRUD(5種)とプリセット投入"
```

---

### Task 3: データ表CRUD（小口・買掛・売掛）

**Files:**
- Modify: `common/posting_store.py`
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces:
  - `add_petty_cash(date, category_id, amount, *, project_id=None, memo=None, source="manual", db_path=None, now=None) -> int`、`list_petty_cash(*, project_id=None, date_from=None, date_to=None, db_path=None) -> list[dict]`、`delete_petty_cash(id, *, db_path=None)`
  - `add_payable(month, vendor_id, amount, *, original_status=None, note=None, project_id=None, source="manual", db_path=None, now=None) -> int`、`list_payables(*, month=None, project_id=None, db_path=None)`、`delete_payable(id, *, db_path=None)`
  - `add_receivable(month, client_id, amount, *, note=None, project_id=None, db_path=None, now=None) -> int`、`list_receivables(*, month=None, project_id=None, db_path=None)`、`delete_receivable(id, *, db_path=None)`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_petty_cash_roundtrip_and_filter(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    a = store.add_petty_cash("2026-06-19", 1, 1200, project_id=3, memo="駐車場", db_path=db, now="T")
    store.add_petty_cash("2026-06-25", 1, 500, db_path=db, now="T")
    assert len(store.list_petty_cash(db_path=db)) == 2
    only = store.list_petty_cash(project_id=3, db_path=db)
    assert len(only) == 1 and only[0]["id"] == a
    ranged = store.list_petty_cash(date_from="2026-06-20", date_to="2026-06-30", db_path=db)
    assert len(ranged) == 1 and ranged[0]["amount"] == 500


def test_payable_with_original_status(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_payable("2026-06", 2, 245300, original_status="本社",
                            note="web請求書 家賃", db_path=db, now="T")
    rows = store.list_payables(month="2026-06", db_path=db)
    assert rows[0]["id"] == pid and rows[0]["original_status"] == "本社"


def test_receivable_roundtrip(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_receivable("2026-06", 1, 3184799, note="6/26号", db_path=db, now="T")
    rows = store.list_receivables(month="2026-06", db_path=db)
    assert rows[0]["amount"] == 3184799
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/test_posting_store.py -k "petty or payable or receivable" -v`
Expected: FAIL

- [ ] **Step 3: データ表関数を実装**

`common/posting_store.py` に追記:

```python
def add_petty_cash(date, category_id, amount, *, project_id=None, memo=None,
                   source="manual", db_path=None, now=None):
    return _add("petty_cash",
                ["date", "category_id", "amount", "project_id", "memo", "source", "created_at"],
                [date, _int_or_none(category_id), int(amount), _int_or_none(project_id),
                 memo, source, _now(now)], db_path)


def list_petty_cash(*, project_id=None, date_from=None, date_to=None, db_path=None):
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM petty_cash WHERE 1=1"
        args = []
        if project_id is not None:
            sql += " AND project_id=?"; args.append(int(project_id))
        if date_from is not None:
            sql += " AND date>=?"; args.append(date_from)
        if date_to is not None:
            sql += " AND date<=?"; args.append(date_to)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_petty_cash(row_id, *, db_path=None):
    _delete("petty_cash", row_id, db_path)


def add_payable(month, vendor_id, amount, *, original_status=None, note=None,
                project_id=None, source="manual", db_path=None, now=None):
    return _add("payables",
                ["month", "vendor_id", "amount", "original_status", "note",
                 "project_id", "source", "created_at"],
                [month, _int_or_none(vendor_id), int(amount), original_status, note,
                 _int_or_none(project_id), source, _now(now)], db_path)


def list_payables(*, month=None, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM payables WHERE 1=1"
        args = []
        if month is not None:
            sql += " AND month=?"; args.append(month)
        if project_id is not None:
            sql += " AND project_id=?"; args.append(int(project_id))
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_payable(row_id, *, db_path=None):
    _delete("payables", row_id, db_path)


def add_receivable(month, client_id, amount, *, note=None, project_id=None,
                   db_path=None, now=None):
    return _add("receivables",
                ["month", "client_id", "amount", "note", "project_id", "created_at"],
                [month, _int_or_none(client_id), int(amount), note,
                 _int_or_none(project_id), _now(now)], db_path)


def list_receivables(*, month=None, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM receivables WHERE 1=1"
        args = []
        if month is not None:
            sql += " AND month=?"; args.append(month)
        if project_id is not None:
            sql += " AND project_id=?"; args.append(int(project_id))
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_receivable(row_id, *, db_path=None):
    _delete("receivables", row_id, db_path)
```

また `_int_or_none` を（未定義なら）ファイル上部に追加:

```python
def _int_or_none(value):
    return None if value is None else int(value)
```

- [ ] **Step 4: テスト成功を確認**

Run: `python -m pytest tests/test_posting_store.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add -A && git commit -m "feat: 小口・買掛・売掛のCRUD"
```

---

### Task 4: 業務委託請求（ヘッダ＋明細行）のCRUD

**Files:**
- Modify: `common/posting_store.py`
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces:
  - `add_contract_invoice(distributor_id, issue_date, period_from, period_to, lines, *, db_path=None, now=None) -> int`
    - `lines`: `list[dict]`。各 dict は `{"project_id", "report_qty", "unit_price", "remark"}`。`amount` は `report_qty*unit_price` で保存側が計算。
  - `get_contract_invoice(invoice_id, *, db_path=None) -> dict`（`{"invoice": {...}, "lines": [...]}`）
  - `list_contract_invoices(*, db_path=None) -> list[dict]`（ヘッダ一覧、新しい順）
  - `delete_contract_invoice(invoice_id, *, db_path=None)`（明細行も削除）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_contract_invoice_roundtrip_and_amount(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    lines = [
        {"project_id": 1, "report_qty": 3713, "unit_price": 3, "remark": "配布"},
        {"project_id": 1, "report_qty": 1, "unit_price": 540, "remark": "交通費"},
    ]
    inv = store.add_contract_invoice(5, "2026-06-30", "2026-06-19", "2026-06-27",
                                     lines, db_path=db, now="T")
    got = store.get_contract_invoice(inv, db_path=db)
    assert got["invoice"]["distributor_id"] == 5
    assert len(got["lines"]) == 2
    # amount = report_qty * unit_price
    assert got["lines"][0]["amount"] == 3713 * 3
    assert got["lines"][1]["amount"] == 540


def test_delete_contract_invoice_removes_lines(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    inv = store.add_contract_invoice(1, "2026-06-30", "2026-06-01", "2026-06-05",
                                     [{"project_id": 1, "report_qty": 10, "unit_price": 5,
                                       "remark": "配布"}], db_path=db, now="T")
    store.delete_contract_invoice(inv, db_path=db)
    assert store.get_contract_invoice(inv, db_path=db) is None
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/test_posting_store.py -k contract -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
def add_contract_invoice(distributor_id, issue_date, period_from, period_to, lines,
                         *, db_path=None, now=None):
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO contract_invoices"
            " (distributor_id, issue_date, period_from, period_to, created_at)"
            " VALUES (?,?,?,?,?)",
            (_int_or_none(distributor_id), issue_date, period_from, period_to, _now(now)))
        invoice_id = int(cur.lastrowid)
        for ln in lines:
            qty = int(ln.get("report_qty") or 0)
            price = int(ln.get("unit_price") or 0)
            conn.execute(
                "INSERT INTO contract_invoice_lines"
                " (invoice_id, project_id, report_qty, unit_price, amount, remark)"
                " VALUES (?,?,?,?,?,?)",
                (invoice_id, _int_or_none(ln.get("project_id")), qty, price,
                 qty * price, ln.get("remark")))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)
    return invoice_id


def get_contract_invoice(invoice_id, *, db_path=None):
    conn = _connect(db_path)
    try:
        head = conn.execute("SELECT * FROM contract_invoices WHERE id=?",
                            (int(invoice_id),)).fetchone()
        if head is None:
            return None
        lines = conn.execute(
            "SELECT * FROM contract_invoice_lines WHERE invoice_id=? ORDER BY id",
            (int(invoice_id),)).fetchall()
        return {"invoice": dict(head), "lines": [dict(r) for r in lines]}
    finally:
        conn.close()


def list_contract_invoices(*, db_path=None):
    conn = _connect(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM contract_invoices ORDER BY id DESC").fetchall()]
    finally:
        conn.close()


def delete_contract_invoice(invoice_id, *, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM contract_invoice_lines WHERE invoice_id=?",
                     (int(invoice_id),))
        conn.execute("DELETE FROM contract_invoices WHERE id=?", (int(invoice_id),))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)
```

- [ ] **Step 4: テスト成功を確認**

Run: `python -m pytest tests/test_posting_store.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add -A && git commit -m "feat: 業務委託請求(ヘッダ+明細行)のCRUD"
```

---

### Task 5: 集計ロジック（部数・請求合計・号別集約・収支）

**Files:**
- Create: `common/posting_logic.py`
- Test: `tests/test_posting_logic.py`

**Interfaces:**
- Consumes: なし（純粋関数。dictのリストを受け取る）
- Produces:
  - `delivered_copies(lines) -> int`：`remark` が `配布` または `挟み込み` の行の `report_qty` 合計。
  - `invoice_total(lines) -> int`：全行 `amount` の合計（＝ご請求金額 税込）。
  - `aggregate_issue(project_id, *, petty, payables, contract_lines, manual) -> dict`：
    指定案件のコスト内訳と合計を返す。戻り値 `{"petty": int, "payables": int, "contract": int, "manual": int, "total": int}`。
  - `issue_balance(cost_total, receivable_total) -> int`：`receivable_total - cost_total`（収支）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_posting_logic.py`:

```python
from common import posting_logic as L


def test_delivered_copies_counts_only_haifu_and_hasamikomi():
    lines = [
        {"report_qty": 3713, "remark": "配布"},
        {"report_qty": 500, "remark": "挟み込み"},
        {"report_qty": 1, "remark": "交通費"},
        {"report_qty": 9, "remark": "手当"},
    ]
    assert L.delivered_copies(lines) == 3713 + 500


def test_invoice_total_sums_amount():
    lines = [{"amount": 11139}, {"amount": 540}, {"amount": 2000}]
    assert L.invoice_total(lines) == 13679


def test_aggregate_issue_sums_each_source():
    result = L.aggregate_issue(
        1,
        petty=[{"project_id": 1, "amount": 1200}, {"project_id": 2, "amount": 999}],
        payables=[{"project_id": 1, "amount": 183342}],
        contract_lines=[{"project_id": 1, "amount": 11139}, {"project_id": 1, "amount": 540}],
        manual=[{"project_id": 1, "amount": 8000}],
    )
    assert result["petty"] == 1200
    assert result["payables"] == 183342
    assert result["contract"] == 11139 + 540
    assert result["manual"] == 8000
    assert result["total"] == 1200 + 183342 + 11139 + 540 + 8000


def test_issue_balance():
    assert L.issue_balance(cost_total=200000, receivable_total=290703) == 90703
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/test_posting_logic.py -v`
Expected: FAIL（`common.posting_logic` 無し）

- [ ] **Step 3: 実装**

`common/posting_logic.py`:

```python
"""配布コストの集計ロジック(純粋関数)。DB非依存でテスト可能。"""

_DELIVERY_REMARKS = ("配布", "挟み込み")


def delivered_copies(lines) -> int:
    return sum(int(l.get("report_qty") or 0)
               for l in lines if l.get("remark") in _DELIVERY_REMARKS)


def invoice_total(lines) -> int:
    return sum(int(l.get("amount") or 0) for l in lines)


def _sum_for_project(rows, project_id) -> int:
    return sum(int(r.get("amount") or 0) for r in rows
               if r.get("project_id") == project_id)


def aggregate_issue(project_id, *, petty, payables, contract_lines, manual) -> dict:
    p = _sum_for_project(petty, project_id)
    pay = _sum_for_project(payables, project_id)
    con = _sum_for_project(contract_lines, project_id)
    man = _sum_for_project(manual, project_id)
    return {"petty": p, "payables": pay, "contract": con, "manual": man,
            "total": p + pay + con + man}


def issue_balance(cost_total, receivable_total) -> int:
    return int(receivable_total) - int(cost_total)
```

- [ ] **Step 4: テスト成功を確認**

Run: `python -m pytest tests/test_posting_logic.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add -A && git commit -m "feat: 集計ロジック(部数/請求合計/号別集約/収支)"
```

---

### Task 6: 完了報告書兼請求書のExcel生成

**Files:**
- Create: `common/invoice_excel.py`
- Test: `tests/test_invoice_excel.py`
- 参照: `templates/業務完了報告書兼請求書テンプレート.xlsx`（Task 1でコピー済）

**Interfaces:**
- Consumes: `posting_logic.invoice_total`, `posting_logic.delivered_copies`
- Produces:
  - `build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines) -> bytes`
    - `lines`: `list[dict]` 各 `{"project_name", "report_qty", "unit_price", "amount", "remark"}`。
    - テンプレの様式を保持したまま値を流し込み、xlsxのバイト列を返す。
    - 明細は13行目から順に：B列=案件名(品名・号数)、D列=報告数、E列=単価、F列=計。
    - A7 のご請求金額セルに合計、F3 に発行日、A10 期間、E20隣(F20)に配布部数。

- [ ] **Step 1: テンプレのセル位置を確認（調査ステップ・コード変更なし）**

Run:
```bash
cd "C:/Users/moro/posting-automation"
PYTHONIOENCODING=utf-8 python -c "import openpyxl; wb=openpyxl.load_workbook('templates/業務完了報告書兼請求書テンプレート.xlsx'); ws=wb.active; [print(c.coordinate, repr(c.value)) for row in ws.iter_rows() for c in row if c.value is not None]"
```
Expected: A1タイトル/A3宛名/F3日付/A7ご請求金額/A10期間/12行ヘッダ(内訳/品名号数/数量/単価/計)/E20配布部数/F20部 が確認できる。**明細開始行=13、列は B(品名号数)・D(数量)・E(単価)・F(計)。**

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_invoice_excel.py`:

```python
import io
import openpyxl
from common import invoice_excel


def _load(data):
    return openpyxl.load_workbook(io.BytesIO(data)).active


def test_build_invoice_fills_lines_and_total():
    lines = [
        {"project_name": "関西ぱど：京阪北版", "report_qty": 3713, "unit_price": 3,
         "amount": 11139, "remark": "配布"},
        {"project_name": "関西ぱど：京阪北版", "report_qty": 1, "unit_price": 540,
         "amount": 540, "remark": "交通費"},
    ]
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="時野", issue_date="2026年6月30日",
        period_from="2026年6月19日", period_to="2026年6月27日", lines=lines)
    ws = _load(data)
    # 明細1行目(13行) の案件名・数量・単価・計
    assert ws["B13"].value == "関西ぱど：京阪北版"
    assert ws["D13"].value == 3713
    assert ws["E13"].value == 3
    assert ws["F13"].value == 11139
    # ご請求金額(A7)に合計 11679 が含まれる
    assert "11679" in str(ws["A7"].value) or ws["A7"].value == 11679
    # 配布部数(F20)= 配布のみ 3713(交通費は除外)
    assert ws["F20"].value == 3713 or "3713" in str(ws["F20"].value)


def test_build_invoice_returns_bytes():
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="黒瀬", issue_date="2026年6月30日",
        period_from="", period_to="",
        lines=[{"project_name": "その他", "report_qty": 10, "unit_price": 5,
                "amount": 50, "remark": "配布"}])
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0
```

- [ ] **Step 3: テスト失敗を確認**

Run: `python -m pytest tests/test_invoice_excel.py -v`
Expected: FAIL（`common.invoice_excel` 無し）

- [ ] **Step 4: 実装**

`common/invoice_excel.py`:

```python
"""業務完了報告書兼請求書テンプレートへの流し込み。様式・数式は保持し値だけ入れる。"""
import io
import os

import openpyxl

from common import posting_logic

_TEMPLATE = os.path.join("templates", "業務完了報告書兼請求書テンプレート.xlsx")
_FIRST_LINE_ROW = 13   # 明細開始行
_MAX_LINE_ROWS = 6     # 13〜18


def _set(ws, coord, value):
    ws[coord] = value


def build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines) -> bytes:
    wb = openpyxl.load_workbook(_TEMPLATE)
    ws = wb.active

    _set(ws, "F3", issue_date)
    # 発行者(配布員)名は宛名の下(B8 但し欄)に併記
    _set(ws, "B8", f"但し：{distributor_name} 配布業務分")
    _set(ws, "A7", f"ご請求金額　　　　{posting_logic.invoice_total(lines):,}　円（税込）")
    _set(ws, "A10", f"配布業務期間　：　{period_from}　～　{period_to}")

    for i, ln in enumerate(lines[:_MAX_LINE_ROWS]):
        r = _FIRST_LINE_ROW + i
        _set(ws, f"B{r}", ln.get("project_name"))
        _set(ws, f"D{r}", int(ln.get("report_qty") or 0))
        _set(ws, f"E{r}", int(ln.get("unit_price") or 0))
        _set(ws, f"F{r}", int(ln.get("amount") or 0))

    # 配布部数(F20)= 配布/挟み込みの報告数合計。ラベルE20は「報告数」に寄せる
    _set(ws, "E20", "報告数")
    _set(ws, "F20", posting_logic.delivered_copies(lines))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

> 注意: Step 1 の調査で明細開始行や列が違った場合は `_FIRST_LINE_ROW` と列指定を実測値へ直す。テスト(`B13/D13/E13/F13`)も同時に合わせる。

- [ ] **Step 5: テスト成功を確認**

Run: `python -m pytest tests/test_invoice_excel.py -v`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add -A && git commit -m "feat: 完了報告書兼請求書のExcel生成"
```

---

### Task 7: OCR（Bedrock画像対応＋抽出）

**Files:**
- Modify: `common/bedrock_client.py`（画像対応の関数を追加）
- Create: `common/ocr.py`
- Test: `tests/test_ocr.py`

**Interfaces:**
- Consumes: `bedrock_client.invoke_vision(prompt, image_bytes, media_type, client=None) -> str`
- Produces:
  - `bedrock_client.invoke_vision(prompt, image_bytes, media_type="image/jpeg", client=None, max_tokens=1024) -> str`
  - `ocr.extract_receipt(image_bytes, media_type="image/jpeg", *, client=None) -> dict`：`{"date": "YYYY-MM-DD"|None, "amount": int|None, "item": str|None}`
  - `ocr.extract_invoice(image_bytes, media_type="image/jpeg", *, client=None) -> dict`：`{"vendor": str|None, "amount": int|None, "note": str|None}`
  - どちらもAIの生JSON文字列をパースし、失敗しても例外にせず値 None のdictを返す（人が手直しする前提）。

- [ ] **Step 1: 失敗するテストを書く（Bedrockはモック）**

`tests/test_ocr.py`:

```python
from common import ocr


class _FakeClient:
    """invoke_model と同じ戻り(本文テキスト)を返すダミー。"""
    def __init__(self, text):
        self._text = text
        self.called_with = None

    def invoke_model(self, **kwargs):
        self.called_with = kwargs
        import json
        body = json.dumps({"content": [{"text": self._text}]}).encode()

        class _R:  # response["body"].read() を模す
            def __init__(self, b): self._b = b
            def read(self): return self._b
        return {"body": _R(body)}


def test_extract_receipt_parses_json():
    fake = _FakeClient('{"date":"2026-06-19","amount":1200,"item":"駐車場代"}')
    result = ocr.extract_receipt(b"\xff\xd8fakejpg", client=fake)
    assert result == {"date": "2026-06-19", "amount": 1200, "item": "駐車場代"}


def test_extract_receipt_tolerates_extra_text():
    fake = _FakeClient('抽出結果です: {"date":"2026-06-19","amount":1200,"item":"飲み物"} 以上')
    result = ocr.extract_receipt(b"x", client=fake)
    assert result["amount"] == 1200


def test_extract_receipt_bad_output_returns_none_fields():
    fake = _FakeClient("読み取れませんでした")
    result = ocr.extract_receipt(b"x", client=fake)
    assert result == {"date": None, "amount": None, "item": None}


def test_extract_invoice_parses_json():
    fake = _FakeClient('{"vendor":"関西電力株式会社","amount":16216,"note":"電気代"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] == "関西電力株式会社" and result["amount"] == 16216
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/test_ocr.py -v`
Expected: FAIL（`common.ocr` 無し）

- [ ] **Step 3: bedrock_client に画像対応を追加**

`common/bedrock_client.py` に追記:

```python
import base64


def invoke_vision(prompt, image_bytes, media_type="image/jpeg", client=None,
                  max_tokens: int = 1024) -> str:
    bedrock = client or _get_client()
    b64 = base64.b64encode(image_bytes).decode()
    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        }),
    )
    body = json.loads(response["body"].read())
    return body["content"][0]["text"]
```

- [ ] **Step 4: ocr.py を実装**

`common/ocr.py`:

```python
"""レシート/請求書の画像から項目を抽出する。抽出は下書き扱い(人が確認・修正)。"""
import json
import re

from common import bedrock_client

_RECEIPT_PROMPT = (
    "この画像はレシートまたは領収書です。日付・合計金額・品目を読み取り、"
    'JSONのみを出力してください。形式: {"date":"YYYY-MM-DD","amount":整数,"item":"品目"}。'
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)
_INVOICE_PROMPT = (
    "この画像は請求書です。請求元(会社名)・請求金額(税込)・内容を読み取り、"
    'JSONのみを出力してください。形式: {"vendor":"会社名","amount":整数,"note":"内容"}。'
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)


def _parse_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return {}


def _as_int(value):
    if value is None:
        return None
    try:
        return int(re.sub(r"[^\d-]", "", str(value)))
    except ValueError:
        return None


def extract_receipt(image_bytes, media_type="image/jpeg", *, client=None) -> dict:
    raw = bedrock_client.invoke_vision(_RECEIPT_PROMPT, image_bytes, media_type, client=client)
    d = _parse_json(raw)
    return {"date": d.get("date") or None,
            "amount": _as_int(d.get("amount")),
            "item": d.get("item") or None}


def extract_invoice(image_bytes, media_type="image/jpeg", *, client=None) -> dict:
    raw = bedrock_client.invoke_vision(_INVOICE_PROMPT, image_bytes, media_type, client=client)
    d = _parse_json(raw)
    return {"vendor": d.get("vendor") or None,
            "amount": _as_int(d.get("amount")),
            "note": d.get("note") or None}
```

- [ ] **Step 5: テスト成功を確認**

Run: `python -m pytest tests/test_ocr.py -v`
Expected: PASS

- [ ] **Step 6: 全テスト回帰確認**

Run: `python -m pytest -v`
Expected: PASS（全件）

- [ ] **Step 7: コミット**

```bash
git add -A && git commit -m "feat: OCR(Bedrock画像対応+レシート/請求書抽出)"
```

---

### Task 8: マスタ管理ページ

**Files:**
- Create: `pages/05_マスタ管理.py`
- 依存: Task 2 の store 関数

**Interfaces:**
- Consumes: `posting_store.list_*` / `add_*` / `update_*`（各マスタ）

- [ ] **Step 1: ページを実装**

`pages/05_マスタ管理.py`:

```python
import streamlit as st

from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("⚙️ マスタ管理")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["案件", "費目(小口)", "買掛先", "売掛先", "配布委託先"])


def _simple_master(label, list_fn, add_fn, update_fn):
    rows = list_fn()
    st.dataframe(rows, use_container_width=True, hide_index=True)
    with st.form(f"add_{label}", clear_on_submit=True):
        name = st.text_input(f"{label}名を追加")
        if st.form_submit_button("追加") and name.strip():
            add_fn(name.strip())
            st.rerun()


with tab1:
    _simple_master("案件", store.list_projects, store.add_project, store.update_project)
with tab2:
    _simple_master("費目", store.list_expense_categories,
                   store.add_expense_category, store.update_expense_category)
with tab3:
    st.dataframe(store.list_payables_vendors(), use_container_width=True, hide_index=True)
    with st.form("add_vendor", clear_on_submit=True):
        n = st.text_input("取引先名")
        c = st.text_input("既定の費目(家賃・電気 等)")
        if st.form_submit_button("追加") and n.strip():
            store.add_payables_vendor(n.strip(), default_category=(c.strip() or None))
            st.rerun()
with tab4:
    _simple_master("売掛先", store.list_receivables_clients,
                   store.add_receivables_client, store.update_receivables_client)
with tab5:
    st.dataframe(store.list_distributors(), use_container_width=True, hide_index=True)
    with st.form("add_dist", clear_on_submit=True):
        n = st.text_input("配布員 氏名")
        kind = st.selectbox("区分", ["業務委託", "自社社員", "アルバイト"])
        if st.form_submit_button("追加") and n.strip():
            store.add_distributor(n.strip(), kind=kind)
            st.rerun()
```

- [ ] **Step 2: 実機確認（アプリ起動）**

Run（PowerShellで独立プロセス起動。教訓: Bash run_in_background だとkillされる）:
```powershell
Get-Process | Where-Object {$_.Path -like '*streamlit*'} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "streamlit" -ArgumentList "run","app.py","--server.port","8502","--server.headless","true" -WorkingDirectory "C:\Users\moro\posting-automation"
```
Playwright で `http://localhost:8502/` を開き、「マスタ管理」→各タブにプリセットが並ぶこと、案件と配布員(区分つき)を追加できることを確認。

- [ ] **Step 3: コミット**

```bash
git add -A && git commit -m "feat: マスタ管理ページ"
```

---

### Task 9: 経費・買掛・売掛ページ（機能①）

**Files:**
- Create: `pages/01_経費・買掛・売掛.py`
- 依存: Task 3(store), Task 7(ocr)

**Interfaces:**
- Consumes: `posting_store.add_petty_cash/add_payable/add_receivable/list_*`, `posting_store.list_projects/list_expense_categories/list_payables_vendors/list_receivables_clients`, `ocr.extract_receipt/extract_invoice`

- [ ] **Step 1: ページを実装**

`pages/01_経費・買掛・売掛.py`:

```python
import streamlit as st

from common import ocr
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("🧾 経費・買掛・売掛")

mode = st.radio("入力の種類", ["小口", "買掛", "売掛", "配布委託費"],
                horizontal=True)


def _project_options():
    return {p["name"]: p["id"] for p in store.list_projects(only_active=True)}


if mode == "配布委託費":
    st.info("配布委託費（配布員への支払い）は『業務委託・請求書』ページで登録します。")
    st.page_link("pages/02_業務委託・請求書.py", label="→ 業務委託・請求書へ", icon="➡️")

elif mode == "小口":
    st.subheader("小口経費（レシートOCR / 手入力）")
    up = st.file_uploader("レシート画像（任意・AIが下書き抽出）", type=["jpg", "jpeg", "png"])
    draft = {"date": None, "amount": None, "item": None}
    if up is not None and st.button("画像をAIで読み取る"):
        media = "image/png" if up.name.lower().endswith("png") else "image/jpeg"
        draft = ocr.extract_receipt(up.getvalue(), media, client=None)
        st.session_state["petty_draft"] = draft
    draft = st.session_state.get("petty_draft", draft)
    with st.form("petty", clear_on_submit=True):
        date = st.text_input("日付(YYYY-MM-DD)", value=draft.get("date") or "")
        cats = {c["name"]: c["id"] for c in store.list_expense_categories(only_active=True)}
        cat = st.selectbox("費目", list(cats.keys()) or ["(費目マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0,
                                 value=int(draft.get("amount") or 0), step=1)
        projs = _project_options()
        proj = st.selectbox("案件(任意)", ["(なし)"] + list(projs.keys()))
        memo = st.text_input("メモ", value=draft.get("item") or "")
        if st.form_submit_button("登録") and amount > 0:
            store.add_petty_cash(
                date or None, cats.get(cat), int(amount),
                project_id=projs.get(proj), memo=memo or None,
                source="ocr" if up is not None else "manual")
            st.session_state.pop("petty_draft", None)
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_petty_cash(), use_container_width=True, hide_index=True)

elif mode == "買掛":
    st.subheader("買掛（固定費・法人業者）")
    up = st.file_uploader("請求書画像（任意・AIが金額を下書き抽出）",
                          type=["jpg", "jpeg", "png"])
    draft = {"vendor": None, "amount": None, "note": None}
    if up is not None and st.button("画像をAIで読み取る"):
        media = "image/png" if up.name.lower().endswith("png") else "image/jpeg"
        draft = ocr.extract_invoice(up.getvalue(), media, client=None)
        st.session_state["pay_draft"] = draft
    draft = st.session_state.get("pay_draft", draft)
    with st.form("payable", clear_on_submit=True):
        month = st.text_input("月度(YYYY-MM)")
        vendors = {v["name"]: v["id"] for v in store.list_payables_vendors(only_active=True)}
        vendor = st.selectbox("取引先", list(vendors.keys()) or ["(買掛先マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0,
                                 value=int(draft.get("amount") or 0), step=1)
        original = st.selectbox("原本区分",
                                ["原本あり", "本社", "クレジット", "振込用紙", "なし"])
        note = st.text_input("備考", value=draft.get("note") or "")
        projs = _project_options()
        proj = st.selectbox("案件(任意・配布業者なら号)", ["(なし)"] + list(projs.keys()))
        if st.form_submit_button("登録") and amount > 0:
            store.add_payable(month or None, vendors.get(vendor), int(amount),
                              original_status=original, note=note or None,
                              project_id=projs.get(proj),
                              source="ocr" if up is not None else "manual")
            st.session_state.pop("pay_draft", None)
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_payables(), use_container_width=True, hide_index=True)

else:  # 売掛
    st.subheader("売掛（売上）")
    with st.form("receivable", clear_on_submit=True):
        month = st.text_input("月度(YYYY-MM)")
        clients = {c["name"]: c["id"] for c in store.list_receivables_clients(only_active=True)}
        client = st.selectbox("売掛先", list(clients.keys()) or ["(売掛先マスタを登録)"])
        amount = st.number_input("金額(税込)", min_value=0, step=1)
        note = st.text_input("備考(号)")
        projs = _project_options()
        proj = st.selectbox("案件(任意)", ["(なし)"] + list(projs.keys()))
        if st.form_submit_button("登録") and amount > 0:
            store.add_receivable(month or None, clients.get(client), int(amount),
                                 note=note or None, project_id=projs.get(proj))
            st.success("登録しました")
            st.rerun()
    st.dataframe(store.list_receivables(), use_container_width=True, hide_index=True)
```

- [ ] **Step 2: 実機確認**

アプリ再起動（Task 8 Step 2 の手順）→「経費・買掛・売掛」で 小口/買掛/売掛 を手入力登録できること、一覧に出ることを確認。OCRボタンはAWS資格情報が無い環境では失敗し得るため、まず手入力で通す（OCRの実写真テストはTask 13で）。

- [ ] **Step 3: コミット**

```bash
git add -A && git commit -m "feat: 経費・買掛・売掛ページ(機能①)"
```

---

### Task 10: 業務委託・請求書ページ（機能②）

**Files:**
- Create: `pages/02_業務委託・請求書.py`
- 依存: Task 4(store), Task 5(logic), Task 6(invoice_excel)

**Interfaces:**
- Consumes: `posting_store.list_distributors/list_projects/add_contract_invoice/list_contract_invoices/get_contract_invoice`, `posting_logic.invoice_total/delivered_copies`, `invoice_excel.build_invoice_xlsx`

- [ ] **Step 1: ページを実装**

`pages/02_業務委託・請求書.py`:

```python
from datetime import date as _date

import pandas as pd
import streamlit as st

from common import invoice_excel
from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("📄 業務委託・請求書")

dists = {d["name"]: d["id"] for d in store.list_distributors(only_active=True)}
projs = {p["name"]: p["id"] for p in store.list_projects(only_active=True)}

if not dists:
    st.warning("先に『マスタ管理』で配布委託先(配布員)を登録してください。")
    st.stop()

dist_name = st.selectbox("配布員", list(dists.keys()))
c1, c2, c3 = st.columns(3)
issue = c1.date_input("発行日", value=_date.today())
pfrom = c2.date_input("配布業務期間(開始)")
pto = c3.date_input("配布業務期間(終了)")

st.markdown("**明細**（案件・報告数・単価・備考）")
editor = st.data_editor(
    pd.DataFrame([{"案件": "", "報告数": 0, "単価": 0, "備考": "配布"}]),
    num_rows="dynamic",
    column_config={
        "案件": st.column_config.SelectboxColumn(options=list(projs.keys())),
        "備考": st.column_config.SelectboxColumn(
            options=["配布", "挟み込み", "交通費", "手当", "その他"]),
    },
    use_container_width=True, key="line_editor")

lines = []
for _, row in editor.iterrows():
    if not row["案件"]:
        continue
    qty = int(row["報告数"] or 0)
    price = int(row["単価"] or 0)
    lines.append({"project_id": projs.get(row["案件"]), "project_name": row["案件"],
                  "report_qty": qty, "unit_price": price, "amount": qty * price,
                  "remark": row["備考"]})

if lines:
    st.metric("ご請求金額(税込)", f"¥{posting_logic.invoice_total(lines):,}")
    st.metric("配布部数(配布+挟み込み)", f"{posting_logic.delivered_copies(lines):,} 部")

col_save, col_dl = st.columns(2)
if col_save.button("この請求を登録", type="primary", disabled=not lines):
    store.add_contract_invoice(
        dists[dist_name], str(issue), str(pfrom), str(pto),
        [{"project_id": l["project_id"], "report_qty": l["report_qty"],
          "unit_price": l["unit_price"], "remark": l["remark"]} for l in lines])
    st.success("登録しました")

if lines:
    xlsx = invoice_excel.build_invoice_xlsx(
        distributor_name=dist_name,
        issue_date=str(issue), period_from=str(pfrom), period_to=str(pto), lines=lines)
    col_dl.download_button(
        "完了報告書兼請求書をダウンロード", data=xlsx,
        file_name=f"業務完了報告書兼請求書_{dist_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.divider()
st.subheader("登録済みの請求 / 配布員別報酬")
invoices = store.list_contract_invoices()
if invoices:
    id2name = {d["id"]: d["name"] for d in store.list_distributors()}
    summary = {}
    rows = []
    for inv in invoices:
        detail = store.get_contract_invoice(inv["id"])
        total = posting_logic.invoice_total(detail["lines"])
        name = id2name.get(inv["distributor_id"], "?")
        summary[name] = summary.get(name, 0) + total
        rows.append({"ID": inv["id"], "配布員": name, "発行日": inv["issue_date"],
                     "期間": f'{inv["period_from"]}〜{inv["period_to"]}', "請求額": total})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.markdown("**配布員別 報酬合計**")
    st.dataframe([{"配布員": k, "報酬合計": v} for k, v in summary.items()],
                 use_container_width=True, hide_index=True)
```

- [ ] **Step 2: 実機確認**

アプリ再起動→配布員を選び、明細（案件=選択式／報告数／単価／備考）を入れると請求金額・部数が自動計算されること、「登録」で一覧に出ること、「ダウンロード」で完了報告書兼請求書xlsxが落ちて明細・合計・報告数が入っていることを確認。

- [ ] **Step 3: コミット**

```bash
git add -A && git commit -m "feat: 業務委託・請求書ページ(機能②)"
```

---

### Task 11: 号別明細ページ（機能③）

**Files:**
- Create: `pages/03_号別明細.py`
- 依存: Task 3/4(store), Task 5(logic)

**Interfaces:**
- Consumes: `posting_store.list_projects/list_petty_cash/list_payables/list_receivables/list_contract_invoices/get_contract_invoice`, `posting_store.add_issue_manual_cost/list_issue_manual_costs`, `posting_logic.aggregate_issue/issue_balance`

- [ ] **Step 1: 号別手入力の store 関数を追加（TDD）**

`tests/test_posting_store.py` に追記:

```python
def test_issue_manual_cost_roundtrip(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_issue_manual_cost(1, "自社社員配布分", 8000, db_path=db, now="T")
    rows = store.list_issue_manual_costs(project_id=1, db_path=db)
    assert rows[0]["amount"] == 8000 and rows[0]["content"] == "自社社員配布分"
```

`common/posting_store.py` に実装追記:

```python
def add_issue_manual_cost(project_id, content, amount, *, db_path=None, now=None):
    return _add("issue_manual_costs", ["project_id", "content", "amount", "created_at"],
                [_int_or_none(project_id), content, int(amount), _now(now)], db_path)


def list_issue_manual_costs(*, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        if project_id is None:
            rows = conn.execute("SELECT * FROM issue_manual_costs ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM issue_manual_costs WHERE project_id=? ORDER BY id DESC",
                (int(project_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

Run: `python -m pytest tests/test_posting_store.py -k issue_manual -v` → PASS を確認。

- [ ] **Step 2: ページを実装**

`pages/03_号別明細.py`:

```python
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("📊 号別明細")

projs = store.list_projects(only_active=True)
if not projs:
    st.warning("案件マスタが空です。『マスタ管理』で登録してください。")
    st.stop()

name2id = {p["name"]: p["id"] for p in projs}
sel = st.selectbox("案件(号)", list(name2id.keys()))
pid = name2id[sel]

# 全委託明細行を集める(案件でひもづけ)
contract_lines = []
for inv in store.list_contract_invoices():
    detail = store.get_contract_invoice(inv["id"])
    contract_lines.extend(detail["lines"])

agg = posting_logic.aggregate_issue(
    pid,
    petty=store.list_petty_cash(),
    payables=store.list_payables(),
    contract_lines=contract_lines,
    manual=store.list_issue_manual_costs(),
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("小口", f"¥{agg['petty']:,}")
c2.metric("買掛", f"¥{agg['payables']:,}")
c3.metric("業務委託", f"¥{agg['contract']:,}")
c4.metric("手入力", f"¥{agg['manual']:,}")
c5.metric("コスト合計", f"¥{agg['total']:,}")

receivable_total = sum(int(r["amount"]) for r in store.list_receivables(project_id=pid))
if receivable_total:
    bal = posting_logic.issue_balance(agg["total"], receivable_total)
    st.metric("収支(売上−コスト)", f"¥{bal:,}", delta=f"売上 ¥{receivable_total:,}")

st.divider()
st.subheader("内訳")
st.markdown("**小口**"); st.dataframe(store.list_petty_cash(project_id=pid),
                                     use_container_width=True, hide_index=True)
st.markdown("**買掛**"); st.dataframe(store.list_payables(project_id=pid),
                                     use_container_width=True, hide_index=True)
st.markdown("**業務委託(この号の行)**")
st.dataframe([l for l in contract_lines if l.get("project_id") == pid],
             use_container_width=True, hide_index=True)

st.divider()
st.subheader("この号に手入力でコストを足す（自社社員配布分 等）")
with st.form("manual_cost", clear_on_submit=True):
    content = st.text_input("内容")
    amount = st.number_input("金額", min_value=0, step=1)
    if st.form_submit_button("追加") and amount > 0 and content.strip():
        store.add_issue_manual_cost(pid, content.strip(), int(amount))
        st.rerun()
st.dataframe(store.list_issue_manual_costs(project_id=pid),
             use_container_width=True, hide_index=True)
```

- [ ] **Step 3: 実機確認**

アプリ再起動→ある案件で小口/買掛/委託を登録済みにしておき、号別明細で合計・内訳が集約表示されること、手入力コストを足すと合計が増えること、売掛があれば収支が出ることを確認。

- [ ] **Step 4: コミット**

```bash
git add -A && git commit -m "feat: 号別明細ページ(機能③)+号別手入力store"
```

---

### Task 12: 経理提出出力ページ（機能④）

**Files:**
- Create: `pages/04_経理提出出力.py`
- Modify: `common/posting_store.py`（期間フィルタ付きエクスポート補助・任意）
- 依存: Task 3(store)

**Interfaces:**
- Consumes: `posting_store.list_petty_cash/list_payables/list_receivables/list_contract_invoices/get_contract_invoice`, pandas

- [ ] **Step 1: ページを実装**

`pages/04_経理提出出力.py`:

```python
import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("⬇️ 経理提出用データ出力")

kind = st.selectbox("データ種別", ["小口一覧", "買掛一覧", "売掛一覧", "業務委託費一覧"])
c1, c2 = st.columns(2)
d_from = c1.text_input("期間 開始(YYYY-MM-DD もしくは 空)")
d_to = c2.text_input("期間 終了(YYYY-MM-DD もしくは 空)")


def _within(value, lo, hi):
    if value is None:
        return False
    if lo and str(value) < lo:
        return False
    if hi and str(value) > hi:
        return False
    return True


if kind == "小口一覧":
    rows = store.list_petty_cash(date_from=(d_from or None), date_to=(d_to or None))
    df = pd.DataFrame(rows)
elif kind == "買掛一覧":
    rows = [r for r in store.list_payables() if _within(r.get("month"), d_from[:7], d_to[:7])] \
        if (d_from or d_to) else store.list_payables()
    df = pd.DataFrame(rows)
elif kind == "売掛一覧":
    rows = [r for r in store.list_receivables() if _within(r.get("month"), d_from[:7], d_to[:7])] \
        if (d_from or d_to) else store.list_receivables()
    df = pd.DataFrame(rows)
else:  # 業務委託費一覧
    flat = []
    id2name = {d["id"]: d["name"] for d in store.list_distributors()}
    for inv in store.list_contract_invoices():
        if not _within(inv.get("issue_date"), d_from, d_to) and (d_from or d_to):
            continue
        detail = store.get_contract_invoice(inv["id"])
        flat.append({"ID": inv["id"], "配布員": id2name.get(inv["distributor_id"]),
                     "発行日": inv["issue_date"],
                     "期間": f'{inv["period_from"]}〜{inv["period_to"]}',
                     "請求額": posting_logic.invoice_total(detail["lines"])})
    df = pd.DataFrame(flat)

st.dataframe(df, use_container_width=True, hide_index=True)

if not df.empty:
    csv = "﻿" + df.to_csv(index=False)
    st.download_button("CSVダウンロード", data=csv.encode("utf-8"),
                       file_name=f"{kind}.csv", mime="text/csv")
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=kind)
    st.download_button("Excelダウンロード", data=buf.getvalue(),
                       file_name=f"{kind}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

- [ ] **Step 2: 実機確認**

アプリ再起動→各種別で期間指定して一覧が絞れること、CSV/Excelがダウンロードでき文字化けしないことを確認。

- [ ] **Step 3: コミット**

```bash
git add -A && git commit -m "feat: 経理提出出力ページ(機能④)"
```

---

### Task 13: ホーム集約・全体E2E・最終確認

**Files:**
- Modify: `home.py`
- Test: 全体

**Interfaces:**
- Consumes: 全 store / logic

- [ ] **Step 1: ホームを号別コスト概況に差し替え**

`home.py`:

```python
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style

apply_app_style()
st.title("📮 配布コスト管理")

projs = store.list_projects(only_active=True)
contract_lines = []
for inv in store.list_contract_invoices():
    contract_lines.extend(store.get_contract_invoice(inv["id"])["lines"])
petty, pays, manual = store.list_petty_cash(), store.list_payables(), store.list_issue_manual_costs()

rows = []
for p in projs:
    agg = posting_logic.aggregate_issue(p["id"], petty=petty, payables=pays,
                                        contract_lines=contract_lines, manual=manual)
    rev = sum(int(r["amount"]) for r in store.list_receivables(project_id=p["id"]))
    rows.append({"案件": p["name"], "コスト合計": agg["total"], "売上": rev,
                 "収支": posting_logic.issue_balance(agg["total"], rev)})
st.dataframe(rows, use_container_width=True, hide_index=True)
st.caption("左メニュー: 経費・買掛・売掛 / 業務委託・請求書 / 号別明細 / 経理提出出力 / マスタ管理")
```

- [ ] **Step 2: 全テスト回帰**

Run: `python -m pytest -v`
Expected: PASS（全件）

- [ ] **Step 3: 実データ流し E2E（Playwright）**

アプリ再起動し、次を一気通貫で確認：
1. マスタ管理でプリセット表示。配布員(例: 時野／自社社員)を追加。
2. 経費で小口(案件=関西ぱど京阪北版・1,200円)・買掛(大東建託・245,300円)・売掛(関西ぱど北大阪・3,184,799円/案件=関西ぱど京阪北版)を登録。
3. 業務委託で時野の明細(配布3,713×3・交通費540)を登録→請求書DL→開いて合計・報告数を確認。
4. 号別明細で関西ぱど京阪北版を選び、コスト合計と収支が出ることを確認。
5. 経理出力で各種別のCSV/Excelが落ちることを確認。

- [ ] **Step 4: コミット**

```bash
git add -A && git commit -m "feat: ホーム号別概況+全体E2E確認"
```

- [ ] **Step 5: superpowers:requesting-code-review でレビュー依頼（任意だが推奨）**

実装完了後、`superpowers:requesting-code-review` で第三者レビューを回し、指摘を `superpowers:receiving-code-review` で取り込む。

---

## Self-Review（spec対応チェック）

- **機能①（小口/買掛/売掛・OCR・原本区分・費目マスタ）** → Task 3,7,9 ✅
- **機能②（配布員マスタ・明細・部数=配布/挟込・請求書テンプレ流し込み・配布員別報酬）** → Task 2,4,5,6,10 ✅
- **機能③（号別集約・自社社員手入力・収支）** → Task 5,11 ✅
- **機能④（期間×種別でExcel/CSV）** → Task 12 ✅
- **マスタ5種＋プリセット（案件/費目/買掛先/売掛先/配布委託先＋区分）** → Task 2,8 ✅
- **売掛を明細表まるごとアプリ化／法人業者は買掛** → 買掛(payables)＋売掛(receivables)テーブルで両対応 ✅
- **ログインはMVP未ゲート（auth.pyは同梱）** → Task 1（app.pyにゲート無し）✅
- **テレアポ資産流用・SQLite＋S3同期・TDD** → Task 1（common流用）・全store（_push_remote）・各Taskのpytest ✅
- **フェーズ2（資料作成変換表・App Runner公開・経理自動送付）は対象外** → 本planに含めず ✅

型整合: `build_invoice_xlsx` の `lines` は `project_name/report_qty/unit_price/amount/remark`（Task6・Task10で一致）。`aggregate_issue` は `project_id/amount` を持つ行を受け取る（Task5・Task11で一致）。`add_contract_invoice` の lines は `project_id/report_qty/unit_price/remark`（Task4・Task10で一致・amountは保存側計算）。

Placeholder scan: TODO/TBD無し。全コードステップに実コードあり。
