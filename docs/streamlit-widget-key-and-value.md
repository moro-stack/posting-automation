# キー付きウィジェットに初期値を入れるときの決まり（Streamlit）

## 概要

`st.text_input(..., value=X, key="k")` のように **`key` と `value` を両方** 渡すと、
一度描画されたあとは `value` が無視され、`st.session_state["k"]` の値が使われる。

2026-08-28 のバグ（AIが読み取ったレシートの金額が0円・日付が空のまま）は、
これを知らずに `key=` を後付けしたことが原因だった。

## 設計・方針

**フォームの値の持ち主は1つに揃える。** `key` を付けたウィジェットでは
`value=` を使わず、初期値も更新も `st.session_state[key]` に書く。

```python
# ✗ 効かない（一度描画されたあとは value が無視される）
st.text_input("日付", value=draft.get("date") or "", key="petty_date")

# ✓ ウィジェットを描くより前に session_state へ書く
st.session_state["petty_date"] = draft.get("date") or ""
...
st.text_input("日付", key="petty_date")
```

## 詳細

### 書き込む順番

`st.session_state[key]` はそのキーのウィジェットが**生成される前**にしか書き換えられない。
生成後に代入すると `StreamlitAPIException` になる。
AIの読み取り結果を反映する処理は、必ず `st.form(...)` ブロックより前に置く。

`pages/01_経費・買掛・売掛.py` の `_apply_draft()` がその受け口。
下書きを一度だけ反映するため、読み終わったら置き場（`petty_draft` など）を消す。

### `clear_on_submit=True` との関係

フォーム送信後、キー付きウィジェットは**その時点の既定値**に戻る。
`value=` を渡していなければ、既定は `text_input` なら空文字、
`number_input` なら `min_value` になる。狙いどおり「入力欄が空に戻る」。

### 一度描画されたか、を意識する

初回描画だけを試すテストではこのバグは出ない。
**「描画 → 値をセット → 再描画」** の2ステップで確かめること。

```python
at.run()                                  # 1回目: ウィジェットが session_state に載る
at.session_state["petty_draft"] = {...}   # AI読み取りが返ってきた状態
at.run()                                  # 2回目: ここで反映されるかを見る
```

## 再発防止

| 何を守るか | どのテストが守るか |
|---|---|
| 小口: AIの下書きがフォームに入る | `tests/test_pages_ocr_draft.py::test_petty_ocr_draft_lands_in_the_form` |
| 小口: 読み取った金額のまま登録できる | `tests/test_pages_ocr_draft.py::test_petty_ocr_draft_can_be_registered_as_read` |
| 買掛: 同じ経路が壊れていない | `tests/test_pages_ocr_draft.py::test_payable_ocr_draft_lands_in_the_form` |
| 2枚目の読み取りが1枚目を上書きする | `tests/test_pages_ocr_draft.py::test_petty_second_ocr_overwrites_the_first_draft` |
| 人が直した値が下書きに勝つ | `tests/test_pages_ocr_draft.py::test_petty_user_edit_wins_over_the_draft` |

### 教訓

- **テストのために `key=` を足すのは、動作を変える変更**である。
  「テスト用だから安全」と思って追加したものが本番の挙動を壊した。
  `key` を足したら、その画面の `value=` が死んでいないか必ず確かめる。
- 「AIが読めていない」と報告されたら、**AIの応答そのものを先に見る**。
  今回は `common/ocr.py` は 900円・2015-02-12 を正しく返しており、
  壊れていたのは画面側だった。入口から順に切り分ければ最初の5分で分かる。
