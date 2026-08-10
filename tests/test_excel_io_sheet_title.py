"""excel_io のシート名サニタイズ（2026-08-10 の点検で見つかった地雷）。"""
from common import excel_io as X

_EXCEL_NG_SHEET_CHARS = set("[]:*?/" + chr(92)) | set("［］：＊？／＼")


def test_safe_sheet_title_removes_fullwidth_forbidden_chars():
    """半角の禁止文字は除いていたが、全角(／［］：＊？＼)が素通りしていた。"""
    for raw in ("メイト/南川", "メイト／南川", "A［1］", "9：00", "計画＊案"):
        got = X._safe_sheet_title(raw)
        assert not set(got) & _EXCEL_NG_SHEET_CHARS, f"{raw!r} → {got!r} に禁止文字が残る"
        assert len(got) <= 31


def test_safe_sheet_title_keeps_normal_titles_and_dedupes():
    assert X._safe_sheet_title("返却リスト") == "返却リスト"
    assert X._safe_sheet_title("返却リスト", existing={"返却リスト"}) == "返却リスト_2"


def test_safe_sheet_title_falls_back_when_everything_is_stripped():
    """全部が禁止文字でも空のシート名にしない（Excelは空名を受け付けない）。"""
    got = X._safe_sheet_title("///")
    assert got and not set(got) & _EXCEL_NG_SHEET_CHARS


def test_all_sheet_name_builders_share_one_definition():
    """🔴 今回の事故は「同じ判定が4か所に散らばって食い違った」ことが原因。

    シート名を作る処理は全部 excel_io.EXCEL_NG_SHEET_CHARS を見ること。
    どれか1つが独自の文字集合を持ち始めたら、このテストで気づける。
    """
    from common import shiwake, atehagi, proceed_atehagi

    ng = set(X.EXCEL_NG_SHEET_CHARS)
    assert shiwake._SHEET_NG == ng, "shiwake が独自の禁止文字集合を持っている"

    # 実際に通してみて、どのビルダーも禁止文字を残さないこと
    for label, fn in [
        ("shiwake", lambda s: shiwake.sheet_name_for(s, set())),
        ("atehagi", lambda s: atehagi._unique_title(s, set())),
        ("proceed", lambda s: proceed_atehagi._unique_title(s, set())),
        ("excel_io", lambda s: X._safe_sheet_title(s)),
    ]:
        for ch in ng:
            got = fn(f"あ{ch}い")
            assert not set(got) & ng, f"{label}: 'あ{ch}い' → {got!r} に禁止文字が残る"

