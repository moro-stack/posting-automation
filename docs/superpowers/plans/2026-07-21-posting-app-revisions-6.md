# 第6弾 実装計画（確認文言統一／号別明細調整／原価・売上まとめ新ページ）

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven / workflow orchestration. TDD・checkbox steps。**各タスクはテストを別ファイルに書く**（`tests/test_rev6_*.py`）＝共有テストファイルの衝突回避。

**Goal:** ①確認ボタンをはい/いいえに統一 ②号別明細の業務委託内訳に支払日 ③号別明細から買掛除外 ④全社の原価・売上まとめ新ページ。

**Tech Stack:** Streamlit 1.58 / pytest / AppTest。データ層不変。

## Global Constraints
- ブランチ `feature/revisions-6`（revisions-5から分岐済）。データ層（`posting_store`/スキーマ）不変。
- 各タスクの新規テストは専用ファイル（`tests/test_rev6_<task>.py`）に書く。既存 `tests/test_pages_smoke.py` はラベル参照アサーションの更新のみ（キー参照は不変なので触らない）。
- 変更後は全リポジトリ `python -m pytest -q` が緑であること。pytestは必ずリポジトリルート `C:\Users\moro\posting-automation` から実行。
- Excelは `freeze_xlsx_bytes`。`flash(section=)`＋`st.rerun()`。data_editorのAppTest選択は同runに束ねる。

---

### Task A（①）: 確認ボタンを「はい／いいえ」に統一

**Files:** Modify `common/ui.py`, `pages/01_経費・買掛・売掛.py`, `tests/test_pages_smoke.py`(ラベル参照の更新のみ); Create `tests/test_rev6_confirm.py`

- [ ] **Step 1: 失敗するテスト（新ファイル）**

```python
# tests/test_rev6_confirm.py
from streamlit.testing.v1 import AppTest


def _confirm_page():
    import streamlit as st
    from common.ui import confirm_delete, apply_app_style
    apply_app_style()
    st.session_state.setdefault("_c", 0)
    confirm_delete(key="t", detail="x",
                   on_confirm=lambda: st.session_state.__setitem__("_c", 1))


def test_confirm_delete_uses_hai_iie():
    at = AppTest.from_function(_confirm_page).run()
    at.button(key="t_btn").click().run()          # 確認を出す
    labels = [b.label for b in at.button]
    assert "はい" in labels and "いいえ" in labels
    assert "はい、削除する" not in labels and "やめる" not in labels


def _bulk_page():
    import streamlit as st
    from common.ui import bulk_delete_action, apply_app_style
    apply_app_style()
    st.session_state.setdefault("_d", [])
    bulk_delete_action([1], delete_fn=lambda i: st.session_state["_d"].append(i),
                       section="t", key="bd")


def test_bulk_delete_uses_hai_iie():
    at = AppTest.from_function(_bulk_page).run()
    at.button(key="bd_btn").click().run()
    labels = [b.label for b in at.button]
    assert "はい" in labels and "いいえ" in labels
```

- [ ] **Step 2: 失敗確認** `python -m pytest tests/test_rev6_confirm.py -v` → FAIL（"はい"が無い）

- [ ] **Step 3: 実装**
  - `common/ui.py` `confirm_delete` 内: `c1.button("はい、削除する", type="primary", key=f"{key}_ok")` の第1引数を **"はい"** に、`c2.button("やめる", key=f"{key}_no")` を **"いいえ"** に。
  - `common/ui.py` `bulk_delete_action` 内: 同様に `"はい、削除する"`→`"はい"`、`"やめる"`→`"いいえ"`。
  - `pages/01_経費・買掛・売掛.py` の重複チェック確認 ×3（`petty_ok`/`petty_no`、`pay_ok`/`pay_no`、`recv_ok`/`recv_no`）: `"はい、登録する"`→`"はい"`、その直後の `"やめる"`→`"いいえ"`。**キーは変えない**。
  - ⚠️ 対象外（変えない）: OCRの `"全部登録"`／`petty_bulk_cancel`・`pay_bulk_cancel` の `"やめる"`、`pages/05` の編集/新規ダイアログの `"やめる"`（フォームcancel）。
  - 既存テストの更新: `tests/test_pages_smoke.py` 内で **ラベル `"はい、削除する"` を参照している箇所を `"はい"` に**（例: `assert any(b.label == "はい、削除する" ...)` → `"はい"`）。`grep -n '"はい、削除する"\|"はい、登録する"' tests/` で全部拾って更新。`"やめる"` を参照する箇所は文脈を確認し、**confirm_delete/bulk_delete/dup-check由来のものだけ `"いいえ"` に**（`_cancel_edit`（編集ダイアログのやめる）は対象外＝そのまま）。

- [ ] **Step 4: パス確認** `python -m pytest tests/test_rev6_confirm.py -v` → PASS。続けて `python -m pytest tests/test_pages_smoke.py -q` で回帰なし。

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: 確認ボタンをはい/いいえに統一(削除・一括削除・重複チェック)"`

---

### Task B（④-logic）: 全社集計の純関数

**Files:** Modify `common/posting_logic.py`; Create `tests/test_rev6_summary_logic.py`

- [ ] **Step 1: 失敗するテスト（新ファイル）**

```python
# tests/test_rev6_summary_logic.py
from common import posting_logic as L


def test_company_summary_totals():
    r = L.company_summary_totals(
        receivables=[{"amount": 1000}, {"amount": 500}],
        payables=[{"amount": 300}], petty=[{"amount": 200}],
        contract_lines=[{"amount": 400}], manual=[{"amount": 100}])
    assert r["sales"] == 1500
    assert r["cost"] == 1000          # 300+200+400+100
    assert r["profit"] == 500


def test_company_summary_rows_classifies_and_resolves_names():
    rows = L.company_summary_rows(
        receivables=[{"month": "2026-07", "client_id": 1, "project_id": 9, "amount": 1000}],
        payables=[{"date": "2026-07-03", "vendor_name": "大家", "project_id": 9, "amount": 300}],
        petty=[{"date": "2026-07-04", "category_id": 2, "project_id": 9, "amount": 200, "memo": "茶"}],
        contract_lines=[{"issue_date": "2026-07-05", "distributor_id": 3, "project_id": 9, "amount": 400}],
        manual=[{"work_date": "2026-07-06", "content": "配布", "project_id": 9, "amount": 100}],
        id2proj={9: "A号"}, id2vendor={}, id2cat={2: "飲料"}, id2client={1: "クライアントX"},
        id2dist={3: "山田"})
    kinds = {row["区分"] for row in rows}
    assert kinds == {"売上", "買掛", "小口", "業務委託", "直接入力"}
    sales = [r for r in rows if r["区分"] == "売上"][0]
    assert sales["項目"] == "クライアントX" and sales["案件"] == "A号" and sales["金額"] == 1000
    pay = [r for r in rows if r["区分"] == "買掛"][0]
    assert pay["項目"] == "大家" and pay["日付"] == "2026-07-03"
    dist = [r for r in rows if r["区分"] == "業務委託"][0]
    assert dist["項目"] == "山田" and dist["日付"] == "2026-07-05"
```

- [ ] **Step 2: 失敗確認** `python -m pytest tests/test_rev6_summary_logic.py -v` → FAIL

- [ ] **Step 3: 実装（`common/posting_logic.py` 末尾に追加）**

```python
def company_summary_totals(*, receivables, payables, petty, contract_lines, manual):
    """全社の売上(売掛)・原価(買掛+小口+業務委託+直接入力)・利益。"""
    s = sum(_num(r.get("amount")) for r in receivables)
    c = (sum(_num(r.get("amount")) for r in payables)
         + sum(_num(r.get("amount")) for r in petty)
         + sum(_num(r.get("amount")) for r in contract_lines)
         + sum(_num(r.get("amount")) for r in manual))
    return {"sales": s, "cost": c, "profit": s - c}


def company_summary_rows(*, receivables, payables, petty, contract_lines, manual,
                         id2proj, id2vendor, id2cat, id2client, id2dist):
    """区分・日付・項目・案件・金額 に正規化した明細行のリスト（原価・売上まとめ用）。"""
    def _proj(pid):
        return id2proj.get(pid, "") if pid is not None else ""
    rows = []
    for r in receivables:
        rows.append({"区分": "売上", "日付": r.get("month") or "",
                     "項目": id2client.get(r.get("client_id"), ""),
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in payables:
        rows.append({"区分": "買掛", "日付": r.get("date") or r.get("month") or "",
                     "項目": r.get("vendor_name") or id2vendor.get(r.get("vendor_id"), ""),
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in petty:
        item = id2cat.get(r.get("category_id"), "")
        if r.get("memo"):
            item = f"{item}（{r['memo']}）" if item else r["memo"]
        rows.append({"区分": "小口", "日付": r.get("date") or "", "項目": item or "小口",
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in contract_lines:
        rows.append({"区分": "業務委託", "日付": r.get("issue_date") or "",
                     "項目": id2dist.get(r.get("distributor_id"), ""),
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    for r in manual:
        rows.append({"区分": "直接入力", "日付": r.get("work_date") or "",
                     "項目": r.get("content") or "",
                     "案件": _proj(r.get("project_id")), "金額": _num(r.get("amount"))})
    return rows
```

- [ ] **Step 4: パス確認** `python -m pytest tests/test_rev6_summary_logic.py -v` → PASS

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: 全社の原価・売上まとめの純関数(totals/rows)"`

---

### Task C（②③）: 号別明細に支払日追加＋買掛を集計から外す

**Files:** Modify `pages/03_号別明細.py`; Create `tests/test_rev6_issue.py`

- [ ] **Step 1: 失敗するテスト（新ファイル）**

```python
# tests/test_rev6_issue.py
import os
from streamlit.testing.v1 import AppTest
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(db):
    at = AppTest.from_file(os.path.join(ROOT, "pages", "03_号別明細.py"), default_timeout=30)
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
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = _run(db)
    text = _rendered(at)
    # 買掛9999は配布原価にも雑費にも出ない
    assert "9999" not in text
    assert "大家" not in text
```

> 注意: seed 関数（`add_project`/`add_distributor`/`add_contract_invoice`/`add_payables_vendor`/`add_payable`）は `common/posting_store.py` の実シグネチャに合わせること（この計画のseedは目安）。`03_号別明細.py` は先頭案件をデフォルト選択（pills key無し）＝AppTestは既定で描画される。買掛が「9999」で出るか出ないかで③を検証。

- [ ] **Step 2: 失敗確認** `python -m pytest tests/test_rev6_issue.py -v` → FAIL（支払日列が無い／買掛が出る）

- [ ] **Step 3: 実装（`pages/03_号別明細.py`）**
  - **③ 買掛除外**:
    - `payables = posting_logic.filter_rows_by_period(store.list_payables(project_id=pid), "month", lo, hi)` の行を削除。
    - `agg = posting_logic.aggregate_issue(pid, petty=petty, payables=[], contract_lines=contract_lines, manual=manual)` に（`payables=[]`）。
    - `pay_total = sum(...)` の行を削除。
    - 雑費内訳 `_misc` を組む部分から `for r in payables:` のループ（買掛行追加）を丸ごと削除。
    - 雑費expander: 見出し `雑費の内訳（小口＋買掛）` → `雑費の内訳（小口）`、`st.caption(f"雑費 ＝ 小口 {_yen(petty_total)} ＋ 買掛 {_yen(pay_total)}")` → `st.caption(f"雑費 ＝ 小口 {_yen(petty_total)}")`。
    - `_misc` の各行 dict にある `"支払方法"` は現金のみになる（`payment_method("petty", r)`）。号原価まとめExcelの雑費シート列定義（`columns=["配布員","項目","金額","支払方法","日付"]`）はそのままでよい。
  - **② 支払日（業務委託内訳）**:
    - `_con_disp` の各行dictの先頭に `"支払日": l.get("issue_date") or ""` を追加（`_with_label(...)` の中の dict に）。例:
      ```python
      _con_disp = [_with_label({"支払日": l.get("issue_date") or "",
                                "配布員": l.get("distributor_name") or "",
                                "種別": l.get("remark") or "",
                                "数量": posting_logic.qty_label(l.get("report_qty"), l.get("remark"), l.get("pay_type")),
                                "単価": _yen(l.get("unit_price")), "合計": _yen(l.get("amount"))},
                               l.get("other_label")) for l in issue_contract]
      ```
    - 号原価まとめExcelの「業務委託」シートの空列定義 `columns=["配布員","種別","数量","単価","合計"]` を `["支払日","配布員","種別","数量","単価","合計"]` に。

- [ ] **Step 4: パス確認** `python -m pytest tests/test_rev6_issue.py -v` → PASS。続けて `python -m pytest tests/test_pages_smoke.py -q`（号別明細の既存テストが買掛前提なら意味を保って更新）。

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: 号別明細の業務委託内訳に支払日追加・買掛を集計から除外"`

---

### Task D（④-page）: 原価・売上まとめ新ページ＋ナビ登録

**Files:** Create `pages/06_原価・売上まとめ.py`; Modify `app.py`; Create `tests/test_rev6_summary_page.py`

**Interfaces:** Consumes `posting_logic.company_summary_totals` / `company_summary_rows`（Task B）。

- [ ] **Step 1: 失敗するテスト（新ファイル）**

```python
# tests/test_rev6_summary_page.py
import os
from streamlit.testing.v1 import AppTest
from common import posting_store as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed(db, monkeypatch):
    monkeypatch.setenv("POSTING_DB_PATH", db)
    store.init_db(db); store.seed_masters(db_path=db)
    pid = store.add_project("A号", db_path=db)
    cli = store.add_receivables_client("クライアントX", db_path=db)
    store.add_receivable("2026-07", cli, 5000, project_id=pid, db_path=db)
    ven = store.add_payables_vendor("大家", db_path=db)
    store.add_payable(None, ven, 3000, date="2026-07-02", project_id=pid, db_path=db)
    return pid


def test_summary_page_shows_sales_cost_profit_and_payable_as_cost(tmp_path, monkeypatch):
    db = os.path.join(tmp_path, "t.db"); _seed(db, monkeypatch)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "06_原価・売上まとめ.py"), default_timeout=30)
    at.run()
    assert not at.exception
    parts = []
    for el in at.markdown: parts.append(str(el.value))
    for el in at.table: parts.append(el.value.to_string())
    for el in at.dataframe: parts.append(str(el.value))
    text = "\n".join(parts)
    assert "売上" in text and "原価" in text and "利益" in text
    assert "5,000" in text            # 売上
    assert "大家" in text             # 買掛が原価明細に出る
    assert "3,000" in text            # 買掛の金額


def test_app_nav_lists_summary_before_issue():
    import re
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    i_sum = src.find("原価・売上まとめ")
    i_iss = src.find("号別明細")
    assert i_sum != -1 and i_sum < i_iss   # ナビで号別明細より前
```

- [ ] **Step 2: 失敗確認** `python -m pytest tests/test_rev6_summary_page.py -v` → FAIL（ページが無い／ナビ未登録）

- [ ] **Step 3: 実装**

`pages/06_原価・売上まとめ.py`（新規）:
```python
import io
import pandas as pd
import streamlit as st

from common import posting_logic
from common import posting_store as store
from common.excel_io import freeze_xlsx_bytes
from common.ui import apply_app_style, section_export, nice_table, period_picker, show_flash

apply_app_style()
show_flash()
st.title("原価・売上まとめ（KPS大阪支社）")


def _yen(v):
    return f"¥{posting_logic.fmt_num(v)}"


lo, hi, note = period_picker(key="summary_period")
st.caption(f"表示期間: {note}")

# 全案件横断で集める（project_id 指定なし＝全件）
receivables = [r for r in store.list_receivables() if posting_logic.in_period(r.get("month"), lo, hi)]
payables = [r for r in store.list_payables()
            if posting_logic.in_period(r.get("date") or r.get("month"), lo, hi)]
petty = [r for r in store.list_petty_cash() if posting_logic.in_period(r.get("date"), lo, hi)]
manual = [r for r in store.list_issue_manual_costs()
          if r.get("work_date") is None or posting_logic.in_period(r.get("work_date"), lo, hi)]
contract_lines = []
for inv in store.list_contract_invoices():
    if not posting_logic.in_period(inv.get("issue_date"), lo, hi):
        continue
    detail = store.get_contract_invoice(inv["id"])
    for ln in detail["lines"]:
        ln = dict(ln)
        ln["issue_date"] = inv.get("issue_date")
        ln["distributor_id"] = inv.get("distributor_id")
        contract_lines.append(ln)

id2proj = {p["id"]: p["name"] for p in store.list_projects()}
id2vendor = {v["id"]: v["name"] for v in store.list_payables_vendors()}
id2cat = {c["id"]: c["name"] for c in store.list_expense_categories()}
id2client = {c["id"]: c["name"] for c in store.list_receivables_clients()}
id2dist = {d["id"]: d["name"] for d in store.list_distributors()}

totals = posting_logic.company_summary_totals(
    receivables=receivables, payables=payables, petty=petty,
    contract_lines=contract_lines, manual=manual)
rows = posting_logic.company_summary_rows(
    receivables=receivables, payables=payables, petty=petty,
    contract_lines=contract_lines, manual=manual,
    id2proj=id2proj, id2vendor=id2vendor, id2cat=id2cat,
    id2client=id2client, id2dist=id2dist)

s1, s2, s3 = st.columns(3)
s1.markdown(f'<div style="color:#67788a;font-weight:700;font-size:.9rem">売上（税込）</div>'
            f'<div style="color:#1f2d3a;font-weight:800;font-size:2.2rem">{_yen(totals["sales"])}</div>',
            unsafe_allow_html=True)
s2.markdown(f'<div style="color:#67788a;font-weight:700;font-size:.9rem">原価（税込）</div>'
            f'<div style="color:#1f2d3a;font-weight:800;font-size:2.2rem">{_yen(totals["cost"])}</div>',
            unsafe_allow_html=True)
_pc = "#0f87b8" if totals["profit"] >= 0 else "#c0392b"
s3.markdown(f'<div style="color:#67788a;font-weight:700;font-size:.9rem">利益</div>'
            f'<div style="color:{_pc};font-weight:800;font-size:2.2rem">{_yen(totals["profit"])}</div>',
            unsafe_allow_html=True)

st.divider()
st.markdown("**明細（原価・売上）**")
# 日付で並べ替え（空は末尾）
disp = sorted(rows, key=lambda r: (r["日付"] == "", r["日付"]))
disp = [{"日付": r["日付"], "区分": r["区分"], "項目": r["項目"],
         "案件": r["案件"], "金額": _yen(r["金額"])} for r in disp]
nice_table(disp, "この期間の原価・売上はありません。")
section_export(disp, "原価売上まとめ", key="summary")
```

`app.py`: `pages` リストで**号別明細の行の"前"に**次を挿入:
```python
    st.Page("pages/06_原価・売上まとめ.py", title="原価・売上まとめ", icon=":material/summarize:"),
```
（`st.Page("pages/03_号別明細.py", ...)` の1行上に置く。号別明細の `default=True` はそのまま維持。）

- [ ] **Step 4: パス確認** `python -m pytest tests/test_rev6_summary_page.py -v` → PASS。続けて全体 `python -m pytest -q`。

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: 原価・売上まとめ新ページを追加(号別明細の前に配置・買掛を原価表示)"`

---

## Self-Review
- **仕様網羅**: ①=TaskA ②=TaskC(支払日) ③=TaskC(買掛除外) ④=TaskB(logic)+TaskD(page+nav)。全対応。
- **プレースホルダ**: なし（実コード・実コマンド）。seed関数のシグネチャは実storeに合わせる旨を明記。
- **一貫性**: `company_summary_totals/rows`（TaskB定義→TaskD使用）、`payables=[]`（TaskC）、app.pyのnav順（TaskD＋テスト）を確認。
- **衝突回避**: 各タスク専用テストファイル。共有 `test_pages_smoke.py` はラベル参照更新のみ。ソースファイルは A(ui.py,pages01) / B(posting_logic) / C(pages03) / D(pages06,app.py) で重ならない。
