"""資料作成・変換表 Phase 1: 京阪あて紙の変換エンジン（純関数＋Excel生成）。

現行 VBA `Module2`（担当地区別_あてがみテンプレ反映）の再現。
DB非依存・Streamlit非依存の純関数として実装し、TDDで検証する。
"""
import io
import os
import re
from collections import OrderedDict

import openpyxl
from openpyxl.worksheet.properties import PageSetupProperties

from common.excel_io import freeze_xlsx_bytes

KEIHAN_KITA = "北"
KEIHAN_MINAMI = "南"


def area5(chiku) -> str:
    """担当地区コードを数字のみ抽出し末尾5桁に正規化する（VBA GetArea5 同等）。"""
    digits = re.sub(r"\D", "", str(chiku))
    return digits[-5:] if len(digits) >= 5 else digits


def chiku_name(version: str, chiku) -> str:
    """版設定に応じた地区名を返す。京阪北版は担当地区コード先頭1桁で判定。"""
    code = area5(chiku)
    if version == KEIHAN_KITA:
        head = code[:1]
        if head in ("1", "2", "3"):
            return "枚方・交野"
        if head in ("4", "5"):
            return "寝屋川・枚方"
        return ""
    if version == KEIHAN_MINAMI:
        raise NotImplementedError("京阪南版の地区名ルールは未設定です")
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
    """担当地区コード（area5）をキーに、出現順を保持して束ねる。"""
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(area5(r["chiku"]), []).append(r)
    return groups


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
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    if ws.sheet_properties.pageSetUpPr is None:
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    else:
        ws.sheet_properties.pageSetUpPr.fitToPage = True


def _fill_atehagi(ws, chiku, rows, version):
    ws["A1"] = chiku_name(version, chiku)
    ws["A3"] = rows[0]["padonna"]
    ws["D4"] = int(chiku)
    ws["G2"] = rows[0]["busuu"]
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


def atehagi_filename(version, rows) -> str:
    label = _VERSION_LABEL.get(version, "京阪")
    gou = next((r["gou"] for r in rows if r.get("gou")), None)
    hb = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
    ymd = re.sub(r"\D", "", str(hb))[:8]
    parts = [label, "あて紙"]
    if gou:
        parts.append(f"{gou}号")
    if ymd:
        parts.append(ymd)
    return "_".join(parts) + ".xlsx"
