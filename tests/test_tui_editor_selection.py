"""输入框里的拖选（feature 16 追加）。

**这是接管鼠标欠下的最后一笔**：终端原生的拖选被我们拿走了，
transcript 那边补上了（T4/T5），而输入框一直没有——用户在里面既选不中、
也复制不走。补它需要给 `LineEditor` 一个它从来没有的东西：**选区**。
"""

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.editor import LineEditor
from pai.tui.keys import Key, KeyDecoder
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript

REVERSE, UNREVERSE = "\x1b[7m", "\x1b[27m"


# --- 编辑器层 -------------------------------------------------------------


def test_point_at_maps_row_and_column_to_a_character_index():
    editor = LineEditor()
    editor.set_text("中文abc")
    assert editor.point_at(0, 0) == 0
    assert editor.point_at(0, 4) == 2          # 两个中文 = 4 列
    assert editor.point_at(0, 99) == 5         # 超出末尾 → 末尾


def test_point_at_across_lines():
    editor = LineEditor()
    editor.set_text("第一行\n第二行")
    assert editor.point_at(1, 0) == 4          # 「第一行」3 字 + 换行
    assert editor.point_at(1, 2) == 5


def test_selecting_and_reading_the_text():
    editor = LineEditor()
    editor.set_text("abcdefg")
    editor.start_selection(1)
    editor.extend_selection(4)
    assert editor.selected_text() == "bcd"


def test_selection_normalises_backwards_drags():
    editor = LineEditor()
    editor.set_text("abcdefg")
    editor.start_selection(5)
    editor.extend_selection(2)
    assert editor.selected_text() == "cde"


def test_a_bare_click_selects_nothing():
    editor = LineEditor()
    editor.set_text("abcdefg")
    editor.start_selection(3)
    assert editor.selected_text() == ""


def test_typing_clears_the_selection():
    """选中一段之后接着打字，选区必须消失——否则屏幕上会留一块假高亮。"""
    editor = LineEditor()
    editor.set_text("abcdefg")
    editor.start_selection(1)
    editor.extend_selection(4)
    editor.handle(Key("char", "x"))
    assert editor.selected_text() == ""


def test_the_selection_is_reversed_on_screen():
    editor = LineEditor()
    editor.set_text("abcdefg")
    editor.start_selection(1)
    editor.extend_selection(4)
    line = editor.render(40)[0]
    assert REVERSE + "bcd" + UNREVERSE in line


def test_the_cursor_marker_survives_a_selection():
    """选区高亮不能把光标标记吃掉——吃掉的话中文 IME 候选框会飘走。"""
    from pai.tui.component import CURSOR_MARKER

    editor = LineEditor()
    editor.set_text("abcdefg")
    editor.start_selection(1)
    editor.extend_selection(4)
    assert CURSOR_MARKER in editor.render(40)[0]


def test_selection_spanning_two_lines():
    editor = LineEditor()
    editor.set_text("第一行\n第二行")
    editor.start_selection(1)
    editor.extend_selection(5)
    assert editor.selected_text() == "一行\n第"


# --- 接线：在输入框里拖 ---------------------------------------------------


def _app(rows=12, cols=60):
    transcript, scroll, selection = Transcript(), ScrollState(), Selection()
    renderer = AltScreenRenderer(write=lambda s: None, width=lambda: cols,
                                 height=lambda: rows, transcript=transcript,
                                 scroll=scroll, selection=selection)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll,
                 selection=selection)
    return app, renderer


def _feed(app, data):
    return app.feed(data, KeyDecoder())


def test_dragging_inside_the_input_box_selects_text():
    app, renderer = _app()
    app.editor.set_text("hello world")
    app.refresh()
    row = renderer.input_row
    _feed(app, f"\x1b[<0;3;{row + 1}M".encode())        # 按下在第 0 列（提示符占 2 列）
    _feed(app, f"\x1b[<32;8;{row + 1}M".encode())       # 拖到第 5 列
    assert app.editor.selected_text() == "hello"


def test_releasing_copies_the_input_selection():
    app, renderer = _app()
    app.editor.set_text("hello world")
    app.refresh()
    row = renderer.input_row
    _feed(app, f"\x1b[<0;3;{row + 1}M".encode()
          + f"\x1b[<32;8;{row + 1}M".encode()
          + f"\x1b[<0;8;{row + 1}m".encode())
    assert app.dock.has_notice()


def test_a_new_press_in_the_input_box_clears_the_old_selection():
    app, renderer = _app()
    app.editor.set_text("hello world")
    app.refresh()
    row = renderer.input_row
    _feed(app, f"\x1b[<0;3;{row + 1}M".encode() + f"\x1b[<32;8;{row + 1}M".encode())
    _feed(app, f"\x1b[<0;5;{row + 1}M".encode())
    assert app.editor.selected_text() == ""


def test_dragging_in_the_input_box_does_not_touch_the_transcript_selection():
    app, renderer = _app()
    app.commit("历史内容")
    app.editor.set_text("hello world")
    app.refresh()
    row = renderer.input_row
    _feed(app, f"\x1b[<0;3;{row + 1}M".encode() + f"\x1b[<32;8;{row + 1}M".encode())
    assert not app.selection.has_selection


# --- 又一轮真跑打回来的 ---------------------------------------------------


def test_typing_over_a_selection_replaces_it():
    """用户：「输入框选中之后为什么删除不了选中文本」。

    选中一段之后打字/退格，应该**先把选中的删掉**——这是所有编辑器的通行行为，
    而 pai 原来是「一按键就清选区」，于是退格只删掉光标前一个字。
    """
    editor = LineEditor()
    editor.set_text("hello world")
    editor.start_selection(0)
    editor.extend_selection(5)
    editor.handle(Key("char", "X"))
    assert editor.text == "X world"
    assert editor.cursor == 1


def test_backspace_over_a_selection_deletes_the_selection():
    editor = LineEditor()
    editor.set_text("hello world")
    editor.start_selection(0)
    editor.extend_selection(6)
    editor.handle(Key("backspace"))
    assert editor.text == "world"
    assert editor.cursor == 0
    assert editor.selected_text() == ""


def test_delete_over_a_selection_deletes_the_selection():
    editor = LineEditor()
    editor.set_text("hello world")
    editor.start_selection(5)
    editor.extend_selection(11)
    editor.handle(Key("delete"))
    assert editor.text == "hello"


def test_pasting_over_a_selection_replaces_it():
    editor = LineEditor()
    editor.set_text("hello world")
    editor.start_selection(0)
    editor.extend_selection(5)
    editor.handle(Key("paste", "你好"))
    assert editor.text == "你好 world"


def test_an_arrow_key_only_clears_the_selection():
    editor = LineEditor()
    editor.set_text("hello")
    editor.start_selection(0)
    editor.extend_selection(3)
    editor.handle(Key("right"))
    assert editor.text == "hello"
    assert editor.selected_text() == ""


def test_a_backwards_drag_in_the_transcript_still_copies():
    """用户：「我从后往前移动复制不了」。

    真因不在方向上，在**手势路由**：`_input_click` 判「这次松开归不归输入框」时
    看的是「编辑器手里还有没有锚点」，而锚点在上一次点输入框之后就一直留着——
    于是 transcript 的松开被输入框吞掉，选区永远不结束、也就不复制。
    """
    app, renderer = _app()
    app.commit("第一行内容")
    app.commit("第二行内容")
    app.refresh()
    _feed(app, f"\x1b[<0;3;{renderer.input_row + 1}M".encode())   # 先点一下输入框
    _feed(app, b"\x1b[<0;6;2M")                                   # 再从第 2 行按下
    _feed(app, b"\x1b[<32;1;1M")                                  # 往**上**拖
    _feed(app, b"\x1b[<0;1;1m")                                   # 松开
    assert app.dock.has_notice()


def test_the_copy_notice_sits_above_the_dock_border():
    """用户：「应该在用户框的上面而不是里面」（对照 CC 的截图）。

    pai 的 dock 顶上有一条分隔线——提示落在分隔线**下面**就成了「框里」。
    """
    app, _ = _app(cols=40)
    app.dock.set_notice("已复制 3 行")
    lines = app.root.render(40)
    notice = next(i for i, line in enumerate(lines) if "已复制" in line)
    rule = next(i for i, line in enumerate(lines) if "─" * 10 in line)
    assert notice < rule


def test_point_at_display_maps_wrapped_rows(feature33=None):
    """21 遗留 1：折行后「显示行 ≠ 逻辑行」，point_at 按逻辑行换算会把
    点第二段定位到错误字符。point_at_display 按 render 同一套折行几何换算，
    列参数含前缀（由它自己按行减，续行前缀宽可以与 prompt 不同）。"""
    editor = LineEditor(prompt="> ")            # 前缀 2 列
    editor.set_text("abcdefghij")               # width=7 → room=5 → ab cde|fghij
    # 显示行 0 = abcde，显示行 1 = fghij（room = 7-2 = 5）
    assert editor.point_at_display(0, 2, 7) == 0    # 前缀后第 0 列 → 'a'
    assert editor.point_at_display(1, 2, 7) == 5    # 第二段第 0 列 → 'f'
    assert editor.point_at_display(1, 4, 7) == 7    # 第二段第 2 列 → 'h'
    assert editor.point_at_display(9, 99, 7) == 10  # 越界行/列 → 末尾


def test_point_at_display_counts_wide_chars_by_columns():
    editor = LineEditor(prompt="> ")
    editor.set_text("你好世界谢谢")               # 每字 2 列
    # width=8 → room=6 → 每显示行 3 个汉字
    assert editor.point_at_display(1, 2, 8) == 3    # 第二段第 0 列 → 「界」
    assert editor.point_at_display(1, 4, 8) == 4


def test_point_at_display_handles_continuation_lines():
    editor = LineEditor(prompt="> ", continuation="    ")   # 续行前缀 4 列
    editor.set_text("first\nsecond")
    # 不折（width 大）：显示行 1 = 续行，列要按续行前缀（4）减，不是 prompt（2）
    assert editor.point_at_display(1, 4, 40) == 6   # 前缀后第 0 列 → 's'
    assert editor.point_at_display(1, 6, 40) == 8
