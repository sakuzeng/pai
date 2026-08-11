"""工具调用状态行：把一串工具事件压成一行「◐ 进行中 | ✓ 已完成 ×N」。

来源是 CC 的状态行（用户截图，取舍表见 features/05-20260810-repl/README.md）：
进行中的单独展开带参数预览排在前，已完成的按工具名折叠计数。pai 一次只跑一个工具，
所以「多个 ◐ 并列」不做——那是并发（阶段 5）的事。

`render_tool_line` 是**纯函数**（events, width) -> str，不碰终端句柄：
这与 roadmap 已拍板的 TUI 设计原则 1（`Component.render(width) -> list[str]`）同构，
TUI 阶段直接复用；副作用（原地刷新）隔离在 StatusLinePrinter 里。
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from typing import Callable, Iterable, List, Optional

from pai.core.events import AgentEvent, ToolEnd, ToolStart

RUNNING, DONE, FAILED = "◐", "✓", "✗"
SEPARATOR = " | "
ELLIPSIS = "…"

DIM = "\x1b[2m"
CYAN = "\x1b[36m"
RED = "\x1b[31m"
RESET = "\x1b[0m"


# 转义序列不占列。三类都要认：
#   CSI  \x1b[...字母      颜色、光标移动
#   OSC  \x1b]...\x07      超链接
#   APC  \x1b_...\x07      TUI 的 CURSOR_MARKER（pai.tui.component）
# 状态行自己撞不上（它先按可见文本截断再上色），但 TUI 组件会把 CURSOR_MARKER
# 嵌进文本里——宽度算错，硬件光标就摆错列，中文 IME 候选框跟着漂。
# pi 的 visibleWidth 同样显式处理 APC（K source-walks/pi-tui-main-screen.md 第六节）。
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[\]_][^\x07]*\x07")


def display_width(text: str) -> int:
    """终端列宽，不是字符数：东亚宽字符（W/F）占两列，转义序列占零列。

    按 len() 截断的话，一行中文会实际占掉两倍宽度把终端撑破行——这是中文终端 UI
    最常见的一个坑，也是本模块唯一真正需要动脑的地方。
    """
    visible = _ESCAPES.sub("", text)
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in visible)


def _truncate(text: str, width: int) -> str:
    """按列宽截断并留出省略号的位置。"""
    if display_width(text) <= width:
        return text
    if width <= 1:
        return ELLIPSIS[:width]
    kept: List[str] = []
    used = 0
    for char in text:
        w = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if used + w > width - 1:            # 给 ELLIPSIS 留一列
            break
        kept.append(char)
        used += w
    return "".join(kept) + ELLIPSIS


def _preview(args: dict) -> str:
    if not args:
        return ""
    first = next(iter(args.values()))
    return str(first)


def render_tool_line(events: Iterable[AgentEvent], width: int, *, color: bool = False) -> str:
    """进行中的排在前（带参数预览），已完成的按工具名折叠计数。"""
    running: dict = {}                       # tool_call_id -> (name, 预览)
    done: List[tuple] = []                   # [(name, is_error)]，保持首次出现顺序
    for event in events:
        if isinstance(event, ToolStart):
            running[event.tool_call_id] = (event.name, _preview(event.args))
        elif isinstance(event, ToolEnd):
            running.pop(event.tool_call_id, None)
            done.append((event.name, event.is_error))

    # (可见文本, 颜色) 分开存：宽度只能按可见文本算，ANSI 转义符不占列——
    # 拿带转义符的串去量宽度是彩色终端 UI 的第二个经典坑（第一个是中文宽度）
    parts: List[tuple] = []
    for name, preview in running.values():
        head = f"{RUNNING} {name}"
        parts.append((f"{head}: {preview}" if preview else head, CYAN))

    counts: dict = {}
    for name, is_error in done:
        key = (name, is_error)
        counts[key] = counts.get(key, 0) + 1
    for (name, is_error), count in counts.items():
        mark = FAILED if is_error else DONE
        text = f"{mark} {name}" + (f" ×{count}" if count > 1 else "")
        parts.append((text, RED if is_error else DIM))

    if not parts:
        return ""
    return _join_within_width(parts, width, color)


def _join_within_width(parts: List[tuple], width: int, color: bool) -> str:
    """按可见宽度拼接：装不下的整段丢掉，最后一段放得下一半就截它。"""
    rendered: List[str] = []
    used = 0
    for text, code in parts:
        cost = display_width(text) + (len(SEPARATOR) if rendered else 0)
        if used + cost <= width:
            rendered.append(_paint(text, code, color))
            used += cost
            continue
        remaining = width - used - (len(SEPARATOR) if rendered else 0)
        if remaining > 1:
            rendered.append(_paint(_truncate(text, remaining), code, color))
        break                                # 后面的整段丢掉，不留半截转义符
    return SEPARATOR.join(rendered)


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


class StatusLinePrinter:
    """单行原地刷新。不需要 alt-screen——`\\r` + 清行就够，滚动仍交给终端。

    非 tty（管道、测试、CI）或设了 NO_COLOR 时自动退化为不输出/不上色，
    否则日志里会塞满转义符。
    """

    def __init__(self, *, stream=None, enabled: Optional[bool] = None,
                 width: Callable[[], int] = lambda: os.get_terminal_size().columns) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._events: List[AgentEvent] = []
        if enabled is None:
            enabled = bool(getattr(self._stream, "isatty", lambda: False)())
        self.enabled = enabled
        self._width = width
        self._color = enabled and not os.environ.get("NO_COLOR")

    def handle(self, event: AgentEvent) -> None:
        if not isinstance(event, (ToolStart, ToolEnd)):
            return
        self._events.append(event)
        if not self.enabled:
            return
        try:
            columns = self._width()
        except OSError:
            columns = 80
        line = render_tool_line(self._events, columns, color=self._color)
        self._stream.write("\r\x1b[K" + line)
        self._stream.flush()

    def clear(self) -> None:
        self._events = []
        if self.enabled:
            self._stream.write("\r\x1b[K")
            self._stream.flush()
