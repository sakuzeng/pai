"""测试基建自身的测试。

模拟器错了会让被测代码的测试**假绿**，所以它自己也得有测试——
这是 concepts/mutation-testing-pitfalls.md 那条「注错了和没测住现象一样」的同款风险。
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
