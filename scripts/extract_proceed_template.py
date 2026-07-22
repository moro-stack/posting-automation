"""リビング新聞あて紙(大橋さん提供)の1枚を、データ・数式を消したテンプレとして切り出す。
実在の広告主名・ブロック番号を残さず、かつ値書き込み方式で使えるよう数式を全消しする。
入力元はメール添付をscratchpadに落としたもの。"""
import os
import openpyxl
from openpyxl.cell.cell import MergedCell

SRC = r"C:\Users\moro\AppData\Local\Temp\claude\C--Users-moro\6150758e-4f52-4031-ab91-3cb1a446eda8\scratchpad\リビング新聞豊中あて紙.xlsx"
OUT = os.path.join(os.path.dirname(__file__), "..", "templates", "あて紙テンプレート_リビング.xlsx")

wb = openpyxl.load_workbook(SRC)   # 体裁を保つため data_only にはしない
ws = wb["豊中-2-1"]                 # 生成済みシート(値/数式入り)をベースに体裁を流用

# 豊中-2-1 以外(FMT/チラシ/原紙=実データ含む)を削除
for name in list(wb.sheetnames):
    if name != "豊中-2-1":
        del wb[name]
ws.title = "あて紙テンプレート"

# 全セルを走査し、数式(=で始まる)・可変データを消す。固定の文字ラベルとA列連番だけ残す。
KEEP = {"B1", "B3", "C4"}          # リビング新聞 / KPS / 担当地区： の固定ラベル
for r in range(1, 51):
    for c in range(1, 10):         # A..I
        cell = ws.cell(row=r, column=c)
        if isinstance(cell, MergedCell):
            continue               # 結合の従セルは書けない(左上のみ保持)
        coord = cell.coordinate
        if coord in KEEP:
            continue
        if c == 1 and 7 <= r <= 40:
            continue               # A7..A40 の連番(1..34)は残す
        v = cell.value
        if isinstance(v, str) and v.startswith("="):
            cell.value = None      # 数式は全消し(値書き込み方式にする)
        elif coord in ("F3", "E4", "G2", "I6") or (3 <= c <= 9 and 6 <= r <= 40):
            cell.value = None      # 可変データ(エリア/部数/広告主明細)を消す

wb.save(os.path.abspath(OUT))
print("WROTE", os.path.abspath(OUT))
