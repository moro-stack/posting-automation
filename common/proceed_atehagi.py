"""資料作成・変換表 Phase 3: リビングプロシード あて紙の変換エンジン。

入力＝プロシードの「配布依頼書兼終了報告書」xlsx（エリア×広告主のマトリクス）。
出力＝大橋さん提供「リビング新聞あて紙」のFMTを踏襲した、エリア(担当地区)ごと1枚のあて紙。

配布依頼書の構造（実物 2025.8.29号【高槻・茨木】で確定）:
- I1 : タイトル「配布依頼書 兼 配布終了報告書【高槻・茨木】」→ エリアグループは【】の中
- A2 : 「2025年08月29日号 …」→ 号
- 2行目 G2:O2 : 広告主名（チラシ名）／5行目 G5:O5 : サイズ
- 明細は9行目から2物理行=1エリア（奇数行=データ）:
    A=件数 / B=エリアコード(高槻-2-1) / F=媒体部数 / G:O=広告主別部数、次の偶数行 B=町名
- 「合 計」行で明細終了

あて紙(FMT)への転記:
- F3=エリアグループ / E4=エリアコード / G2=媒体部数
- 6行目=媒体行: C6「リビング」・H6「ﾀﾌﾞﾛｲﾄﾞ」・I6=媒体部数
- 7行目以降=部数>0の広告主: C=広告主名 / H=サイズ / I=部数
- I48=チラシ数（部数>0の広告主件数）
"""
import io
import os
import re

import openpyxl

from common.atehagi import read_uploaded
from common.excel_io import freeze_xlsx_bytes, sanitize_sheet_chars

PROCEED_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "templates", "あて紙テンプレート_リビング.xlsx",
)

MEDIA_NAME = "リビング"
MEDIA_SIZE = "ﾀﾌﾞﾛｲﾄﾞ"

_FIRST_DETAIL_ROW = 7   # あて紙の広告主明細開始行
_LAST_DETAIL_ROW = 46
_CHIRASHI_COUNT_CELL = "I48"


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _to_int(v):
    if v is None or _s(v) == "":
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _is_number(v) -> bool:
    return _to_int(v) is not None


def _at(row, c):
    """0-indexの列cをrowから安全に引く。"""
    return row[c] if row is not None and 0 <= c < len(row) else None


def _find_cell(table, kw):
    """kw を含む最初のセルの (row, col)（0-index）を返す。無ければ None。"""
    for r, row in enumerate(table):
        if not row:
            continue
        for c, v in enumerate(row):
            if v is not None and kw in str(v):
                return (r, c)
    return None


def _find_col_in_row(row, kw):
    for c, v in enumerate(row or []):
        if v is not None and kw in str(v):
            return c
    return None


# 🔴 2026-09-04 大橋様ご依頼: あて紙6行目「リビング」の黄色塗りは、これまで常時固定
# だったが、加工前ファイルの「刷り分けＢ版」列（表記ゆれで「摺り分け」とも書かれる）に
# "B" が入っている行だけ黄色にしたい。列位置は号・エリアで動く可能性があるため、
# 他の項目と同じくヘッダー語で検出する（固定列にすると1列ずれたときに黙って誤る）。
_SURIWAKE_B_KEYWORDS = ("刷り分け", "摺り分け")


def _find_suriwake_b_col(table):
    for kw in _SURIWAKE_B_KEYWORDS:
        hit = _find_cell(table, kw)
        if hit:
            return hit[1]
    return None


def parse_haifu_irai(table):
    """配布依頼書テーブル(list[list]) を構造化する。

    ⚠️ 列位置は号・エリアで1列ずれることがある（例: 豊中版はA列に「刷り分け版」があり
    全体が1列右）。固定位置ではなく、ヘッダー語（チラシ名/配布エリア/媒体部数/件数）を
    検出して列を決める。
    """
    # タイトル→エリアグループ、号
    tp = _find_cell(table, "配布依頼書")
    group = ""
    if tp:
        m = re.search(r"【(.+?)】", str(table[tp[0]][tp[1]]))
        group = m.group(1) if m else ""
    gou = ""
    gp = _find_cell(table, "日号")
    if gp:
        m = re.search(r"\d+年\s*\d+月\s*\d+日号", str(table[gp[0]][gp[1]]).replace("\n", " "))
        gou = m.group(0) if m else ""

    # 広告主: 「チラシ名」ラベルの右～「チラシ枚数」の手前
    al = _find_cell(table, "チラシ名")
    if al is None:
        raise ValueError("広告主ヘッダー（チラシ名）が見つかりません")
    ad_row, ad_col = al
    maisuu_col = None
    for c in range(ad_col + 1, len(table[ad_row])):
        v = table[ad_row][c]
        if v is not None and "枚数" in str(v):
            maisuu_col = c
            break
    if maisuu_col is None:
        maisuu_col = len(table[ad_row])
    advertisers = []
    for c in range(ad_col + 1, maisuu_col):
        name = _s(_at(table[ad_row], c))
        if name != "":
            advertisers.append({"col": c, "name": name, "size": ""})
    # サイズ行（チラシ名ラベル列に「サイズ」がある行）から各広告主のサイズ
    for r in range(ad_row + 1, min(ad_row + 6, len(table))):
        if _s(_at(table[r], ad_col)) == "サイズ":
            for ad in advertisers:
                ad["size"] = _s(_at(table[r], ad["col"]))
            break

    # 明細ヘッダー行（「配布エリア」を含む行）から 件数/エリア/媒体部数 の列を決める
    dh = _find_cell(table, "配布エリア")
    if dh is None:
        raise ValueError("明細ヘッダー（配布エリア）が見つかりません")
    dh_row = dh[0]
    area_col = _find_col_in_row(table[dh_row], "配布エリア")
    media_col = _find_col_in_row(table[dh_row], "媒体部数")
    suriwake_col = _find_suriwake_b_col(table)

    areas = []
    r = dh_row + 1
    while r < len(table):
        code = _s(_at(table[r], area_col))
        if code == "" or code.startswith("合"):
            break
        media = _to_int(_at(table[r], media_col)) or 0
        ads = [(_to_int(_at(table[r], ad["col"])) or 0) for ad in advertisers]
        town = _s(_at(table[r + 1], area_col)) if r + 1 < len(table) else ""
        suriwake_b = (suriwake_col is not None and _s(_at(table[r], suriwake_col)) == "B")
        areas.append({"code": code, "media_busuu": media, "town": town, "ads": ads,
                      "suriwake_b": suriwake_b})
        r += 2

    return {"group": group, "gou": gou, "advertisers": advertisers, "areas": areas}


def _unique_title(title, used):
    # 🔴 半角だけを - に置換していたため、全角(／［］：＊？＼)が素通りしていた。
    #    Excel は全角を半角に正規化して判定するので、残すと修復にかかる（2026-08-10）。
    t = sanitize_sheet_chars(title, "-")[:31]
    base, n = t, 1
    while t in used:
        n += 1
        t = f"{base[:28]}_{n}"
    used.add(t)
    return t


_YELLOW_FILL = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFFFFF00")
_NO_FILL = openpyxl.styles.PatternFill(fill_type=None)


def _fill_proceed(ws, parsed, area):
    ws["F3"] = parsed["group"]
    ws["E4"] = area["code"]
    ws["G2"] = area["media_busuu"]
    ws["C6"] = MEDIA_NAME
    ws["C6"].fill = _YELLOW_FILL if area.get("suriwake_b") else _NO_FILL
    ws["H6"] = MEDIA_SIZE
    ws["I6"] = area["media_busuu"]
    for r in range(_FIRST_DETAIL_ROW, _LAST_DETAIL_ROW + 1):   # 明細クリア(C/H/I)
        ws.cell(row=r, column=3).value = None
        ws.cell(row=r, column=8).value = None
        ws.cell(row=r, column=9).value = None
    out_r = _FIRST_DETAIL_ROW
    count = 0
    for i, ad in enumerate(parsed["advertisers"]):
        busuu = area["ads"][i] if i < len(area["ads"]) else 0
        if busuu and busuu > 0 and out_r <= _LAST_DETAIL_ROW:
            ws.cell(row=out_r, column=3).value = ad["name"]    # C 配送物(広告主)
            ws.cell(row=out_r, column=8).value = ad["size"]    # H サイズ
            ws.cell(row=out_r, column=9).value = busuu          # I 部数
            out_r += 1
            count += 1
    ws[_CHIRASHI_COUNT_CELL] = count
    ws.print_area = "B1:I50"
    ws.page_setup.orientation = "portrait"


def build_proceed_atehagi_workbook(parsed, template_path=PROCEED_TEMPLATE) -> bytes:
    """エリア(担当地区)ごとに1シートずつ流し込んだあて紙ブックを bytes で返す。"""
    wb = openpyxl.load_workbook(template_path)
    base = wb[wb.sheetnames[0]]
    used = set()
    for area in parsed["areas"]:
        ws = wb.copy_worksheet(base)
        ws.title = _unique_title(area["code"], used)
        _fill_proceed(ws, parsed, area)
    wb.remove(base)
    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())


def proceed_atehagi_filename(parsed) -> str:
    group = parsed.get("group") or "リビング"
    gou = parsed.get("gou") or ""
    ymd = re.sub(r"\D", "", gou)[:8]
    parts = ["リビングプロシード", "あて紙", group]
    if ymd:
        parts.append(ymd)
    return "_".join(p for p in parts if p) + ".xlsx"


def read_and_parse(name: str, data: bytes):
    """アップロードされた配布依頼書を読み、構造化して返す。"""
    return parse_haifu_irai(read_uploaded(name, data))
