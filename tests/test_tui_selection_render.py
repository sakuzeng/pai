"""选区高亮（feature 16 T5）：屏幕上看得见选中了什么。

用反显（`\\x1b[7m`）而不是配色：**选区要在任何主题下都看得出来**，
而反显是唯一不依赖主题的手段（theme.py 里那套颜色在浅色终端上会翻车）。
"""

from typing import List

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.component import Component
from pai.tui.screen import VirtualScreen
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript, dynamic_entry, text_entry

REVERSE, UNREVERSE = "\x1b[7m", "\x1b[27m"


class FakeDock(Component):
    def render(self, width: int) -> List[str]:
        return ["dock-line"]


class Harness:
    def __init__(self, cols=20, rows=6, lines=("aaaa", "bbbb", "cccc", "dddd")):
        self.cols, self.rows = cols, rows
        self.writes: List[str] = []
        self.screen = VirtualScreen(cols=cols, rows=rows, strict=False)
        self.transcript = Transcript()
        for line in lines:
            self.transcript.append(text_entry([line]))
        self.scroll = ScrollState()
        self.selection = Selection()
        self.renderer = AltScreenRenderer(
            write=self._write, width=lambda: self.cols, height=lambda: self.rows,
            transcript=self.transcript, scroll=self.scroll, selection=self.selection)

    def _write(self, data):
        self.writes.append(data)
        self.screen.write(data)

    def draw(self):
        self.renderer.draw(FakeDock())
        return self.writes[-1]


def test_no_selection_leaves_the_frame_byte_identical():
    """回归防线：没选中任何东西时，本 task 一个字节都不该改变。"""
    plain = Harness()
    plain.renderer.selection = None
    a = plain.draw()
    withsel = Harness()
    b = withsel.draw()
    assert a == b


def test_selected_range_is_reversed():
    h = Harness()
    h.selection.start(1, 1)
    h.selection.update(1, 2)
    out = h.draw()
    assert REVERSE + "bb" + UNREVERSE in out


def test_selection_spans_multiple_lines():
    """首行从起点到行尾、末行从行首到终点、中间整行。"""
    h = Harness()
    h.selection.start(0, 2)
    h.selection.update(2, 1)
    out = h.draw()
    assert REVERSE + "aa" + UNREVERSE in out       # 首行 2..行尾
    assert REVERSE + "bbbb" + UNREVERSE in out     # 中间整行
    assert REVERSE + "cc" + UNREVERSE in out       # 末行 0..1


def test_columns_are_display_columns_not_character_indexes():
    h = Harness(lines=("中文abc",))
    h.selection.start(0, 0)
    h.selection.update(0, 3)                       # 列 0..3 = 「中文」
    assert REVERSE + "中文" + UNREVERSE in h.draw()


def test_highlight_is_applied_after_truncation():
    """先套高亮再截断的话，一行被截短而高亮区间还按原长算——列号与屏幕对不上。

    注意用 `dynamic_entry`：`text_entry` 会**折行**（那是正常路径），
    而 `_fit` 的截断是给「条目自己吐出超宽行」准备的第二道闸——
    要测截断就得走那条路。
    """
    h = Harness(cols=8, lines=())
    h.transcript.append(dynamic_entry(lambda w: ["abcdefghijklmnop"]))
    h.selection.start(0, 5)
    h.selection.update(0, 30)                      # 终点远超屏幕宽度
    out = h.draw()
    assert REVERSE + "fgh" + UNREVERSE in out      # 只高亮到第 8 列为止
    assert "ijkl" not in out


def test_the_dock_is_never_highlighted():
    """选区只在 transcript 区域；dock 是「现在」，不该被过去的选择涂到。"""
    h = Harness(rows=6)
    h.selection.start(0, 0)
    h.selection.update(99, 99)                     # 一路选到底
    assert REVERSE + "dock-line" not in h.draw()


def test_a_colour_reset_inside_the_selection_does_not_kill_the_reverse():
    """选中一段带颜色的文本时，中间的 `\\x1b[0m` 会把反显一起关掉——
    必须在每个 SGR 之后把反显补回来（pi 与 CC 都这么干）。"""
    h = Harness(lines=("\x1b[36mab\x1b[0mcd",))
    h.selection.start(0, 0)
    h.selection.update(0, 3)
    out = h.draw()
    tail = out[out.index(REVERSE):]
    assert tail.index("\x1b[0m") < tail.index("cd")
    assert REVERSE in tail[tail.index("\x1b[0m"):tail.index("cd")]


def test_scrolling_moves_the_highlight_with_the_content():
    """选区锚在逻辑行：内容滚上去，高亮跟着内容走，不粘在屏幕上。"""
    h = Harness(rows=4, lines=tuple(f"line{i}" for i in range(20)))
    h.selection.start(17, 0)
    h.selection.update(17, 4)
    first = h.draw()
    h.scroll.scroll_by(-2)
    second = h.draw()
    assert REVERSE in first and REVERSE in second
    assert first != second
