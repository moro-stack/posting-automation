"""レシート/請求書の画像から項目を抽出する。抽出は下書き扱い(人が確認・修正)。"""
import json
import re

from common import bedrock_client

# 🔴 2026-08-27 大橋様ご指摘: AIが金額を誤って読むことがある(小計・消費税・
# お預り金額などを拾ってしまう)。取引先の誤読対策(717e123)と同じ方針で、
# 「AIには金額の候補をラベル付きで全部出させ、どれを採るかはコード側で決める」形にする。
# プロンプトだけを強化する方法は 2026-08-20 の検証で改善しなかった実績があるため、
# 判断そのものをコードに持たせて再現性を確保する。
_AMOUNT_CANDIDATES_RULE = (
    'amount_candidates には、金額らしき数字を「その数字のすぐ近く(左・上)に書かれている'
    '見出しの文字」とセットで、書類にあるだけ列挙してください。'
    '形式: [{"label":"見出しの文字","value":整数}, ...]。'
    '見出しは書類に書かれているとおりの文字(例:「合計」「ご請求額」「小計」「消費税」「お預り」)を'
    'そのまま入れてください。要約したり言い換えたりしないこと。'
    "amount には、そのうち『請求額』または『合計』の文字の近くにある数字を選んでください。"
    "小計・消費税・単価・お預り・お釣りは総額ではないので amount にしないこと。"
)
_RECEIPT_PROMPT = (
    "この画像はレシートまたは領収書です。日付・合計金額・品目を読み取り、"
    'JSONのみを出力してください。'
    '形式: {"date":"YYYY-MM-DD","amount":整数,"item":"品目",'
    '"amount_candidates":[{"label":"見出し","value":整数}]}。'
    + _AMOUNT_CANDIDATES_RULE +
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)
_INVOICE_PROMPT = (
    "この画像またはPDFは請求書です。請求元(会社名)・請求金額(税込)・請求日・内容を読み取り、"
    'JSONのみを出力してください。'
    '形式: {"vendor":"会社名","amount":整数,"date":"YYYY-MM-DD","note":"内容",'
    '"amount_candidates":[{"label":"見出し","value":整数}]}。'
    "vendor は請求書を発行した側(請求元・差出人)の会社名。"
    "『御中』『様』が付く宛名は受取側(請求先)なので vendor にしてはいけない。"
    "特に受取側が『ケイピーエス』『KPS』『ケイビーエス』等の場合、それは自社(請求先)なので vendor にしない。"
    "amount は合計請求額(税込)。小計・消費税・単価などの一部金額ではなく総額を選ぶ。"
    + _AMOUNT_CANDIDATES_RULE +
    "date は請求書の発行日(または請求日)を優先し YYYY-MM-DD 形式で。"
    "日が特定できず年月しか分からない場合は YYYY-MM でよい。"
    "読み取れない項目は null。金額はカンマや円記号を除いた整数で。"
)

# 🔴 2026-08-20: プロンプトで「宛名(御中/様)をvendorにしない」と指示しても、AIが自社(受取側)の
# 名前をvendorとして返すことがある(大橋様ご指摘・実際の請求書14枚でテストし2件で再現)。
# プロンプトを強化して再テストしたが改善せず、むしろ他の書類で取引先名の読み取りが悪化した
# (試行1回で悪化を確認・AIの読み取り精度そのものの限界と判断)。
# 確実性を優先し、既知の誤りパターン(受取側の名前・宛名の敬称)をコード側で検知したら
# vendor を null にする(誤った値を確定登録するより、空欄にして人に入力してもらう方が安全)。
_SELF_COMPANY_MARKERS = ("ケイピーエス", "ケイビーエス", "kps")
_RECIPIENT_SUFFIXES = ("御中", "様")


def _sanitize_vendor(vendor):
    """AIが受取側(自社/御中)の名前をvendorとして返す既知の誤りを検知し、nullにする。"""
    if not vendor:
        return None
    v = vendor.strip()
    if not v:
        return None
    if any(marker in v.lower() for marker in _SELF_COMPANY_MARKERS):
        return None
    if v.endswith(_RECIPIENT_SUFFIXES):
        return None
    return v


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


# 金額の見出しの優先順位。数字が小さいほど優先。
# 「請求額」＞「合計」の順にするのは、請求書は請求額が総額、レシートは合計が総額で、
# 両方が載っている書類では請求額の方が確実に総額だから(小計や税額とは別枠で書かれる)。
_AMOUNT_LABEL_RANKS = (
    ("請求", 0),
    ("お買上", 1), ("お買い上げ", 1), ("合計", 1), ("総額", 1), ("総計", 1), ("計", 2),
)
# 総額ではないと分かっている見出し。これしか無いときは候補を採らない。
_AMOUNT_LABEL_EXCLUDES = (
    "小計", "消費税", "内税", "外税", "税額", "対象", "値引", "割引",
    "お預", "預り", "お釣", "釣銭", "つり", "ポイント", "単価", "前回", "繰越",
)


def _amount_label_rank(label):
    """見出しの文字から優先順位を返す。総額でないと分かる見出しは None。"""
    s = str(label or "")
    if any(ng in s for ng in _AMOUNT_LABEL_EXCLUDES):
        return None
    for key, rank in _AMOUNT_LABEL_RANKS:
        if key in s:
            return rank
    return None


def pick_amount(data) -> int | None:
    """AIの応答から採用する金額を決める。

    「請求額」「合計」の文字の近くにある数字を優先する(2026-08-27 大橋様ご指摘)。
    amount_candidates(見出し付きの候補)があれば見出しの優先順位で選び、
    候補が無い・どれも総額と判断できない場合は、従来どおり amount をそのまま使う。
    候補は「AIが読めた数字」なので、値が数値として読めないものは黙って捨てる。
    """
    best_rank, best_value = None, None
    for c in (data or {}).get("amount_candidates") or []:
        if not isinstance(c, dict):
            continue
        rank = _amount_label_rank(c.get("label"))
        if rank is None:
            continue
        value = _as_int(c.get("value"))
        if value is None:
            continue
        # 同順位の見出しが複数あるときは大きい方(総額)を採る
        if best_rank is None or rank < best_rank or (rank == best_rank and value > best_value):
            best_rank, best_value = rank, value
    if best_value is not None:
        return best_value
    return _as_int((data or {}).get("amount"))


def extract_receipt(image_bytes, media_type="image/jpeg", *, client=None) -> dict:
    raw = bedrock_client.invoke_vision(_RECEIPT_PROMPT, image_bytes, media_type, client=client)
    d = _parse_json(raw)
    return {"date": d.get("date") or None,
            "amount": pick_amount(d),
            "item": d.get("item") or None}


def extract_invoice(image_bytes, media_type="image/jpeg", *, client=None) -> dict:
    raw = bedrock_client.invoke_vision(_INVOICE_PROMPT, image_bytes, media_type, client=client)
    d = _parse_json(raw)
    return {"vendor": _sanitize_vendor(d.get("vendor")),
            "amount": pick_amount(d),
            "date": d.get("date") or None,
            "note": d.get("note") or None}

def failed_reads(drafts):
    """AIの読み取りに失敗したものを [(ファイル名, 原因)] で返す。

    🔴 例外の中身を握りつぶさないための関数。画面に原因をそのまま出すのに使う。
    2026-08-07、AWSの権限エラー(IAMポリシー未アタッチ)を画面にもログにも出して
    いなかったため「0件しか読めない」の原因究明に50分かかった。1行出ていれば5分だった。
    """
    return [(d.get("_file") or "", d["_error"]) for d in drafts if d.get("_error")]

