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
    "この画像またはPDFは請求書です。請求元(会社名)・請求金額(税込)・請求日・内容を読み取り、"
    'JSONのみを出力してください。'
    '形式: {"vendor":"会社名","amount":整数,"date":"YYYY-MM-DD","note":"内容"}。'
    "vendor は請求書を発行した側(請求元・差出人)の会社名。"
    "『御中』『様』が付く宛名は受取側(請求先)なので vendor にしてはいけない。"
    "特に受取側が『ケイピーエス』『KPS』『ケイビーエス』等の場合、それは自社(請求先)なので vendor にしない。"
    "amount は合計請求額(税込)。小計・消費税・単価などの一部金額ではなく総額を選ぶ。"
    "date は請求書の発行日(または請求日)を優先し YYYY-MM-DD 形式で。"
    "日が特定できず年月しか分からない場合は YYYY-MM でよい。"
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)


def media_type_for(filename: str) -> str:
    """ファイル名から Bedrock 送信用のメディア種別を返す(PDF/PNG/JPEG対応)。"""
    n = (filename or "").lower()
    if n.endswith(".pdf"):
        return "application/pdf"
    if n.endswith(".png"):
        return "image/png"
    return "image/jpeg"


_KNOWN_MEDIA_TYPES = ("application/pdf", "image/png", "image/jpeg")


def media_type_for_upload(upload, *, default="image/jpeg") -> str:
    """アップロード/撮影されたファイルのメディア種別。

    Streamlit の UploadedFile が持つ `type` を最優先で使う。
    カメラ撮影(st.camera_input)はファイル名から拡張子を取れないことがあり、
    かつ実体がPNGのこともあるため、ファイル名だけで決めると
    「PNGのデータを image/jpeg と偽って送る」ことになりかねない。
    type が取れなければファイル名の拡張子、それも無ければ default。
    """
    t = (getattr(upload, "type", "") or "").strip().lower()
    if t == "image/jpg":
        return "image/jpeg"
    if t in _KNOWN_MEDIA_TYPES:
        return t
    name = getattr(upload, "name", "") or ""
    if "." in name:
        return media_type_for(name)
    return default


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
            "date": d.get("date") or None,
            "note": d.get("note") or None}

def failed_reads(drafts):
    """AIの読み取りに失敗したものを [(ファイル名, 原因)] で返す。

    🔴 例外の中身を握りつぶさないための関数。画面に原因をそのまま出すのに使う。
    2026-08-07、AWSの権限エラー(IAMポリシー未アタッチ)を画面にもログにも出して
    いなかったため「0件しか読めない」の原因究明に50分かかった。1行出ていれば5分だった。
    """
    return [(d.get("_file") or "", d["_error"]) for d in drafts if d.get("_error")]

