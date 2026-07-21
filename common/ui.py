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

/* カレンダーの曜日ヘッダを日本語に。元の英語(Su/Mo/Tu/We/Th/Fr/Sa)はfont-size:0で消し、
   CSSのcontentで日月火…を出す。CSS生成文字はブラウザの自動翻訳の対象外なので、
   万一翻訳が効いても「スーモートゥ私たちはフロリーサ」に化けない。
   [data-baseweb="calendar"] 内の div[role="presentation"] は曜日ヘッダ行だけに一意対応。 */
[data-baseweb="calendar"] div[role="presentation"] > div{ font-size:0 !important; }
[data-baseweb="calendar"] div[role="presentation"] > div::after{
  font-size:.78rem; font-weight:700; color:var(--muted);
}
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(1)::after{ content:"日"; color:#c0392b; }
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(2)::after{ content:"月"; }
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(3)::after{ content:"火"; }
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(4)::after{ content:"水"; }
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(5)::after{ content:"木"; }
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(6)::after{ content:"金"; }
[data-baseweb="calendar"] div[role="presentation"] > div:nth-child(7)::after{ content:"土"; color:#0f87b8; }

/* カレンダーの月表示(July等)を日本語に。JS(_NO_TRANSLATE_JS)が月名のボタンに
   data-jp-month="July" のような「属性」だけを付け、置換はCSSのcontentで行う。
   テキストノードを書き換えるとReactの管理DOMとズレてremoveChildエラーを自ら招くため、
   属性を付けるだけに留めるのが肝。年(2026)は数字なのでそのまま。 */
[data-baseweb="calendar"] button[data-jp-month]{ font-size:0 !important; }
[data-baseweb="calendar"] button[data-jp-month] > span{ font-size:1rem; }   /* ▼アイコンを戻す */
[data-baseweb="calendar"] button[data-jp-month]::before{
  font-size:.95rem; font-weight:700; color:var(--ink);
}
[data-baseweb="calendar"] button[data-jp-month="January"]::before{ content:"1月"; }
[data-baseweb="calendar"] button[data-jp-month="February"]::before{ content:"2月"; }
[data-baseweb="calendar"] button[data-jp-month="March"]::before{ content:"3月"; }
[data-baseweb="calendar"] button[data-jp-month="April"]::before{ content:"4月"; }
[data-baseweb="calendar"] button[data-jp-month="May"]::before{ content:"5月"; }
[data-baseweb="calendar"] button[data-jp-month="June"]::before{ content:"6月"; }
[data-baseweb="calendar"] button[data-jp-month="July"]::before{ content:"7月"; }
[data-baseweb="calendar"] button[data-jp-month="August"]::before{ content:"8月"; }
[data-baseweb="calendar"] button[data-jp-month="September"]::before{ content:"9月"; }
[data-baseweb="calendar"] button[data-jp-month="October"]::before{ content:"10月"; }
[data-baseweb="calendar"] button[data-jp-month="November"]::before{ content:"11月"; }
[data-baseweb="calendar"] button[data-jp-month="December"]::before{ content:"12月"; }

/* 自動翻訳を止めるための仕込み(下記 _NO_TRANSLATE_JS)で入るiframeは高さ0。行ごと消す。 */
[data-testid="stElementContainer"]:has(iframe[height="0"]){ display:none !important; }

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

/* ===== マスタ管理: ステータストグル（運用中=光る水色の丸 / 停止中=グレーの丸） ===== */
/* 行ごとの st.container(key="mstat-on-<master>-<id>") が付ける st-key-* で全行をまとめてスコープ */
[class*="st-key-mstat-on-"] .stButton>button{
  border-radius:999px !important; background:var(--primary) !important; color:#fff !important;
  border:none !important; font-weight:700 !important; padding:.35rem 1rem !important;
  animation:mstatpulse 1.7s infinite;
}
@keyframes mstatpulse{
  0%{ box-shadow:0 0 0 0 rgba(20,164,220,.55); }
  70%{ box-shadow:0 0 0 8px rgba(20,164,220,0); }
  100%{ box-shadow:0 0 0 0 rgba(20,164,220,0); }
}
[class*="st-key-mstat-off-"] .stButton>button{
  border-radius:999px !important; background:#eef1f4 !important; color:#8b98a6 !important;
  border:1px solid var(--line) !important; font-weight:700 !important; padding:.35rem 1rem !important;
  box-shadow:none !important;
}
[class*="st-key-mstat-off-"] .stButton>button:hover{ background:#e4e8ee !important; color:#67788a !important; }
/* 削除(ゴミ箱)は控えめなアイコンボタンに */
[class*="st-key-mtrash-"] .stButton>button{
  background:#fff !important; color:#c0392b !important; border:1px solid var(--line) !important;
  box-shadow:none !important; padding:.35rem .6rem !important;
}
[class*="st-key-mtrash-"] .stButton>button:hover{ background:#fdecea !important; }
</style>
"""


# Streamlit は <html lang="en"> を固定で出力する。中身が日本語でもブラウザは「英語のページ」と
# 判定し、Chromeの自動翻訳(英語→日本語)が走る。すると
#   ・カレンダーの Su Mo Tu We Th Fr Sa が「スーモートゥ私たちはフロリーサ」に化ける
#   ・翻訳がテキストノードを差し替えるためReactの管理DOMとズレ、再描画時に
#     NotFoundError: Failed to execute 'removeChild' on 'Node' が出る
# の2つが起きる。lang を ja にし、translate=no / notranslate を明示して翻訳自体を止める。
# st.markdown 内の <script> は実行されないため、components.html(iframe)から親documentを触る。
_NO_TRANSLATE_JS = """
<script>
(function () {
  var doc = window.parent.document;
  if (!doc) return;
  doc.documentElement.lang = "ja";
  doc.documentElement.setAttribute("translate", "no");
  doc.documentElement.classList.add("notranslate");
  if (!doc.querySelector('meta[name="google"][content="notranslate"]')) {
    var m = doc.createElement("meta");
    m.name = "google";
    m.content = "notranslate";
    doc.head.appendChild(m);
  }

  // カレンダーの月名ボタン(July等)に data-jp-month 属性を付けるだけの処理。
  // 実際の日本語化はCSS側(content)で行う。テキストノードを書き換えるとReactの
  // 管理DOMとズレて removeChild エラーを招くため、属性の付与だけに留めている。
  var MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"];
  function tagMonthButtons() {
    var btns = doc.querySelectorAll('[data-baseweb="calendar"] button[aria-live="polite"]');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i], own = "";
      for (var j = 0; j < b.childNodes.length; j++) {
        if (b.childNodes[j].nodeType === 3) own += b.childNodes[j].textContent;
      }
      own = own.trim();
      // 月名のボタンだけ印を付ける(年ボタン=2026 は数字なので対象外)
      if (MONTHS.indexOf(own) >= 0) {
        if (b.getAttribute("data-jp-month") !== own) b.setAttribute("data-jp-month", own);
      }
    }
  }
  // Streamlitは頻繁にDOMを触るので、描画フレーム単位にまとめて実行する
  var queued = false;
  new MutationObserver(function () {
    if (queued) return;
    queued = true;
    window.parent.requestAnimationFrame(function () { queued = false; tagMonthButtons(); });
  }).observe(doc.body, { childList: true, subtree: true });
  tagMonthButtons();
})();
</script>
"""


def apply_app_style():
    """モダン・水色ワンポイント・暗色サイドバーのスタイルを現在のページに適用する。
    あわせてブラウザの自動翻訳を止める(化け文字・removeChildエラーの防止)。"""
    st.markdown(_STYLE, unsafe_allow_html=True)
    components.html(_NO_TRANSLATE_JS, height=0)


_PERIOD_PRESETS = {"全期間": "all", "今月": "month", "今週": "week"}
_PERIOD_CUSTOM = "期間指定"


def period_picker(*, key: str):
    """全期間 / 今月 / 今週 / 期間指定 を同じ並びのボタンで選ばせる共通の期間フィルタ。
    「期間指定」を選んだ時だけカレンダーを出す。(lo, hi, 表示ラベル) を返す。
    lo/hi は 'YYYY-MM-DD' 文字列、全期間なら (None, None)。"""
    from common import posting_logic

    options = list(_PERIOD_PRESETS.keys()) + [_PERIOD_CUSTOM]
    sel = st.pills("期間", options, selection_mode="single", default="全期間",
                   label_visibility="collapsed", key=f"{key}_pills")
    if not sel:
        sel = "全期間"

    if sel == _PERIOD_CUSTOM:
        custom = st.date_input(":material/calendar_month: 期間を指定（クリックでカレンダー）",
                               value=(), format="YYYY/MM/DD", key=f"{key}_custom")
        if isinstance(custom, (list, tuple)) and len(custom) == 2:
            lo, hi = str(custom[0]), str(custom[1])
            return lo, hi, f"{lo} 〜 {hi}"
        # 開始だけ選んだ途中の状態。確定するまでは全期間のまま見せる。
        return None, None, "全期間（開始日と終了日を選ぶと絞り込みます）"

    lo, hi = posting_logic.period_range(_PERIOD_PRESETS[sel])
    return lo, hi, ("全期間" if lo is None else f"{lo} 〜 {hi}")


def _flash_slot(section: str | None) -> str:
    """flash の保存先キー。section 省略時は従来どおり "_flash"(後方互換)。"""
    return "_flash" if section is None else f"_flash_{section}"


def flash(message: str, section: str | None = None):
    """登録直後の再実行(rerun)をまたいで1度だけ出す成功メッセージをセットする。
    rerun 直前に st.success を出しても新しい実行で消えてしまうため、session_state に退避する。

    section: メッセージを出したい場所の識別子(タブ名など)。
      Streamlit のタブは1回の実行で全タブの本体を描画するため、section を付けないと
      最初に呼ばれた show_flash() がメッセージを奪い、操作したタブに出ない。
      section を付けると、同じ section の show_flash() だけが受け取る。
      省略時は従来と同じ共有の1枠を使う(既存ページはそのまま動く)。
    """
    st.session_state[_flash_slot(section)] = message


def show_flash(section: str | None = None):
    """flash() でセットされたメッセージがあれば success で表示して消す(1回だけ)。
    登録フォームの先頭で呼ぶ。section を渡すと自分宛のメッセージだけを消費する。"""
    msg = st.session_state.pop(_flash_slot(section), None)
    if msg:
        st.success(msg)


def confirm_delete(*, key: str, detail: str, on_confirm, label: str = "削除",
                   warning: str | None = None, success: str = "削除しました",
                   section: str | None = None, button_container=None):
    """削除→確認→実行を全画面で同じ挙動にする共通部品。
    ボタンを押した時点では消さず、session_state に確認待ちを立てて確認UIを出す。
    「はい」で on_confirm() を実行し、flash で結果を知らせる。

    key      : 画面内で一意な文字列(行idを含めること。固定keyだと別の行を消しかねない)
    detail   : 確認画面に出す対象の内容(日付・金額など)
    on_confirm: 実際に消す処理(引数なしの呼び出し可能オブジェクト)
    label    : ボタンの文言(マスタでは「停止中にする」を渡す)
    warning  : 確認の見出し(省略時は「削除しますか？」)
    success  : 実行後に出すメッセージ
    section  : flash(success) の宛先(タブ毎に分けたいとき。show_flash(section) と対で使う)
    button_container: 削除ボタンだけを描画する場所(st.columns の列など)。
      渡すと、確認UI(警告文・詳細・はい/いいえ)は呼び出した場所にそのまま出るので、
      行の右端の狭い列にボタンを置きつつ確認は全幅で出せる。省略時は全部その場に描画。
    """
    pending = f"_del_pending_{key}"
    if st.session_state.get(pending):
        st.warning(warning or "⚠️ 削除しますか？")
        if detail:
            st.caption(detail)
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("はい", type="primary", key=f"{key}_ok"):
            on_confirm()
            st.session_state.pop(pending, None)
            flash(success, section)
            st.rerun()
        if c2.button("いいえ", key=f"{key}_no"):
            st.session_state.pop(pending, None)
            st.rerun()
        return
    target = button_container if button_container is not None else st
    if target.button(label, key=f"{key}_btn"):
        st.session_state[pending] = True
        st.rerun()


def checkbox_list_editor(disp_rows, *, key, select_col="選択"):
    """一覧を『選択チェック列＋他列は読み取り専用』の data_editor で描画して返す。
    disp_rows は list[dict] か DataFrame（表示用に整形済み・id列も含めておく）。"""
    import pandas as pd

    df = disp_rows if isinstance(disp_rows, pd.DataFrame) else pd.DataFrame(disp_rows)
    if df.empty:
        st.caption("表示できる行がありません。")
        return df
    other = [c for c in df.columns if c != select_col]
    if select_col not in df.columns:
        df = df.copy()
        df.insert(0, select_col, False)
    df = df[[select_col] + [c for c in df.columns if c != select_col]]
    return st.data_editor(
        df, hide_index=True, use_container_width=True,
        column_config={select_col: st.column_config.CheckboxColumn(select_col, default=False)},
        disabled=other, key=key)


def selected_rows_excel_button(edited_df, *, key, filename, select_col="選択",
                               label=None, container=None):
    """選択された行だけを（選択列を除いて）Excel化する download_button。0件は無効。"""
    from common import posting_logic
    from common.excel_io import freeze_xlsx_bytes
    import pandas as pd

    rows = posting_logic.rows_for_excel(edited_df, select_col=select_col)
    target = container if container is not None else st
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(rows or [{}]).to_excel(w, index=False, sheet_name="選択した行")
    target.download_button(
        label or f"選択した行をExcelで保存（{len(rows)}件）",
        data=freeze_xlsx_bytes(buf.getvalue()), file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:", disabled=not rows, key=key,
        use_container_width=True)


def bulk_delete_action(selected_ids, *, delete_fn, section, key, noun="件", container=None):
    """選択した行をまとめて削除する。確認を挟み、押した時点の選択idを固定してから消す。
    ボタンだけ container(列)に置くと、確認UIは呼び出し位置＝全幅に出る。"""
    pending = f"_bulkdel_pending_{key}"
    ids = st.session_state.get(pending)
    if ids:  # 確認待ち
        st.warning(f"⚠️ 選択した{len(ids)}{noun}を削除しますか？")
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("はい", type="primary", key=f"{key}_ok"):
            for i in ids:
                delete_fn(i)
            st.session_state.pop(pending, None)
            flash(f"{len(ids)}{noun}を削除しました", section)
            st.rerun()
        if c2.button("いいえ", key=f"{key}_no"):
            st.session_state.pop(pending, None)
            st.rerun()
        return
    target = container if container is not None else st
    if target.button(f"選択した行を削除（{len(selected_ids)}{noun}）",
                     key=f"{key}_btn", disabled=not selected_ids,
                     use_container_width=True):
        st.session_state[pending] = list(selected_ids)
        st.rerun()


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
    from common.excel_io import freeze_xlsx_bytes

    c1, c2, _ = st.columns([1, 1, 6])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="data")
    # 内容が同じなら毎回同じバイト列に(＝ダウンロードURLが変わらず404にならない)
    c1.download_button(
        "Excelで保存", data=freeze_xlsx_bytes(buf.getvalue()), file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key}_xlsx", use_container_width=True)
    with c2:
        components.html(
            """<button onclick="window.parent.print()"
                style="width:100%;padding:.5rem .6rem;border:1.5px solid #14a4dc;border-radius:10px;
                       background:#fff;color:#0f87b8;font-weight:700;cursor:pointer;
                       font-family:'Noto Sans JP',sans-serif;">印刷する</button>""",
            height=46)
