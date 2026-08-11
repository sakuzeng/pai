"""整屏帧渲染器（feature 13 T4）。

alt 屏下 pai 拥有整个屏幕：每帧 = transcript 视口 + dock，**正好 rows 行**。
两条硬约束来自实测（features/13 evidence）：
**绝不发 `2J`**（先擦会让屏幕在整个渲染耗时里全黑）、
**绝不重发 `?1049h`**（会清屏闪白——两个 macOS 终端实测一致）。
"""

from typing import List

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.component import CURSOR_MARKER, Component
from pai.tui.screen import VirtualScreen
from pai.tui.scroll import ScrollState
from pai.tui.transcript import Transcript, text_entry


class FakeDock(Component):
    def __init__(self, lines: List[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> List[str]:
        return list(self.lines)


class Harness:
    """把渲染器接到一块虚拟屏上，既能断言屏幕内容，也能断言写出的字节。"""

    def __init__(self, cols=20, rows=8, entries=("l1", "l2", "l3", "l4", "l5")):
        self.cols, self.rows = cols, rows
        self.screen = VirtualScreen(cols=cols, rows=rows)
        self.writes: List[str] = []
        self.transcript = Transcript()
        for line in entries:
            self.transcript.append(text_entry([line]))
        self.scroll = ScrollState()
        self.renderer = AltScreenRenderer(
            write=self._write,
            width=lambda: self.cols,
            height=lambda: self.rows,
            transcript=self.transcript,
            scroll=self.scroll,
        )

    def _write(self, data: str) -> None:
        self.writes.append(data)
        self.screen.write(data)

    def last(self) -> str:
        return self.writes[-1] if self.writes else ""

    def resize(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.screen = VirtualScreen(cols=cols, rows=rows)


def test_frame_is_exactly_terminal_height_with_dock_at_the_bottom():
    h = Harness(rows=8)
    h.renderer.draw(FakeDock(["dock-1", "dock-2"]))
    assert h.screen.lines()[-2:] == ["dock-1", "dock-2"]
    assert len(h.screen.lines()) == 8


def test_transcript_fills_the_space_above_the_dock():
    h = Harness(rows=8, entries=tuple(f"line{i}" for i in range(1, 21)))
    h.renderer.draw(FakeDock(["dock"]))
    # 视口 7 行，跟随末尾 → 显示最后 7 条
    assert h.screen.lines()[:7] == [f"line{i}" for i in range(14, 21)]


def test_short_transcript_leaves_blank_rows_not_garbage():
    h = Harness(rows=8, entries=("only",))
    h.renderer.draw(FakeDock(["dock"]))
    assert h.screen.lines()[0] == "only"
    assert h.screen.lines()[1:7] == [""] * 6


def test_viewport_keeps_at_least_one_row_when_the_dock_is_huge():
    h = Harness(rows=5)
    h.renderer.draw(FakeDock([f"d{i}" for i in range(10)]))
    assert len(h.screen.lines()) == 5
    assert h.screen.lines()[0] != ""          # transcript 还剩至少 1 行


def test_second_frame_only_rewrites_changed_rows():
    h = Harness(rows=6)
    h.renderer.draw(FakeDock(["dock"]))
    h.writes.clear()
    h.renderer.draw(FakeDock(["dock-changed"]))
    out = h.last()
    assert "\x1b[6;1H" in out                  # dock 那行（1-indexed）
    assert "\x1b[1;1H" not in out              # 没变的 transcript 行不该被重写


def test_unchanged_frame_writes_no_rows_at_all():
    h = Harness(rows=6)
    h.renderer.draw(FakeDock(["dock"]))
    h.writes.clear()
    h.renderer.draw(FakeDock(["dock"]))
    assert "\x1b[2K" not in h.last()


def test_never_clears_the_screen():
    """`2J` 会让屏幕在整个渲染耗时里全黑（CC 注释：render 可能要 ~80ms）。"""
    h = Harness()
    h.renderer.draw(FakeDock(["dock"]))
    h.renderer.draw(FakeDock(["other"]))
    assert "\x1b[2J" not in "".join(h.writes)


def test_never_re_enters_alt_screen():
    """重发 `?1049h` 会清屏闪白（iTerm2 与 Terminal.app 实测）。进 alt 归 terminal 层管。"""
    h = Harness()
    h.renderer.draw(FakeDock(["dock"]))
    h.renderer.draw(FakeDock(["other"]))
    assert "?1049" not in "".join(h.writes)


def test_every_frame_is_wrapped_in_synchronized_output():
    h = Harness()
    h.renderer.draw(FakeDock(["dock"]))
    assert h.last().startswith("\x1b[?2026h")
    assert h.last().endswith("\x1b[?2026l")


def test_cursor_marker_places_the_hardware_cursor_and_shows_it():
    h = Harness(rows=6)
    h.renderer.draw(FakeDock(["ab" + CURSOR_MARKER + "cd"]))
    assert "\x1b[6;3H" in h.last()             # 第 6 行第 3 列
    assert h.last().rstrip("\x1b[?2026l").endswith("\x1b[?25h")
    assert CURSOR_MARKER not in h.screen.lines()[5]


def test_no_marker_hides_the_cursor():
    h = Harness()
    h.renderer.draw(FakeDock(["dock"]))
    assert "\x1b[?25l" in h.last()


def test_cursor_column_counts_chinese_as_two_columns():
    h = Harness(rows=6, cols=20)
    h.renderer.draw(FakeDock(["中文" + CURSOR_MARKER + "x"]))
    assert "\x1b[6;5H" in h.last()


def test_lines_are_truncated_to_the_terminal_width():
    h = Harness(cols=8, rows=4, entries=("abcdefghijklmno",))
    h.renderer.draw(FakeDock(["dock"]))
    for line in h.screen.lines():
        assert len(line) <= 8


def test_resize_repaints_every_row_and_still_does_not_clear():
    h = Harness(cols=20, rows=6)
    h.renderer.draw(FakeDock(["dock"]))
    h.resize(30, 5)
    h.writes.clear()
    h.renderer.draw(FakeDock(["dock"]))
    out = h.last()
    for row in range(1, 6):
        assert f"\x1b[{row};1H" in out
    assert "\x1b[2J" not in out


def test_scroll_position_is_reflected_in_the_frame():
    h = Harness(rows=6, entries=tuple(f"line{i}" for i in range(1, 21)))
    h.renderer.draw(FakeDock(["dock"]))
    assert h.screen.lines()[0] == "line16"
    h.scroll.page_up()
    h.renderer.draw(FakeDock(["dock"]))
    assert h.screen.lines()[0] == "line15"


def test_dock_stays_put_while_the_transcript_scrolls():
    h = Harness(rows=6, entries=tuple(f"line{i}" for i in range(1, 21)))
    h.renderer.draw(FakeDock(["dock"]))
    h.scroll.scroll_by(-3)
    h.renderer.draw(FakeDock(["dock"]))
    assert h.screen.lines()[5] == "dock"


# --- resize 与重入（交付前反向对照在真 iTerm2 里撞出来的）--------------------


def test_a_redraw_triggered_from_inside_a_write_does_not_interleave():
    """`SIGWINCH` 处理器会在一帧**写到一半**时调 `app.refresh()`。

    两帧的字节交错写出去，屏幕就是花的；而后一帧还会把 `_previous` 覆盖成
    「已经画好了」，于是下一帧的 diff 以为没变、再也修不回来。
    真 iTerm2 里的症状是 resize 之后顶部残留一行**主屏**的内容
    （features/13 evidence 交付前那次）。
    """
    h = Harness(rows=6)
    h.renderer.draw(FakeDock(["dock"]))
    depth = {"max": 0, "now": 0}
    original = h._write

    def reentrant(data):
        depth["now"] += 1
        depth["max"] = max(depth["max"], depth["now"])
        original(data)
        if depth["now"] == 1 and not depth.get("done"):
            depth["done"] = True
            h.renderer.draw(FakeDock(["dock-2"]))     # 信号处理器插进来
        depth["now"] -= 1

    h._write = reentrant
    h.renderer.write = reentrant
    h.renderer._write = reentrant
    h.renderer.draw(FakeDock(["dock-3"]))
    assert depth["max"] == 1, "一帧还没写完就写了下一帧"


def test_resize_forces_a_full_repaint_even_if_the_frame_is_identical():
    """终端**自己**会在 resize 时挪动内容（实测 iTerm2 会把主屏的行混进来）。

    所以「这一帧与上一帧一样，那就什么都不用写」在 resize 之后**不成立**——
    上一帧记的是 pai 以为屏幕上有什么，而终端刚刚背着它改过。
    """
    h = Harness(rows=6)
    h.renderer.draw(FakeDock(["dock"]))
    h.renderer.invalidate()                  # resize 的通知
    h.writes.clear()
    h.renderer.draw(FakeDock(["dock"]))      # 内容一模一样
    out = h.last()
    for row in range(1, 7):
        assert f"\x1b[{row};1H" in out
