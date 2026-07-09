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
[data-testid="stSidebarCollapseButton"] *, [data-testid="stSidebarCollapsedControl"] *{ color:var(--side-ink) !important; }

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
[data-testid="stCaptionContainer"]{ color:var(--muted); }
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


def section_export(rows, filename: str, key: str):
    """一覧(rows: list[dict] か DataFrame)を CSV / Excel でダウンロード & 印刷できるボタン列を出す。
    経理提出用の出力を各セクションに分散させるための共通部品。"""
    import pandas as pd

    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df is None or df.empty:
        return
    c1, c2, c3, _ = st.columns([1, 1, 1, 5])
    csv = ("﻿" + df.to_csv(index=False)).encode("utf-8")
    c1.download_button("⬇️ CSV", data=csv, file_name=f"{filename}.csv",
                       mime="text/csv", key=f"{key}_csv", use_container_width=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="data")
    c2.download_button(
        "⬇️ Excel", data=buf.getvalue(), file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key}_xlsx", use_container_width=True)
    with c3:
        components.html(
            """<button onclick="window.parent.print()"
                style="width:100%;padding:.5rem .6rem;border:1.5px solid #14a4dc;border-radius:10px;
                       background:#fff;color:#0f87b8;font-weight:700;cursor:pointer;
                       font-family:'Noto Sans JP',sans-serif;">🖨️ 印刷</button>""",
            height=46)
