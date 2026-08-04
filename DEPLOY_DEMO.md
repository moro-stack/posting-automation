# デモ公開ガイド（Streamlit Community Cloud・無料・常時公開）

このアプリを、同僚が**いつでもアクセスできる公開URL**にする手順です。
**サンプル（架空）データ**＋**共有パスワード**で公開します。実データ・秘匿情報は上がりません（`.gitignore`で除外済み）。

---

## この構成で起きること（安心材料）
- 公開されるのは **架空のデモデータのみ**（`DEMO_MODE=1` のとき、実在名の入った初期データ`seed_masters`は使わず、`デモ配布A号`等の架空データを投入）。
- **共有パスワード1つ**でログイン（`APP_PASSWORD`。未入力5回で30秒ロック）。パスワード無しの人は入れません。
- Streamlit Cloud のDBは再起動で**まっさらに戻る**＝デモは毎回リセット。実データは載りません。
- あなたの**手元の8502（実データ）は無関係**・無変更（ログインも不要のまま）。

---

## 手順

### 事前準備
- **GitHubアカウント**（無料。無ければ https://github.com/signup で作成）。
- **Streamlit Community Cloud**（無料。GitHubアカウントでそのままサインイン）：https://share.streamlit.io

### Step 1. コードをGitHub（非公開リポジトリ）に上げる
1. GitHubで **New repository** → 名前（例 `posting-automation`）→ **Private** で作成。
2. 手元のターミナルで（`<URL>` は作成したリポジトリのURL）:
   ```
   cd C:\Users\moro\posting-automation
   git remote add origin <URL>
   git push -u origin feature/demo-share
   ```
   ※ `.gitignore` が `data/`・`*.db`・`.env` を除外しているので、**実DB・秘匿情報は上がりません**。
   ※ `feature/demo-share` ブランチには第3〜6弾の全機能＋デモ設定が入っています。

### Step 2. Streamlit Cloud でアプリを作る
1. https://share.streamlit.io → **Create app** → GitHubを連携。
2. 設定：
   - Repository: 上で作ったリポジトリ
   - Branch: **`feature/demo-share`**
   - Main file path: **`app.py`**
3. **Advanced settings → Secrets** に次を貼る（パスワードは好きな文字列に）:
   ```toml
   APP_PASSWORD = "ここに共有パスワード"
   DEMO_MODE = "1"
   ```
   ⚠️ `DB_S3_BUCKET` は**設定しない**（設定すると本物のS3と繋がってしまうため）。
4. **Deploy** を押す → 数分で `https://○○○.streamlit.app` が発行されます。

### Step 3. 共有する
- 発行URL＋共有パスワードを同僚に渡すだけ。24時間アクセス可（一定時間アクセスが無いとスリープし、開くと数十秒で復帰）。

---

## よくある質問
- **AI（レシート/請求書の自動読取）を試させたい**：任意。SecretsにAWS認証情報を追加すれば動きます（Bedrock課金が発生）。未設定でも**アプリは落ちず**、「手入力できます」と出るだけなのでデモには支障ありません。
  ```toml
  # 任意（OCRも試させる場合のみ）
  AWS_ACCESS_KEY_ID = "..."
  AWS_SECRET_ACCESS_KEY = "..."
  AWS_DEFAULT_REGION = "ap-northeast-1"
  ```
- **本番運用（実データを全員で共有）にしたい**：別途相談。S3同期（`DB_S3_BUCKET`）＋AWS認証を入れる構成に変えます（同時編集の注意あり）。
- **パスワードを変えたい**：Streamlit Cloud の Secrets を編集して再起動するだけ。

---

## 分担
- **私（ぽすたん）**：アプリ側の実装は完了（ログインゲート／secrets橋渡し／架空データseed）。この手順の各ステップも一緒に進めます。
- **あなた**：GitHubアカウント作成・push、Streamlit Cloudのサインイン（GitHubログイン）、共有パスワードの決定。分からない所は都度案内します。
