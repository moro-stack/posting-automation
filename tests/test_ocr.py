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


# ===== 取引先が受取側(自社/御中)に化けるバグ（2026-08-20・大橋様ご指摘） =====
# 実際の請求書14枚でテストし、プロンプトで「御中/様は宛名なのでvendorにしない」と
# 指示していても、AIが受取側の名前をvendorとして返すことが2件で再現した
# (配夢株式会社の請求書で vendor="株式会社ケイピーエス 大阪支社 御中"、
#  株式会社スペースリーダーの請求書で vendor="株式会社ケイピーエス"）。
# プロンプトを強化して再テストしたが改善せず、他の書類で悪化もしたため、
# コード側で既知の誤りパターンを検知してnullにする方式にした。


def test_extract_invoice_nulls_vendor_when_ai_returns_recipient_with_onchu():
    """再現ケースそのもの：配夢株式会社の請求書でAIが返した実際の誤り値。"""
    fake = _FakeClient('{"vendor":"株式会社ケイピーエス 大阪支社 御中","amount":198000,'
                       '"date":"2026-06-30","note":"6月度ご請求"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] is None
    assert result["amount"] == 198000  # 他の項目は正しいので巻き込んで消さない


def test_extract_invoice_nulls_vendor_when_ai_returns_bare_self_company():
    """再現ケースそのもの：株式会社スペースリーダーの請求書でAIが返した実際の誤り値
    （敬称なしで自社名だけを返すこともある）。"""
    fake = _FakeClient('{"vendor":"株式会社ケイピーエス","amount":11000,'
                       '"date":"2026-06-10","note":"備品費"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] is None


def test_extract_invoice_nulls_vendor_ending_in_sama():
    fake = _FakeClient('{"vendor":"黒瀬 誠 様","amount":1000,"note":"備考"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] is None


def test_extract_invoice_keeps_normal_vendor_name():
    """自社名を含まない普通の取引先名まで巻き込んで消さないこと。"""
    fake = _FakeClient('{"vendor":"株式会社ネクストレベル","amount":32307,"note":"宿泊費"}')
    result = ocr.extract_invoice(b"x", client=fake)
    assert result["vendor"] == "株式会社ネクストレベル"


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

# ===== 読み取り失敗の「原因」を画面に出すため（2026-08-10） =====

def test_failed_reads_returns_file_and_reason():
    """🔴 例外の中身を捨てない。8/7 は AWS の権限エラーを画面にもログにも出さず、
    「0件しか読めない」の原因究明に50分かかった。原因の文字列が必ず取り出せること。"""
    reason = ("Bedrock呼び出しに失敗しました: AccessDeniedException: "
              "User is not authorized to perform: bedrock:InvokeModel")
    drafts = [
        {"amount": 3300, "_file": "ok.jpg"},
        {"amount": None, "_file": "ng.pdf", "_error": reason},
    ]
    assert ocr.failed_reads(drafts) == [("ng.pdf", reason)]


def test_failed_reads_is_empty_when_all_succeeded():
    drafts = [{"amount": 1, "_file": "a.jpg"}, {"amount": 2, "_file": "b.jpg"}]
    assert ocr.failed_reads(drafts) == []


def test_failed_reads_keeps_every_failure():
    """複数落ちたら全部返す。1件だけ出して他を握りつぶさないこと。"""
    drafts = [
        {"amount": None, "_file": "a.pdf", "_error": "E1"},
        {"amount": 5, "_file": "b.jpg"},
        {"amount": None, "_file": "c.png", "_error": "E2"},
    ]
    assert ocr.failed_reads(drafts) == [("a.pdf", "E1"), ("c.png", "E2")]


def test_failed_reads_survives_missing_file_name():
    """カメラ撮影などでファイル名が無くても、原因は落とさない。"""
    assert ocr.failed_reads([{"_error": "E"}]) == [("", "E")]


# ===== 金額の誤読を減らす（2026-08-27・大橋様ご指摘） =====
# 「請求額」「合計」の近くにある数字を優先して金額に採る。
# 取引先の誤読対策(717e123)と同じ方針＝プロンプトだけに頼らず、AIには候補を
# ラベル付きで出させ、どれを採るかはコード側の決め打ちで決める。


def test_pick_amount_prefers_seikyugaku_over_other_numbers():
    """「請求額」ラベルの候補が最優先。小計・消費税に引っ張られない。"""
    d = {"amount": 3000, "amount_candidates": [
        {"label": "小計", "value": 30000},
        {"label": "消費税", "value": 3000},
        {"label": "ご請求額", "value": 33000},
    ]}
    assert ocr.pick_amount(d) == 33000


def test_pick_amount_prefers_goukei_when_no_seikyugaku():
    d = {"amount": 500, "amount_candidates": [
        {"label": "小計", "value": 5000},
        {"label": "合計", "value": 5500},
    ]}
    assert ocr.pick_amount(d) == 5500


def test_pick_amount_ranks_seikyu_above_goukei():
    """両方あるときは「請求額」を採る(請求書の総額はこちら)。"""
    d = {"amount": 1, "amount_candidates": [
        {"label": "合計", "value": 1000},
        {"label": "請求金額", "value": 2000},
    ]}
    assert ocr.pick_amount(d) == 2000


def test_pick_amount_ignores_excluded_labels_even_if_they_are_the_only_ones():
    """お預り・お釣り・消費税だけしか無いなら候補は使わず、amount に落とす
    (誤った値を確定させるより、AIの本命の値を人に確認してもらう方が安全)。"""
    d = {"amount": 1200, "amount_candidates": [
        {"label": "お預り", "value": 5000},
        {"label": "お釣り", "value": 3800},
    ]}
    assert ocr.pick_amount(d) == 1200


def test_pick_amount_falls_back_to_amount_when_no_candidates():
    assert ocr.pick_amount({"amount": 1200}) == 1200
    assert ocr.pick_amount({"amount": None}) is None


def test_pick_amount_parses_string_values_with_yen_and_comma():
    d = {"amount": None, "amount_candidates": [{"label": "合計", "value": "¥16,216"}]}
    assert ocr.pick_amount(d) == 16216


def test_pick_amount_skips_unreadable_candidate_values():
    d = {"amount": 100, "amount_candidates": [
        {"label": "合計", "value": "—"},
        {"label": "合計", "value": 880},
    ]}
    assert ocr.pick_amount(d) == 880


def test_extract_receipt_uses_the_goukei_candidate():
    fake = _FakeClient('{"date":"2026-06-19","item":"駐車場代","amount":500,'
                       '"amount_candidates":[{"label":"小計","value":500},'
                       '{"label":"合計","value":1200}]}')
    assert ocr.extract_receipt(b"x", client=fake)["amount"] == 1200


def test_extract_invoice_uses_the_seikyugaku_candidate():
    fake = _FakeClient('{"vendor":"関西電力株式会社","date":"2026-06-16","note":"電気",'
                       '"amount":14742,'
                       '"amount_candidates":[{"label":"小計","value":14742},'
                       '{"label":"ご請求額","value":16216}]}')
    assert ocr.extract_invoice(b"x", client=fake)["amount"] == 16216


def test_extract_invoice_without_candidates_keeps_old_behaviour():
    """候補を返さない旧応答でも従来どおり amount を使う(後方互換)。"""
    fake = _FakeClient('{"vendor":"関西電力株式会社","amount":16216,"note":"電気"}')
    assert ocr.extract_invoice(b"x", client=fake)["amount"] == 16216


def test_prompts_tell_the_ai_to_look_near_the_amount_labels():
    """プロンプト側でも「請求額」「合計」の近くの数字を採るよう指示していること。"""
    for prompt in (ocr._RECEIPT_PROMPT, ocr._INVOICE_PROMPT):
        assert "請求額" in prompt
        assert "合計" in prompt
        assert "amount_candidates" in prompt
