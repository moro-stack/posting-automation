# 号別明細サマリーの文字重なり（`.metric-lines`）

## 概要

`st.columns` に複数行のカスタムHTMLを入れると、スマホ幅で縦積みになったときに
次のカラムがめり込み、文字が重なって表示される。これを防ぐための共通クラスが
`.metric-lines`（`common/ui.py`）である。

対象は 03 号別明細の上部サマリー（配布原価／売上／利益）と、
06 大阪支社売上のKPI（売上／原価／利益／利益率／配布部数／挟み込み数）。

## 設計・方針

Streamlit の markdown コンテナ（`[data-testid="stMarkdownContainer"]`）には
`marginBottom: -1rem`（`theme.spacing.lg`）が付いている。これは単一の `<p>` を
想定した詰め調整だが、親が `display:flex; align-items:center` のとき
**フレックスアイテムのクロスサイズをそのまま 1rem 分短く**する。
縦積みになったカラムでは、その欠けた 16px ぶん次のカラムがめり込む。

打ち消す方法は2つある。

| 方式 | セレクタ | 問題 |
|---|---|---|
| 親を選んで margin を 0 にする | `[data-testid="stMarkdownContainer"]:has(.metric-lines)` | `:has()` は **iOS Safari 15.6 未満で効かない**（caniuse: css-has）。古いiPhoneでは修正が丸ごと無効 |
| 子に同じ量の padding を持たせる | `.metric-lines` | 単純なクラスセレクタなので全ブラウザで確実に効く |

**採用は後者。** 内容の高さ +1rem、外側マージン −1rem で相殺され、
マージンボックスの高さは `:has()` 版とまったく同じになる。

```css
.metric-lines{ display:block; padding-bottom:1rem; }
```

## 詳細

### 使い方

`st.columns` のカラムに複数行の生HTMLを出すときは、必ず外側の div に
`class="metric-lines"` を付ける。

```python
col.markdown(
    '<div class="metric-lines" style="line-height:1.15">'
    '<div style="...">売上（税込）</div>'
    '<div style="...">¥1,234,567</div></div>',
    unsafe_allow_html=True)
```

### やってはいけないこと

- `.metric-lines` の div に `margin-bottom` / `padding-bottom` を
  **インラインstyleで書かない**。CSSより後勝ちするので相殺が壊れ、同じバグが再発する。
- 打ち消しを `:has()` に戻さない。iPhoneで直っていないのに直ったつもりになる。

### 相殺量が 1rem である根拠

Streamlit 1.58 の `index.*.js` 内、markdown コンテナの styled component が
`marginBottom: r||i ? '' : '-${e.spacing.lg}'`（`spacing.lg` = 1rem）を持つ。
Streamlit を上げたときにこの値が変わったら、`.metric-lines` の padding も合わせること。

## 再発防止

| 何を守るか | どのテストが守るか |
|---|---|
| サマリー3項目すべてに `metric-lines` が付いている | `tests/test_rev6_issue.py::test_issue_summary_metrics_have_overlap_fix_marker` |
| 相殺が `:has()` に依存していない | `tests/test_rev6_issue.py::test_overlap_fix_does_not_depend_on_has_pseudo_class` |
| インラインstyleで相殺を壊していない | `tests/test_rev6_issue.py::test_metric_lines_blocks_do_not_carry_inline_margin_that_reopens_the_gap` |

### 経緯から得た教訓（2026-08-27）

2026-08-20 に `:has()` 版で修正したが、大橋様の画面では直っていなかった。
真因は **10コミットがGitHubにpushされておらず、Streamlit Cloud の公開デモが
8/20より前の古いコードのままだった**こと。CSSの問題ではなかった。

- **「直したのに直っていない」と言われたら、まず相手が見ているコードが
  本当に自分の直したコードかを確認する。** `git log origin/<branch>..HEAD` が空かを見る。
- そのうえで、CSSの新しい仕様（`:has()` など）に単独で依存しない実装を選ぶ。
  端末が古いと修正そのものが無効になり、原因の切り分けが二重に難しくなる。
