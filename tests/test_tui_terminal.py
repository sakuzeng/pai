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


def test_changed_size_defers_the_redraw_to_the_main_loop():
    """feature 19 拍板问 3 改了这条：处理器只置标志，重画交给主循环。

    原来这里叫 `..._triggers_a_redraw_synchronously`，断言 `calls == [1]`——
    那是 feature 12 拍的「同步处理」。同步本身就是 R4#12 的根因（信号打在
    一帧写到一半的位置 → 字节交错，或撞上 buffered IO 抛
    `RuntimeError: reentrant call` 掀掉整个 TUI）。
    **改的只是「同步」这一半，「不去抖」与「同尺寸丢弃」照旧。**
    """
    calls = []
    session, _, box = make(on_resize=lambda: calls.append(1))
    box["size"] = (40, 24)

    assert session.handle_resize() is True
    assert calls == [], "处理器不许画"
    assert session.columns == 40

    assert session.take_resize_pending() is True
    session.redraw_after_resize()
    assert calls == [1], "主循环取走标志之后才画"


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


# ---- feature 19 T4：SIGWINCH 处理器只置标志（2026-08-19，拍板问 3 方案 A）----


def test_the_signal_handler_does_not_draw():
    """处理器里同步写 stdout 是 R4#12 的根因。

    两条后果：DockRenderer 没有 `AltScreenRenderer` 那样的重入门，信号打在
    一帧写到一半的位置会让两帧字节交错、`_height`/`_cursor_offset` 被重入改写，
    dock 永久漂移；更硬的一刀是主线程正处在 `sys.stdout.write` 内部时处理器
    再写同一 stream，Python 的 buffered IO 会抛 `RuntimeError: reentrant call`，
    而 TUI 的大 try 只有 finally 没有 except，异常直接掀掉整个 TUI。

    feature 12 当时拍的是「同步处理、同尺寸丢弃」（对齐 CC 的不去抖）。
    本轮只改「同步」这一半——**不去抖照旧**，同尺寸丢弃也照旧。
    """
    drawn: list = []
    sizes = iter([(80, 24), (100, 30)])
    session = TerminalSession(on_resize=lambda: drawn.append("draw"),
                              size=lambda: next(sizes))

    changed = session.handle_resize()

    assert changed is True
    assert drawn == [], "处理器不许画，只许置标志"
    assert session.resize_pending is True


def test_taking_the_pending_flag_clears_it():
    """标志由主循环取走：取一次就该清掉，否则每个 poll 周期都白重画一遍。"""
    sizes = iter([(80, 24), (100, 30)])
    session = TerminalSession(size=lambda: next(sizes))
    session.handle_resize()

    assert session.take_resize_pending() is True
    assert session.take_resize_pending() is False


def test_a_same_size_event_still_sets_nothing():
    """同尺寸丢弃是 feature 12 拍板的，本轮不动它。"""
    session = TerminalSession(size=lambda: (80, 24))

    assert session.handle_resize() is False
    assert session.resize_pending is False
