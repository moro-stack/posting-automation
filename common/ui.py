"""アプリ共通のUIスタイル(モダン・水色ワンポイント・暗色サイドバー・Noto Sans JP)。各ページ先頭で apply_app_style()。"""
import io

import streamlit as st
import streamlit.components.v1 as components

_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;800&display=swap');

:root{
  --bg:#f5f8fb; --paper:#ffffff;
  --primary:#14a4dc; --primary-d:#0f87b8; --primary-soft:#e6f6fc;
  --ink:#1f2d3a; --muted:#67788a; --line:#e6ebf1; --icon:#8b98a6;
  --side:#2e3238; --side-hover:#3a3f47; --side-ink:#d6dae1; --side-active:#ffffff;
  --shadow:0 1px 2px rgba(20,40,60,.05), 0 6px 18px rgba(20,40,60,.05);
}

.stApp{ background:var(--bg); }

html, body, .stApp, [data-testid="stAppViewContainer"], [class*="css"]{
  font-family:"Noto Sans JP",-apple-system,"Hiragino Kaku Gothic ProN","Yu Gothic UI","Meiryo",sans-serif !important;
  color:var(--ink);
  -webkit-font-smoothing:antialiased;
}

/* メイン領域: 全幅・広め(サイドバーを狭くした分ゆったり) */
.block-container{
  max-width:100% !important;
  padding:1.5rem 2.2rem 3rem !important;
}

/* Streamlit装飾を控えめに */
[data-testid="stHeader"]{ background:transparent; }
[data-testid="stDecoration"]{ display:none; }
#MainMenu, footer{ visibility:hidden; }

/* 見出し(小さめ・Streamlit既定より優先させるため詳細度を上げる) */
h1,h2,h3,h4{ color:var(--ink); font-weight:700; }
[data-testid="stHeading"] h1, [data-testid="stMarkdownContainer"] h1, .stMarkdown h1{
  font-size:1.35rem !important; letter-spacing:.01em; margin-bottom:.35rem; padding-top:.2rem;
}
[data-testid="stHeading"] h2, [data-testid="stMarkdownContainer"] h2, .stMarkdown h2{ font-size:1.14rem !important; }
[data-testid="stHeading"] h3, [data-testid="stMarkdownContainer"] h3, .stMarkdown h3{ font-size:1.02rem !important; }

/* ===== ヒーロー ===== */
.hero{ margin:.1rem 0 1.1rem; }
.hero .kicker{
  display:inline-block; color:var(--primary); font-weight:700; font-size:.78rem;
  letter-spacing:.10em; margin-bottom:.2rem;
}
.hero .hero-title{ font-size:1.4rem; font-weight:800; color:var(--ink); line-height:1.25; }
.hero .hl{ color:var(--primary); }
.hero .hero-sub{ color:var(--muted); font-size:.92rem; font-weight:500; margin-top:.2rem; }

/* ===== 機能カード ===== */
.feat-head{ display:flex; align-items:center; gap:.55rem; margin:.1rem 0 .35rem; }
.feat-ic{
  width:34px; height:34px; flex:none; border-radius:10px;
  display:flex; align-items:center; justify-content:center; font-size:1.05rem;
  background:var(--primary-soft); color:var(--primary);
}
.feat-title{ font-weight:700; color:var(--ink); font-size:1.0rem; }

/* ===== サイドバー: 暗色ネイビー・幅狭め・水色アクセント ===== */
[data-testid="stSidebar"]{
  background:var(--side); border-right:none;
  width:220px !important; min-width:220px !important;
}
[data-testid="stSidebar"] *{ color:var(--side-ink); }
[data-testid="stSidebarNav"]{ padding-top:.5rem; }
[data-testid="stSidebarNav"] a{
  border-radius:9px; font-weight:600; margin:2px 8px; padding:.36rem .55rem;
  transition:all .12s ease;
}
/* ナビ名を省略(…)せず全部見せる */
[data-testid="stSidebarNav"] a p{
  color:var(--side-ink) !important; font-size:.88rem; line-height:1.25;
  white-space:normal !important; overflow:visible !important; text-overflow:clip !important;
}
[data-testid="stSidebarNav"] a span{ overflow:visible !important; }
[data-testid="stSidebarNav"] a:hover{ background:var(--side-hover); }
[data-testid="stSidebarNav"] a:hover p{ color:#fff !important; }
[data-testid="stSidebarNav"] a[aria-current="page"]{
  background:linear-gradient(90deg, rgba(20,164,220,.30), rgba(20,164,220,.08));
  box-shadow:inset 3px 0 0 var(--primary);
}
[data-testid="stSidebarNav"] a[aria-current="page"] p{ color:var(--side-active) !important; }
[data-testid="stSidebarNav"] span[data-testid="stIconMaterial"]{ color:#8fa6bd !important; }
[data-testid="stSidebarNav"] a[aria-current="page"] span[data-testid="stIconMaterial"]{ color:var(--primary) !important; }
/* サイドバー内(暗色)のたたむボタンは明色 */
[data-testid="stSidebarCollapseButton"] *{ color:var(--side-ink) !important; }

/* ボタン: 水色フィル(登録・送信) */
.stButton>button, [data-testid="stFormSubmitButton"]>button{
  background:var(--primary); color:#fff !important; border:none; border-radius:10px;
  padding:0.5rem 1.25rem; font-weight:700; transition:all .15s ease;
  box-shadow:0 1px 2px rgba(15,135,184,.25);
}
.stButton>button:hover, [data-testid="stFormSubmitButton"]>button:hover{
  background:var(--primary-d); color:#fff !important; box-shadow:0 4px 12px rgba(15,135,184,.30);
}
[data-testid="stDownloadButton"]>button{
  background:#fff; color:var(--primary-d) !important; border:1.5px solid var(--primary);
  border-radius:10px; padding:0.5rem 1.25rem; font-weight:700; transition:all .15s ease;
}
[data-testid="stDownloadButton"]>button:hover{ background:var(--primary-soft); }

/* pills(案件・期間指定)を水色ボタンで目立たせる。未選択=水色枠/選択=水色フィル */
button[data-testid="stBaseButton-pills"]{
  border-radius:999px !important; border:1.5px solid var(--primary) !important;
  color:var(--primary-d) !important; background:#fff !important; font-weight:700 !important;
}
button[data-testid="stBaseButton-pills"] p{ color:var(--primary-d) !important; }
button[data-testid="stBaseButton-pills"]:hover{ background:var(--primary-soft) !important; }
button[data-testid="stBaseButton-pillsActive"]{
  border-radius:999px !important; background:var(--primary) !important;
  color:#fff !important; border:1.5px solid var(--primary) !important; font-weight:700 !important;
}
button[data-testid="stBaseButton-pillsActive"] p{ color:#fff !important; }

/* page_link */
[data-testid="stPageLink"] a{
  display:inline-flex; align-items:center; gap:.3rem; font-weight:700; color:var(--primary-d) !important;
  background:var(--primary-soft); border-radius:8px; padding:.32rem 1rem; transition:all .15s ease;
}
[data-testid="stPageLink"] a:hover{ background:#d3eefa; }
[data-testid="stPageLink"] a p{ color:var(--primary-d) !important; font-weight:700; }

/* 入力欄 */
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input{
  border-radius:9px !important; border:1.5px solid var(--line) !important; background:#fff !important;
}
[data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus{
  border-color:var(--primary) !important; box-shadow:0 0 0 3px rgba(20,164,220,.15) !important;
}

/* メトリクス: 白カード */
[data-testid="stMetric"]{
  background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:1rem 1.1rem; box-shadow:var(--shadow);
}
[data-testid="stMetricValue"]{ font-weight:800; color:var(--ink); }
[data-testid="stMetricLabel"]{ color:var(--muted); font-weight:600; }

/* ファイルアップローダー */
[data-testid="stFileUploaderDropzone"]{
  background:#fff; border:1.5px dashed #b9c6d2; border-radius:14px;
}

/* コンテナ(カード)・展開・アラート・表 */
[data-testid="stVerticalBlockBorderWrapper"]{
  background:#fff; border:1px solid var(--line) !important; border-radius:14px !important;
  box-shadow:var(--shadow); transition:box-shadow .15s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover{ box-shadow:0 10px 26px rgba(20,40,60,.10); }
[data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stDataEditor"]{
  border-radius:12px; overflow:hidden; border:1px solid var(--line);
}
[data-testid="stAlert"]{ border-radius:12px; border:1px solid var(--line); }
[data-testid="stExpander"]{ border:1px solid var(--line); border-radius:12px; background:#fff; }
[data-testid="stExpander"] summary:hover{ color:var(--primary-d); }
/* 内訳(配布員代/雑費)の見出しを太く・見やすく */
[data-testid="stExpander"] summary{ font-weight:700 !important; }
[data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span{
  font-weight:700 !important; font-size:1.0rem; color:var(--ink);
}
[data-testid="stCaptionContainer"]{ color:var(--muted); }

/* ===== 英語を減らす・実務的に整える ===== */
/* 右上のDeploy等ツールバー、表ホバー時の英語ツールバー、入力欄下の英語ヒントを隠す */
[data-testid="stToolbar"], [data-testid="stAppDeployButton"]{ display:none !important; }
[data-testid="stElementToolbar"], [data-testid="stElementToolbarButton"]{ display:none !important; }
/* サイドバーを畳んだ時の「展開」ボタンはツールバー内にあるため、ツールバー非表示だと
   一緒に消えてしまう。展開ボタンがある時だけツールバーを出し、白丸ボタンで必ず見えるように。 */
[data-testid="stToolbar"]:has([data-testid="stExpandSidebarButton"]){
  display:flex !important; background:transparent !important; z-index:1000;
}
[data-testid="stExpandSidebarButton"]{ display:flex !important; }
[data-testid="stExpandSidebarButton"] button{
  background:#fff !important; border:1px solid var(--line) !important; border-radius:10px !important;
  box-shadow:var(--shadow);
}
[data-testid="stExpandSidebarButton"] button:hover{ background:var(--primary-soft) !important; }
[data-testid="stExpandSidebarButton"] *{ color:var(--primary-d) !important; }
[data-testid="InputInstructions"]{ display:none !important; }
/* 日付レンジのカレンダーに出る英語のクイック選択(Choose a date range/None)を隠す(preset pillsで代替) */
div[data-baseweb="popover"]:has([data-baseweb="calendar"]) [data-baseweb="select"],
div[data-baseweb="popover"]:has([data-baseweb="calendar"]) label{ display:none !important; }

/* ファイルアップローダーを日本語化 */
[data-testid="stFileUploaderDropzoneInstructions"]{ display:none !important; }
[data-testid="stFileUploaderDropzone"]{ position:relative; min-height:84px; align-items:center; }
[data-testid="stFileUploaderDropzone"]::before{
  content:"ここにファイルをドラッグ、または右のボタンで選択（画像・PDF）";
  color:var(--muted); font-size:.9rem; padding-left:.7rem;
}
/* 「Browse files」ボタンだけ日本語化。×(削除)・＋(追加)ボタンには効かせない
   (以前は dropzone 内の全 button を対象にしていたため、ファイル選択後に出る
    削除(×)・追加(＋)ボタンのアイコンが消え「ファイルを選ぶ」に化けていた) */
[data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] > *{ display:none !important; }
[data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"]::after{
  content:"ファイルを選ぶ"; font-size:.9rem !important; font-weight:700;
}

/* ===== 表を見やすく（罫線・角丸・ヘッダ強調・行間ゆったり） ===== */
[data-testid="stDataFrame"]{ border:1px solid var(--line) !important; border-radius:12px; }
[data-testid="stDataFrame"] [role="columnheader"]{ font-weight:700 !important; background:#f1f5f9 !important; }
[data-testid="stTable"] table{ border-collapse:separate; border-spacing:0; }
[data-testid="stTable"] thead th{
  background:#eef3f8; color:var(--ink); font-weight:700; font-size:.92rem;
  padding:.6rem .8rem; border-bottom:2px solid #dbe3ec; text-align:left;
}
[data-testid="stTable"] tbody td{
  padding:.55rem .8rem; border-bottom:1px solid var(--line); font-size:.92rem;
}
[data-testid="stTable"] tbody tr:nth-child(even) td{ background:#f7fafc; }
[data-testid="stTable"] tbody tr:hover td{ background:var(--primary-soft); }
</style>
"""


def apply_app_style():
    """モダン・水色ワンポイント・暗色サイドバーのスタイルを現在のページに適用する。"""
    st.markdown(_STYLE, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = ""):
    """統一感のあるページ見出し(任意)。"""
    prefix = f"{icon} " if icon else ""
    st.markdown(f"# {prefix}{title}")
    if subtitle:
        st.caption(subtitle)


def nice_table(rows, empty_msg: str = "データはまだありません。"):
    """見やすいHTMLテーブルで表示(英語ツールバー無し・行間ゆったり・番号列なし)。
    rows は list[dict] か DataFrame。表示用に整形済みの値を渡すこと。"""
    import pandas as pd

    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df is None or df.empty:
        st.caption(empty_msg)
        return
    try:
        st.table(df.style.hide(axis="index"))
    except Exception:  # noqa: BLE001 - 古いpandas等の保険
        st.table(df.reset_index(drop=True))


def section_export(rows, filename: str, key: str):
    """一覧(rows: list[dict] か DataFrame)を CSV / Excel でダウンロード & 印刷できるボタン列を出す。
    経理提出用の出力を各セクションに分散させるための共通部品。"""
    import pandas as pd

    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df is None or df.empty:
        return
    c1, c2, _ = st.columns([1, 1, 6])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="data")
    c1.download_button(
        "Excelで保存", data=buf.getvalue(), file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key}_xlsx", use_container_width=True)
    with c2:
        components.html(
            """<button onclick="window.parent.print()"
                style="width:100%;padding:.5rem .6rem;border:1.5px solid #14a4dc;border-radius:10px;
                       background:#fff;color:#0f87b8;font-weight:700;cursor:pointer;
                       font-family:'Noto Sans JP',sans-serif;">印刷する</button>""",
            height=46)
