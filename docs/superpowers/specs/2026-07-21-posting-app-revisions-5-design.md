# 配布コスト管理アプリ 第5弾 設計書：一覧の一括操作（チェック選択→選択Excel／選択削除）

- 日付: 2026-07-21
- 対象: `pages/01_経費・買掛・売掛.py`（小口・買掛・売掛の3タブ）／`pages/02_業務委託登録.py`（登録済み一覧タブ）／`common/ui.py`（共通部品）
- ブランチ: `feature/revisions-5`（`feature/revisions-4` から分岐。第3・4・5をまとめて実機確認→一括master）
- 前提: streamlit 1.58.0。データ層（`posting_store` の削除関数）は変更しない。

## 背景・目的

小口・買掛・売掛・業務委託登録の「登録済み一覧」で、削除が**行ごとの削除ボタン**（`confirm_delete` を行数ぶん）になっていて使いにくい。業務委託登録には既に「選択」チェックボックス＋選択Excelがあるが、削除だけ行ごとのまま。

**目的**: 4画面すべてを「チェックで複数選択 → 下のボタンでまとめて操作（選択した行をExcel／選択した行を削除）」に統一する。行ごとの削除ボタンは廃止する。

## スコープ

- **小口・買掛・売掛**（`pages/01`）: 各「登録済み一覧」タブに**選択チェックボックス**を導入し、下に〔選択した行をExcelで保存〕〔選択した行を削除〕を並べる。行ごと削除（`_delete_rows_ui`）は廃止。既存の**「一覧全体をExcel/印刷」（`section_export`）は残す**（経理提出用・全件）。
- **業務委託登録**（`pages/02` 登録済み一覧）: 既存の〔報告書まとめてZIP〕〔選択した行を一覧Excel〕は**残す**。下部の**行ごと「請求を削除」セクション（divider＋forループ）を廃止**し、〔選択した行を削除〕に置換。
- **マスタ管理（pages/05）は対象外**（第4弾のトグル/削除UIのまま）。
- データ層（`posting_store` / スキーマ）変更なし。

## 共通部品（`common/ui.py` に追加）

3つの純粋なUI部品を足し、4画面で使い回す（DRY）。

### 1. `checkbox_list_editor(disp_rows, *, key, select_col="選択") -> pd.DataFrame`
- `disp_rows`（list[dict] か DataFrame）の先頭に `select_col`（`CheckboxColumn`・既定False）を付け、他の全列は `disabled` にした `st.data_editor` を描画し、編集後DataFrameを返す。
- 呼び出し側が「どの列が選択か」「どのidか」を解釈する。

### 2. `selected_rows_excel_button(edited_df, *, key, filename, select_col="選択", label=None, container=None)`
- `edited_df` の `select_col==True` の行だけを、`select_col` を除いた列でExcel化し、`freeze_xlsx_bytes` を通して `download_button` を出す（内容不変ならURL不変・404防止）。
- 選択0件のときは `disabled`。ラベル既定＝「選択した行をExcelで保存（N件）」。

### 3. `bulk_delete_action(selected_ids, *, delete_fn, section, key, noun="件", container=None)`
- 「選択した行を削除（N件）」ボタン（選択0件なら `disabled`）。押すと確認待ちを session_state に立て、**押した時点の選択idをスナップショット**する（押下→確認の間に選択が変わっても、確認時のidで消えないよう固定）。
- 確認UIは「⚠️ 選択したN件を削除しますか？」＋〔はい、削除する〕〔やめる〕を**全幅**で出す（`confirm_delete` と同じ思想。狭い列に潰さない）。
- 〔はい〕で `for i in ids: delete_fn(i)` → `flash(f"{N}件を削除しました", section)` → `st.rerun()`。
- `container` を渡すとボタンだけそこ（列）に置き、確認UIは呼び出し位置＝全幅に出す。

> 確認のスナップショット例:
> ```python
> pending = f"_bulkdel_pending_{key}"
> ids = st.session_state.get(pending)
> if ids:  # 確認待ち
>     st.warning(f"⚠️ 選択した{len(ids)}{noun}を削除しますか？")
>     c1, c2, _ = st.columns([1, 1, 4])
>     if c1.button("はい、削除する", type="primary", key=f"{key}_ok"):
>         for i in ids: delete_fn(i)
>         st.session_state.pop(pending, None)
>         flash(f"{len(ids)}{noun}を削除しました", section)
>         st.rerun()
>     if c2.button("やめる", key=f"{key}_no"):
>         st.session_state.pop(pending, None); st.rerun()
>     return
> target = container if container is not None else st
> if target.button(f"選択した行を削除（{len(selected_ids)}{noun}）",
>                  key=f"{key}_btn", disabled=not selected_ids):
>     st.session_state[pending] = list(selected_ids)
>     st.rerun()
> ```

## 画面の組み立て

### 小口・買掛・売掛（pages/01 の各一覧タブ）
現状（例：小口）:
```python
section_export(_disp, "小口一覧", key="petty")
_delete_rows_ui(_rows, _disp, "del_petty", store.delete_petty_cash, ...)
```
変更後:
```python
section_export(_disp, "小口一覧", key="petty")     # 全件Excel/印刷は残す
edited = checkbox_list_editor(_disp_with_id, key="petty_select")   # _disp に No.(id) 列を含める
selected_ids = [int(r["No."]) for _, r in edited.iterrows() if r["選択"]]
st.caption(f"選択中：{len(selected_ids)}件")
b1, b2 = st.columns(2)
selected_rows_excel_button(edited, key="petty_sel_xlsx", filename="小口_選択一覧", container=b1)
bulk_delete_action(selected_ids, delete_fn=store.delete_petty_cash,
                   section="petty", key="petty_bulk_del", container=b2)
```
- `_disp` に既に表示用の列がある。行の削除に使う**id（No.列）を表示行に含める**必要がある（現状 `_delete_rows_ui` は `_rows`(生データ)から id を取っていた）。表示行に `"No."` として id を持たせ、`disabled` 列に含める。
- 買掛=`store.delete_payable`／売掛=`store.delete_receivable`／section=`payable`/`receivable`、keyは `pay_*`/`recv_*` で一意化。
- `_delete_rows_ui` は3タブとも使わなくなるので削除（他から未使用を確認のうえ）。

### 業務委託登録（pages/02 登録済み一覧）
- 既存の `edited`（`contract_list_editor`）と `selected_ids` はそのまま使う。
- 既存の b1（ZIP報告書）・b2（選択一覧Excel）は残す。
- **下部の「請求を削除」セクション（`st.divider()`＋`st.markdown("**請求を削除**")`＋`for inv in invoices:` の `confirm_delete` ループ）を削除**し、選択削除ボタンに置換:
  ```python
  bulk_delete_action(selected_ids, delete_fn=store.delete_contract_invoice,
                     section="invoice_list", key="invoice_bulk_del")
  ```
  （b1/b2 の並びの下、または b2 の隣に置く。「配布員別 報酬合計」より上。）

## テスト方針（TDD）

- 共通部品の純ロジック/描画を `AppTest` と小さなユニットで守る:
  - `bulk_delete_action`: 選択idをスナップショットして確認→はいで `delete_fn` が各idに呼ばれる（スパイ）／やめるで呼ばれない／選択0件はボタン `disabled`。確認は全幅（`button_container` 経由）。
  - `selected_rows_excel_button`: 選択行だけがExcel化される（`select_col` 除外）／0件は `disabled`。
  - `checkbox_list_editor`: 先頭に選択列、他列 `disabled`。
- 画面（AppTest・実データDBのコピー相当の一時DB＋`POSTING_DB_PATH`）:
  - 小口/買掛/売掛/業務委託の各一覧で、`session_state[<editor_key>]` に選択を注入（`{"edited_rows": {row: {"選択": True}}, ...}`＝第4弾までで実証済みの手法）→ 選択削除→確認→はい で、**選んだ行だけDBから消える**／他は残る。
  - 行ごとの削除ボタン（`del_petty_*` 等・`del_inv_*`）が**もう無い**こと。
  - 小口/買掛/売掛で「一覧全体をExcel/印刷」（`section_export`）が**残っている**こと。

## 既知の地雷（踏襲）

- **`common/*.py` を変えたら 8502 をプロセスごと停止して再起動**（本日のAttributeErrorの原因＝古いモジュールキャッシュ）。
- Excel出力は `freeze_xlsx_bytes()` を通す（内容不変ならDL URL不変・404防止）。
- `flash(msg, section=...)` ＋ `show_flash(section)` の対で、操作したタブにだけ成功メッセージ（タブは1実行で全描画されるため section 必須）。
- `st.data_editor` の選択は AppTest では `session_state[key] = {"edited_rows": {...}, "added_rows": [], "deleted_rows": []}` で再現できる。

## スコープ外

- マスタ管理（pages/05）のUI。
- 一括削除のUndo。
- 「一覧全体をExcel/印刷」の廃止（オーナー判断で残す）。
- デモ画面の外部共有・公開サーバー化（別途フェーズ2で相談）。
