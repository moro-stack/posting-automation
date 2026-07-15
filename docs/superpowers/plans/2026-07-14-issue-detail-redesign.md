# 号別明細ページ改修 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 号別明細ページを「配布員代（業務委託＋日ごと直接入力）／雑費（小口＋買掛）／配布原価」の管理表レイアウトに改修する。

**Architecture:** 既存 `issue_manual_costs` に `work_date` を足して「配布員代の直接入力（日ごと・作業別）」に格上げ（追加・修正・削除可）。業務委託は既存のまま配布員代へ集計。雑費は小口＋買掛を自動集計し支払方法を判定。総額（配布原価）は現行のコスト合計と不変で、グループの見せ方だけを変える。

**Tech Stack:** Python 3.11 / Streamlit / SQLite（`common/posting_store.py`）/ pandas・openpyxl。テストは pytest（`tests/`）。

## Global Constraints

- 対象ブランチ: `feature/mvp`（現行の作業ブランチ）。
- DB 移行は既存慣例に従う: `_ensure_schema` 内で `ALTER TABLE ... ADD COLUMN`（`payables.date` と同型）。旧DB後方互換必須。
- store の追加/更新/削除は既存ヘルパ `_add` / `_update`（`_UNSET` センチネル）/ `_delete` を使う。
- 金額は整数円。表示は `posting_logic.fmt_num` / `¥` 付き。
- 共通モジュール変更は streamlit 再起動で反映（`--server.port 8502 --server.headless true`）。
- Python 実行パス: `C:\Users\moro\AppData\Local\Programs\Python\Python311\python.exe`（テストは `python -m pytest`）。

---

### Task 1: `issue_manual_costs` に work_date（配布員代の直接入力）＋ 追加/一覧/修正/削除

**Files:**
- Modify: `common/posting_store.py`（`_ensure_schema` の移行ブロック、`add_issue_manual_cost`、`list_issue_manual_costs`、新規 `update_issue_manual_cost` / `delete_issue_manual_cost`）
- Test: `tests/test_posting_store.py`

**Interfaces:**
- Consumes: 既存 `_add`, `_update`, `_delete`, `_UNSET`, `_int_or_none`, `_now`, `_connect`。
- Produces:
  - `add_issue_manual_cost(project_id, content, amount, *, work_date=None, db_path=None, now=None) -> int`
  - `list_issue_manual_costs(*, project_id=None, db_path=None) -> list[dict]`（各 dict に `work_date` を含む。work_date 昇順・None 末尾・同順は id 昇順）
  - `update_issue_manual_cost(row_id, *, work_date=_UNSET, content=_UNSET, amount=_UNSET, db_path=None) -> None`
  - `delete_issue_manual_cost(row_id, *, db_path=None) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_posting_store.py` の末尾に追記:

```python
def test_issue_manual_cost_work_date_add_and_ordering(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("6/26号", db_path=db)
    a = store.add_issue_manual_cost(pid, "配布", 104700, work_date="2026-06-22", db_path=db)
    b = store.add_issue_manual_cost(pid, "挟みこみ", 32250, work_date="2026-06-23", db_path=db)
    c = store.add_issue_manual_cost(pid, "日付なし", 8000, db_path=db)
    rows = store.list_issue_manual_costs(project_id=pid, db_path=db)
    assert [r["id"] for r in rows] == [a, b, c]           # 日付あり昇順→None末尾
    assert rows[0]["work_date"] == "2026-06-22"
    assert rows[2]["work_date"] is None


def test_issue_manual_cost_update_and_delete(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    pid = store.add_project("号", db_path=db)
    rid = store.add_issue_manual_cost(pid, "配布", 100, work_date="2026-06-01", db_path=db)
    store.update_issue_manual_cost(rid, work_date="2026-06-22", content="丁合・配布",
                                   amount=136950, db_path=db)
    row = [r for r in store.list_issue_manual_costs(project_id=pid, db_path=db) if r["id"] == rid][0]
    assert row["work_date"] == "2026-06-22" and row["content"] == "丁合・配布" and row["amount"] == 136950
    store.delete_issue_manual_cost(rid, db_path=db)
    assert all(r["id"] != rid for r in store.list_issue_manual_costs(project_id=pid, db_path=db))


def test_issue_manual_cost_migrates_old_db(tmp_path):
    import sqlite3
    db = os.path.join(tmp_path, "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE issue_manual_costs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " project_id INTEGER, content TEXT, amount INTEGER NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO issue_manual_costs (project_id, content, amount, created_at)"
                 " VALUES (1, '旧行', 5000, '2026-06-01T00:00:00')")
    conn.commit()
    conn.close()
    rows = store.list_issue_manual_costs(project_id=1, db_path=db)  # 接続時に自動ALTER
    assert rows and rows[0]["content"] == "旧行" and rows[0]["work_date"] is None
```

- [ ] **Step 2: 失敗確認**

Run: `python -m pytest tests/test_posting_store.py -k issue_manual_cost -v`
Expected: FAIL（`add_issue_manual_cost() got an unexpected keyword argument 'work_date'` 等）

- [ ] **Step 3: 実装**

`common/posting_store.py`、`_ensure_schema` の `conn.commit()`（payables 移行の直後）の**前**に追記:

```python
    # 号別明細の手入力コストに配布作業日を持たせる。旧DBは自動でカラム追加。
    imc_cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_manual_costs)")}
    if "work_date" not in imc_cols:
        conn.execute("ALTER TABLE issue_manual_costs ADD COLUMN work_date TEXT")
```

`add_issue_manual_cost` を差し替え:

```python
def add_issue_manual_cost(project_id, content, amount, *, work_date=None, db_path=None, now=None):
    return _add("issue_manual_costs",
                ["project_id", "content", "amount", "work_date", "created_at"],
                [_int_or_none(project_id), content, int(amount), work_date or None, _now(now)],
                db_path)
```

`list_issue_manual_costs` を差し替え（並びを work_date 昇順・None 末尾に）:

```python
def list_issue_manual_costs(*, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        order = "ORDER BY work_date IS NULL, work_date, id"
        if project_id is None:
            rows = conn.execute(f"SELECT * FROM issue_manual_costs {order}").fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM issue_manual_costs WHERE project_id=? {order}",
                (int(project_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

`list_issue_manual_costs` の直後に追記:

```python
def update_issue_manual_cost(row_id, *, work_date=_UNSET, content=_UNSET, amount=_UNSET, db_path=None):
    fields = {"work_date": work_date, "content": content,
              "amount": (int(amount) if amount is not _UNSET else _UNSET)}
    _update("issue_manual_costs", row_id, fields, db_path)


def delete_issue_manual_cost(row_id, *, db_path=None):
    _delete("issue_manual_costs", row_id, db_path)
```

- [ ] **Step 4: テスト成功確認**

Run: `python -m pytest tests/test_posting_store.py -k issue_manual_cost -v`
Expected: PASS（3件）

- [ ] **Step 5: 全テスト回帰**

Run: `python -m pytest -q`
Expected: PASS（既存も全て緑）

- [ ] **Step 6: コミット**

```bash
git add common/posting_store.py tests/test_posting_store.py
git commit -m "feat(store): issue_manual_costsにwork_date追加+更新/削除(配布員代の直接入力)"
```

---

### Task 2: 雑費の支払方法判定 `payment_method`（純粋関数）

**Files:**
- Modify: `common/posting_logic.py`（関数追加）
- Test: `tests/test_posting_logic.py`

**Interfaces:**
- Produces: `payment_method(kind: str, row: dict) -> str`（`kind` は `"petty"` か `"payable"`）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_posting_logic.py` 末尾に追記:

```python
def test_payment_method_petty_is_cash():
    assert L.payment_method("petty", {}) == "現金"


def test_payment_method_payable_from_original_status():
    assert L.payment_method("payable", {"original_status": "クレジット"}) == "クレジット"
    assert L.payment_method("payable", {"original_status": "振込用紙"}) == "振込"
    assert L.payment_method("payable", {"original_status": "原本あり"}) == "買掛"
    assert L.payment_method("payable", {}) == "買掛"
```

- [ ] **Step 2: 失敗確認**

Run: `python -m pytest tests/test_posting_logic.py -k payment_method -v`
Expected: FAIL（`module 'common.posting_logic' has no attribute 'payment_method'`）

- [ ] **Step 3: 実装**

`common/posting_logic.py` の `issue_balance` の後に追記:

```python
def payment_method(kind, row) -> str:
    """雑費の支払方法ラベル。kind: 'petty'(小口=現金) / 'payable'(買掛=原本区分から判定)。"""
    if kind == "petty":
        return "現金"
    status = str((row or {}).get("original_status") or "")
    if "クレジット" in status:
        return "クレジット"
    if "振込" in status:
        return "振込"
    return "買掛"
```

- [ ] **Step 4: テスト成功確認**

Run: `python -m pytest tests/test_posting_logic.py -k payment_method -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add common/posting_logic.py tests/test_posting_logic.py
git commit -m "feat(logic): 雑費の支払方法判定 payment_method を追加"
```

---

### Task 3: 新レイアウトのグループ集計 `cost_groups`（純粋関数）

**Files:**
- Modify: `common/posting_logic.py`（関数追加）
- Test: `tests/test_posting_logic.py`

**Interfaces:**
- Consumes: `aggregate_issue(...)` の戻り dict（`petty/payables/contract/manual/total`）
- Produces: `cost_groups(agg: dict) -> dict`（`{"labor", "misc", "genka"}`）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_posting_logic.py` 末尾に追記:

```python
def test_cost_groups_regroups_totals():
    agg = {"petty": 1200, "payables": 183342, "contract": 11679, "manual": 8000,
           "total": 1200 + 183342 + 11679 + 8000}
    g = L.cost_groups(agg)
    assert g["labor"] == 11679 + 8000       # 配布員代=業務委託+直接入力
    assert g["misc"] == 1200 + 183342        # 雑費=小口+買掛
    assert g["genka"] == agg["total"]        # 配布原価=総額(不変)
```

- [ ] **Step 2: 失敗確認**

Run: `python -m pytest tests/test_posting_logic.py -k cost_groups -v`
Expected: FAIL（`has no attribute 'cost_groups'`）

- [ ] **Step 3: 実装**

`common/posting_logic.py` の `payment_method` の後に追記:

```python
def cost_groups(agg) -> dict:
    """aggregate_issue の結果を新レイアウトへ再編。
    配布員代=業務委託+直接入力(manual)、雑費=小口+買掛、配布原価=両者の和(=total)。"""
    labor = _num(agg.get("contract")) + _num(agg.get("manual"))
    misc = _num(agg.get("petty")) + _num(agg.get("payables"))
    return {"labor": labor, "misc": misc, "genka": labor + misc}
```

- [ ] **Step 4: テスト成功確認**

Run: `python -m pytest tests/test_posting_logic.py -k cost_groups -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add common/posting_logic.py tests/test_posting_logic.py
git commit -m "feat(logic): 号原価のグループ集計 cost_groups を追加"
```

---

### Task 4: 号別明細ページを新レイアウトに改修（UI）

**Files:**
- Modify（全面置換）: `pages/03_号別明細.py`

**Interfaces:**
- Consumes: Task1/2/3 の store・logic 関数、既存 `aggregate_issue`, `issue_balance`, `period_range`, `filter_rows_by_period`, `in_period`, `unit_for`, `fmt_num`, `_num`、`nice_table`, `section_export`。

- [ ] **Step 1: ページを全面置換**

`pages/03_号別明細.py` を次の内容で置き換える:

```python
from datetime import date as _date, datetime as _datetime
import io

import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.ui import apply_app_style, section_export, nice_table

apply_app_style()
st.title("号別の明細・収支")

_WD = ["月", "火", "水", "木", "金", "土", "日"]


def _yen(v):
    return f"¥{posting_logic.fmt_num(v)}"


def _weekday(ds):
    try:
        return _WD[_datetime.strptime(str(ds)[:10], "%Y-%m-%d").weekday()]
    except (ValueError, TypeError):
        return ""


projs = store.list_projects(only_active=True)
if not projs:
    st.warning("案件マスタが空です。『マスタ管理』で登録してください。")
    st.stop()

name2id = {p["name"]: p["id"] for p in projs}
names = list(name2id.keys())
st.markdown("**案件(号)**")
sel = st.pills("案件(号)", names, selection_mode="single",
               default=names[0], label_visibility="collapsed", key="proj_pills")
if not sel:
    sel = names[0]
pid = name2id[sel]

st.markdown("**期間指定**")
_PRESETS = {"全期間": "all", "今年": "year", "今月": "month", "今週": "week"}
period_label = st.pills("期間指定", list(_PRESETS.keys()) + ["期間を指定"],
                        selection_mode="single", default="全期間",
                        label_visibility="collapsed", key="period_pills")
if not period_label:
    period_label = "全期間"
if period_label == "期間を指定":
    c1, c2 = st.columns(2)
    d_from = c1.date_input("開始日", value=_date.today().replace(day=1))
    d_to = c2.date_input("終了日", value=_date.today())
    lo, hi = str(d_from), str(d_to)
else:
    lo, hi = posting_logic.period_range(_PRESETS[period_label])
period_note = "全期間" if (lo is None and hi is None) else f"{lo} 〜 {hi}"
st.caption(f"表示期間: {period_note}")

# --- コストを集める ---
petty = posting_logic.filter_rows_by_period(
    store.list_petty_cash(project_id=pid), "date", lo, hi)
payables = posting_logic.filter_rows_by_period(
    store.list_payables(project_id=pid), "month", lo, hi)
receivables = posting_logic.filter_rows_by_period(
    store.list_receivables(project_id=pid), "month", lo, hi)

contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    contract_lines.extend(detail["lines"])

# 直接入力(配布員代): work_date で期間絞り込み。日付なしは常に計上。
all_manual = store.list_issue_manual_costs(project_id=pid)
manual = [r for r in all_manual
          if r.get("work_date") is None or posting_logic.in_period(r.get("work_date"), lo, hi)]

agg = posting_logic.aggregate_issue(
    pid, petty=petty, payables=payables, contract_lines=contract_lines, manual=manual)
groups = posting_logic.cost_groups(agg)

# --- 上部サマリー ---
mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("配布原価(税込)", _yen(groups["genka"]))
mcol2.metric("配布員代", _yen(groups["labor"]))
mcol3.metric("雑費", _yen(groups["misc"]))

receivable_total = sum(posting_logic._num(r["amount"]) for r in receivables)
if receivable_total:
    bal = posting_logic.issue_balance(groups["genka"], receivable_total)
    st.metric("収支(売上−配布原価)", _yen(bal), delta=f"売上 {_yen(receivable_total)}")

st.divider()

# ===== 配布員代 =====
st.subheader("配布員代")

st.markdown("**業務委託（配布員別・報告書/請求書ページで計算）**")
issue_contract = [l for l in contract_lines if l.get("project_id") == pid]
_con_disp = [{"種別": l.get("remark") or "",
              "数量": f'{posting_logic.fmt_num(l.get("report_qty"))} {posting_logic.unit_for(l.get("remark"))}',
              "単価": _yen(l.get("unit_price")), "合計": _yen(l.get("amount"))}
             for l in issue_contract]
nice_table(_con_disp, "この号の業務委託はありません。")

st.markdown("**直接入力（日ごと・作業別）**")
_man_disp = [{"日付": r.get("work_date") or "（日付なし）",
              "曜日": _weekday(r.get("work_date")),
              "作業": r.get("content") or "",
              "金額": _yen(r.get("amount"))} for r in manual]
nice_table(_man_disp, "直接入力の配布員代はありません。")

with st.form("add_labor", clear_on_submit=True):
    st.caption("配布員代を直接追加（日給の人・後からの追加もここで）")
    a1, a2, a3 = st.columns([1, 2, 1])
    w = a1.date_input("日付", value=_date.today())
    work = a2.text_input("作業", placeholder="例：配布 / 丁合・配布")
    amt = a3.number_input("金額", min_value=0, step=1)
    if st.form_submit_button("追加") and amt > 0:
        store.add_issue_manual_cost(pid, work.strip() or "配布", int(amt), work_date=str(w))
        st.rerun()

if manual:
    st.caption("入力済みの直接入力を修正・削除")
    opt = {f'{(r.get("work_date") or "日付なし")}｜{r.get("content") or ""}｜{_yen(r.get("amount"))}': r
           for r in manual}
    pick = st.selectbox("対象の行", list(opt.keys()), key="edit_pick")
    target = opt[pick]
    with st.form("edit_labor"):
        e1, e2, e3 = st.columns([1, 2, 1])
        cur_date = (_datetime.strptime(target["work_date"][:10], "%Y-%m-%d").date()
                    if target.get("work_date") else _date.today())
        ew = e1.date_input("日付", value=cur_date, key="edit_date")
        ework = e2.text_input("作業", value=target.get("content") or "", key="edit_work")
        eamt = e3.number_input("金額", min_value=0, step=1,
                               value=int(target.get("amount") or 0), key="edit_amt")
        u1, u2, _ = st.columns([1, 1, 4])
        if u1.form_submit_button("更新") and eamt > 0:
            store.update_issue_manual_cost(target["id"], work_date=str(ew),
                                           content=ework.strip() or "配布", amount=int(eamt))
            st.rerun()
        if u2.form_submit_button("削除"):
            store.delete_issue_manual_cost(target["id"])
            st.rerun()

st.metric("配布員代 小計", _yen(groups["labor"]))
section_export(_man_disp, f"配布員代直接入力_{sel}", key="issue_labor")

st.divider()

# ===== 雑費 =====
st.subheader("雑費（小口・買掛から自動集計）")
_cats = {c["id"]: c["name"] for c in store.list_expense_categories()}
_vends = {v["id"]: v["name"] for v in store.list_payables_vendors()}
_misc = []
for r in petty:
    item = _cats.get(r.get("category_id"), "")
    if r.get("memo"):
        item = f'{item}（{r["memo"]}）' if item else r["memo"]
    _misc.append({"項目": item or "小口", "金額": _yen(r.get("amount")),
                  "支払方法": posting_logic.payment_method("petty", r),
                  "日付": r.get("date") or ""})
for r in payables:
    item = r.get("vendor_name") or _vends.get(r.get("vendor_id"), "")
    _misc.append({"項目": item or "買掛", "金額": _yen(r.get("amount")),
                  "支払方法": posting_logic.payment_method("payable", r),
                  "日付": r.get("date") or r.get("month") or ""})
nice_table(_misc, "この号の雑費（小口・買掛）はありません。")
st.metric("雑費 小計", _yen(groups["misc"]))
section_export(_misc, f"雑費_{sel}", key="issue_misc")

st.divider()

# ===== 号原価まとめ 出力 =====
st.subheader("号原価まとめの出力")
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    (pd.DataFrame(_con_disp) if _con_disp
     else pd.DataFrame(columns=["種別", "数量", "単価", "合計"])).to_excel(
        writer, index=False, sheet_name="業務委託")
    (pd.DataFrame(_man_disp) if _man_disp
     else pd.DataFrame(columns=["日付", "曜日", "作業", "金額"])).to_excel(
        writer, index=False, sheet_name="直接入力")
    (pd.DataFrame(_misc) if _misc
     else pd.DataFrame(columns=["項目", "金額", "支払方法", "日付"])).to_excel(
        writer, index=False, sheet_name="雑費")
    pd.DataFrame([{"項目": "配布員代", "金額": groups["labor"]},
                  {"項目": "雑費", "金額": groups["misc"]},
                  {"項目": "配布原価(税込)", "金額": groups["genka"]}]).to_excel(
        writer, index=False, sheet_name="合計")
st.download_button("⬇️ 号原価まとめをExcelで保存", data=buf.getvalue(),
                   file_name=f"号原価まとめ_{sel}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   key="dl_genka")
```

- [ ] **Step 2: 構文チェック**

Run: `python -m py_compile pages/03_号別明細.py`
Expected: エラーなし

- [ ] **Step 3: 全テスト回帰**

Run: `python -m pytest -q`
Expected: PASS（全緑）

- [ ] **Step 4: アプリ再起動して実機確認（Playwright）**

再起動:
```bash
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }"
"C:/Users/moro/AppData/Local/Programs/Python/Python311/Scripts/streamlit.exe" run app.py --server.port 8502 --server.headless true &
```
health=ok を待って `http://localhost:8502/号別明細` を開き、次を目視確認:
- 号を選ぶと「配布原価(税込)／配布員代／雑費」メトリクスが出る
- 「直接入力」で 日付・作業・金額 を追加 → 表に日付・曜日つきで並び、配布員代小計・配布原価が増える
- 追加した行を「対象の行」で選び **更新**（金額変更）→ 反映。**削除** → 消える
- 「雑費」に小口(現金)・買掛(クレジット/振込)が支払方法つきで出る
- 「号原価まとめをExcelで保存」で4シート(業務委託/直接入力/雑費/合計)が落ちる
- 電卓確認: 配布原価 = 配布員代小計 + 雑費小計

- [ ] **Step 5: コミット**

```bash
git add pages/03_号別明細.py
git commit -m "feat(ui): 号別明細を配布員代(業務委託+直接入力)/雑費(小口+買掛)/配布原価に改修"
```

---

## Self-Review（作成後チェック）

- 仕様カバレッジ: work_date 拡張(T1) / 支払方法(T2) / グループ集計(T3) / ページUI・直接入力の追加修正削除・雑費自動集計・号原価まとめ出力(T4) を網羅。
- プレースホルダ: なし（各ステップに実コード・実コマンド）。
- 型整合: `payment_method(kind,row)`、`cost_groups(agg)->{labor,misc,genka}`、`add/update/delete_issue_manual_cost` の署名が T1〜T4 で一致。
- 総額不変: `cost_groups.genka == aggregate_issue.total` をテストで担保、実機の電卓確認も実施。
