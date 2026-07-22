"""資料作成・変換表 Phase 4: アドバリュー 依頼表 → 報告書化＋京阪南版エリア被り判定。

入力2つ:
- アドバリュー依頼表（A=GeoCode / B=市区名 / C=町丁目名(大久保町1) / D=世帯数15 /
  E=共同住宅主世帯数15 / F=暫定部数 / G=クライアント①○× / H=クライアント②○× /
  I=配布日メモ / J=併配チラシ暫定部数 / K=備考(店舗名) / L=投禁物件 / M=配布日 / N=重複）
- 京阪南版 配送管理表（京阪北と同じ17列。N=町界名 / O=街区(番地)名称 / I=担当地区6桁）

やること: 依頼表の各「町丁目名」を 町名＋丁目 に分解し、京阪南の 町界名＋街区 に照合して
担当地区を割り出す（マッチ=京阪南と被り／未マッチ=被らない）。丁目パーサは現行マクロの
取りこぼしバグ（「1丁目・2丁目11～34」等で2丁目以降を落とす）を直して正確に判定する。
出力=依頼表の列＋「担当地区(被り)」＋「被り/非被り」の報告書Excel。
"""
import io
import re

import openpyxl

from common.atehagi import read_uploaded
from common.excel_io import freeze_xlsx_bytes

_ZEN2HAN = str.maketrans("０１２３４５６７８９", "0123456789")


def _z2h(s) -> str:
    return "" if s is None else str(s).translate(_ZEN2HAN)


def normalize_town(s) -> str:
    """町名の突合キー: 全角数字→半角、空白除去。"""
    return re.sub(r"\s|　", "", _z2h(s)).strip()


def parse_choume_from_gaiku(gaiku):
    """京阪南マスタの「街区（番地）名称」から、含まれる丁目番号の集合を返す。

    例: '1丁目1～21'→{1} / '2・3丁目'→{2,3} / '4・5丁目'→{4,5} /
        '6丁目51～57・7丁目'→{6,7} / '1丁目・2丁目11～34'→{1,2}
    丁目が無い（空/全域）→ 空集合（＝その町の全丁目を覆うワイルドカード扱い）。
    """
    s = _z2h(gaiku)
    if s.strip() == "":
        return set()
    s = re.sub(r"[、，]", "・", s)               # 区切りを ・ に統一
    s = re.sub(r"[～〜~－ー–—-]", "~", s)         # 範囲記号を ~ に統一
    parts = s.split("丁目")
    if len(parts) == 1:
        return set()                             # 丁目表記なし＝ワイルドカード
    choume = set()
    k = len(parts) - 1                           # 丁目 の出現回数
    for i in range(k):
        seg = parts[i]
        tokens = [t.strip() for t in seg.split("・")]
        if i == 0:
            # 先頭: 丁目の直前は全部が丁目番号（番地は丁目より後にしか来ない）
            for t in tokens:
                if re.fullmatch(r"\d+", t):
                    choume.add(int(t))
        else:
            # 途中: 「前の丁目の番地レンジ ・ 次の丁目番号」→ 末尾の素の数字だけが次の丁目
            for t in reversed(tokens):
                if re.fullmatch(r"\d+", t):
                    choume.add(int(t))
                else:
                    break
    return choume


def split_town_choume(choume_name):
    """依頼表の町丁目名を (町名, 丁目番号 or None) に分解する。例 '大久保町1'→('大久保町',1)。"""
    s = _z2h(choume_name).strip()
    s = re.sub(r"丁目$", "", s)
    m = re.match(r"^(.*?)(\d+)$", s)
    if m and m.group(1):
        return (m.group(1), int(m.group(2)))
    return (s, None)


_MASTER_HEADER_KEY = "担当地区"
_COL_CHIKU = 9      # I 担当地区
_COL_CHOUKAI = 14   # N 町界名
_COL_GAIKU = 15     # O 街区（番地）名称


def build_minami_index(minami_table):
    """京阪南配送管理表から {normalize(町名): [(丁目集合, 担当地区コード), ...]} を作る。"""
    hidx = None
    for i, row in enumerate(minami_table):
        if row and any(str(c).strip() == _MASTER_HEADER_KEY for c in row if c is not None):
            hidx = i
            break
    if hidx is None:
        raise ValueError("京阪南 配送管理表のヘッダー行（担当地区）が見つかりません")

    def cell(row, col1):
        c = col1 - 1
        return row[c] if row and c < len(row) else None

    index = {}
    seen = set()   # (町名, 街区, 担当地区) の重複行(=同地区の複数チラシ行)を1つに
    for row in minami_table[hidx + 1:]:
        if row is None:
            continue
        chiku = cell(row, _COL_CHIKU)
        choukai = cell(row, _COL_CHOUKAI)
        if chiku is None or str(chiku).strip() == "" or choukai is None:
            continue
        code = str(chiku).strip()
        town = str(choukai).strip()
        gaiku = cell(row, _COL_GAIKU)
        dedup = (town, str(gaiku), code)
        if dedup in seen:
            continue
        seen.add(dedup)
        index.setdefault(normalize_town(town), []).append(
            (parse_choume_from_gaiku(gaiku), code))
    return index


def match_area(town, choume, index):
    """町名＋丁目 に一致する京阪南の担当地区コード（複数可・重複除去・順序保持）を返す。

    町名は完全一致を優先し、無ければ「町」サフィックスの有無を吸収して照合する
    （依頼表「大日」＝京阪南「大日町」のような省略に対応）。
    """
    key = normalize_town(town)
    hits = index.get(key)
    if hits is None and not key.endswith("町"):
        hits = index.get(key + "町")            # 「大日」→「大日町」
    if hits is None and key.endswith("町"):
        hits = index.get(key[:-1])              # 逆方向も一応
    hits = hits or []
    codes = []
    for choume_set, code in hits:
        if choume is None or not choume_set or choume in choume_set:
            if code not in codes:
                codes.append(code)
    return codes


_IRAI_HEADER_KEY = "町丁目名"
_IRAI_COLS = {
    "geocode": 1, "shiku": 2, "choume_name": 3, "setai": 4, "kyodo_setai": 5,
    "zantei": 6, "client1": 7, "client2": 8, "haifubi_memo": 9, "heihai": 10,
    "biko": 11, "toukin": 12, "haifubi": 13,
}


def parse_advalue_irai(table):
    """アドバリュー依頼表を行dictのリストに正規化する。"""
    hidx = None
    for i, row in enumerate(table):
        if row and any(str(c).strip() == _IRAI_HEADER_KEY for c in row if c is not None):
            hidx = i
            break
    if hidx is None:
        raise ValueError("依頼表のヘッダー行（町丁目名）が見つかりません")

    def cell(row, col1):
        c = col1 - 1
        return row[c] if row and c < len(row) else None

    def s(v):
        return "" if v is None else str(v).strip()

    rows = []
    for row in table[hidx + 1:]:
        if row is None:
            continue
        name = s(cell(row, _IRAI_COLS["choume_name"]))
        if name == "" or name in ("合計", "合 計"):
            break
        rows.append({k: cell(row, col1) for k, col1 in _IRAI_COLS.items()})
    return rows


_REPORT_HEADERS = [
    "町丁目名", "市区名", "担当地区(被り)", "被り", "世帯数15", "暫定部数",
    "クライアント①", "クライアント②", "配布日メモ", "併配部数", "店舗名", "投禁物件", "配布日",
]


def build_report_rows(irai_rows, minami_index):
    """依頼表＋京阪南突合の結果を、報告書の行(dictリスト)にする。"""
    out = []
    for r in irai_rows:
        name = "" if r["choume_name"] is None else str(r["choume_name"]).strip()
        town, choume = split_town_choume(name)
        codes = match_area(town, choume, minami_index)
        out.append({
            "町丁目名": name,
            "市区名": r["shiku"],
            "担当地区(被り)": "、".join(codes) if codes else "未マッチ",
            "被り": "被り" if codes else "非被り",
            "世帯数15": r["setai"],
            "暫定部数": r["zantei"],
            "クライアント①": r["client1"],
            "クライアント②": r["client2"],
            "配布日メモ": r["haifubi_memo"],
            "併配部数": r["heihai"],
            "店舗名": r["biko"],
            "投禁物件": r["toukin"],
            "配布日": r["haifubi"],
        })
    return out


def build_advalue_report_workbook(report_rows) -> bytes:
    """報告書Excel（1シート＝ヘッダー＋明細）を bytes で返す。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "アドバリュー報告書"
    ws.append(_REPORT_HEADERS)
    for r in report_rows:
        ws.append([r.get(h) for h in _REPORT_HEADERS])
    for col in range(1, len(_REPORT_HEADERS) + 1):
        ws.cell(row=1, column=col).font = openpyxl.styles.Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())


def overlap_summary(report_rows):
    """被り/非被りの件数サマリ。"""
    hit = sum(1 for r in report_rows if r["被り"] == "被り")
    return {"total": len(report_rows), "overlap": hit, "non_overlap": len(report_rows) - hit}


def read_irai(name, data):
    return parse_advalue_irai(read_uploaded(name, data))


def read_minami_index(name, data):
    return build_minami_index(read_uploaded(name, data))
