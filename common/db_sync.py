"""SQLite DB を S3 と同期する(App Runner などの揮発ストレージ対策)。

環境変数 DB_S3_BUCKET が設定されているときだけ動作する。
未設定なら全関数が no-op を返し、従来のローカル SQLite 動作のまま。

- 起動時: pull_db() で S3 の最新DBをローカルへ取得
- 書込後: push_db() でローカルDBを S3 へアップロード

App Runner は最小1台固定で運用する想定(同時書き込み衝突を避ける)。
"""
import os

from botocore.exceptions import ClientError

DEFAULT_KEY = "dashboard.db"


def s3_target():
    """(bucket, key) を返す。DB_S3_BUCKET 未設定なら None。"""
    bucket = os.environ.get("DB_S3_BUCKET")
    if not bucket:
        return None
    key = os.environ.get("DB_S3_KEY") or DEFAULT_KEY
    return (bucket, key)


def _make_client():
    # boto3 クライアント生成。テストでは monkeypatch で差し替える。
    import boto3

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    return boto3.client("s3", region_name=region) if region else boto3.client("s3")


def push_db(local_path, *, target=None, client=None) -> bool:
    """ローカルDBを S3 へアップロード。未設定/ファイル無しなら False。"""
    target = target or s3_target()
    if target is None:
        return False
    if not os.path.exists(local_path):
        return False
    bucket, key = target
    client = client or _make_client()
    client.upload_file(local_path, bucket, key)
    return True


def pull_db(local_path, *, target=None, client=None) -> bool:
    """S3 のDBをローカルへ取得。未設定/オブジェクト無しなら False。"""
    target = target or s3_target()
    if target is None:
        return False
    bucket, key = target
    client = client or _make_client()
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError:
        return False
    parent = os.path.dirname(os.path.abspath(local_path))
    os.makedirs(parent, exist_ok=True)
    client.download_file(bucket, key, local_path)
    return True
