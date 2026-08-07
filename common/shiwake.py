"""仕分け表。倉庫に届いたチラシを配布員ごとの山に分けるための作業チェック表。

設計: docs/superpowers/specs/2026-08-07-shiwake-hyo-design.md

入力は「配送管理表」(17列)。あて紙・集計表が読む「その他配送管理表」とは
別のファイルだが列は同じ。1人1枚(印刷したとき)になるよう、1シートに全員を並べて
人ごとに改ページを入れる。
"""
import datetime as dt
import io

import openpyxl

# 異動 がこれの人は仕分け表に入れない(オーナー指示 2026-08-07)。
ABSENT_MARK = "休"

# チラシサイズが空＝ぱど本誌。仕分け表には「情報誌」と書く(オーナー指示)。
PADO_SIZE_LABEL = "情報誌"

# 配送管理表の列名。2行目がヘッダで、この並びで来る。
_COLS = ("配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所", "電話番号",
         "担当地区", "チラシコード", "配送物", "配布部数", "配送備考", "町界名",
         "街区（番地）名称", "受注種別", "チラシサイズ")


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _to_int(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def format_junni(value) -> str:
    """配送順位を元の表記に戻す。

    配送順位は `9101-04-01` のようなコード(ルート-順-枝番)だが、Excel が
    日付として読んでしまい datetime(9101, 4, 1) になる。そのまま書くと
    `9101/4/1` と表示されて別物になるため、元の桁数の表記に戻す。
    """
    if value is None or value == "":
        return ""
    if isinstance(value, dt.datetime):
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    if isinstance(value, dt.date):
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    return str(value).strip()


def rows_from_haiso_table(table):
    """配送管理表の明細を辞書のリストに正規化する。

    ヘッダ行(「配布日」で始まる行)を探し、その次の行から明細として読む。
    ぱどんな が空の行は明細ではないので飛ばす。
    """
    header_at = None
    for i, row in enumerate(table):
        vals = [_s(c) for c in row]
        if "配布日" in vals and "ぱどんな" in vals and "配送物" in vals:
            header_at = i
            idx = {name: j for j, name in enumerate(vals) if name}
            break
    if header_at is None:
        raise ValueError("ヘッダー行（配布日・ぱどんな・配送物）が見つかりません")

    missing = [c for c in ("ぱどんな", "配送物", "配布部数") if c not in idx]
    if missing:
        raise ValueError(f"配送管理表に必要な列がありません: {missing}")

    def get(row, name):
        j = idx.get(name)
        return row[j] if j is not None and j < len(row) else None

    rows = []
    for row in table[header_at + 1:]:
        if not row or get(row, "ぱどんな") in (None, ""):
            continue
        rows.append({
            "padonna": _s(get(row, "ぱどんな")),
            "ido": _s(get(row, "異動")),
            "junni": get(row, "配送順位"),
            "chiku": _s(get(row, "担当地区")),
            "chirashi": _s(get(row, "配送物")),
            "busuu": _to_int(get(row, "配布部数")),
            "size": _s(get(row, "チラシサイズ")),
            "gou": _s(get(row, "号数")),
            "haifubi": get(row, "配布日"),
        })
    return rows


def shiwake_groups(rows):
    """配布員ごとにまとめて (groups, warnings) を返す。

    groups は配送順位の昇順(空は末尾)。各要素:
        {"name", "junni", "items": [{"chirashi", "busuu", "size"}], "total"}

    部数は**配布員ごとの合計**。同じ人が複数の担当地区を持つとき、同じチラシは
    足して1行にする(倉庫では人単位で山を作るため)。

    warnings:
        {"excluded": [休で外した人], "unknown_ido": [(人, 見慣れない異動値)]}

    🔴 異動が「休」以外の見慣れない値でも人を落とさない。落として山が足りなく
    なるほうが事故として重い。残したうえで呼び出し側に警告を渡す。
    """
    excluded = []
    unknown = []
    by_person = {}

    for r in rows:
        name = r["padonna"]
        ido = r["ido"]
        if ido == ABSENT_MARK:
            if name not in excluded:
                excluded.append(name)
            continue
        if ido and (name, ido) not in unknown:
            unknown.append((name, ido))

        p = by_person.setdefault(name, {"name": name, "junni": None, "items": {}})
        if p["junni"] in (None, "") and r["junni"] not in (None, ""):
            p["junni"] = r["junni"]
        key = r["chirashi"]
        it = p["items"].setdefault(key, {"chirashi": key, "busuu": 0, "size": None})
        it["busuu"] += r["busuu"]
        if it["size"] is None:
            it["size"] = r["size"] or PADO_SIZE_LABEL

    # 休だけの人が by_person に混ざることは無いが、休と稼働が同居する人は残す
    excluded = [n for n in excluded if n not in by_person]

    groups = []
    for p in by_person.values():
        items = list(p["items"].values())
        groups.append({
            "name": p["name"],
            "junni": format_junni(p["junni"]),
            "items": items,
            "total": sum(i["busuu"] for i in items),
        })

    # 配送順位の昇順。空は末尾。
    groups.sort(key=lambda g: (g["junni"] == "", g["junni"], g["name"]))
    return groups, {"excluded": excluded, "unknown_ido": unknown}


def _fmt_haifubi(v) -> str:
    if isinstance(v, (dt.datetime, dt.date)):
        return f"{v.year}/{v.month:02d}/{v.day:02d}"
    return _s(v)


def build_shiwake_workbook(groups, gou=None, haifubi=None) -> bytes:
    """1シートに全員・1人ごとに改ページした xlsx を返す。

    シートを人数分に分けないのは、24人なら24シートになり一括印刷しづらいため。
    """
    from openpyxl.styles import Alignment, Border, Font, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "仕分け表"

    thin = Side(style="thin")
    medium = Side(style="medium")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_box = Border(left=medium, right=medium, top=medium, bottom=medium)
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")
    right = Alignment(horizontal="right", vertical="center")

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 8

    r = 1
    for n, g in enumerate(groups):
        if n:
            ws.row_breaks.append(openpyxl.worksheet.pagebreak.Break(id=r - 1))

        top = f"{_fmt_haifubi(haifubi)}　{gou}号" if (gou or haifubi) else ""
        c = ws.cell(r, 1, top)
        c.font = Font(size=11)
        c.alignment = left
        r += 1

        c = ws.cell(r, 1, f"配布員: {g['name']}")
        c.font = Font(size=16, bold=True)
        c.alignment = left
        ws.row_dimensions[r].height = 24
        c = ws.cell(r, 3, f"配送順位: {g['junni']}")
        c.font = Font(size=12)
        c.alignment = left
        r += 1

        for col, label in enumerate(("チラシ名", "部数", "サイズ", "済"), start=1):
            c = ws.cell(r, col, label)
            c.font = Font(size=11, bold=True)
            c.alignment = center
            c.border = head_box
        r += 1

        for it in g["items"]:
            ws.cell(r, 1, it["chirashi"]).border = box
            ws.cell(r, 1).alignment = left
            cb = ws.cell(r, 2, it["busuu"])
            cb.border = box
            cb.alignment = right
            cb.number_format = "#,##0"
            cs = ws.cell(r, 3, it["size"])
            cs.border = box
            cs.alignment = center
            # チェック欄は空のまま。作業員が手で書く。
            ws.cell(r, 4).border = box
            ws.row_dimensions[r].height = 22
            r += 1

        c = ws.cell(r, 1, "合計")
        c.border = head_box
        c.alignment = center
        c.font = Font(bold=True)
        ct = ws.cell(r, 2, g["total"])
        ct.border = head_box
        ct.alignment = right
        ct.font = Font(bold=True)
        ct.number_format = "#,##0"
        ws.cell(r, 3).border = head_box
        ws.cell(r, 4).border = head_box
        r += 2

    ws.page_setup.orientation = "portrait"
    ws.print_options.horizontalCentered = False

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def shiwake_filename(gou=None, haifubi=None) -> str:
    parts = [p for p in [_fmt_haifubi(haifubi).replace("/", ""),
                         (f"{gou}号" if gou else None), "仕分け表"] if p]
    return "_".join(parts) + ".xlsx"
