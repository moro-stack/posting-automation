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
