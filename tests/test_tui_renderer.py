"""T1：dock 渲染器——画得出、重画得对、收缩不留残影、commit 上交 scrollback。

断言的是**屏幕内容**而不是字节：同一个效果有多种字节写法，断言字节等于把实现钉死。
屏幕由 tests/tui_screen.py 的最小终端模拟器给出。
只有三条例外（「绝不发清屏」「包同步输出」）必须看字节——那本来就是字节层面的要求。
"""

import pytest

from pai.tui.component import CURSOR_MARKER, Container, Text
from pai.tui.renderer import DockRenderer
from tests.tui_screen import VirtualScreen


def make(cols=40, rows=8):
    screen = VirtualScreen(cols=cols, rows=rows)
    raw = []

    def write(data):
        raw.append(data)
        screen.write(data)

    renderer = DockRenderer(write=write, width=lambda: screen.cols)
    return screen, renderer, raw


def dock(*lines):
    return Container([Text(t) for t in lines])


# --- 画出来 -----------------------------------------------------------

def test_first_draw_puts_every_line_on_screen():
    screen, r, _ = make()
    r.draw(dock("one", "two", "three"))
    assert screen.visible() == ["one", "two", "three"]


def test_cursor_ends_on_the_last_dock_line():
    """下一帧的相对移动全部以此为基准，错一行整块就漂。"""
    screen, r, _ = make()
    r.draw(dock("one", "two", "three"))
    screen.write("\rZ")
    assert screen.visible() == ["one", "two", "Zhree"]


def test_every_write_is_wrapped_in_synchronized_output():
    _, r, raw = make()
    r.draw(dock("one"))
    for chunk in raw:
        assert chunk.startswith("\x1b[?2026h") and chunk.endswith("\x1b[?2026l")


# --- 重画 -------------------------------------------------------------

def test_redraw_same_height_replaces_content():
    screen, r, _ = make()
    r.draw(dock("aaa", "bbb"))
    r.draw(dock("xxx", "yyy"))
    assert screen.visible() == ["xxx", "yyy"]


def test_redraw_never_clears_screen_or_scrollback():
    """main-screen 模式下 scrollback 归终端所有。pi 敢发 `3J` 是因为它持有整份文档，
    pai 不持有——清掉就画不回来了（K pi-tui-main-screen 第四节）。"""
    _, r, raw = make()
    r.draw(dock("aaa", "bbb"))
    r.draw(dock("xxx"))
    emitted = "".join(raw)
    assert "\x1b[2J" not in emitted
    assert "\x1b[3J" not in emitted
    assert "\x1b[H" not in emitted


def test_shrinking_dock_leaves_no_residue():
    """dock 变矮时多出来的行必须先清空——它们一旦留在屏幕上就再也够不着了。"""
    screen, r, _ = make()
    r.draw(dock("aaa", "bbb", "ccc", "ddd", "eee"))
    r.draw(dock("xxx", "yyy"))
    assert screen.visible() == ["xxx", "yyy"]


def test_shrinking_dock_leaves_cursor_on_new_last_line():
    screen, r, _ = make()
    r.draw(dock("aaa", "bbb", "ccc"))
    r.draw(dock("xxx"))
    screen.write("\rZ")
    assert screen.visible() == ["Zxx"]


def test_growing_dock_keeps_content_above_it():
    screen, r, _ = make()
    r.commit(["历史一行"])
    r.draw(dock("aaa"))
    r.draw(dock("aaa", "bbb", "ccc"))
    assert screen.logical_lines()[:4] == ["历史一行", "aaa", "bbb", "ccc"]


def test_redraw_is_whole_dock_not_a_diff():
    """原则 4：差量重绘后置。只改一行时其余行也重写——先正确后快。"""
    _, r, raw = make()
    r.draw(dock("aaa", "bbb"))
    raw.clear()
    r.draw(dock("aaa", "ZZZ"))
    assert "aaa" in "".join(raw)


# --- commit：从 dock 上交到 scrollback ---------------------------------

def test_commit_puts_lines_above_the_dock():
    screen, r, _ = make()
    r.draw(dock("› 输入"))
    r.commit(["🤖 答案"], root=dock("› 输入"))
    assert screen.visible() == ["🤖 答案", "› 输入"]


def test_commit_does_not_interleave_with_dock():
    """先清 dock 再打印。顺序反了，上交的内容会与 dock 残影叠在一起。"""
    screen, r, _ = make()
    r.draw(dock("状态行", "› 输入"))
    r.commit(["提交的一行"], root=dock("状态行", "› 输入"))
    assert screen.visible() == ["提交的一行", "状态行", "› 输入"]


def test_redraw_after_commit_does_not_cover_committed_lines():
    screen, r, _ = make()
    r.draw(dock("› 输入"))
    r.commit(["第一条"], root=dock("› 输入"))
    r.commit(["第二条"], root=dock("› 输入"))
    r.draw(dock("› 输入", "多了一行"))
    assert screen.visible() == ["第一条", "第二条", "› 输入", "多了一行"]


def test_commit_without_root_leaves_no_dock():
    screen, r, _ = make()
    r.draw(dock("› 输入"))
    r.commit(["再见。"])
    assert screen.visible() == ["再见。"]


def test_commit_scrolls_old_content_into_scrollback():
    screen, r, _ = make(rows=4)
    for i in range(6):
        r.commit([f"行{i}"], root=dock("› 输入"))
    assert screen.scrollback[:2] == ["行0", "行1"]
    assert screen.visible()[-1] == "› 输入"


def test_clear_removes_the_dock_entirely():
    screen, r, _ = make()
    r.commit(["留下的"], root=dock("状态行", "› 输入"))
    r.clear()
    assert screen.visible() == ["留下的"]


# --- CURSOR_MARKER：中文 IME 候选框的锚点 -------------------------------

class _Focused:
    """一个把光标标记吐在指定位置的组件（模拟输入行）。"""

    def __init__(self, text, at):
        self.text, self.at = text, at

    def render(self, width):
        return [self.text[:self.at] + CURSOR_MARKER + self.text[self.at:]]

    def invalidate(self):
        pass


def test_marker_is_stripped_and_never_reaches_the_screen():
    screen, r, raw = make()
    r.draw(Container([_Focused("› 中文ab", 5)]))
    assert CURSOR_MARKER not in "".join(raw)
    assert screen.visible() == ["› 中文ab"]


def test_hardware_cursor_lands_on_the_marker_column_by_display_width():
    """「› 中文a」= 2+4+1 = 7 列，所以光标该在第 7 列（0 起）。

    按字符数算会得到 5，光标停在半个中文上——IME 候选框就飘了。
    """
    screen, r, _ = make()
    r.draw(Container([_Focused("› 中文ab", 5)]))
    assert screen.col == 7


def test_hardware_cursor_lands_on_the_right_row_when_the_dock_has_more_below():
    screen, r, _ = make()
    r.draw(Container([Text("活动区"), _Focused("› hi", 4), Text("状态行")]))
    assert screen.row == 1
    screen.write("X")
    assert screen.visible() == ["活动区", "› hiX", "状态行"]


def test_next_redraw_uses_the_cursor_row_as_its_base_not_the_last_line():
    """光标停在输入行而不是最后一行，重绘的相对移动必须按前者算——
    按最后一行算会让整块 dock 每帧上移一行。"""
    screen, r, _ = make()
    r.draw(Container([Text("活动区"), _Focused("› hi", 4), Text("状态行")]))
    r.draw(Container([Text("活动区2"), _Focused("› hey", 5), Text("状态行2")]))
    assert screen.visible() == ["活动区2", "› hey", "状态行2"]
