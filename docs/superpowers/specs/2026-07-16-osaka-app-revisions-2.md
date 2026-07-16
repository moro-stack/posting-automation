# 大阪支社アプリ 改修仕様（2026-07-16・第2弾）

配布コスト管理アプリ（`posting-automation`・Streamlit・8502）への機能追加。
オーナー実運用フィードバック。**締切 2026-07-17 10:00**。

## 対象と前提
- 既存ページ: `01_経費・買掛・売掛` / `02_業務委託登録` / `03_号別明細` / `04_経理提出出力` / `05_マスタ管理`
- 既存の作法に合わせる（`common/ui.py` の `period_picker` / `nice_table` / `section_export`、`common/posting_store.py`、`common/invoice_excel.py`）。
- DB は SQLite（`data/posting.db`）。旧DBは `_ensure_schema` で自動マイグレーションする既存パターンに倣う。
- ブランチ: master 直（既存も master 運用）。ただし着手時に作業ブランチを切る。

---

## 要件① 号別明細：「その他」が何の案件かを一覧で見える化

### 背景
号(案件)に catch-all の「その他」がある。ここに小口・買掛・売掛・業務委託などを入れると、
号別明細では金額が合算されるだけで**中身が何だったか区別できない**。

### 仕様
号別明細ページに **「明細（内訳）一覧」** セクションを追加する。選択中の号に紐づく各エントリを
**1行＝1データ**で、内容ラベル付きで表示する。

表示列: `区分` / `内容` / `金額` / `日付`

| データ源 | 区分 | 内容(ラベル)の取得元 | 日付の取得元 |
|---|---|---|---|
| receivables(売掛) | 売上 | note | month |
| petty_cash(小口) | 原価・小口 | memo（費目名を接頭に付す） | date |
| payables(買掛) | 原価・買掛 | note or vendor_name | date or month |
| contract_invoice_lines(業務委託) | 原価・業務委託 | remark(種別) | 紐づく invoice の issue_date |
| issue_manual_costs(直接入力) | 原価・直接入力 | content | work_date |

- **登録フォームは変更しない**。内容ラベルは既存の memo/note/content をそのまま拾う（＝"登録"は既にメモ欄でできており、欠けていたのは"一覧表示"）。
- 期間フィルタ（`period_picker`）の絞り込み結果と整合させる（既に集計で使っている lo/hi を流用）。
- この一覧も `section_export`（Excel/印刷）に対応。
- 表示位置: サマリー（配布原価/売上/利益）の下、既存の「配布員代」「雑費」expander の前に配置。折りたたみ（expander）で出す。

### ストア/ロジック（TDD対象）
- `posting_logic.issue_breakdown_rows(...)` （新規・純関数）: 上表のとおり各データ源のリストを受け取り、
  表示用の行 list[dict]（区分/内容/金額/日付）に正規化して返す。号別明細ページから既取得のデータを渡す。
  - 金額は `_num` を通す。日付が無いものは空文字。並び順は 売上→原価（小口/買掛/委託/直接入力）。

---

## 要件② 業務委託ページ

### (a) 配布員の絞り込み入力
- 現状 `st.selectbox("配布員", ...)` は入力で絞り込み可能。**作り替えはしない**。
- プレースホルダ/ヘルプで「入力で絞り込めます」と明示するのみ。新規追加はマスタ管理のまま。

### (b)(c) タブ分け・期間フィルタ・ソート
- ページを **`st.tabs(["✒️ 登録", "📋 登録済み一覧"])`** に分割（01ページと同じ作法）。
  - 登録タブ: 既存の登録フォーム＋登録直後の即時Excel出力（現状維持）。
  - 一覧タブ: 下記(d)(e)を含む一覧。
- 一覧タブ上部に **期間フィルタ**（`period_picker`、対象は請求の `issue_date`）。
- **並べ替え**: radio/selectbox で `並び順 = 発行日(新しい順) / 発行日(古い順) / 配布員名`。
  - 既定は発行日の新しい順（現状の `list_contract_invoices` は id DESC）。

### (d) チェックで複数選択 → 出力
- 一覧を `st.data_editor` で表示し、先頭に **`選択`（CheckboxColumn）** を置く。他列は読み取り専用
  （`disabled`）: No./配布員/発行日/配布業務期間/請求額/出力状況。
- 選択行に対する操作ボタン2つ:
  1. **「選択した請求の報告書をまとめてダウンロード(ZIP)」**
     - 各請求ごとに `invoice_excel.build_invoice_xlsx` で1ファイル生成し、`zipfile` で1つにまとめて `download_button`。
     - ファイル名: `業務完了報告書兼請求書_{配布員}_{発行日}.xlsx`、ZIP名 `業務完了報告書_選択{n}件.zip`。
     - 6明細超の請求はスキップし、警告に「No.X は明細6行超のためスキップ」と列挙（既存の6行制限に整合）。
     - ダウンロード実行時（`download_button` が True を返した run）に、対象請求へ **出力印**(下記e)を付ける。
  2. **「選択した行を一覧Excelで保存」** … 選択行の表を `section_export` 相当で1シート出力。
- 選択0件のときは両ボタン disabled。

### (e) 出力済みの注意表示
- `contract_invoices` に **`last_exported_at TEXT`** 列を追加（`_ensure_schema` で自動 ALTER）。
- 報告書をダウンロードした請求に、その時刻を記録する（単一の出し直し・ZIP一括の両方）。
- 一覧の `出力状況` 列に、`last_exported_at` があれば **「⚠️ N日前(YYYY-MM-DD)に出力済み」**、無ければ空。
  - 経過日数 N は「今日 - 出力日」。0日は「本日出力済み」。
  - **ブロックはしない**（注意のみ）。

### ストア（TDD対象）
- `store.mark_contract_invoice_exported(invoice_id, *, now=None)`: `last_exported_at` を更新。
- `list_contract_invoices` の返却に `last_exported_at` が含まれる（`SELECT *` なので列追加で自動的に入る）。
- `store.add_contract_invoice` 既存の並びは維持。
- 表示日数計算 `posting_logic.days_since(iso_str, today=None)` （新規・純関数）: 何日前かを返す。今日基準。

---

## テスト方針
- **TDD（ストア/ロジック層）**:
  - `test_posting_store.py`: `mark_contract_invoice_exported` で `last_exported_at` が入る／`list_contract_invoices` に出る／旧DB(列なし)からの自動マイグレーション。
  - `test_posting_logic.py`: `issue_breakdown_rows`（各データ源が正しい区分/内容/金額/日付になる・並び順）、`days_since`（今日=0、過去=正、None=None）。
- **UI は実機確認**（8502・Playwright/オーナー目視）:
  - 号別明細で その他 号に小口2件＋売掛1件を入れ、内訳一覧に内容ラベル付きで出る。
  - 業務委託タブ分割・期間フィルタ・ソート・チェック複数選択→ZIP・一覧Excel・出力済み警告。
- 既存テスト（全152件想定）が壊れないこと。

## 非対象（YAGNI）
- 配布員の自由入力/その場新規追加（オーナー: 絞り込みだけでよい）。
- 出力履歴の全件保持（最終出力日時のみ。何日前が出れば足りる）。
- 複数請求を1枚に合算する報告書（テンプレ6行制限のため 1請求=1ファイルZIP を採用）。

## リスク/注意
- **`common/*.py` を変更したら streamlit 再起動が必須**（既知）。
- Excel バイト列は `freeze_xlsx_bytes` で安定化（DLの404回避・既存方針）。ZIP内の各xlsxも freeze 済みバイトを使う。
- `st.download_button` は毎回データを用意する必要がある。ZIPは選択が変わるたびに再生成（件数は小さい想定）。
