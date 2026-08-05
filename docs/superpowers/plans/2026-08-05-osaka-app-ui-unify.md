# 大阪支社アプリ 一覧UI統一・報告書印刷・スマホ対応 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 業務完了報告書のA4印刷でG列が切れる不具合を直し、全ページの一覧操作（選択→印刷・ダウンロード・削除）を共通部品2つに統一し、スマホから小口レシートを登録できるようにする。

**Architecture:** `common/ui.py` に `selectable_list`（すべて選択＋チェック列付き一覧）と `list_action_bar`（印刷・DL・削除を同じ並びで出す）の2部品を新設し、既存の4部品（`section_export` / `checkbox_list_editor` / `selected_rows_excel_button` / `bulk_delete_action`）を吸収して撤去する。印刷は選択行だけのHTMLを描画し `@media print` で他を隠してブラウザ印刷する。金額合計の算出など純ロジックは `common/posting_logic.py` に置いてテストしやすくする。

**Tech Stack:** Python 3.11 / Streamlit 1.58 / pandas / openpyxl / pytest + `streamlit.testing.v1.AppTest`

**設計書:** `docs/superpowers/specs/2026-08-05-osaka-app-ui-unify-design.md`

## Global Constraints

- リポジトリ: `C:\Users\moro\posting-automation`。作業ブランチ **`feature/ui-unify-2026-08`**（既に作成済み・設計書コミット `4b65632`）。
- **ベースラインは全317テスト緑**（2026-08-05に実測）。各タスクの最後で `python -m pytest -q` を通し、317＋新規分が緑であること。
- **日本語をターミナルに直接書かない。** cp932 で文字化けする。長い日本語を含むファイル生成・追記は必ず `.py` に書いてから実行し、確認は Read ツールで行う。Bashヒアドキュメント内でバッククォートを使わない。
- **`.company/` 配下は触らない。** 記録は別途行う。
- **`data/posting.db`（本番DB）を触らない。** テストは `POSTING_DB_PATH` を一時DBに向ける既存 fixture（`tests/test_pages_smoke.py` の `db`）を使う。
- **実機確認・master へのマージはこの計画の範囲外**（オーナー不在のため。戻られてから実施）。
- 既存のコメント文体（なぜそうしたかを日本語で書く）に合わせる。
- 出力するxlsxのバイト列は `freeze_xlsx_bytes` で固定する規約を崩さない（ダウンロードURLが毎回変わると404になるため）。

---

## File Structure

| ファイル | 役割 | 変更 |
|---|---|---|
| `common/invoice_excel.py` | 業務完了報告書の生成 | 印刷設定を追加（Task 1） |
| `common/posting_logic.py` | 純ロジック（UI非依存） | `print_total()` を追加（Task 4） |
| `common/ui.py` | 共通UI部品・スタイル | `selectable_list` / `list_action_bar` / 印刷ビュー / print・mobile CSS を追加、旧4部品を撤去（Task 2,3,4,8,10,12） |
| `pages/01_経費・買掛・売掛.py` | 小口・買掛・売掛 | 共通部品へ載せ替え・segmented_control・カメラ（Task 5,9,12） |
| `pages/02_業務委託登録.py` | 業務委託 | 共通部品へ載せ替え・ZIPは遅延生成（Task 6） |
| `pages/03_号別明細.py` | 号別明細 | 共通部品へ載せ替え（削除無効）（Task 7） |
| `pages/06_原価・売上まとめ.py` | まとめ | 共通部品へ載せ替え（削除無効）（Task 7） |
| `pages/07_資料作成・変換表.py` | 資料作成 | segmented_control（Task 9） |
| `起動_大阪支社アプリ.bat` | 起動ランチャー | LAN公開（Task 11） |
| `tests/test_invoice_excel.py` | 報告書のテスト | 印刷設定のテスト追加（Task 1） |
| `tests/test_ui_list_actions.py` | **新規** 共通部品のテスト | Task 2,3,4 |
| `tests/test_pages_smoke.py` | 画面スモーク | キー変更・radio→segmented_control に追随（Task 5,6,7,9） |
| `tests/test_rev6_confirm.py` | 買掛・売掛の確認 | radio→segmented_control に追随（Task 9） |
| `tests/test_pages_atehagi_ui.py` | あて紙UI | radio→segmented_control に追随（Task 9） |

---

### Task 1: 業務完了報告書の印刷範囲を直す（依頼①）

**Files:**
- Modify: `common/invoice_excel.py`
- Test: `tests/test_invoice_excel.py`

**Interfaces:**
- Consumes: なし（このタスクが最初）
- Produces: `invoice_excel.build_invoice_xlsx(...)` の戻り値xlsxが `print_area="A1:G27"` と `page_setup.fitToWidth == 1` を持つ。他タスクはこれに依存しない。

**背景（実物で確認済み）:** テンプレートの `print_area` が `'Sheet1'!$A$1:$F$27` で、備考のG列が印刷範囲の外にある。幅不足ではない（A〜G合計 約99.6文字幅 ≒ A4縦の使用可能幅とほぼ同じで、縮小85%もかかる）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_invoice_excel.py` の末尾に追記する。

```python
def test_build_invoice_print_area_includes_bikou_column():
    """🔴 依頼①。備考(G列)が印刷範囲に入っていること。

    テンプレートの print_area は 'Sheet1'!$A$1:$F$27 で、G列が印刷範囲の外にあった。
    そのためA4印刷すると備考だけ紙に載らない(幅不足ではない)。
    """
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="時野", issue_date="2026-08-05",
        period_from="2026-08-01", period_to="2026-08-04",
        lines=[{"project_name": "案件A", "report_qty": 100, "unit_price": 4,
                "amount": 400, "remark": "配布"}])
    ws = _load(data)
    assert ws.print_area == "'Sheet1'!$A$1:$G$27"


def test_build_invoice_fits_to_one_page_wide():
    """横は必ず1ページに収める。列を増やしても切れないようにするため。"""
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="時野", issue_date="2026-08-05",
        period_from="", period_to="",
        lines=[{"project_name": "案件A", "report_qty": 100, "unit_price": 4,
                "amount": 400, "remark": "配布"}])
    ws = _load(data)
    assert ws.page_setup.fitToWidth == 1
    assert ws.sheet_properties.pageSetUpPr.fitToPage is True


def test_build_invoice_all_written_bikou_rows_are_inside_print_area():
    """🔴 列だけでなく行も見る。備考を書いた明細行が全部 print_area の内側にあること。
    明細は13〜18行なので、print_area の下端が12行などに退行したら落ちる。"""
    lines = [{"project_name": f"案件{i}", "report_qty": 1, "unit_price": 1,
              "amount": 1, "remark": "配布"} for i in range(6)]
    data = invoice_excel.build_invoice_xlsx(
        distributor_name="時野", issue_date="2026-08-05",
        period_from="", period_to="", lines=lines)
    ws = _load(data)

    from openpyxl.utils.cell import range_boundaries
    min_col, min_row, max_col, max_row = range_boundaries(
        ws.print_area.split("!")[-1].replace("$", ""))

    written = [(c, r) for r in range(1, ws.max_row + 1)
               for c in range(1, ws.max_column + 1)
               if ws.cell(r, c).value not in (None, "", " ", "\u3000")]
    assert written, "セルに何も書かれていない＝テストが空振りしている"
    outside = [(c, r) for c, r in written
               if not (min_col <= c <= max_col and min_row <= r <= max_row)]
    assert outside == [], f"印刷範囲の外に中身がある: {outside}"
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_invoice_excel.py -q -k "print_area or fits_to_one_page or inside_print_area"`
Expected: FAIL 3件。`assert "'Sheet1'!$A$1:$F$27" == "'Sheet1'!$A$1:$G$27"` および `assert None == 1`。

- [ ] **Step 3: 実装する**

`common/invoice_excel.py` の import に追加:

```python
from openpyxl.worksheet.properties import PageSetupProperties
```

`build_invoice_xlsx` の中、`wb.properties.created = _FIXED_DT` の直前に追加:

```python
    # 🔴 テンプレートの印刷範囲は A1:F27 で、備考(G列)が範囲の外にあった。
    # そのままA4印刷すると備考だけ紙に載らない(幅不足ではない)。
    # ここで毎回設定し直すことで、テンプレートを差し替えても効くようにする。
    # fitToWidth=1 にすると横は必ず1ページに収まる(このとき page_setup.scale は無視される)。
    ws.print_area = "A1:G27"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0     # 縦は成り行き(明細が増えても縮めすぎない)
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_invoice_excel.py -q`
Expected: 全て PASS（既存の決定性テスト `test_build_invoice_is_deterministic` も緑のまま）。

- [ ] **Step 5: ミューテーションで検出力を確認**

`print_area` を `"A1:F27"` に戻して Run: `python -m pytest tests/test_invoice_excel.py -q -k "print_area or inside_print_area"`
Expected: **FAIL**（落ちなければテストが空振りしている）。

続いて `ws.page_setup.fitToWidth = 1` の行をコメントアウトして Run: `python -m pytest tests/test_invoice_excel.py -q -k fits_to_one_page`
Expected: **FAIL**。

確認したら両方とも元に戻し、Run: `python -m pytest tests/test_invoice_excel.py -q` → 全PASS。

- [ ] **Step 6: 生成物を実ファイルで目視できる形にする**

Run:
```
python -c "from common import invoice_excel; open('C:/Users/moro/AppData/Local/Temp/claude/C--Users-moro/d5af685c-3763-483b-b5bc-8044029222e3/scratchpad/invoice_check.xlsx','wb').write(invoice_excel.build_invoice_xlsx(distributor_name='確認用',issue_date='2026-08-05',period_from='2026-08-01',period_to='2026-08-04',lines=[{'project_name':'案件A','report_qty':100,'unit_price':4,'amount':400,'remark':'配布'}]))"
```
Expected: エラーなく完了。このファイルはオーナーが戻られてから Excel の印刷プレビューで確認する（`fitToHeight=0` の解釈が Excel のバージョンで揺れる可能性があるため）。パスを実行ログに残す。

- [ ] **Step 7: コミット**

```bash
git add common/invoice_excel.py tests/test_invoice_excel.py
git commit -m "fix(invoice): 業務完了報告書の印刷範囲にG列(備考)を含める

テンプレートの print_area が A1:F27 で、備考のG列が印刷範囲の外にあった。
A4印刷で備考だけ紙に載らない原因。幅不足ではない(A-G合計 約99.6文字幅で
A4縦の使用可能幅に収まる)。テンプレートのxlsxではなく生成コード側で毎回
設定し、テストで固定する。fitToWidth=1 で今後列が増えても切れない。"
```

---

### Task 2: `selectable_list`（すべて選択＋チェック列付き一覧）

**Files:**
- Modify: `common/ui.py`
- Create: `tests/test_ui_list_actions.py`

**Interfaces:**
- Consumes: `posting_logic.selected_ids_from_editor(edited_df, *, id_col="No.", select_col="選択") -> list[int]`（既存）
- Produces:
  - `ui.selectable_list(rows, *, key, select_col="選択", id_col="No.") -> tuple[pandas.DataFrame, list[int]]`
  - ウィジェットkey: 全選択チェック `f"{key}_all"`、data_editor `f"{key}_select_{0 or 1}"`（0=通常 / 1=全選択中）
  - 空リストを渡すと `(空のDataFrame, [])` を返し、キャプションだけ出す

- [ ] **Step 1: 失敗するテストを書く**

新規ファイル `tests/test_ui_list_actions.py`:

```python
"""一覧の共通操作部品(selectable_list / list_action_bar)のテスト。
実DBに触れないよう、AppTest.from_function で部品だけを描画して見る。"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

_ROWS = [
    {"No.": 11, "日付": "2026-08-01", "費目": "消耗品", "金額": "¥3,200"},
    {"No.": 12, "日付": "2026-08-02", "費目": "交通費", "金額": "¥980"},
    {"No.": 13, "日付": "2026-08-03", "費目": "雑費", "金額": "¥1,500"},
]


def _list_page():
    import streamlit as st  # noqa: F401
    from common import ui

    edited, ids = ui.selectable_list(_ROWS, key="t")
    st.session_state["_ids"] = ids


def test_selectable_list_starts_with_nothing_selected():
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state["_ids"] == []


def test_selectable_list_has_select_all_checkbox():
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    assert "t_all" in {c.key for c in at.checkbox}


def test_selectable_list_select_all_selects_every_row():
    """🔴 「すべて選択」を押すと全行のidが返ること。"""
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    assert not at.exception
    assert at.session_state["_ids"] == [11, 12, 13]


def test_selectable_list_unselect_all_clears_selection():
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.checkbox(key="t_all").uncheck().run()
    assert at.session_state["_ids"] == []


def test_selectable_list_individual_checkbox_selects_one_row():
    """チェック列で1行だけ選べること(data_editorの状態を直接セットして再現)。"""
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    at.session_state["t_select_0"] = {
        "edited_rows": {1: {"選択": True}}, "added_rows": [], "deleted_rows": []}
    at.run()
    assert at.session_state["_ids"] == [12]


def test_selectable_list_editor_key_changes_with_select_all():
    """🔴 全選択の反映は data_editor の key を切り替えて再初期化することで行う。
    key が固定だと、前回の編集状態が残って「すべて選択」が効かない。"""
    at = AppTest.from_function(_list_page, default_timeout=30)
    at.run()
    assert "t_select_0" in at.session_state
    at.checkbox(key="t_all").check().run()
    assert "t_select_1" in at.session_state


def test_selectable_list_without_id_column_returns_empty_ids():
    """03・06の集計行はid列を持たない。id_col=None で呼べて、選択idは空になる。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"日付": "2026-08-01", "区分": "原価", "金額": "¥100"}]
        edited, ids = ui.selectable_list(rows, key="n", id_col=None)
        st.session_state["_ids"] = ids
        st.session_state["_cols"] = list(edited.columns)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="n_all").check().run()
    assert not at.exception
    assert at.session_state["_ids"] == []
    assert at.session_state["_cols"][0] == "選択"


def test_selectable_list_empty_rows_does_not_crash():
    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        edited, ids = ui.selectable_list([], key="e")
        st.session_state["_ids"] = ids
        st.session_state["_empty"] = bool(edited.empty)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state["_ids"] == []
    assert at.session_state["_empty"] is True
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q`
Expected: FAIL（`AttributeError: module 'common.ui' has no attribute 'selectable_list'`）。

- [ ] **Step 3: 実装する**

`common/ui.py` の `checkbox_list_editor` の直後に追加（`checkbox_list_editor` はTask 8まで残す）:

```python
def selectable_list(rows, *, key, select_col="選択", id_col="No."):
    """「すべて選択」チェック＋チェック列付きの一覧を描いて (編集後DataFrame, 選択id) を返す。

    全ページの一覧をこの1つに揃えるための部品。`list_action_bar` と対で使う。

    id_col=None は「id列を持たない一覧」(03 号別明細・06 まとめの集計行)。
    このとき選択idは常に空リストになる。印刷とダウンロードは選択列だけ見れば足り、
    idが要るのは削除だけなので、削除を出さない画面では問題にならない。

    全選択の反映は data_editor の key を切り替えて再初期化することで行う。
    Streamlit の data_editor は外から選択状態を書き換えるのが不安定なため、
    「チェックボックスを表より前に置き、その値で選択列の初期値を決める」形にしている。
    同じ key の中では個別編集が保持されるので、全選択してから数件だけ外せる。
    """
    import pandas as pd

    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df is None or df.empty:
        st.caption("表示できる行がありません。")
        return pd.DataFrame(), []

    all_sel = bool(st.checkbox("すべて選択", key=f"{key}_all"))
    df = df.copy()
    df[select_col] = all_sel
    df = df[[select_col] + [c for c in df.columns if c != select_col]]
    other = [c for c in df.columns if c != select_col]

    edited = st.data_editor(
        df, hide_index=True, use_container_width=True,
        column_config={select_col: st.column_config.CheckboxColumn(select_col, default=False)},
        disabled=other, key=f"{key}_select_{int(all_sel)}")

    ids = ([] if id_col is None
           else posting_logic_selected_ids(edited, id_col=id_col, select_col=select_col))
    n = sum(1 for _, r in edited.iterrows() if r.get(select_col))
    st.caption(f"選択中：{n}件")
    return edited, ids


def posting_logic_selected_ids(edited, *, id_col, select_col):
    """posting_logic への依存を関数内 import に閉じ込めるための薄い包み
    (common/ui.py はモジュール先頭で posting_logic を import していないため)。"""
    from common import posting_logic

    return posting_logic.selected_ids_from_editor(edited, id_col=id_col, select_col=select_col)
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q`
Expected: 8 passed。

- [ ] **Step 5: ミューテーションで検出力を確認**

`key=f"{key}_select_{int(all_sel)}"` を `key=f"{key}_select"`（固定）に変えて Run: `python -m pytest tests/test_ui_list_actions.py -q`
Expected: **FAIL**（`test_selectable_list_editor_key_changes_with_select_all` と `test_selectable_list_select_all_selects_every_row` が落ちる）。元に戻す。

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `325 passed`（317 + 新規8）。

- [ ] **Step 7: コミット**

```bash
git add common/ui.py tests/test_ui_list_actions.py
git commit -m "feat(ui): すべて選択つきの共通一覧 selectable_list を追加

全ページの一覧を同じ形に揃えるための土台。全選択は data_editor の key を
切り替えて再初期化する(外から選択状態を書き換えるのは不安定なため)。
id列を持たない集計一覧(03/06)のために id_col=None を用意した。"
```

---

### Task 3: `list_action_bar` のダウンロードと削除

**Files:**
- Modify: `common/ui.py`
- Test: `tests/test_ui_list_actions.py`

**Interfaces:**
- Consumes: `ui.selectable_list`（Task 2）、`posting_logic.rows_for_excel`、`excel_io.freeze_xlsx_bytes`、`ui.flash`
- Produces:
  - `ui.list_action_bar(edited_df, *, key, title, filename, section=None, select_col="選択", id_col="No.", delete_fn=None, delete_note=None, extra=None) -> None`
  - ウィジェットkey: 印刷 `f"{key}_print"` / DL `f"{key}_dl"` / 削除 `f"{key}_bulk_del_btn"`・`f"{key}_bulk_del_ok"`・`f"{key}_bulk_del_no"`
  - **既存ページの削除ボタンkeyと一致させる**ため `_bulk_del_*` の綴りは変えない（`bulk_delete_action(key="petty_bulk_del")` → `list_action_bar(key="petty")` で同じ `petty_bulk_del_btn` になる）
  - `delete_fn` を渡して `id_col=None` の組み合わせは `ValueError`

印刷ボタンは本タスクでは「押すと `st.session_state[f"_print_{key}"]` に選択行を積む」ところまで作り、印刷ビューの描画はTask 4で足す。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_ui_list_actions.py` の末尾に追記:

```python
# ===== list_action_bar =====

def _bar_page():
    import streamlit as st  # noqa: F401
    from common import ui

    st.session_state.setdefault("_deleted", [])
    edited, ids = ui.selectable_list(_ROWS, key="t")
    ui.list_action_bar(
        edited, key="t", title="小口一覧", filename="小口一覧", section="sec",
        delete_fn=lambda i: st.session_state["_deleted"].append(i))


def test_action_bar_shows_three_buttons_in_fixed_order():
    """🔴 印刷・ダウンロード・削除が必ずこの順で出ること(全ページ統一の肝)。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    assert not at.exception
    keys = [b.key for b in at.button if b.key and b.key.startswith("t_")]
    assert "t_print" in keys
    assert "t_bulk_del_btn" in keys
    ids = [d.id for d in at.get("download_button")]
    assert any("t_dl" in i for i in ids)


def test_action_bar_buttons_are_disabled_when_nothing_selected():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    assert at.button(key="t_print").disabled is True
    assert at.button(key="t_bulk_del_btn").disabled is True


def test_action_bar_buttons_enabled_after_select_all():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    assert at.button(key="t_print").disabled is False
    assert at.button(key="t_bulk_del_btn").disabled is False


def test_action_bar_delete_asks_before_deleting():
    """押しただけでは消さない。確認を挟む。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_bulk_del_btn").click().run()
    assert at.session_state["_deleted"] == []
    assert len(at.warning) == 1


def test_action_bar_delete_removes_selected_and_flashes():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_bulk_del_btn").click().run()
    at.button(key="t_bulk_del_ok").click().run()
    assert at.session_state["_deleted"] == [11, 12, 13]
    assert at.session_state["_flash_sec"] == "3件を削除しました"


def test_action_bar_delete_cancel_keeps_rows():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_bulk_del_btn").click().run()
    at.button(key="t_bulk_del_no").click().run()
    assert at.session_state["_deleted"] == []
    assert len(at.warning) == 0


def test_action_bar_delete_button_disabled_when_no_delete_fn():
    """🔴 03・06 の「見るだけの画面」。削除ボタンは出るが押せないこと。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"日付": "2026-08-01", "区分": "原価", "金額": "¥100"}]
        edited, _ = ui.selectable_list(rows, key="v", id_col=None)
        ui.list_action_bar(edited, key="v", title="まとめ", filename="まとめ",
                           id_col=None, delete_fn=None,
                           delete_note="このデータは登録画面から削除してください")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="v_all").check().run()
    assert not at.exception
    # 選択しても削除だけは押せない
    assert at.button(key="v_bulk_del_btn").disabled is True
    assert at.button(key="v_print").disabled is False


def test_action_bar_rejects_delete_fn_without_id_col():
    """🔴 削除できるのに id 列が無い＝「削除したのに消えない」を無言で作らせない。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui
        import pandas as pd

        df = pd.DataFrame([{"選択": True, "日付": "2026-08-01"}])
        ui.list_action_bar(df, key="bad", title="x", filename="x",
                           id_col=None, delete_fn=lambda i: None)

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert at.exception
    assert "id_col" in str(at.exception[0].value)


def test_action_bar_extra_button_is_rendered():
    """業務委託のZIPのような、ページ固有のボタンを右端に足せること。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        edited, _ = ui.selectable_list(_ROWS, key="x")
        ui.list_action_bar(edited, key="x", title="一覧", filename="一覧",
                           extra=lambda c, rows, ids: c.button("ZIP", key="x_zip"))

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert "x_zip" in {b.key for b in at.button}


def test_action_bar_print_button_stores_selected_rows():
    """印刷を押すと選択行が session_state に積まれること(描画はTask 4)。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_print").click().run()
    stored = at.session_state["_print_t"]
    assert [r["No."] for r in stored] == [11, 12, 13]
    assert "選択" not in stored[0]
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q -k action_bar`
Expected: FAIL（`AttributeError: module 'common.ui' has no attribute 'list_action_bar'`）。

- [ ] **Step 3: 実装する**

`common/ui.py` の `selectable_list` の直後に追加:

```python
def list_action_bar(edited_df, *, key, title, filename, section=None,
                    select_col="選択", id_col="No.",
                    delete_fn=None, delete_note=None, extra=None):
    """選択した行に対する「印刷・ダウンロード・削除」を、全ページで同じ順・同じ見た目で出す。

    delete_fn=None のときは削除だけ無効(灰色)にし、delete_note をホバーで出す。
    03 号別明細・06 まとめは集計を見るだけの画面で、ここから消しても元データは
    消えないため、この形にしている(見た目は揃えつつ、事故は起こさない)。

    extra は右端に足すページ固有のボタン。extra(container, rows, ids) で呼ばれる。
    """
    from common import posting_logic
    from common.excel_io import freeze_xlsx_bytes
    import pandas as pd

    if delete_fn is not None and id_col is None:
        # 削除できるのに行を特定できない＝「削除したのに消えない」を無言で作らないため
        raise ValueError("delete_fn を渡すときは id_col が必要です（削除対象を特定できません）")

    if edited_df is None or getattr(edited_df, "empty", True):
        return

    # 印刷ビューが開いていれば、そちらだけを描いて操作バーは出さない
    if _print_view(key=key, title=title):
        return

    rows = posting_logic.rows_for_excel(edited_df, select_col=select_col)
    ids = ([] if id_col is None
           else posting_logic.selected_ids_from_editor(edited_df, id_col=id_col,
                                                       select_col=select_col))
    n = len(rows)

    # 削除の確認待ちは、ボタンの並びより先に全幅で出す(狭い列に潰さない)
    pending = f"_bulkdel_pending_{key}"
    waiting = st.session_state.get(pending)
    if waiting:
        st.warning(f"⚠️ 選択した{len(waiting)}件を削除しますか？")
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("はい", type="primary", key=f"{key}_bulk_del_ok"):
            for i in waiting:
                delete_fn(i)
            st.session_state.pop(pending, None)
            flash(f"{len(waiting)}件を削除しました", section)
            st.rerun()
        if c2.button("いいえ", key=f"{key}_bulk_del_no"):
            st.session_state.pop(pending, None)
            st.rerun()
        return

    cols = st.columns(4 if extra else 3)

    if cols[0].button("印刷", icon=":material/print:", key=f"{key}_print",
                      disabled=not n, use_container_width=True):
        st.session_state[f"_print_{key}"] = rows
        st.rerun()

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(rows or [{}]).to_excel(w, index=False, sheet_name="選択した行")
    cols[1].download_button(
        "ダウンロード", data=freeze_xlsx_bytes(buf.getvalue()),
        file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:", disabled=not n, key=f"{key}_dl",
        use_container_width=True)

    if cols[2].button("削除", icon=":material/delete:", key=f"{key}_bulk_del_btn",
                      disabled=(delete_fn is None or not ids),
                      help=delete_note if delete_fn is None else None,
                      use_container_width=True):
        st.session_state[pending] = list(ids)
        st.rerun()

    if extra:
        extra(cols[3], rows, ids)
```

`_print_view` はTask 4で本実装する。まずは常に False を返す仮実装を `list_action_bar` の直前に置く:

```python
def _print_view(*, key, title):
    """印刷ビューを描いたら True。Task 4 で本実装する。"""
    return False
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q`
Expected: 19 passed（Task 2の8件＋本タスクの11件）。

- [ ] **Step 5: ミューテーションで検出力を確認**

`disabled=(delete_fn is None or not ids)` を `disabled=not ids` に変えて Run: `python -m pytest tests/test_ui_list_actions.py -q -k no_delete_fn`
Expected: **FAIL**。元に戻す。

次に `raise ValueError(...)` の行を削除して Run: `python -m pytest tests/test_ui_list_actions.py -q -k without_id_col`
Expected: **FAIL**。元に戻す。

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `336 passed`。

- [ ] **Step 7: コミット**

```bash
git add common/ui.py tests/test_ui_list_actions.py
git commit -m "feat(ui): list_action_bar に印刷・ダウンロード・削除を実装

全ページで同じ順・同じ見た目のボタンを出す共通部品。delete_fn=None の
画面(03 号別明細・06 まとめ)は削除だけ灰色にして、見た目を揃えつつ
集計元が消える事故を防ぐ。delete_fn があるのに id_col=None の組み合わせは
ValueError で弾く(削除したのに消えない状態を無言で作らないため)。"
```

---

### Task 4: 印刷プレビューと `@media print`

**Files:**
- Modify: `common/posting_logic.py`, `common/ui.py`
- Test: `tests/test_posting_logic.py`, `tests/test_ui_list_actions.py`

**Interfaces:**
- Consumes: `list_action_bar` が積む `st.session_state[f"_print_{key}"]`（Task 3）
- Produces:
  - `posting_logic.print_total(rows) -> tuple[str, float] | None`
  - `ui._print_view(*, key, title) -> bool`（Task 3の仮実装を差し替え）
  - ウィジェットkey: 閉じる `f"{key}_print_close"`

- [ ] **Step 1: 合計ロジックの失敗するテストを書く**

`tests/test_posting_logic.py` の末尾に追記:

```python
def test_print_total_sums_yen_formatted_amounts():
    """印刷の合計。表示用の「¥1,234」形式をパースして合計する。"""
    rows = [{"No.": 1, "金額": "¥3,200"}, {"No.": 2, "金額": "¥980"}]
    assert posting_logic.print_total(rows) == ("金額", 4180)


def test_print_total_uses_seikyugaku_column_too():
    rows = [{"No.": 1, "請求額": "¥1,000"}, {"No.": 2, "請求額": "¥2,000"}]
    assert posting_logic.print_total(rows) == ("請求額", 3000)


def test_print_total_returns_none_without_amount_column():
    assert posting_logic.print_total([{"No.": 1, "日付": "2026-08-01"}]) is None


def test_print_total_returns_none_if_any_row_is_unparsable():
    """🔴 1行でも読めなければ合計を出さない。嘘の数字を紙に載せないため。"""
    rows = [{"金額": "¥1,000"}, {"金額": "—"}, {"金額": "¥2,000"}]
    assert posting_logic.print_total(rows) is None


def test_print_total_returns_none_for_empty_rows():
    assert posting_logic.print_total([]) is None
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_posting_logic.py -q -k print_total`
Expected: FAIL（`AttributeError: module 'common.posting_logic' has no attribute 'print_total'`）。

- [ ] **Step 3: `print_total` を実装する**

`common/posting_logic.py` の `rows_for_excel` の直後に追加:

```python
_PRINT_AMOUNT_KEYS = ("金額", "請求額", "合計")


def print_total(rows):
    """印刷用の合計。金額らしき列があり、全行が数値として読めるときだけ (列名, 合計) を返す。

    一覧の値は表示用に整形済みの文字列(「¥1,234」)。1行でも読めない値(「—」など)が
    混ざったまま合計すると、その行を無かったことにした嘘の合計を紙に載せてしまう。
    そのため「全行読めるとき以外は合計を出さない」を明示的な仕様にしている。
    """
    if not rows:
        return None
    col = next((c for c in rows[0] if any(k in str(c) for k in _PRINT_AMOUNT_KEYS)), None)
    if col is None:
        return None
    total = 0.0
    for r in rows:
        raw = (str(r.get(col, "")).replace("¥", "").replace(",", "")
               .replace("円", "").strip())
        if not raw:
            return None
        try:
            total += float(raw)
        except ValueError:
            return None
    return (col, total)
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_posting_logic.py -q -k print_total`
Expected: 5 passed。

- [ ] **Step 5: 印刷ビューの失敗するテストを書く**

`tests/test_ui_list_actions.py` の末尾に追記:

```python
# ===== 印刷ビュー =====

def test_print_view_opens_after_pressing_print():
    """🔴 印刷を押すと、選択行だけの印刷ビューに切り替わること。"""
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_print").click().run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert 'class="printable"' in body
    assert "消耗品" in body and "交通費" in body
    # 印刷ビューでは操作バーは出さない(印刷対象に混ざらないように)
    assert not any(b.key == "t_bulk_del_btn" for b in at.button)


def test_print_view_shows_title_and_count():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_print").click().run()
    body = " ".join(m.value for m in at.markdown)
    assert "小口一覧" in body
    assert "3件" in body


def test_print_view_shows_total_when_all_amounts_parse():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_print").click().run()
    body = " ".join(m.value for m in at.markdown)
    assert "5,680" in body      # 3200 + 980 + 1500


def test_print_view_omits_total_when_a_value_is_unparsable():
    """🔴 読めない値があるときは合計行そのものを出さない。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"No.": 1, "金額": "¥100"}, {"No.": 2, "金額": "—"}]
        edited, _ = ui.selectable_list(rows, key="u")
        ui.list_action_bar(edited, key="u", title="一覧", filename="一覧")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="u_all").check().run()
    at.button(key="u_print").click().run()
    body = " ".join(m.value for m in at.markdown)
    assert "合計" not in body


def test_print_view_escapes_html_in_values():
    """🔴 値をそのままHTMLに入れない(社名に < > が入っていても表が壊れない)。"""

    def _page():
        import streamlit as st  # noqa: F401
        from common import ui

        rows = [{"No.": 1, "取引先": "<b>タグ入り</b>"}]
        edited, _ = ui.selectable_list(rows, key="h")
        ui.list_action_bar(edited, key="h", title="一覧", filename="一覧")

    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    at.checkbox(key="h_all").check().run()
    at.button(key="h_print").click().run()
    body = " ".join(m.value for m in at.markdown)
    assert "&lt;b&gt;タグ入り&lt;/b&gt;" in body
    assert "<b>タグ入り</b>" not in body


def test_print_view_close_returns_to_the_list():
    at = AppTest.from_function(_bar_page, default_timeout=30)
    at.run()
    at.checkbox(key="t_all").check().run()
    at.button(key="t_print").click().run()
    at.button(key="t_print_close").click().run()
    assert "_print_t" not in at.session_state
    assert any(b.key == "t_bulk_del_btn" for b in at.button)
```

- [ ] **Step 6: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q -k print_view`
Expected: FAIL（`_print_view` が常に False を返す仮実装のため、印刷ビューが出ない）。

- [ ] **Step 7: `_print_view` を本実装する**

`common/ui.py` の import に追加（ファイル先頭の `import io` の下）:

```python
import html as _html
from datetime import date as _date
```

Task 3で置いた仮の `_print_view` を丸ごと差し替える:

```python
def _print_table_html(rows, *, title, subtitle, total):
    """選択行だけの印刷用HTML。値は必ずエスケープする(社名に < > が入っても壊れない)。"""
    heads = list(rows[0].keys())
    thead = "".join(f"<th>{_html.escape(str(h))}</th>" for h in heads)
    body = "".join(
        "<tr>" + "".join(
            f"<td>{_html.escape('' if r.get(h) is None else str(r.get(h)))}</td>"
            for h in heads) + "</tr>"
        for r in rows)
    tfoot = ""
    if total is not None:
        col, value = total
        from common import posting_logic

        tfoot = (f'<div class="ptotal">{_html.escape(str(col))}の合計：'
                 f'¥{posting_logic.fmt_num(value)}</div>')
    return (f'<div class="printable">'
            f'<h2 class="ptitle">{_html.escape(title)}</h2>'
            f'<div class="pmeta">{_html.escape(subtitle)}</div>'
            f'<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>'
            f'{tfoot}</div>')


def _print_view(*, key, title):
    """印刷ビューが開いていれば描いて True。閉じていれば False。

    印刷は「選択行だけのきれいな表を出して、その状態でブラウザ印刷する」方式。
    ページ全体を print すると、サイドバーもボタンも紙に載ってしまうため、
    表示を切り替えたうえで @media print で残りを隠している。
    """
    from common import posting_logic

    slot = f"_print_{key}"
    rows = st.session_state.get(slot)
    if not rows:
        return False

    subtitle = f"出力日 {_date.today().isoformat()}　／　{len(rows)}件"
    st.markdown(
        _print_table_html(rows, title=title, subtitle=subtitle,
                          total=posting_logic.print_total(rows)),
        unsafe_allow_html=True)

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        components.html(
            """<button onclick="window.parent.print()"
                style="width:100%;padding:.5rem .6rem;border:none;border-radius:10px;
                       background:#14a4dc;color:#fff;font-weight:700;cursor:pointer;
                       font-family:'Noto Sans JP',sans-serif;">印刷する</button>""",
            height=46)
    if c2.button("閉じる", key=f"{key}_print_close"):
        st.session_state.pop(slot, None)
        st.rerun()
    return True
```

`_STYLE` の閉じタグ `</style>` の直前に追加:

```css
/* ===== 印刷ビュー(選択した行だけを紙に載せる) ===== */
.printable{ background:#fff; border:1px solid var(--line); border-radius:14px;
            padding:1.2rem 1.4rem; margin:.4rem 0 1rem; }
.printable .ptitle{ font-size:1.2rem; font-weight:800; margin:0 0 .2rem; }
.printable .pmeta{ color:var(--muted); font-size:.85rem; margin-bottom:.7rem; }
.printable table{ width:100%; border-collapse:collapse; font-size:.9rem; }
.printable th, .printable td{ border:1px solid #cfd8e3; padding:.4rem .6rem; text-align:left; }
.printable thead th{ background:#eef3f8; font-weight:700; }
.printable .ptotal{ margin-top:.7rem; font-weight:800; text-align:right; font-size:1rem; }

@media print{
  /* 紙に載せるのは .printable だけ。操作用のUIは全部消す */
  [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"],
  [data-testid="stDataFrame"], [data-testid="stDataEditor"], [data-testid="stCheckbox"],
  [data-testid="stExpander"], [data-testid="stAlert"], [data-testid="stMetric"],
  .stButton, [data-testid="stDownloadButton"], [data-testid="stCaptionContainer"],
  iframe{ display:none !important; }
  .stApp{ background:#fff !important; }
  .block-container{ padding:0 !important; max-width:100% !important; }
  .printable{ border:none !important; padding:0 !important; }
  .printable thead th{ background:#eee !important; -webkit-print-color-adjust:exact;
                       print-color-adjust:exact; }
  @page{ size:A4 portrait; margin:12mm; }
}
```

- [ ] **Step 8: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q`
Expected: 25 passed。

- [ ] **Step 9: ミューテーションで検出力を確認**

`_html.escape(...)` を素の `str(...)` に変えて（`_print_table_html` の td 側）Run: `python -m pytest tests/test_ui_list_actions.py -q -k escapes_html`
Expected: **FAIL**。元に戻す。

`print_total` の `except ValueError: return None` を `except ValueError: continue` に変えて Run: `python -m pytest tests/test_posting_logic.py tests/test_ui_list_actions.py -q -k "unparsable"`
Expected: **FAIL**。元に戻す。

- [ ] **Step 10: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `347 passed`。

- [ ] **Step 11: コミット**

```bash
git add common/ui.py common/posting_logic.py tests/test_ui_list_actions.py tests/test_posting_logic.py
git commit -m "feat(ui): 選択した行だけの印刷プレビューと @media print を追加

ページ全体を print するとサイドバーもボタンも紙に載るため、選択行だけの
表に切り替えてから印刷する方式にした。値は必ずHTMLエスケープする。
合計は全行が数値として読めるときだけ出す(1行でも読めなければ出さない＝
嘘の合計を紙に載せない)。"
```

---

### Task 5: `pages/01_経費・買掛・売掛.py` を共通部品へ載せ替え

**Files:**
- Modify: `pages/01_経費・買掛・売掛.py:195-218, 335-358, 406-427`
- Modify: `tests/test_pages_smoke.py:826-833`

**Interfaces:**
- Consumes: `ui.selectable_list` / `ui.list_action_bar`（Task 2,3,4）
- Produces: 小口=`key="petty"` / 買掛=`key="pay"` / 売掛=`key="recv"`。削除ボタンkeyは従来どおり `petty_bulk_del_btn` 等になる。data_editor のkeyは `petty_select` → **`petty_select_0`** に変わる。

- [ ] **Step 1: 既存テストを新しいキーに合わせて直す（先に落として確認する）**

`tests/test_pages_smoke.py` の `at.session_state["petty_select"]` を `at.session_state["petty_select_0"]` に置換（3か所: 766行付近・783行付近・809行付近）。同様に `"pay_select"` → `"pay_select_0"`、`"recv_select"` → `"recv_select_0"`。

`test_petty_whole_list_export_kept` を次に差し替える:

```python
def test_petty_list_has_unified_download_button(db):
    """section_export の全件Excelは撤去し、統一バーのダウンロードに集約した。
    「すべて選択」を押せば全件をダウンロードできる。"""
    _seed_petty(db)
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"), default_timeout=30)
    at.run()
    ids = [b.id for b in at.get("download_button")]
    assert any("petty_dl" in i for i in ids)
    assert not any("petty_xlsx" in i for i in ids)   # 旧 section_export は無い
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "petty or payable or receivable"`
Expected: FAIL（`petty_dl` が無い／`petty_select_0` が反映されない）。

- [ ] **Step 3: 実装する**

`pages/01_経費・買掛・売掛.py` の import（9〜11行）を差し替え:

```python
from common.ui import (apply_app_style, nice_table, period_picker,
                       flash, show_flash,
                       selectable_list, list_action_bar)
```

小口の一覧（207〜218行）を差し替え:

```python
        if not _disp:
            st.caption("小口の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="petty")
            list_action_bar(edited, key="petty", title="小口一覧",
                            filename="小口_選択一覧", section="petty",
                            delete_fn=store.delete_petty_cash)
```

買掛の一覧（347〜358行）を差し替え:

```python
        if not _disp:
            st.caption("買掛の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="pay")
            list_action_bar(edited, key="pay", title="買掛一覧",
                            filename="買掛_選択一覧", section="payable",
                            delete_fn=store.delete_payable)
```

売掛の一覧（416〜427行）を差し替え:

```python
        if not _disp:
            st.caption("売掛の登録はまだありません。")
        else:
            edited, selected_ids = selectable_list(_disp, key="recv")
            list_action_bar(edited, key="recv", title="売掛一覧",
                            filename="売掛_選択一覧", section="receivable",
                            delete_fn=store.delete_receivable)
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py tests/test_rev6_confirm.py -q`
Expected: 全PASS。

- [ ] **Step 5: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `347 passed`（差し替えたテストは件数が変わらない）。

- [ ] **Step 6: コミット**

```bash
git add pages/01_経費・買掛・売掛.py tests/test_pages_smoke.py
git commit -m "refactor(01): 小口・買掛・売掛の一覧を共通部品へ載せ替え

section_export + checkbox_list_editor + selected_rows_excel_button +
bulk_delete_action の4行を selectable_list + list_action_bar の2行にした。
全件Excelは「すべて選択」→ダウンロードで代替できるため撤去。"
```

---

### Task 6: `pages/02_業務委託登録.py` を共通部品へ載せ替え（ZIPは遅延生成）

**Files:**
- Modify: `pages/02_業務委託登録.py:213-294`
- Modify: `tests/test_pages_smoke.py`（`contract_list_editor` を使う箇所）

**Interfaces:**
- Consumes: `ui.selectable_list` / `ui.list_action_bar`
- Produces: `key="contract"`。data_editor key は `contract_list_editor` → **`contract_select_0`**。削除ボタンは `contract_bulk_del_btn`（従来は `invoice_bulk_del_btn`）。ZIPは `extra` で右端に出し、key は `dl_zip` のまま。

**あわせて直す既存の問題:** 現在ZIPは毎回の再描画で全件生成している（240〜264行）。選択が多いと描画のたびに全件のExcelを作り直すため、ボタンを押した時だけ作る形にする。

- [ ] **Step 1: 既存テストを新しいキーに合わせて直す**

`tests/test_pages_smoke.py` 内の `at.session_state["contract_list_editor"]` を `at.session_state["contract_select_0"]` に、`invoice_bulk_del_btn` / `invoice_bulk_del_ok` を `contract_bulk_del_btn` / `contract_bulk_del_ok` に置換する。

Run: `python -m pytest tests/test_pages_smoke.py -q -k contract` して、置換対象が実在することを先に確認する（該当が無ければ置換は不要）。

- [ ] **Step 2: 失敗するテストを追加する**

`tests/test_pages_smoke.py` の業務委託セクション末尾に追記:

```python
def test_contract_list_uses_unified_action_bar(db):
    """🔴 業務委託の一覧も統一バーになっていること(選択するまでボタンが無い状態の解消)。"""
    _seed_invoice(db)
    at = _run(_CONTRACT_PAGE)
    keys = {b.key for b in at.button}
    assert "contract_print" in keys
    assert "contract_bulk_del_btn" in keys
    ids = [b.id for b in at.get("download_button")]
    assert any("contract_dl" in i for i in ids)
    # 何も選んでいなくてもボタンは存在する(灰色なだけ)
    assert at.button(key="contract_bulk_del_btn").disabled is True


def test_contract_zip_button_exists_without_selection(db):
    """報告書ZIPも、選択が無くても存在すること(押せないだけ)。"""
    _seed_invoice(db)
    at = _run(_CONTRACT_PAGE)
    ids = [b.id for b in at.get("download_button")]
    assert any("dl_zip" in i for i in ids)
```

- [ ] **Step 3: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "unified_action_bar or zip_button_exists"`
Expected: FAIL（`contract_print` が無い）。

- [ ] **Step 4: 実装する**

`pages/02_業務委託登録.py` の import（11〜13行）を差し替え:

```python
from common.ui import (apply_app_style, nice_table, period_picker,
                       flash, show_flash, selectable_list, list_action_bar)
from common.excel_io import freeze_xlsx_bytes
```

213行の `# --- 一覧（チェックで複数選択） ---` から 294行の `bulk_delete_action(...)` までを、次で置き換える（`disp_rows` を組み立てる部分＝216〜232行はそのまま残し、`"選択": False,` の行だけ削除する。選択列は `selectable_list` が付けるため）:

```python
    st.caption("チェックを付けた請求を、下のボタンでまとめて出力できます。")
    edited, selected_ids = selectable_list(disp_rows, key="contract")

    def _zip_button(container, rows, ids):
        """報告書をまとめてZIPで出す(このページ固有)。
        ⚠️ 押した時だけ作る。以前は毎回の再描画で全件のExcelを作り直していた。"""
        zip_buf, skipped = io.BytesIO(), []
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for iid in ids:
                detail = detail_by_id.get(iid) or store.get_contract_invoice(iid)
                head = detail["invoice"]
                out_lines = _invoice_out_lines(detail, id2proj)
                if len(out_lines) > 6:
                    skipped.append(iid)
                    continue
                name = id2name.get(head["distributor_id"], "")
                zf.writestr(
                    f'業務完了報告書兼請求書_{name}_{head["issue_date"]}.xlsx',
                    invoice_excel.build_invoice_xlsx(
                        distributor_name=name, issue_date=head["issue_date"],
                        period_from=head["period_from"], period_to=head["period_to"],
                        lines=out_lines,
                        # マスタの現在値ではなく請求に焼き付けた支払形態を使う。現在値を使うと
                        # 支払形態を変えた瞬間に過去の報告書の単位が化ける。
                        pay_type=head.get("pay_type")))
        exported = [i for i in ids if i not in skipped]
        if skipped:
            st.warning("次の請求は明細が6行を超えるためスキップしました（案件ごとに集約してください）："
                       + "、".join(f"No.{i}" for i in skipped))
        if container.download_button(
                f"報告書ZIP（{len(exported)}件）", data=zip_buf.getvalue(),
                file_name=f"業務完了報告書_選択{len(exported)}件.zip",
                mime="application/zip", icon=":material/folder_zip:",
                disabled=not exported, key="dl_zip", use_container_width=True):
            for iid in exported:
                store.mark_contract_invoice_exported(iid)
            st.rerun()

    list_action_bar(edited, key="contract", title="業務委託 請求一覧",
                    filename=f"業務委託_選択一覧_{len(selected_ids)}件",
                    section="invoice_list",
                    delete_fn=store.delete_contract_invoice, extra=_zip_button)
```

- [ ] **Step 5: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k contract`
Expected: 全PASS。

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `349 passed`。

- [ ] **Step 7: コミット**

```bash
git add pages/02_業務委託登録.py tests/test_pages_smoke.py
git commit -m "refactor(02): 業務委託の一覧を共通部品へ載せ替え、ZIPは押した時だけ作る

選択するまでボタン自体が存在しない状態(依頼③の実体)を解消。
ZIPは毎回の再描画で全件のExcelを作り直していたため、押した時だけ生成する
形に変えた。出力済みフラグを立てるタイミングは変えていない。"
```

---

### Task 7: `pages/03_号別明細.py` と `pages/06_原価・売上まとめ.py`（削除は無効）

**Files:**
- Modify: `pages/03_号別明細.py:198, 217`
- Modify: `pages/06_原価・売上まとめ.py:73`
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: `ui.selectable_list(id_col=None)` / `ui.list_action_bar(delete_fn=None)`
- Produces: 03=`key="issue_labor"`・`key="issue_misc"` / 06=`key="summary"`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pages_smoke.py` の末尾に追記:

```python
# ===== 見るだけの画面(03・06)にも同じバーを置く。削除だけ無効 =====

def test_summary_page_has_action_bar_with_delete_disabled(db):
    """🔴 06 まとめ。印刷・DLは使えるが、削除は押せないこと。
    ここの行は 01・02 のデータのコピーで、消しても元は消えないため。"""
    store.add_receivables_client("得意先", db_path=db)
    at = _run("06_原価・売上まとめ.py")
    assert not at.exception
    keys = {b.key for b in at.button}
    assert "summary_print" in keys
    assert "summary_bulk_del_btn" in keys
    assert at.button(key="summary_bulk_del_btn").disabled is True


def test_summary_page_delete_stays_disabled_even_when_all_selected(db):
    """🔴 全選択しても削除は押せないままであること(集計元が消える事故をゼロにする)。"""
    cid = store.add_receivables_client("得意先", db_path=db)
    store.add_receivable("2026-08", cid, 1000, db_path=db)
    at = _run("06_原価・売上まとめ.py")
    at.checkbox(key="summary_all").check().run()
    assert not at.exception
    assert at.button(key="summary_bulk_del_btn").disabled is True
    assert at.button(key="summary_print").disabled is False


def test_summary_page_old_section_export_is_gone(db):
    at = _run("06_原価・売上まとめ.py")
    ids = [b.id for b in at.get("download_button")]
    assert not any("summary_xlsx" in i for i in ids)
    assert any("summary_dl" in i for i in ids)
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k summary_page`
Expected: FAIL（`summary_print` が無い）。

- [ ] **Step 3: 実装する**

`pages/06_原価・売上まとめ.py` の import（7行）を差し替え:

```python
from common.ui import (apply_app_style, nice_table, period_picker, show_flash,
                       selectable_list, list_action_bar)
```

73行 `section_export(disp, "原価売上まとめ", key="summary")` を差し替え（直前の `nice_table(disp, ...)` は撤去する。選択できる表に置き換わるため）:

```python
_edited, _ = selectable_list(disp, key="summary", id_col=None)
list_action_bar(_edited, key="summary", title="原価・売上まとめ",
                filename="原価売上まとめ", id_col=None, delete_fn=None,
                delete_note="この画面は集計を見るためのものです。"
                            "元のデータは『小口／買掛／売掛』『業務委託登録』から削除してください。")
```

`pages/03_号別明細.py` の import（11行）を差し替え:

```python
from common.ui import (apply_app_style, nice_table, period_picker, flash, show_flash,
                       selectable_list, list_action_bar)
```

198行 `section_export(_man_disp, f"配布員代直接入力_{sel}", key="issue_labor")` を差し替え:

```python
    _lab_edited, _ = selectable_list(_man_disp, key="issue_labor", id_col=None)
    list_action_bar(_lab_edited, key="issue_labor", title=f"配布員代 直接入力（{sel}）",
                    filename=f"配布員代直接入力_{sel}", id_col=None, delete_fn=None,
                    delete_note="この一覧の削除は上の編集フォームから行ってください。")
```

217行 `section_export(_misc, f"雑費_{sel}", key="issue_misc")` を差し替え（直前の `nice_table(_misc, ...)` は撤去）:

```python
    _misc_edited, _ = selectable_list(_misc, key="issue_misc", id_col=None)
    list_action_bar(_misc_edited, key="issue_misc", title=f"雑費（{sel}）",
                    filename=f"雑費_{sel}", id_col=None, delete_fn=None,
                    delete_note="雑費の元データは『小口／買掛／売掛』の小口から削除してください。")
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k summary_page`
Expected: 3 passed。

- [ ] **Step 5: ミューテーションで検出力を確認**

`pages/06` の `delete_fn=None` を `delete_fn=lambda i: None` に変えて Run: `python -m pytest tests/test_pages_smoke.py -q -k summary_page`
Expected: **FAIL**（`id_col=None` との組み合わせで `ValueError` になり例外で落ちる＝Task 3のガードが効いていることも同時に確認できる）。元に戻す。

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `352 passed`。

- [ ] **Step 7: コミット**

```bash
git add pages/03_号別明細.py pages/06_原価・売上まとめ.py tests/test_pages_smoke.py
git commit -m "refactor(03,06): 集計画面にも統一バーを置き、削除だけ無効にする

この2画面の行は 01・02 のデータのコピーで、ここから消しても元は消えない。
見た目は他ページと完全に揃えつつ、削除は灰色にして誤操作で集計元が
消える事故をゼロにする。id列を持たないため id_col=None で呼ぶ。"
```

---

### Task 8: 旧部品の撤去

**Files:**
- Modify: `common/ui.py`（`section_export` / `checkbox_list_editor` / `selected_rows_excel_button` / `bulk_delete_action` を削除）
- Test: `tests/test_ui_list_actions.py`

**Interfaces:**
- Consumes: なし
- Produces: `common.ui` から上記4関数が消える。`confirm_delete` は残る（05 マスタ管理が使用）。

- [ ] **Step 1: 使われていないことを確認する**

Run: `python -m pytest -q` が緑であることを確認したうえで、
Run: `grep -rn "section_export\|checkbox_list_editor\|selected_rows_excel_button\|bulk_delete_action" pages/ common/ tests/`
Expected: `common/ui.py` の定義行以外にヒットが無い。ヒットがあれば、その呼び出し元を先に共通部品へ移すこと。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_ui_list_actions.py` の末尾に追記:

```python
def test_old_list_helpers_are_removed():
    """🔴 統一の目的は「作りが2通りある状態をなくす」こと。
    旧部品が残っていると新しいページがまた旧部品を使い、同じ散らばりが再発する。"""
    from common import ui

    for name in ("section_export", "checkbox_list_editor",
                 "selected_rows_excel_button", "bulk_delete_action"):
        assert not hasattr(ui, name), f"{name} が残っている"
    # 行ごと削除(05 マスタ管理)で使うので confirm_delete は残す
    assert hasattr(ui, "confirm_delete")
```

- [ ] **Step 3: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_ui_list_actions.py -q -k old_list_helpers`
Expected: FAIL（`section_export が残っている`）。

- [ ] **Step 4: 実装する**

`common/ui.py` から次の4つの関数定義を丸ごと削除する:
- `checkbox_list_editor`（444〜461行付近）
- `selected_rows_excel_button`（464〜481行付近）
- `bulk_delete_action`（484〜507行付近）
- `section_export`（533〜558行付近）

- [ ] **Step 5: テストを走らせて通ることを確認**

Run: `python -m pytest -q`
Expected: `353 passed`。

- [ ] **Step 6: コミット**

```bash
git add common/ui.py tests/test_ui_list_actions.py
git commit -m "refactor(ui): 旧一覧部品4つを撤去して統一部品に一本化

section_export / checkbox_list_editor / selected_rows_excel_button /
bulk_delete_action を削除。残すと新しいページがまた旧部品を使い、
ページごとに作りが違う状態が再発するため。confirm_delete は 05 マスタ管理の
行ごと削除で使うので残す。"
```

---

### Task 9: ラジオを `segmented_control` へ置き換える（依頼②）

**Files:**
- Modify: `pages/01_経費・買掛・売掛.py:16`
- Modify: `pages/07_資料作成・変換表.py:22-24`
- Modify: `common/ui.py`（CSS）
- Modify: `tests/test_pages_smoke.py`, `tests/test_rev6_confirm.py`, `tests/test_pages_atehagi_ui.py`

**Interfaces:**
- Consumes: なし
- Produces: `at.radio[0]` で取れていた入力が `at.segmented_control[0]` になる。`pages/01` は `key="entry_mode"`、`pages/07` は `key="keihan_version"`（据え置き）。

**🔴 このタスクで一番大事な点:** `st.segmented_control` は**選択を解除でき、そのとき `None` を返す**。現在のコードは None を考慮していないため、素朴に置き換えると
- `pages/07`: `version = A.KEIHAN_KITA if version_label == "京阪北版" else A.KEIHAN_MINAMI` が `else` に落ち、**全枚数のあて紙で地区名が誤る**
- `pages/01`: `if mode == "小口" ... elif "買掛" ... else` が `else` に落ち、**売掛の画面が開く**

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pages_smoke.py` の末尾に追記:

```python
# ===== ラジオ → segmented_control(依頼②) =====

def test_expense_page_mode_is_segmented_control(db):
    at = _run(_EXPENSE_PAGE)
    assert not at.exception
    assert [s.key for s in at.segmented_control] == ["entry_mode"]
    assert at.segmented_control[0].options == ["小口", "買掛", "売掛"]
    assert not at.radio


def test_expense_page_falls_back_to_petty_when_deselected(db):
    """🔴 segmented_control は選択解除で None を返す。
    None のまま else に落ちると売掛の画面が開いてしまう。既定へ戻ること。"""
    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.session_state["entry_mode"] = None
    at.run()
    assert not at.exception
    assert "小口経費" in _rendered_text(at)
    assert "売掛（売上）" not in _rendered_text(at)


def test_shiryo_page_version_is_segmented_control(db):
    at = _run("07_資料作成・変換表.py")
    assert not at.exception
    keys = {s.key for s in at.segmented_control}
    assert "keihan_version" in keys
    assert not at.radio


def test_shiryo_page_version_falls_back_to_kita_when_deselected(db):
    """🔴 版が None のまま else に落ちると南版になり、全枚数の地区名が誤る。"""
    from common import atehagi as A

    at = AppTest.from_file(os.path.join(ROOT, "pages", "07_資料作成・変換表.py"),
                           default_timeout=30)
    at.session_state["keihan_version"] = None
    at.session_state["_probe"] = None
    at.run()
    assert not at.exception
    # 版の判定結果をページが session_state に残す(下の実装で追加する)
    assert at.session_state["_resolved_version"] == A.KEIHAN_KITA
```

`tests/test_rev6_confirm.py:73,91` と `tests/test_pages_smoke.py` の `at.radio[0].set_value(...)` を全て `at.segmented_control[0].set_value(...)` に置換する（対象は Grep 済み: `test_rev6_confirm.py:73,91` / `test_pages_smoke.py:839,850,864,906,943`）。

`tests/test_pages_atehagi_ui.py:54` の `at.radio[0].set_value(version)` を `at.segmented_control[0].set_value(version)` に置換する。

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py tests/test_rev6_confirm.py tests/test_pages_atehagi_ui.py -q`
Expected: FAIL（`at.segmented_control` が空、`entry_mode` が無い）。

- [ ] **Step 3: 実装する**

`pages/01_経費・買掛・売掛.py:16` を差し替え:

```python
# 🔴 segmented_control は選択を解除でき、そのとき None を返す。None のまま下の
# if/elif/else に流すと else に落ちて「売掛」の画面が開いてしまうため、
# 明示的に既定へ戻す。
_MODES = ["小口", "買掛", "売掛"]
mode = st.segmented_control("入力の種類", _MODES, default=_MODES[0],
                            key="entry_mode") or _MODES[0]
```

`pages/07_資料作成・変換表.py:22-24` を差し替え:

```python
    # 🔴 segmented_control は選択を解除でき、そのとき None を返す。
    # `A.KEIHAN_KITA if label == "京阪北版" else A.KEIHAN_MINAMI` のような書き方だと
    # None が黙って南版に落ち、全枚数のあて紙で地区名が誤る。
    # 既定へ戻したうえで、対応表で引く。
    _VERSIONS = {"京阪北版": A.KEIHAN_KITA, "京阪南版": A.KEIHAN_MINAMI}
    version_label = st.segmented_control("版", list(_VERSIONS), default="京阪北版",
                                         key="keihan_version") or "京阪北版"
    version = _VERSIONS[version_label]
    # 版の取り違えは全枚数に影響するため、テストで固定できるよう解決結果を残す
    st.session_state["_resolved_version"] = version
```

`common/ui.py` の `_STYLE` の `</style>` 直前に追加:

```css
/* segmented_control(入力の種類・版): ●ではなくボタン全体を押せるように大きく */
[data-testid="stSegmentedControl"] button{
  min-height:44px !important; padding:.45rem 1.1rem !important;
  font-weight:700 !important;
}
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py tests/test_rev6_confirm.py tests/test_pages_atehagi_ui.py -q`
Expected: 全PASS。

- [ ] **Step 5: ミューテーションで検出力を確認**

`pages/07` の `or "京阪北版"` を外して Run: `python -m pytest tests/test_pages_smoke.py -q -k falls_back_to_kita`
Expected: **FAIL**。元に戻す。

`pages/01` の `or _MODES[0]` を外して Run: `python -m pytest tests/test_pages_smoke.py -q -k falls_back_to_petty`
Expected: **FAIL**。元に戻す。

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `357 passed`。

- [ ] **Step 7: コミット**

```bash
git add pages/01_経費・買掛・売掛.py pages/07_資料作成・変換表.py common/ui.py tests/
git commit -m "feat(ui): ラジオを segmented_control にしてボタン全体を押せるようにする

●の当たり判定ではなくボタン全体が押せるようになる。最小高さ44pxでスマホでも
押しやすい。segmented_control は選択解除で None を返すため、None のまま
else に落ちて 07 の版が南版に化ける(全枚数の地区名が誤る)・01 が売掛画面に
なるのを防ぐガードを入れ、テストで固定した。"
```

---

### Task 10: マスタ管理のボタン見た目を他ページに揃える

**Files:**
- Modify: `common/ui.py`（CSS のみ）
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: なし
- Produces: なし（見た目のみ）

**オーナー決定:** 05 は行ごとの削除の作りを**残す**（全選択→まとめて削除はマスタが全滅するため作らない）。揃えるのはボタンの形・色・アイコンだけ。

- [ ] **Step 1: 退行防止のテストを書く**

`tests/test_pages_smoke.py` の末尾に追記:

```python
def test_master_page_keeps_per_row_delete(db):
    """🔴 05 マスタ管理は行ごとの削除のまま。全選択→まとめて削除は作らない。
    マスタの削除は他の一覧と意味が違い(費目・配布員そのものが消える)、
    まとめて消せる経路を作るとチェック全部入り＋削除で全滅する。"""
    did = store.add_distributor("行ごとの人", db_path=db)
    at = _run("05_マスタ管理.py")
    keys = {b.key for b in at.button}
    assert f"del_distributor_{did}_btn" in keys          # 行ごとの削除は残っている
    assert not any(k and k.endswith("_bulk_del_btn") for k in keys)   # 一括削除は無い
    assert not any(c.key and c.key.endswith("_all") for c in at.checkbox)  # 全選択も無い
```

- [ ] **Step 2: テストを走らせて通ることを確認（既に満たしているはず）**

Run: `python -m pytest tests/test_pages_smoke.py -q -k keeps_per_row_delete`
Expected: PASS。落ちる場合は 05 に一括削除が混入しているので取り除く。

- [ ] **Step 3: CSS を揃える**

`common/ui.py` の既存の `[class*="st-key-mtrash-"] .stButton>button` ブロックを差し替え、他ページの削除ボタンと同じ見え方にする:

```css
/* 削除(ゴミ箱)は他ページの削除ボタンと同じ見え方に揃える(白地・赤字・薄い枠) */
[class*="st-key-mtrash-"] .stButton>button{
  background:#fff !important; color:#c0392b !important;
  border:1.5px solid #f0c8c2 !important; border-radius:10px !important;
  box-shadow:none !important; padding:.42rem .7rem !important; min-height:40px;
}
[class*="st-key-mtrash-"] .stButton>button:hover{
  background:#fdecea !important; border-color:#c0392b !important;
}
```

- [ ] **Step 4: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `358 passed`。

- [ ] **Step 5: コミット**

```bash
git add common/ui.py tests/test_pages_smoke.py
git commit -m "style(05): マスタ管理の削除ボタンの見た目を他ページに揃える

行ごとの削除の作りは残す(オーナー決定)。マスタの削除は費目・配布員そのものが
消えて過去データの表示が壊れるため、全選択→まとめて削除の経路は作らない。
その方針を退行防止テストで固定した。"
```

---

### Task 11: 起動batを社内LAN公開にする（依頼⑤の到達手段）

**Files:**
- Modify: `起動_大阪支社アプリ.bat`

**Interfaces:**
- Consumes: なし
- Produces: 8502 が `0.0.0.0` で待ち受け、起動時にLAN IPを画面に出す。

**オーナー決定:** 共有パスワードはかけない（同じWi-Fiの人は誰でも開ける状態になることを承知のうえ）。`APP_PASSWORD` を設定すればいつでも有効化できる実装は既にある（`common/auth.py`）。

- [ ] **Step 1: 起動引数を変える**

`起動_大阪支社アプリ.bat` の21行の `ArgumentList` を差し替える:

```
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath '%STREAMLIT%' -ArgumentList 'run','app.py','--server.port','8502','--server.address','0.0.0.0','--server.headless','true' -WorkingDirectory 'C:\Users\moro\posting-automation'"
```

- [ ] **Step 2: 起動後にスマホ用URLを出す**

`:ready` ラベル（33〜37行）を差し替える:

```
:ready
echo 起動しました。ブラウザを開きます。
echo.
echo ---------------------------------------------
echo  スマホから使う場合（同じWi-Fiに繋いでください）
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } ^| Select-Object -First 1 -ExpandProperty IPAddress)"`) do echo   http://%%I:8502/
echo.
echo  ※ 初回はWindowsのファイアウォールの確認が出ることがあります。
echo    「アクセスを許可する」を押してください。
echo ---------------------------------------------
echo.
start "" "%URL%"
timeout /t 5 >nul
exit /b 0
```

- [ ] **Step 3: 構文だけ確認する（実起動はしない）**

⚠️ **8502 は本番DBに繋がっているため、このタスクでは起動しない。** オーナーが戻られてから起動して確認する。
Run: `python -c "print(open(r'起動_大阪支社アプリ.bat', encoding='utf-8').read().count('0.0.0.0'))"`
Expected: `1`

- [ ] **Step 4: コミット**

```bash
git add 起動_大阪支社アプリ.bat
git commit -m "feat(bat): 社内LANからアクセスできるようにして起動時にスマホ用URLを出す

--server.address 0.0.0.0 で待ち受け、同じWi-Fiのスマホから
http://<PCのIP>:8502 で開けるようにする。実データのDBにそのまま登録される。
共有パスワードはかけない方針(オーナー決定)。必要になれば APP_PASSWORD を
設定するだけで既存のログインゲートが有効になる。"
```

---

### Task 12: カメラ撮影とスマホ幅のCSS（依頼⑤の画面側）

**Files:**
- Modify: `pages/01_経費・買掛・売掛.py:67-86, 93-107`
- Modify: `common/ui.py`（CSS）
- Test: `tests/test_pages_smoke.py`

**Interfaces:**
- Consumes: `ocr.extract_receipt(data, media_type, client=None)`（既存）
- Produces: `pages/01` の小口登録に `st.camera_input(key="petty_camera")` と読み取りボタン `key="petty_camera_ocr"`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pages_smoke.py` の末尾に追記:

```python
def test_petty_registration_has_camera_input(db):
    """🔴 依頼⑤。スマホでその場で撮って登録できること。"""
    at = _run(_EXPENSE_PAGE)
    assert not at.exception
    assert "petty_camera" in {c.key for c in at.get("camera_input")}


def test_camera_shot_is_read_as_jpeg(db, monkeypatch):
    """🔴 camera_input の戻り値はファイル名から MIME を決められないため、
    image/jpeg 固定で渡すこと。ocr.media_type_for に通すと拡張子が無く落ちる。"""
    from common import ocr

    seen = {}

    def _fake(data, media_type, client=None):
        seen["media_type"] = media_type
        return {"amount": 1200, "date": "2026-08-05", "item": "コーヒー"}

    monkeypatch.setattr(ocr, "extract_receipt", _fake)

    class _Shot:
        name = "camera_input"

        def getvalue(self):
            return b"\xff\xd8\xff\xe0dummy-jpeg"

    at = AppTest.from_file(os.path.join(ROOT, "pages", _EXPENSE_PAGE), default_timeout=30)
    at.run()
    at.session_state["petty_camera"] = _Shot()
    at.run()
    at.button(key="petty_camera_ocr").click().run()

    assert not at.exception
    assert seen["media_type"] == "image/jpeg"
```

- [ ] **Step 2: テストを走らせて落ちることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k "camera"`
Expected: FAIL（`petty_camera` が無い）。

- [ ] **Step 3: 実装する**

`pages/01_経費・買掛・売掛.py` の `_ocr_files`（67行）のシグネチャと本体を差し替える:

```python
def _ocr_files(files, reader, media_type=None):
    """複数ファイルをAIで読み取り、下書きリストを返す。失敗しても止めない(#7の保険)。

    media_type を渡すと拡張子からの判定を使わない。カメラ撮影(st.camera_input)は
    戻り値のファイル名が固定で拡張子を持たないため、image/jpeg を明示して渡す。
    """
    drafts = []
    prog = st.progress(0.0)
    for i, f in enumerate(files):
        name = getattr(f, "name", "") or "camera.jpg"
        try:
            mt = media_type or ocr.media_type_for(name)
            d = reader(f.getvalue(), mt, client=None)
        except Exception as e:  # noqa: BLE001
            d = {"amount": None, "_error": str(e)}
        d["_file"] = name
        drafts.append(d)
        prog.progress((i + 1) / len(files))
    prog.empty()
    n_ok = sum(1 for d in drafts if d.get("amount"))
    if n_ok < len(drafts):
        st.warning(f"{len(drafts)}件中 {n_ok}件のみ金額を取得できました。"
                   "（AI未設定/読取失敗分は手入力できます）")
    else:
        st.success(f"{len(drafts)}件を読み取りました。内容を確認・修正して登録してください。")
    return drafts
```

⚠️ `reader` は `monkeypatch` で差し替えたモジュール属性を見る必要があるため、呼び出し側は
`ocr.extract_receipt` を**その場で参照する**こと（`_ocr_files(ups, ocr.extract_receipt)` は
呼び出し時に解決されるので既存のままで良い）。

小口登録タブ（95〜106行）の `ups = st.file_uploader(...)` の直後に追加:

```python
        # スマホからその場で撮って登録できるようにする(社内Wi-Fiで 8502 を開いた場合)
        shot = st.camera_input("その場で撮る（スマホ向け）", key="petty_camera")
        if shot is not None and st.button("撮った写真をAIで読み取る", key="petty_camera_ocr"):
            # camera_input の戻り値はファイル名が固定で拡張子から MIME を決められないため
            # image/jpeg を明示する
            drafts = _ocr_files([shot], ocr.extract_receipt, media_type="image/jpeg")
            st.session_state.pop("petty_draft", None)
            st.session_state.pop("petty_bulk", None)
            if len(drafts) == 1 and drafts[0].get("amount"):
                st.session_state["petty_draft"] = {"date": drafts[0].get("date"),
                                                   "amount": drafts[0].get("amount"),
                                                   "item": drafts[0].get("item")}
            else:
                st.session_state["petty_bulk"] = drafts
```

`common/ui.py` の `_STYLE` の `</style>` 直前に追加:

```css
/* ===== スマホ幅(社内Wi-Fiからスマホで開いたとき) ===== */
@media (max-width: 640px){
  .block-container{ padding:1rem .8rem 2.4rem !important; }
  [data-testid="stSidebar"]{ width:180px !important; min-width:180px !important; }
  /* 横並びの列は縦積みにする(操作バーのボタンが潰れないように) */
  [data-testid="stHorizontalBlock"]{ flex-direction:column !important; gap:.45rem !important; }
  [data-testid="stHorizontalBlock"] > div{ width:100% !important; }
  .stButton>button, [data-testid="stDownloadButton"]>button{
    width:100% !important; min-height:44px;
  }
  /* 表は画面からはみ出さず、中で横スクロールさせる */
  [data-testid="stDataFrame"], [data-testid="stDataEditor"], .printable{
    overflow-x:auto !important;
  }
  [data-testid="stHeading"] h1, .stMarkdown h1{ font-size:1.15rem !important; }
}
```

- [ ] **Step 4: テストを走らせて通ることを確認**

Run: `python -m pytest tests/test_pages_smoke.py -q -k camera`
Expected: 2 passed。

- [ ] **Step 5: ミューテーションで検出力を確認**

`media_type="image/jpeg"` を外して Run: `python -m pytest tests/test_pages_smoke.py -q -k camera_shot_is_read_as_jpeg`
Expected: **FAIL**。元に戻す。

- [ ] **Step 6: 全テストを走らせる**

Run: `python -m pytest -q`
Expected: `360 passed`。

- [ ] **Step 7: コミット**

```bash
git add pages/01_経費・買掛・売掛.py common/ui.py tests/test_pages_smoke.py
git commit -m "feat(01): 小口にカメラ撮影を追加しスマホ幅のレイアウトを整える

社内Wi-Fiでスマホから8502を開き、その場でレシートを撮って登録できるように
する。camera_input はファイル名から MIME を決められないため image/jpeg を
明示して渡す。640px以下では列を縦積みにしてボタンを潰さない。"
```

---

## 完了後の状態と、オーナーが戻られてから行うこと

このプランを完走すると `feature/ui-unify-2026-08` に全12タスクがコミットされ、テストは **360件緑**（ベースライン317 + 新規43）になる。

**戻られてから一緒にやること（この計画の範囲外）:**

1. **8502 をプロセスごと再起動**（`common/*.py` を変更したため、batの再クリックでは反映されない）
2. **5ページの目視確認**（`section_export` 撤去で全ページの見た目が同時に変わるため）
3. **報告書のExcel印刷プレビューでG列が出ることの確認**（Task 1 Step 6 で出力したファイル、または実データで生成した報告書）
4. **スマホからのアクセス確認**（bat が表示するURLで開く／ファイアウォールの許可）
5. **master へのマージ判断**

---

## Self-Review

**1. 仕様の網羅** — 設計書の各章とタスクの対応:

| 設計書 | タスク |
|---|---|
| 3章 印刷範囲（①） | Task 1 |
| 4章 共通部品 `selectable_list` | Task 2 |
| 4章 共通部品 `list_action_bar`（DL・削除） | Task 3 |
| 4章 印刷の動き・合計のパースガード | Task 4 |
| 4章 id列を持たない一覧（03・06） | Task 2（`id_col=None`）・Task 3（ガード）・Task 7（適用） |
| 4章 各ページへの適用 | Task 5（01）・Task 6（02）・Task 7（03・06） |
| 4章 02 のZIP遅延生成 | Task 6 |
| 4章 既存部品の行き先 | Task 8 |
| 5章 クリックしやすさ・Noneガード | Task 9 |
| 2章 確定事項5（05は行ごと維持） | Task 10 |
| 6章 LAN公開 | Task 11 |
| 6章 カメラ・スマホCSS | Task 12 |
| 7章 テスト方針（ミューテーション） | 各タスクのミューテーション手順 |

漏れなし。

**2. プレースホルダ** — 「TBD」「適切にエラー処理」等は無い。全ステップに実コードと実コマンドがある。Task 1 Step 6 の `fitToHeight` 目視確認は設計書に明記した既知の未確認事項で、確認手順とフォールバック（`fitToHeight=1`）を書いてある。

**3. 型・名前の一貫性** — `selectable_list` は全タスクで `(DataFrame, list[int])` を返す。`list_action_bar` の引数名（`key` / `title` / `filename` / `section` / `id_col` / `delete_fn` / `delete_note` / `extra`）はTask 3の定義とTask 5〜7の呼び出しで一致。`extra` のシグネチャは Task 3 のテスト（`lambda c, rows, ids`）と Task 6 の実装（`_zip_button(container, rows, ids)`）で一致。`print_total` は Task 4 で定義し Task 4 内でのみ使用。data_editor のkey規約 `f"{key}_select_{0|1}"` は Task 2 の定義と Task 5・6 のテスト修正で一致。

**修正済みの不整合:** Task 4 の `_print_table_html` にあった `<table>>` の誤記を `<table>` に修正した。
