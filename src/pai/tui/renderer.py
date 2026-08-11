"""唯一碰终端的地方：把组件树画进屏幕底部的 dock，并把内容「上交」给 scrollback。

**心智模型**（roadmap 阶段 2 原则 2）：屏幕分两块，
上面归**终端**（scrollback，pai 打出去就再也够不着），下面归 **pai**（dock，逐帧重绘）。
两块之间只有一条通道：`commit()`——先清 dock、把内容当普通输出打出去、再在下面重画 dock。

**不做差量重绘**（原则 4）：dock 每帧整体重画。dock 高度是个位数，代价可接受；
真要优化必须先有数字（AGENTS.md 里 `perf` 的判据）。

**绝不发清屏/清 scrollback**：pi 的 main-screen 宽度一变就 `\\x1b[2J\\x1b[H\\x1b[3J`
重画，它敢清是因为它持有整份文档；pai 不持有，清掉就画不回来
（K source-walks/pi-tui-main-screen.md 第四节）。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from pai.tui.component import Component, extract_cursor as _extract_cursor

SYNC_START = "\x1b[?2026h"      # DEC synchronized output：整帧写完再刷新，防撕裂
SYNC_END = "\x1b[?2026l"
CLEAR_LINE = "\x1b[2K"


class DockRenderer:
    """屏幕底部若干行的所有者。

    **不变量**：每次公开方法返回后，硬件光标停在 **dock 最后一行的第 0 列**；
    dock 为空时停在「dock 本该开始的那一行」的第 0 列。
    下一帧的相对移动全部以此为基准——错一行，整块就漂。

    **前置条件**：首次调用前光标应在一个空行的行首（调用方打完欢迎语要带换行）。
    这条判不了，只能写下来。
    """

    def __init__(self, *, write: Callable[[str], None],
                 width: Callable[[], int]) -> None:
        self._write = write
        self._width = width
        self._height = 0            # dock 当前占了几行
        self._cursor_offset = 0     # 硬件光标此刻在 dock 的第几行（0 = 第一行）

    @property
    def height(self) -> int:
        return self._height

    # --- 公开操作 -----------------------------------------------------

    def draw(self, root: Component) -> None:
        """整块重画 dock。"""
        lines = root.render(self._width())
        lines, cursor = _extract_cursor(lines)
        self._write(SYNC_START + self._repaint(lines, cursor) + SYNC_END)
        self._height = len(lines)

    def commit(self, lines, root: Optional[Component] = None) -> None:
        """把内容从 dock **上交**到 scrollback：清 dock → 当普通输出打 → 重画 dock。

        收 `TranscriptEntry` 或裸行数组。**上交之后 pai 就够不着了**——
        这正是 alt 屏那条路径存在的理由（feature 13）。

        顺序不能反：先打印再清 dock，上交的内容会与 dock 残影叠在一起。
        打完每行都带换行，于是结束时光标停在一个空行的行首——正好是 dock 的新起点。
        """
        if hasattr(lines, "render"):
            lines = lines.render(self._width())
        buf = SYNC_START + self._erase()
        for line in lines:
            buf += line + "\r\n"
        self._write(buf + SYNC_END)
        self._height = 0
        if root is not None:
            self.draw(root)

    def clear(self) -> None:
        """擦掉 dock，把那几行还给终端（退出路径用）。"""
        if self._height == 0:
            return
        self._write(SYNC_START + self._erase() + SYNC_END)
        self._height = 0

    # --- 内部：只拼字符串，不写终端 -------------------------------------

    def _to_top(self) -> str:
        """从光标当前所在的 dock 行回到第一行的行首。

        基准是 `_cursor_offset` 而不是 `height - 1`：有 CURSOR_MARKER 时光标停在
        输入行而不是最后一行，按最后一行算会整块上移一行。
        """
        up = f"\x1b[{self._cursor_offset}A" if self._cursor_offset > 0 else ""
        return up + "\r"

    def _erase(self) -> str:
        """清空 dock 占的每一行，光标停在 dock 第一行的行首。"""
        if self._height == 0:
            return ""
        buf = self._to_top()
        for i in range(self._height):
            if i:
                buf += "\r\n"
            buf += CLEAR_LINE
        if self._height > 1:
            buf += f"\x1b[{self._height - 1}A"
        self._cursor_offset = 0
        return buf + "\r"

    def _repaint(self, lines: List[str], cursor=None) -> str:
        """重画成 lines。旧的比新的高时，多出来的行**先清空再收缩**。

        多出来的那几行一旦留在屏幕上就够不着了——它们此刻还在 dock 区，
        下一帧的 dock 变矮之后就成了 scrollback 的一部分，谁也擦不掉。
        """
        old = self._height
        total = max(len(lines), old)
        if total == 0:
            self._cursor_offset = 0
            return ""
        buf = self._to_top()
        for i in range(total):
            if i:
                buf += "\r\n"
            buf += CLEAR_LINE
            if i < len(lines):
                buf += lines[i]
        last = max(0, len(lines) - 1)
        back = (total - 1) - last
        if back > 0:
            buf += f"\x1b[{back}A"
        buf += "\r"
        self._cursor_offset = last
        if cursor is not None:
            # 原则 3：把**硬件光标**摆到标记处。中文 IME 候选框就贴着它弹，
            # 摆错列 = 候选框飘到别处。CURSOR_MARKER 本身已在上面剥掉。
            row, col = cursor
            if last > row:
                buf += f"\x1b[{last - row}A"
            buf += f"\x1b[{col + 1}G"
            self._cursor_offset = row
        return buf


# `_extract_cursor` 已挪进 component.py（feature 13：alt 屏渲染器也要用同一份）。
