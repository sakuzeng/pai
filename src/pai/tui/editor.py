"""行编辑器：收按键、吐新状态，不碰终端、不做 IO。

替掉 readline（方案 A 全程 raw mode，readline 用不了）。
**已知回退**：`Ctrl+R` 增量搜索不做——拍板时就知道的代价，已登记 TODO。

光标是**字符索引**不是列号：一个中文是一个字符、两列。两者混用是中文终端 UI
第二常见的坑（第一是宽度），所以这里只在 `render` 里把索引换算成列。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from pai.modes.statusline import display_width
from pai.tui import theme
from pai.tui.component import CURSOR_MARKER, Component

REVERSE = "\x1b[7m"       # 选中用反显：不依赖主题，浅色深色终端上都看得出来
UNREVERSE = "\x1b[27m"
from pai.tui.keys import Key

_WORD_BREAK = " \t\n"


def _wrap_spans(line: str, room: Optional[int]) -> List[tuple]:
    """把一个逻辑行按显示列切成 `(start, end)` 字符区间。

    `room is None` = 不折（width 未知时保持旧行为）。按 `display_width`
    逐字符量宽：组合记号计 0 列所以天然粘在基字符后面；宽字符不会被劈成两半
    （放不下就整个挪去下一段）。单字符比 room 还宽（room=1 撞上汉字）时照放，
    宁可超 1 列也不许造出空段死循环。"""
    if room is None or not line:
        return [(0, len(line))]
    spans: List[tuple] = []
    start, used = 0, 0
    for idx, ch in enumerate(line):
        w = display_width(ch)
        if used + w > room and idx > start:
            spans.append((start, idx))
            start, used = idx, 0
        used += w
    spans.append((start, len(line)))
    return spans


class LineEditor(Component):
    """一行（或 `\\` 续行出来的多行）输入。`handle` 返回非 None 表示这一行提交了。"""

    def __init__(self, *, prompt: str = "› ", continuation: str = "  ",
                 history: Optional[Sequence[str]] = None,
                 color: bool = False) -> None:
        self.color = color
        self.prompt = prompt
        self.continuation = continuation
        # 选区：字符下标（不是显示列）。**编辑器此前完全没有选区概念**——
        # 接管鼠标之后终端原生的拖选没了，这一块是补给输入框的。
        self._sel_anchor = None
        self._sel_focus = None
        self.text = ""
        self.cursor = 0
        self._history: List[str] = list(history) if history else []
        self._hpos: Optional[int] = None      # None = 不在翻历史
        self._draft = ""                      # 翻历史前正在打的那半句

    # --- 输入 ---------------------------------------------------------

    def handle(self, key: Key) -> Optional[str]:
        name = key.name
        # **选中一段之后打字/退格，先把选中的删掉**——所有编辑器的通行行为。
        # 原来这里是「一按键就清选区」，于是退格只删掉光标前一个字（用户打回来的）。
        span = self.selection_range()
        self.clear_selection()
        if span is not None and name in ("char", "paste", "backspace", "delete"):
            lo, hi = span
            self.text = self.text[:lo] + self.text[hi:]
            self.cursor = lo
            if name in ("backspace", "delete"):
                return None          # 删掉选区就是这次按键的全部效果
        if name == "char":
            self._insert(key.text)
        elif name == "paste":
            self._insert(key.text)            # 粘贴内容里的换行不提交
        elif name == "enter":
            return self._enter()
        elif name == "backspace":
            if self.cursor:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
        elif name == "delete":
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        elif name == "left":
            self.cursor = max(0, self.cursor - 1)
        elif name == "right":
            self.cursor = min(len(self.text), self.cursor + 1)
        elif name in ("home", "ctrl_a"):
            self.cursor = 0
        elif name in ("end", "ctrl_e"):
            self.cursor = len(self.text)
        elif name == "ctrl_u":
            self.text = self.text[self.cursor:]
            self.cursor = 0
        elif name == "ctrl_k":
            self.text = self.text[:self.cursor]
        elif name == "ctrl_w":
            start = self._word_start()
            self.text = self.text[:start] + self.text[self.cursor:]
            self.cursor = start
        elif name == "word_left":
            self.cursor = self._word_start()
        elif name == "word_right":
            self.cursor = self._word_end()
        elif name == "up":
            self._history_step(-1)
        elif name == "down":
            self._history_step(1)
        # 其余（unknown / ctrl_c / esc / shift_tab …）不归编辑器管，交给上层仲裁
        return None

    # --- 选区（feature 16）--------------------------------------------

    def start_selection(self, index: int) -> None:
        """按下：只记锚点。**裸点击不产生选区**（同 transcript 那边的规矩）。"""
        self._sel_anchor = max(0, min(len(self.text), index))
        self._sel_focus = None

    def extend_selection(self, index: int) -> None:
        if self._sel_anchor is None:
            return
        self._sel_focus = max(0, min(len(self.text), index))

    def clear_selection(self) -> None:
        self._sel_anchor = self._sel_focus = None

    @property
    def selection_anchor(self):
        """拖动是不是从输入框里开始的——接线层据此判断这次拖动归谁。"""
        return self._sel_anchor

    def selection_range(self):
        """归一化成 (起, 止) 的字符下标；没选中返回 None。"""
        if self._sel_anchor is None or self._sel_focus is None:
            return None
        lo, hi = sorted((self._sel_anchor, self._sel_focus))
        return None if lo == hi else (lo, hi)

    def selected_text(self) -> str:
        span = self.selection_range()
        return "" if span is None else self.text[span[0]:span[1]]

    def point_at(self, line_index: int, col: int) -> int:
        """(第几行, 显示列) → **整段文本里的字符下标**。

        按显示列而不是字符数：一个中文占两列，按字符数算会差一半。
        """
        from pai.modes.statusline import display_width

        lines = self.text.split("\n")
        line_index = max(0, min(len(lines) - 1, line_index))
        base = sum(len(l) + 1 for l in lines[:line_index])
        line = lines[line_index]
        if col <= 0:
            return base
        used = 0
        for i, ch in enumerate(line):
            w = display_width(ch)
            if used + w > col:
                return base + i
            used += w
        return base + len(line)

    def prompt_width(self) -> int:
        """提示符占几列（点击定位要按它偏移）。

        `prompt` 里**已经含了那个空格**（`"› "`）——再 +1 就把光标整体推右一列。
        """
        from pai.modes.statusline import display_width

        return display_width(self.prompt)

    def move_to_column(self, col: int) -> None:
        """把光标挪到**显示列** col 处。超出末尾就停在末尾。

        按显示列而不是字符下标：一个中文占两列，按下标算会差一半。
        """
        from pai.modes.statusline import display_width

        if col <= 0:
            self.cursor = 0
            return
        used = 0
        for i, ch in enumerate(self.text):
            w = display_width(ch)
            if used + w > col:
                self.cursor = i
                return
            used += w
        self.cursor = len(self.text)

    def set_text(self, text: str) -> None:
        self.text = text
        self.cursor = len(text)

    def clear(self) -> None:
        self.text = ""
        self.cursor = 0
        self._hpos = None
        self._draft = ""

    # --- 内部 ---------------------------------------------------------

    def _insert(self, text: str) -> None:
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)

    def _enter(self) -> Optional[str]:
        if self.text.endswith("\\"):          # 05 已交付的续行语义，不做多行编辑器
            self.text = self.text[:-1] + "\n"
            self.cursor = len(self.text)
            return None
        line = self.text
        self.clear()
        return line

    def _word_start(self) -> int:
        i = self.cursor
        while i > 0 and self.text[i - 1] in _WORD_BREAK:
            i -= 1
        while i > 0 and self.text[i - 1] not in _WORD_BREAK:
            i -= 1
        return i

    def _word_end(self) -> int:
        i = self.cursor
        n = len(self.text)
        while i < n and self.text[i] in _WORD_BREAK:
            i += 1
        while i < n and self.text[i] not in _WORD_BREAK:
            i += 1
        return i

    def _history_step(self, delta: int) -> None:
        if not self._history:
            return
        if self._hpos is None:
            if delta > 0:
                return                        # 没在翻历史时按 ↓ 无事发生
            self._draft = self.text
            self._hpos = len(self._history)
        pos = self._hpos + delta
        if pos < 0:
            return                            # 顶到头就停住
        if pos >= len(self._history):
            self._hpos = None
            self.set_text(self._draft)        # 翻回来要能拿回正在打的那半句
            return
        self._hpos = pos
        self.set_text(self._history[pos])

    # --- 渲染 ---------------------------------------------------------

    def render(self, width: int) -> List[str]:
        """逻辑行 → 显示行。超宽按**显示列**折行（feature 21 拍板 A，pi 与 CC
        独立同选）：此前 width 收了不用，main-screen 下终端自动折行让 dock 的
        高度记账全错（阶梯同款根因），alt 下 `_fit` 连 CURSOR_MARKER 一起截掉。

        三条不变量：折行不丢字符；CURSOR_MARKER 永远落在光标所在的显示行；
        选区反显对**每个显示行内配平**——alt 屏按行 diff 重绘，跨行悬空的 SGR
        会在只重绘其中一行时漏出来。折行按字符边界不做词级（pi 的词级回退是
        体验优化非正确性，中文也没词边界）。"""
        lines = self.text.split("\n")
        before = self.text[:self.cursor]
        row = before.count("\n")
        col = len(before) - (before.rfind("\n") + 1)
        span = self.selection_range()
        out: List[str] = []
        base = 0
        for i, line in enumerate(lines):
            raw_prefix = self.prompt if i == 0 else self.continuation
            prefix = theme.paint(raw_prefix, theme.CYAN, color=self.color)
            pad = " " * display_width(raw_prefix)
            room = max(1, width - display_width(raw_prefix)) if width > 0 else None
            chunks = _wrap_spans(line, room)
            for k, (lo_c, hi_c) in enumerate(chunks):
                body = line[lo_c:hi_c]
                # 光标在本段内（或在行尾且这是最后一段）才插标记
                cut = None
                if i == row and (lo_c <= col < hi_c
                                 or (col == hi_c and k == len(chunks) - 1)):
                    cut = col - lo_c
                    body = body[:cut] + CURSOR_MARKER + body[cut:]
                if span is not None:
                    # 选区是**整段文本**的下标，换算成本段的局部区间；
                    # 光标标记已经插进去了，切片时要把它的长度算上
                    lo = span[0] - base - lo_c
                    hi = span[1] - base - lo_c
                    if cut is not None and cut <= lo:
                        lo += len(CURSOR_MARKER)
                    if cut is not None and cut <= hi:
                        hi += len(CURSOR_MARKER)
                    lo = max(0, min(len(body), lo))
                    hi = max(0, min(len(body), hi))
                    if hi > lo:
                        body = (body[:lo] + REVERSE + body[lo:hi]
                                + UNREVERSE + body[hi:])
                out.append((prefix if k == 0 else pad) + body)
            base += len(line) + 1
        return out
