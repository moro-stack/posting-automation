from common import ocr


class _FakeClient:
    """invoke_model と同じ戻り(本文テキスト)を返すダミー。"""
    def __init__(self, text):
        self._text = text
        self.called_with = None

    def invoke_model(self, **kwargs):
        self.called_with = kwargs
        import json
        body = json.dumps({"content": [{"text": self._text}]}).encode()

        class _R:  # response["body"].read() を模す
            def __init__(self, b): self._b = b
            def read(self): return self._b
        return {"body": _R(body)}


def test_extract_receipt_parses_json():
    fake = _FakeClient('{"date":"2026-06-19","amount":1200,"item":"駐車場代"}')
    result = ocr.extract_receipt(b"\xff\xd8fakejpg", client=fake)
    assert result == {"date": "2026-06-19", "amount": 1200, "item": "駐車場代"}


def test_extract_receipt_tolerates_extra_text():
    fake = _FakeClient('抽出結果です: {"date":"2026-06-19","amount":1200,"item":"飲み物"} 以上')
    result = ocr.extract_receipt(b"x", client=fake)
    assert result["amount"] == 1200


def test_extract_receipt_bad_output_returns_none_fields():
    fake = _FakeClient("読み取れませんでした")
    result = ocr.extract_receipt(b"x", client=fake)
    assert result == {"date": None, "amount": None, "item": None}


def test_extract_invoice_parses_json():
    fake = _FakeClient('{"vendor":"関西電力株式会社","amount":16216,"note":"電気代"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] == "関西電力株式会社" and result["amount"] == 16216


def test_extract_invoice_parses_date_and_vendor():
    fake = _FakeClient('{"vendor":"NTTドコモビジネス株式会社","amount":1848,'
                       '"date":"2026-06-16","note":"通信費"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] == "NTTドコモビジネス株式会社"
    assert result["amount"] == 1848
    assert result["date"] == "2026-06-16"


def test_extract_invoice_missing_date_is_none():
    fake = _FakeClient('{"vendor":"関西電力株式会社","amount":16216,"note":"電気"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["date"] is None


def test_as_int_handles_float():
    assert ocr._as_int(1200.0) == 1200


def test_as_int_handles_decimal_string_with_comma():
    assert ocr._as_int("1,200.50") == 1200


def test_as_int_handles_yen_string():
    assert ocr._as_int("¥16,216") == 16216


def test_as_int_returns_none_for_unreadable_string():
    assert ocr._as_int("読めない") is None


def test_as_int_returns_none_for_none():
    assert ocr._as_int(None) is None


def test_media_type_for_pdf_png_jpeg():
    assert ocr.media_type_for("領収書.pdf") == "application/pdf"
    assert ocr.media_type_for("RECEIPT.PDF") == "application/pdf"
    assert ocr.media_type_for("a.png") == "image/png"
    assert ocr.media_type_for("a.jpg") == "image/jpeg"
    assert ocr.media_type_for("a.jpeg") == "image/jpeg"


def test_invoke_vision_pdf_uses_document_block():
    import base64
    import json

    fake = _FakeClient('{"vendor":"関西電力株式会社","amount":16216,"note":"電気"}')
    pdf_bytes = b"%PDF-1.4 fake pdf"
    ocr.extract_invoice(pdf_bytes, media_type="application/pdf", client=fake)

    body = json.loads(fake.called_with["body"])
    content_block = body["messages"][0]["content"][0]
    assert content_block["type"] == "document"
    assert content_block["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(content_block["source"]["data"]) == pdf_bytes


def test_invoke_vision_image_block_structure():
    import base64
    import json

    fake = _FakeClient('{"date":"2026-06-19","amount":1200,"item":"駐車場代"}')
    image_bytes = b"\xff\xd8abc"
    ocr.extract_receipt(image_bytes, media_type="image/jpeg", client=fake)

    body = json.loads(fake.called_with["body"])
    content_block = body["messages"][0]["content"][0]
    assert content_block["type"] == "image"
    assert content_block["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(content_block["source"]["data"]) == image_bytes


# ===== カメラ撮影・アップロードのメディア種別(依頼⑤) =====


class _Upload:
    def __init__(self, name="", type=""):
        self.name = name
        self.type = type


def test_media_type_for_upload_prefers_the_uploads_own_type():
    """🔴 カメラ撮影は実体がPNGのこともある。ファイル名だけで決めると
    PNGを image/jpeg と偽って送ることになる。upload.type を最優先する。"""
    assert ocr.media_type_for_upload(_Upload(name="camera_input", type="image/png")) == "image/png"
    assert ocr.media_type_for_upload(_Upload(name="camera_input", type="image/jpeg")) == "image/jpeg"


def test_media_type_for_upload_normalises_image_jpg():
    assert ocr.media_type_for_upload(_Upload(type="image/jpg")) == "image/jpeg"


def test_media_type_for_upload_falls_back_to_extension():
    """type が空なら拡張子で決める(従来のアップロード経路と同じ)。"""
    assert ocr.media_type_for_upload(_Upload(name="請求書.pdf", type="")) == "application/pdf"
    assert ocr.media_type_for_upload(_Upload(name="レシート.png", type="")) == "image/png"


def test_media_type_for_upload_falls_back_to_default_without_name_or_type():
    """🔴 camera_input は拡張子なしの名前になることがある。ここで落ちてはいけない。"""
    assert ocr.media_type_for_upload(_Upload(name="camera_input", type="")) == "image/jpeg"
    assert ocr.media_type_for_upload(object()) == "image/jpeg"


def test_media_type_for_upload_ignores_unknown_type():
    """知らない type は信用せず、拡張子/既定に落とす。"""
    assert ocr.media_type_for_upload(_Upload(name="a.png", type="application/octet-stream")) == "image/png"
