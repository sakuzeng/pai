"""终端生命周期：进出 raw mode、resize、退出复原。唯一有系统副作用的另一半。

三条都是**从别人的事故里抄来的**：

1. **非 tty 就整个不进 TUI**，判的是 **stdout**（能不能画）不是 stdin——同 CC 的
   `!process.stdout.isTTY`（K cc-input-ownership-and-modes.md 第六节）。
2. **resize 同步处理、同尺寸事件丢弃**：CC 的 `handleResize` 顶着一段注释说明为什么
   刻意不去抖（去抖会开一个「尺寸已新、内部记录还旧」的窗口，造成双重闪烁），
   以及终端一次用户操作常发 2 次以上 resize 事件。
3. **退出时无条件复原**：不做终端能力检测——CC 的理由是检测不可靠，
   不支持的终端上这些序列是 no-op。异常逃逸把用户终端留在 raw mode 是不可接受的。
"""

from __future__ import annotations

import os
import signal
import sys
import threading
from typing import Callable, Optional

ENABLE_BRACKETED_PASTE = "\x1b[?2004h"
DISABLE_BRACKETED_PASTE = "\x1b[?2004l"
SHOW_CURSOR = "\x1b[?25h"
HIDE_CURSOR = "\x1b[?25l"
# 进备用屏：存光标 + 切过去 + **清空它**（清空是 DECSET 1049 定义的一部分）。
# 全仓库**只有这里**允许发 `2J`：此刻屏幕本来就是空的，擦不掉任何东西。
ENTER_ALT_SCREEN = "\x1b[?1049h\x1b[?7l\x1b[2J\x1b[H" + HIDE_CURSOR
# 出来的顺序不能反：`?1049l` 之后写的东西落在**主屏**上，
# 复原序列必须赶在它前面，否则等于往用户的 shell 屏幕上吐控制字符。
EXIT_ALT_SCREEN = SHOW_CURSOR + "\x1b[?7h\x1b[?1049l"
# 鼠标上报：**只发 1002 + 1006**。
#
# CC 发的是四条（`termio/dec.ts` 的 ENABLE_MOUSE_TRACKING：1000+1002+1003+1006），
# 而实测 **1000/1002/1003 是互斥单选、只有最后一条生效**（features/13 evidence 第 3 条），
# 所以 CC 实际拿到的是 1003「任何移动都上报」。
#
# pai 2026-08-11 **复议了「照抄 CC」这条拍板**，降到 1002，理由是两条实测：
# ① 1003 确实上报无按键移动——鼠标划过窗口就有字节不断流进 stdin，
#    而且它直接带出过一个 bug（无按键移动被当成拖动，松手后高亮还跟着鼠标走）；
# ② 它多买的 hover 高亮**本轮是非目标**，等于白付。
# 1002 给的是「按下/松开 + 拖动 + 滚轮」，正好是选区与点击需要的全部；
# 1006 是正交的**编码**开关（SGR），与它并存。
ENABLE_MOUSE = "\x1b[?1002h\x1b[?1006h"
DISABLE_MOUSE = "\x1b[?1006l\x1b[?1002l"


def tui_available(stream=None) -> bool:
    """能不能进 TUI。判 stdout：画不出来就别装。

    `PAI_NO_TUI=1` 是显式逃生口（终端行为诡异时用户得有办法退回纯 REPL）。
    """
    if os.environ.get("PAI_NO_TUI"):
        return False
    stream = stream if stream is not None else sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def in_main_thread() -> bool:
    """信号处理器只有主线程装得上。

    05 遗留：`_install_sigint` 在非主线程静默退化为「不可中断」——本轮的结论是
    **不把 REPL 挪到子线程**，并让这条假设**被违反时会响**，而不是等中断静默失效。
    """
    return threading.current_thread() is threading.main_thread()


class TerminalSession:
    """raw mode + SIGWINCH 的持有者。所有系统调用都可注入，于是离线可测。"""

    def __init__(self, *, stream=None, on_resize: Optional[Callable[[], None]] = None,
                 alt_screen: bool = False, mouse: bool = False,
                 enter_raw: Optional[Callable[[], object]] = None,
                 exit_raw: Optional[Callable[[object], None]] = None,
                 size: Optional[Callable[[], tuple]] = None,
                 install_signal: Optional[Callable[[int, Callable], object]] = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._on_resize = on_resize
        self.alt_screen = alt_screen
        # 鼠标只在备用屏下有意义：main-screen 下 pai 不拥有屏幕，
        # 接管鼠标只会把终端原生的选中复制白白弄坏
        self.mouse = mouse and alt_screen
        self._enter_raw = enter_raw or _default_enter_raw
        self._exit_raw = exit_raw or _default_exit_raw
        self._size = size or _default_size
        self._install_signal = install_signal or signal.signal
        self._saved = None
        self._previous_winch = None
        self._columns, self._rows = self._size()
        self.started = False
        self.warnings: list = []

    # --- 尺寸 ---------------------------------------------------------

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    def handle_resize(self, *_args) -> bool:
        """返回「尺寸真的变了吗」。

        **同尺寸事件直接丢弃**：终端一次用户操作常发 2 次以上事件，
        每次都重画等于白闪一遍。
        """
        columns, rows = self._size()
        if (columns, rows) == (self._columns, self._rows):
            return False
        self._columns, self._rows = columns, rows
        if self._on_resize is not None:
            self._on_resize()
        return True

    # --- 生命周期 -----------------------------------------------------

    def start(self) -> None:
        if self.started:
            return
        if not in_main_thread():
            # 静默退化是 05 的老毛病，这里必须出声
            self.warnings.append(
                "TUI 不在主线程：resize 与中断都装不上处理器，会静默失效。"
                "pai 的线程模型是「主线程持有 stdin、信号与 loop」，别把 REPL 挪到子线程。")
        else:
            self._previous_winch = self._install_signal(signal.SIGWINCH, self.handle_resize)
        self._saved = self._enter_raw()
        # 进备用屏必须**早于第一帧**。CC 的教训（AlternateScreen.tsx 用
        # useInsertionEffect 而不是 useLayoutEffect 的那段注释）：顺序反了的话，
        # 第一帧被画在主屏上并保存下来，**退出 alt 之后**才作为一个坏掉的视图出现。
        preamble = ENABLE_BRACKETED_PASTE + (ENTER_ALT_SCREEN if self.alt_screen else "")
        if self.mouse:
            preamble += ENABLE_MOUSE
        self._stream.write(preamble)
        self._stream.flush()
        self.started = True

    def stop(self) -> None:
        """复原。**无条件发**，且每一步都不许因为前一步失败而跳过。"""
        if not self.started:
            return
        self.started = False
        try:
            # **先关鼠标**：终端需要一个往返才停止发送事件。放在退备用屏之后的话，
            # 事件会在恢复 cooked 模式期间到达——回显到屏幕上，或者漏进 shell
            # （照 CC 的 `gracefulShutdown`，它把这条写在注释里）。
            restore = (DISABLE_MOUSE if self.mouse else "")
            restore += DISABLE_BRACKETED_PASTE + SHOW_CURSOR
            if self.alt_screen:
                restore += EXIT_ALT_SCREEN
            self._stream.write(restore)
            self._stream.flush()
        except Exception:                      # noqa: BLE001 - 退出路径不许再抛
            pass
        try:
            self._exit_raw(self._saved)
        except Exception:                      # noqa: BLE001
            pass
        if self._previous_winch is not None:
            try:
                self._install_signal(signal.SIGWINCH, self._previous_winch)
            except Exception:                  # noqa: BLE001
                pass

    def __enter__(self) -> "TerminalSession":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()


def _default_enter_raw():
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setraw(fd)
    return (fd, saved)


def _default_exit_raw(saved) -> None:
    import termios

    if saved is None:
        return
    fd, attrs = saved
    termios.tcsetattr(fd, termios.TCSADRAIN, attrs)


def _default_size() -> tuple:
    try:
        size = os.get_terminal_size()
        return (size.columns, size.lines)
    except OSError:
        return (80, 24)
