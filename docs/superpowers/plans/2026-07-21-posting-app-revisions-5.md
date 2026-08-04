# 第5弾 一覧の一括操作（チェック選択→選択Excel/選択削除） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 小口・買掛・売掛（pages/01）と業務委託登録の登録済み一覧（pages/02）を、チェックで複数選択→〔選択した行をExcel〕〔選択した行を削除（確認付き）〕に統一し、行ごとの削除ボタンを廃止する。

**Architecture:** 共通部品を `common/ui.py` に3つ追加（純ロジックは `common/posting_logic.py` に2つ）。データ層（`posting_store` の削除関数）は不変。pages/01 は `nice_table` をチェック付きエディタに置換し `section_export`（全件）は残す。pages/02 は既存のチェックUIを流用し、行ごと「請求を削除」を選択削除に置換。

**Tech Stack:** Streamlit 1.58.0（`st.data_editor` CheckboxColumn / session_state 注入で AppTest 選択再現）、pytest、`streamlit.testing.v1.AppTest`。

## Global Constraints

- ブランチは `feature/revisions-5`（`feature/revisions-4` から分岐済み）。
- データ層（`posting_store` / スキーマ）は変更しない。削除は既存 `store.delete_petty_cash` / `store.delete_payable` / `store.delete_receivable` / `store.delete_contract_invoice` を使う。
- 一括削除は必ず確認を挟む（「⚠️ 選択したN件を削除しますか？」→ はい/やめる）。押した時点の選択idをスナップショットして確定する。
- `flash(msg, section=...)` ＋ `show_flash(section)` の対で操作タブにだけ成功メッセージ（タブは1実行で全描画されるため section 必須）。更新後 `st.rerun()`。
- Excel出力は `common.excel_io.freeze_xlsx_bytes()` を通す（内容不変ならDL URL不変・404防止）。
- ウィジェット/確認の key は画面内で一意（行id・master名・用途で区別）。
- `common/*.py` を変えたら 8502 を**プロセスごと停止して**再起動（bat再クリックでは反映されない）。
- 検証は実データを触らない：`POSTING_DB_PATH` に一時DB＋`store.init_db`／`store.seed_masters`（AppTest）。
- `st.data_editor` の選択は AppTest では `session_state[<editor_key>] = {"edited_rows": {row_index: {"選択": True}}, "added_rows": [], "deleted_rows": []}` で再現する。

---

### Task 1: 選択の純ロジック（id抽出・Excel用行）

**Files:**
- Modify: `common/posting_logic.py`（末尾に2関数追加）
- Test: `tests/test_posting_logic.py`（末尾に追加）

**Interfaces:**
- Produces:
  - `selected_ids_from_editor(edited_df, *, id_col="No.", select_col="選択") -> list[int]` — `select_col==True` の行の `id_col` を int で返す。
  - `rows_for_excel(edited_df, *, select_col="選択") -> list[dict]` — `select_col==True` の行から `select_col` を除いた dict のリスト。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_posting_logic.py の末尾に追加
import pandas as pd
from common import posting_logic


def test_selected_ids_from_editor():
    df = pd.DataFrame([
        {"選択": True, "No.": 3, "金額": "¥1"},
        {"選択": False, "No.": 2, "金額": "¥2"},
        {"選択": True, "No.": 5, "金額": "¥3"},
    ])
    assert posting_logic.selected_ids_from_editor(df) == [3, 5]


def test_selected_ids_empty_when_none_checked():
    df = pd.DataFrame([{"選択": False, "No.": 1}])
    assert posting_logic.selected_ids_from_editor(df) == []


def test_rows_for_excel_drops_select_col():
    df = pd.DataFrame([
        {"選択": True, "No.": 3, "金額": "¥1"},
        {"選択": False, "No.": 2, "金額": "¥2"},
    ])
    rows = posting_logic.rows_for_excel(df)
    assert rows == [{"No.": 3, "金額": "¥1"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_posting_logic.py -k "selected_ids or rows_for_excel" -v`
Expected: FAIL（`AttributeError: ... has no attribute 'selected_ids_from_editor'`）

- [ ] **Step 3: Write minimal implementation**

```python
# common/posting_logic.py の末尾に追加
def selected_ids_from_editor(edited_df, *, id_col="No.", select_col="選択"):
    """data_editor の編集結果から、選択された行の id を int のリストで返す。"""
    ids = []
    for _, row in edited_df.iterrows():
        if row.get(select_col):
            ids.append(int(row[id_col]))
    return ids


def rows_for_excel(edited_df, *, select_col="選択"):
    """選択された行から選択列を除いた dict のリスト（選択行のExcel出力用）。"""
    out = []
    for _, row in edited_df.iterrows():
        if row.get(select_col):
            out.append({k: v for k, v in row.items() if k != select_col})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_posting_logic.py -k "selected_ids or rows_for_excel" -v`
Expected: PASS（3件）

- [ ] **Step 5: Commit**

```bash
git add common/posting_logic.py tests/test_posting_logic.py
git commit -m "feat: 選択行のid抽出・Excel用行を作る純関数(第5弾の土台)"
```

---

### Task 2: 一括操作の共通UI部品（common/ui.py）

**Files:**
- Modify: `common/ui.py`
- Test: `tests/test_pages_smoke.py`（AppTest.from_function で共通部品を直接描画して確認）

**Interfaces:**
- Consumes: `posting_logic.selected_ids_from_editor` / `rows_for_excel`（Task 1）、`freeze_xlsx_bytes`、`flash`。
- Produces:
  - `checkbox_list_editor(disp_rows, *, key, select_col="選択") -> pd.DataFrame` — 先頭に選択チェック列、他列 `disabled` の `st.data_editor`。
  - `selected_rows_excel_button(edited_df, *, key, filename, select_col="選択", label=None, container=None)` — 選択行だけを（選択列除外で）Excel化して download_button。0件は disabled。
  - `bulk_delete_action(selected_ids, *, delete_fn, section, key, noun="件", container=None)` — 「選択した行を削除（N件）」＋確認（スナップショット）→ はいで各id削除→flash→rerun。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -k "bulk_delete_action" -v`
Expected: FAIL（`ImportError: cannot import name 'bulk_delete_action'`）

- [ ] **Step 3: Write minimal implementation**

`common/ui.py` に追加（`confirm_delete` の下あたり）:

```python
def checkbox_list_editor(disp_rows, *, key, select_col="選択"):
    """一覧を『選択チェック列＋他列は読み取り専用』の data_editor で描画して返す。
    disp_rows は list[dict] か DataFrame（表示用に整形済み・id列も含めておく）。"""
    import pandas as pd

    df = disp_rows if isinstance(disp_rows, pd.DataFrame) else pd.DataFrame(disp_rows)
    if df.empty:
        st.caption("表示できる行がありません。")
        return df
    other = [c for c in df.columns if c != select_col]
    if select_col not in df.columns:
        df = df.copy()
        df.insert(0, select_col, False)
    df = df[[select_col] + [c for c in df.columns if c != select_col]]
    return st.data_editor(
        df, hide_index=True, use_container_width=True,
        column_config={select_col: st.column_config.CheckboxColumn(select_col, default=False)},
        disabled=other, key=key)


def selected_rows_excel_button(edited_df, *, key, filename, select_col="選択",
                               label=None, container=None):
    """選択された行だけを（選択列を除いて）Excel化する download_button。0件は無効。"""
    from common import posting_logic
    from common.excel_io import freeze_xlsx_bytes
    import pandas as pd

    rows = posting_logic.rows_for_excel(edited_df, select_col=select_col)
    target = container if container is not None else st
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(rows or [{}]).to_excel(w, index=False, sheet_name="選択した行")
    target.download_button(
        label or f"選択した行をExcelで保存（{len(rows)}件）",
        data=freeze_xlsx_bytes(buf.getvalue()), file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:", disabled=not rows, key=key,
        use_container_width=True)


def bulk_delete_action(selected_ids, *, delete_fn, section, key, noun="件", container=None):
    """選択した行をまとめて削除する。確認を挟み、押した時点の選択idを固定してから消す。
    ボタンだけ container(列)に置くと、確認UIは呼び出し位置＝全幅に出る。"""
    pending = f"_bulkdel_pending_{key}"
    ids = st.session_state.get(pending)
    if ids:  # 確認待ち
        st.warning(f"⚠️ 選択した{len(ids)}{noun}を削除しますか？")
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("はい、削除する", type="primary", key=f"{key}_ok"):
            for i in ids:
                delete_fn(i)
            st.session_state.pop(pending, None)
            flash(f"{len(ids)}{noun}を削除しました", section)
            st.rerun()
        if c2.button("やめる", key=f"{key}_no"):
            st.session_state.pop(pending, None)
            st.rerun()
        return
    target = container if container is not None else st
    if target.button(f"選択した行を削除（{len(selected_ids)}{noun}）",
                     key=f"{key}_btn", disabled=not selected_ids,
                     use_container_width=True):
        st.session_state[pending] = list(selected_ids)
        st.rerun()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages_smoke.py -k "bulk_delete_action" -v`
Expected: PASS（2件）

- [ ] **Step 5: Commit**

```bash
git add common/ui.py tests/test_pages_smoke.py
git commit -m "feat: 一括操作の共通UI部品(checkbox_list_editor/選択Excel/一括削除・確認付き)"
```

---

### Task 3: 小口・買掛・売掛（pages/01）をチェック選択の一括操作に

**Files:**
- Modify: `pages/01_経費・買掛・売掛.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: `checkbox_list_editor` / `selected_rows_excel_button` / `bulk_delete_action`（Task 2）、`posting_logic.selected_ids_from_editor`（Task 1）。
- Produces: 小口/買掛/売掛の各一覧タブが「チェック付き一覧＋全件Excel/印刷（残す）＋〔選択した行をExcel〕〔選択した行を削除（確認付き）〕」になる。行ごと削除（`_delete_rows_ui`）は撤去し、関数も削除。

**方針:** 各タブで `_disp` の先頭に `"No."`＝`r["id"]` を足し、`nice_table(_disp,...)` を `checkbox_list_editor(_disp, key=...)` に置換。`section_export(_disp,...)` は残す。`_delete_rows_ui(...)` を選択Excel＋一括削除に置換。3タブとも同型。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
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
    # 先頭行(index 0)だけ選択
    at.session_state["petty_select"] = {
        "edited_rows": {0: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.run()
    at.button(key="petty_bulk_del_btn").click().run()
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
    keys = [b.key for b in at.download_button]
    assert any(k and "petty_xlsx" in k for k in keys)  # section_export の全件Excelが残る
```

> 注意: `mode` の radio は key 無しで既定「小口」。上のテストは小口だけを検証する（買掛/売掛は同型の配線なので、必要なら `at.radio[0].set_value("買掛").run()` で切替えて追加検証してよい）。選択の反映（`session_state["petty_select"]`）や行indexは実装に合わせて調整してよいが、アサーション＝「選択した1件だけ消える」「`del_petty_*` が無い」「全件Excelが残る」は変えないこと。`add_petty_cash`/`add_expense_category` 等の seed 関数のシグネチャは既存の `common/posting_store.py` を読んで正しい引数で呼ぶこと（この計画のseedコードは目安）。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pages_smoke.py -k "petty_bulk_delete or per_row_delete_gone or whole_list_export" -v`
Expected: FAIL（`petty_bulk_del_btn` が無い／`del_petty_*` がまだ在る）

- [ ] **Step 3: Write minimal implementation**

各一覧タブを次の形に変える。**小口**（現状 `nice_table`→`section_export`→`_delete_rows_ui` の3行を置換）:

```python
        _disp = [{"No.": r["id"], "日付": r["date"] or "",
                  "配布員": _dists.get(r.get("distributor_id"), ""),
                  "費目": _cats.get(r["category_id"], ""),
                  "金額": _yen(r["amount"]), "案件": _projs.get(r["project_id"], ""),
                  "メモ": r["memo"] or "",
                  "登録日": (r.get("created_at") or "")[:10]} for r in _rows]
        if not _disp:
            st.caption("小口の登録はまだありません。")
        else:
            section_export(_disp, "小口一覧", key="petty")   # 全件Excel/印刷（残す）
            edited = checkbox_list_editor(_disp, key="petty_select")
            selected_ids = posting_logic.selected_ids_from_editor(edited)
            st.caption(f"選択中：{len(selected_ids)}件")
            b1, b2 = st.columns(2)
            selected_rows_excel_button(edited, key="petty_sel_xlsx",
                                       filename="小口_選択一覧", container=b1)
            bulk_delete_action(selected_ids, delete_fn=store.delete_petty_cash,
                               section="petty", key="petty_bulk_del", container=b2)
```

**買掛**（同型・`_disp` 先頭に `"No.": r["id"]`）:
```python
        if not _disp:
            st.caption("買掛の登録はまだありません。")
        else:
            section_export(_disp, "買掛一覧", key="pay")
            edited = checkbox_list_editor(_disp, key="pay_select")
            selected_ids = posting_logic.selected_ids_from_editor(edited)
            st.caption(f"選択中：{len(selected_ids)}件")
            b1, b2 = st.columns(2)
            selected_rows_excel_button(edited, key="pay_sel_xlsx",
                                       filename="買掛_選択一覧", container=b1)
            bulk_delete_action(selected_ids, delete_fn=store.delete_payable,
                               section="payable", key="pay_bulk_del", container=b2)
```
（買掛 `_disp` に `"No.": r["id"]` を先頭追加）

**売掛**（同型・`_disp` 先頭に `"No.": r["id"]`・`filename="売掛_選択一覧"`・`delete_fn=store.delete_receivable`・section=`receivable`・key接頭 `recv_*`）。

各タブで旧 `nice_table(_disp, ...)` と `_delete_rows_ui(...)` の呼び出しを削除。3タブとも `_delete_rows_ui` を呼ばなくなったら、関数定義（`pages/01` 冒頭の `_delete_rows_ui`）も削除する。`import` に `checkbox_list_editor, selected_rows_excel_button, bulk_delete_action` を追加（`from common.ui import (...)` に足す）。`nice_table` が他で未使用になれば import から外してよい（残しても害はない）。

> `_disp` に `"No."` を足すと `section_export`（全件Excel）にも No. 列が入る。実害はない（No.＝id）。気になる場合のみ section_export に渡す前に No. を除いた別リストを作ってよいが、YAGNI で今はそのまま。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages_smoke.py -k "petty_bulk_delete or per_row_delete_gone or whole_list_export or pages_smoke" -v`
その後: `python -m pytest tests/test_pages_smoke.py -q`
Expected: PASS（新規＋既存スモーク）。既存の `del_petty_*`/`del_pay_*`/`del_recv_*` を参照する旧テストがあれば、選択削除方式に合わせて**アサーションの意味を保ったまま**書き換える（「選んだ行が消える」ことを検証する形に）。

- [ ] **Step 5: Commit**

```bash
git add pages/01_経費・買掛・売掛.py tests/test_pages_smoke.py
git commit -m "feat: 小口・買掛・売掛の一覧をチェック選択の一括Excel/一括削除に(行ごと削除を廃止)"
```

---

### Task 4: 業務委託登録（pages/02）の削除を選択削除に

**Files:**
- Modify: `pages/02_業務委託登録.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: `bulk_delete_action`（Task 2）。既存の `edited`（`contract_list_editor`）・`selected_ids` をそのまま使う。
- Produces: 下部の行ごと「請求を削除」セクションを撤去し、〔選択した行を削除〕に置換。〔報告書まとめてZIP〕〔選択した行を一覧Excel〕は残す。

**方針:** `pages/02` の登録済み一覧タブで、`st.divider()` ＋ `st.markdown("**請求を削除**")` ＋ `for inv in invoices:` の `confirm_delete` ループ（"請求を削除" セクション全体）を削除し、代わりに `bulk_delete_action` を1行置く。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
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
    at.run()
    at.button(key="invoice_bulk_del_btn").click().run()
    at.button(key="invoice_bulk_del_ok").click().run()
    assert len(store.list_contract_invoices(db_path=db)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pages_smoke.py -k "contract_per_row or contract_bulk_delete" -v`
Expected: FAIL（`del_inv_*` がまだ在る／`invoice_bulk_del_btn` が無い）

- [ ] **Step 3: Write minimal implementation**

`pages/02_業務委託登録.py` の登録済み一覧タブで、次のブロック（"請求を削除" セクション全体）を削除する:
```python
    # --- 請求を削除 ---
    st.divider()
    st.markdown("**請求を削除**")
    for inv in invoices:
        total = posting_logic.invoice_total(detail_by_id[inv["id"]]["lines"])
        name = id2name.get(inv["distributor_id"], "?")
        detail_txt = (...)
        c1, c2 = st.columns([5, 1])
        c1.caption(detail_txt)
        confirm_delete(key=f"del_inv_{inv['id']}", detail=detail_txt,
                       on_confirm=lambda i=inv["id"]: store.delete_contract_invoice(i),
                       section="invoice_list", button_container=c2)
```
代わりに、選択Excel（b2）の後・「配布員別 報酬合計」の `st.divider()` の前に置く:
```python
    from common.ui import bulk_delete_action  # 既存 import に足してもよい
    bulk_delete_action(selected_ids, delete_fn=store.delete_contract_invoice,
                       section="invoice_list", key="invoice_bulk_del")
```
（`from common.ui import (...)` の行に `bulk_delete_action` を足すのが望ましい。`confirm_delete` が他で未使用になれば import から外してよい。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages_smoke.py -k "contract_per_row or contract_bulk_delete" -v`
その後: `python -m pytest tests/test_pages_smoke.py -q`
Expected: PASS。既存の `del_inv_*` を参照するテストがあれば選択削除方式に合わせて書き換える（意味＝「選んだ請求が消える」を保つ）。

- [ ] **Step 5: Commit**

```bash
git add pages/02_業務委託登録.py tests/test_pages_smoke.py
git commit -m "feat: 業務委託登録の削除を選択削除に(行ごと請求削除を廃止・ZIP/選択Excelは維持)"
```

---

### Task 5: 全テスト＋8502再起動＋実機目視

**Files:**
- Test: 全体

- [ ] **Step 1: 全テスト**

Run: `cd /c/Users/moro/posting-automation && python -m pytest -q`
Expected: 全パス。失敗は原因を直して再実行。

- [ ] **Step 2: 8502 をプロセスごと停止して新コードで再起動**

（common/ui.py・pages を変更しているため必須。古いモジュールのキャッシュが AttributeError の原因になる。）
PowerShell 相当:
```
# 8502 の python/streamlit を Stop-Process（8501 テレアポは残す）→
# streamlit run app.py --server.port 8502 --server.headless true を新規起動 → /_stcore/health が ok を確認
```

- [ ] **Step 3: 目視チェック（オーナー確認観点）**

- [ ] 小口/買掛/売掛/業務委託の各一覧に**選択チェック列**が出る
- [ ] チェックした行だけ〔選択した行をExcel〕でダウンロードできる
- [ ] 〔選択した行を削除〕→**確認**（はい/やめる）→ 選んだ行だけ消える
- [ ] 行ごとの削除ボタンが無くなっている
- [ ] 小口/買掛/売掛で「一覧全体をExcel/印刷」が**残っている**
- [ ] 業務委託登録の〔報告書まとめてZIP〕〔選択した行を一覧Excel〕が**残っている**
- [ ] 既存データ（第3・4弾までの登録）が壊れていない

- [ ] **Step 4: オーナーへ実機確認を依頼**

第3・4・5弾をまとめて 8502 で確認 → OKなら `git merge --no-ff feature/revisions-5`（3弾すべて同時にmasterへ）。

---

## Self-Review（この計画のチェック結果）

- **仕様網羅**: ①チェック選択導入=Task2+Task3+Task4 ②選択Excel=Task2(selected_rows_excel_button)+Task3/4 ③選択削除（確認付き）=Task2(bulk_delete_action)+Task3/4 ④行ごと削除廃止=Task3(_delete_rows_ui撤去)/Task4(請求を削除撤去) ⑤小口等の全件Excel/印刷を残す=Task3(section_export維持) ⑥業務委託のZIP/選択Excel維持=Task4。すべて対応あり。
- **プレースホルダ**: なし（各ステップに実コード・実コマンド・期待結果）。
- **型/名前の一貫性**: `selected_ids_from_editor`/`rows_for_excel`（Task1定義→Task2/3使用）、`checkbox_list_editor`/`selected_rows_excel_button`/`bulk_delete_action`（Task2定義→Task3/4使用）、ボタンkey `*_bulk_del_btn/_ok/_no`・`*_sel_xlsx`（テストと実装で一致）、削除関数名（`delete_petty_cash`/`delete_payable`/`delete_receivable`/`delete_contract_invoice`＝既存）を確認。
- **スコープ**: pages/01・02 と共通部品のみ。単一計画に収まる。
