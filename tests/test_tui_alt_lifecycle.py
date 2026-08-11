"""进出备用屏 + 开关（feature 13 T5）。

alt-screen 独有的失败模式是「程序没了，屏幕还在备用屏里」——用户看到一个空屏、
打字没回显、也不知道发生了什么。main-screen 下最坏只是留个乱掉的 dock。
所以复原路径的测试比进入路径重要。
"""

import json

import pytest

from pai.core.settings import alt_screen_enabled, load_settings
from pai.tui.terminal import TerminalSession


class FakeStream:
    def __init__(self) -> None:
        self.data = ""

    def write(self, text: str) -> None:
        self.data += text

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return True


def _session(stream, **kw):
    return TerminalSession(
        stream=stream,
        enter_raw=lambda: "saved",
        exit_raw=lambda saved: None,
        size=lambda: (80, 24),
        install_signal=lambda sig, handler: None,
        **kw,
    )


def test_entering_alt_screen_sends_the_whole_preamble():
    out = FakeStream()
    _session(out, alt_screen=True).start()
    assert "\x1b[?1049h" in out.data          # 进备用屏
    assert "\x1b[?7l" in out.data             # 关自动折行（超宽行不许糟蹋下一行）
    assert "\x1b[2J" in out.data              # 只有**这一次**允许清屏
    assert "\x1b[H" in out.data
    assert "\x1b[?25l" in out.data


def test_alt_screen_is_entered_before_any_frame_is_written():
    """CC 的教训：顺序反了，那一帧留在主屏上，**退出之后**才作为脏东西暴露。"""
    out = FakeStream()
    session = _session(out, alt_screen=True)
    session.start()
    out.write("第一帧的内容")
    assert out.data.index("\x1b[?1049h") < out.data.index("第一帧的内容")


def test_leaving_alt_screen_restores_everything():
    out = FakeStream()
    session = _session(out, alt_screen=True)
    session.start()
    session.stop()
    tail = out.data[out.data.index("\x1b[?1049h") + 8:]
    assert "\x1b[?7h" in tail                 # 折行还回去
    assert "\x1b[?25h" in tail                # 光标还回去
    assert "\x1b[?1049l" in tail              # 屏幕还回去


def test_exit_alt_comes_after_re_enabling_autowrap():
    """`?1049l` 之后写的东西落在**主屏**上——复原序列要赶在它前面。"""
    out = FakeStream()
    session = _session(out, alt_screen=True)
    session.start()
    session.stop()
    assert out.data.index("\x1b[?7h") < out.data.index("\x1b[?1049l")


def test_restores_alt_screen_even_when_the_body_raises():
    out = FakeStream()
    with pytest.raises(RuntimeError):
        with _session(out, alt_screen=True):
            raise RuntimeError("界面代码炸了")
    assert "\x1b[?1049l" in out.data


def test_stop_is_idempotent():
    out = FakeStream()
    session = _session(out, alt_screen=True)
    session.start()
    session.stop()
    session.stop()
    assert out.data.count("\x1b[?1049l") == 1


def test_alt_screen_off_sends_no_alt_sequences_at_all():
    out = FakeStream()
    session = _session(out, alt_screen=False)
    session.start()
    session.stop()
    assert "?1049" not in out.data
    assert "?7l" not in out.data


def test_stop_still_restores_the_terminal_when_a_write_fails():
    class Broken(FakeStream):
        def write(self, text):
            raise OSError("管道断了")

    restored = []
    session = TerminalSession(
        stream=Broken(), alt_screen=True,
        enter_raw=lambda: "saved",
        exit_raw=lambda saved: restored.append(saved),
        size=lambda: (80, 24),
        install_signal=lambda sig, handler: None,
    )
    session.started = True
    session.stop()
    assert restored == [None] or restored == ["saved"]


# --- settings 开关 --------------------------------------------------------


def _write_settings(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_alt_screen_defaults_to_on(tmp_path):
    settings = load_settings(cwd=str(tmp_path), home=str(tmp_path / "home"))
    assert alt_screen_enabled(settings) is True


def test_project_settings_can_turn_alt_screen_off(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    _write_settings(project / ".pai" / "settings.json", {"tui": {"altScreen": False}})
    settings = load_settings(cwd=str(project), home=str(home))
    assert alt_screen_enabled(settings) is False


def test_project_layer_overrides_the_user_layer(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    _write_settings(home / ".pai" / "settings.json", {"tui": {"altScreen": False}})
    _write_settings(project / ".pai" / "settings.json", {"tui": {"altScreen": True}})
    settings = load_settings(cwd=str(project), home=str(home))
    assert alt_screen_enabled(settings) is True


def test_non_boolean_value_warns_and_falls_back(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    _write_settings(project / ".pai" / "settings.json", {"tui": {"altScreen": "yes"}})
    warnings = []
    settings = load_settings(cwd=str(project), home=str(home))
    # 校验挂在**解释这个值的地方**，不挂在读文件的地方——读的人不知道每个键该是什么类型
    assert alt_screen_enabled(settings, warn=warnings.append) is True   # 退回默认，不炸
    assert warnings and "altScreen" in warnings[0]


def test_broken_json_does_not_take_down_the_ui(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    path = project / ".pai" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ 这不是 JSON", encoding="utf-8")
    warnings = []
    settings = load_settings(cwd=str(project), home=str(home), warn=warnings.append)
    assert alt_screen_enabled(settings) is True
    assert warnings
