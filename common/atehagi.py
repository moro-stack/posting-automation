"""資料作成・変換表 Phase 1: 京阪あて紙の変換エンジン（純関数＋Excel生成）。

現行 VBA `Module2`（担当地区別_あてがみテンプレ反映）の再現。
DB非依存・Streamlit非依存の純関数として実装し、TDDで検証する。
"""
import re

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
