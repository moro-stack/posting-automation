"""アプリ共通のUIスタイル(落ち着いた水色・モダン・Noto Sans JP)。各ページ先頭で apply_app_style()。"""
import streamlit as st

_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;800&display=swap');

:root{
  --bg:#f4f7fa; --paper:#ffffff;
  --primary:#2f8fae; --primary-d:#246d86; --primary-soft:#e7f1f6;
  --ink:#23323f; --muted:#69788a; --line:#e5eaf0; --icon:#7c8a99;
  --shadow:0 1px 2px rgba(20,40,60,.05), 0 6px 18px rgba(20,40,60,.05);
}

.stApp{ background:var(--bg); }

html, body, .stApp, [data-testid="stAppViewContainer"], [class*="css"]{
  font-family:"Noto Sans JP",-apple-system,"Hiragino Kaku Gothic ProN","Yu Gothic UI","Meiryo",sans-serif !important;
  color:var(--ink);
  -webkit-font-smoothing:antialiased;
}

/* メイン領域: 左右を余すことなく全幅。黄色フレームは廃止。 */
.block-container{
  max-width:100% !important;
  padding:2.0rem 2.6rem 3.5rem !important;
}

/* Streamlit装飾を控えめに */
[data-testid="stHeader"]{ background:transparent; }
[data-testid="stDecoration"]{ display:none; }
#MainMenu, footer{ visibility:hidden; }

/* 見出し */
h1,h2,h3,h4{ color:var(--ink); font-weight:700; }
h1{ font-size:1.7rem; letter-spacing:.01em; }
h2{ font-size:1.3rem; }
h3{ font-size:1.12rem; }

/* ===== ヒーロー(ホーム) ===== */
.hero{ margin:.1rem 0 1.4rem; }
.hero .kicker{
  display:inline-block; color:var(--primary); font-weight:700; font-size:.82rem;
  letter-spacing:.10em; margin-bottom:.25rem;
}
.hero .hero-title{ font-size:1.85rem; font-weight:800; color:var(--ink); line-height:1.25; }
.hero .hl{ color:var(--primary); }
.hero .hero-sub{ color:var(--muted); font-size:.95rem; font-weight:500; margin-top:.25rem; }

/* ===== 機能カード(ホーム) ===== */
.feat-head{ display:flex; align-items:center; gap:.55rem; margin:.1rem 0 .35rem; }
.feat-ic{
  width:38px; height:38px; flex:none; border-radius:10px;
  display:flex; align-items:center; justify-content:center; font-size:1.15rem;
  background:#eef2f6; color:var(--icon); filter:grayscale(1);
}
.feat-title{ font-weight:700; color:var(--ink); font-size:1.05rem; }

/* サイドバー */
[data-testid="stSidebar"]{ background:#fbfcfe; border-right:1px solid var(--line); }
[data-testid="stSidebarNav"] a{ border-radius:8px; font-weight:600; }
[data-testid="stSidebarNav"] a:hover{ background:var(--primary-soft); }
[data-testid="stSidebarNav"] a[aria-current="page"]{ background:var(--primary-soft); }
[data-testid="stSidebarNav"] a p{ color:var(--ink) !important; }
/* サイドバーのアイコンはグレーで統一 */
[data-testid="stSidebarNav"] span[data-testid="stIconMaterial"]{ color:var(--icon) !important; }

/* ボタン: 落ち着いた水色・モダン(控えめな角丸と影) */
.stButton>button, [data-testid="stFormSubmitButton"]>button{
  background:var(--primary); color:#fff !important; border:none; border-radius:10px;
  padding:0.5rem 1.2rem; font-weight:700; transition:all .15s ease;
  box-shadow:0 1px 2px rgba(36,109,134,.25);
}
.stButton>button:hover, [data-testid="stFormSubmitButton"]>button:hover{
  background:var(--primary-d); color:#fff !important; box-shadow:0 3px 10px rgba(36,109,134,.28);
}
[data-testid="stDownloadButton"]>button{
  background:#fff; color:var(--primary-d) !important; border:1.5px solid var(--primary);
  border-radius:10px; padding:0.5rem 1.2rem; font-weight:700; transition:all .15s ease;
}
[data-testid="stDownloadButton"]>button:hover{ background:var(--primary-soft); }

/* page_link */
[data-testid="stPageLink"] a{
  display:inline-flex; align-items:center; gap:.3rem; font-weight:700; color:var(--primary-d) !important;
  background:var(--primary-soft); border-radius:8px; padding:.32rem 1rem; transition:all .15s ease;
}
[data-testid="stPageLink"] a:hover{ background:#d8e9f0; }
[data-testid="stPageLink"] a p{ color:var(--primary-d) !important; font-weight:700; }

/* 入力欄 */
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input{
  border-radius:9px !important; border:1.5px solid var(--line) !important; background:#fff !important;
}
[data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus{
  border-color:var(--primary) !important; box-shadow:0 0 0 3px rgba(47,143,174,.15) !important;
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
[data-testid="stCaptionContainer"]{ color:var(--muted); }
</style>
"""


def apply_app_style():
    """落ち着いた水色・モダンなスタイル(Noto Sans JP・全幅)を現在のページに適用する。"""
    st.markdown(_STYLE, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = ""):
    """統一感のあるページ見出し(任意)。"""
    prefix = f"{icon} " if icon else ""
    st.markdown(f"# {prefix}{title}")
    if subtitle:
        st.caption(subtitle)
