"""测试基建自身的测试。

模拟器错了会让被测代码的测试**假绿**，所以它自己也得有测试——
这是 engineering/mutation-testing-pitfalls.md 那条「注错了和没测住现象一样」的同款风险。
"""

import pytest

from tests.tui_screen import VirtualScreen


def test_plain_text_and_newline():
    s = VirtualScreen(cols=10, rows=3)
    s.write("abc\r\ndef")
    assert s.visible() == ["abc", "def"]


def test_carriage_return_overwrites_in_place():
    s = VirtualScreen(cols=10, rows=3)
    s.write("abcdef\rXY")
    assert s.visible() == ["XYcdef"]


def test_clear_line_erases_whole_row():
    s = VirtualScreen(cols=10, rows=3)
    s.write("abcdef\r\x1b[2K")
    assert s.visible() == []


def test_cursor_up_and_down_move_between_rows():
    s = VirtualScreen(cols=10, rows=4)
    s.write("one\r\ntwo\r\nthree")
    s.write("\x1b[2A\rX")
    assert s.visible() == ["Xne", "two", "three"]


def test_wide_chars_take_two_columns():
    s = VirtualScreen(cols=10, rows=2)
    s.write("中文ab")
    assert s.visible() == ["中文ab"]
    assert s.col == 6


def test_newline_at_bottom_scrolls_into_scrollback():
    s = VirtualScreen(cols=10, rows=2)
    s.write("one\r\ntwo\r\nthree")
    assert s.scrollback == ["one"]
    assert s.visible() == ["two", "three"]
    assert s.logical_lines()[:3] == ["one", "two", "three"]


def test_synchronized_output_markers_are_transparent():
    s = VirtualScreen(cols=10, rows=2)
    s.write("\x1b[?2026habc\x1b[?2026l")
    assert s.visible() == ["abc"]


def test_absolute_column_is_one_indexed():
    s = VirtualScreen(cols=10, rows=2)
    s.write("abcdef\x1b[3GX")
    assert s.visible() == ["abXdef"]


def test_unknown_escape_raises_instead_of_being_ignored():
    """静默忽略会让测试对着「模拟器没看懂」的假象变绿。"""
    s = VirtualScreen(cols=10, rows=2)
    with pytest.raises(AssertionError):
        s.write("\x1b[99Z")


# --- feature 13：备用屏（alt-screen）---------------------------------------
#
# 模拟器不认 DECSET 1049 的话，alt-screen 一上线，录制回放出的图就是错的、
# e2e 全部失效——「让 AI 自己看得见界面」退回到让用户截图。所以先扩它。
# 行为以实测为准（features/13 evidence 说明.md），不以「常识」为准。


def _snapshot(screen):
    return [[None if c is None else (c.char, c.fg, c.bg) for c in row]
            for row in screen.cells()]


def test_alt_screen_starts_empty_and_hides_main():
    s = VirtualScreen(cols=10, rows=3)
    s.write("MAIN-1\r\nMAIN-2")
    s.write("\x1b[?1049h")
    assert s.visible() == []                     # 备用屏是空的
    s.write("ALT")
    assert s.visible() == ["ALT"]                # 且主屏内容看不见了


def test_leaving_alt_screen_restores_main_cell_for_cell():
    s = VirtualScreen(cols=10, rows=3)
    s.write("MAIN-1\r\n\x1b[31mMAIN-2\x1b[0m")
    before = _snapshot(s)
    s.write("\x1b[?1049h\x1b[2J\x1b[HALT-1\r\nALT-2\x1b[?1049l")
    assert _snapshot(s) == before                # 连样式一起逐格还原


def test_reentering_alt_screen_clears_it_and_homes_cursor():
    """**不是 no-op**：iTerm2 3.6.11 与 Terminal.app 470.2 实测都清屏 + 光标回原点。

    CC 源码里两处注释自相矛盾（`handleResize` 说会清、`reenterAltScreen()` 说是 no-op），
    实测站前者。写反了的后果是「自愈式重进 alt」闪白屏。
    """
    s = VirtualScreen(cols=10, rows=3)
    s.write("\x1b[?1049hALT-1\r\nALT-2")
    assert s.visible() == ["ALT-1", "ALT-2"]
    s.write("\x1b[?1049h")
    assert s.visible() == []
    assert (s.row, s.col) == (0, 0)


def test_alt_screen_saves_and_restores_the_cursor():
    s = VirtualScreen(cols=20, rows=4)
    s.write("one\r\ntwo\r\nabcdef")
    row, col = s.row, s.col
    s.write("\x1b[?1049h\x1b[5;3HX\x1b[?1049l")
    assert (s.row, s.col) == (row, col)


def test_alt_screen_scrolling_does_not_pollute_main_scrollback():
    """备用屏没有 scrollback——滚出去的行就是没了，不该混进主屏的历史。"""
    s = VirtualScreen(cols=10, rows=2)
    s.write("MAIN\r\n")
    s.write("\x1b[?1049hA\r\nB\r\nC")
    assert s.scrollback == []
    assert s.visible() == ["B", "C"]


def test_leaving_alt_when_not_in_alt_is_a_no_op():
    s = VirtualScreen(cols=10, rows=2)
    s.write("abc\x1b[?1049l")
    assert s.visible() == ["abc"]


def test_cursor_position_is_one_indexed_row_and_column():
    s = VirtualScreen(cols=10, rows=4)
    s.write("\x1b[3;5HX")
    assert s.visible() == ["", "", "    X"]


def test_cursor_position_defaults_to_home_and_clamps():
    s = VirtualScreen(cols=10, rows=3)
    s.write("abc\r\ndef\x1b[HX")
    assert s.visible() == ["Xbc", "def"]
    s.write("\x1b[99;99HY")               # 超界钳到最后一行最后一列
    assert s.lines()[2] == " " * 9 + "Y"


def test_erase_display_modes():
    s = VirtualScreen(cols=6, rows=3)
    s.write("aaa\r\nbbb\r\nccc\x1b[2;2H\x1b[0J")      # 清到屏尾
    assert s.visible() == ["aaa", "b"]
    s.write("\x1b[2J")                                # 整屏
    assert s.visible() == []
    s.write("\x1b[1;1Hxxx\r\nyyy\x1b[2;2H\x1b[1J")    # 清到屏首（**含**光标那一格）
    assert s.visible() == ["", "  y"]


def test_autowrap_off_truncates_at_the_right_edge():
    """`?7l` 是保命的第二道闸：一行超宽时**不折到下一行**去糟蹋下一行的内容。"""
    s = VirtualScreen(cols=5, rows=3)
    s.write("\x1b[?7labcdefgh\r\n2nd")
    assert s.visible() == ["abcde", "2nd"]
    s.write("\x1b[2J\x1b[H\x1b[?7habcdefgh")
    assert s.visible() == ["abcde", "fgh"]


def test_wide_char_at_the_edge_with_autowrap_off_is_dropped_not_split():
    s = VirtualScreen(cols=5, rows=2)
    s.write("\x1b[?7labcd中")
    assert s.visible() == ["abcd"]


def test_cursor_visibility_and_unrelated_private_modes_stay_no_ops():
    s = VirtualScreen(cols=10, rows=2)
    s.write("\x1b[?25labc\x1b[?25h\x1b[?2004h")
    assert s.visible() == ["abc"]
