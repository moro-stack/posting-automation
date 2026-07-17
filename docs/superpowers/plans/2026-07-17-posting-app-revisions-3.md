# 大阪支社アプリ 改修（第3弾）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 号別明細・小口への配布員名の表示、マスタの項目追加（買掛の原本区分／業務委託の振込先・支払形態・日当金額）、支払形態に応じた報酬の自動計算、全画面への削除ボタン（マスタは停止中方式）とアナウンスを実装する。

**Architecture:** 既存の3層（`common/posting_store.py`=SQLite永続化／`common/posting_logic.py`=DB非依存の純関数／`pages/*.py`=Streamlit画面）をそのまま踏襲する。スキーマ変更は既存の `_ensure_schema` 内の `PRAGMA table_info` → `ALTER TABLE` 方式で足し、既存データを保持する。判定ロジック（単位・部数・原本区分の一致・削除か停止中か）はすべて `posting_logic` の純関数に置いてテストする。画面は薄く保つ。

**Tech Stack:** Python 3 / Streamlit / SQLite（標準ライブラリ `sqlite3`）/ pandas / openpyxl / pytest

**設計書:** `docs/superpowers/specs/2026-07-17-posting-app-revisions-3-design.md`

## Global Constraints

- ブランチは `feature/revisions-3`。master へは直接コミットしない
- **既存の全73テストが常に通ること。** 各タスクの最後に `pytest` 全体を走らせる
- **後方互換は絶対**: `pay_type` が NULL の既存請求は「歩合」と同じ扱い＝現行の「枚」表示・現行の部数計算のまま変わらないこと
- スキーマ変更は必ず `_ensure_schema` の自動マイグレ方式（`PRAGMA table_info` で列の有無を見て `ALTER TABLE`）。**既存DBを作り直さない**
- 新しい純関数の引数 `pay_type` は**必ずデフォルト `None`**。既存の呼び出し側を壊さない
- 金額は整数（円）、数量・単価は小数可（既存の `_num` / `fmt_num` を使う）
- Streamlit の `st.form` 内では選択に応じた動的な出し分けができない。動的表示が要るものは form の外に置く
- `common/*.py` を変更したら 8502 の**手動再起動が必須**（起動batは health=ok なら既存サーバーを開くだけ）
- 実機検証は**実データDBのコピー**＋別ポート（8599）＋環境変数 `POSTING_DB_PATH`。本番DBを汚さない
- 種別（配布／挟み込み／交通費／手当／その他）は `is_delivery` の判定に使う既存の軸。**業務名で置き換えたり兼用したりしない**

---

## File Structure

| ファイル | 責務 | 変更 |
|---|---|---|
| `common/posting_store.py` | SQLite の永続化・マイグレ | 列追加、`distributor_daily_rates` テーブル、CRUD拡張、`find_vendor_by_name`、`count_master_usage` |
| `common/posting_logic.py` | DB非依存の純関数 | `unit_for`/`qty_label` の pay_type 拡張、`line_copies`、`delivered_copies` 拡張、`resolve_original_status`、`master_delete_action` |
| `common/ui.py` | 画面共通部品 | `confirm_delete()` を新設 |
| `pages/01_経費・買掛・売掛.py` | 小口/買掛/売掛の登録・一覧 | 小口に配布員欄、買掛の原本区分オートセット、各一覧に削除 |
| `pages/02_業務委託登録.py` | 業務委託の請求登録・一覧 | 支払形態に応じた明細・自動計算・部数列、一覧に削除 |
| `pages/03_号別明細.py` | 号ごとの原価集計 | 業務委託内訳と雑費内訳に配布員列、Excel出力も追随 |
| `pages/05_マスタ管理.py` | 5マスタの管理 | タブ改名、項目追加、日当金額、停止中方式、削除 |
| `tests/test_posting_store.py` | store のテスト | 追加 |
| `tests/test_posting_logic.py` | 純関数のテスト | 追加 |
| `tests/test_pages_smoke.py` | 画面のスモークテスト | **新規作成** |

---

### Task 1: distributors の項目追加（振込先・支払形態・時給額・月額）

**Files:**
- Modify: `common/posting_store.py`（`_ensure_schema` / `add_distributor` / `update_distributor`）
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Consumes: 既存の `_add` / `_update` / `_ensure_schema`
- Produces:
  - `add_distributor(name, *, kind="業務委託", bank_info=None, pay_type=None, hourly_rate=None, monthly_rate=None, active=1, db_path=None) -> int`
  - `update_distributor(row_id, *, name=_UNSET, kind=_UNSET, bank_info=_UNSET, pay_type=_UNSET, hourly_rate=_UNSET, monthly_rate=_UNSET, active=_UNSET, db_path=None) -> None`
  - `list_distributors()` の各行に `bank_info` / `pay_type` / `hourly_rate` / `monthly_rate` が含まれる

- [ ] **Step 1: Write the failing test**

`tests/test_posting_store.py` の末尾に追記:

```python
def test_distributor_stores_bank_and_pay_type(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor(
        "山田太郎", kind="業務委託",
        bank_info="三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ",
        pay_type="日当", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["bank_info"] == "三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ"
    assert row["pay_type"] == "日当"
    assert row["kind"] == "業務委託"


def test_distributor_hourly_and_monthly_rate(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    h = store.add_distributor("時給の人", pay_type="時給", hourly_rate=1200, db_path=db)
    m = store.add_distributor("月給の人", pay_type="月給", monthly_rate=250000, db_path=db)
    rows = {r["id"]: r for r in store.list_distributors(db_path=db)}
    assert rows[h]["hourly_rate"] == 1200
    assert rows[m]["monthly_rate"] == 250000


def test_update_distributor_changes_pay_type_and_bank(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.update_distributor(did, pay_type="歩合", bank_info="ゆうちょ 12345", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["pay_type"] == "歩合"
    assert row["bank_info"] == "ゆうちょ 12345"


def test_old_distributors_table_gets_new_columns(tmp_path):
    """第2弾までの列しかない旧DBを開いても壊れず、新しい列が足されること。"""
    import sqlite3
    db = os.path.join(tmp_path, "old.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE distributors (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '業務委託',"
                 " active INTEGER NOT NULL DEFAULT 1)")
    conn.execute("INSERT INTO distributors (name) VALUES ('既存の人')")
    conn.commit()
    conn.close()
    rows = store.list_distributors(db_path=db)
    assert rows[0]["name"] == "既存の人"
    assert rows[0]["pay_type"] is None
    assert rows[0]["bank_info"] is None
    assert rows[0]["hourly_rate"] is None
    assert rows[0]["monthly_rate"] is None


def test_update_distributor_normalizes_hourly_and_monthly_rate(tmp_path):
    """add_distributor 同様、update_distributor でも文字列の数値を int に正規化すること。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="時給", hourly_rate=1000, db_path=db)
    store.update_distributor(did, hourly_rate="1500", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["hourly_rate"] == 1500
    assert isinstance(row["hourly_rate"], int)


def test_update_distributor_leaves_rate_unchanged_when_not_passed(tmp_path):
    """_UNSET の番兵が効いていること。他のフィールドだけ更新しても hourly_rate は変わらない。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="時給", hourly_rate=1200, db_path=db)
    store.update_distributor(did, name="別名", db_path=db)
    row = next(r for r in store.list_distributors(db_path=db) if r["id"] == did)
    assert row["name"] == "別名"
    assert row["hourly_rate"] == 1200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\moro\posting-automation && python -m pytest tests/test_posting_store.py -k "bank or hourly or pay_type or old_distributors" -v`
Expected: FAIL（`add_distributor() got an unexpected keyword argument 'bank_info'` / `KeyError: 'pay_type'`）

- [ ] **Step 3: Write minimal implementation**

`_ensure_schema` の `conn.commit()` の直前に追記:

```python
    # 業務委託(配布員)に 振込先・支払形態・時給額・月額 を持たせる。旧DBは自動でカラム追加。
    dist_cols = {r[1] for r in conn.execute("PRAGMA table_info(distributors)")}
    for col, typ in (("bank_info", "TEXT"), ("pay_type", "TEXT"),
                     ("hourly_rate", "INTEGER"), ("monthly_rate", "INTEGER")):
        if col not in dist_cols:
            conn.execute(f"ALTER TABLE distributors ADD COLUMN {col} {typ}")
```

`add_distributor` / `update_distributor` を差し替え:

```python
def add_distributor(name, *, kind="業務委託", bank_info=None, pay_type=None,
                    hourly_rate=None, monthly_rate=None, active=1, db_path=None):
    return _add("distributors",
                ["name", "kind", "bank_info", "pay_type", "hourly_rate",
                 "monthly_rate", "active"],
                [name, kind, bank_info, pay_type, _int_or_none(hourly_rate),
                 _int_or_none(monthly_rate), int(active)], db_path)


def update_distributor(row_id, *, name=_UNSET, kind=_UNSET, bank_info=_UNSET,
                       pay_type=_UNSET, hourly_rate=_UNSET, monthly_rate=_UNSET,
                       active=_UNSET, db_path=None):
    _update("distributors", row_id,
            {"name": name, "kind": kind, "bank_info": bank_info, "pay_type": pay_type,
             "hourly_rate": (_int_or_none(hourly_rate) if hourly_rate is not _UNSET else _UNSET),
             "monthly_rate": (_int_or_none(monthly_rate) if monthly_rate is not _UNSET else _UNSET),
             "active": active}, db_path)
```

`_UNSET` は「更新しない」の番兵。`hourly_rate`/`monthly_rate` が `_UNSET`（未指定）のときは
`_int_or_none()` に通さず `_UNSET` のまま渡すこと（`_int_or_none(_UNSET)` を呼ぶと
`int(_UNSET)` で例外になるほか、番兵が壊れて全マスタの部分更新が壊れる）。
`update_issue_manual_cost` の `amount` 正規化と同じパターン。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: 既存73件＋新規6件が **すべて PASS**

- [ ] **Step 5: Commit**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat: 業務委託マスタに振込先・支払形態・時給額・月額を追加"
```

---

### Task 2: 日当金額テーブル（distributor_daily_rates）

**Files:**
- Modify: `common/posting_store.py`
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces:
  - `list_daily_rates(distributor_id, *, db_path=None) -> list[dict]`（`id` / `distributor_id` / `work_name` / `amount`。`id` 昇順）
  - `replace_daily_rates(distributor_id, rates, *, db_path=None) -> None`（`rates` は `[{"work_name": str, "amount": int}, ...]`。その配布員の行を**全消し→入れ直し**）

- [ ] **Step 1: Write the failing test**

```python
def test_daily_rates_replace_and_list(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "丁合・配布", "amount": 8000},
                                    {"work_name": "ポスティング", "amount": 7500}], db_path=db)
    rows = store.list_daily_rates(did, db_path=db)
    assert [(r["work_name"], r["amount"]) for r in rows] == [
        ("丁合・配布", 8000), ("ポスティング", 7500)]


def test_daily_rates_replace_overwrites_previous(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "丁合・配布", "amount": 8000}], db_path=db)
    store.replace_daily_rates(did, [{"work_name": "丁合・配布", "amount": 9000}], db_path=db)
    rows = store.list_daily_rates(did, db_path=db)
    assert len(rows) == 1
    assert rows[0]["amount"] == 9000


def test_daily_rates_are_per_distributor(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    a = store.add_distributor("Aさん", pay_type="日当", db_path=db)
    b = store.add_distributor("Bさん", pay_type="日当", db_path=db)
    store.replace_daily_rates(a, [{"work_name": "配布", "amount": 8000}], db_path=db)
    store.replace_daily_rates(b, [{"work_name": "配布", "amount": 6000}], db_path=db)
    assert store.list_daily_rates(a, db_path=db)[0]["amount"] == 8000
    assert store.list_daily_rates(b, db_path=db)[0]["amount"] == 6000


def test_replace_daily_rates_with_empty_clears(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    store.replace_daily_rates(did, [{"work_name": "配布", "amount": 8000}], db_path=db)
    store.replace_daily_rates(did, [], db_path=db)
    assert store.list_daily_rates(did, db_path=db) == []
```

`TABLES` セットにも `"distributor_daily_rates"` を追加すること（`test_init_db_creates_all_tables` が拾う）。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_store.py -k "daily_rates or init_db" -v`
Expected: FAIL（`module 'common.posting_store' has no attribute 'replace_daily_rates'`）

- [ ] **Step 3: Write minimal implementation**

`_ensure_schema` の `executescript` の中（`issue_manual_costs` の後）に追記:

```sql
        CREATE TABLE IF NOT EXISTS distributor_daily_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distributor_id INTEGER NOT NULL,
            work_name TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0);
```

`# --- distributors ---` 節の末尾に追記:

```python
def list_daily_rates(distributor_id, *, db_path=None):
    """支払形態=日当の配布員の、業務名ごとの日当金額。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM distributor_daily_rates WHERE distributor_id=? ORDER BY id",
            (int(distributor_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def replace_daily_rates(distributor_id, rates, *, db_path=None):
    """その配布員の日当金額を丸ごと入れ替える(全消し→入れ直し)。
    画面の data_editor が「編集後の全行」を返すので、差分を取るより入れ替えが素直。"""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM distributor_daily_rates WHERE distributor_id=?",
                     (int(distributor_id),))
        for r in rates:
            name = str(r.get("work_name") or "").strip()
            if not name:
                continue
            conn.execute(
                "INSERT INTO distributor_daily_rates (distributor_id, work_name, amount)"
                " VALUES (?,?,?)",
                (int(distributor_id), name, int(r.get("amount") or 0)))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat: 業務委託マスタに業務名ごとの日当金額を持たせる"
```

---

### Task 3: 小口の配布員（petty_cash.distributor_id）

**Files:**
- Modify: `common/posting_store.py`（`_ensure_schema` / `add_petty_cash`）
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces: `add_petty_cash(date, category_id, amount, *, project_id=None, memo=None, source="manual", other_label=None, distributor_id=None, db_path=None, now=None) -> int`

- [ ] **Step 1: Write the failing test**

```python
def test_petty_cash_stores_distributor(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", db_path=db)
    rid = store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    row = next(r for r in store.list_petty_cash(db_path=db) if r["id"] == rid)
    assert row["distributor_id"] == did


def test_petty_cash_distributor_is_optional(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    rid = store.add_petty_cash("2026-07-17", None, 1500, db_path=db)
    row = next(r for r in store.list_petty_cash(db_path=db) if r["id"] == rid)
    assert row["distributor_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_store.py -k "petty_cash_stores_distributor or petty_cash_distributor_is_optional" -v`
Expected: FAIL（`unexpected keyword argument 'distributor_id'`）

- [ ] **Step 3: Write minimal implementation**

`_ensure_schema` に追記（`pay_cols` の処理の近く）:

```python
    # 小口に配布員を持たせる(誰の分の費用か号別明細で追えるように)。旧DBは自動でカラム追加。
    petty_cols = {r[1] for r in conn.execute("PRAGMA table_info(petty_cash)")}
    if "distributor_id" not in petty_cols:
        conn.execute("ALTER TABLE petty_cash ADD COLUMN distributor_id INTEGER")
```

`add_petty_cash` を差し替え:

```python
def add_petty_cash(date, category_id, amount, *, project_id=None, memo=None,
                   source="manual", other_label=None, distributor_id=None,
                   db_path=None, now=None):
    return _add("petty_cash",
                ["date", "category_id", "amount", "project_id", "memo", "source",
                 "other_label", "distributor_id", "created_at"],
                [date, _int_or_none(category_id), int(amount), _int_or_none(project_id),
                 memo, source, other_label, _int_or_none(distributor_id), _now(now)], db_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat: 小口に配布員を紐づけられるようにする"
```

---

### Task 4: 買掛先マスタの既定の原本区分

**Files:**
- Modify: `common/posting_store.py`
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces:
  - `add_payables_vendor(name, *, default_category=None, default_original_status=None, active=1, db_path=None) -> int`
  - `update_payables_vendor(row_id, *, name=_UNSET, default_category=_UNSET, default_original_status=_UNSET, active=_UNSET, db_path=None) -> None`
  - `find_vendor_by_name(name, *, db_path=None) -> dict | None`（前後の空白を除いた完全一致。無ければ None）

- [ ] **Step 1: Write the failing test**

```python
def test_payables_vendor_default_original_status(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    vid = store.add_payables_vendor("関西電力株式会社", default_category="電気",
                                    default_original_status="振込用紙", db_path=db)
    row = next(r for r in store.list_payables_vendors(db_path=db) if r["id"] == vid)
    assert row["default_original_status"] == "振込用紙"


def test_find_vendor_by_name(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_payables_vendor("関西電力株式会社", default_original_status="振込用紙", db_path=db)
    found = store.find_vendor_by_name("関西電力株式会社", db_path=db)
    assert found is not None
    assert found["default_original_status"] == "振込用紙"


def test_find_vendor_by_name_trims_whitespace(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_payables_vendor("関西電力株式会社", default_original_status="振込用紙", db_path=db)
    assert store.find_vendor_by_name("  関西電力株式会社  ", db_path=db) is not None


def test_find_vendor_by_name_returns_none_when_absent(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    store.add_payables_vendor("関西電力株式会社", db_path=db)
    assert store.find_vendor_by_name("知らない会社", db_path=db) is None
    assert store.find_vendor_by_name("", db_path=db) is None
    assert store.find_vendor_by_name(None, db_path=db) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_store.py -k "vendor" -v`
Expected: FAIL（`unexpected keyword argument 'default_original_status'`）

- [ ] **Step 3: Write minimal implementation**

`_ensure_schema` に追記:

```python
    # 買掛先マスタに「既定の原本区分」を持たせる(買掛登録で自動セットするため)。
    ven_cols = {r[1] for r in conn.execute("PRAGMA table_info(payables_vendors)")}
    if "default_original_status" not in ven_cols:
        conn.execute("ALTER TABLE payables_vendors ADD COLUMN default_original_status TEXT")
```

`payables_vendors` 節を差し替え・追記:

```python
def add_payables_vendor(name, *, default_category=None, default_original_status=None,
                        active=1, db_path=None):
    return _add("payables_vendors",
                ["name", "default_category", "default_original_status", "active"],
                [name, default_category, default_original_status, int(active)], db_path)


def update_payables_vendor(row_id, *, name=_UNSET, default_category=_UNSET,
                           default_original_status=_UNSET, active=_UNSET, db_path=None):
    _update("payables_vendors", row_id,
            {"name": name, "default_category": default_category,
             "default_original_status": default_original_status, "active": active}, db_path)


def find_vendor_by_name(name, *, db_path=None):
    """取引先名(自由入力)が買掛先マスタと完全一致すればその行を返す。無ければ None。
    買掛登録で原本区分を自動セットするために使う。"""
    key = str(name or "").strip()
    if not key:
        return None
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM payables_vendors WHERE TRIM(name)=?",
                           (key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat: 買掛先マスタに既定の原本区分を持たせる"
```

---

### Task 5: 請求への支払形態スナップショットと部数（copies）

**Files:**
- Modify: `common/posting_store.py`（`_ensure_schema` / `add_contract_invoice`）
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces:
  - `add_contract_invoice(distributor_id, issue_date, period_from, period_to, lines, *, pay_type=None, db_path=None, now=None) -> int`
  - `lines` の各要素は `{"project_id", "report_qty", "unit_price", "remark", "other_label", "copies"}`（`copies` は任意）
  - `get_contract_invoice(id)["invoice"]["pay_type"]`、`...["lines"][i]["copies"]` が読める

- [ ] **Step 1: Write the failing test**

```python
def test_contract_invoice_stores_pay_type_snapshot(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    pid = store.add_project("関西ぱど：京阪北版", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3, "unit_price": 8000, "remark": "配布",
          "copies": 3713}],
        pay_type="日当", db_path=db)
    detail = store.get_contract_invoice(iid, db_path=db)
    assert detail["invoice"]["pay_type"] == "日当"
    assert detail["lines"][0]["copies"] == 3713
    assert detail["lines"][0]["amount"] == 3 * 8000


def test_contract_invoice_pay_type_survives_master_change(tmp_path):
    """登録後にマスタの支払形態を変えても、過去の請求の支払形態は変わらない。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    pid = store.add_project("案件", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3, "unit_price": 8000, "remark": "配布"}],
        pay_type="日当", db_path=db)
    store.update_distributor(did, pay_type="歩合", db_path=db)
    assert store.get_contract_invoice(iid, db_path=db)["invoice"]["pay_type"] == "日当"


def test_contract_invoice_without_pay_type_is_null(tmp_path):
    """pay_type を渡さない既存の呼び出しは NULL のまま(=歩合扱い・後方互換)。"""
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", db_path=db)
    pid = store.add_project("案件", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3713, "unit_price": 2.5, "remark": "配布"}],
        db_path=db)
    detail = store.get_contract_invoice(iid, db_path=db)
    assert detail["invoice"]["pay_type"] is None
    assert detail["lines"][0]["copies"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_store.py -k "contract_invoice_stores_pay_type or survives_master_change or without_pay_type" -v`
Expected: FAIL（`unexpected keyword argument 'pay_type'`）

- [ ] **Step 3: Write minimal implementation**

`_ensure_schema` の `ci_cols` の処理に追記:

```python
    if "pay_type" not in ci_cols:
        conn.execute("ALTER TABLE contract_invoices ADD COLUMN pay_type TEXT")
    # 歩合以外(日当・時給・月給)は数量が部数でないため、配布部数を別列で持つ。
    cil_cols = {r[1] for r in conn.execute("PRAGMA table_info(contract_invoice_lines)")}
    if "copies" not in cil_cols:
        conn.execute("ALTER TABLE contract_invoice_lines ADD COLUMN copies INTEGER")
```

`add_contract_invoice` を差し替え:

```python
def add_contract_invoice(distributor_id, issue_date, period_from, period_to, lines,
                         *, pay_type=None, db_path=None, now=None):
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO contract_invoices"
            " (distributor_id, issue_date, period_from, period_to, pay_type, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (_int_or_none(distributor_id), issue_date, period_from, period_to,
             pay_type, _now(now)))
        invoice_id = int(cur.lastrowid)
        for ln in lines:
            qty = float(ln.get("report_qty") or 0)
            price = float(ln.get("unit_price") or 0)
            conn.execute(
                "INSERT INTO contract_invoice_lines"
                " (invoice_id, project_id, report_qty, unit_price, amount, remark,"
                "  other_label, copies)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (invoice_id, _int_or_none(ln.get("project_id")), qty, price,
                 qty * price, ln.get("remark"), ln.get("other_label"),
                 _int_or_none(ln.get("copies"))))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)
    return invoice_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat: 請求に登録時点の支払形態と配布部数を保存する

マスタの現在値で過去請求を描くと「3日」が後日「3枚」に化けるため、
支払形態は登録時点の事実として請求ヘッダに固定する。"
```

---

### Task 6: マスタの使用件数（count_master_usage）

**Files:**
- Modify: `common/posting_store.py`
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Produces: `count_master_usage(master, row_id, *, db_path=None) -> int`
  - `master` は `"project"` / `"expense_category"` / `"payables_vendor"` / `"receivables_client"` / `"distributor"`
  - 未知の `master` は `ValueError`

- [ ] **Step 1: Write the failing test**

```python
def test_count_master_usage_project_counts_all_sources(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("案件", db_path=db)
    did = store.add_distributor("山田太郎", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, project_id=pid, db_path=db)
    store.add_payable(None, None, 8000, date="2026-07-17", project_id=pid, db_path=db)
    store.add_receivable("2026-07", None, 90000, project_id=pid, db_path=db)
    store.add_issue_manual_cost(pid, "配布", 50000, db_path=db)
    store.add_contract_invoice(did, "2026-07-17", "2026-07-01", "2026-07-15",
                               [{"project_id": pid, "report_qty": 1, "unit_price": 100,
                                 "remark": "配布"}], db_path=db)
    assert store.count_master_usage("project", pid, db_path=db) == 5


def test_count_master_usage_zero_for_unused(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("使っていない案件", db_path=db)
    did = store.add_distributor("使っていない人", db_path=db)
    cid = store.add_expense_category("使っていない費目", db_path=db)
    assert store.count_master_usage("project", pid, db_path=db) == 0
    assert store.count_master_usage("distributor", did, db_path=db) == 0
    assert store.count_master_usage("expense_category", cid, db_path=db) == 0


def test_count_master_usage_distributor_counts_invoices_and_petty(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    did = store.add_distributor("山田太郎", db_path=db)
    pid = store.add_project("案件", db_path=db)
    store.add_contract_invoice(did, "2026-07-17", "2026-07-01", "2026-07-15",
                               [{"project_id": pid, "report_qty": 1, "unit_price": 100,
                                 "remark": "配布"}], db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    assert store.count_master_usage("distributor", did, db_path=db) == 2


def test_count_master_usage_category_and_client(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    cid = store.add_expense_category("駐車場代", db_path=db)
    clid = store.add_receivables_client("株式会社アド・バリュー", db_path=db)
    vid = store.add_payables_vendor("関西電力株式会社", db_path=db)
    store.add_petty_cash("2026-07-17", cid, 1500, db_path=db)
    store.add_receivable("2026-07", clid, 90000, db_path=db)
    store.add_payable("2026-07", vid, 8000, db_path=db)
    assert store.count_master_usage("expense_category", cid, db_path=db) == 1
    assert store.count_master_usage("receivables_client", clid, db_path=db) == 1
    assert store.count_master_usage("payables_vendor", vid, db_path=db) == 1


def test_count_master_usage_rejects_unknown_master(tmp_path):
    import pytest
    db = os.path.join(tmp_path, "t.db")
    with pytest.raises(ValueError):
        store.count_master_usage("知らないマスタ", 1, db_path=db)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_store.py -k "count_master_usage" -v`
Expected: FAIL（`has no attribute 'count_master_usage'`）

- [ ] **Step 3: Write minimal implementation**

`seed_masters` の直前に追記:

```python
# マスタごとに「どのテーブルのどの列で使われているか」。停止中方式の判定に使う。
_MASTER_USAGE = {
    "project": [("petty_cash", "project_id"), ("payables", "project_id"),
                ("receivables", "project_id"), ("contract_invoice_lines", "project_id"),
                ("issue_manual_costs", "project_id")],
    "expense_category": [("petty_cash", "category_id")],
    "payables_vendor": [("payables", "vendor_id")],
    "receivables_client": [("receivables", "client_id")],
    "distributor": [("contract_invoices", "distributor_id"),
                    ("petty_cash", "distributor_id")],
}


def count_master_usage(master, row_id, *, db_path=None) -> int:
    """マスタの行が実データで何件使われているかを数える。
    0件なら消してよい(物理削除)、1件以上なら消すと過去データの表示が欠けるので停止中にする。"""
    if master not in _MASTER_USAGE:
        raise ValueError(f"unknown master: {master}")
    conn = _connect(db_path)
    try:
        total = 0
        for table, col in _MASTER_USAGE[master]:
            row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=?",
                               (int(row_id),)).fetchone()
            total += int(row[0])
        return total
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat: マスタの使用件数を数える(停止中方式の判定用)"
```

---

### Task 7: 純関数 — 原本区分の一致と、削除か停止中かの判定

**Files:**
- Modify: `common/posting_logic.py`
- Test: `tests/test_posting_logic.py`

**Interfaces:**
- Produces:
  - `resolve_original_status(vendor_name, vendors) -> str | None`（`vendors` は `list_payables_vendors()` の戻り）
  - `master_delete_action(usage_count) -> "delete" | "deactivate"`

- [ ] **Step 1: Write the failing test**

`tests/test_posting_logic.py` の末尾に追記:

```python
# ---- 買掛の原本区分オートセット ----
_VENDORS = [
    {"name": "関西電力株式会社", "default_original_status": "振込用紙"},
    {"name": "株式会社スペースリーダー", "default_original_status": "クレジット"},
    {"name": "既定なしの会社", "default_original_status": None},
]


def test_resolve_original_status_matches_by_name():
    assert L.resolve_original_status("関西電力株式会社", _VENDORS) == "振込用紙"
    assert L.resolve_original_status("株式会社スペースリーダー", _VENDORS) == "クレジット"


def test_resolve_original_status_trims_whitespace():
    assert L.resolve_original_status("  関西電力株式会社 ", _VENDORS) == "振込用紙"


def test_resolve_original_status_returns_none_when_no_match():
    assert L.resolve_original_status("知らない会社", _VENDORS) is None
    assert L.resolve_original_status("", _VENDORS) is None
    assert L.resolve_original_status(None, _VENDORS) is None


def test_resolve_original_status_returns_none_when_master_has_no_default():
    assert L.resolve_original_status("既定なしの会社", _VENDORS) is None


# ---- マスタ削除 or 停止中 ----
def test_master_delete_action_deletes_when_unused():
    assert L.master_delete_action(0) == "delete"


def test_master_delete_action_deactivates_when_used():
    assert L.master_delete_action(1) == "deactivate"
    assert L.master_delete_action(12) == "deactivate"


def test_master_delete_action_deactivates_when_usage_count_is_none():
    """使用件数が不明(None)なときに安易に0とみなして削除可にしてはいけない(安全側)。"""
    assert L.master_delete_action(None) == "deactivate"


def test_master_delete_action_deactivates_on_invalid_type():
    """型不正の値も安全側(消さない)に倒す。"""
    assert L.master_delete_action("abc") == "deactivate"


def test_master_delete_action_deactivates_on_negative_value():
    """ありえない負値も安全側(消さない)に倒す。"""
    assert L.master_delete_action(-1) == "deactivate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_logic.py -k "resolve_original_status or master_delete_action" -v`
Expected: FAIL（`has no attribute 'resolve_original_status'`）

- [ ] **Step 3: Write minimal implementation**

`common/posting_logic.py` の `payment_method` の後に追記:

```python
def resolve_original_status(vendor_name, vendors):
    """取引先名(自由入力)が買掛先マスタと一致したら、その既定の原本区分を返す。
    一致しない・マスタに既定が無い場合は None(＝画面は既定値のまま)。"""
    key = str(vendor_name or "").strip()
    if not key:
        return None
    for v in vendors or []:
        if str(v.get("name") or "").strip() == key:
            return v.get("default_original_status") or None
    return None


def master_delete_action(usage_count) -> str:
    """マスタの行を消すときの動き。
    使用実績が「非負整数として明確に0」であるときだけ物理削除("delete")。
    それ以外(None・型不正・負値を含む)はすべて停止中("deactivate"、＝安全側)にする。

    なぜ安全側に倒すか: 配布員は入れ替わりが激しく、使用中のマスタを物理削除すると
    過去の号別明細・報告書からその配布員の名前が消えてしまう(それを防ぐのが停止中方式の
    目的そのもの)。使用件数が不明(None)の値を安易に0とみなして「削除可」と判定するのは、
    この目的の裏を突く挙動になるため避ける。判定できない入力に対しても例外は投げず、
    消えない側(deactivate)を返すことで、画面が落ちるより実害を小さくする。"""
    if isinstance(usage_count, bool):
        return "deactivate"
    if isinstance(usage_count, int) and usage_count == 0:
        return "delete"
    return "deactivate"
```

注: `int(usage_count or 0)` のような falsy 判定は使わない。`None` が渡ったときに `0`(＝削除可)へ丸められてしまい、
「使用中のマスタを物理削除して過去データから名前を消してしまう」事故につながるため(2026-07-17 レビューで指摘・修正済み)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/posting_logic.py tests/test_posting_logic.py
git commit -m "feat: 原本区分のマスタ一致と、削除/停止中の判定を純関数で追加"
```

---

### Task 8: 純関数 — 支払形態に応じた単位と配布部数

**Files:**
- Modify: `common/posting_logic.py`（`unit_for` / `qty_label` / `delivered_copies`）
- Test: `tests/test_posting_logic.py`

**Interfaces:**
- Produces:
  - `unit_for(remark, pay_type=None) -> str`
  - `qty_label(qty, remark, pay_type=None) -> str`
  - `line_copies(line, pay_type=None) -> float`
  - `delivered_copies(lines, pay_type=None) -> float`

**⚠️ 後方互換が最重要のタスク。** `pay_type` を渡さない既存の呼び出しが1つも動きを変えないこと。

- [ ] **Step 1: Write the failing test**

```python
# ---- 支払形態に応じた単位 ----
def test_unit_for_without_pay_type_keeps_current_behavior():
    """既存の呼び出し(pay_type なし)は今までと同じ。"""
    assert L.unit_for("配布") == "枚"
    assert L.unit_for("挟み込み") == "枚"
    assert L.unit_for("交通費") == "一式"
    assert L.unit_for("手当") == "一式"
    assert L.unit_for("その他") == "一式"


def test_unit_for_by_pay_type_on_delivery_rows():
    assert L.unit_for("配布", "日当") == "日"
    assert L.unit_for("配布", "時給") == "時間"
    assert L.unit_for("配布", "月給") == "一式"
    assert L.unit_for("配布", "歩合") == "枚"
    assert L.unit_for("挟み込み", "日当") == "日"


def test_unit_for_non_delivery_rows_ignore_pay_type():
    """日当の人でも交通費・手当の行は「一式」。支払形態で一律に上書きしない。"""
    for pt in ("日当", "時給", "月給", "歩合", None):
        assert L.unit_for("交通費", pt) == "一式"
        assert L.unit_for("手当", pt) == "一式"
        assert L.unit_for("その他", pt) == "一式"


def test_qty_label_with_pay_type():
    assert L.qty_label(3, "配布", "日当") == "3 日"
    assert L.qty_label(6.5, "配布", "時給") == "6.5 時間"
    assert L.qty_label(1, "配布", "月給") == "一式"
    assert L.qty_label(3713, "配布", "歩合") == "3,713 枚"


def test_qty_label_without_pay_type_keeps_current_behavior():
    assert L.qty_label(3713, "配布") == "3,713 枚"
    assert L.qty_label(1, "交通費") == "一式"


# ---- 配布部数 ----
def test_line_copies_uses_qty_for_houbai_and_none():
    line = {"report_qty": 3713, "copies": 999, "remark": "配布"}
    assert L.line_copies(line, "歩合") == 3713
    assert L.line_copies(line, None) == 3713


def test_line_copies_uses_copies_column_for_other_pay_types():
    line = {"report_qty": 3, "copies": 3713, "remark": "配布"}
    assert L.line_copies(line, "日当") == 3713
    assert L.line_copies(line, "時給") == 3713
    assert L.line_copies(line, "月給") == 3713


def test_line_copies_is_zero_when_copies_missing():
    assert L.line_copies({"report_qty": 3, "remark": "配布"}, "日当") == 0
    assert L.line_copies({"report_qty": 3, "copies": None, "remark": "配布"}, "日当") == 0


def test_line_copies_is_zero_for_non_delivery_rows():
    assert L.line_copies({"report_qty": 1, "copies": 500, "remark": "交通費"}, "日当") == 0
    assert L.line_copies({"report_qty": 1, "remark": "手当"}, "歩合") == 0


def test_delivered_copies_without_pay_type_keeps_current_behavior():
    lines = [
        {"report_qty": 3713, "remark": "配布"},
        {"report_qty": 500, "remark": "挟み込み"},
        {"report_qty": 1, "remark": "交通費"},
    ]
    assert L.delivered_copies(lines) == 3713 + 500


def test_delivered_copies_for_nichito_uses_copies_column():
    lines = [
        {"report_qty": 3, "copies": 3713, "remark": "配布"},
        {"report_qty": 1, "copies": 500, "remark": "挟み込み"},
        {"report_qty": 1, "copies": 99, "remark": "交通費"},
    ]
    assert L.delivered_copies(lines, "日当") == 3713 + 500


# ---- unit_for と line_copies で未知の pay_type の解釈を揃える ----
# レビュー指摘: 未知の pay_type(特に画面から来る空文字)で unit_for が「枚」、
# line_copies が copies列(=0) に倒れると、画面は「3,713 枚」と表示するのに
# 報告部数は「0部」になる。例外も出ずに静かに矛盾するので、両者は必ず同じ側(歩合)に倒す。
def test_line_copies_treats_unknown_pay_type_as_houbai():
    line = {"report_qty": 3713, "copies": 999, "remark": "配布"}
    assert L.line_copies(line, "") == 3713
    assert L.line_copies(line, "未知の形態") == 3713


def test_unit_for_agrees_with_line_copies_on_unknown_pay_type():
    line = {"report_qty": 3713, "copies": 999, "remark": "配布"}
    for pay_type in ("", "未知の形態"):
        assert L.unit_for("配布", pay_type) == "枚"
        assert L.line_copies(line, pay_type) == 3713


def test_delivered_copies_empty_string_pay_type_keeps_current_behavior():
    lines = [
        {"report_qty": 3713, "copies": 999, "remark": "配布"},
        {"report_qty": 500, "copies": 1, "remark": "挟み込み"},
        {"report_qty": 1, "copies": 500, "remark": "交通費"},
    ]
    assert L.delivered_copies(lines, "") == 3713 + 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_posting_logic.py -k "unit_for or qty_label or copies" -v`
Expected: FAIL（`unit_for() takes 1 positional argument but 2 were given` / `has no attribute 'line_copies'`）

- [ ] **Step 3: Write minimal implementation**

`common/posting_logic.py` の上部の定数の下に追記し、`unit_for` / `qty_label` / `delivered_copies` を差し替える:

```python
# 支払形態ごとの、配布・挟み込み行の数量の単位。
# 歩合(と未設定)は数量がそのまま部数なので「枚」＝これまでの動き。
# 月給は数量を数えない(月額×1)ので「一式」。
_PAY_TYPE_UNITS = {"日当": "日", "時給": "時間", "月給": "一式", "歩合": "枚"}


def unit_for(remark, pay_type=None) -> str:
    """数量の単位。交通費・手当・その他は数を数えないので『一式』(支払形態によらない)。
    配布・挟み込みのときだけ支払形態で単位が変わる(日当=日 / 時給=時間 / 月給=一式 / 歩合=枚)。"""
    if not is_delivery(remark):
        return "一式"
    return _PAY_TYPE_UNITS.get(pay_type, "枚")


def qty_label(qty, remark, pay_type=None) -> str:
    """明細の数量表示。歩合の配布なら『3,713 枚』、日当なら『3 日』。
    単位が『一式』のものは数を数えないので『一式』だけを出す(「1 一式」とは出さない)。"""
    unit = unit_for(remark, pay_type)
    if unit == "一式":
        return unit
    return f"{fmt_num(qty)} {unit}"


def line_copies(line, pay_type=None):
    """その明細行の配布部数。歩合(と未設定・未知の値)は数量がそのまま部数＝これまでの動き。
    日当・時給・月給は数量が日数/時間なので、別列の copies を使う。
    配布・挟み込み以外の行は部数を数えない。

    未知の pay_type を歩合に倒すのは unit_for と解釈を揃えるため。片方だけ非歩合に倒れると
    「3,713 枚と表示しているのに報告数は0部」という静かな食い違いが起きる。"""
    if not is_delivery((line or {}).get("remark")):
        return 0
    if pay_type not in ("日当", "時給", "月給"):
        return _num((line or {}).get("report_qty"))
    return _num((line or {}).get("copies"))


def delivered_copies(lines, pay_type=None):
    return sum(line_copies(l, pay_type) for l in lines)
```

⚠️ `qty_label` は `unit == "一式"` で判定する。`is_delivery` で判定すると**月給の配布行が「1 一式」になってしまう**（月給の単位は一式のため）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS。**特に既存の `test_delivered_copies_counts_only_haifu_and_hasamikomi` と `test_qty_label_*` が変わらず通ること**

- [ ] **Step 5: Commit**

```bash
git add common/posting_logic.py tests/test_posting_logic.py
git commit -m "feat: 支払形態に応じた数量の単位と配布部数を純関数で追加

pay_type 未指定は歩合と同じ＝現行動作のまま(後方互換)。"
```

---

### Task 9: 削除ボタンの共通部品（confirm_delete）

**Files:**
- Modify: `common/ui.py`
- Test: `tests/test_pages_smoke.py`（**新規作成**）

**Interfaces:**
- Produces: `confirm_delete(*, key, detail, on_confirm, label="削除", warning=None, success="削除しました") -> None`
  - 押下 → session_state に確認待ちを立てて rerun → 確認UI → 「はい、削除する」で `on_confirm()` 実行 → `flash(success)` → rerun

- [ ] **Step 1: Write the failing test**

`tests/test_pages_smoke.py` を新規作成:

```python
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


def test_confirm_delete_shows_confirmation_before_running(db):
    """confirm_delete は押しただけでは実行せず、確認を出す。"""
    from common import ui
    called = []

    def _page():
        import streamlit as st  # noqa: F401
        ui.confirm_delete(key="t1", detail="7/17 ／ 駐車場代 ／ ¥1,500",
                          on_confirm=lambda: called.append(1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert any(b.label == "削除" for b in at.button)
    at.button(key="t1_btn").click().run()
    # 確認が出て、まだ実行されていない
    assert called == []
    assert len(at.warning) == 1
    assert any(b.label == "はい、削除する" for b in at.button)


def test_confirm_delete_runs_on_confirm(db):
    from common import ui
    called = []

    def _page():
        import streamlit as st  # noqa: F401
        ui.confirm_delete(key="t2", detail="対象", on_confirm=lambda: called.append(1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t2_btn").click().run()
    at.button(key="t2_ok").click().run()
    assert called == [1]


def test_confirm_delete_cancel_does_not_run(db):
    from common import ui
    called = []

    def _page():
        import streamlit as st  # noqa: F401
        ui.confirm_delete(key="t3", detail="対象", on_confirm=lambda: called.append(1))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.button(key="t3_btn").click().run()
    at.button(key="t3_no").click().run()
    assert called == []
    assert len(at.warning) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -v`
Expected: FAIL（`module 'common.ui' has no attribute 'confirm_delete'`）

- [ ] **Step 3: Write minimal implementation**

`common/ui.py` の `show_flash` の後に追記:

```python
def confirm_delete(*, key: str, detail: str, on_confirm, label: str = "削除",
                   warning: str = None, success: str = "削除しました"):
    """削除→確認→実行を全画面で同じ挙動にする共通部品。
    ボタンを押した時点では消さず、session_state に確認待ちを立てて確認UIを出す。
    「はい」で on_confirm() を実行し、flash で結果を知らせる。

    key      : 画面内で一意な文字列(行idを含めること。固定keyだと別の行を消しかねない)
    detail   : 確認画面に出す対象の内容(日付・金額など)
    on_confirm: 実際に消す処理(引数なしの呼び出し可能オブジェクト)
    label    : ボタンの文言(マスタでは「停止中にする」を渡す)
    warning  : 確認の見出し(省略時は「削除しますか？」)
    success  : 実行後に出すメッセージ
    """
    pending = f"_del_pending_{key}"
    if st.session_state.get(pending):
        st.warning(warning or "⚠️ 削除しますか？")
        if detail:
            st.caption(detail)
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("はい、削除する", type="primary", key=f"{key}_ok"):
            on_confirm()
            st.session_state.pop(pending, None)
            flash(success)
            st.rerun()
        if c2.button("やめる", key=f"{key}_no"):
            st.session_state.pop(pending, None)
            st.rerun()
        return
    if st.button(label, key=f"{key}_btn"):
        st.session_state[pending] = True
        st.rerun()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add common/ui.py tests/test_pages_smoke.py
git commit -m "feat: 削除→確認→実行の共通部品(confirm_delete)を追加"
```

---

### Task 10: マスタ管理 — タブ改名・項目追加・停止中方式・削除

**Files:**
- Modify: `pages/05_マスタ管理.py`（全面的に書き直し）
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: Task 1・2・4・6 の store 関数、Task 7 の `master_delete_action`、Task 9 の `confirm_delete`

- [ ] **Step 1: Write the failing test**

`tests/test_pages_smoke.py` に追記:

```python
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
    store.add_distributor("現役の人", db_path=db)
    store.add_distributor("辞めた人", active=0, db_path=db)
    at = _run("05_マスタ管理.py")
    body = str(at)
    assert "現役の人" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -k master -v`
Expected: FAIL（タブ名が「配布委託先」のまま）

- [ ] **Step 3: Write minimal implementation**

`pages/05_マスタ管理.py` を以下で全面的に置き換える:

```python
import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, nice_table, flash, show_flash, confirm_delete

apply_app_style()
st.title("マスタ管理")

_ORIGINAL_STATUSES = ["原本あり", "本社", "クレジット", "振込用紙", "なし"]
_PAY_TYPES = ["歩合", "日当", "時給", "月給"]


def _split_active(rows):
    """有効な行と停止中の行に分ける。一覧は有効だけを出し、停止中は折りたたみへ。"""
    return ([r for r in rows if r.get("active", 1)],
            [r for r in rows if not r.get("active", 1)])


def _remove_ui(master, row, *, label_name, update_fn):
    """削除ボタン。使用実績があれば物理削除でなく停止中にする(過去データを守るため)。"""
    n = store.count_master_usage(master, row["id"])
    if posting_logic.master_delete_action(n) == "delete":
        confirm_delete(
            key=f"del_{master}_{row['id']}", label="削除",
            detail=f"{label_name}「{row['name']}」を削除します。使用実績はありません。",
            on_confirm=lambda: _delete_master(master, row["id"]),
            success="削除しました")
    else:
        confirm_delete(
            key=f"off_{master}_{row['id']}", label="停止中にする",
            warning=f"⚠️ 「{row['name']}」は {n}件のデータで使用中です。",
            detail="過去データを残すため、削除ではなく停止中にします"
                   "（登録の選択肢から消えるだけで、一覧・報告書の表示は変わりません）。",
            on_confirm=lambda: update_fn(row["id"], active=0),
            success="停止中にしました")


_DELETE_FNS = {
    "project": store.delete_project,
    "expense_category": store.delete_expense_category,
    "payables_vendor": store.delete_payables_vendor,
    "receivables_client": store.delete_receivables_client,
    "distributor": store.delete_distributor,
}


def _delete_master(master, row_id):
    _DELETE_FNS[master](row_id)


def _inactive_ui(master, inactive, *, update_fn):
    """停止中のマスタは折りたたみの中に。ここから有効に戻せる。"""
    if not inactive:
        return
    with st.expander(f"停止中（{len(inactive)}件）", expanded=False):
        for r in inactive:
            c1, c2 = st.columns([3, 1])
            c1.write(r["name"])
            if c2.button("有効に戻す", key=f"on_{master}_{r['id']}"):
                update_fn(r["id"], active=1)
                flash("有効に戻しました")
                st.rerun()


def _rows_ui(master, rows, *, update_fn, label_name):
    """有効な行を1行ずつ出し、右端に削除(or 停止中)ボタンを置く。"""
    if not rows:
        st.caption(f"{label_name}はまだ登録されていません。")
        return
    for r in rows:
        c1, c2 = st.columns([4, 1])
        c1.write(r["name"])
        with c2:
            _remove_ui(master, r, label_name=label_name, update_fn=update_fn)


def _simple_master(label, master, list_fn, add_fn, update_fn):
    show_flash()
    active, inactive = _split_active(list_fn())
    _rows_ui(master, active, update_fn=update_fn, label_name=label)
    _inactive_ui(master, inactive, update_fn=update_fn)
    with st.form(f"add_{label}", clear_on_submit=True):
        name = st.text_input(f"{label}名を追加")
        if st.form_submit_button("追加") and name.strip():
            add_fn(name.strip())
            flash(f"{label}を追加しました")
            st.rerun()


tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["案件", "費目（小口）", "買掛先", "売掛先", "業務委託"])

with tab1:
    _simple_master("案件", "project", store.list_projects,
                   store.add_project, store.update_project)
with tab2:
    _simple_master("費目", "expense_category", store.list_expense_categories,
                   store.add_expense_category, store.update_expense_category)

with tab3:
    show_flash()
    active, inactive = _split_active(store.list_payables_vendors())
    disp = [{"取引先": r["name"], "既定の費目": r.get("default_category") or "",
             "既定の原本区分": r.get("default_original_status") or ""} for r in active]
    nice_table(disp, "買掛先はまだ登録されていません。")
    st.caption("既定の原本区分を入れておくと、買掛登録で取引先名が一致したときに自動で入ります。")
    for r in active:
        c1, c2 = st.columns([4, 1])
        c1.write(r["name"])
        with c2:
            _remove_ui("payables_vendor", r, label_name="買掛先",
                       update_fn=store.update_payables_vendor)
    _inactive_ui("payables_vendor", inactive, update_fn=store.update_payables_vendor)
    with st.form("add_vendor", clear_on_submit=True):
        n = st.text_input("取引先名")
        c = st.text_input("既定の費目（家賃・電気 など）")
        o = st.selectbox("既定の原本区分", ["(なし)"] + _ORIGINAL_STATUSES)
        if st.form_submit_button("追加") and n.strip():
            store.add_payables_vendor(
                n.strip(), default_category=(c.strip() or None),
                default_original_status=(None if o == "(なし)" else o))
            flash("買掛先を追加しました")
            st.rerun()

with tab4:
    _simple_master("売掛先", "receivables_client", store.list_receivables_clients,
                   store.add_receivables_client, store.update_receivables_client)

with tab5:
    show_flash()
    active, inactive = _split_active(store.list_distributors())
    disp = [{"配布員 氏名": r["name"], "区分": r.get("kind") or "",
             "支払形態": r.get("pay_type") or "",
             "時給額": r.get("hourly_rate") or "", "月額": r.get("monthly_rate") or "",
             "振込先": r.get("bank_info") or ""} for r in active]
    nice_table(disp, "業務委託はまだ登録されていません。")
    for r in active:
        c1, c2 = st.columns([4, 1])
        c1.write(r["name"])
        with c2:
            _remove_ui("distributor", r, label_name="業務委託",
                       update_fn=store.update_distributor)
    _inactive_ui("distributor", inactive, update_fn=store.update_distributor)

    with st.form("add_dist", clear_on_submit=True):
        n = st.text_input("配布員 氏名")
        kind = st.selectbox("区分（雇用形態）", ["業務委託", "自社社員", "アルバイト"])
        pay_type = st.selectbox("支払形態（報酬の計算方法）", _PAY_TYPES)
        bank = st.text_area("振込先", placeholder="例：三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ")
        h1, h2 = st.columns(2)
        hourly = h1.number_input("時給額", min_value=0, step=1)
        monthly = h2.number_input("月額", min_value=0, step=1)
        st.caption("時給額は支払形態が「時給」のとき、月額は「月給」のときだけ使います。"
                   "日当の金額は、登録した後に下の「日当金額の設定」で入れてください。")
        if st.form_submit_button("追加") and n.strip():
            store.add_distributor(n.strip(), kind=kind, pay_type=pay_type,
                                  bank_info=(bank.strip() or None),
                                  hourly_rate=(int(hourly) or None),
                                  monthly_rate=(int(monthly) or None))
            flash("業務委託を追加しました")
            st.rerun()

    # --- 日当金額の設定（支払形態=日当の人だけ）---
    # st.form の中では「日当を選んだ瞬間に表を出す」ができない(Streamlitの仕様)ため、
    # 登録フォームとは別のセクションに置く。
    st.divider()
    st.markdown("**日当金額の設定**")
    nichito = [r for r in active if r.get("pay_type") == "日当"]
    if not nichito:
        st.caption("支払形態が「日当」の業務委託がいません。上で登録してください。")
    else:
        name2id = {r["name"]: r["id"] for r in nichito}
        pick = st.selectbox("配布員", list(name2id.keys()), key="rate_pick")
        did = name2id[pick]
        rates = store.list_daily_rates(did)
        base = pd.DataFrame(
            [{"業務名": r["work_name"], "金額": int(r["amount"])} for r in rates]
            or [{"業務名": "", "金額": 0}])
        edited = st.data_editor(
            base, num_rows="dynamic", use_container_width=True,
            column_config={"金額": st.column_config.NumberColumn(min_value=0, step=1,
                                                                format="localized")},
            key=f"rate_editor_{did}")
        st.caption("ここで登録した業務名と金額が、業務委託登録の明細で選べるようになります。")
        if st.button("日当金額を保存", key="rate_save"):
            store.replace_daily_rates(did, [
                {"work_name": str(r["業務名"]), "amount": int(r["金額"] or 0)}
                for _, r in edited.iterrows() if str(r["業務名"] or "").strip()])
            flash("日当金額を保存しました")
            st.rerun()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add pages/05_マスタ管理.py tests/test_pages_smoke.py
git commit -m "feat: マスタ管理に停止中方式・削除・原本区分・支払形態・日当金額を追加

タブ名を「配布委託先」→「業務委託」に変更。使用中のマスタは物理削除
せず停止中にし、過去データの名前が欠けないようにする。"
```

---

### Task 11: 小口の配布員欄と、買掛の原本区分オートセット、各一覧の削除

**Files:**
- Modify: `pages/01_経費・買掛・売掛.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: Task 3 の `add_petty_cash(distributor_id=...)`、Task 7 の `resolve_original_status`、Task 9 の `confirm_delete`

- [ ] **Step 1: Write the failing test**

```python
def test_expense_page_renders(db):
    at = _run("01_経費・買掛・売掛.py")
    assert not at.exception


def test_petty_form_has_distributor_select(db):
    store.add_distributor("山田太郎", db_path=db)
    at = _run("01_経費・買掛・売掛.py")
    labels = [s.label for s in at.selectbox]
    assert "配布員(任意)" in labels


def test_petty_list_shows_distributor_name(db):
    did = store.add_distributor("山田太郎", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, distributor_id=did, db_path=db)
    at = _run("01_経費・買掛・売掛.py")
    assert "山田太郎" in str(at)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -k "petty or expense_page" -v`
Expected: FAIL（「配布員(任意)」の selectbox が無い）

- [ ] **Step 3: Write minimal implementation**

**(a)** import に `confirm_delete` を足す:

```python
from common.ui import (apply_app_style, section_export, nice_table, period_picker,
                       flash, show_flash, confirm_delete)
```

**(b)** `_project_options()` の下に追記:

```python
def _distributor_options():
    return {d["name"]: d["id"] for d in store.list_distributors(only_active=True)}


def _delete_rows_ui(rows, disp, key_prefix, delete_fn, detail_fn):
    """一覧の各行に削除ボタンを出す。行idを key に含めて取り違えを防ぐ。"""
    if not rows:
        return
    st.markdown("**行を削除**")
    for r, d in zip(rows, disp):
        c1, c2 = st.columns([5, 1])
        c1.caption(detail_fn(r, d))
        with c2:
            confirm_delete(key=f"{key_prefix}_{r['id']}", detail=detail_fn(r, d),
                           on_confirm=lambda rid=r["id"]: delete_fn(rid))
```

**(c)** 小口の登録フォーム（`with st.form("petty", ...)`）の `proj` の直後に配布員欄を足す:

```python
            dists = _distributor_options()
            dist = st.selectbox("配布員(任意)", ["(なし)"] + list(dists.keys()),
                                help="この費用が誰の分か。号別明細の雑費の内訳に出ます。")
```

同フォームの `payload` に `"distributor_id": dists.get(dist)` を足し、
`store.add_petty_cash(...)` の呼び出し2箇所（重複確認の分岐前と `petty_pending` の「はい、登録する」）に
`distributor_id=payload["distributor_id"]` / `distributor_id=p.get("distributor_id")` を渡す。

**(d)** 小口の一覧タブ（`with tab_list:`）を差し替え:

```python
    with tab_list:
        show_flash()
        st.markdown("**登録済みの小口一覧**")
        _cats, _projs = _names(store.list_expense_categories), _names(store.list_projects)
        _dists = _names(store.list_distributors)
        _rows = _period_filter(store.list_petty_cash(), "date", "petty_period", "小口")
        _disp = [{"日付": r["date"] or "", "配布員": _dists.get(r.get("distributor_id"), ""),
                  "費目": _cats.get(r["category_id"], ""),
                  "金額": _yen(r["amount"]), "案件": _projs.get(r["project_id"], ""),
                  "メモ": r["memo"] or "",
                  "登録日": (r.get("created_at") or "")[:10]} for r in _rows]
        nice_table(_disp, "小口の登録はまだありません。")
        section_export(_disp, "小口一覧", key="petty")
        _delete_rows_ui(_rows, _disp, "del_petty", store.delete_petty_cash,
                        lambda r, d: f'{d["日付"] or "日付なし"} ／ {d["費目"]} ／ {d["金額"]}')
```

**(e)** 買掛の登録フォームの `original` を差し替え（オートセット）:

```python
            _vendors = store.list_payables_vendors()
            _auto = posting_logic.resolve_original_status(vendor, _vendors)
            original = st.selectbox(
                "原本区分", _ORIGINAL_STATUSES,
                index=(_ORIGINAL_STATUSES.index(_auto) if _auto in _ORIGINAL_STATUSES else 0))
            if _auto:
                st.caption(f"✔️ 買掛先マスタの既定「{_auto}」を反映しました（変更できます）。")
```

ファイル冒頭の `_LIST_TAB` の近くに定数を足す:

```python
_ORIGINAL_STATUSES = ["原本あり", "本社", "クレジット", "振込用紙", "なし"]
```

⚠️ `vendor` は同じ form 内の `st.text_input` の値。form は submit するまで再実行されないため、
**オートセットが効くのは「AI読み取りで vendor が入った状態で再実行された後」または「一度登録して戻ってきた後」**になる。
手入力の途中では反映されない（Streamlit の form の仕様）。caption でそれと分かるようにしてある。

**(f)** 買掛の一覧タブと売掛の一覧タブにも `show_flash()` と `_delete_rows_ui` を足す:

```python
        # 買掛の一覧タブの末尾
        _delete_rows_ui(_rows, _disp, "del_pay", store.delete_payable,
                        lambda r, d: f'{d["請求書の日付"] or d["請求月度"]} ／ {d["取引先"]} ／ {d["金額"]}')

        # 売掛の一覧タブの末尾
        _delete_rows_ui(_rows, _disp, "del_recv", store.delete_receivable,
                        lambda r, d: f'{d["月度"]} ／ {d["売掛先"]} ／ {d["金額"]}')
```

両タブの先頭にも `show_flash()` を足すこと（削除後のメッセージを出すため）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add pages/01_経費・買掛・売掛.py tests/test_pages_smoke.py
git commit -m "feat: 小口に配布員欄、買掛に原本区分の自動セット、各一覧に削除ボタン"
```

---

### Task 12: 業務委託登録 — 支払形態に応じた明細と自動計算

**Files:**
- Modify: `pages/02_業務委託登録.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: Task 1・2・5 の store、Task 8 の `qty_label` / `delivered_copies`、Task 9 の `confirm_delete`

- [ ] **Step 1: Write the failing test**

```python
def _seed_invoice(db, pay_type="歩合", copies=None):
    did = store.add_distributor("山田太郎", pay_type=pay_type, db_path=db)
    pid = store.add_project("案件A", db_path=db)
    iid = store.add_contract_invoice(
        did, "2026-07-17", "2026-07-01", "2026-07-15",
        [{"project_id": pid, "report_qty": 3, "unit_price": 8000, "remark": "配布",
          "copies": copies}],
        pay_type=pay_type, db_path=db)
    return did, pid, iid


def test_contract_page_renders(db):
    store.add_distributor("山田太郎", pay_type="歩合", db_path=db)
    at = _run("02_業務委託登録.py")
    assert not at.exception


def test_contract_page_shows_pay_type_of_selected_distributor(db):
    store.add_distributor("山田太郎", pay_type="日当", db_path=db)
    at = _run("02_業務委託登録.py")
    assert "日当" in str(at)


def test_contract_list_shows_nichito_qty_in_days(db):
    """日当で登録した請求は、一覧で数量が「日」で出る(枚ではない)。"""
    _seed_invoice(db, pay_type="日当", copies=3713)
    at = _run("02_業務委託登録.py")
    body = str(at)
    assert "山田太郎" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -k contract -v`
Expected: FAIL（支払形態が画面に出ていない）

- [ ] **Step 3: Write minimal implementation**

**(a)** import に `confirm_delete` を足す。

**(b)** `dists` の作り方を変えて、配布員の行そのものを持つ:

```python
dist_rows = {d["name"]: d for d in store.list_distributors(only_active=True)}
dists = {name: d["id"] for name, d in dist_rows.items()}
```

**(c)** 登録タブの `dist_name` の直後に支払形態の表示と、明細エディタの組み立てを差し替え:

```python
    _dist = dist_rows[dist_name]
    pay_type = _dist.get("pay_type") or "歩合"
    st.caption(f"支払形態: **{pay_type}**　"
               f"{'（数量は日数を入れてください）' if pay_type == '日当' else ''}"
               f"{'（数量は時間を入れてください）' if pay_type == '時給' else ''}"
               f"{'（数量は1固定・月額をそのまま請求します）' if pay_type == '月給' else ''}"
               f"{'（数量は部数を入れてください）' if pay_type == '歩合' else ''}")

    # 支払形態ごとの単価の既定値。歩合だけは号ごとに違うのでマスタに持たず 0 のまま。
    _rates = {r["work_name"]: int(r["amount"]) for r in store.list_daily_rates(_dist["id"])} \
        if pay_type == "日当" else {}
    _default_price = 0.0
    if pay_type == "時給":
        _default_price = float(_dist.get("hourly_rate") or 0)
    elif pay_type == "月給":
        _default_price = float(_dist.get("monthly_rate") or 0)

    _qty_label = {"日当": "数量(日)", "時給": "数量(時間)", "月給": "数量(1固定)"}.get(
        pay_type, "数量(枚)")
    _needs_copies = pay_type != "歩合"

    _base = {"案件": "", "種別": "配布", "単価": _default_price,
             "数量": 1.0 if pay_type == "月給" else 0.0, "その他の案件名": ""}
    _cols = ["案件", "種別", "単価", "数量", "その他の案件名"]
    _conf = {
        "案件": st.column_config.SelectboxColumn(options=list(projs.keys())),
        "種別": st.column_config.SelectboxColumn(
            options=["配布", "挟み込み", "交通費", "手当", "その他"]),
        "単価": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%g"),
        "数量": st.column_config.NumberColumn(_qty_label, min_value=0.0, step=0.5,
                                             format="%g"),
        "その他の案件名": st.column_config.TextColumn(help="案件を『その他』にしたとき、何の案件か"),
    }
    if pay_type == "日当":
        _base = {"案件": "", "種別": "配布", "業務": "", "単価": 0.0, "数量": 0.0,
                 "部数": 0, "その他の案件名": ""}
        _cols = ["案件", "種別", "業務", "単価", "数量", "部数", "その他の案件名"]
        _conf["業務"] = st.column_config.SelectboxColumn(
            options=list(_rates.keys()),
            help="マスタに登録した業務名。選ぶと単価に日当額が入ります。")
    if _needs_copies and "部数" not in _cols:
        _cols.insert(_cols.index("数量") + 1, "部数")
        _base["部数"] = 0
    if _needs_copies:
        _conf["部数"] = st.column_config.NumberColumn(
            "部数", min_value=0, step=1, format="localized",
            help="報告書の報告数に使います。報酬の計算には使いません。")

    st.markdown(f"**明細**（案件・種別・単価・{_qty_label}）｜数量と単価は小数点も入力できます")
    st.caption("案件を「その他」にした行は、右の『その他の案件名』に何の案件か入力してください"
               "（号別明細の『その他』で確認できます）。")
    editor = st.data_editor(
        pd.DataFrame([_base]), num_rows="dynamic", column_config=_conf,
        column_order=_cols, use_container_width=True, key=f"line_editor_{pay_type}")
```

**(d)** `lines` の組み立てを差し替え（業務名から単価を補完・部数を拾う）:

```python
    lines = []
    for _, row in editor.iterrows():
        if not row["案件"] or pd.isna(row["案件"]):
            continue
        qty = posting_logic._num(row["数量"]) if pd.notna(row["数量"]) else 0
        price = posting_logic._num(row["単価"]) if pd.notna(row["単価"]) else 0
        # 日当: 業務を選んで単価が空(0)なら、マスタの日当額を入れる。
        # 単価が手で入っていればそちらを優先する(その回だけ違う金額にできる)。
        if pay_type == "日当" and not price:
            work = row.get("業務") if "業務" in row else None
            if pd.notna(work):
                price = _rates.get(str(work), 0)
        remark = row["種別"] if pd.notna(row["種別"]) else "配布"
        olabel = row.get("その他の案件名") if "その他の案件名" in row else None
        olabel = (str(olabel).strip() or None) if (pd.notna(olabel) and row["案件"] == "その他") else None
        copies = None
        if _needs_copies and "部数" in row and pd.notna(row["部数"]):
            copies = int(row["部数"] or 0)
        lines.append({"project_id": projs.get(row["案件"]), "project_name": row["案件"],
                      "report_qty": qty, "unit_price": price, "amount": qty * price,
                      "remark": remark, "other_label": olabel, "copies": copies})
```

**(e)** プレビューとメトリクスを支払形態に対応させる:

```python
        preview = [{
            "案件": l["project_name"],
            "種別": l["remark"],
            "数量": posting_logic.qty_label(l["report_qty"], l["remark"], pay_type),
            "単価": f'¥{posting_logic.fmt_num(l["unit_price"])}',
            "合計": f'¥{posting_logic.fmt_num(l["amount"])}',
        } for l in lines]
        nice_table(preview)

        m1, m2 = st.columns(2)
        m1.metric("ご請求金額(税込)", f"¥{posting_logic.fmt_num(posting_logic.invoice_total(lines))}")
        m2.metric("配布部数(配布+挟み込み)",
                  f"{posting_logic.fmt_num(posting_logic.delivered_copies(lines, pay_type))} 部")
```

**(f)** 登録時に `pay_type` と `copies` を渡す:

```python
    if col_save.button("この請求を登録", type="primary", disabled=not lines):
        store.add_contract_invoice(
            dists[dist_name], str(issue), str(pfrom), str(pto),
            [{"project_id": l["project_id"], "report_qty": l["report_qty"],
              "unit_price": l["unit_price"], "remark": l["remark"],
              "other_label": l.get("other_label"), "copies": l.get("copies")} for l in lines],
            pay_type=pay_type)
        st.session_state.pop(f"line_editor_{pay_type}", None)
        flash("登録しました")
        st.rerun()
```

**(g)** 一覧タブ：`_invoice_out_lines` に `copies` を通し、削除ボタンを足す:

```python
def _invoice_out_lines(detail, id2proj):
    """保存済み請求の明細を報告書生成用の行に整える。"""
    return [{"project_name": id2proj.get(l.get("project_id"), ""),
             "report_qty": l.get("report_qty"), "unit_price": l.get("unit_price"),
             "amount": l.get("amount"), "remark": l.get("remark"),
             "copies": l.get("copies")}
            for l in detail["lines"]]
```

一覧タブの先頭に `show_flash()` を足し、末尾（配布員別 報酬合計の前）に追記:

```python
    st.markdown("**請求を削除**")
    for inv in invoices:
        total = posting_logic.invoice_total(detail_by_id[inv["id"]]["lines"])
        name = id2name.get(inv["distributor_id"], "?")
        detail_txt = f'No.{inv["id"]} ／ {name} ／ {inv.get("issue_date")} ／ ¥{posting_logic.fmt_num(total)}'
        c1, c2 = st.columns([5, 1])
        c1.caption(detail_txt)
        with c2:
            confirm_delete(key=f"del_inv_{inv['id']}", detail=detail_txt,
                           on_confirm=lambda i=inv["id"]: store.delete_contract_invoice(i))
```

`st.warning("先に『マスタ管理』で配布委託先(配布員)を登録してください。")` の文言を
`"先に『マスタ管理』の「業務委託」タブで配布員を登録してください。"` に直す。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add pages/02_業務委託登録.py tests/test_pages_smoke.py
git commit -m "feat: 業務委託登録に支払形態別の明細と報酬の自動計算を追加"
```

---

### Task 13: 報告書兼請求書 — 支払形態に応じた数量と報告数

**Files:**
- Modify: `common/invoice_excel.py`、`pages/02_業務委託登録.py`（呼び出し2箇所）
- Test: `tests/test_invoice_excel.py`

**Interfaces:**
- Produces: `build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines, pay_type=None) -> bytes`

現物（`common/invoice_excel.py:25-52`）の作りはこうなっている:

- `D{r}`（数量）= 配布・挟み込みなら **数値**、それ以外は `unit_for(remark)` の文字列（＝「一式」）
- `G{r}`（備考）= 種別（配布／挟み込み／…）
- `F20`（報告数）= `delivered_copies(lines)` に「部」を付けたもの

日当・時給では `D` に入る数値が日数・時間になるが、**Excel上は数字だけで単位が見えない**。
そこで備考（G列）に単位を併記して、配布員が「3」が何の3なのか分かるようにする。

- [ ] **Step 1: Write the failing test**

`tests/test_invoice_excel.py` に追記（既存テストの読み出し方に合わせること。
既存テストが `openpyxl.load_workbook(io.BytesIO(xlsx))` でセルを見ているならそれに倣う）:

```python
def test_invoice_xlsx_nichito_puts_days_in_remark(tmp_path):
    """日当の請求書は備考に「配布（3 日）」と単位が出る。数量セルは日数の数値。"""
    xlsx = invoice_excel.build_invoice_xlsx(
        distributor_name="山田太郎", issue_date="2026-07-17",
        period_from="2026-07-01", period_to="2026-07-15",
        lines=[{"project_name": "案件A", "report_qty": 3, "unit_price": 8000,
                "amount": 24000, "remark": "配布", "copies": 3713}],
        pay_type="日当")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    ws = wb.active
    assert ws["D13"].value == 3
    assert ws["G13"].value == "配布（3 日）"
    # 報告数は copies 列から取る(数量の3ではない)
    assert ws["F20"].value == "3,713部"


def test_invoice_xlsx_getkyu_shows_isshiki(tmp_path):
    """月給は数量を数えないので数量セルが「一式」。"""
    xlsx = invoice_excel.build_invoice_xlsx(
        distributor_name="月給の人", issue_date="2026-07-17",
        period_from="2026-07-01", period_to="2026-07-31",
        lines=[{"project_name": "案件A", "report_qty": 1, "unit_price": 250000,
                "amount": 250000, "remark": "配布", "copies": 5000}],
        pay_type="月給")
    ws = openpyxl.load_workbook(io.BytesIO(xlsx)).active
    assert ws["D13"].value == "一式"
    assert ws["F20"].value == "5,000部"


def test_invoice_xlsx_without_pay_type_keeps_current_behavior(tmp_path):
    """pay_type を渡さない既存の呼び出しは1ミリも変わらない(後方互換)。"""
    xlsx = invoice_excel.build_invoice_xlsx(
        distributor_name="山田太郎", issue_date="2026-07-17",
        period_from="2026-07-01", period_to="2026-07-15",
        lines=[{"project_name": "案件A", "report_qty": 3713, "unit_price": 2.5,
                "amount": 9283, "remark": "配布"},
               {"project_name": "案件A", "report_qty": 1, "unit_price": 540,
                "amount": 540, "remark": "交通費"}])
    ws = openpyxl.load_workbook(io.BytesIO(xlsx)).active
    assert ws["D13"].value == 3713          # 配布は数値のまま
    assert ws["G13"].value == "配布"         # 備考に単位は付けない
    assert ws["D14"].value == "一式"         # 交通費は今まで通り
    assert ws["F20"].value == "3,713部"
```

テストファイルの先頭に `import io` と `import openpyxl` が無ければ足すこと。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_invoice_excel.py -v`
Expected: FAIL（`build_invoice_xlsx() got an unexpected keyword argument 'pay_type'`）

- [ ] **Step 3: Write minimal implementation**

`common/invoice_excel.py` の `build_invoice_xlsx` を差し替え（**変更するのは3箇所だけ**）:

```python
def build_invoice_xlsx(*, distributor_name, issue_date, period_from, period_to, lines,
                       pay_type=None) -> bytes:
```

明細のループを差し替え:

```python
    for i, ln in enumerate(lines[:_MAX_LINE_ROWS]):
        r = _FIRST_LINE_ROW + i
        _set(ws, f"B{r}", ln.get("project_name"))
        # 数量: 数を数える種別は数値。数えないもの(交通費・手当・その他、月給の行)は『一式』と書く。
        unit = posting_logic.unit_for(ln.get("remark"), pay_type)
        _set(ws, f"D{r}", "一式" if unit == "一式"
             else posting_logic._num(ln.get("report_qty")))
        _set(ws, f"E{r}", posting_logic._num(ln.get("unit_price")))
        _set(ws, f"F{r}", posting_logic._num(ln.get("amount")))
        # 備考(G列)には種別を入れる。歩合以外は数量セルの数字が部数でない(日数・時間)ため、
        # 何の数なのかが分かるよう単位を併記する。例: 配布（3 日）
        remark = ln.get("remark")
        if unit not in ("一式", "枚"):
            remark = f"{remark}（{posting_logic.qty_label(ln.get('report_qty'), remark, pay_type)}）"
        _set(ws, f"G{r}", remark)
```

報告数を差し替え:

```python
    _set(ws, "F20", f"{posting_logic.fmt_num(posting_logic.delivered_copies(lines, pay_type))}部")
```

⚠️ `unit not in ("一式", "枚")` で判定する。`pay_type` を見て分岐すると、
**歩合でも交通費の行に単位が付く**などのズレが出る。単位が答えなので単位で分ける。

- [ ] **Step 4: 呼び出し側に pay_type を渡す**

`pages/02_業務委託登録.py` の `build_invoice_xlsx` の呼び出し2箇所:

- 登録タブのダウンロード（`col_dl.download_button` の直前）→ `pay_type=pay_type` を足す
- 一覧タブのZIP出力（`zf.writestr` の直前）→ `pay_type=head.get("pay_type")` を足す

⚠️ 一覧タブは**マスタの現在値ではなく、請求に保存した `head["pay_type"]` を使う**こと。
マスタの現在値を使うと、支払形態を変えた瞬間に過去の報告書の単位が化ける。

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 6: Commit**

```bash
git add common/invoice_excel.py pages/02_業務委託登録.py tests/test_invoice_excel.py
git commit -m "feat: 報告書兼請求書を支払形態に応じた数量・報告数で出す"
```

---

### Task 14: 号別明細 — 業務委託と雑費の内訳に配布員名

**Files:**
- Modify: `pages/03_号別明細.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: Task 5 の `pay_type`、Task 8 の `qty_label`

- [ ] **Step 1: Write the failing test**

```python
def test_issue_page_renders(db):
    at = _run("03_号別明細.py")
    assert not at.exception


def test_issue_page_shows_distributor_in_contract_breakdown(db):
    did, pid, iid = _seed_invoice(db, pay_type="歩合")
    at = _run("03_号別明細.py")
    assert "山田太郎" in str(at)


def test_issue_page_shows_distributor_for_petty(db):
    did = store.add_distributor("佐藤花子", db_path=db)
    pid = store.add_project("案件A", db_path=db)
    store.add_petty_cash("2026-07-17", None, 1500, project_id=pid,
                         distributor_id=did, db_path=db)
    at = _run("03_号別明細.py")
    assert "佐藤花子" in str(at)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -k issue_page -v`
Expected: FAIL（配布員名が出ていない）

- [ ] **Step 3: Write minimal implementation**

**(a)** `contract_lines` を集めるループで、請求ヘッダの配布員名と支払形態を各行に持たせる:

```python
_dist_names = {d["id"]: d["name"] for d in store.list_distributors()}  # 停止中も含めて引く

contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    for ln in detail["lines"]:
        ln = dict(ln)
        ln["issue_date"] = inv.get("issue_date")   # その他の案件内訳で発行日を出すため
        ln["distributor_name"] = _dist_names.get(inv.get("distributor_id"), "")
        ln["pay_type"] = inv.get("pay_type")       # 登録時点の支払形態(マスタの現在値は使わない)
        contract_lines.append(ln)
```

**(b)** `_con_disp` を差し替え（種別の左に配布員）:

```python
_con_disp = [_with_label({"配布員": l.get("distributor_name") or "",
                          "種別": l.get("remark") or "",
                          "数量": posting_logic.qty_label(l.get("report_qty"), l.get("remark"),
                                                        l.get("pay_type")),
                          "単価": _yen(l.get("unit_price")), "合計": _yen(l.get("amount"))},
                         l.get("other_label"))
             for l in issue_contract]
```

**(c)** 雑費の `_misc` を差し替え（左端に配布員・買掛は空欄）:

```python
for r in petty:
    item = _cats.get(r.get("category_id"), "")
    if r.get("memo"):
        item = f'{item}（{r["memo"]}）' if item else r["memo"]
    _misc.append(_with_label(
        {"配布員": _dist_names.get(r.get("distributor_id"), ""),
         "項目": item or "小口", "金額": _yen(r.get("amount")),
         "支払方法": posting_logic.payment_method("petty", r),
         "日付": r.get("date") or ""}, r.get("other_label")))
for r in payables:
    item = r.get("vendor_name") or _vends.get(r.get("vendor_id"), "")
    # 買掛は配布員を持たない(オーナー判断で小口のみ)ため、この列は空欄になる。
    _misc.append(_with_label(
        {"配布員": "", "項目": item or "買掛", "金額": _yen(r.get("amount")),
         "支払方法": posting_logic.payment_method("payable", r),
         "日付": r.get("date") or r.get("month") or ""}, r.get("other_label")))
```

**(d)** 号原価まとめExcelの空のときの列名を新しい構成に合わせる:

```python
    (pd.DataFrame(_con_disp) if _con_disp
     else pd.DataFrame(columns=["配布員", "種別", "数量", "単価", "合計"])).to_excel(
        writer, index=False, sheet_name="業務委託")
    ...
    (pd.DataFrame(_misc) if _misc
     else pd.DataFrame(columns=["配布員", "項目", "金額", "支払方法", "日付"])).to_excel(
        writer, index=False, sheet_name="雑費")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add pages/03_号別明細.py tests/test_pages_smoke.py
git commit -m "feat: 号別明細の業務委託・雑費の内訳に配布員名を表示"
```

---

### Task 15: 実データのコピーで最終検証

**Files:**
- 変更なし（検証のみ）

- [ ] **Step 1: 全テストを走らせる**

Run: `cd C:\Users\moro\posting-automation && python -m pytest tests/ -v`
Expected: **すべて PASS**（既存73件＋今回の追加分）

- [ ] **Step 2: 実データDBをコピーして検証用に隔離する**

```bash
mkdir -p /c/Users/moro/AppData/Local/Temp/claude/scratch-posting
cp /c/Users/moro/posting-automation/data/posting.db /c/Users/moro/AppData/Local/Temp/claude/scratch-posting/verify.db
```

- [ ] **Step 3: 検証用DBでマイグレーションが通ることを確認する**

```bash
cd /c/Users/moro/posting-automation
POSTING_DB_PATH=/c/Users/moro/AppData/Local/Temp/claude/scratch-posting/verify.db python -c "
from common import posting_store as store
store.init_db()
print('migrated ok')
invs = store.list_contract_invoices()
print('invoices:', len(invs))
for i in invs[:3]:
    print(' pay_type:', i.get('pay_type'))
"
```

Expected: `migrated ok` が出て、既存の請求の `pay_type` が **すべて None**（＝歩合扱い＝現行動作のまま）

- [ ] **Step 4: 既存データの表示が変わっていないことを確認する**

```bash
POSTING_DB_PATH=/c/Users/moro/AppData/Local/Temp/claude/scratch-posting/verify.db python -c "
from common import posting_store as store, posting_logic as L
for inv in store.list_contract_invoices()[:5]:
    d = store.get_contract_invoice(inv['id'])
    pt = d['invoice'].get('pay_type')
    for ln in d['lines']:
        print(inv['id'], ln.get('remark'), '->', L.qty_label(ln.get('report_qty'), ln.get('remark'), pt))
    print('  部数:', L.delivered_copies(d['lines'], pt))
"
```

Expected: 配布・挟み込みの行が **今まで通り「N 枚」**で出て、部数も今まで通りの数字であること

- [ ] **Step 5: 検証用DBを片付け、実データDBが無傷なことを確認する**

```bash
rm -rf /c/Users/moro/AppData/Local/Temp/claude/scratch-posting
cd /c/Users/moro/posting-automation && git status --short
```

Expected: 検証用DBが消えていること。`data/posting.db` が変更されていない（`git status` に出ない、もしくは元から追跡外）こと

- [ ] **Step 6: 8502 を再起動してオーナーに実機確認を依頼する**

⚠️ `common/*.py` を変えているので**必ず手動再起動**する（起動batは health=ok なら既存サーバーを開くだけ）。

```powershell
Get-NetTCPConnection -LocalPort 8502 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
cd C:\Users\moro\posting-automation
streamlit run app.py --server.port 8502 --server.headless true
```

オーナーに見てもらう点:
1. マスタ管理のタブが「業務委託」になっているか。停止中の折りたたみが出るか
2. 業務委託マスタに振込先・支払形態・時給額・月額が入るか。日当の人に日当金額を設定できるか
3. 業務委託登録で、日当の人を選ぶと明細が「業務／単価／数量(日)／部数」になり、業務を選ぶと単価が入るか
4. 号別明細の業務委託・雑費の内訳に配布員名が出るか
5. 各一覧の削除ボタンが確認を挟み、「削除しました」が出るか
6. **既存の請求（歩合）の表示が今までと変わっていないか**

- [ ] **Step 7: Commit（もし修正が出たら）**

```bash
git add -A
git commit -m "fix: 実機確認で出た点の修正"
```

---

## 完了の定義

- 全タスクのテストが通る（`python -m pytest tests/ -v` が全 PASS）
- 実データのコピーでマイグレーションが通り、**既存の請求の表示が1つも変わらない**
- オーナーが 8502 の実機で6点を確認して承認
- master へのマージは**オーナーの承認後**（第2弾と同じ `git merge --no-ff` で）
