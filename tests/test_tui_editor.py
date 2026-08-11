"""T2：行编辑器。纯状态机——收按键、吐新状态，不碰终端。

替掉 readline。**已知回退**：`Ctrl+R` 增量搜索不做（拍板时就知道，已登记 TODO）。
"""

import pytest

from pai.modes.statusline import display_width
from pai.tui.component import CURSOR_MARKER
from pai.tui.editor import LineEditor
from pai.tui.keys import KeyDecoder


def press(editor, data):
    """把真实字节喂给编辑器——测试要走与真终端同一条解码路径。"""
    submitted = []
    for key in KeyDecoder().feed(data):
        result = editor.handle(key)
        if result is not None:
            submitted.append(result)
    return submitted


def test_typing_inserts_text():
    e = LineEditor()
    press(e, "你好abc".encode("utf-8"))
    assert e.text == "你好abc"


def test_enter_submits_and_clears():
    e = LineEditor()
    press(e, b"hi")
    assert press(e, b"\r") == ["hi"]
    assert e.text == ""


def test_backspace_deletes_before_cursor():
    e = LineEditor()
    press(e, b"abc\x7f")
    assert e.text == "ab"


def test_backspace_deletes_a_whole_wide_char():
    """一个中文是一个字符，不是两个——退格删一次就该没了。"""
    e = LineEditor()
    press(e, "中文".encode("utf-8"))
    press(e, b"\x7f")
    assert e.text == "中"


def test_left_right_and_insert_in_the_middle():
    e = LineEditor()
    press(e, b"abd\x1b[D")
    press(e, b"c")
    assert e.text == "abcd"


def test_home_and_end():
    e = LineEditor()
    press(e, b"abc\x1b[HX")
    assert e.text == "Xabc"
    press(e, b"\x1b[FY")
    assert e.text == "Xabcy".replace("y", "Y")


def test_delete_removes_under_cursor():
    e = LineEditor()
    press(e, b"abc\x1b[H\x1b[3~")
    assert e.text == "bc"


def test_ctrl_a_and_ctrl_e():
    e = LineEditor()
    press(e, b"abc\x01X")
    assert e.text == "Xabc"
    press(e, b"\x05Y")
    assert e.text == "XabcY"


def test_ctrl_u_kills_to_start_ctrl_k_kills_to_end():
    e = LineEditor()
    press(e, b"abcdef\x1b[D\x1b[D\x15")
    assert e.text == "ef"
    e2 = LineEditor()
    press(e2, b"abcdef\x1b[D\x1b[D\x0b")
    assert e2.text == "abcd"


def test_ctrl_w_kills_previous_word():
    e = LineEditor()
    press(e, b"hello world\x17")
    assert e.text == "hello "


def test_ctrl_w_at_start_is_a_noop():
    e = LineEditor()
    press(e, b"\x17")
    assert e.text == ""


def test_word_navigation():
    e = LineEditor()
    press(e, b"one two\x1bb")
    press(e, b"X")
    assert e.text == "one Xtwo"


def test_paste_inserts_at_cursor_without_submitting():
    e = LineEditor()
    press(e, b"ab\x1b[D")
    assert press(e, b"\x1b[200~XY\x1b[201~") == []
    assert e.text == "aXYb"


def test_cursor_marker_sits_at_the_cursor_and_is_zero_width():
    e = LineEditor(prompt="› ")
    press(e, "中文ab".encode("utf-8"))
    press(e, b"\x1b[D")                      # 光标退到 b 之前
    line = e.render(40)[0]
    assert CURSOR_MARKER in line
    before = line.split(CURSOR_MARKER)[0]
    # 「› 」2 列 + 「中文」4 列 + 「a」1 列 = 7
    assert display_width(before) == 7
    assert display_width(line) == display_width(line.replace(CURSOR_MARKER, ""))


def test_render_shows_prompt_and_text():
    e = LineEditor(prompt="› ")
    press(e, b"hi")
    assert e.render(40)[0].replace(CURSOR_MARKER, "") == "› hi"


def test_trailing_backslash_continues_instead_of_submitting():
    """保留 05 已交付的续行语义（`\\` + Enter），不做多行编辑器。"""
    e = LineEditor()
    assert press(e, b"first\\\r") == []
    press(e, b"second")
    assert press(e, b"\r") == ["first\nsecond"]


def test_continuation_lines_render_with_their_own_prompt():
    e = LineEditor(prompt="› ", continuation="… ")
    press(e, b"a\\\rb")
    lines = [ln.replace(CURSOR_MARKER, "") for ln in e.render(40)]
    assert lines == ["› a", "… b"]


def test_history_up_and_down():
    e = LineEditor(history=["first", "second"])
    press(e, b"\x1b[A")
    assert e.text == "second"
    press(e, b"\x1b[A")
    assert e.text == "first"
    press(e, b"\x1b[B")
    assert e.text == "second"


def test_history_down_past_the_end_restores_the_draft():
    """翻上去看看又翻回来，正在打的那半句不能丢。"""
    e = LineEditor(history=["old"])
    press(e, b"draft")
    press(e, b"\x1b[A")
    assert e.text == "old"
    press(e, b"\x1b[B")
    assert e.text == "draft"


def test_history_up_at_the_top_stays_put():
    e = LineEditor(history=["only"])
    press(e, b"\x1b[A\x1b[A")
    assert e.text == "only"


def test_submitting_resets_history_position():
    e = LineEditor(history=["old"])
    press(e, b"\x1b[A")
    press(e, b"\r")
    press(e, b"\x1b[A")
    assert e.text == "old"


def test_unknown_key_is_ignored():
    e = LineEditor()
    press(e, b"ab\x1b[15~")
    assert e.text == "ab"


def test_empty_enter_submits_empty_string():
    """空行提交由上层决定怎么处理（今天的 REPL 是忽略），编辑器不替它做主。"""
    e = LineEditor()
    assert press(e, b"\r") == [""]


@pytest.mark.parametrize("text", ["", "a", "中文", "a中b", "🎉"])
def test_render_width_never_exceeds_terminal(text):
    e = LineEditor()
    press(e, text.encode("utf-8"))
    for line in e.render(8):
        assert display_width(line) <= 8
