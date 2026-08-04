# 京阪集計表 実物レイアウト出力 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 京阪南北版の集計表を、大阪支社が使う実物帳票のレイアウト（エリア×リーダー×チラシ種類数のマトリクス＋各集計）でExcel出力する。数値は検証済み `shukei_data` をそのまま使う。

**Architecture:** `shukei_data`（実物と全項目一致・変更なし）を、まず純関数 `_shukei_layout` で「エリア→リーダー→チラシ種類数エントリ＋合計」の順序付き構造に整え、`build_shukei_daishi_workbook` が上部マトリクス（6エントリ/行で折り返し・エリア/リーダー縦結合・右端に配布部数計/地区数計）＋下部集計（チラシ種類数別・帳合/挿込/ぱどのみ/折チラシ空/チラシ総数・エリア別部数）を配置する。旧 `build_shukei_workbook` は撤去。

**Tech Stack:** Python 3, openpyxl, Streamlit, pytest。

## Global Constraints
- 数値は `shukei_data(groups, version)` の値をそのまま使う（`shukei_data` は変更しない・実物と一致済）。
- 上部マトリクス: エリア昇順（`int(area)`）→リーダー（部数降順・同値は名前昇順）→チラシ種類数昇順の (種類数, コース数, 部数)。
- 1リーダーの by_type は **6エントリ/行**で折り返し。ブロックk(0..5)の開始列 = `3 + k*5`（C,H,M,R,W,AB）、各ブロック4列＝〔種類数, "-", コース数, 部数〕。
- 右端 `AG`(列33)=配布部数計 `per[..]["busuu"]`、`AH`(列34)=地区数計 `per[..]["chiku"]`。リーダーが複数行なら AG/AH/リーダー名/エリア番号を縦結合。
- 折チラシ（B3,B4）は **"—"（手入力用）**。他の集計値は自動。
- チラシ種類数別は 11→0 降順で全種類（無い種類は 0/0）＋総計行。
- A4横（landscape, fitToWidth=1）。生成bytesは必ず `freeze_xlsx_bytes` を通す。`_md_from`・`_VERSION_LABEL` は既存を再利用。
- 既存の全テストは緑（回帰なし）。日本語データはターミナル出力に頼らずファイル＋Read で確認。

---

### Task 1: `_shukei_layout` 純関数（上部マトリクスの並び）

**Files:**
- Modify: `common/atehagi.py`（`shukei_data` の直後に追加）
- Test: `tests/test_atehagi_shukei.py`（新テストを追記。無ければ作成し先頭に `import io`／`import openpyxl`／`from common import atehagi as A`）

**Interfaces:**
- Consumes: `shukei_data` の返す `data["per"]`（{(area, leader): {"chiku","busuu","by_type":{t:[ku,bu]}}}）。
- Produces: `_shukei_layout(data) -> list[dict]`。各要素 `{"area": str, "leaders": [{"name": str, "chiku": int, "busuu": int, "types": [(種類数, コース数, 部数), ...]}]}`。area 昇順、leaders 部数降順、types 種類数昇順。

- [ ] **Step 1: Write the failing test**

`tests/test_atehagi_shukei.py` に追記:

```python
def _sample_shukei_data():
    return {
        "per": {
            ("1", "aim"): {"chiku": 3, "busuu": 300, "by_type": {2: [2, 200], 1: [1, 100]}},
            ("1", "fs"): {"chiku": 1, "busuu": 50, "by_type": {0: [1, 50]}},
            ("2", "x"): {"chiku": 2, "busuu": 150, "by_type": {3: [2, 150]}},
        },
        "area_busuu": {"1": 350, "2": 150},
        "area_chiku": {"1": 4, "2": 2},
        "type_dist": {0: [1, 50], 1: [1, 100], 2: [2, 200], 3: [2, 150]},
        "total_chiku": 6, "total_busuu": 500, "chirashi_sou": 9999,
        "pado_only_busuu": 50, "choai_busuu": 200, "sashikomi_busuu": 450,
    }


def test_shukei_layout_orders_area_leader_type():
    layout = A._shukei_layout(_sample_shukei_data())
    assert [b["area"] for b in layout] == ["1", "2"]           # エリア昇順
    a1 = layout[0]["leaders"]
    assert [l["name"] for l in a1] == ["aim", "fs"]            # 部数降順
    assert a1[0]["types"] == [(1, 1, 100), (2, 2, 200)]        # 種類数昇順
    assert a1[0]["busuu"] == 300 and a1[0]["chiku"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_atehagi_shukei.py::test_shukei_layout_orders_area_leader_type -v`
Expected: FAIL（`_shukei_layout` 未定義）

- [ ] **Step 3: Implement `_shukei_layout`**

`common/atehagi.py` の `shukei_data` の直後に追加:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_atehagi_shukei.py -v`
Expected: PASS（既存含め全て緑）

- [ ] **Step 5: Commit**

```bash
git add common/atehagi.py tests/test_atehagi_shukei.py
git commit -m "feat(shukei): 集計表マトリクスの並び _shukei_layout を追加"
```

---

### Task 2: `build_shukei_daishi_workbook` 実物レイアウト

**Files:**
- Modify: `common/atehagi.py`（`build_shukei_workbook` の直後に追加）
- Test: `tests/test_atehagi_shukei.py`（新テストを追記）

**Interfaces:**
- Consumes: `_shukei_layout(data)`、`data` の各集計、`_VERSION_LABEL`、`_md_from`、`freeze_xlsx_bytes`、openpyxl。
- Produces: `build_shukei_daishi_workbook(data, version, gou, haifubi) -> bytes`。

- [ ] **Step 1: Write the failing test**

`tests/test_atehagi_shukei.py` に追記:

```python
def test_build_shukei_daishi_layout():
    data = _sample_shukei_data()
    out = A.build_shukei_daishi_workbook(data, A.KEIHAN_KITA, gou=1248, haifubi="2026-06-26")
    wb = openpyxl.load_workbook(io.BytesIO(out))
    ws = wb.active
    # タイトル・ヘッダー
    assert ws["A1"].value == "京阪北版"
    assert ws["A3"].value == "エリア" and ws["B3"].value == "リーダー"
    assert ws["C3"].value == "チラシ種類" and ws["E3"].value == "コース数"
    assert ws["AG3"].value == "配布部数" and ws["AH3"].value == "地区数"
    # 上部マトリクス: area1 aim(row4) → 種類数1,2 が C,H ブロック
    assert ws["A4"].value == 1 and ws["B4"].value == "aim"
    assert ws["C4"].value == 1 and ws["D4"].value == "-" and ws["E4"].value == 1 and ws["F4"].value == 100
    assert ws["H4"].value == 2 and ws["K4"].value == 200
    assert ws["AG4"].value == 300 and ws["AH4"].value == 3
    # fs(row5), area2 x(row7・区切り空行あり)
    assert ws["B5"].value == "fs" and ws["C5"].value == 0 and ws["F5"].value == 50
    assert ws["A7"].value == 2 and ws["B7"].value == "x" and ws["C7"].value == 3 and ws["F7"].value == 150
    # 下部: チラシ種類数別(11→0)＋総計。br = 上部末尾+2 = 10
    assert ws["B10"].value == 11 and ws["D10"].value == 0            # 種類数11=データ無し→0
    assert ws["B21"].value == 0 and ws["D21"].value == 1 and ws["F21"].value == 50   # 種類数0
    assert ws["B22"].value == 6 and ws["F22"].value == 500          # 総計
    # 集計指標(M列ラベル/Q列値)・折チラシ空
    assert ws["M10"].value == "帳合" and ws["Q10"].value == 200
    assert ws["M13"].value == "折チラシ（B3,B4）" and ws["Q13"].value == "—"
    assert ws["M14"].value == "チラシ総数" and ws["Q14"].value == 9999
    # エリア別部数
    assert ws["M18"].value == "エリア1" and ws["P18"].value == 350
    assert ws.page_setup.orientation == "landscape"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_atehagi_shukei.py::test_build_shukei_daishi_layout -v`
Expected: FAIL（`build_shukei_daishi_workbook` 未定義）

- [ ] **Step 3: Implement `build_shukei_daishi_workbook`**

`common/atehagi.py` の `build_shukei_workbook` の直後に追加:

```python
def build_shukei_daishi_workbook(data, version, gou, haifubi) -> bytes:
    """集計表を実物帳票レイアウトで出力。上部=エリア×リーダー×チラシ種類数
    マトリクス(6/行折返し・縦結合・右端に配布部数計/地区数計)、下部=チラシ種類数別・
    集計指標(折チラシは手入力"—")・エリア別部数。"""
    from openpyxl.styles import Alignment, Font, Border, Side
    from openpyxl.worksheet.properties import PageSetupProperties
    from openpyxl.utils import get_column_letter as gl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "集計表"
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    bold = Font(bold=True)

    label = _VERSION_LABEL.get(version, "京阪")
    md = _md_from(haifubi)
    ws.cell(1, 1, label).font = Font(bold=True, size=14)
    ws.merge_cells("A1:E1")
    g = ws.cell(1, 7, f"{md} 号" if md else "号")
    g.font = bold
    ws.merge_cells(start_row=1, start_column=7, end_row=1, end_column=31)

    for c, txt in [(1, "エリア"), (2, "リーダー"), (3, "チラシ種類"),
                   (5, "コース数"), (33, "配布部数"), (34, "地区数")]:
        cell = ws.cell(3, c, txt)
        cell.font = bold
        cell.alignment = center
        cell.border = box

    PER_ROW = 6
    r = 4
    for area_block in _shukei_layout(data):
        area_top = r
        for leader in area_block["leaders"]:
            ltop = r
            for i, (t, ku, bu) in enumerate(leader["types"]):
                if i and i % PER_ROW == 0:
                    r += 1
                col = 3 + (i % PER_ROW) * 5
                for cc, val in [(col, t), (col + 1, "-"), (col + 2, ku), (col + 3, bu)]:
                    cell = ws.cell(r, cc, val)
                    cell.alignment = center
                    cell.border = box
            lbot = r
            bcell = ws.cell(ltop, 2, leader["name"])
            bcell.alignment = center
            bcell.border = box
            ag = ws.cell(ltop, 33, leader["busuu"]); ag.alignment = center; ag.border = box
            ah = ws.cell(ltop, 34, leader["chiku"]); ah.alignment = center; ah.border = box
            if lbot > ltop:
                ws.merge_cells(start_row=ltop, start_column=2, end_row=lbot, end_column=2)
                ws.merge_cells(start_row=ltop, start_column=33, end_row=lbot, end_column=33)
                ws.merge_cells(start_row=ltop, start_column=34, end_row=lbot, end_column=34)
            r += 1
        area_bot = r - 1
        acell = ws.cell(area_top, 1, int(area_block["area"]))
        acell.alignment = center
        acell.border = box
        if area_bot > area_top:
            ws.merge_cells(start_row=area_top, start_column=1, end_row=area_bot, end_column=1)
        r += 1  # エリア区切りの空行

    # ---- 下部集計 ----
    br = r + 1
    td = data["type_dist"]
    rr = br
    for t in range(11, -1, -1):
        ku, bu = td.get(t, [0, 0])
        for cc, val in [(2, t), (3, "-"), (4, ku), (6, bu)]:
            ws.cell(rr, cc, val).alignment = center
        rr += 1
    ws.cell(rr, 2, data["total_chiku"]).font = bold
    ws.cell(rr, 6, data["total_busuu"]).font = bold
    total_row = rr

    indicators = [
        ("帳合", data["choai_busuu"]),
        ("挿み込み", data["sashikomi_busuu"]),
        ("ぱどのみ", data["pado_only_busuu"]),
        ("折チラシ（B3,B4）", "—"),
        ("チラシ総数", data["chirashi_sou"]),
    ]
    for k, (lab, val) in enumerate(indicators):
        ws.cell(br + k, 13, lab).font = bold
        ws.cell(br + k, 17, val)

    for k, area in enumerate(sorted(data["area_busuu"], key=lambda a: int(a))):
        ws.cell(br + 8 + k, 13, f"エリア{area}").font = bold
        ws.cell(br + 8 + k, 15, "部")
        ws.cell(br + 8 + k, 16, data["area_busuu"][area])

    base_w = [3.6, 2.6, 4.7, 9.2, 3.7]
    for col in range(3, 33):
        ws.column_dimensions[gl(col)].width = base_w[(col - 3) % 5]
    ws.column_dimensions["A"].width = 6.2
    ws.column_dimensions["B"].width = 10.7
    ws.column_dimensions["AG"].width = 10.6
    ws.column_dimensions["AH"].width = 8.6

    last_row = max(total_row, br + 12)
    ws.print_area = f"A1:AH{last_row}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_atehagi_shukei.py -v`
Expected: PASS（全て緑）

- [ ] **Step 5: Commit**

```bash
git add common/atehagi.py tests/test_atehagi_shukei.py
git commit -m "feat(shukei): 集計表を実物レイアウトで出力する build_shukei_daishi_workbook を追加"
```

---

### Task 3: UI差し替え＋旧 build_shukei_workbook 撤去

**Files:**
- Modify: `pages/07_資料作成・変換表.py`（集計表ボタン 87-93行付近）
- Modify: `common/atehagi.py`（旧 `build_shukei_workbook` を削除）
- Modify: 旧 `build_shukei_workbook` を参照するテストがあれば更新（`tests/test_atehagi_shukei.py` 等。grep で確認）

**Interfaces:**
- Consumes: `shukei_data`, `build_shukei_daishi_workbook`, `shukei_filename`。

- [ ] **Step 1: Update the UI button**

`pages/07_資料作成・変換表.py` の集計表ボタンの出力を新関数に差し替え。`data`(=`shukei_data(...)`)・`rows`・`version` は同スコープにある。号・配布日は rows から取得。出力は既存どおり `st.session_state["keihan_out"] = (label, data_bytes, fname)`:

```python
            if c3.button("集計表を生成", key="keihan_shukei"):
                sdata = A.shukei_data(groups, version)
                gou = next((r["gou"] for r in rows if r.get("gou")), None)
                haifubi = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
                st.session_state["keihan_out"] = (
                    f"集計表（総地区数 {sdata['total_chiku']} / "
                    f"総配布部数 {sdata['total_busuu']:,} / チラシ総数 {sdata['chirashi_sou']:,}）",
                    A.build_shukei_daishi_workbook(sdata, version, gou, haifubi),
                    A.shukei_filename(version, rows))
```

- [ ] **Step 2: Remove old function**

`common/atehagi.py` から `def build_shukei_workbook(data, version, title=...):` 全体を削除（`shukei_data`・`build_shukei_daishi_workbook`・`shukei_filename` は残す）。

- [ ] **Step 3: Update/remove old tests referencing it**

`grep -rn "build_shukei_workbook" tests/ common/ pages/` で参照を洗い出す。`tests/test_atehagi_shukei.py` に旧 `build_shukei_workbook` を呼ぶテストがあれば、新 `build_shukei_daishi_workbook` ベースに置換するか削除（新レイアウトを検証する Task2 のテストがあるため、旧出力形式のセル位置テストは削除でよい）。撤去後、コードに旧名の参照が残っていないこと（docs markdown は可）。

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS（全て緑・pristine・`build_shukei_workbook` への参照ゼロ）

- [ ] **Step 5: Commit**

```bash
git add common/atehagi.py tests/test_atehagi_shukei.py "pages/07_資料作成・変換表.py"
git commit -m "feat(shukei): 集計表UIを実物レイアウトに差し替え旧出力を撤去"
```

---

### Task 4: 実データ突合＋実機E2E＋オーナー目視（検証・非コミット）

**Files:**
- 一時スクリプト（scratchpad・コミットしない）。実データ xlsm はリポジトリに置かない。

- [ ] **Step 1: 実データ突合（スクリプト）**

scratchpad のスクリプトで 実データ京阪北 `Downloads/京阪北版CSV リーダー名あり.xlsm` を `read_uploaded`→`rows_from_table`→`group_by_chiku`→`shukei_data`→`build_shukei_daishi_workbook` で生成し、UTF-8 ファイルに結果を書いて Read で確認:
- 生成物の主要セルが実物一致値と合う: 総計353/148,232（総計行）、帳合127,051(Q)、挿込138,625、ぱどのみ9,607、チラシ総数552,815、エリア別部数(エリア1=21,067 … 5=31,156)、上部マトリクス代表 aim=配布部数13,743/地区数37。
- 折チラシセルが "—"。
- 生成物を `OneDrive/Desktop/京阪北版_集計表_サンプル_20260724.xlsx` に保存（オーナー目視用）。

Expected: 主要セルが実物一致値と一致（折チラシ除く）。

- [ ] **Step 2: 実機E2E（別ポート・Playwright）**

8502は触らず別ポート(例8503)で `feature/jisseki-daishi` を起動。Playwright で「資料作成・変換表」→実xlsmアップロード→「集計表を生成」→DL。DL物を openpyxl で開き主要セルを検証。

Expected: UIから集計表が生成・DLできる。

- [ ] **Step 3: オーナー目視で1枚確認**

生成サンプルをオーナーに見てもらい、エリア/リーダーの並び・区切り空行・版名注記・折チラシ手入力欄・列幅の収まりを確認。指摘があれば軽微調整（並び順・空行・列幅・注記）。

Expected: オーナーOK。NGなら軽微修正して再確認。

- [ ] **Step 4: 完了処理**

`superpowers:verification-before-completion` で全テスト緑を再確認 → 実績表とあわせて `superpowers:finishing-a-development-branch` でマージ/デプロイ方針をオーナーに提示（公開デモ `feature/demo-share` へ反映するか）。記録を `.company/distribution/pm/projects/` と `secretary/notes` に残す。

---

## Self-Review
- **Spec coverage**: §4.1タイトル=Task2、§4.2上部マトリクス=Task1+Task2、§4.3種類数別=Task2、§4.4指標(折チラシ空)=Task2、§4.5エリア別=Task2、§5 UI=Task3、§6検証=Task4。数値変更なし(§3・§7)。
- **Placeholder scan**: コードは全て実体。Task3 Step3 は grep で参照確認する具体指示。
- **Type consistency**: `_shukei_layout` の返す dict キー（area/leaders, leader の name/chiku/busuu/types, types は (種類数,コース数,部数) タプル）を Task2 実装・テストで一貫使用。`build_shukei_daishi_workbook(data, version, gou, haifubi)` を Task2/3 で一致。ブロック開始列 `3 + k*5`、AG=33/AH=34、下部 br=上部末尾+2 をテストと実装で一致。
