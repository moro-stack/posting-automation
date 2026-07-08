# common/bedrock_client.py
import json
import os
import time

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
MAX_RETRIES = 1


class BedrockInvocationError(Exception):
    pass


def _get_client():
    import boto3

    return boto3.client("bedrock-runtime", region_name="ap-northeast-1")


def invoke_model(prompt: str, client=None, max_tokens: int = 1024) -> str:
    bedrock_client_instance = client or _get_client()
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = bedrock_client_instance.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
            )
            body = json.loads(response["body"].read())
            return body["content"][0]["text"]
        except Exception as error:  # noqa: BLE001 - 外部API呼び出しのため広く捕捉してリトライする
            last_error = error
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
    raise BedrockInvocationError(f"Bedrock呼び出しに失敗しました: {last_error}")


def map_column_via_llm(header: str, target_columns, client=None):
    prompt = (
        f"次の列名「{header}」は、以下の自社フォーマットの列のどれに該当しますか。"
        f"候補: {', '.join(target_columns)}。"
        "該当する列名のみを1つ出力してください。該当するものがなければ「なし」と出力してください。"
    )
    raw_output = invoke_model(prompt, client=client).strip()
    if raw_output not in target_columns:
        return None
    return raw_output
