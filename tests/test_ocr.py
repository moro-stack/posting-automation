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
