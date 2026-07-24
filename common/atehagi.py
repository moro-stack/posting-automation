"""資料作成・変換表 Phase 1: 京阪あて紙の変換エンジン（純関数＋Excel生成）。

現行 VBA `Module2`（担当地区別_あてがみテンプレ反映）の再現。
DB非依存・Streamlit非依存の純関数として実装し、TDDで検証する。
"""
import csv as _csv
import io
import os
import re
from collections import OrderedDict

import openpyxl
from openpyxl.worksheet.properties import PageSetupProperties

from common.excel_io import freeze_xlsx_bytes

KEIHAN_KITA = "北"
KEIHAN_MINAMI = "南"


_CODE_MAX_DIGITS = 6      # 担当地区コードの最大桁（北版5桁 / 南版6桁）
_ZEN2HAN = str.maketrans("０１２３４５６７８９", "0123456789")


def area_code(chiku) -> str:
    """担当地区コードを数字のみ抽出して正規化する（グループ化キー・シート名に使う）。

    北版は5桁（10101）、南版は6桁（911001）。7桁以上の異常値のみ末尾6桁に切る。
    日本語入力のままの全角数字も受け付ける（画面から手入力されるため）。
    ※旧 area5 は「末尾5桁」に切っていたため、南版の先頭1桁が落ちていた。
    """
    digits = re.sub(r"\D", "", str(chiku).translate(_ZEN2HAN))
    return digits[-_CODE_MAX_DIGITS:] if len(digits) > _CODE_MAX_DIGITS else digits


def area_code6(chiku) -> str:
    """あて紙に印字する担当地区コード（6桁ゼロ埋め）。

    北版 10101 → '010101' ／ 南版 911001 → '911001'（既に6桁なので0は足さない）。
    先頭2桁が配送物名の番号（「01 ぱど」「91 ぱど」）と一致する（関西ぱど 2026-07-23）。
    """
    return area_code(chiku).zfill(_CODE_MAX_DIGITS)


def area_no(chiku) -> str:
    """エリア番号。担当地区コードの値をそのまま使い、勝手に振り直さない。

    6桁ゼロ埋めの先頭2桁（＝配送物名の番号「01 ぱど」「91 ぱど」と一致する部分）から
    表記上の先頭0だけを落とす。
      北版 10101 → '010101' → '01' → **'1'**（従来どおり）
      南版 911001 → '911001' → **'91'**（'1' に読み替えない）
    先頭0付きのテキスト（'010101'）で来ても同じ番号になる。
    """
    return area_code6(chiku)[:2].lstrip("0") or "0"


def chiku_name(version: str, chiku) -> str:
    """版設定に応じた地区名を返す。京阪北版はエリア番号で判定。"""
    if version == KEIHAN_KITA:
        head = area_no(chiku)
        if head in ("1", "2", "3"):
            return "枚方・交野"
        if head in ("4", "5"):
            return "寝屋川・枚方"
        return ""
    if version == KEIHAN_MINAMI:
        return "守口・門真"          # 南版は担当地区によらず共通（関西ぱど 2026-07-23）
    raise ValueError(f"未知の版: {version!r}")


_HEADER_KEY = "担当地区"
_FIELDS = {
    "haifubi": "配布日", "gou": "号数", "padonna": "ぱどんな",
    "chiku": "担当地区", "haisoubutsu": "配送物", "busuu": "配布部数",
    "size": "チラシサイズ",
}


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _to_int(v):
    if v is None or _s(v) == "":
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (ValueError, TypeError):
        return None


def rows_from_table(table):
    """配送管理表テーブル（list[list]）を正規化行 list[dict] に変換する。

    ヘッダー行（"担当地区" を含む行）を自動検出し、以降のデータ行のうち
    担当地区が空でない行を返す。各dictキー:
    padonna, chiku, haisoubutsu, busuu(int|None), size, gou, haifubi。
    """
    hidx = None
    for i, row in enumerate(table):
        if row and any(_s(c) == _HEADER_KEY for c in row):
            hidx = i
            break
    if hidx is None:
        raise ValueError("ヘッダー行（担当地区）が見つかりません")
    header = [_s(c) for c in table[hidx]]
    col = {name: header.index(h) for name, h in _FIELDS.items() if h in header}
    if "chiku" not in col:
        raise ValueError("担当地区列がありません")

    def get(row, field):
        j = col.get(field)
        if j is None or j >= len(row):
            return None
        return row[j]

    out = []
    for row in table[hidx + 1:]:
        if row is None:
            continue
        chiku = get(row, "chiku")
        if _s(chiku) == "":
            continue
        out.append({
            "padonna": _s(get(row, "padonna")),
            "chiku": chiku,
            "haisoubutsu": _s(get(row, "haisoubutsu")),
            "busuu": _to_int(get(row, "busuu")),
            "size": _s(get(row, "size")),
            "gou": _to_int(get(row, "gou")),
            "haifubi": _s(get(row, "haifubi")),
        })
    return out


def group_by_chiku(rows):
    """担当地区コード（area_code）をキーに、出現順を保持して束ねる。"""
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(area_code(r["chiku"]), []).append(r)
    return groups


_PADO_MARK = "ぱど"


def pado_row(group_rows):
    """グループ内の「ぱど」行（配送物に'ぱど'を含む行）を返す。無ければ先頭行。

    あて紙上部の部数・リーダー名の基準行。実データでは常に先頭行がぱど行だが、
    並び順に依存すると入力の順序が変わったときに静かに誤るため明示的に探す
    （関西ぱど 2026-07-23「部数は…ぱどの配布部数を基準にする」）。
    """
    for r in group_rows:
        if _PADO_MARK in _s(r.get("haisoubutsu")):
            return r
    return group_rows[0]


def parse_area_codes(text):
    """担当地区コードの入力（カンマ/空白/改行区切り）を6桁ゼロ埋め一覧に正規化する。

    「10101」でも「010101」でも同じコードとして扱う。重複は除き、入力順を保つ。
    """
    out, seen = [], set()
    for tok in re.split(r"[,\s、，]+", str(text or "")):
        digits = re.sub(r"\D", "", tok.translate(_ZEN2HAN))
        if not digits:
            continue
        if len(digits) > _CODE_MAX_DIGITS:
            # 「010101046501」のように区切りを忘れた入力。末尾6桁だけ採ると
            # 前半の地区が黙って消えるため、不正としてまとめて弾く。
            return []
        code = area_code6(digits)
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def select_groups(groups, codes):
    """指定した担当地区コードのグループだけを、指定された順で抜き出す。

    codes は文字列（カンマ区切り可）でもコード一覧でもよい。ゼロ埋めの有無は問わない。
    存在しないコードは黙って無視する（呼び出し側で差集合を取って警告できる）。
    """
    if isinstance(codes, str):
        codes = parse_area_codes(codes)
    index = {area_code6(k): k for k in groups}
    selected = OrderedDict()
    for c in codes:
        key = index.get(area_code6(c))
        if key is not None and key not in selected:
            selected[key] = groups[key]
    return selected


_VERSION_PREFIX = {
    KEIHAN_KITA: {"01", "02", "03", "04", "05"},
    KEIHAN_MINAMI: {"91", "92"},
}


def detect_version(groups):
    """担当地区コードから版（北/南）を推定する。判断できなければ None。

    6桁ゼロ埋めの先頭2桁が、配送物名の番号（「01 ぱど」「91 ぱど」）と一致することを使う。
    版を取り違えたまま生成すると、地区名が全件誤った紙が黙って出来上がるため、
    画面で選ばれた版との食い違いを検出する用途に使う。
    """
    counts = {v: 0 for v in _VERSION_PREFIX}
    for chiku in groups:
        head2 = area_code6(chiku)[:2]
        for ver, heads in _VERSION_PREFIX.items():
            if head2 in heads:
                counts[ver] += 1
    hit = [v for v, n in counts.items() if n]
    return hit[0] if len(hit) == 1 else None


def overflow_areas(groups, limit=None):
    """明細がテンプレの行数上限を超える地区の (コード, 明細件数) 一覧を返す。

    テンプレの明細枠は13行しかなく、超過分は印字できない。
    無警告で落とすと紙とチラシ数(I18)が食い違うため、呼び出し側で必ず通知する。
    """
    lim = _MAX_DETAIL_ROWS if limit is None else limit
    return [(c, len(rs)) for c, rs in groups.items() if len(rs) > lim]


def chirashi_count(group_rows) -> int:
    """グループ内でチラシサイズが非空の明細件数（I18）。"""
    return sum(1 for r in group_rows if _s(r.get("size")) != "")


TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "templates", "あて紙テンプレート_京阪.xlsx",
)

_MERGES = ("A3:E3", "D4:G4", "G2:I2")
_MAX_DETAIL_ROWS = 13   # row5〜17（row18は集計行）

_VERSION_LABEL = {KEIHAN_KITA: "京阪北版", KEIHAN_MINAMI: "京阪南版"}


def _unique_title(title, used):
    t = str(title)[:31]
    base, n = t, 1
    while t in used:
        n += 1
        t = f"{base[:28]}_{n}"
    used.add(t)
    return t


def _apply_merges(ws):
    existing = {str(m) for m in ws.merged_cells.ranges}
    for rng in _MERGES:
        if rng not in existing:
            ws.merge_cells(rng)


def _set_print(ws):
    ws.print_area = "A1:J18"
    ws.page_setup.orientation = "portrait"
    # 用紙(B5 JIS=テンプレ由来)の左右・上下ともに中央へ（関西ぱど 2026-07-23）
    ws.print_options.horizontalCentered = True
    ws.print_options.verticalCentered = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    if ws.sheet_properties.pageSetUpPr is None:
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    else:
        ws.sheet_properties.pageSetUpPr.fitToPage = True


def _fill_atehagi(ws, chiku, rows, version):
    base = pado_row(rows)               # 上部の部数・名前は「ぱど行」が基準
    ws["A1"] = chiku_name(version, chiku)
    ws["A3"] = base["padonna"]
    # 担当地区は6桁ゼロ埋めの1セルに印字する（関西ぱど 2026-07-23）。
    # テンプレ固定の C4=0 は「5桁コードを6桁に見せる」ための作りだったので消す。
    ws["D4"] = area_code6(chiku)
    ws["C4"] = None
    ws["G2"] = base["busuu"]
    for r in range(5, 19):          # 明細領域をクリア（H18ラベルもクリア=マクロ挙動）
        for c in range(2, 11):
            ws.cell(row=r, column=c).value = None
    for i, row in enumerate(rows[:_MAX_DETAIL_ROWS]):
        rr = 5 + i
        ws.cell(row=rr, column=2).value = row["haisoubutsu"]       # B
        ws.cell(row=rr, column=9).value = row["size"] or None       # I
        ws.cell(row=rr, column=10).value = row["busuu"]             # J
    ws["I18"] = chirashi_count(rows)
    _apply_merges(ws)
    _set_print(ws)


def build_atehagi_workbook(groups, version, template_path=TEMPLATE_PATH) -> bytes:
    """担当地区ごとに1シートずつ流し込んだあて紙ブックを bytes で返す。"""
    wb = openpyxl.load_workbook(template_path)
    base = wb[wb.sheetnames[0]]
    used = set()
    for chiku, rows in groups.items():
        ws = wb.copy_worksheet(base)
        ws.title = _unique_title(chiku, used)
        _fill_atehagi(ws, chiku, rows, version)
    wb.remove(base)
    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())


def atehagi_filename(version, rows, chiku=None) -> str:
    """あて紙のファイル名。chiku を渡すと担当地区コードを末尾に付ける（単票の刷り直し用）。"""
    label = _VERSION_LABEL.get(version, "京阪")
    gou = next((r["gou"] for r in rows if r.get("gou")), None)
    hb = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
    ymd = re.sub(r"\D", "", str(hb))[:8]
    parts = [label, "あて紙"]
    if gou:
        parts.append(f"{gou}号")
    if ymd:
        parts.append(ymd)
    if chiku:
        codes = [chiku] if isinstance(chiku, (str, int)) else list(chiku)
        suffix = area_code6(codes[0])
        if len(codes) > 1:
            suffix += f"他{len(codes) - 1}件"
        parts.append(suffix)
    return "_".join(parts) + ".xlsx"


def jisseki_courses(groups, version):
    """実績表台紙の1コース分データ。挟み込みチラシ(size非空)が1つ以上ある
    コースのみ。ぱどのみ地区は除外。flyers は元の並び順。"""
    out = []
    for chiku, rows in groups.items():
        flyers = [
            {"name": r["haisoubutsu"], "count": r["busuu"]}
            for r in rows if _s(r.get("size")) != ""
        ]
        if not flyers:
            continue
        name = chiku_name(version, chiku)
        code = area_code6(chiku)
        out.append({
            "code": code,
            "chiku_name": name,
            "course_name": f"{code} {name}",
            "flyers": flyers,
        })
    return out


def _md_from(haifubi) -> str:
    """配布日から "M/D"（例 6/26）。datetime/文字列どちらも可。"""
    import datetime
    if isinstance(haifubi, (datetime.date, datetime.datetime)):
        return f"{haifubi.month}/{haifubi.day}"
    s = str(haifubi or "")
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", s)
    if m:
        return f"{int(m.group(2))}/{int(m.group(3))}"
    return ""


def build_jisseki_daishi_workbook(courses, version, gou, haifubi, per_row=4) -> bytes:
    """実績表を実物台紙スタイルで出力。1コース=ヘッダー行(コース名)+本文行
    (案件名/枚数を1チラシ1行)+サイン行(横線付き)。per_row コース/行で折り返す。"""
    from openpyxl.styles import Alignment, Font, Border, Side
    from openpyxl.worksheet.properties import PageSetupProperties

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "実績表"
    ncol = per_row * 2

    label = _VERSION_LABEL.get(version, "京阪")
    md = _md_from(haifubi)
    gou_part = f"{gou}号" if gou else "号"
    title = f"{md} ／ {gou_part}　{label}"
    ws.cell(row=1, column=1, value=title)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    t = ws.cell(row=1, column=1)
    t.font = Font(bold=True, size=16)
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    thin = Side(style="thin")
    thick = Side(style="medium")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    topleft = Alignment(horizontal="left", vertical="top", wrap_text=True)
    topright = Alignment(horizontal="right", vertical="top", wrap_text=True)
    signalign = Alignment(horizontal="left", vertical="bottom")

    ROWS_PER = 3  # ヘッダー・本文・サイン

    for i, c in enumerate(courses):
        grp, col = divmod(i, per_row)
        top = 2 + grp * ROWS_PER
        rh, rb, rs = top, top + 1, top + 2
        c0 = 1 + col * 2
        c1 = c0 + 1
        ws.merge_cells(start_row=rh, start_column=c0, end_row=rh, end_column=c1)
        h = ws.cell(row=rh, column=c0, value=c["course_name"])
        h.font = Font(bold=True, size=11)
        h.alignment = center
        names = "\n".join(f["name"] for f in c["flyers"])
        counts = "\n".join(str(f["count"]) for f in c["flyers"])
        ws.cell(row=rb, column=c0, value=names).alignment = topleft
        ws.cell(row=rb, column=c1, value=counts).alignment = topright
        ws.merge_cells(start_row=rs, start_column=c0, end_row=rs, end_column=c1)
        s = ws.cell(row=rs, column=c0, value="サイン：")
        s.alignment = signalign
        for (r, cc) in [(rh, c0), (rh, c1), (rb, c0), (rb, c1), (rs, c0), (rs, c1)]:
            ws.cell(row=r, column=cc).border = Border(
                left=thick if cc == c0 else thin,
                right=thick if cc == c1 else thin,
                top=thick if r == rh else thin,
                bottom=thick if r == rs else thin,
            )

    ngrp = (len(courses) + per_row - 1) // per_row
    for grp in range(ngrp):
        block = courses[grp * per_row:(grp + 1) * per_row]
        max_lines = max(len(c["flyers"]) for c in block)
        top = 2 + grp * ROWS_PER
        ws.row_dimensions[top].height = 20
        ws.row_dimensions[top + 1].height = max(36, max_lines * 18)
        ws.row_dimensions[top + 2].height = 28
    for col in range(per_row):
        ws.column_dimensions[openpyxl.utils.get_column_letter(1 + col * 2)].width = 24
        ws.column_dimensions[openpyxl.utils.get_column_letter(2 + col * 2)].width = 6

    last_row = 1 + ngrp * ROWS_PER if ngrp else 1
    last_col = openpyxl.utils.get_column_letter(ncol)
    ws.print_area = f"A1:{last_col}{last_row}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())


def jisseki_filename(version, rows) -> str:
    label = _VERSION_LABEL.get(version, "京阪")
    gou = next((r["gou"] for r in rows if r.get("gou")), None)
    hb = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
    ymd = re.sub(r"\D", "", str(hb))[:8]
    parts = [label, "挟み込み実績表"]
    if gou:
        parts.append(f"{gou}号")
    if ymd:
        parts.append(ymd)
    return "_".join(parts) + ".xlsx"


def shukei_data(groups, version):
    """集計表の集計。逆算で確定したロジック:
    - エリア = 担当地区コード先頭1桁 / リーダー = ぱどんな
    - (エリア,リーダー)ごとに、地区を「チラシ種類数」でグループ化し 地区数・部数 を出す
    - 総計/エリア別部数/チラシ総数/ぱどのみ部数 も算出
    """
    from collections import defaultdict

    per = defaultdict(lambda: {"chiku": 0, "busuu": 0,
                               "by_type": defaultdict(lambda: [0, 0])})
    area_busuu = defaultdict(int)
    area_chiku = defaultdict(int)
    type_dist = defaultdict(lambda: [0, 0])   # チラシ種類数 -> [地区数, 部数]（全体分布）
    total_chiku = 0
    total_busuu = 0
    chirashi_sou = 0
    pado_only_busuu = 0
    choai_busuu = 0        # 帳合＝チラシ2種類以上の地区の部数
    sashikomi_busuu = 0    # 挿込＝チラシがある地区の部数（=総-ぱどのみ）
    for chiku, rows in groups.items():
        area = area_no(chiku)
        base = pado_row(rows)             # あて紙・実績表と同じ「ぱど行」基準
        leader = base["padonna"]
        busuu = base["busuu"] or 0
        ctype = sum(1 for r in rows if _s(r.get("size")) != "")   # チラシ種類数
        total_chiku += 1
        total_busuu += busuu
        area_busuu[area] += busuu
        area_chiku[area] += 1
        type_dist[ctype][0] += 1
        type_dist[ctype][1] += busuu
        p = per[(area, leader)]
        p["chiku"] += 1
        p["busuu"] += busuu
        p["by_type"][ctype][0] += 1
        p["by_type"][ctype][1] += busuu
        if ctype == 0:
            pado_only_busuu += busuu
        if ctype >= 1:
            sashikomi_busuu += busuu
        if ctype >= 2:
            choai_busuu += busuu
        for r in rows:
            if _s(r.get("size")) != "":
                chirashi_sou += (r["busuu"] or 0)
    return {
        "per": per, "area_busuu": dict(area_busuu), "area_chiku": dict(area_chiku),
        "type_dist": {k: list(v) for k, v in type_dist.items()},
        "total_chiku": total_chiku, "total_busuu": total_busuu,
        "chirashi_sou": chirashi_sou, "pado_only_busuu": pado_only_busuu,
        "choai_busuu": choai_busuu, "sashikomi_busuu": sashikomi_busuu,
    }


def build_shukei_workbook(data, version, title="京阪 集計表") -> bytes:
    """集計表Excel（リーダー別×チラシ種類数の明細＋エリア別＋総計）を bytes で返す。"""
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "集計表"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["エリア", "リーダー", "チラシ種類数", "地区数(コース数)", "配布部数"])
    hdr = ws.max_row
    for c in range(1, 6):
        ws.cell(row=hdr, column=c).font = Font(bold=True)
    for (area, leader) in sorted(data["per"].keys()):
        p = data["per"][(area, leader)]
        for ctype in sorted(p["by_type"].keys()):
            ku, bu = p["by_type"][ctype]
            ws.append([area, leader, ctype, ku, bu])
        row = ws.append(["", f"　{leader} 計", "", p["chiku"], p["busuu"]])
        ws.cell(row=ws.max_row, column=2).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=4).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=5).font = Font(bold=True)

    ws.append([])
    ws.append(["エリア別", "地区数", "配布部数"])
    for c in range(1, 4):
        ws.cell(row=ws.max_row, column=c).font = Font(bold=True)
    for area in sorted(data["area_busuu"].keys()):
        ws.append([f"エリア{area}", data["area_chiku"][area], data["area_busuu"][area]])

    ws.append([])
    ws.append(["チラシ種類数分布", "地区数", "部数"])
    for c in range(1, 4):
        ws.cell(row=ws.max_row, column=c).font = Font(bold=True)
    for t in sorted(data["type_dist"].keys(), reverse=True):
        ku, bu = data["type_dist"][t]
        ws.append([f"{t}種", ku, bu])

    ws.append([])
    ws.append(["総計", ""])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    ws.append(["総地区数", data["total_chiku"]])
    ws.append(["総配布部数", data["total_busuu"]])
    ws.append(["チラシ総数(全チラシ部数)", data["chirashi_sou"]])
    ws.append(["帳合(チラシ2種以上の地区の部数)", data["choai_busuu"]])
    ws.append(["挿込(チラシがある地区の部数)", data["sashikomi_busuu"]])
    ws.append(["ぱどのみ部数(チラシ無し)", data["pado_only_busuu"]])

    for col, w in zip("ABCDE", [12, 18, 14, 16, 12]):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())


def _shukei_layout(data):
    """集計表 上部マトリクスの並び。エリア昇順→リーダー(部数降順)→
    チラシ種類数昇順の (種類数, コース数, 部数)。"""
    areas = {}
    for (area, leader), p in data["per"].items():
        types = [(t, p["by_type"][t][0], p["by_type"][t][1])
                 for t in sorted(p["by_type"])]
        areas.setdefault(area, []).append({
            "name": leader, "chiku": p["chiku"], "busuu": p["busuu"], "types": types,
        })
    out = []
    for area in sorted(areas, key=lambda a: int(a)):
        leaders = sorted(areas[area], key=lambda l: (-l["busuu"], l["name"]))
        out.append({"area": area, "leaders": leaders})
    return out


def shukei_filename(version, rows) -> str:
    label = _VERSION_LABEL.get(version, "京阪")
    gou = next((r["gou"] for r in rows if r.get("gou")), None)
    hb = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
    ymd = re.sub(r"\D", "", str(hb))[:8]
    parts = [label, "集計表"]
    if gou:
        parts.append(f"{gou}号")
    if ymd:
        parts.append(ymd)
    return "_".join(parts) + ".xlsx"


def read_uploaded(name: str, data: bytes):
    """アップロードされたCSV/xlsxの先頭シートをテーブル（list[list]）化する。

    xlsx/xlsm/xls は先頭シートを読み取り、CSVは cp932→utf-8-sig→utf-8 の順で復号する。
    """
    lower = str(name).lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return table
    text = None
    for enc in ("cp932", "utf-8-sig", "utf-8"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSVの文字コードを判別できません（cp932/utf-8）")
    return [row for row in _csv.reader(io.StringIO(text))]
