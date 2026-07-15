# common/bedrock_client.py
import base64
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


def _image_block(image_bytes, media_type):
    b64 = base64.b64encode(image_bytes).decode()
    return {"type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64}}


def _pdf_to_image_blocks(pdf_bytes, *, dpi: int = 200, max_pages: int = 8):
    """PDFの各ページを画像(PNG)に変換して image ブロックのリストを返す。

    請求書PDFはフォントの符号化(CID等)によりテキスト層が文字化けしていることがあり、
    生PDFのまま渡すと会社名などが読めない。画像化して見た目どおりにOCRさせることで
    取引先名・金額を安定して読み取れるようにする。
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    blocks = []
    for i in range(min(doc.page_count, max_pages)):
        pix = doc.load_page(i).get_pixmap(dpi=dpi)
        blocks.append(_image_block(pix.tobytes("png"), "image/png"))
    doc.close()
    return blocks


def _content_blocks(file_bytes, media_type):
    """媒体に応じた content ブロック列を組む。
    PDFは画像化して渡す(テキスト層の文字化け対策)。失敗時は生PDFにフォールバック。"""
    if media_type == "application/pdf":
        try:
            blocks = _pdf_to_image_blocks(file_bytes)
            if blocks:
                return blocks
        except Exception:  # noqa: BLE001 - 変換不能なPDFは生のまま渡して救済する
            pass
        b64 = base64.b64encode(file_bytes).decode()
        return [{"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}]
    return [_image_block(file_bytes, media_type)]


def invoke_vision(prompt, file_bytes, media_type="image/jpeg", client=None,
                  max_tokens: int = 1024) -> str:
    """画像またはPDFをClaudeに渡してテキスト応答を得る。"""
    bedrock = client or _get_client()
    content = _content_blocks(file_bytes, media_type) + [{"type": "text", "text": prompt}]
    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }),
    )
    body = json.loads(response["body"].read())
    return body["content"][0]["text"]


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
