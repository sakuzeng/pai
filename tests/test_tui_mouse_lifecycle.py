"""鼠标模式的进出与开关（feature 16 T8）。

**鼠标模式泄漏到 shell 里比留在备用屏还烦**：用户回到 shell 后鼠标失灵、
点哪儿都没反应，而且看不出是谁干的。所以复原路径的测试比进入路径重要。
"""

import json

import pytest

from pai.core.settings import load_settings, mouse_enabled
from pai.tui.terminal import TerminalSession


class FakeStream:
    def __init__(self):
        self.data = ""

    def write(self, text):
        self.data += text

    def flush(self):
        pass

    def isatty(self):
        return True


def _session(stream, **kw):
    return TerminalSession(stream=stream, enter_raw=lambda: "saved",
                           exit_raw=lambda saved: None, size=lambda: (80, 24),
                           install_signal=lambda sig, handler: None, **kw)


def test_mouse_tracking_is_enabled_after_entering_alt_screen():
    out = FakeStream()
    _session(out, alt_screen=True, mouse=True).start()
    for mode in ("1002", "1006"):
        assert f"\x1b[?{mode}h" in out.data
    assert out.data.index("\x1b[?1049h") < out.data.index("\x1b[?1006h")


def test_we_ask_for_1002_not_1003():
    """**2026-08-11 复议了「照抄 CC 发 1003」这条拍板**，理由是实测：

    ① 1003 确实上报**无按键移动**（鼠标划过窗口就有字节流进来），
       而且它直接带出过一个 bug（把无按键移动当成拖动，松手后高亮还跟着走）；
    ② 它多买的那个 hover 高亮**本轮是非目标**，也就是白付。
    1002 给的是「按键 + 拖动 + 滚轮」，正好是选区与点击需要的全部。
    """
    out = FakeStream()
    _session(out, alt_screen=True, mouse=True).start()
    assert "\x1b[?1003h" not in out.data
    assert "\x1b[?1000h" not in out.data      # 1002 已含按下/松开，不必再发


def test_mouse_tracking_is_disabled_before_leaving_alt_screen():
    """照 CC 的 `gracefulShutdown`：**先关鼠标**，终端需要一个往返才停止发送事件。
    顺序反了的话，事件在恢复 cooked 模式期间到达，会回显到屏幕上或漏进 shell。"""
    out = FakeStream()
    session = _session(out, alt_screen=True, mouse=True)
    session.start()
    session.stop()
    assert out.data.index("\x1b[?1006l") < out.data.index("\x1b[?1049l")


def test_every_enabled_mode_is_disabled_again():
    out = FakeStream()
    session = _session(out, alt_screen=True, mouse=True)
    session.start()
    session.stop()
    for mode in ("1002", "1006"):
        assert f"\x1b[?{mode}l" in out.data


def test_mouse_is_restored_even_when_the_body_raises():
    out = FakeStream()
    with pytest.raises(RuntimeError):
        with _session(out, alt_screen=True, mouse=True):
            raise RuntimeError("界面代码炸了")
    assert "\x1b[?1006l" in out.data


def test_mouse_off_sends_no_mouse_sequences_at_all():
    out = FakeStream()
    session = _session(out, alt_screen=True, mouse=False)
    session.start()
    session.stop()
    assert "?1000" not in out.data and "?1002" not in out.data
    assert "?1003" not in out.data and "?1006" not in out.data
    assert "\x1b[?1049h" in out.data          # 备用屏照旧


def test_no_alt_screen_means_no_mouse():
    """main-screen 下 pai 不拥有屏幕，接管鼠标只会把终端原生的选中复制白白弄坏。"""
    out = FakeStream()
    session = _session(out, alt_screen=False, mouse=True)
    session.start()
    session.stop()
    assert "?1006" not in out.data


def _write_settings(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_mouse_defaults_to_on(tmp_path):
    assert mouse_enabled(load_settings(cwd=str(tmp_path), home=str(tmp_path / "h"))) is True


def test_mouse_can_be_turned_off_in_settings(tmp_path):
    project = tmp_path / "proj"
    _write_settings(project / ".pai" / "settings.json", {"tui": {"mouse": False}})
    settings = load_settings(cwd=str(project), home=str(tmp_path / "h"))
    assert mouse_enabled(settings) is False


def test_non_boolean_falls_back_and_warns(tmp_path):
    project = tmp_path / "proj"
    _write_settings(project / ".pai" / "settings.json", {"tui": {"mouse": "yes"}})
    warnings = []
    settings = load_settings(cwd=str(project), home=str(tmp_path / "h"))
    assert mouse_enabled(settings, warn=warnings.append) is True
    assert warnings and "mouse" in warnings[0]
