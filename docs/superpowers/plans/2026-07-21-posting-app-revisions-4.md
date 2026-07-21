# マスタ管理 第4弾（ステータストグル・別窓登録/編集） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** マスタ管理（全5タブ）を「1行＝1マスタ・その行でステータスが分かりトグルで切替・編集/新規登録は別窓」に作り替える。

**Architecture:** データ層は不変（第3弾の `active`・`count_master_usage`・`master_delete_action`・`update_*(active=...)` を再利用）。UIは `pages/05_マスタ管理.py` の作り替え＋`common/ui.py` にCSS追加＋`common/posting_logic.py` に純関数1つ追加。別窓は `st.dialog`。行ごとのCSSスコープは `st.container(key=...)` が付ける `st-key-<key>` クラスで限定する。

**Tech Stack:** Streamlit 1.58.0（`st.dialog` / `st.container(key=...)` 利用可）、pytest、`streamlit.testing.v1.AppTest`。

## Global Constraints

- ブランチは `feature/revisions-4`（`feature/revisions-3` から分岐済み）。
- データ層（`posting_store` / スキーマ）は変更しない。UIとCSSと純関数のみ。
- 物理削除の可否は必ず `posting_logic.master_delete_action(count)`（int==0 のときだけ `"delete"`）で判定する。使用中マスタを物理削除しない（過去データ保護）。
- ウィジェット／ダイアログ内の入力欄 key には必ず**行id**を含める（固定keyだと別行の値が残り誤って別行へ書き込む＝2026-07-14の事故）。
- `flash(msg, section=master)` ＋ `show_flash(master)` の対で、操作したタブにだけ成功メッセージを出す。更新後は `st.rerun()`。
- `common/*.py` を変えたら **8502 を手動再起動**（起動batは health=ok なら既存サーバーを開くだけ）。
- 検証は実データを触らない：`POSTING_DB_PATH` に一時DB＋`store.init_db`／`store.seed_masters`（AppTest）。手動確認は実データDBのコピー＋別ポート8599。
- 配色は既存テーマ（`--primary:#14a4dc` 水色）を踏襲。新規CSSは `common/ui.py` の `_STYLE` に追記する。

---

### Task 1: 行の補助情報（薄字サブタイトル）の純関数

**Files:**
- Modify: `common/posting_logic.py`（末尾に関数追加）
- Test: `tests/test_posting_logic.py`（末尾にテスト追加）

**Interfaces:**
- Produces: `master_row_subtitle(master: str, row: dict) -> str`
  - `"distributor"` → `区分・支払形態`（空の要素は除き "・" で連結）
  - `"payables_vendor"` → `既定費目 / 原本区分`（空の要素は除き " / " で連結）
  - それ以外 → `""`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_posting_logic.py の末尾に追加
from common import posting_logic


def test_master_row_subtitle_distributor():
    row = {"kind": "業務委託", "pay_type": "歩合"}
    assert posting_logic.master_row_subtitle("distributor", row) == "業務委託・歩合"


def test_master_row_subtitle_distributor_partial():
    assert posting_logic.master_row_subtitle("distributor", {"kind": "自社社員", "pay_type": None}) == "自社社員"


def test_master_row_subtitle_vendor():
    row = {"default_category": "家賃", "default_original_status": "本社"}
    assert posting_logic.master_row_subtitle("payables_vendor", row) == "家賃 / 本社"


def test_master_row_subtitle_vendor_empty():
    assert posting_logic.master_row_subtitle("payables_vendor", {"default_category": None, "default_original_status": None}) == ""


def test_master_row_subtitle_other_master():
    assert posting_logic.master_row_subtitle("project", {"name": "A社チラシ"}) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_posting_logic.py -k subtitle -v`
Expected: FAIL（`AttributeError: module 'common.posting_logic' has no attribute 'master_row_subtitle'`）

- [ ] **Step 3: Write minimal implementation**

```python
# common/posting_logic.py の末尾に追加
def master_row_subtitle(master, row) -> str:
    """一覧の各行で名前の右に薄字で出す補助情報。中身が空なら空文字。
    業務委託=「区分・支払形態」、買掛先=「既定費目 / 原本区分」、他マスタは無し。"""
    if master == "distributor":
        parts = [p for p in [row.get("kind"), row.get("pay_type")] if p]
        return "・".join(parts)
    if master == "payables_vendor":
        parts = [p for p in [row.get("default_category"), row.get("default_original_status")] if p]
        return " / ".join(parts)
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_posting_logic.py -k subtitle -v`
Expected: PASS（5件）

- [ ] **Step 5: Commit**

```bash
git add common/posting_logic.py tests/test_posting_logic.py
git commit -m "feat: マスタ行の補助情報(薄字)を作る純関数 master_row_subtitle"
```

---

### Task 2: ステータストグル／削除アイコンのCSS（common/ui.py）

**Files:**
- Modify: `common/ui.py`（`_STYLE` 文字列の `</style>` 直前にCSSブロックを追記）
- Test: `tests/test_pages_smoke.py`（CSS文字列が入っていることと、ページが例外なく描画されることを見る軽いテスト）

**Interfaces:**
- Produces: CSSクラスの契約。行の中で
  - 運用中トグルは `st.container(key=f"mstat-on-{master}-{id}")` の中に置く → 水色の丸い光る（脈打つ）ボタン
  - 停止中トグルは `st.container(key=f"mstat-off-{master}-{id}")` の中に置く → グレーの丸いボタン
  - `st.container(key=...)` はDOMに `st-key-<key>` クラスを付ける。CSSは `[class*="st-key-mstat-on-"] ...` で全行の運用中ボタンをまとめてスコープする。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
from common import ui as _ui


def test_status_toggle_css_present():
    # 運用中の脈打ちアニメ・停止中のグレー・スコープ用クラスが CSS に入っている
    assert "mstatpulse" in _ui._STYLE
    assert "st-key-mstat-on-" in _ui._STYLE
    assert "st-key-mstat-off-" in _ui._STYLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py::test_status_toggle_css_present -v`
Expected: FAIL（`assert "mstatpulse" in ...` が False）

- [ ] **Step 3: Write minimal implementation**

`common/ui.py` の `_STYLE` 内、最後の `</style>` の直前に以下を追記する：

```css
/* ===== マスタ管理: ステータストグル（運用中=光る水色の丸 / 停止中=グレーの丸） ===== */
/* 行ごとの st.container(key="mstat-on-<master>-<id>") が付ける st-key-* で全行をまとめてスコープ */
[class*="st-key-mstat-on-"] .stButton>button{
  border-radius:999px !important; background:var(--primary) !important; color:#fff !important;
  border:none !important; font-weight:700 !important; padding:.35rem 1rem !important;
  animation:mstatpulse 1.7s infinite;
}
@keyframes mstatpulse{
  0%{ box-shadow:0 0 0 0 rgba(20,164,220,.55); }
  70%{ box-shadow:0 0 0 8px rgba(20,164,220,0); }
  100%{ box-shadow:0 0 0 0 rgba(20,164,220,0); }
}
[class*="st-key-mstat-off-"] .stButton>button{
  border-radius:999px !important; background:#eef1f4 !important; color:#8b98a6 !important;
  border:1px solid var(--line) !important; font-weight:700 !important; padding:.35rem 1rem !important;
  box-shadow:none !important;
}
[class*="st-key-mstat-off-"] .stButton>button:hover{ background:#e4e8ee !important; color:#67788a !important; }
/* 削除(ゴミ箱)は控えめなアイコンボタンに */
[class*="st-key-mtrash-"] .stButton>button{
  background:#fff !important; color:#c0392b !important; border:1px solid var(--line) !important;
  box-shadow:none !important; padding:.35rem .6rem !important;
}
[class*="st-key-mtrash-"] .stButton>button:hover{ background:#fdecea !important; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pages_smoke.py::test_status_toggle_css_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add common/ui.py tests/test_pages_smoke.py
git commit -m "style: マスタ管理のステータストグル(光る水色/停止中グレー)と削除アイコンのCSS"
```

---

### Task 3: 新規登録を別窓（st.dialog）にする（全5タブ）

**Files:**
- Modify: `pages/05_マスタ管理.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Produces: 各タブ上部に `st.button("＋ 新規登録", key=f"add_open_{master}")`。押すと `@st.dialog` の追加フォームが開く。ページ下部の旧 `st.form(add_*)` は全廃。

**方針:** `st.dialog` 関数は「呼ぶと開く」。ボタンが押されたら該当の dialog 関数を呼ぶ。dialog 内の「追加」で `add_*()` → `flash(..., master)` → `st.rerun()`（rerunでダイアログは閉じる）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
def test_each_tab_has_new_register_button(db):
    at = _run("05_マスタ管理.py")
    labels = [b.label for b in at.button]
    # 5タブぶんの「＋ 新規登録」ボタンが描画されている
    assert sum(1 for L in labels if "新規登録" in L) >= 5


def test_new_distributor_via_dialog(db):
    at = _run("05_マスタ管理.py")
    # 業務委託タブの新規登録を開く
    at.button(key="add_open_distributor").click().run()
    # ダイアログ内の氏名を入れて追加
    at.text_input(key="add_name_distributor").set_value("テスト太郎").run()
    at.button(key="add_submit_distributor").click().run()
    names = [r["name"] for r in store.list_distributors(db_path=db)]
    assert "テスト太郎" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pages_smoke.py -k "new_register or new_distributor" -v`
Expected: FAIL（`add_open_distributor` ボタンが無い）

- [ ] **Step 3: Write minimal implementation**

`pages/05_マスタ管理.py` に、追加フォームを開く共通部品と各マスタの dialog を用意し、各タブ本体で「旧・最下部の追加フォーム」を「上部の新規登録ボタン＋dialog呼び出し」に置き換える。

共通の「単純マスタ（案件・費目・売掛先）」用 dialog と、買掛先・業務委託の専用 dialog を定義する：

```python
@st.dialog("新規登録")
def _add_simple_dialog(label, master, add_fn):
    name = st.text_input(f"{label}名", key=f"add_name_{master}")
    c1, c2 = st.columns(2)
    if c1.button("追加", key=f"add_submit_{master}", type="primary"):
        if name.strip():
            add_fn(name.strip())
            flash(f"{label}を追加しました", master)
            st.rerun()
    if c2.button("やめる", key=f"add_cancel_{master}"):
        st.rerun()


@st.dialog("買掛先を新規登録")
def _add_vendor_dialog():
    master = "payables_vendor"
    n = st.text_input("取引先名", key="add_name_payables_vendor")
    c = st.text_input("既定の費目（家賃・電気 など）", key="add_cat_payables_vendor")
    o = st.selectbox("既定の原本区分", ["(なし)"] + _ORIGINAL_STATUSES, key="add_orig_payables_vendor")
    c1, c2 = st.columns(2)
    if c1.button("追加", key="add_submit_payables_vendor", type="primary"):
        if n.strip():
            store.add_payables_vendor(n.strip(), default_category=(c.strip() or None),
                                      default_original_status=(None if o == "(なし)" else o))
            flash("買掛先を追加しました", master)
            st.rerun()
    if c2.button("やめる", key="add_cancel_payables_vendor"):
        st.rerun()


@st.dialog("業務委託を新規登録")
def _add_distributor_dialog():
    master = "distributor"
    n = st.text_input("配布員 氏名", key="add_name_distributor")
    kind = st.selectbox("区分（雇用形態）", _KINDS, key="add_kind_distributor")
    pay_type = st.selectbox("支払形態（報酬の計算方法）", _PAY_TYPES, key="add_pay_distributor")
    bank = st.text_area("振込先", key="add_bank_distributor",
                        placeholder="例：三井住友銀行 梅田支店 普通 1234567 ヤマダ タロウ")
    h1, h2 = st.columns(2)
    hourly = h1.number_input("時給額", min_value=0, step=1, key="add_hourly_distributor")
    monthly = h2.number_input("月額", min_value=0, step=1, key="add_monthly_distributor")
    st.caption("時給額は支払形態が「時給」、月額は「月給」のときだけ使います。"
               "日当の金額は登録後、その人の「編集」から設定できます。")
    c1, c2 = st.columns(2)
    if c1.button("追加", key="add_submit_distributor", type="primary"):
        if n.strip():
            store.add_distributor(n.strip(), kind=kind, pay_type=pay_type,
                                  bank_info=(bank.strip() or None),
                                  hourly_rate=(int(hourly) or None),
                                  monthly_rate=(int(monthly) or None))
            flash("業務委託を追加しました", master)
            st.rerun()
    if c2.button("やめる", key="add_cancel_distributor"):
        st.rerun()
```

各タブ本体で、一覧の**上**に新規登録ボタンを置き、押されたら dialog を呼ぶ。旧・最下部の `st.form(add_*)` は削除する。`_simple_master()` を次のように変える（追加フォーム部分を差し替え）：

```python
def _simple_master(label, master, list_fn, add_fn, update_fn):
    show_flash(master)
    if st.button("＋ 新規登録", key=f"add_open_{master}"):
        _add_simple_dialog(label, master, add_fn)
    active, inactive = _split_active(list_fn())
    _rows_ui(master, active, update_fn=update_fn, label_name=label,
             fields_fn=_name_fields(master, label))
    _inactive_ui(master, inactive, update_fn=update_fn)   # ← Task 5 で廃止
```

買掛先タブ（tab3）は最下部の `with st.form("add_vendor", ...)` ブロックを削除し、`show_flash(master)` の直後に：

```python
    if st.button("＋ 新規登録", key="add_open_payables_vendor"):
        _add_vendor_dialog()
```

業務委託タブ（tab5）は最下部の `with st.form("add_dist", ...)` ブロックを削除し、`show_flash(master)` の直後に：

```python
    if st.button("＋ 新規登録", key="add_open_distributor"):
        _add_distributor_dialog()
```

> 注意: `_ORIGINAL_STATUSES` `_KINDS` `_PAY_TYPES` は既にファイル冒頭で定義済み。dialog 関数はそれらを参照するため、定義より後（=各 `_*_fields` の近く）に置くこと。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages_smoke.py -k "new_register or new_distributor or master_page" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pages/05_マスタ管理.py tests/test_pages_smoke.py
git commit -m "feat: マスタの新規登録を別窓(st.dialog)に。旧最下部フォームを廃止(全5タブ)"
```

---

### Task 4: 編集を別窓（st.dialog）にする＋業務委託の日当金額を編集窓に集約

**Files:**
- Modify: `pages/05_マスタ管理.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Produces: `_edit_dialog(master, row, *, update_fn, fields_fn, with_daily=False)` を `@st.dialog("編集")` で定義。行の `st.button("編集", key=f"edit_{master}_{id}")` で開く。旧 `_edit_ui`（インラインのフォーム）と、業務委託タブ最下部の「日当金額の設定」セクションは廃止。

**方針:** dialog 内は `st.form` を使わず素のウィジェット＋「更新／やめる」ボタン（`st.data_editor` を form 内に入れる不確実性を避ける）。業務委託で支払形態＝日当のときだけ、同じ窓に業務名×金額の `st.data_editor` を出し、更新時に `replace_daily_rates` で保存する。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
def test_edit_distributor_via_dialog(db):
    store.add_distributor("編集前", kind="業務委託", pay_type="歩合", db_path=db)
    at = _run("05_マスタ管理.py")
    rid = [r["id"] for r in store.list_distributors(db_path=db) if r["name"] == "編集前"][0]
    at.button(key=f"edit_distributor_{rid}").click().run()
    at.text_input(key=f"edit_name_distributor_{rid}").set_value("編集後").run()
    at.button(key=f"edit_submit_distributor_{rid}").click().run()
    names = [r["name"] for r in store.list_distributors(db_path=db)]
    assert "編集後" in names and "編集前" not in names


def test_no_bottom_daily_section_label(db):
    # 日当金額の設定は編集窓に移り、ページ下部の独立セクションは無い
    store.add_distributor("日当さん", kind="業務委託", pay_type="日当", db_path=db)
    at = _run("05_マスタ管理.py")
    text = _rendered_text(at)
    assert "日当金額の設定" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pages_smoke.py -k "edit_distributor_via_dialog or bottom_daily" -v`
Expected: FAIL（`edit_distributor_{rid}` のsubmit key が無い／"日当金額の設定" がまだ本文に出る）

- [ ] **Step 3: Write minimal implementation**

`_edit_dialog` を追加し、`_edit_ui`（インライン）を廃止して `_row_ui` から呼ぶ形に差し替える。業務委託タブ最下部の「日当金額の設定」ブロック（`st.divider()`〜`rate_save`）は削除する。

```python
@st.dialog("編集")
def _edit_dialog(master, row, *, update_fn, fields_fn, with_daily=False):
    st.markdown(f"**「{row['name']}」を編集**")
    kwargs = fields_fn(row)   # 素のウィジェット。key に行idを含む(既存 _*_fields のまま)
    edited_rates = None
    if with_daily and kwargs.get("pay_type") == "日当":
        st.markdown("**日当金額の設定**")
        rates = store.list_daily_rates(row["id"])
        base = pd.DataFrame(
            [{"業務名": r["work_name"], "金額": int(r["amount"])} for r in rates]
            or [{"業務名": "", "金額": 0}])
        edited_rates = st.data_editor(
            base, num_rows="dynamic", use_container_width=True,
            column_config={"金額": st.column_config.NumberColumn(min_value=0, step=1,
                                                                format="localized")},
            key=f"edit_rates_{row['id']}")
        st.caption("ここで登録した業務名と金額が、業務委託登録の明細で選べるようになります。")
    c1, c2 = st.columns(2)
    if c1.button("更新", key=f"edit_submit_{master}_{row['id']}", type="primary"):
        if str(kwargs.get("name") or "").strip():
            update_fn(row["id"], **kwargs)
            if edited_rates is not None:
                store.replace_daily_rates(row["id"], [
                    {"work_name": str(r["業務名"]), "amount": int(r["金額"] or 0)}
                    for _, r in edited_rates.iterrows() if str(r["業務名"] or "").strip()])
            flash("更新しました", master)
            st.rerun()
    if c2.button("やめる", key=f"edit_cancel_{master}_{row['id']}"):
        st.rerun()
```

`_row_ui` を、編集ボタンを押したら dialog を開く形に変える（`_edit_ui` の呼び出しを置換）：

```python
def _row_ui(master, row, *, update_fn, label_name, fields_fn, with_daily=False):
    c1, c2, c3 = st.columns([4, 1, 1])
    c1.write(row["name"])
    if c2.button("編集", key=f"edit_{master}_{row['id']}"):
        _edit_dialog(master, row, update_fn=update_fn, fields_fn=fields_fn, with_daily=with_daily)
    _remove_ui(master, row, label_name=label_name, update_fn=update_fn, button_container=c3)
```

業務委託タブ（tab5）の `_row_ui(...)` 呼び出しに `with_daily=True` を渡す。旧 `_edit_ui` / `_open_edit` / `_close_edit` / `_edit_slot` は使わなくなるので削除する。業務委託タブ最下部の「日当金額の設定」セクション（`st.divider()` 以降）も削除する。

> 注意: `_edit_dialog` は `pd` を使う。ファイル冒頭で `import pandas as pd` 済み。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages_smoke.py -k "edit_distributor_via_dialog or bottom_daily or master_page" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pages/05_マスタ管理.py tests/test_pages_smoke.py
git commit -m "feat: マスタ編集を別窓(st.dialog)に。業務委託の日当金額を編集窓へ集約"
```

---

### Task 5: ステータストグル＋停止中インライン表示＋未使用のみ削除＋補助情報／読み取り専用表・折りたたみ廃止

**Files:**
- Modify: `pages/05_マスタ管理.py`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: `posting_logic.master_row_subtitle`（Task 1）／CSSクラス `mstat-on-*` `mstat-off-*` `mtrash-*`（Task 2）／`_edit_dialog`（Task 4）。
- Produces: 行 `_row_ui` を「名前＋補助情報｜ステータストグル｜編集｜（未使用のみ）🗑」に再構成。有効・停止中を同じ一覧にインライン表示。買掛先・業務委託の `nice_table`（読み取り専用表）と `_inactive_ui`（停止中の折りたたみ）を廃止。

**方針:**
- 一覧は `list_fn()`（`only_active=False`＝停止中も含む）を取得順で全部出す（`_split_active` は使わない）。
- 各行のステータス列：
  - 運用中（`active`）→ `st.container(key=f"mstat-on-{master}-{id}")` の中で `confirm_delete(label="運用中", ...)` を呼ぶ（押す→確認→`update_fn(id, active=0)`／使用実績に応じた説明文）。
  - 停止中 → `st.container(key=f"mstat-off-{master}-{id}")` の中で `st.button("停止中")`（押す→`update_fn(id, active=1)`、確認なし）。
- 🗑 は `posting_logic.master_delete_action(count)=="delete"` の行だけ、`st.container(key=f"mtrash-{master}-{id}")` の中で `confirm_delete(label="🗑", ...)` を呼ぶ（物理削除）。使用中の行には出さない。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages_smoke.py の末尾に追加
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
    at = _run("05_マスタ管理.py")
    rid = [r["id"] for r in store.list_distributors(db_path=db) if r["name"] == "未使用さん"][0]
    keys = [b.key for b in at.button]
    assert f"del_distributor_{rid}_btn" in keys  # 未使用は🗑あり


def test_no_readonly_table_header(db):
    # 読み取り専用テーブルの見出し「配布員 氏名」等が本文に出ない（行リストに一本化）
    at = _run("05_マスタ管理.py")
    text = _rendered_text(at)
    assert "停止中（" not in text  # 折りたたみの見出しが無い
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pages_smoke.py -k "toggle_deactivates or inline_and_reactivates or trash_only or readonly_table" -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`_row_ui` をステータス列つきに作り替える。`_remove_ui` は🗑（物理削除）専用に整理し、停止中への切替はステータストグル側で行う。停止中への切替と有効化のための小さなヘルパを足す。

```python
def _status_ui(master, row, *, update_fn, container):
    """行のステータス列。運用中=光る水色トグル(確認あり→停止中)、停止中=グレー(→有効化)。"""
    with container:
        if row.get("active", 1):
            with st.container(key=f"mstat-on-{master}-{row['id']}"):
                n = store.count_master_usage(master, row["id"])
                detail = (f"「{row['name']}」を停止中にします。"
                          + (f"{n}件のデータで使用中のため、登録の選択肢から消えるだけで"
                             "一覧・報告書の表示は変わりません。" if n else
                             "登録の選択肢から外します（いつでも有効に戻せます）。"))
                confirm_delete(
                    key=f"deact_{master}_{row['id']}", label="運用中",
                    warning=f"⚠️「{row['name']}」を停止中にしますか？", detail=detail,
                    on_confirm=lambda: update_fn(row["id"], active=0),
                    success="停止中にしました", section=master)
        else:
            with st.container(key=f"mstat-off-{master}-{row['id']}"):
                if st.button("停止中", key=f"react_{master}_{row['id']}"):
                    update_fn(row["id"], active=1)
                    flash("有効に戻しました", master)
                    st.rerun()


def _trash_ui(master, row, *, container):
    """使用実績0件の行だけに出す物理削除(ゴミ箱)。使用中の行には呼ばない。"""
    with container:
        with st.container(key=f"mtrash-{master}-{row['id']}"):
            confirm_delete(
                key=f"del_{master}_{row['id']}", label="🗑",
                detail=f"「{row['name']}」を完全に削除します。使用実績はありません。",
                on_confirm=lambda: _delete_master(master, row["id"]),
                success="削除しました", section=master)


def _row_ui(master, row, *, update_fn, label_name, fields_fn, with_daily=False):
    """1行: 名前＋補助情報｜ステータス｜編集｜(未使用のみ)🗑。編集・確認は列の外＝全幅。"""
    sub = posting_logic.master_row_subtitle(master, row)
    c_name, c_status, c_edit, c_trash = st.columns([4, 2, 1, 1])
    with c_name:
        st.write(row["name"])
        if sub:
            st.caption(sub)
    _status_ui(master, row, update_fn=update_fn, container=c_status)
    if c_edit.button("編集", key=f"edit_{master}_{row['id']}"):
        _edit_dialog(master, row, update_fn=update_fn, fields_fn=fields_fn, with_daily=with_daily)
    if posting_logic.master_delete_action(store.count_master_usage(master, row["id"])) == "delete":
        _trash_ui(master, row, container=c_trash)
```

一覧の取得を「停止中も含めて全部・取得順」に変える。`_rows_ui` はそのまま（渡す行が全件になるだけ）。呼び出し側を修正：

`_simple_master`：
```python
def _simple_master(label, master, list_fn, add_fn, update_fn):
    show_flash(master)
    if st.button("＋ 新規登録", key=f"add_open_{master}"):
        _add_simple_dialog(label, master, add_fn)
    _rows_ui(master, list_fn(), update_fn=update_fn, label_name=label,
             fields_fn=_name_fields(master, label))
```

買掛先タブ（tab3）：`nice_table(...)` とその `st.caption`、`_split_active`、`_inactive_ui(...)` を削除し、全件を行リストに：
```python
with tab3:
    master = "payables_vendor"
    show_flash(master)
    if st.button("＋ 新規登録", key="add_open_payables_vendor"):
        _add_vendor_dialog()
    st.caption("既定の原本区分を入れておくと、買掛登録で取引先名が一致したときに自動で入ります。")
    for r in store.list_payables_vendors():
        _row_ui(master, r, update_fn=store.update_payables_vendor,
                label_name="買掛先", fields_fn=_vendor_fields)
```

業務委託タブ（tab5）：`nice_table(...)`、`_split_active`、`_inactive_ui(...)` を削除し、全件を行リストに（`with_daily=True`）：
```python
with tab5:
    master = "distributor"
    show_flash(master)
    if st.button("＋ 新規登録", key="add_open_distributor"):
        _add_distributor_dialog()
    for r in store.list_distributors():
        _row_ui(master, r, update_fn=store.update_distributor,
                label_name="業務委託", fields_fn=_distributor_fields, with_daily=True)
```

不要になった関数を削除：`_remove_ui`（旧・停止中/削除兼用）・`_split_active`・`_inactive_ui`。`_delete_master` と `_DELETE_FNS` は `_trash_ui` が使うので残す。

> 注意: `posting_logic` は既に import 済み（`from common import posting_logic`）。`nice_table` の import 行は他で使わなくなるが、残っていてもよい（未使用 import の削除は任意）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages_smoke.py -v`
Expected: PASS（既存スモーク＋新規すべて）

- [ ] **Step 5: Commit**

```bash
git add pages/05_マスタ管理.py tests/test_pages_smoke.py
git commit -m "feat: マスタ一覧にステータストグル・停止中インライン・未使用のみ削除。読取専用表と折りたたみを廃止"
```

---

### Task 6: 全テスト＋実機（8502）目視検証

**Files:**
- Test: 既存全体
- Modify: 必要なら微修正のみ

- [ ] **Step 1: 全テストを流す**

Run: `cd /c/Users/moro/posting-automation && python -m pytest -q`
Expected: 全パス（第3弾の202件＋今回追加分）。失敗があれば原因を直して再実行。

- [ ] **Step 2: 実データを汚さない検証用DBで8502相当を起動**

```bash
cd /c/Users/moro/posting-automation
cp data/posting.db /tmp/rev4_check.db 2>/dev/null || cp data/dashboard.db /tmp/rev4_check.db
POSTING_DB_PATH=/tmp/rev4_check.db DB_S3_BUCKET= streamlit run app.py --server.port 8599 --server.headless true
```
（`common/*.py` を変更しているため、既存8502は必ず一度停止してから起動する。db_sync は `DB_S3_BUCKET` 未設定で no-op。）

- [ ] **Step 3: マスタ管理を目視チェック（オーナー確認用の観点）**

- [ ] 全5タブに「＋ 新規登録」ボタンがあり、押すと**別窓**が開く／追加すると閉じてメッセージが出る
- [ ] 各行に**ステータス**が出る：運用中＝**水色の丸いボタンが脈打って光る**／停止中＝グレーの「停止中」
- [ ] 運用中をクリック→確認→停止中に変わる／停止中をクリック→有効に戻る
- [ ] **停止中の行も同じ一覧にインライン表示**（折りたたみが無い）
- [ ] 使用実績0件の行だけ🗑が出て、使用中の行には出ない
- [ ] 行の「編集」で**別窓**が開き更新できる／業務委託で支払形態＝日当のとき、同じ窓に**業務名×金額の表**が出て保存できる
- [ ] 買掛先・業務委託の上にあった読み取り専用テーブルが無くなり、行に一本化されている
- [ ] 既存データ（第3弾までの請求・号別明細）が壊れていない（号別明細を開いて金額・部数が従来どおり）

- [ ] **Step 4: 検証用DB後始末**

```bash
rm -f /tmp/rev4_check.db
```
実データDB（`data/`）が無傷であることを確認。

- [ ] **Step 5: オーナーへ実機確認を依頼**

第3弾＋第4弾をまとめて 8502 で確認 → OKなら第3弾を含めて master へ `git merge --no-ff`（第2弾と同じ手順）。

---

## Self-Review（この計画のチェック結果）

- **仕様網羅**: ①ステータス列＋トグル=Task2(CSS)+Task5 ②同じ行で編集=Task4 ③運用中=光る水色/停止中=表記=Task2+Task5 ④新規登録=別窓=Task3 ⑤停止中インライン(折りたたみ廃止)=Task5 ⑥未使用のみ削除(過去データ保護)=Task5 ⑦業務委託の日当を編集窓へ=Task4 ⑧補助情報の薄字=Task1+Task5。すべてタスクに対応あり。
- **プレースホルダ**: なし（各ステップに実コード・実コマンド・期待結果）。
- **型/名前の一貫性**: `master_row_subtitle`（Task1で定義→Task5で使用）、`_edit_dialog`（Task4定義→Task5使用）、CSSキー `mstat-on-/mstat-off-/mtrash-`（Task2定義→Task5でcontainer key一致）、ボタンkey `deact_/react_/del_/edit_/add_*`（テストと実装で一致）を確認。
- **スコープ**: マスタ管理1画面＋CSS＋純関数1つ。単一計画に収まる。
