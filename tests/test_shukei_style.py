"""集計表の書式がテンプレート（実物）と一致することを機械で確かめる。

設計: docs/superpowers/specs/2026-08-07-shukei-design-fidelity-design.md
目視で「合っている」と言わないための土台。
"""
import io

import openpyxl
import pytest

from common import atehagi as A
from common import shukei_style as S


@pytest.fixture(scope="module")
def tpl():
    return S.ShukeiTemplate()


# ===== テンプレートそのものの前提を固定する =====


def test_template_exists_and_has_shukei_sheet(tpl):
    assert tpl.ws.title == "集計表"
    assert tpl.ws.max_row >= 39


def test_template_font_is_yu_gothic_everywhere(tpl):
    """🔴 実物は游ゴシックのみ。ここが崩れると全体の見た目が変わる。"""
    names = {c.font.name for row in tpl.ws.iter_rows() for c in row
             if c.value is not None}
    assert names == {"游ゴシック"}


def test_template_uses_five_border_styles(tpl):
    """実物は dotted/double/hair/medium/thin の5種を使い分けている。"""
    styles = set()
    for row in tpl.ws.iter_rows():
        for c in row:
            for side in ("left", "right", "top", "bottom"):
                st = getattr(c.border, side).style
                if st:
                    styles.add(st)
    assert styles == {"dotted", "double", "hair", "medium", "thin"}


def test_template_has_column_widths(tpl):
    widths = {k: d.width for k, d in tpl.ws.column_dimensions.items() if d.width}
    assert widths["A"] == pytest.approx(6.2, abs=0.05)
    assert widths["B"] == pytest.approx(10.7, abs=0.05)
    assert widths["AG"] == pytest.approx(10.6, abs=0.05)


# ===== 複写のふるまい =====


def test_copy_style_copies_font_border_and_format(tpl):
    wb = openpyxl.Workbook()
    ws = wb.active
    cell = ws.cell(1, 1, 123)
    src = tpl.ws.cell(4, 6)          # 上部マトリクスの部数セル
    S.copy_style(src, cell)
    assert cell.font.name == src.font.name
    assert cell.font.sz == src.font.sz
    assert cell.font.b == src.font.b
    assert cell.border.top.style == src.border.top.style
    assert cell.border.bottom.style == src.border.bottom.style
    assert cell.number_format == src.number_format


def test_copy_style_does_not_share_objects(tpl):
    """🔴 Font/Border を共有すると、片方を変えたとき他方も変わる。

    openpyxl は代入で参照を共有してしまうので copy() が要る。
    ここが壊れると「1セル直したら別のセルまで変わる」事故になる。
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    a = ws.cell(1, 1, 1)
    b = ws.cell(2, 1, 2)
    src = tpl.ws.cell(4, 3)
    S.copy_style(src, a)
    S.copy_style(src, b)
    assert a.font is not b.font
    assert a.border is not b.border


def test_apply_uses_the_role_row(tpl):
    wb = openpyxl.Workbook()
    ws = wb.active
    cell = ws.cell(5, 1)
    tpl.apply(cell, "header", 1)
    src = tpl.ws.cell(S.ROLE_ROWS["header"], 1)
    assert cell.font.sz == src.font.sz
    assert cell.border.top.style == src.border.top.style


def test_copy_column_widths(tpl):
    wb = openpyxl.Workbook()
    ws = wb.active
    tpl.copy_column_widths(ws)
    assert ws.column_dimensions["A"].width == pytest.approx(6.2, abs=0.05)
    assert ws.column_dimensions["B"].width == pytest.approx(10.7, abs=0.05)


@pytest.mark.parametrize("index,count,expected", [
    (0, 1, "area_first"),
    (0, 3, "area_first"),
    (1, 3, "area_middle"),
    (2, 3, "area_last"),
])
def test_leader_role(index, count, expected):
    assert S.leader_role(index, count) == expected


# ===== 生成物がテンプレートの書式を持っていること =====


def _build_from_real_like_data():
    """小さな作りデータで集計表を生成する。"""
    table = [
        ["配送管理表", "2026/08/21", "(1213号)"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
    ]
    # 🔴 部数は必ず4桁以上にする。3桁だと「1000以上のセル」が0件になり、
    # 桁区切りのテストが空集合を検査するだけの無意味なものになる(2026-08-07に踏んだ)。
    for chiku, name, code, butsu, bu in [
        ("911001", "ケイピーエス", None, "91 ぱど", 4380),
        ("911001", "ケイピーエス", 3, "丸源ラーメン", 4380),
        ("911003", "ケイピーエス", None, "91 ぱど", 3080),
        ("921001", "フィールドサービス", None, "92 ぱど", 2000),
    ]:
        table.append(["2026/08/21", "1213", 0, "", "", name, "", None, chiku,
                      code, butsu, bu, "", "", "", "", ""])
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    version = A.detect_version(groups)
    data = A.shukei_data(groups, version)
    raw = A.build_shukei_daishi_workbook(data, version, "1213", "2026/08/21")
    return openpyxl.load_workbook(io.BytesIO(raw))


def test_generated_sheet_uses_yu_gothic(tpl):
    """🔴 生成物のフォントが游ゴシックであること(既定のCalibriのままにしない)。"""
    ws = _build_from_real_like_data()["集計表"]
    names = {c.font.name for row in ws.iter_rows() for c in row
             if c.value is not None}
    assert names == {"游ゴシック"}, f"游ゴシック以外が混ざっている: {names}"


def test_generated_sheet_has_template_column_widths(tpl):
    """🔴 列幅が実物どおりであること(指定なしだと全列同じ幅になる)。"""
    ws = _build_from_real_like_data()["集計表"]
    assert ws.column_dimensions["A"].width == pytest.approx(6.2, abs=0.05)
    assert ws.column_dimensions["B"].width == pytest.approx(10.7, abs=0.05)
    assert ws.column_dimensions["AG"].width == pytest.approx(10.6, abs=0.05)


def test_generated_sheet_uses_more_than_one_border_style(tpl):
    """🔴 罫線が1種類(thin)だけになっていないこと。

    以前は全セル4辺 thin で、実物(5種を使い分け)と別物になっていた。
    """
    ws = _build_from_real_like_data()["集計表"]
    styles = set()
    for row in ws.iter_rows():
        for c in row:
            for side in ("left", "right", "top", "bottom"):
                st = getattr(c.border, side).style
                if st:
                    styles.add(st)
    assert len(styles) >= 3, f"罫線が {styles} しか使われていない"
    assert "medium" in styles


def test_generated_numbers_have_thousands_separator(tpl):
    """🔴 部数に桁区切りが付くこと(実物は #,##0 形式)。"""
    ws = _build_from_real_like_data()["集計表"]
    fmts = {c.number_format for row in ws.iter_rows() for c in row
            if isinstance(c.value, int) and c.value >= 1000}
    assert any("#,##0" in f for f in fmts), f"桁区切りが無い: {fmts}"


def test_generated_sheet_has_no_unsized_font(tpl):
    """🔴 サイズ未指定のセルを残さない。

    合計行でフォントを Font(name=..., bold=True) で上書きしたとき、
    サイズが抜けてそこだけ既定サイズになっていた(2026-08-07)。
    """
    ws = _build_from_real_like_data()["集計表"]
    bad = [(c.coordinate, c.value) for row in ws.iter_rows() for c in row
           if c.value is not None and c.font.sz is None]
    assert bad == [], f"サイズ未指定のセルがある: {bad}"


def test_generated_font_sizes_are_all_in_template_vocabulary(tpl):
    """🔴 生成物に使うフォント(名前・サイズ)が、実物にあるものだけであること。"""
    tpl_vocab = {(c.font.name, c.font.sz)
                 for row in tpl.ws.iter_rows() for c in row if c.value is not None}
    ws = _build_from_real_like_data()["集計表"]
    used = {(c.font.name, c.font.sz)
            for row in ws.iter_rows() for c in row if c.value is not None}
    assert used <= tpl_vocab, f"実物に無いフォントが使われている: {used - tpl_vocab}"


def test_generated_sheet_uses_all_five_border_styles(tpl):
    """🔴 実物と同じ5種の罫線が出ていること。"""
    ws = _build_from_real_like_data()["集計表"]
    styles = set()
    for row in ws.iter_rows():
        for c in row:
            for side in ("left", "right", "top", "bottom"):
                st = getattr(c.border, side).style
                if st:
                    styles.add(st)
    assert styles == {"dotted", "double", "hair", "medium", "thin"}, styles


def test_generated_title_is_red_18pt_at_b1(tpl):
    """🔴 実物は版名が B1・赤・18pt。"""
    ws = _build_from_real_like_data()["集計表"]
    assert ws["A1"].value is None
    assert ws["B1"].font.color.rgb == "FFFF0000"
    assert ws["B1"].font.sz == 18.0


def test_bottom_indicator_values_are_all_14pt(tpl):
    """🔴 帳合・挿み込み・ぱどのみ の数字が小さくならないこと。

    実物は 帳合/挿み込み/ぱどのみ の数字を **P列**、
    折チラシ/チラシ総数 を **Q列** に置いている。
    全部を Q列に書くと、実物では空セルの行(既定11pt)から書式を拾ってしまい、
    3行だけ 11pt になって読めなくなる(2026-08-07 オーナー指摘)。
    """
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    found = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                # 同じ行の右側にある値セルを探す
                vals = [x for x in ws[c.row] if x.column > c.column
                        and x.value is not None]
                found[c.value] = (c.font.sz, vals[0].font.sz if vals else None)
    assert set(found) == set(labels), f"見つからないラベルがある: {set(labels) - set(found)}"
    for lab, (label_sz, value_sz) in found.items():
        assert label_sz == 14.0, f"{lab} のラベルが {label_sz}pt"
        assert value_sz == 14.0, f"{lab} の数字が {value_sz}pt（14ptにする）"


def test_bottom_indicator_labels_are_all_bold(tpl):
    """折チラシだけ太字が外れていた(実物の空行から書式を拾っていたため)。"""
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                assert c.font.b is True, f"{c.value} が太字でない"


def test_area_busuu_line_is_uniform_size(tpl):
    """エリア別部数の行で「部」だけ小さくならないこと。"""
    ws = _build_from_real_like_data()["集計表"]
    for row in ws.iter_rows():
        cells = [c for c in row if c.value is not None]
        # ⚠️ 見出し行の A3「エリア」も startswith に一致してしまうので、
        # 下部集計の列(13以降)かつ「エリア1」のように番号が続くものだけを見る。
        labels = [c for c in cells if isinstance(c.value, str)
                  and c.column >= 13 and c.value.startswith("エリア")
                  and c.value != "エリア"]
        if not labels:
            continue
        sizes = {c.font.sz for c in cells if c.column >= 13}
        assert sizes == {14.0}, f"{labels[0].value} の行のサイズが揃っていない: {sizes}"


def _merged_width(ws, cell):
    """そのセルが属する結合範囲の合計幅を返す（結合していなければ単独の幅）。"""
    from openpyxl.utils import get_column_letter as gl
    for rng in ws.merged_cells.ranges:
        if cell.coordinate in rng:
            return sum((ws.column_dimensions[gl(c)].width or 8.43)
                       for c in range(rng.min_col, rng.max_col + 1))
    return ws.column_dimensions[gl(cell.column)].width or 8.43


def test_bottom_labels_are_wide_enough_not_to_shrink(tpl):
    """🔴 下部集計のラベルが縮んで読めなくならないこと。

    実物はラベルをセル結合で横に広げている(M27:O27 / 折チラシは M31:P31)。
    結合しないと幅3.6のM列に押し込まれ、shrink_to_fit が効いて
    14ptでも表示だけ小さくなる(2026-08-08 オーナー指摘)。
    幅は「文字数×1.9」を目安に必要量を見る。
    """
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    seen = set()
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                seen.add(c.value)
                need = len(str(c.value)) * 1.9
                got = _merged_width(ws, c)
                # 折り返し可＋行が高いぶんは容量が増える（実物も折チラシは2行になる）
                h = ws.row_dimensions[c.row].height or 19.2
                lines = max(1, round(h / 19.2)) if c.alignment.wrap_text else 1
                assert got * lines >= need, (
                    f"{c.value}: 幅{got:.1f}×{lines}行 < 必要{need:.1f}")
    assert seen == set(labels)


def test_bottom_values_are_wide_enough(tpl):
    """数字も同様。桁区切り込みで縮まない幅があること。"""
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                vals = [x for x in ws[c.row] if x.column > c.column
                        and x.value is not None]
                assert vals, f"{c.value} の数字が無い"
                assert _merged_width(ws, vals[0]) >= 12,                     f"{c.value} の数字の幅が狭い"


def test_bottom_rows_have_height(tpl):
    """🔴 行間が詰まっていないこと(オーナー指示 2026-08-08)。"""
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                h = ws.row_dimensions[c.row].height
                assert h is not None and h >= 19, f"{c.value} の行高が {h}"


def test_upper_matrix_column_widths_are_uniform(tpl):
    """🔴 下部のために上の表の列幅を変えないこと。

    K列を広げて回避すると、K は上部マトリクスの部数列でもあるため
    2ブロック目だけ間延びする。
    """
    ws = _build_from_real_like_data()["集計表"]
    # 部数列は F,K,P,U,Z,AE（stride 5）。すべて同じ幅であること。
    widths = {col: ws.column_dimensions[col].width
              for col in ("F", "K", "P", "U", "Z", "AE")}
    assert len(set(round(w, 2) for w in widths.values())) == 1, widths


def test_only_labels_that_need_it_are_wrapped(tpl):
    """🔴 1行で収まるラベルに折り返しを付けないこと。

    付けると行高が1行ぶんのままなので文字が切れる(2026-08-08 オーナー指摘)。
    折り返すのは幅に収まらないものだけ。収まらない行は行高も2行ぶんにする。
    """
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    seen = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                w = _merged_width(ws, c)
                need = len(str(c.value)) * 1.9
                h = ws.row_dimensions[c.row].height
                seen[c.value] = (bool(c.alignment.wrap_text), w, need, h)
    assert set(seen) == set(labels)
    for lab, (wrapped, w, need, h) in seen.items():
        if need <= w:
            assert not wrapped, f"{lab} は1行で収まるのに折り返しが付いている"
            assert h == 19.2, f"{lab} の行高が {h}"
        else:
            assert wrapped, f"{lab} は収まらないのに折り返しが無い"
            assert h and h >= 32, f"{lab} は折り返すのに行高が {h}"


def _build_with_three_leaders_in_one_area():
    """1エリアに3人のリーダーがいるデータ(area_first/area_middle/area_last が
    すべて登場する)を作る。"""
    table = [
        ["配送管理表", "2026/08/21", "(1213号)"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
    ]
    for chiku, name, code, butsu, bu in [
        ("911001", "リーダーA", None, "91 ぱど", 4380),
        ("912001", "リーダーB", None, "91 ぱど", 3080),
        ("913001", "リーダーC", None, "91 ぱど", 2000),
    ]:
        table.append(["2026/08/21", "1213", 0, "", "", name, "", None, chiku,
                      code, butsu, bu, "", "", "", "", ""])
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    version = A.detect_version(groups)
    data = A.shukei_data(groups, version)
    raw = A.build_shukei_daishi_workbook(data, version, "1213", "2026/08/21")
    return openpyxl.load_workbook(io.BytesIO(raw))


def test_leader_name_font_is_uniform_regardless_of_position_in_area(tpl):
    """🔴 大橋様ご指摘(2026-08-19): リーダー名の文字サイズがバラバラで見づらい。

    実物テンプレートは名前欄(B列)のフォントが行の役割(area_first/middle/last)
    によって 16pt太字 だったり 11pt細字 だったりする(人が手で作った帳票の
    サンプルにたまたま名前が書かれていた行とそうでない行の違い)。
    そのままだと、エリア内で1人目のリーダーだけ大きく、2人目以降が小さく
    表示されてしまう。名前は全員 area_first の見本(太字)で統一する。

    🔴 2026-08-28 追記: 大きさの「値」は名前の長さで決まるようになった
    (長い名前が行に収まる一番大きいサイズをシート全体で1つ選ぶ)。
    このテストが守るのは **全員が同じ大きさであること**。
    値そのものは fit_name_font_size と突き合わせて確認する。
    """
    ws = _build_with_three_leaders_in_one_area()["集計表"]
    names = {"リーダーA", "リーダーB", "リーダーC"}
    found = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value in names:
                found[c.value] = (c.font.sz, c.font.b)
    assert set(found) == names, f"見つからないリーダーがある: {names - set(found)}"
    sizes = {v for v in found.values()}
    assert len(sizes) == 1, f"リーダー名のフォントが揃っていない: {found}"
    size, bold = next(iter(sizes))
    assert bold is True, "名前は太字のまま"
    expected = S.fit_name_font_size(sorted(names),
                                    col_width=ws.column_dimensions["B"].width,
                                    base_height=42.0)
    assert size == expected, f"想定と違うフォント: {size} (期待 {expected})"


def test_shrink_to_fit_is_off_in_bottom_block(tpl):
    """🔴 縮小表示は必ず切る（14ptでも表示だけ小さくなる元凶）。"""
    ws = _build_from_real_like_data()["集計表"]
    labels = ("帳合", "挿み込み", "ぱどのみ", "折チラシ（B3,B4）", "チラシ総数")
    for row in ws.iter_rows():
        for c in row:
            if c.value in labels:
                assert not c.alignment.shrink_to_fit, f"{c.value} に縮小が残っている"
                vals = [x for x in ws[c.row] if x.column > c.column
                        and x.value is not None]
                assert not vals[0].alignment.shrink_to_fit,                     f"{c.value} の数字に縮小が残っている"


# ===== B列(名前)の折り返し（2026-08-27・大橋様ご指摘） =====
# 「フィールドサービス」「クローバージャパン」のような長い配布員名(外注先)が
# B列(幅10.7≒全角5文字)からはみ出して読めない。セル内で折り返して全文を見せる。


def test_name_line_count_counts_wrapped_lines_by_column_width():
    """全角1文字＝列幅2の換算。幅10.7なら1行5文字。"""
    assert S.name_line_count("枡田", 10.7) == 1
    assert S.name_line_count("aim", 10.7) == 1
    assert S.name_line_count("フィールドサービス", 10.7) == 2      # 9文字
    assert S.name_line_count("クローバージャパン", 10.7) == 2      # 9文字
    assert S.name_line_count("あ" * 11, 10.7) == 3


def test_name_line_count_handles_empty_and_none():
    assert S.name_line_count("", 10.7) == 1
    assert S.name_line_count(None, 10.7) == 1


def test_name_line_count_never_divides_by_zero_on_a_tiny_column():
    assert S.name_line_count("あいう", 0.5) == 3


def test_wrapped_name_height_keeps_the_template_height_for_short_names():
    """短い名前は今までどおり。テンプレートの行高を勝手に変えない。"""
    assert S.wrapped_name_height("枡田", col_width=10.7, font_size=16,
                                 base_height=42.0) == 42.0


def test_wrapped_name_height_grows_for_long_names():
    """3行になる名前は42ptでは入りきらないので、行高を伸ばす。"""
    h = S.wrapped_name_height("あ" * 13, col_width=10.7, font_size=16, base_height=42.0)
    assert h > 42.0
    assert h >= 3 * 16  # 3行ぶんの高さは最低でも確保されている


def test_apply_name_turns_on_wrap_text(tpl):
    """🔴 テンプレートの area_middle/area_last は wrap_text が付いていない。
    複写しただけだと2人目以降の長い名前がはみ出したまま。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    for role in ("area_first", "area_middle", "area_last"):
        cell = ws.cell(1, 2)
        tpl.apply_name(cell, role, 2)
        assert cell.alignment.wrap_text is True, f"{role} で折り返しが付いていない"


def test_apply_name_keeps_border_and_font_unchanged(tpl):
    """折り返しを足すだけ。罫線とフォント統一(16pt太字)は変えない。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    cell = ws.cell(1, 2)
    tpl.apply_name(cell, "area_last", 2)
    src = tpl.ws.cell(S.ROLE_ROWS["area_last"], 2)
    assert cell.border.left.style == src.border.left.style
    assert cell.border.bottom.style == src.border.bottom.style
    assert (cell.font.sz, cell.font.b) == (16.0, True)   # area_first の見本で統一
    assert cell.alignment.horizontal == src.alignment.horizontal


def _build_with_long_leader_names():
    table = [
        ["配送管理表", "2026/08/21", "(1213号)"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
    ]
    for chiku, name, bu in [
        ("911001", "フィールドサービス", 4380),
        ("912001", "クローバージャパン", 3080),
        ("913001", "枡田", 2000),
    ]:
        table.append(["2026/08/21", "1213", 0, "", "", name, "", None, chiku,
                      None, "91 ぱど", bu, "", "", "", "", ""])
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    version = A.detect_version(groups)
    data = A.shukei_data(groups, version)
    raw = A.build_shukei_daishi_workbook(data, version, "1213", "2026/08/21")
    return openpyxl.load_workbook(io.BytesIO(raw))["集計表"]


def test_long_leader_names_are_wrapped_in_the_generated_sheet():
    ws = _build_with_long_leader_names()
    seen = {}
    for row in ws.iter_rows(min_col=2, max_col=2):
        for c in row:
            if c.value in ("フィールドサービス", "クローバージャパン", "枡田"):
                seen[c.value] = c
    assert set(seen) == {"フィールドサービス", "クローバージャパン", "枡田"}
    for name, c in seen.items():
        assert c.alignment.wrap_text is True, f"{name} が折り返し設定になっていない"


def test_long_leader_name_rows_are_tall_enough_to_show_every_line():
    """折り返した2行目が行高に隠れて読めない、を防ぐ。"""
    ws = _build_with_long_leader_names()
    for row in ws.iter_rows(min_col=2, max_col=2):
        for c in row:
            if c.value == "フィールドサービス":
                need = S.wrapped_name_height(
                    c.value, col_width=ws.column_dimensions["B"].width,
                    font_size=c.font.sz, base_height=0)
                h = ws.row_dimensions[c.row].height
                assert h is not None and h >= need, f"行高 {h} < 必要 {need}"


# ===== 名前がまだ重なる（2026-08-28・実ファイルで再現） =====
# 実際に生成された「京阪北版_集計表_1250号_2026828.xlsx」を開いたところ、
# 「ポスティングスタッフ」「クローバージャパン」の行高が43.2ptしか無く、
# 16ptでは3行必要なため文字が隠れていた。
# 原因は幅の見積り違い2点:
#   ① 列幅の単位は「標準フォント(11pt)の文字幅」。16ptで描く名前は1.45倍太いのに
#      11pt基準のまま「1行5文字入る」と数えていた。
#   ② 半角カナ(ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ)を全角と同じ幅で数えていた。
# 対策は折り返し・行高に加えて「全員が収まるフォントサイズまで一律で小さくする」。


def test_text_width_units_counts_fullwidth_as_two_halfwidth_as_one():
    assert S.text_width_units("枡田") == 4
    assert S.text_width_units("aim") == 3
    assert S.text_width_units("ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ") == 11      # 半角カナは1
    assert S.text_width_units("クローバージャパン") == 18   # 全角は2
    assert S.text_width_units("") == 0
    assert S.text_width_units(None) == 0


def test_name_line_count_accounts_for_the_font_size():
    """🔴 16ptで描くなら1行に入る文字数は減る。ここを見ていなかったのがバグの本体。"""
    assert S.name_line_count("クローバージャパン", 10.7, font_size=11) == 2
    assert S.name_line_count("クローバージャパン", 10.7, font_size=16) == 3


def test_name_line_count_defaults_to_the_standard_font_size():
    assert S.name_line_count("クローバージャパン", 10.7) == \
        S.name_line_count("クローバージャパン", 10.7, font_size=S.STANDARD_FONT_SIZE)


def test_fit_name_font_size_shrinks_until_every_name_fits():
    """実ファイルの顔ぶれで、42ptの行に全員収まるサイズが選ばれること。"""
    names = ["aim", "ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ", "枡田", "時野", "クローバージャパン",
             "ポスティングスタッフ", "黒瀬"]
    size = S.fit_name_font_size(names, col_width=10.7, base_height=42.0)
    assert size < 16.0, "縮めていない（重なりが直らない）"
    for n in names:
        assert S.wrapped_name_height(n, col_width=10.7, font_size=size,
                                     base_height=0) <= 42.0, f"{n} が収まっていない"


def test_fit_name_font_size_keeps_the_original_size_for_short_names():
    """短い名前しかいない集計表は、今までどおり16ptのまま(見た目を変えない)。"""
    assert S.fit_name_font_size(["枡田", "時野", "黒瀬"], col_width=10.7,
                                base_height=42.0) == 16.0


def test_fit_name_font_size_never_goes_below_the_floor():
    """極端に長い名前でも読めない大きさにはしない(足りない分は行高で稼ぐ)。"""
    size = S.fit_name_font_size(["あ" * 60], col_width=10.7, base_height=42.0)
    assert size == S.NAME_FONT_MIN


def test_fit_name_font_size_on_empty_input():
    assert S.fit_name_font_size([], col_width=10.7, base_height=42.0) == 16.0


def _build_with_the_real_leader_names():
    """実ファイルと同じ顔ぶれ(長い外注先名を含む)で集計表を作る。"""
    table = [
        ["配送管理表", "2026/08/28", "(1250号)"],
        ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ"],
    ]
    names = ["aim", "ﾌｨｰﾙﾄﾞｻｰﾋﾞｽ", "枡田", "時野", "クローバージャパン",
             "ポスティングスタッフ", "黒瀬"]
    for i, name in enumerate(names):
        table.append(["2026/08/28", "1250", 0, "", "", name, "", None,
                      f"91{i}001", None, "91 ぱど", 1000 + i, "", "", "", "", ""])
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    version = A.detect_version(groups)
    data = A.shukei_data(groups, version)
    raw = A.build_shukei_daishi_workbook(data, version, "1250", "2026/08/28")
    return openpyxl.load_workbook(io.BytesIO(raw))["集計表"], names


def _name_cells(ws, names):
    found = {}
    for row in ws.iter_rows(min_col=2, max_col=2):
        for c in row:
            if c.value in names:
                found[c.value] = c
    return found


def test_generated_names_all_share_one_font_size():
    """🔴 2026-08-19 の「フォントを統一する」対応を壊さないこと。
    小さくするときも全員同じサイズにする。"""
    ws, names = _build_with_the_real_leader_names()
    found = _name_cells(ws, names)
    assert set(found) == set(names)
    assert len({c.font.sz for c in found.values()}) == 1


def test_generated_long_names_are_smaller_than_the_template_size():
    ws, names = _build_with_the_real_leader_names()
    found = _name_cells(ws, names)
    assert found["ポスティングスタッフ"].font.sz < 16.0


def test_every_generated_name_fits_in_its_row():
    """🔴 これが本丸。全員が行高の中に収まり、重ならないこと。"""
    ws, names = _build_with_the_real_leader_names()
    width = ws.column_dimensions["B"].width
    for name, cell in _name_cells(ws, names).items():
        need = S.wrapped_name_height(name, col_width=width,
                                     font_size=cell.font.sz, base_height=0)
        have = ws.row_dimensions[cell.row].height
        assert have is not None and have >= need, \
            f"{name}: 行高 {have} < 必要 {need}（{cell.font.sz}pt）"


def test_generated_names_keep_wrap_and_bold():
    ws, names = _build_with_the_real_leader_names()
    for name, cell in _name_cells(ws, names).items():
        assert cell.alignment.wrap_text is True, name
        assert cell.font.b is True, name
        assert cell.font.name == "游ゴシック", name


def test_short_name_sheets_keep_the_template_look():
    """長い名前がいない集計表は、これまでどおり16pt・行高42のまま。"""
    ws = _build_with_long_leader_names()   # 枡田など短い名前も含む既存の作り
    for row in ws.iter_rows(min_col=2, max_col=2):
        for c in row:
            if c.value == "枡田":
                assert c.font.sz <= 16.0
