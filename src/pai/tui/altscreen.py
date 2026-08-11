"""备用屏渲染器：pai 拥有整个屏幕时，每帧长什么样。

**与 `DockRenderer` 的分工**（feature 13）：
- `DockRenderer`：只拥有屏幕底部若干行，靠**相对**光标移动重画，上面归终端；
- 本模块：拥有全部 `rows` 行，靠**绝对**坐标（`CSI r;1H`）重写变了的行。

两条硬约束来自实测（features/13 evidence/说明.md），不是风格偏好：

1. **绝不发 `2J`**——先擦再画，屏幕在整个渲染耗时里是全黑的（CC 注释：可能 ~80ms）。
   要「全量重绘」就老老实实每行都写一遍，屏幕内容会被逐行覆盖，中间态是旧内容不是黑屏。
2. **绝不重发 `?1049h`**——已经在备用屏里再发一次会**清屏 + 光标回原点**
   （iTerm2 3.6.11 与 Terminal.app 470.2 实测一致；CC 源码里有一处注释把这条写反了）。
   进出备用屏是 `terminal.py` 的事，本模块一个 `?1049` 都不发。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from pai.modes.statusline import _ESCAPES, display_width
from pai.tui import theme
from pai.tui.component import Component, extract_cursor
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript, TranscriptEntry

REVERSE = "\x1b[7m"
UNREVERSE = "\x1b[27m"
SYNC_START = "\x1b[?2026h"
SYNC_END = "\x1b[?2026l"
CLEAR_LINE = "\x1b[2K"
SHOW_CURSOR = "\x1b[?25h"
HIDE_CURSOR = "\x1b[?25l"


class AltScreenRenderer:
    """整屏帧 + 行 diff。"""

    #: 内容归 pai 自己持有（`app.commit` 据此决定要不要往 transcript 里塞）
    keeps_transcript = True

    def __init__(self, *, write: Callable[[str], None],
                 width: Callable[[], int], height: Callable[[], int],
                 transcript: Transcript, scroll: ScrollState,
                 selection: Optional[Selection] = None) -> None:
        self._write = write
        self._width = width
        self._height = height
        self.transcript = transcript
        self.scroll = scroll
        self.selection = selection
        self._previous: List[str] = []
        self._previous_size = (0, 0)
        self._drawing = False
        self._again = False
        self.viewport = 0          # 最近一帧里 transcript 占了几行（命中测试要用）
        self.input_row: Optional[int] = None   # 输入行在屏幕第几行（点击定位要用）

    # --- 公开操作（与 DockRenderer 同名同义）-----------------------------

    def invalidate(self) -> None:
        """下一帧全量重画。

        resize 之后必须调：**终端自己会在 resize 时挪动内容**（实测 iTerm2 会把
        主屏的行混进备用屏），而 `_previous` 记的是「pai 以为屏幕上有什么」——
        它刚刚被终端背着改过，据它做 diff 会漏掉那些行，且再也修不回来。
        """
        self._previous = []

    def draw(self, root: Component) -> None:
        if self._drawing:
            # `SIGWINCH` 处理器会在一帧**写到一半**时调进来。两帧的字节交错写出去
            # 屏幕就是花的，而且后一帧会把 `_previous` 覆盖成「已经画好了」，
            # 于是下一帧的 diff 以为没变化——错位从此永久留在屏幕上。
            self._again = True
            return
        self._drawing = True
        try:
            self._draw(root)
        finally:
            self._drawing = False
        if self._again:
            self._again = False
            self.invalidate()          # 被打断过，屏幕上有什么已经不可信了
            self.draw(root)

    def _draw(self, root: Component) -> None:
        width, height = max(1, self._width()), max(1, self._height())
        frame = self._compose(root, width, height)
        frame, cursor = extract_cursor(frame)
        # 尺寸变了：上一帧的行与屏幕格子不再对应，逐行全写一遍（**不清屏**）
        full = self._previous_size != (width, height) or not self._previous
        buf = SYNC_START
        for row, line in enumerate(frame):
            if not full and row < len(self._previous) and line == self._previous[row]:
                continue
            buf += f"\x1b[{row + 1};1H{CLEAR_LINE}{line}"
        if cursor is not None:
            buf += f"\x1b[{cursor[0] + 1};{min(width, cursor[1] + 1)}H{SHOW_CURSOR}"
        else:
            buf += HIDE_CURSOR
        self._write(buf + SYNC_END)
        self._previous = frame
        self._previous_size = (width, height)

    def commit(self, entry: TranscriptEntry, root: Optional[Component] = None) -> None:
        """条目已经进了 transcript（`app.commit` 放的），这里只要重画。

        与 `DockRenderer.commit` 的区别是本质的：那边「上交给终端、从此够不着」，
        这边**没有上交这回事**——所有内容始终归 pai 所有，这正是能滚能重排的原因。
        """
        if root is not None:
            self.draw(root)

    def clear(self) -> None:
        """退出路径：屏幕整个还给终端（`terminal.py` 随后发 `?1049l`），这里无事可做。"""
        self._previous = []
        self._previous_size = (0, 0)

    # --- 组帧 -----------------------------------------------------------

    def _compose(self, root: Component, width: int, height: int) -> List[str]:
        # **两遍**：第一遍只为量出 dock 有多高（视口高度依赖它），更新完滚动状态
        # 再画第二遍——否则状态行上的「已上滚」永远慢一帧。
        # 两遍的高度**可能不一样**（状态行会多一条「已上滚」之类），
        # 所以第二遍之后必须重算视口，不能拿第一遍的长度去截第二遍的结果。
        total = self.transcript.total_lines(width)
        dock, _ = self._dock(root, width, height)
        self.scroll.update(total, max(1, height - len(dock)))
        dock, dropped = self._dock(root, width, height)
        viewport = max(1, height - len(dock))
        self.scroll.update(total, viewport)
        self.viewport = viewport
        offset = getattr(root, "editor_offset", None)
        # dock 被截断过的话，输入行在 dock 里的下标要跟着往上挪
        self.input_row = (viewport + offset - dropped
                          if offset is not None and offset >= dropped else None)

        # **先截断再套高亮**：反过来的话，一行被截短而高亮区间还按原长算，
        # 屏幕上的列号与选区就对不上了。
        body = [_fit(line, width)
                for line in self.transcript.slice(width, self.scroll.scroll_top, viewport)]
        body = self._highlight(body, width)
        body += [""] * (viewport - len(body))
        frame = body + dock
        # 帧必须正好 height 行。**多出来时砍上面**：dock 是「现在」——
        # 正在问的问题、正在输入的那一行都在里面，砍掉它等于把界面砍没了。
        if len(frame) > height:
            frame = frame[len(frame) - height:]
        return frame + [""] * max(0, height - len(frame))

    def logical_row(self, screen_row: int) -> Optional[int]:
        """屏幕第几行 → transcript 第几个逻辑行。落在 dock 上返回 None。

        **这就是命中测试**：pai 的 transcript 是一串行，映射是一维的
        （`scroll_top + 屏幕行`），不需要 CC 那棵矩形树。
        """
        if screen_row < 0 or screen_row >= self.viewport:
            return None
        return self.scroll.scroll_top + screen_row

    def _highlight(self, body: List[str], width: int) -> List[str]:
        """把选区套上反显。**只作用于 transcript 区域**——dock 是「现在」，
        不该被过去的选择涂到。

        屏幕第 i 行 ↔ 逻辑行 `scroll_top + i`，这就是全部映射
        （选区锚在逻辑行号，所以滚动时高亮跟着内容走）。
        """
        span = self.selection.bounds() if self.selection is not None else None
        if span is None:
            return body
        start, end = span
        top = self.scroll.scroll_top
        out = []
        for offset, line in enumerate(body):
            row = top + offset
            if row < start.row or row > end.row:
                out.append(line)
                continue
            lo = start.col if row == start.row else 0
            hi = (end.col + 1) if row == end.row else None
            out.append(_reverse_columns(line, lo, hi))
        return out

    def _dock(self, root: Component, width: int, height: int):
        """返回 (dock 的行, 被截掉了几行)。截掉的行数是给「输入行在第几行」用的。"""
        lines = [_fit(line, width) for line in root.render(width)]
        dropped = 0
        # dock 再高也要给 transcript 留一行：一行不留的话，
        # 「上面是历史、下面是现在」这个心智模型当场破产（用户以为对话没了）
        if height > 1 and len(lines) > height - 1:
            dropped = len(lines) - (height - 1)
            lines = lines[dropped:]
        return lines, dropped


def _reverse_columns(line: str, lo: int, hi: Optional[int]) -> str:
    """给 [lo, hi) 这段**显示列**套上反显。

    用反显而不是配色：选区要在任何主题下都看得出来。
    两处容易错的：
    ① 转义序列**不占列**，按字符数算列号会让高亮从中间某处开始偏；
    ② 选中的文本里若有 `\x1b[0m`，它会把反显一起关掉——**每个 SGR 之后要补回来**
       （pi 的 `applySelectionHighlight` 与 CC 都这么干）。
    """
    out = []
    col = 0
    on = False
    i = 0
    while i < len(line):
        m = _ESCAPES.match(line, i)
        if m:
            out.append(m.group(0))
            if on and m.group(0).endswith("m"):
                out.append(REVERSE)          # 被 SGR 打断的反显要立刻补回来
            i = m.end()
            continue
        ch = line[i]
        w = display_width(ch)
        inside = col + w > lo and (hi is None or col < hi)
        if inside and not on:
            out.append(REVERSE)
            on = True
        elif not inside and on:
            out.append(UNREVERSE)
            on = False
        out.append(ch)
        col += w
        i += 1
    if on:
        out.append(UNREVERSE)
    return "".join(out)


def _fit(line: str, width: int) -> str:
    """把一行硬切到 width 列。

    这是**第二道闸**：条目渲染时已经折过行了，正常不该有超宽的行。
    但一行超宽在 alt 屏里的症状是「悄悄吃掉下一行」（配 `?7l` 则是右边界截断），
    而 pi 为同一个问题准备的是 fail-loud（超宽即 dump + throw）——
    pai 这里先取「静默截断」，等有一次真撞上再考虑要不要吵。
    """
    return theme.wrap(line, width)[0] if line else line
