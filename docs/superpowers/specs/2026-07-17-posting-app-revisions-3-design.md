# 大阪支社アプリ 改修（第3弾）設計書

- 日付: 2026-07-17
- 対象: `posting-automation`（配布コスト管理アプリ・Streamlit・8502）
- 前提: 第2弾（`3158eba`）が master にマージ済み・全73テストパスの状態から着手する

## 背景

オーナーが実運用して出た要望3系統。

1. 号別明細の業務委託の内訳に**配布員名が出ない**ので、誰の分の費用か号の画面から分からない。小口も同様。
2. マスタの項目不足。買掛の原本区分を毎回選び直している／業務委託先の振込先・支払形態を管理する場所がない。
3. 登録した行を**画面から消せない**（DB側に削除処理はあるが画面に出ていない）。追加・削除したときの反応も薄い。

## 確定した仕様（2026-07-17 オーナー確認済み）

| # | 論点 | 決定 |
|---|------|------|
| 1 | ①「小口も同様の機能」の意味 | 小口登録に**「配布員」欄（任意・マスタから選択）**を追加し、号別明細の雑費内訳と小口一覧に配布員名を表示する。**買掛には追加しない** |
| 2 | 買掛の原本区分の自動反映 | 取引先は**自由入力のまま**。入力/AI読み取りされた会社名が買掛先マスタと**名前一致したら原本区分を自動セット**（手で変更可） |
| 3 | 日当の「業務ごと」の単位 | **自由入力の業務名ごと**（例: 丁合・配布 ¥8,000／ポスティング ¥7,500） |
| 4 | 削除ボタンの挙動 | **確認を挟む**（削除→「削除しますか？」→はい／やめる→「削除しました」） |
| 5 | 削除ボタンの範囲 | 小口・買掛・売掛の一覧／業務委託の登録済み一覧／マスタ管理の5タブすべて |
| 6 | 振込先の形式 | **自由入力の1欄**（銀行名・支店・口座を丸ごとテキスト） |
| 7 | 支払形態と既存「区分」の関係 | **別項目として両方残す**（区分=雇用形態／支払形態=報酬の計算方法） |
| 8 | マスタ削除で過去データが欠ける問題 | **停止中方式**。使用実績があれば物理削除せず `active=0` にする。過去データの名前は引き続き表示される |
| 9 | 停止中の見せ方 | 一覧には**有効なものだけ**表示。停止中は**折りたたみの中**に置き、そこから「有効に戻す」 |
| 10 | 停止中方式の適用範囲 | **5マスタすべて**（案件／費目／買掛先／売掛先／業務委託）で同じ挙動に揃える |

## データモデル

すべて既存の自動マイグレ方式（`_ensure_schema` 内の `PRAGMA table_info` → `ALTER TABLE`）で追加する。**既存データは保持される。**

### 列の追加

| テーブル | 列 | 型 | 用途 |
|---|---|---|---|
| `petty_cash` | `distributor_id` | INTEGER | 小口の配布員（任意・NULL可） |
| `payables_vendors` | `default_original_status` | TEXT | 既定の原本区分 |
| `distributors` | `bank_info` | TEXT | 振込先（自由入力1欄） |
| `distributors` | `pay_type` | TEXT | 支払形態（日当／歩合／時給／月給） |

`distributors.kind`（区分: 業務委託／自社社員／アルバイト）は**変更せず残す**。

### 新規テーブル

```sql
CREATE TABLE IF NOT EXISTS distributor_daily_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    distributor_id INTEGER NOT NULL,
    work_name TEXT NOT NULL,      -- 自由入力の業務名（例: 丁合・配布）
    amount INTEGER NOT NULL DEFAULT 0
);
```

支払形態が「日当」の配布員に対して、業務名ごとの日当金額を 0〜N 行持つ。

### store に追加する関数

- `update_petty_cash(row_id, ...)` は不要（小口は追加/削除のみ）。`add_petty_cash` に `distributor_id` 引数を追加
- `add_payables_vendor` / `update_payables_vendor` に `default_original_status` を追加
- `add_distributor` / `update_distributor` に `bank_info` / `pay_type` を追加
- `list_daily_rates(distributor_id)` / `replace_daily_rates(distributor_id, rates)` / `delete_daily_rates_for(distributor_id)`
- `find_vendor_by_name(name)` — 買掛の原本区分オートセット用（名前の完全一致）
- `count_master_usage(master, row_id)` — マスタの使用件数を数える（停止中方式の判定用）
- `deactivate_*` は既存の `update_*(active=0)` を使うため新設しない

## ロジック（純関数・`common/posting_logic.py`）

画面から切り離してテストできるよう、判定は純関数に置く。

- `resolve_original_status(vendor_name, vendors) -> str | None`
  取引先名がマスタと一致したら既定の原本区分を返す。一致しなければ None。
- `master_delete_action(usage_count) -> "delete" | "deactivate"`
  使用実績 0 なら物理削除、1件以上なら停止中。
- 表示行の組み立て（配布員名の差し込み）は既存の `_with_label` と同じ方式でページ側に置く。

## 画面

### ① 号別明細（`pages/03_号別明細.py`）

- 業務委託の内訳表：**種別の左に「配布員」列**。請求ヘッダの `distributor_id` → 名前で引く（`list_distributors()` は停止中も含むため、辞めた配布員の名前も出続ける）
- 雑費の内訳表：**左端に「配布員」列**。小口行のみ値が入り、**買掛行は空欄**（買掛に配布員を持たせない方針のため。オーナー確認済み）
- 号原価まとめのExcel出力も同じ列構成に追随させる

### ① 小口登録（`pages/01_経費・買掛・売掛.py`）

- 登録フォームに「配布員（任意）」の selectbox を追加（`(なし)` ＋ 有効な配布員）
- 登録済み一覧に「配布員」列を追加

### ② 買掛登録（同ページ）

- 取引先名が買掛先マスタと一致したら、原本区分の selectbox の初期選択を既定値にする
- 一致した場合は「マスタの既定を反映しました」と caption を出す（勝手に変わったように見せない）

### ② マスタ管理（`pages/05_マスタ管理.py`）

- タブ名「配布委託先」→**「業務委託」**。画面内の文言（`配布委託先はまだ登録されていません` など）もあわせて変更
- 買掛先タブ：追加フォームに「既定の原本区分」selectbox を追加。一覧にも列を追加
- 業務委託タブ：追加フォームに「振込先」（`text_area`）・「支払形態」（selectbox）を追加。一覧にも列を追加
- **日当金額の設定**：支払形態が「日当」の配布員を selectbox で選び、`data_editor` で業務名＋金額を編集 →「保存」。
  ※ Streamlit の `st.form` 内では選択に応じた動的表示ができないため、**登録とは別セクション**に置く（オーナー確認済み）
- 全タブ：一覧は**有効なものだけ**表示。停止中は `st.expander("停止中（N件）")` の中に一覧＋「有効に戻す」ボタン

### ③ 削除ボタン（`common/ui.py` に共通部品を新設）

```python
def confirm_delete(*, key, label, detail, on_confirm, warning=None):
    """削除→確認→実行 を全画面で同じ挙動に統一する共通部品。
    既存の重複警告(pay_pending 等)と同じ session_state 方式で作る。"""
```

- 押下 → `st.warning("⚠️ 削除しますか？")` ＋ 対象の内容（日付・金額など）→「はい、削除する」／「やめる」
- 実行後は既存の `flash()` で「削除しました」
- 適用先：小口／買掛／売掛の一覧の各行、業務委託の登録済み一覧、マスタ5タブ

**マスタの削除は停止中方式**：

- 押下時に `count_master_usage` で使用件数を数える
- 1件以上 → 「山田太郎さんは請求12件で使用中です。過去データを残すため**停止中**にします（一覧・報告書の表示は変わりません）」→ 実行すると `active=0`、「停止中にしました」
- 0件 → 「削除しますか？」→ 物理削除、「削除しました」

### ③ アナウンス

既存の `flash()` / `show_flash()` をそのまま使い、追加時「追加しました」・削除時「削除しました」・停止時「停止中にしました」・復帰時「有効に戻しました」を出す。新しい仕組みは作らない。

## テスト

- `tests/test_posting_store.py`：新しい列・テーブルのマイグレ（旧DBを開いても壊れない）、`distributor_daily_rates` のCRUD、`count_master_usage`、`find_vendor_by_name`
- `tests/test_posting_logic.py`：`resolve_original_status`、`master_delete_action`
- 画面：Streamlit AppTest（`from streamlit.testing.v1 import AppTest`）で各ページが例外なく描画されること、削除の確認フローが出ること
- **既存の全73テストが通ること**を最後に確認する

## 検証時の注意（既知の地雷・過去セッションの実証済み知見）

- `common/*.py` を変更したら **8502 の手動再起動が必須**。起動batは health=ok なら既存サーバーを開くだけで、コード変更は反映されない
- 検証は**実データDBのコピー**＋別ポート（8599）＋環境変数 `POSTING_DB_PATH` で行い、本番DBを汚さない。`db_sync` は `DB_S3_BUCKET` 未設定なら no-op なので外部へのpushも起きない
- Excel出力を触る場合は `freeze_xlsx_bytes()` を通す（内容が同じでもバイト列が変わるとDL URLが404になる）

## スコープ外（やらない）

- 買掛への配布員欄の追加（オーナー判断で小口のみ）
- 支払形態に応じた**報酬の自動計算**（今回は登録・表示まで。計算は要望に含まれていない）
- 削除の取り消し（Undo）機能
- `feature/revisions-2` ブランチの削除（オーナー確認後に別途）
