# 小口カメラのボタン化 ＋ 原価売上まとめのタブ分け Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 小口ページを開いてもカメラが起動しないようにし（押したときだけ起動）、原価売上まとめの明細を「原価」「売上」の2タブに分ける。

**Architecture:** カメラは `st.camera_input` を「描画するかどうか」を `st.session_state` のフラグで切り替える（描画＝許可要求なので、描画を止めれば起動しない）。閉じたときは widget の key に含めた世代番号を上げて、前回の撮影データを引き継がせない。タブ分けは、区分→タブの対応を `common/posting_logic.py` に定数として置き、ページはそれを参照するだけにする。

**Tech Stack:** Python 3.11 / Streamlit / pytest / streamlit.testing.v1.AppTest

## Global Constraints

- 設計書: `docs/superpowers/specs/2026-08-07-camera-gate-and-summary-tabs-design.md`
- ブランチ: `feature/camera-and-summary-tabs`（`feature/demo-share` から分岐済み）
- 既存の全テストが緑のままであること。テスト実行は `python -m pytest -q`（リポジトリ直下）
- カメラは**小口モードのみ**。買掛・売掛には出さない（現行どおり）
- 06 の削除ボタンは**灰色のまま**（`delete_fn=None`）。集計元が消える事故を防ぐため
- 日本語を含む Python はターミナル経由で書かない（cp932 で化ける）。Write ツールで書く
- AppTest の癖: `camera_input` は `.key` が None なので `.id` で見る

---

### Task 1: 区分→タブの対応を posting_logic に定数として置く

**Files:**
- Modify: `common/posting_logic.py`（`company_summary_rows` の直前に定数を追加）
- Test: `tests/test_rev6_summary_logic.py`（末尾に追加）

**Interfaces:**
- Consumes: `company_summary_rows(...)`（既存・戻り値の各行は `{"区分","日付","項目","案件","金額"}`）
- Produces:
  - `posting_logic.SALES_KINDS: tuple[str, ...]` = `("売上",)`
  - `posting_logic.COST_KINDS: tuple[str, ...]` = `("買掛", "小口", "業務委託", "直接入力")`
  - `posting_logic.split_summary_rows(rows) -> tuple[list[dict], list[dict]]` — `(原価の行, 売上の行)` を返す

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_rev6_summary_logic.py` の末尾に追加：

```python
# ===== 原価/売上のタブ分け(2026-08-07) =====


def _all_kinds_rows():
    """company_summary_rows が返しうる区分を全種類ぶん作る。"""
    return posting_logic.company_summary_rows(
        receivables=[{"month": "2026-08", "client_id": 1, "amount": 1000}],
        payables=[{"date": "2026-08-01", "vendor_id": 1, "amount": 200}],
        petty=[{"date": "2026-08-02", "category_id": 1, "amount": 30}],
        contract_lines=[{"issue_date": "2026-08-03", "distributor_id": 1, "amount": 4}],
        manual=[{"work_date": "2026-08-04", "content": "直接", "amount": 5}],
        id2proj={}, id2vendor={1: "仕入先"}, id2cat={1: "駐車場代"},
        id2client={1: "得意先"}, id2dist={1: "配布員"})


def test_split_summary_rows_separates_cost_and_sales():
    cost, sales = posting_logic.split_summary_rows(_all_kinds_rows())
    assert [r["区分"] for r in sales] == ["売上"]
    assert set(r["区分"] for r in cost) == {"買掛", "小口", "業務委託", "直接入力"}


def test_split_summary_rows_loses_no_row():
    rows = _all_kinds_rows()
    cost, sales = posting_logic.split_summary_rows(rows)
    assert len(cost) + len(sales) == len(rows)


def test_every_kind_is_covered_by_a_tab():
    """🔴 取りこぼしゼロ。区分が増えたとき「どちらのタブにも出ない行」を防ぐ。"""
    kinds = {r["区分"] for r in _all_kinds_rows()}
    assert kinds <= set(posting_logic.SALES_KINDS) | set(posting_logic.COST_KINDS)


def test_sales_and_cost_kinds_do_not_overlap():
    assert not (set(posting_logic.SALES_KINDS) & set(posting_logic.COST_KINDS))


def test_split_summary_rows_totals_match_company_summary_totals():
    """タブの小計が KPI の数字と一致すること。"""
    receivables = [{"month": "2026-08", "client_id": 1, "amount": 1000}]
    payables = [{"date": "2026-08-01", "vendor_id": 1, "amount": 200}]
    petty = [{"date": "2026-08-02", "category_id": 1, "amount": 30}]
    contract_lines = [{"issue_date": "2026-08-03", "distributor_id": 1, "amount": 4}]
    manual = [{"work_date": "2026-08-04", "content": "直接", "amount": 5}]
    totals = posting_logic.company_summary_totals(
        receivables=receivables, payables=payables, petty=petty,
        contract_lines=contract_lines, manual=manual)
    rows = posting_logic.company_summary_rows(
        receivables=receivables, payables=payables, petty=petty,
        contract_lines=contract_lines, manual=manual,
        id2proj={}, id2vendor={1: "仕入先"}, id2cat={1: "駐車場代"},
        id2client={1: "得意先"}, id2dist={1: "配布員"})
    cost, sales = posting_logic.split_summary_rows(rows)
    assert sum(r["金額"] for r in sales) == totals["sales"]
    assert sum(r["金額"] for r in cost) == totals["cost"]
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_rev6_summary_logic.py -q -k "split_summary or every_kind or sales_and_cost"`
Expected: FAIL（`AttributeError: module 'common.posting_logic' has no attribute 'split_summary_rows'`）

- [ ] **Step 3: 最小の実装を書く**

`common/posting_logic.py` の `company_summary_rows` の定義の直前（現行 273 行目の直前）に追加：

```python
# 原価・売上まとめの明細をタブに振り分けるための区分。
# ページ側に if 区分 == "売上" と直接書くと、区分が増えたときに
# 「どちらのタブにも出ない行」が静かに生まれるため、ここに集約する。
# company_summary_rows が新しい区分を足したら、必ずどちらかに加えること
# (tests/test_rev6_summary_logic.py の test_every_kind_is_covered_by_a_tab が守る)。
SALES_KINDS = ("売上",)
COST_KINDS = ("買掛", "小口", "業務委託", "直接入力")


def split_summary_rows(rows):
    """明細行を (原価の行, 売上の行) に分ける。並び順は元のまま保つ。"""
    sales = [r for r in rows if r.get("区分") in SALES_KINDS]
    cost = [r for r in rows if r.get("区分") in COST_KINDS]
    return cost, sales
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_rev6_summary_logic.py -q`
Expected: PASS（全件）

- [ ] **Step 5: コミット**

```bash
git add common/posting_logic.py tests/test_rev6_summary_logic.py
git commit -m "feat(logic): 原価/売上の区分をSALES_KINDS/COST_KINDSに集約しsplit_summary_rowsを追加"
```

---

### Task 2: 原価売上まとめを2タブに分ける

**Files:**
- Modify: `pages/06_原価・売上まとめ.py:67-79`（`st.divider()` 以降の明細部分を丸ごと差し替え）
- Modify: `tests/test_pages_smoke.py:1623-1653`（既存3テストのキー名を新しいものに更新）
- Test: `tests/test_pages_smoke.py`（末尾に新規テストを追加）

**Interfaces:**
- Consumes: `posting_logic.split_summary_rows(rows)`（Task 1）、`selectable_list(rows, *, key, id_col)`、`list_action_bar(edited_df, *, key, title, filename, id_col, delete_fn, delete_note)`
- Produces: ボタン/チェックボックスの key が `summary_cost_*` と `summary_sales_*` の2系統になる

> 🔴 **既存テストが壊れる。** `tests/test_pages_smoke.py` の
> `test_summary_page_has_action_bar_with_delete_disabled` / `test_summary_page_delete_stays_disabled_even_when_all_selected` /
> `test_summary_page_old_section_export_is_gone` は `summary_print` `summary_bulk_del_btn` `summary_all` `summary_dl`
> を見ている。タブ分割でキーが変わるので、このタスクの中で更新する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pages_smoke.py` の末尾に追加：

```python
# ===== 原価/売上のタブ分け(2026-08-07) =====


def _summary_with_both(db):
    """売上1件・原価3件(買掛/小口/直接入力)を入れた 06 を描く。"""
    cid = store.add_receivables_client("得意先", db_path=db)
    store.add_receivable("2026-08", cid, 1000, db_path=db)
    vid = store.list_payables_vendors(db_path=db)[0]["id"]
    store.add_payable("2026-08-01", vid, 200, db_path=db)
    cat = store.list_expense_categories(db_path=db)[0]["id"]
    store.add_petty_cash("2026-08-02", cat, 30, db_path=db)
    pid = store.list_projects(db_path=db)[0]["id"]
    store.add_issue_manual_cost(pid, "配布", 5, work_date="2026-08-04", db_path=db)
    return _run("06_原価・売上まとめ.py")


def test_summary_page_has_cost_and_sales_tabs(db):
    at = _summary_with_both(db)
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert "原価" in labels and "売上" in labels


def test_summary_tabs_have_separate_action_bars(db):
    """🔴 タブごとに別の一覧＝キーが別系統であること(同じkeyだと状態が混線する)。"""
    at = _summary_with_both(db)
    keys = {b.key for b in at.button}
    assert "summary_cost_print" in keys
    assert "summary_sales_print" in keys
    assert "summary_cost_bulk_del_btn" in keys
    assert "summary_sales_bulk_del_btn" in keys


def test_summary_tabs_delete_is_disabled_on_both(db):
    """🔴 どちらのタブでも削除は押せないこと(集計元が消える事故をゼロに)。"""
    at = _summary_with_both(db)
    assert at.button(key="summary_cost_bulk_del_btn").disabled is True
    assert at.button(key="summary_sales_bulk_del_btn").disabled is True
    assert at.button(key="summary_cost_print").disabled is False


def test_summary_cost_tab_shows_no_sales_row(db):
    """🔴 原価タブに売上の行が1件も無いこと。

    ⚠️ Streamlit の tabs は1回の実行で全タブの中身が描かれるため、
    at 全体の文字列では分離を検証できない。data_editor の key で
    タブごとのデータフレームを取り出して見る。

    ⚠️ data_editor の key は `common/ui.py` の selectable_list が
    `f"{key}_select_{int(all_sel)}"` で作る。全選択していない初期状態は
    `_select_0`。`_editor` ではないので注意。"""
    at = _summary_with_both(db)
    frames = {e.key: e.value for e in at.get("data_editor") if e.key}
    cost = frames["summary_cost_select_0"]
    sales = frames["summary_sales_select_0"]
    assert "売上" not in set(cost["区分"])
    assert set(sales["区分"]) == {"売上"}


def test_summary_tabs_cover_every_row(db):
    """2つのタブの行数の合計＝明細の全行数。重複も欠落も無いこと。"""
    at = _summary_with_both(db)
    frames = {e.key: e.value for e in at.get("data_editor") if e.key}
    assert len(frames["summary_cost_select_0"]) == 3   # 買掛・小口・直接入力
    assert len(frames["summary_sales_select_0"]) == 1  # 売上
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "summary_page_has_cost_and_sales or summary_tabs"`
Expected: FAIL（タブが無いので `labels` が空、`summary_cost_print` が見つからない）

> `common/ui.py` の key 命名は確認済み（2026-08-07）:
> チェックボックス `{key}_all` ／ data_editor `{key}_select_{0|1}` ／
> 印刷 `{key}_print` ／ ダウンロード `{key}_dl` ／ 削除 `{key}_bulk_del_btn`。
> **`common/ui.py` は変更しない。**

- [ ] **Step 3: `pages/06_原価・売上まとめ.py` の明細部分を差し替える**

現行 67〜79 行目（`st.divider()` から最後まで）を、次で置き換える：

```python
st.divider()

cost_rows, sales_rows = posting_logic.split_summary_rows(rows)


def _render_tab(tab_rows, *, key, title, filename):
    """1つのタブの中身。件数と小計を出してから一覧を描く。

    集計を見るだけの画面なので、削除は灰色のまま(delete_fn=None)。
    ここから消しても 01・02 の元データは消えない。
    """
    st.caption(f"{len(tab_rows)}件 ／ 小計 {_yen(sum(r['金額'] for r in tab_rows))}")
    disp = sorted(tab_rows, key=lambda r: (r["日付"] == "", r["日付"]))
    disp = [{"日付": r["日付"], "区分": r["区分"], "項目": r["項目"],
             "案件": r["案件"], "金額": _yen(r["金額"])} for r in disp]
    edited, _ = selectable_list(disp, key=key, id_col=None)
    list_action_bar(edited, key=key, title=title, filename=filename, id_col=None,
                    delete_fn=None,
                    delete_note="この画面は集計を見るためのものです。"
                                "元のデータは『小口／買掛／売掛』『業務委託登録』から削除してください。")


tab_cost, tab_sales = st.tabs(["原価", "売上"])
with tab_cost:
    _render_tab(cost_rows, key="summary_cost", title="原価明細", filename="原価明細")
with tab_sales:
    _render_tab(sales_rows, key="summary_sales", title="売上明細", filename="売上明細")
```

- [ ] **Step 4: 既存3テストのキー名を更新する**

`tests/test_pages_smoke.py` の 1623〜1653 行目付近を、次のように書き換える：

```python
def test_summary_page_has_action_bar_with_delete_disabled(db):
    """🔴 06 まとめ。印刷・DLは使えるが、削除は押せないこと。
    ここの行は 01・02 のデータのコピーで、消しても元は消えないため。
    (2026-08-07 タブ分割でキーが summary_cost_* / summary_sales_* の2系統になった)"""
    cid = store.add_receivables_client("得意先", db_path=db)
    store.add_receivable("2026-08", cid, 1000, db_path=db)
    at = _run("06_原価・売上まとめ.py")
    assert not at.exception
    keys = {b.key for b in at.button}
    assert "summary_sales_print" in keys
    assert "summary_sales_bulk_del_btn" in keys
    assert at.button(key="summary_sales_bulk_del_btn").disabled is True


def test_summary_page_delete_stays_disabled_even_when_all_selected(db):
    """🔴 全選択しても削除は押せないままであること(集計元が消える事故をゼロにする)。"""
    cid = store.add_receivables_client("得意先", db_path=db)
    store.add_receivable("2026-08", cid, 1000, db_path=db)
    at = _run("06_原価・売上まとめ.py")
    at.checkbox(key="summary_sales_all").check().run()
    assert not at.exception
    assert at.button(key="summary_sales_bulk_del_btn").disabled is True
    assert at.button(key="summary_sales_print").disabled is False


def test_summary_page_old_section_export_is_gone(db):
    cid = store.add_receivables_client("得意先", db_path=db)
    store.add_receivable("2026-08", cid, 1000, db_path=db)
    at = _run("06_原価・売上まとめ.py")
    ids = [b.id for b in at.get("download_button")]
    assert not any("summary_xlsx" in i for i in ids)
    assert any("summary_sales_dl" in i for i in ids)
```

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "summary"`
Expected: PASS（全件）

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: 既存のテストも含めて全件 PASS

- [ ] **Step 7: コミット**

```bash
git add pages/06_原価・売上まとめ.py tests/test_pages_smoke.py
git commit -m "feat(06): 原価売上まとめの明細を原価/売上の2タブに分ける"
```

---

### Task 3: 小口のカメラをボタン式にする

**Files:**
- Modify: `pages/01_経費・買掛・売掛.py:119-133`（`st.camera_input` の描画部分）
- Modify: `tests/test_pages_smoke.py:1732-1738`（`test_petty_registration_has_camera_input` を置き換え）

**Interfaces:**
- Consumes: `ocr.media_type_for_upload(upload)`、`_ocr_files(files, reader, media_type=None)`（どちらも既存・変更しない）
- Produces: `st.session_state["petty_camera_on"]: bool`、`st.session_state["petty_camera_gen"]: int`、カメラ widget の key は `petty_camera_{gen}`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pages_smoke.py` の `test_petty_registration_has_camera_input`（1732〜1738 行目）を
**丸ごと次で置き換える**：

```python
def test_petty_camera_is_not_started_on_page_load(db):
    """🔴 ページを開いただけではカメラを起動しないこと。

    st.camera_input は「描画された時点で」ブラウザにカメラ許可を要求する。
    PC で小口を開くと内カメラが点きっぱなしになるため、描画自体をボタンで出し分ける。
    ⚠️ camera_input ノードは .key が None を返すため .id で見る。"""
    at = _run(_EXPENSE_PAGE)
    assert not at.exception
    assert at.get("camera_input") == []
    assert any(b.key == "petty_camera_open" for b in at.button)


def test_petty_camera_appears_after_pressing_open(db):
    at = _run(_EXPENSE_PAGE)
    at.button(key="petty_camera_open").click().run()
    assert not at.exception
    ids = [c.id for c in at.get("camera_input")]
    assert any("petty_camera" in i for i in ids)


def test_petty_camera_disappears_after_pressing_close(db):
    at = _run(_EXPENSE_PAGE)
    at.button(key="petty_camera_open").click().run()
    at.button(key="petty_camera_close").click().run()
    assert not at.exception
    assert at.get("camera_input") == []


def test_petty_camera_key_changes_after_close(db):
    """🔴 閉じて開き直したら widget の key が変わること。

    同じ key のままだと前回の写真が残り、撮り直したつもりで
    「古い写真を読み取る」事故になる。"""
    at = _run(_EXPENSE_PAGE)
    at.button(key="petty_camera_open").click().run()
    first = [c.id for c in at.get("camera_input")]
    at.button(key="petty_camera_close").click().run()
    at.button(key="petty_camera_open").click().run()
    second = [c.id for c in at.get("camera_input")]
    assert first and second
    assert first != second


def test_camera_is_not_shown_in_payable_mode(db):
    """買掛にはカメラを出さない(現行の挙動を壊していないこと)。"""
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.run()
    at.segmented_control[0].set_value("買掛").run()
    assert not at.exception
    assert at.get("camera_input") == []
    assert not any(b.key == "petty_camera_open" for b in at.button)
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "petty_camera or camera_is_not_shown"`
Expected: FAIL（`test_petty_camera_is_not_started_on_page_load` が
「カメラが存在する」ため落ち、`petty_camera_open` ボタンも見つからない）

- [ ] **Step 3: `pages/01_経費・買掛・売掛.py` の 119〜133 行目を差し替える**

現行の

```python
        # スマホからその場で撮って登録できるようにする(社内Wi-Fiで 8502 を開いた場合)
        shot = st.camera_input("その場で撮る（スマホ向け）", key="petty_camera")
        if shot is not None and st.button("撮った写真をAIで読み取る", key="petty_camera_ocr"):
```

から `st.session_state["petty_bulk"] = drafts` までを、次で置き換える：

```python
        # カメラは「描画した時点で」ブラウザに許可を要求する。ページを開いただけで
        # 内カメラが点くのを避けるため、描画自体をボタンで出し分ける(PC・スマホ共通)。
        st.session_state.setdefault("petty_camera_on", False)
        st.session_state.setdefault("petty_camera_gen", 0)

        if not st.session_state["petty_camera_on"]:
            if st.button("📷 カメラを起動", key="petty_camera_open"):
                st.session_state["petty_camera_on"] = True
                st.rerun()
        else:
            # 閉じるたびに gen を上げて key を変える。同じ key のままだと前回の写真が
            # 残り、撮り直したつもりで古い写真を読み取ってしまう。
            shot = st.camera_input("その場で撮る",
                                   key=f"petty_camera_{st.session_state['petty_camera_gen']}")
            c_ocr, c_close = st.columns(2)
            if shot is not None and c_ocr.button("撮った写真をAIで読み取る",
                                                 key="petty_camera_ocr"):
                # camera_input はファイル名から拡張子を取れず、実体がPNGのこともある。
                # 撮影データ自身が持つ type を優先して決める(嘘のMIMEで送らないため)。
                drafts = _ocr_files([shot], ocr.extract_receipt,
                                    media_type=ocr.media_type_for_upload(shot))
                st.session_state.pop("petty_draft", None)
                st.session_state.pop("petty_bulk", None)
                if len(drafts) == 1 and drafts[0].get("amount"):
                    st.session_state["petty_draft"] = {"date": drafts[0].get("date"),
                                                       "amount": drafts[0].get("amount"),
                                                       "item": drafts[0].get("item")}
                else:
                    st.session_state["petty_bulk"] = drafts
            if c_close.button("カメラを閉じる", key="petty_camera_close"):
                st.session_state["petty_camera_on"] = False
                st.session_state["petty_camera_gen"] += 1
                st.rerun()
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "petty_camera or camera_is_not_shown"`
Expected: PASS（5件）

- [ ] **Step 5: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: 全件 PASS

- [ ] **Step 6: コミット**

```bash
git add pages/01_経費・買掛・売掛.py tests/test_pages_smoke.py
git commit -m "feat(01): カメラをボタンを押したときだけ起動する(閉じたら撮影データも捨てる)"
```

---

### Task 4: ミューテーションテスト（検出力の確認）

**Files:**
- 一時的に変更して元に戻す: `common/posting_logic.py`、`pages/01_経費・買掛・売掛.py`、`pages/06_原価・売上まとめ.py`

「全項目 OK」は、**わざと壊して検知できるまで信用しない**。
各ミューテーションは `git stash` か手で元に戻す。**1つずつ行い、必ず元に戻してから次へ進む。**

- [ ] **Step 1: カメラを無条件描画に戻す**

`pages/01_経費・買掛・売掛.py` の `if not st.session_state["petty_camera_on"]:` を
`if False:` に変え、`else:` の中身が常に走るようにする。

Run: `python -m pytest tests/test_pages_smoke.py -q -k "petty_camera_is_not_started"`
Expected: **FAIL**（落ちなければテストが無意味＝テストを直す）
→ 元に戻す。

- [ ] **Step 2: 閉じても gen を増やさない**

`st.session_state["petty_camera_gen"] += 1` を削除する。

Run: `python -m pytest tests/test_pages_smoke.py -q -k "petty_camera_key_changes_after_close"`
Expected: **FAIL**
→ 元に戻す。

- [ ] **Step 3: 原価タブのフィルタを全件にする**

`common/posting_logic.py` の `split_summary_rows` を
`cost = list(rows)` に変える。

Run: `python -m pytest -q -k "summary"`
Expected: **FAIL**（`test_split_summary_rows_loses_no_row`・
`test_summary_cost_tab_shows_no_sales_row`・`test_summary_tabs_cover_every_row`・
`test_split_summary_rows_totals_match_company_summary_totals` が落ちる）
→ 元に戻す。

- [ ] **Step 4: COST_KINDS から「直接入力」を抜く**

`COST_KINDS = ("買掛", "小口", "業務委託")` にする。

Run: `python -m pytest -q -k "every_kind or loses_no_row or cover_every_row or totals_match"`
Expected: **FAIL**
→ 元に戻す。

- [ ] **Step 5: 元に戻ったことを確認して全テスト**

Run: `git diff --stat`
Expected: 出力が空（ミューテーションが残っていない）

Run: `python -m pytest -q`
Expected: 全件 PASS

- [ ] **Step 6: 結果を記録してコミット**

`docs/superpowers/plans/2026-08-07-camera-gate-and-summary-tabs.md` の
このタスクの各ステップにチェックを入れ、ミューテーション4件すべてが
期待どおり FAIL したことを追記する。

```bash
git add docs/superpowers/plans/2026-08-07-camera-gate-and-summary-tabs.md
git commit -m "docs(plan): ミューテーションテスト4件の結果を記録"
```

---

## 実行結果（2026-08-07）

### ミューテーションテストの結果：4件すべて期待どおり FAIL

| # | 壊し方 | 落ちたテスト | 判定 |
|---|---|---|---|
| 1 | カメラを常時描画に戻す（`if False:`） | `test_petty_camera_is_not_started_on_page_load` | ✅ 検知 |
| 2 | 閉じても `petty_camera_gen` を増やさない | `test_petty_camera_key_changes_after_close` | ✅ 検知 |
| 3 | `split_summary_rows` の原価を全件にする | 7件（ページ3件・ロジック4件） | ✅ 検知 |
| 4 | `COST_KINDS` から「直接入力」を抜く | 6件（`test_every_kind_is_covered_by_a_tab` を含む） | ✅ 検知 |

> 🔴 **ミューテーション1は最初 `if True:` で書いて空振りした。**
> それだと「起動ボタン側」が常に出るだけでカメラは描画されず、狙った退行になっていなかった。
> `if False:` に直して初めて検知できた。**ミューテーション自体が正しく壊せているかを確かめること。**

### 実装中に分かったこと（計画になかったもの）

1. **`st.data_editor` は `at.get("data_editor")` では取れず `at.dataframe` に出る。**
   計画のテストは前者で書いていて空振りした。
2. **`selectable_list` は行が0件だと一覧もアクションバーも描かない。**
   片方のタブが0件だと真っ白になるため、件数・小計のキャプションを必ず先に出し、
   `test_summary_empty_tab_still_shows_zero_caption` で固定した。
3. **既存の `test_petty_registration_saves_distributor` が `at.button[0]` で押していた。**
   カメラ起動ボタンが先頭に来て登録ボタンを押せなくなった。ラベルで選ぶよう修正。
   位置指定のボタン操作はこの1箇所だけだった。

## 完了の定義

- [x] `python -m pytest -q` が全件 PASS → **385件 PASS**（従来369＋新規16）
- [x] ミューテーション4件すべてが期待どおり FAIL した
- [ ] 小口ページを開いてもカメラが起動しない（PC の実機で目視）← **オーナー確認待ち**
- [ ] 原価・売上まとめに「原価」「売上」のタブが出て、区分が混ざらない（目視）← **オーナー確認待ち**
