"""レシート/請求書の画像から項目を抽出する。抽出は下書き扱い(人が確認・修正)。"""
import json
import re

from common import bedrock_client

_RECEIPT_PROMPT = (
    "この画像はレシートまたは領収書です。日付・合計金額・品目を読み取り、"
    'JSONのみを出力してください。形式: {"date":"YYYY-MM-DD","amount":整数,"item":"品目"}。'
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)
_INVOICE_PROMPT = (
    "この画像は請求書です。請求元(会社名)・請求金額(税込)・内容を読み取り、"
    'JSONのみを出力してください。形式: {"vendor":"会社名","amount":整数,"note":"内容"}。'
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)


def _parse_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return {}


def _as_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        cleaned = re.sub(r"[^\d-]", "", str(value).split(".")[0])
        if cleaned in ("", "-"):
            return None
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def extract_receipt(image_bytes, media_type="image/jpeg", *, client=None) -> dict:
    raw = bedrock_client.invoke_vision(_RECEIPT_PROMPT, image_bytes, media_type, client=client)
    d = _parse_json(raw)
    return {"date": d.get("date") or None,
            "amount": _as_int(d.get("amount")),
            "item": d.get("item") or None}


def extract_invoice(image_bytes, media_type="image/jpeg", *, client=None) -> dict:
    raw = bedrock_client.invoke_vision(_INVOICE_PROMPT, image_bytes, media_type, client=client)
    d = _parse_json(raw)
    return {"vendor": d.get("vendor") or None,
            "amount": _as_int(d.get("amount")),
            "note": d.get("note") or None}
