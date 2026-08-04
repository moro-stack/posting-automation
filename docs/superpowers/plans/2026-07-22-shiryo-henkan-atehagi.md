# 資料作成・変換表（Phase 1: 京阪北/南 あて紙）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 関西ぱどの配送管理表CSVをアップロードすると、担当地区コードごとに1枚ずつのあて紙を並べたExcelブックを生成・ダウンロードできる新ページを追加する（現行VBAマクロと完全一致）。

**Architecture:** 変換ロジックはDB非依存・Streamlit非依存の純関数モジュール `common/atehagi.py` に集約（TDD）。Excel出力はデータレス化した `templates/あて紙テンプレート_京阪.xlsx` を1地区ごとにコピーして値を流し込み、既存 `freeze_xlsx_bytes` でDLを安定化。UIは新ページ `pages/07_資料作成・変換表.py`。

**Tech Stack:** Python 3, Streamlit, openpyxl, pandas 不使用（標準csv）, pytest。

## Global Constraints

- 生成xlsxは必ず `common.excel_io.freeze_xlsx_bytes(data: bytes) -> bytes` を通す（未通過はStreamlit `/media/<hash>.xlsx` が404）。
- openpyxlのセル書き込みは `ws["A1"] = v` / `ws.cell(row=r, column=c).value = v`（属性代入）で行う。`ws.cell(r, c, value=...)` の位置引数版は使わない。
- 結合セルは左上セルにのみ書き込む（A3:E3→A3, D4:G4→D4, G2:I2→G2）。
- CSV読取は cp932 優先・utf-8-sig / utf-8 フォールバック。CSV出力があれば utf-8-sig（BOM）。
- 日本語の確認はターミナル直出力せずファイル(utf-8)へ書いて読む（cp932文字化け回避）。
- 公開GitHubリポジトリに実配送データ（実在の配送物名・担当者名・地区コード）をコミットしない。テンプレは抽出時にデータセルを消す。ゴールデン突合テストはローカルの実`.xlsm`があるときだけ実行しCIではskip。
- 京阪北版の地区名ルール（現行マクロ Module2）: 担当地区コード先頭1桁が `1/2/3 → 枚方・交野`、`4/5 → 寝屋川・枚方`。
- あて紙レイアウト（1地区=1シート・印刷範囲A1:J18・A4縦・1ページ・結合A3:E3/D4:G4/G2:I2）:
  - A1=地区名 / A3=ぱどんな(先頭行) / A4="担当地区　：　"(固定) / C4=0(固定) / D4=担当地区コード(int) / G2=先頭行の配布部数 / J2=" 部"(固定) / B5..B17=配送物 / I5..I17=チラシサイズ / J5..J17=配布部数 / I18=チラシ数(サイズ非空件数)。明細は最大13行(row5〜17)、row18は集計行。

**実行前提:** 新規ブランチ `feature/shiryo-henkan` を現在のHEADから作成して作業する（`git switch -c feature/shiryo-henkan`）。既存の未マージ列(revisions-3〜6/demo-share)には触れない。

**入力サンプル(開発用・実データ・コミット禁止):** `C:\Users\moro\Downloads\@マクロ（京阪北版）あて紙　マスタ (1).xlsm`
- 1枚目シート `京阪北_その他配送管理表`（表題1行＋ヘッダー1行＋データ1738行, 17列）= 先方から来る配送管理表。
- 生成物の正解 = 同ブックのシート `10101`〜`57805`（353枚）。

---

### Task 1: 純関数 `area5` / `chiku_name`（地区コード正規化＋地区名ルール）

**Files:**
- Create: `common/atehagi.py`
- Test: `tests/test_atehagi.py`

**Interfaces:**
- Produces:
  - `KEIHAN_KITA = "北"` / `KEIHAN_MINAMI = "南"`
  - `area5(chiku) -> str`（数字のみ抽出し末尾5桁。5桁未満はそのまま）
  - `chiku_name(version: str, chiku) -> str`（北版=先頭桁ルール。南版は未設定で `NotImplementedError`）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_atehagi.py
import pytest
from common import atehagi as A


def test_area5_extracts_last5_digits():
    assert A.area5(10101) == "10101"
    assert A.area5("10101") == "10101"
    assert A.area5("X-44408") == "44408"      # 数字以外を除去
    assert A.area5("  46501 ") == "46501"


def test_chiku_name_kita_rule():
    assert A.chiku_name(A.KEIHAN_KITA, "10101") == "枚方・交野"   # 先頭1
    assert A.chiku_name(A.KEIHAN_KITA, "30101") == "枚方・交野"   # 先頭3
    assert A.chiku_name(A.KEIHAN_KITA, "44408") == "寝屋川・枚方"  # 先頭4
    assert A.chiku_name(A.KEIHAN_KITA, 46501) == "寝屋川・枚方"    # 先頭5扱いでなく4


def test_chiku_name_minami_not_configured():
    with pytest.raises(NotImplementedError):
        A.chiku_name(A.KEIHAN_MINAMI, "10101")
```

- [ ] **Step 2: 失敗を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py -q`
Expected: FAIL（`ModuleNotFoundError: common.atehagi` or `AttributeError`）

- [ ] **Step 3: 最小実装**

```python
# common/atehagi.py
import re

KEIHAN_KITA = "北"
KEIHAN_MINAMI = "南"


def area5(chiku) -> str:
    digits = re.sub(r"\D", "", str(chiku))
    return digits[-5:] if len(digits) >= 5 else digits


def chiku_name(version: str, chiku) -> str:
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
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py -q`
Expected: PASS（3 tests）

- [ ] **Step 5: コミット**

```bash
git add common/atehagi.py tests/test_atehagi.py
git commit -m "feat(atehagi): 地区コード正規化と京阪北版の地区名ルール"
```

---

### Task 2: 純関数 `rows_from_table`（配送管理表 → 正規化行）

**Files:**
- Modify: `common/atehagi.py`
- Test: `tests/test_atehagi.py`

**Interfaces:**
- Consumes: なし（table = list[list] を受ける純関数）
- Produces:
  - `rows_from_table(table) -> list[dict]`。各dictキー: `padonna, chiku, haisoubutsu, busuu(int|None), size, gou, haifubi`。ヘッダー行（"担当地区"を含む行）を自動検出し、以降のデータ行のうち担当地区が空でない行を返す。

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_atehagi.py に追記
def _sample_table():
    # 実データを模した最小の合成テーブル（表題行＋ヘッダー行＋データ4行）
    header = ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所",
              "電話番号", "担当地区", "チラシコード", "配送物", "配布部数", "配送備考",
              "町界名", "街区（番地）名称", "受注種別", "チラシサイズ"]
    return [
        ["配送管理表", "2026-06-26", "(1248号)", "作成日:2026/06/18"],
        header,
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, None,
         "01 ぱど", 224, " ", "大住ヶ丘", "1丁目", None, None],
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, 28,
         "京都生協", 224, " ", "大住ヶ丘", "1丁目", "全戸配布(チラシ)", "Ｂ４(折済)"],
        ["2026-06-26", 1248, 0, None, None, "テスト花子", None, None, 46501, None,
         "04 ぱど", 436, " ", "香里園", "1丁目", None, None],
        [None] * 17,  # 空行は無視される
    ]


def test_rows_from_table_normalizes():
    rows = A.rows_from_table(_sample_table())
    assert len(rows) == 3
    assert rows[0] == {
        "padonna": "テスト太郎", "chiku": 10101, "haisoubutsu": "01 ぱど",
        "busuu": 224, "size": "", "gou": 1248, "haifubi": "2026-06-26",
    }
    assert rows[1]["size"] == "Ｂ４(折済)"
    assert rows[1]["busuu"] == 224
    assert rows[2]["chiku"] == 46501


def test_rows_from_table_no_header_raises():
    with pytest.raises(ValueError):
        A.rows_from_table([["a", "b"], ["c", "d"]])
```

- [ ] **Step 2: 失敗を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py::test_rows_from_table_normalizes -q`
Expected: FAIL（`AttributeError: rows_from_table`）

- [ ] **Step 3: 最小実装**

```python
# common/atehagi.py に追記
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
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py -q`
Expected: PASS（5 tests）

- [ ] **Step 5: コミット**

```bash
git add common/atehagi.py tests/test_atehagi.py
git commit -m "feat(atehagi): 配送管理表テーブルを正規化行に変換"
```

---

### Task 3: 純関数 `group_by_chiku` / `chirashi_count`

**Files:**
- Modify: `common/atehagi.py`
- Test: `tests/test_atehagi.py`

**Interfaces:**
- Consumes: `rows_from_table` の出力（list[dict]）
- Produces:
  - `group_by_chiku(rows) -> "collections.OrderedDict[str, list[dict]]"`（キー=area5(chiku), 出現順保持）
  - `chirashi_count(group_rows) -> int`（size 非空の件数）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_atehagi.py に追記
def test_group_by_chiku_preserves_order_and_counts():
    rows = A.rows_from_table(_sample_table())
    groups = A.group_by_chiku(rows)
    assert list(groups.keys()) == ["10101", "46501"]     # 出現順
    assert len(groups["10101"]) == 2
    assert A.chirashi_count(groups["10101"]) == 1        # 京都生協のみサイズ有り
    assert A.chirashi_count(groups["46501"]) == 0        # 04 ぱど のみ・サイズ無し
```

- [ ] **Step 2: 失敗を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py::test_group_by_chiku_preserves_order_and_counts -q`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 最小実装**

```python
# common/atehagi.py に追記
from collections import OrderedDict


def group_by_chiku(rows):
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(area5(r["chiku"]), []).append(r)
    return groups


def chirashi_count(group_rows) -> int:
    return sum(1 for r in group_rows if _s(r.get("size")) != "")
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py -q`
Expected: PASS（6 tests）

- [ ] **Step 5: コミット**

```bash
git add common/atehagi.py tests/test_atehagi.py
git commit -m "feat(atehagi): 担当地区コードでのグループ化とチラシ数集計"
```

---

### Task 4: テンプレート抽出（データレス化）

**Files:**
- Create: `templates/あて紙テンプレート_京阪.xlsx`（スクリプトで生成してコミット）
- Create: `scripts/extract_atehagi_template.py`（再現用・任意でコミット）
- Test: `tests/test_atehagi_template.py`

**Interfaces:**
- Produces: 単一シートのあて紙テンプレ（固定文字A4/C4/J2＋結合A3:E3/D4:G4/G2:I2＋印刷設定を保持、可変セルは空）。

- [ ] **Step 1: 抽出スクリプトを書く**

```python
# scripts/extract_atehagi_template.py
"""現行 .xlsm の あてがみ シートを、データを消したテンプレとして切り出す。
実データ(実在の配送物名・担当者名・地区コード)を残さないため可変セルをクリアする。"""
import os
import openpyxl

XLSM = r"C:\Users\moro\Downloads\@マクロ（京阪北版）あて紙　マスタ (1).xlsm"
OUT = os.path.join(os.path.dirname(__file__), "..", "templates", "あて紙テンプレート_京阪.xlsx")

wb = openpyxl.load_workbook(XLSM)  # 書式・結合・印刷設定を保持（read_only不可）
ws = wb["あてがみ"]

# 可変セルをクリア（固定文字 A4/C4/J2 は残す）
for coord in ["A1", "A3", "D4", "G2", "H18", "I18"]:
    ws[coord] = None
for r in range(5, 19):          # B5:J18 の明細領域
    for c in range(2, 11):
        ws.cell(row=r, column=c).value = None

# あてがみ 以外の 354 シートを削除
for name in list(wb.sheetnames):
    if name != "あてがみ":
        del wb[name]
ws.title = "あて紙テンプレート"

wb.save(os.path.abspath(OUT))
print("WROTE", os.path.abspath(OUT))
```

- [ ] **Step 2: 実行してテンプレを生成**

Run: `cd /c/Users/moro/posting-automation && python scripts/extract_atehagi_template.py`
Expected: `WROTE ...templates\あて紙テンプレート_京阪.xlsx`

- [ ] **Step 3: テンプレ検証テストを書く**

```python
# tests/test_atehagi_template.py
import os
import openpyxl

ROOT = os.path.dirname(os.path.dirname(__file__))
TMPL = os.path.join(ROOT, "templates", "あて紙テンプレート_京阪.xlsx")


def test_template_has_constants_merges_and_no_data():
    wb = openpyxl.load_workbook(TMPL)
    ws = wb[wb.sheetnames[0]]
    merged = {str(m) for m in ws.merged_cells.ranges}
    assert {"A3:E3", "D4:G4", "G2:I2"} <= merged
    assert str(ws["A4"].value).startswith("担当地区")   # 固定ラベル保持
    assert ws["C4"].value == 0
    assert str(ws["J2"].value).strip() == "部"
    # 可変セルは空（実データが残っていない）
    for coord in ["A1", "A3", "D4", "G2", "B5", "B6", "I6", "J5", "I18"]:
        assert ws[coord].value in (None, ""), f"{coord} にデータが残っている"
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi_template.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add scripts/extract_atehagi_template.py templates/あて紙テンプレート_京阪.xlsx tests/test_atehagi_template.py
git commit -m "feat(atehagi): あて紙テンプレをデータレス化して同梱"
```

---

### Task 5: `build_atehagi_workbook`（あて紙Excel生成）

**Files:**
- Modify: `common/atehagi.py`
- Test: `tests/test_atehagi_build.py`

**Interfaces:**
- Consumes: `group_by_chiku` の出力、`chiku_name`、`chirashi_count`、`common.excel_io.freeze_xlsx_bytes`
- Produces:
  - `TEMPLATE_PATH`（`templates/あて紙テンプレート_京阪.xlsx` の絶対パス）
  - `build_atehagi_workbook(groups, version, template_path=TEMPLATE_PATH) -> bytes`
  - `atehagi_filename(version, rows) -> str`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_atehagi_build.py
import io
import hashlib
import openpyxl
from common import atehagi as A


def _groups():
    from tests.test_atehagi import _sample_table
    return A.group_by_chiku(A.rows_from_table(_sample_table()))


def test_build_atehagi_cells_match_layout():
    data = A.build_atehagi_workbook(_groups(), A.KEIHAN_KITA)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["10101", "46501"]

    s = wb["10101"]
    assert s["A1"].value == "枚方・交野"
    assert s["A3"].value == "テスト太郎"
    assert s["D4"].value == 10101
    assert s["G2"].value == 224
    assert s["B5"].value == "01 ぱど"
    assert s["I5"].value in (None, "")          # 先頭行はサイズ無し
    assert s["J5"].value == 224
    assert s["B6"].value == "京都生協"
    assert s["I6"].value == "Ｂ４(折済)"
    assert s["J6"].value == 224
    assert s["I18"].value == 1                   # チラシ数
    # 固定ラベルは保持
    assert str(s["A4"].value).startswith("担当地区")
    assert s["C4"].value == 0
    # 結合セルは維持
    assert {"A3:E3", "D4:G4", "G2:I2"} <= {str(m) for m in s.merged_cells.ranges}

    s2 = wb["46501"]
    assert s2["A1"].value == "寝屋川・枚方"
    assert s2["I18"].value == 0


def test_build_atehagi_is_deterministic():
    g = _groups()
    a = A.build_atehagi_workbook(g, A.KEIHAN_KITA)
    b = A.build_atehagi_workbook(A.group_by_chiku(
        A.rows_from_table(__import__("tests.test_atehagi", fromlist=["_sample_table"])._sample_table())),
        A.KEIHAN_KITA)
    assert hashlib.md5(a).hexdigest() == hashlib.md5(b).hexdigest()


def test_atehagi_filename():
    rows = A.rows_from_table(__import__("tests.test_atehagi", fromlist=["_sample_table"])._sample_table())
    name = A.atehagi_filename(A.KEIHAN_KITA, rows)
    assert name.startswith("京阪北版_あて紙_1248号_")
    assert name.endswith(".xlsx")
```

- [ ] **Step 2: 失敗を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi_build.py -q`
Expected: FAIL（`AttributeError: build_atehagi_workbook`）

- [ ] **Step 3: 最小実装**

```python
# common/atehagi.py に追記
import io
import os
import openpyxl
from openpyxl.worksheet.properties import PageSetupProperties

from common.excel_io import freeze_xlsx_bytes

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
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi_build.py -q`
Expected: PASS（3 tests）。※ `copy_worksheet` が結合セルを落とす環境でも `_apply_merges` が補うため merged のassertは通る。落ちる場合は `_fill_atehagi` の `_apply_merges` を確認。

- [ ] **Step 5: 全テスト実行**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi.py tests/test_atehagi_build.py tests/test_atehagi_template.py -q`
Expected: 全PASS

- [ ] **Step 6: コミット**

```bash
git add common/atehagi.py tests/test_atehagi_build.py
git commit -m "feat(atehagi): あて紙Excelブック生成（テンプレ流し込み＋freeze）"
```

---

### Task 6: 入力ファイル読取 `read_uploaded`（CSV/xlsx）

**Files:**
- Modify: `common/atehagi.py`
- Test: `tests/test_atehagi_io.py`

**Interfaces:**
- Produces: `read_uploaded(name: str, data: bytes) -> list[list]`（先頭シート/CSVをテーブル化。cp932→utf-8-sig→utf-8）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_atehagi_io.py
import io
import openpyxl
from common import atehagi as A


def test_read_uploaded_csv_cp932():
    text = "配送管理表,,,\n担当地区,ぱどんな,配送物,配布部数,チラシサイズ\n10101,太郎,01 ぱど,224,\n"
    data = text.encode("cp932")
    table = A.read_uploaded("x.csv", data)
    rows = A.rows_from_table(table)
    assert rows[0]["chiku"] == "10101"
    assert rows[0]["padonna"] == "太郎"


def test_read_uploaded_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["配送管理表", None, None])
    ws.append(["担当地区", "ぱどんな", "配送物", "配布部数", "チラシサイズ"])
    ws.append([10101, "太郎", "01 ぱど", 224, None])
    buf = io.BytesIO(); wb.save(buf)
    table = A.read_uploaded("x.xlsx", buf.getvalue())
    rows = A.rows_from_table(table)
    assert rows[0]["chiku"] == 10101
```

- [ ] **Step 2: 失敗を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi_io.py -q`
Expected: FAIL（`AttributeError: read_uploaded`）

- [ ] **Step 3: 最小実装**

```python
# common/atehagi.py に追記
import csv as _csv


def read_uploaded(name: str, data: bytes):
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
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi_io.py -q`
Expected: PASS（2 tests）

- [ ] **Step 5: コミット**

```bash
git add common/atehagi.py tests/test_atehagi_io.py
git commit -m "feat(atehagi): CSV(cp932)/xlsx アップロードのテーブル読取"
```

---

### Task 7: ゴールデン突合テスト（現行マクロと完全一致・ローカルskip）

**Files:**
- Test: `tests/test_atehagi_golden.py`

**Interfaces:**
- Consumes: `read_uploaded`, `rows_from_table`, `group_by_chiku`, `build_atehagi_workbook`

- [ ] **Step 1: ゴールデン突合テストを書く**

```python
# tests/test_atehagi_golden.py
"""ローカルに実 .xlsm があるときだけ実行。CIでは自動skip。
同じ配送管理表からアプリが生成したあて紙を、マクロ生成の正解シートとセル単位で突合する。"""
import io
import os
import openpyxl
import pytest
from common import atehagi as A

XLSM = r"C:\Users\moro\Downloads\@マクロ（京阪北版）あて紙　マスタ (1).xlsm"
pytestmark = pytest.mark.skipif(not os.path.exists(XLSM), reason="実 .xlsm がローカルに無い")

# 突合するセル（明細は最大 B5:J17）
_HEAD_CELLS = ["A1", "A3", "D4", "G2"]


def _cells(ws):
    d = {c: ws[c].value for c in _HEAD_CELLS}
    for r in range(5, 18):     # row5〜17（明細）
        for col in ("B", "I", "J"):
            d[f"{col}{r}"] = ws[f"{col}{r}"].value
    d["I18"] = ws["I18"].value
    return d


def test_generated_matches_macro_sheets():
    with open(XLSM, "rb") as f:
        data = f.read()
    table = A.read_uploaded("@マクロ（京阪北版）あて紙　マスタ (1).xlsm", data)
    rows = A.rows_from_table(table)
    groups = A.group_by_chiku(rows)
    out = A.build_atehagi_workbook(groups, A.KEIHAN_KITA)
    gen = openpyxl.load_workbook(io.BytesIO(out))

    macro = openpyxl.load_workbook(XLSM, data_only=True)
    golden_names = [n for n in macro.sheetnames if n not in ("京阪北_その他配送管理表", "あてがみ")]

    assert set(gen.sheetnames) == set(golden_names), "生成した地区シートの集合が一致しない"

    mismatches = []
    for name in golden_names:
        gc, mc = _cells(gen[name]), _cells(macro[name])
        for k in mc:
            if (gc.get(k) or None) != (mc.get(k) or None):
                mismatches.append((name, k, gc.get(k), mc.get(k)))
    assert not mismatches, f"不一致 {len(mismatches)}件: 先頭 {mismatches[:10]}"
```

- [ ] **Step 2: ローカルで突合実行**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_atehagi_golden.py -q`
Expected: PASS（実 .xlsm がある開発機。ズレがあれば不一致セルが表示されるので `atehagi` を修正して再実行）

- [ ] **Step 3: コミット**

```bash
git add tests/test_atehagi_golden.py
git commit -m "test(atehagi): 現行マクロ生成あて紙とのゴールデン突合(ローカルskip)"
```

---

### Task 8: 新ページ `07_資料作成・変換表` とナビ登録

**Files:**
- Create: `pages/07_資料作成・変換表.py`
- Modify: `app.py`（`pages` リストに1行追加）
- Test: `tests/test_pages_smoke.py`（既存に追記）

**Interfaces:**
- Consumes: `common.atehagi`（`read_uploaded`/`rows_from_table`/`group_by_chiku`/`build_atehagi_workbook`/`atehagi_filename`/`KEIHAN_KITA`/`KEIHAN_MINAMI`）、`common.ui.apply_app_style`

- [ ] **Step 1: ページを作成**

```python
# pages/07_資料作成・変換表.py
import streamlit as st

from common.ui import apply_app_style
from common import atehagi as A

apply_app_style()
st.title("資料作成・変換表")

tab_atehagi, tab_other = st.tabs(["京阪 あて紙", "その他（準備中）"])

with tab_atehagi:
    st.caption("関西ぱどの配送管理表（CSV / Excel）をアップロードすると、"
               "担当地区ごとのあて紙をまとめたExcelを作成します。")
    version_label = st.radio("版", ["京阪北版", "京阪南版"], horizontal=True)
    version = A.KEIHAN_KITA if version_label == "京阪北版" else A.KEIHAN_MINAMI

    up = st.file_uploader("配送管理表をアップロード", type=["csv", "xlsx", "xlsm"])
    if up is not None:
        try:
            table = A.read_uploaded(up.name, up.getvalue())
            rows = A.rows_from_table(table)
            groups = A.group_by_chiku(rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"読み取りに失敗しました: {e}")
            st.stop()

        gou = next((r["gou"] for r in rows if r.get("gou")), "—")
        hb = next((r["haifubi"] for r in rows if r.get("haifubi")), "—")
        st.success(f"読み込みOK：号数 {gou} / 配布日 {hb} / "
                   f"データ {len(rows)}行 / 地区 {len(groups)}件")

        if version == A.KEIHAN_MINAMI:
            st.warning("京阪南版の地区名ルールが未設定です。管理者に地区名ルールの登録を依頼してください。")
        elif st.button("あて紙を生成", type="primary"):
            data = A.build_atehagi_workbook(groups, version)
            st.download_button(
                "あて紙をダウンロード",
                data=data,
                file_name=A.atehagi_filename(version, rows),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

with tab_other:
    st.info("リビングプロシード（配布依頼書→あて紙）、京阪の報告書・集計表・実績表、"
            "アドバリュー（依頼表→報告書＋エリア被り判定）は順次追加予定です。")
```

- [ ] **Step 2: `app.py` にページ登録**

`app.py` の `pages = [ ... ]` リスト末尾（`05_マスタ管理.py` の行の後）に追加:

```python
    st.Page("pages/07_資料作成・変換表.py", title="資料作成・変換表", icon=":material/transform:"),
```

- [ ] **Step 3: スモークテストを追記**

`tests/test_pages_smoke.py` のページ一覧に `"07_資料作成・変換表.py"` を追加（既存の parametrize / ループに沿って1要素追加。既存の一時DB fixture をそのまま使う）。例:

```python
PAGES = [
    "01_経費・買掛・売掛.py",
    "02_業務委託登録.py",
    "03_号別明細.py",
    "05_マスタ管理.py",
    "06_原価・売上まとめ.py",
    "07_資料作成・変換表.py",   # 追加
]
```

- [ ] **Step 4: スモークテスト実行**

Run: `cd /c/Users/moro/posting-automation && python -m pytest tests/test_pages_smoke.py -q`
Expected: PASS（新ページが例外なくレンダリング）

- [ ] **Step 5: 全テスト実行**

Run: `cd /c/Users/moro/posting-automation && python -m pytest -q`
Expected: 既存＋新規すべてPASS（ゴールデンはローカルなら実行/CIならskip）

- [ ] **Step 6: コミット**

```bash
git add pages/07_資料作成・変換表.py app.py tests/test_pages_smoke.py
git commit -m "feat(atehagi): 資料作成・変換表ページを追加(京阪あて紙)"
```

---

### Task 9: 実機確認（8502）

**Files:** なし（手動確認）

- [ ] **Step 1: 8502を再起動**（`common/*.py` 追加のためプロセス停止→再起動）

```bash
cd /c/Users/moro/posting-automation
# 既存8502プロセスを停止してから
python -m streamlit run app.py --server.port 8502 --server.headless true
```

- [ ] **Step 2:** ブラウザで「資料作成・変換表」→「京阪 あて紙」→ 京阪北版を選択 → 実 `.xlsm`（または関西ぱどCSV）をアップロード → 「あて紙を生成」→ ダウンロードしたExcelを開き、地区数・A1地区名・A3ぱどんな・明細・I18チラシ数が正しいこと、印刷プレビューがA4縦1枚に収まることを目視。
- [ ] **Step 3:** 問題なければオーナーへ完了報告（マージはオーナーの実機確認後 `git merge --no-ff feature/shiryo-henkan`）。

---

## Self-Review（計画）

- **Spec coverage**:
  - §3 入力仕様 → Task 2/6。§4 変換ロジック(area5/地区名/グループ化/チラシ数) → Task 1/3。§5 出力(テンプレ・セルマッピング・freeze・ファイル名) → Task 4/5。§6 UI → Task 8。§8 検証(ゴールデン・決定性・スモーク) → Task 5/7/8。§10 南版未設定 → Task 1(`NotImplementedError`)＋Task 8(警告表示)。§10 実CSVエンコーディング → Task 6(cp932フォールバック)。✓
  - 南版の地区名ルール確定は本計画外（ルール受領後に `chiku_name` の南分岐＋テストを1タスク追加）。UIは南で警告して安全にブロック。✓
- **Placeholder scan**: 各ステップに実コード/実コマンド/期待値あり。TBD無し。✓
- **Type consistency**: `area5`(str)→`chiku_name`/`group_by_chiku`が使用、`rows_from_table`のdictキー(`padonna/chiku/haisoubutsu/busuu/size/gou/haifubi`)を`_fill_atehagi`/`chirashi_count`/`atehagi_filename`が一貫使用、`build_atehagi_workbook(groups, version)`のシグネチャがUI/テストと一致。✓
- **既知リスク**: `copy_worksheet` の結合セル/印刷設定の欠落 → `_apply_merges`/`_set_print` で明示補完。大規模ブック(約350シート)の生成時間 → Task 9 で実測、問題あれば別途最適化（PDFや分割）。
