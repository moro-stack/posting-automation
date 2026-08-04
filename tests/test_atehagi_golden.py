"""ゴールデン突合: 現行マクロ(Module2)が生成したあて紙と、アプリ生成のあて紙を突合する。

ローカルに実 .xlsm があるときだけ実行し、CIでは自動 skip。

【重要な前提・2026-07-22 の調査で判明】
見本の .xlsm は「配送管理表を貼り替えてあて紙を生成 → その後に配送管理表の部数を手編集」
した作業ファイルで、**配送管理表とその中のあて紙が部数で少しズレている**（元データを
編集してもあて紙は再生成されていない箇所がある）。そのため:
  - 地区名(A1)/ぱどんな(A3)/担当地区(D4)/配送物(B)/チラシサイズ(I)/チラシ数(I18) は
    全地区で完全一致するはず（変換ロジックの正しさ＝ここは 0 不一致を必須にする）。
  - 部数(G2, J列) は見本ファイルのドリフト分だけ食い違う。全353地区で判別した結果、
    G2規則は Module2 の「先頭レコード(ぱど基準行)の部数」が最多数で、残りは元データの
    後編集。→ 部数の不一致は「地区数に対してごく少数(数十セル)」に収まることだけ担保し、
    大量にズレたら実装バグとして落とす。触っていない受領時CSVなら完全一致する。
"""
import io
import os

import openpyxl
import pytest

from common import atehagi as A

XLSM = r"C:\Users\moro\Downloads\@マクロ（京阪北版）あて紙　マスタ (1).xlsm"
pytestmark = pytest.mark.skipif(not os.path.exists(XLSM), reason="実 .xlsm がローカルに無い")

_HEAD_CELLS = ["A1", "A3", "D4", "G2"]
_BUSUU_CELLS = {"G2"} | {f"J{r}" for r in range(5, 18)}   # 部数はドリフトし得る
_MAX_BUSUU_DRIFT = 80   # 見本ファイルの部数ドリフト許容上限（実測33。ここを超えたら実装バグ）

# 2026-07-23 関西ぱど指摘により、担当地区(D4)は「6桁ゼロ埋め文字列」で印字する仕様に変更した
# （マクロは 10101 という数値、アプリは "010101" という文字列）。
# リテラル比較からは外すが、代わりに「マクロの値を6桁ゼロ埋めしたものと完全一致」を別途必須にする
# ＝ 緩めるのではなく、意図した変換であることを厳密に検証する。
_CHIKU_CELL = "D4"


def _cells(ws):
    d = {c: ws[c].value for c in _HEAD_CELLS}
    for r in range(5, 18):     # row5〜17（明細）
        for col in ("B", "I", "J"):
            d[f"{col}{r}"] = ws[f"{col}{r}"].value
    d["I18"] = ws["I18"].value
    return d


def _norm(v):
    return None if (v is None or str(v).strip() == "") else v


def test_generated_matches_macro_sheets():
    with open(XLSM, "rb") as f:
        data = f.read()
    table = A.read_uploaded(os.path.basename(XLSM), data)
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    out = A.build_atehagi_workbook(groups, A.KEIHAN_KITA)
    gen = openpyxl.load_workbook(io.BytesIO(out))

    macro = openpyxl.load_workbook(XLSM, data_only=True)
    golden_names = [n for n in macro.sheetnames
                    if n not in ("京阪北_その他配送管理表", "あてがみ")]

    # 1) 生成した地区シートの集合が正解と一致すること
    assert set(gen.sheetnames) == set(golden_names), "生成した地区シートの集合が一致しない"

    # 2) セル単位で突合し、部数(ドリフトし得る)とそれ以外に分けて評価
    nonbusuu_mismatch = []
    busuu_mismatch = []
    chiku_mismatch = []
    for name in golden_names:
        gc, mc = _cells(gen[name]), _cells(macro[name])
        for k in mc:
            if k == _CHIKU_CELL:
                # 担当地区は「マクロの値を6桁ゼロ埋めしたもの」と完全一致すること。
                # ⚠️ 期待値の組み立てに実装(A.area_code6)を使うと自己参照になり、
                #    ゼロ埋めが壊れても両辺が同じように壊れて検出できない。
                #    ここでは実装を経由せずテスト内で期待値を作る。
                expected = str(mc.get(k)).strip().zfill(6)
                if str(gc.get(k)) != expected:
                    chiku_mismatch.append((name, k, gc.get(k), expected))
                continue
            if _norm(gc.get(k)) != _norm(mc.get(k)):
                (busuu_mismatch if k in _BUSUU_CELLS else nonbusuu_mismatch).append(
                    (name, k, gc.get(k), mc.get(k)))

    # 2-b) 担当地区は 1件の例外もなく「6桁ゼロ埋め」であること
    assert not chiku_mismatch, (
        f"担当地区(D4)が6桁ゼロ埋めになっていない {len(chiku_mismatch)}件: "
        f"先頭 {chiku_mismatch[:10]}")

    # 3) 部数以外(変換ロジック)は完全一致が必須
    assert not nonbusuu_mismatch, (
        f"部数以外で不一致 {len(nonbusuu_mismatch)}件（変換ロジックのバグ）: "
        f"先頭 {nonbusuu_mismatch[:10]}")

    # 4) 部数の不一致は見本ファイルのドリフト分のみ＝少数に収まること
    assert len(busuu_mismatch) <= _MAX_BUSUU_DRIFT, (
        f"部数の不一致が想定超({len(busuu_mismatch)} > {_MAX_BUSUU_DRIFT})＝実装バグの疑い: "
        f"先頭 {busuu_mismatch[:10]}")
