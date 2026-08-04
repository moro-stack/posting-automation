# 配布コスト管理アプリ 第6弾 設計書：確認文言統一＋号別明細調整＋原価・売上まとめ新ページ

- 日付: 2026-07-21
- 対象: `common/ui.py`／`common/posting_logic.py`／`pages/01_経費・買掛・売掛.py`／`pages/03_号別明細.py`／`app.py`／新規 `pages/06_原価・売上まとめ.py`
- ブランチ: `feature/revisions-6`（`feature/revisions-5` から分岐。第3〜6をまとめて実機確認→一括master）
- 前提: データ層（`posting_store`／スキーマ）は変更しない。既存の集計・store関数を再利用。

## 4つの変更

### ① 確認ボタンを「はい／いいえ」に統一
はい/いいえ形式の**確認ダイアログ**のボタン文言を統一する。対象：
- `common/ui.py` `confirm_delete`（429/434行）：「はい、削除する」→**「はい」**、「やめる」→**「いいえ」**。
- `common/ui.py` `bulk_delete_action`（492/498行）：「はい、削除する」→**「はい」**、「やめる」→**「いいえ」**。
- `pages/01` の重複チェック確認 ×3（petty/pay/recv の「⚠️ 同様の内容が登録済みです。それでも登録しますか？」）：「はい、登録する」→**「はい」**、「やめる」→**「いいえ」**。

**対象外**（はい/いいえの問いではないので変えない）：
- OCR一括登録の「全部登録／やめる」（`petty_bulk_cancel`/`pay_bulk_cancel`）。
- マスタ編集/新規登録ダイアログの「やめる」（`pages/05` のフォームcancel）。

### ② 号別明細：配布員代（業務委託）の内訳に「支払日（発行日）」を追加
- `pages/03` の業務委託内訳 `_con_disp` に **「支払日」＝ `l.get("issue_date")`** 列を（先頭に）追加。`contract_lines` は既に `issue_date` を持つ。
- 号原価まとめExcelの「業務委託」シートの列にも「支払日」を含める。
- 直接入力（`_man_disp`）・雑費は既に日付あり＝変更不要。

### ③ 買掛を号別明細の集計から外す
- `pages/03` の `aggregate_issue(...)` に **`payables=[]`** を渡す（＝配布原価から買掛除外。`cost_groups` は不変で misc=小口のみになる）。
- 雑費内訳 `_misc` から**買掛の行（`for r in payables:` ループ）を削除**（小口のみ）。
- 雑費expanderの見出し「雑費の内訳（小口＋買掛）」→**「雑費の内訳（小口）」**、キャプション「雑費 ＝ 小口 X ＋ 買掛 Y」→**「雑費 ＝ 小口 X」**。号原価まとめExcelの雑費シートも小口のみ。
- コスト計算に使わなくなる `payables = filter_rows_by_period(...)` 行と `pay_total` は削除（`receivables` は売上で引き続き使用）。
- ⚠️ `home.py` は `aggregate_issue(payables=pays)` で買掛を含むが、**`app.py` の `st.navigation` に未登録＝画面に出ない**ため本改修の対象外（スコープ外・据え置き）。

### ④ 新ページ「KPS大阪支社 原価・売上まとめ」
- 新規 `pages/06_原価・売上まとめ.py`。**`app.py` の `pages` リストで号別明細の"前"に** `st.Page("pages/06_原価・売上まとめ.py", title="原価・売上まとめ", icon=":material/summarize:")` を挿入（並びはリスト順で決まる＝ファイル名の番号は無関係）。
- 期間指定（`period_picker`）。**全案件横断**（`project_id` 指定なしで全件取得）。
- **上部**：売上合計（売掛）／**原価合計（買掛＋全案件の 業務委託＋直接入力＋小口）**／利益 を大きく表示。
- **下部：明細リスト**（列＝日付・区分・項目・案件・金額）＋`section_export`（Excel/印刷）。
- 区分＝`売上`（売掛）／`買掛`／`小口`／`業務委託`／`直接入力`。
- 純ロジックは `common/posting_logic.py` に追加（下記）。二重計上なし（買掛は号別明細から外し、この全社ページに一本化）。

## 新しい純関数（`common/posting_logic.py`）

```
company_summary_totals(*, receivables, payables, petty, contract_lines, manual) -> {"sales", "cost", "profit"}
  sales = Σ receivables.amount
  cost  = Σ payables.amount + Σ petty.amount + Σ contract_lines.amount + Σ manual.amount
  profit = sales - cost

company_summary_rows(*, receivables, payables, petty, contract_lines, manual,
                     id2proj, id2vendor, id2cat, id2client, id2dist) -> list[dict]
  各ソースを {区分, 日付, 項目, 案件, 金額(int)} に正規化して結合。
  - 売上   : 区分"売上"   日付=month        項目=売掛先(id2client) 案件=id2proj 金額
  - 買掛   : 区分"買掛"   日付=date or month 項目=取引先(vendor_name or id2vendor) 案件=id2proj 金額
  - 小口   : 区分"小口"   日付=date         項目=費目(id2cat)(+memo) 案件=id2proj 金額
  - 業務委託: 区分"業務委託" 日付=issue_date   項目=配布員(id2dist) 案件=id2proj 金額
  - 直接入力: 区分"直接入力" 日付=work_date    項目=作業(content)     案件=id2proj 金額
```
金額は数値（表示の¥整形は画面側）。日付昇順など並びは画面側で。

## 期間フィルタ（画面側）
ソースごとに日付キーが違うので既存の `filter_rows_by_period` / `in_period` を使う：
receivables=month／payables=month（or date）／petty=date／contract=issue_date／manual=work_date。

## テスト方針（TDD・タスクごとに別テストファイルで衝突回避）
- ①: `confirm_delete`/`bulk_delete_action` のボタンラベルが「はい」「いいえ」であること／dup-check確認も。既存の `"はい、削除する"` 依存テスト（`tests/test_pages_smoke.py:445` 等）を新ラベルへ更新（意味は不変）。
- ④-logic: `company_summary_totals`（売上/原価/利益）と `company_summary_rows`（区分別の行生成・案件/項目名解決）を純関数で検証。
- ②③: `pages/03` を AppTest（実データ相当の一時DB）で。業務委託内訳に支払日列が出る／雑費に買掛が出ない・配布原価に買掛が含まれない（買掛を1件入れても genka が増えない）。
- ④-page: `pages/06` を AppTest。売上/原価/利益が出る・買掛が原価明細に出る・全案件横断。

## 既知の地雷（踏襲）
- `common/*.py` 変更後は 8502 をプロセスごと停止して再起動（本日のAttributeError＝再起動漏れ）。
- Excelは `freeze_xlsx_bytes` を通す。`flash(section=)`＋`st.rerun()`。data_editorのAppTest選択は同runに束ねる。
- ラベル変更でキー参照テストは壊れない（キーは不変）。ラベル参照のテストのみ更新する。

## スコープ外
- `home.py`（nav未登録）。マスタ管理・業務委託登録の削除UI（第4・5弾のまま）。デモ公開/ログイン（フェーズ2）。
