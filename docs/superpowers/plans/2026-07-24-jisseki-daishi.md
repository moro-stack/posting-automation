# 京阪実績表 台紙スタイル出力 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 京阪南北版の「挟み込み実績表」を、大阪支社が実際に使う手書き台紙の書き方（上にコース名・下に案件名/枚数/サイン）で、コース名・案件名・枚数まで印字した「サインするだけ」の状態でExcel出力する。

**Architecture:** 既存 `common/atehagi.py` のデータ抽出（`group_by_chiku`/`chiku_name`/`area_code6`/`pado_row`）を再利用し、(1) 1コース分の構造を返す純関数 `jisseki_courses` と (2) 台紙レイアウトのブックを bytes で返す `build_jisseki_daishi_workbook` を追加。旧・表形式の `jisseki_rows`/`build_jisseki_workbook` は撤去し、UI(`pages/07`)を新関数に差し替える。

**Tech Stack:** Python 3, openpyxl, Streamlit, pytest。

## Global Constraints
- コース＝担当地区（1あて紙＝1コース）。**挟み込みチラシ（`size` 非空）が1つ以上あるコースのみ**出力。ぱどのみ地区は除外。
- コース名＝`area_code6(chiku)`（6桁ゼロ埋め）＋半角スペース＋`chiku_name(version, chiku)`（例 `010101 枚方・交野`）。
- 各コースの中身＝`size` 非空の各行を `{"name": haisoubutsu, "count": busuu}` で、**元の並び順**に列挙。
- サイン欄は印字せず、`（サイン）` プレースホルダ行のみ（現場で手書き）。
- レイアウト＝**1行4コース**・A4横（`orientation="landscape"`, `fitToWidth=1`）。
- 北版・南版の両対応（`chiku_name` が版別に地区名を返す。南版は 2026-07-23 のあて紙修正で解禁済）。
- 生成 bytes は必ず既存 `freeze_xlsx_bytes(...)` を通す。
- 既存の全テストは緑のまま（回帰なし）。日本語データはターミナル出力に頼らずファイル＋Read で確認。

---

### Task 1: `jisseki_courses` 純関数（旧 `jisseki_rows` の後継）

**Files:**
- Modify: `common/atehagi.py`（`jisseki_rows` の直後に追加）
- Test: `tests/test_atehagi_jisseki.py`（新テストを追記）

**Interfaces:**
- Consumes: `group_by_chiku(rows) -> {chiku: [row,...]}`、`chiku_name(version, chiku) -> str`、`area_code6(chiku) -> str`、`_s(x) -> str`、行の各キー `haisoubutsu / busuu / size`。
- Produces: `jisseki_courses(groups, version) -> list[dict]`。各 dict は `{"code": str, "chiku_name": str, "course_name": str, "flyers": list[{"name": str, "count": int|None}]}`。

- [ ] **Step 1: Write the failing tests**

`tests/test_atehagi_jisseki.py` の末尾に追記:

```python
def test_jisseki_courses_basic():
    groups = A.group_by_chiku(A.rows_from_table(_sample_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    # 10101 は チラシ有り→載る。46501 は ぱどのみ→除外。
    assert len(courses) == 1
    c = courses[0]
    assert c["code"] == "010101"
    assert c["chiku_name"] == "枚方・交野"
    assert c["course_name"] == "010101 枚方・交野"
    assert c["flyers"] == [{"name": "サンプル生協", "count": 224}]


def _multi_flyer_table():
    header = ["配布日", "号数", "ルート", "異動", "配送順位", "ぱどんな", "住所",
              "電話番号", "担当地区", "チラシコード", "配送物", "配布部数", "配送備考",
              "町界名", "街区（番地）名称", "受注種別", "チラシサイズ"]
    return [
        ["配送管理表", "2026-06-26", "(1248号)", "作成日:2026/06/18"],
        header,
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, None,
         "01 ぱど", 400, " ", "大住ヶ丘", "1丁目", None, None],
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, 400,
         "SUUMO/注文住宅", 400, " ", "大住ヶ丘", "1丁目", "全戸配布(チラシ)", "Ｂ４"],
        ["2026-06-26", 1248, 0, None, None, "テスト太郎", None, None, 10101, 400,
         "ECC/宮野", 400, " ", "大住ヶ丘", "1丁目", "全戸配布(チラシ)", "Ｂ４"],
    ]


def test_jisseki_courses_multi_flyer_keeps_order():
    groups = A.group_by_chiku(A.rows_from_table(_multi_flyer_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    assert len(courses) == 1
    assert courses[0]["flyers"] == [
        {"name": "SUUMO/注文住宅", "count": 400},
        {"name": "ECC/宮野", "count": 400},
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_atehagi_jisseki.py::test_jisseki_courses_basic tests/test_atehagi_jisseki.py::test_jisseki_courses_multi_flyer_keeps_order -v`
Expected: FAIL with `AttributeError: module 'common.atehagi' has no attribute 'jisseki_courses'`

- [ ] **Step 3: Implement `jisseki_courses`**

`common/atehagi.py` の `jisseki_rows` 関数の直後に追加:

```python
def jisseki_courses(groups, version):
    """実績表台紙の1コース分データ。挟み込みチラシ(size非空)が1つ以上ある
    コースのみ。ぱどのみ地区は除外。flyers は元の並び順。"""
    out = []
    for chiku, rows in groups.items():
        flyers = [
            {"name": r["haisoubutsu"], "count": r["busuu"]}
            for r in rows if _s(r.get("size")) != ""
        ]
        if not flyers:
            continue
        name = chiku_name(version, chiku)
        code = area_code6(chiku)
        out.append({
            "code": code,
            "chiku_name": name,
            "course_name": f"{code} {name}",
            "flyers": flyers,
        })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_atehagi_jisseki.py -v`
Expected: PASS（既存テスト含め全て緑）

- [ ] **Step 5: Commit**

```bash
git add common/atehagi.py tests/test_atehagi_jisseki.py
git commit -m "feat(jisseki): 実績表台紙のコース抽出 jisseki_courses を追加"
```

---

### Task 2: `build_jisseki_daishi_workbook` 台紙レイアウト

**Files:**
- Modify: `common/atehagi.py`（`build_jisseki_workbook` の直後に追加。ヘルパ `_md_from` も追加）
- Test: `tests/test_atehagi_jisseki.py`（新テストを追記）

**Interfaces:**
- Consumes: `jisseki_courses(...) -> list[dict]`、`_VERSION_LABEL`、`freeze_xlsx_bytes(bytes) -> bytes`、openpyxl。
- Produces: `build_jisseki_daishi_workbook(courses, version, gou, haifubi, per_row=4) -> bytes`。1コース＝ヘッダー行(コース名・2列結合)＋本文行(案件名列に各名+「（サイン）」、枚数列に各枚数)。4コース/行で折り返し。`_md_from(haifubi) -> str`（"2026-06-26"→"6/26"）。

- [ ] **Step 1: Write the failing tests**

`tests/test_atehagi_jisseki.py` の末尾に追記:

```python
def test_md_from():
    assert A._md_from("2026-06-26") == "6/26"
    import datetime
    assert A._md_from(datetime.date(2026, 6, 26)) == "6/26"
    assert A._md_from("") == ""


def test_build_daishi_title_and_first_course():
    groups = A.group_by_chiku(A.rows_from_table(_sample_table()))
    courses = A.jisseki_courses(groups, A.KEIHAN_KITA)
    data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1248,
                                           haifubi="2026-06-26")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "6/26 ／ 1248号　京阪北版"
    assert ws["A2"].value == "010101 枚方・交野"          # ヘッダー(コース名)
    assert ws["A3"].value == "サンプル生協\n（サイン）"     # 本文(案件名+サイン)
    assert ws["B3"].value == "224"                        # 本文(枚数)
    assert ws.page_setup.orientation == "landscape"


def test_build_daishi_wrapping_4_per_row():
    # 5コース → 2行目(grp1)に5コース目が来る（行2-3がgrp0、行4-5がgrp1）
    courses = [
        {"code": f"01010{i}", "chiku_name": "枚方・交野",
         "course_name": f"01010{i} 枚方・交野",
         "flyers": [{"name": "A", "count": 100}]}
        for i in range(1, 6)
    ]
    data = A.build_jisseki_daishi_workbook(courses, A.KEIHAN_KITA, gou=1,
                                           haifubi="2026-06-26")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    # 4コース目は grp0 の col3 → 案件名列 = 1+3*2 = 7 (G列) の行2
    assert ws["G2"].value == "010104 枚方・交野"
    # 5コース目は grp1 の col0 → A列 の行4
    assert ws["A4"].value == "010105 枚方・交野"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_atehagi_jisseki.py::test_md_from tests/test_atehagi_jisseki.py::test_build_daishi_title_and_first_course tests/test_atehagi_jisseki.py::test_build_daishi_wrapping_4_per_row -v`
Expected: FAIL（`_md_from` / `build_jisseki_daishi_workbook` 未定義）

- [ ] **Step 3: Implement `_md_from` と `build_jisseki_daishi_workbook`**

`common/atehagi.py` の `build_jisseki_workbook` の直後に追加:

```python
def _md_from(haifubi) -> str:
    """配布日から "M/D"（例 6/26）。datetime/文字列どちらも可。"""
    import datetime
    if isinstance(haifubi, (datetime.date, datetime.datetime)):
        return f"{haifubi.month}/{haifubi.day}"
    s = str(haifubi or "")
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", s)
    if m:
        return f"{int(m.group(2))}/{int(m.group(3))}"
    return ""


def build_jisseki_daishi_workbook(courses, version, gou, haifubi, per_row=4) -> bytes:
    """実績表を実物台紙スタイルで出力。1コース=ヘッダー行(コース名)+本文行
    (案件名/枚数を1チラシ1行+サイン空)。per_row コース/行で折り返す。"""
    from openpyxl.styles import Alignment, Font, Border, Side
    from openpyxl.worksheet.properties import PageSetupProperties

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "実績表"
    ncol = per_row * 2

    label = _VERSION_LABEL.get(version, "京阪")
    md = _md_from(haifubi)
    gou_part = f"{gou}号" if gou else "号"
    title = f"{md} ／ {gou_part}　{label}"
    ws.cell(row=1, column=1, value=title)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    t = ws.cell(row=1, column=1)
    t.font = Font(bold=True, size=16)
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    thin = Side(style="thin")
    thick = Side(style="medium")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    topleft = Alignment(horizontal="left", vertical="top", wrap_text=True)
    topright = Alignment(horizontal="right", vertical="top", wrap_text=True)

    for i, c in enumerate(courses):
        grp, col = divmod(i, per_row)
        rh = 2 + grp * 2
        rb = rh + 1
        c0 = 1 + col * 2
        c1 = c0 + 1
        ws.merge_cells(start_row=rh, start_column=c0, end_row=rh, end_column=c1)
        h = ws.cell(row=rh, column=c0, value=c["course_name"])
        h.font = Font(bold=True, size=11)
        h.alignment = center
        names = "\n".join([f["name"] for f in c["flyers"]] + ["（サイン）"])
        counts = "\n".join([str(f["count"]) for f in c["flyers"]])
        bn = ws.cell(row=rb, column=c0, value=names)
        bn.alignment = topleft
        bc = ws.cell(row=rb, column=c1, value=counts)
        bc.alignment = topright
        for (r, cc) in [(rh, c0), (rh, c1), (rb, c0), (rb, c1)]:
            ws.cell(row=r, column=cc).border = Border(
                left=thick if cc == c0 else thin,
                right=thick if cc == c1 else thin,
                top=thick if r == rh else thin,
                bottom=thick if r == rb else thin,
            )

    ngrp = (len(courses) + per_row - 1) // per_row
    for grp in range(ngrp):
        block = courses[grp * per_row:(grp + 1) * per_row]
        max_lines = max((len(c["flyers"]) + 1) for c in block)
        ws.row_dimensions[2 + grp * 2].height = 20
        ws.row_dimensions[3 + grp * 2].height = max(40, max_lines * 18)
    for col in range(per_row):
        ws.column_dimensions[openpyxl.utils.get_column_letter(1 + col * 2)].width = 24
        ws.column_dimensions[openpyxl.utils.get_column_letter(2 + col * 2)].width = 6

    last_row = 1 + ngrp * 2 if ngrp else 1
    last_col = openpyxl.utils.get_column_letter(ncol)
    ws.print_area = f"A1:{last_col}{last_row}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    buf = io.BytesIO()
    wb.save(buf)
    return freeze_xlsx_bytes(buf.getvalue())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_atehagi_jisseki.py -v`
Expected: PASS（全て緑）

- [ ] **Step 5: Commit**

```bash
git add common/atehagi.py tests/test_atehagi_jisseki.py
git commit -m "feat(jisseki): 実績表台紙レイアウト build_jisseki_daishi_workbook を追加"
```

---

### Task 3: UI差し替え＋旧・表形式の撤去

**Files:**
- Modify: `pages/07_資料作成・変換表.py:81-86`（実績表ボタン）
- Modify: `common/atehagi.py`（旧 `jisseki_rows`・`build_jisseki_workbook` を削除。`_JISSEKI_HEADERS` も削除）
- Modify: `tests/test_atehagi_jisseki.py`（旧 `test_jisseki_rows_skips_pado_only_area`・`test_build_jisseki_workbook` を削除。`jisseki_filename` のテストは残す）

**Interfaces:**
- Consumes: `jisseki_courses(groups, version)`、`build_jisseki_daishi_workbook(courses, version, gou, haifubi)`、`jisseki_filename(version, rows)`。
- Produces: UI から新台紙の DL。

- [ ] **Step 1: Update the UI button**

`pages/07_資料作成・変換表.py` の実績表ボタン（81-86行）を次に置換。`rows`・`groups`・`version` は同スコープに既にある。出力は既存どおり `st.session_state["keihan_out"] = (label, data, fname)` に入れる（DLはボタン外の共通処理が拾う）。号・配布日は `rows` から取得:

```python
            if c2.button("挟み込み実績表を生成", key="keihan_jisseki"):
                courses = A.jisseki_courses(groups, version)
                gou = next((r["gou"] for r in rows if r.get("gou")), None)
                haifubi = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
                st.session_state["keihan_out"] = (
                    f"挟み込み実績表（{len(courses)}コース）",
                    A.build_jisseki_daishi_workbook(courses, version, gou, haifubi),
                    A.jisseki_filename(version, rows))
```

- [ ] **Step 2: Remove old functions**

`common/atehagi.py` から次を削除:
- `_JISSEKI_HEADERS = [...]` の定義
- `def jisseki_rows(groups, version):` 全体
- `def build_jisseki_workbook(rows, title=...):` 全体

（`jisseki_filename` と `jisseki_courses`・`build_jisseki_daishi_workbook`・`_md_from` は残す。）

- [ ] **Step 3: Remove old tests**

`tests/test_atehagi_jisseki.py` から `test_jisseki_rows_skips_pado_only_area` と `test_build_jisseki_workbook` の2関数を削除（`test_jisseki_filename` と Task1/2 で足した新テストは残す）。

- [ ] **Step 4: Run the full suite to verify green**

Run: `python -m pytest -q`
Expected: PASS（310件前後の既存＋新テスト全て緑。`jisseki_rows`/`build_jisseki_workbook` への参照が残っていないこと）

- [ ] **Step 5: Commit**

```bash
git add common/atehagi.py tests/test_atehagi_jisseki.py "pages/07_資料作成・変換表.py"
git commit -m "feat(jisseki): 実績表UIを台紙スタイルに一本化し旧表形式を撤去"
```

---

### Task 4: 実データ突合＋実機E2E＋オーナー目視（検証・非コミット）

**Files:**
- 一時スクリプト（scratchpad・コミットしない）。実データ（実xlsm）はリポジトリに置かない。

**Interfaces:**
- Consumes: 実データ京阪北 1248号の配送管理表 xlsm、`common/atehagi` の各関数、Playwright MCP（別ポート起動）。

- [ ] **Step 1: 実データでコース数・枚数を突合（スクリプト）**

scratchpad にスクリプトを作成し、実 xlsm から `rows_from_table`→`group_by_chiku`→`jisseki_courses` を実行。次を UTF-8 ファイルに書き出して Read で確認:
- `len(courses)` が既存の集計「挟み込みあり地区数（=実績表対象・331件）」と一致。
- 先頭数コースの `course_name`・`flyers`（案件名/枚数）が元データ（配送管理表の該当地区の size 非空行）と一致。
- 南版データがあれば版=`KEIHAN_MINAMI` でも地区名が出る（先頭「9」が落ちない）ことを確認。

Expected: コース数・各コースの案件名/枚数が元データと一致。

- [ ] **Step 2: 実機E2E（別ポート・Playwright）**

`common/*.py` を変更したので 8502 は触らず、別ポート（例 8503）で `feature/jisseki-daishi` を起動。Playwright で「資料作成・変換表」→実xlsmアップロード→「挟み込み実績表を生成」→DL。DL 実物を openpyxl で開き、タイトル/コース名/案件名/枚数/`（サイン）`空欄/4コース折り返し/印刷=landscape を検証。

Expected: 台紙が正しく生成され、目視で実物の雰囲気（上コース名・下案件名/枚数/サイン）になっている。

- [ ] **Step 3: オーナー目視で1枚確認**

生成した1ページ目をオーナーに見てもらい、`（サイン）`の見せ方・列幅・4コース/行の収まりを確認。指摘があれば列幅/サイン表現を微調整（`build_jisseki_daishi_workbook` の列幅定数 or サイン行文言のみ）。

Expected: オーナーOK。NGなら軽微修正して再確認。

- [ ] **Step 4: 完了処理**

`superpowers:verification-before-completion` で全テスト緑を再確認 → `superpowers:finishing-a-development-branch` でマージ/PR方針を提示（公開デモ `feature/demo-share` へ反映するかはオーナー確認）。記録を `.company/distribution/pm/projects/` と `secretary/notes` に残す。

---

## Self-Review
- **Spec coverage**: 要件1-8 すべてタスクに対応（1-5=Task1/2、6-7=Task2/3、8=Task1/2の版対応＋Task4検証）。検証(§6)=Task4。非対象(§7)=計画に含めず。未確定(§8)=Task4 Step3 で確定。
- **Placeholder scan**: コードは全て実体。`_dl` ヘルパ名の注意書きは既存ファイルの呼び出し形に合わせる指示として明示。
- **Type consistency**: `jisseki_courses` の返す dict キー（code/chiku_name/course_name/flyers, flyers内 name/count）を Task2 テスト・実装で一貫使用。`build_jisseki_daishi_workbook(courses, version, gou, haifubi, per_row=4)` のシグネチャを Task2/3 で一致。
