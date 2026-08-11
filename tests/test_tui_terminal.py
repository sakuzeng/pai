"""T8：终端生命周期 —— 非 tty 闸门、resize、复原、主线程断言。"""

import signal
import threading

import pytest

from pai.tui.terminal import (
    DISABLE_BRACKETED_PASTE,
    SHOW_CURSOR,
    TerminalSession,
    tui_available,
)


class FakeStream:
    def __init__(self, tty=True):
        self._tty = tty
        self.written = []

    def isatty(self):
        return self._tty

    def write(self, data):
        self.written.append(data)

    def flush(self):
        pass


def make(size=(80, 24), **kw):
    stream = FakeStream()
    box = {"size": size, "raw": 0, "signals": []}

    def enter_raw():
        box["raw"] += 1
        return "saved"

    def exit_raw(saved):
        box["raw"] -= 1
        box["restored"] = saved

    def install(sig, handler):
        box["signals"].append((sig, handler))
        return "previous"

    session = TerminalSession(stream=stream, enter_raw=enter_raw, exit_raw=exit_raw,
                              size=lambda: box["size"], install_signal=install, **kw)
    return session, stream, box


# --- 非 tty 闸门 -------------------------------------------------------

def test_tui_is_unavailable_when_stdout_is_not_a_tty():
    """判 stdout（能不能画）不是 stdin——与 CC 同口径。"""
    assert tui_available(FakeStream(tty=False)) is False
    assert tui_available(FakeStream(tty=True)) is True


def test_env_var_is_an_explicit_escape_hatch(monkeypatch):
    monkeypatch.setenv("PAI_NO_TUI", "1")
    assert tui_available(FakeStream(tty=True)) is False


# --- resize ------------------------------------------------------------

def test_same_size_resize_event_is_dropped():
    """终端一次用户操作常发 2 次以上事件，每次都重画等于白闪一遍。"""
    calls = []
    session, _, box = make(on_resize=lambda: calls.append(1))
    assert session.handle_resize() is False
    assert calls == []


def test_changed_size_triggers_a_redraw_synchronously():
    calls = []
    session, _, box = make(on_resize=lambda: calls.append(1))
    box["size"] = (40, 24)
    assert session.handle_resize() is True
    assert calls == [1]
    assert session.columns == 40


def test_sigwinch_handler_is_installed_on_start():
    session, _, box = make()
    session.start()
    assert signal.SIGWINCH in [sig for sig, _ in box["signals"]]
    session.stop()


# --- 生命周期 ----------------------------------------------------------

def test_start_enters_raw_mode_and_enables_bracketed_paste():
    session, stream, box = make()
    session.start()
    assert box["raw"] == 1
    assert any("2004h" in w for w in stream.written)
    session.stop()


def test_stop_restores_everything_unconditionally():
    session, stream, box = make()
    session.start()
    session.stop()
    assert box["raw"] == 0
    assert DISABLE_BRACKETED_PASTE in "".join(stream.written)
    assert SHOW_CURSOR in "".join(stream.written)


def test_stop_still_restores_raw_mode_when_writing_fails():
    """写终端失败也不能跳过复原——把用户终端留在 raw mode 是不可接受的。"""
    session, stream, box = make()
    session.start()
    stream.write = lambda *_: (_ for _ in ()).throw(OSError("broken pipe"))
    session.stop()
    assert box["raw"] == 0


def test_context_manager_restores_on_exception():
    session, _, box = make()
    with pytest.raises(RuntimeError):
        with session:
            raise RuntimeError("炸了")
    assert box["raw"] == 0


def test_double_stop_is_harmless():
    session, _, box = make()
    session.start()
    session.stop()
    session.stop()
    assert box["raw"] == 0


# --- 主线程断言 --------------------------------------------------------

def test_non_main_thread_warns_instead_of_failing_silently():
    """05 遗留：`_install_sigint` 在非主线程静默退化为不可中断。这条让它出声。"""
    captured = {}

    def run():
        session, _, box = make()
        session.start()
        captured["warnings"] = list(session.warnings)
        captured["signals"] = list(box["signals"])
        session.stop()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert captured["warnings"], "非主线程必须留下告警"
    assert "主线程" in captured["warnings"][0]
    assert captured["signals"] == []      # 装不上就是装不上，不假装


def test_main_thread_produces_no_warning():
    session, _, _ = make()
    session.start()
    assert session.warnings == []
    session.stop()
