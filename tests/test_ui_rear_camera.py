"""小口のカメラを外カメラ(背面)で起動する(2026-08-27・大橋様ご指摘)。

st.camera_input はネイティブに facingMode を指定できない。ブラウザは何も
指定されないと内カメラ(前面)を選ぶことが多く、レシートを撮るのに毎回
切り替えが要る。親documentの navigator.mediaDevices.getUserMedia を
差し替えて facingMode:"environment" を足すことで、Streamlit本体に手を
入れずに背面カメラを既定にする。
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from common import ui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return ui._REAR_CAMERA_JS.replace(" ", "")


def test_js_patches_get_user_media_with_environment_facing_mode():
    js = _js()
    assert "getUserMedia" in js
    assert 'facingMode' in js
    assert '"environment"' in js or "'environment'" in js


def test_js_uses_ideal_not_exact_so_pcs_without_a_rear_camera_still_work():
    """🔴 exact:"environment" にすると背面カメラが無いPCで
    OverconstrainedError になり、カメラがまったく起動しなくなる。
    「パソコン・スマホ両方で外カメラ」という依頼だが、PCは1台しかカメラが
    無いのが普通なので、必ず ideal(希望)にして落ちないようにする。"""
    js = _js()
    assert "ideal:" in js
    assert "exact:" not in js


def test_js_does_not_override_an_explicitly_chosen_device():
    """Streamlitのカメラ切り替えで deviceId を指定してきたときは、
    こちらの facingMode で上書きしない(ユーザーの選択が効かなくなるため)。"""
    assert "deviceId" in _js()


def test_js_is_idempotent_so_reruns_do_not_stack_patches():
    """Streamlitは操作のたびにスクリプトを再実行する。毎回 getUserMedia を
    包み直すと入れ子が積み上がる。二重適用を防ぐ印を持つこと。"""
    js = _js()
    assert "Patched" in js or "patched" in js


def test_js_touches_the_parent_document_not_the_iframe():
    """components.html は iframe。カメラを使うのは親ページ側なので、
    親の navigator を差し替える必要がある。"""
    assert "window.parent" in _js()


def test_force_environment_camera_emits_the_patch(monkeypatch):
    calls = []
    monkeypatch.setattr(ui.components, "html", lambda html, **kw: calls.append(html))
    ui.force_environment_camera()
    assert any("getUserMedia" in c for c in calls)


def test_petty_page_installs_the_patch_before_the_camera_is_used(monkeypatch):
    """🔴 実際に 01 のページを動かして、パッチが仕込まれることを確かめる。
    ソースに関数呼び出しが書いてあるだけでは「カメラを開く前に効いているか」を
    保証できないため、ページを走らせて components.html の中身を見る。"""
    calls = []
    monkeypatch.setattr(ui.components, "html", lambda html, **kw: calls.append(html))
    at = AppTest.from_file(os.path.join(ROOT, "pages", "01_経費・買掛・売掛.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception
    assert any("getUserMedia" in c and "environment" in c for c in calls), \
        "小口ページで外カメラのパッチが仕込まれていない"
