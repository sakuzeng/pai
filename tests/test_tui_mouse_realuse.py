"""用户真跑打回来的四条（feature 16 交付前）。

四条里最值得记的是**第 4 条**：点击展开在 T7 里 12 条测试全绿，
而真实的工具输出**根本点不开**——因为 T7 的测试自己造了个 `_tool_entry()` fixture，
生产路径上 `on_event` 提交的仍是不可展开的 `dynamic_entry`。
**测试造了一个「本该是被测对象」的替身，于是测的是替身。**
"""

from typing import List

from pai.core.events import ToolEnd
from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.keys import KeyDecoder
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


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


def _press(row, col=0):
    return f"\x1b[<0;{col + 1};{row + 1}M".encode()


def _drag(row, col):
    return f"\x1b[<32;{col + 1};{row + 1}M".encode()


def _release(row, col=0):
    return f"\x1b[<0;{col + 1};{row + 1}m".encode()


def _tool_event(name="bash", result="total 8\na\nb\nc"):
    return ToolEnd(tool_call_id="1", name=name, args={"command": "ls -la"},
                   result=result, is_error=False)


# --- 1. 松开之后高亮不该赖着不走 -----------------------------------------


def test_the_highlight_goes_away_after_the_copy():
    """用户：「鼠标已经不按了但是还在选中」。

    照 CC 的 `finishSelection` 注释：选区留着是为了能复制——**复制完就该清掉**。
    留着的话，用户下次去看屏幕会以为自己还选着东西。
    """
    app, _ = _app()
    app.commit("可以复制的一整行文本")
    app.refresh()
    _feed(app, _press(0, 0) + _drag(0, 5) + _release(0, 5))
    assert not app.selection.has_selection


def test_a_bare_click_does_not_leave_a_stale_anchor():
    app, _ = _app()
    app.commit("一行")
    app.refresh()
    _feed(app, _press(0, 0) + _release(0, 0))
    assert not app.selection.has_selection


# --- 2. 复制提示：位置与消失 ---------------------------------------------


def test_the_copy_notice_is_right_aligned_above_the_input_row():
    """用户：「应该和 cc 一样放到用户框的右上角」。"""
    app, _ = _app(cols=40)
    app.dock.set_notice("已复制 3 行")
    lines = app.root.render(40)
    notice_rows = [i for i, line in enumerate(lines) if "已复制" in line]
    assert notice_rows, "提示行没出现"
    row = notice_rows[0]
    assert lines[row].startswith(" ")            # 右对齐：左边是空白
    assert any("›" in line for line in lines[row + 1:]), "提示应在输入行**上方**"


def test_the_copy_notice_disappears_by_itself():
    """用户：「这里面这个复制一直都在」——它现在永远不消失。"""
    app, _ = _app()
    clock = Clock()
    app.dock._now = clock
    app.dock.set_notice("已复制 3 行")
    assert "已复制" in "\n".join(app.root.render(40))
    clock.now += 5
    assert "已复制" not in "\n".join(app.root.render(40))


def test_a_pending_notice_keeps_the_ticker_alive():
    """不重画的话，提示到期了屏幕上还留着——空闲时必须有人来擦。"""
    app, _ = _app()
    clock = Clock()
    app.dock._now = clock
    app.dock.set_notice("已复制 3 行")
    assert app.needs_tick()
    clock.now += 5
    assert not app.needs_tick()


# --- 3. 输入行：点哪儿光标就去哪儿 ---------------------------------------


def test_clicking_the_input_row_moves_the_cursor():
    """用户：「鼠标也点不位置」。拿走鼠标之后，连终端原生的点击定位也没了。"""
    app, renderer = _app()
    app.editor.set_text("一二三abc")
    app.refresh()
    row = renderer.input_row
    assert row is not None
    _feed(app, _press(row, 2 + 4))               # 提示符占 2 列，再往后 4 列
    assert app.editor.cursor == 2                # 两个中文 = 4 列


def test_clicking_past_the_end_of_the_text_goes_to_the_end():
    app, renderer = _app()
    app.editor.set_text("abc")
    app.refresh()
    _feed(app, _press(renderer.input_row, 50))
    assert app.editor.cursor == 3


def test_clicking_the_input_row_does_not_start_a_transcript_selection():
    app, renderer = _app()
    app.commit("历史内容")
    app.editor.set_text("abc")
    app.refresh()
    _feed(app, _press(renderer.input_row, 3) + _drag(renderer.input_row, 6)
          + _release(renderer.input_row, 6))
    assert not app.selection.has_selection


# --- 4. 真实的工具输出要能点开 -------------------------------------------


def test_a_real_tool_result_is_expandable():
    """**T7 的 12 条测试没抓到这条**：它们自己造了个可展开的 fixture，
    而生产路径上提交的是不可展开的 `dynamic_entry`。"""
    app, _ = _app()
    app.on_event(_tool_event())
    entry = app.transcript.owner_at(60, 0)
    assert entry is not None and entry.expandable


def test_clicking_a_real_tool_result_expands_it():
    app, _ = _app()
    app.on_event(_tool_event())
    app.refresh()
    before = app.transcript.total_lines(60)
    _feed(app, _press(0, 3) + _release(0, 3))
    assert app.transcript.total_lines(60) > before


def test_the_collapsed_hint_only_advertises_the_shortcut():
    """**这条断言被后来「照 CC」的决定改过**（原来断言的是提示语里有「点击」）。

    CC 的折叠块**也能点**，但它的提示语里只写快捷键
    （`… +12 lines (ctrl+o to expand)`）。跟它保持一致：
    能点是能力，提示语里不再多说一句——一行里塞两个入口反而让人读不懂
    （用户看到我编的 `^O/点击展开` 时的第一反应就是「这里是什么」）。
    """
    app, _ = _app()
    app.on_event(_tool_event())
    line = app.transcript.slice(60, 0, 1)[0]
    assert "^O" in line and "点击" not in line


def test_a_single_line_tool_result_is_not_expandable():
    """没有被折叠的行就没什么可展开的——不该给用户一个点了没反应的东西。"""
    app, _ = _app()
    app.on_event(_tool_event(result="ok"))
    entry = app.transcript.owner_at(60, 0)
    assert entry is not None and not entry.expandable


# --- 5. 松手之后高亮还跟着鼠标走（第二轮真跑打回来的）-------------------


def test_motion_without_a_button_is_not_a_drag():
    """SGR 里 `button=35`（32|3）**低两位 3 表示「没有按键」**——那是纯移动，不是拖动。

    把它当拖动的后果正是用户看到的：松手之后高亮还跟着鼠标走。
    **这条也定了一件之前「未定」的事**：1003 确实上报无按键移动
    （features/16 evidence 第 4 条当时测到 0，是因为那两段在滚轮而不是移动指针）。
    """
    from pai.tui.keys import KeyDecoder

    (event,) = [k.mouse for k in KeyDecoder().feed(b"\x1b[<35;5;3M")]
    assert event.kind == "move"


def test_moving_the_mouse_after_release_does_not_extend_the_selection():
    app, _ = _app()
    app.commit("第一行内容")
    app.commit("第二行内容")
    app.refresh()
    _feed(app, _press(0, 0) + _drag(0, 4) + _release(0, 4))
    _feed(app, b"\x1b[<35;20;2M")                # 松手之后随便动动鼠标
    assert not app.selection.has_selection


def test_releasing_over_the_input_row_still_finishes_the_drag():
    """从 transcript 拖到输入行上松手——**释放事件不能被输入行吞掉**，
    否则选区永远停在「拖动中」，之后鼠标一动高亮就跟着跑。"""
    app, renderer = _app()
    app.commit("一行可以选的内容")
    app.refresh()
    _feed(app, _press(0, 0) + _drag(0, 5))
    _feed(app, _release(renderer.input_row, 5))
    assert not app.selection.dragging


# --- 6. 展开之后的样子 ---------------------------------------------------


def test_expanding_keeps_the_command_visible():
    """用户：「点开之后应该是这样的」——CC 展开后**命令还在**，输出挂在它下面。
    现在的做法把整行换成了「bash 的完整输出：」，命令没了。"""
    app, _ = _app(cols=60)
    app.on_event(_tool_event(result="total 8\naaa\nbbb"))
    app.refresh()
    _feed(app, _press(0, 3) + _release(0, 3))
    lines = app.transcript.slice(60, 0, 20)
    assert "ls -la" in lines[0]                  # 命令还在第一行
    assert "(^O 收起)" in lines[0]                # 与折叠态同一套措辞（照 CC）


def test_expanded_output_is_indented_under_the_command():
    """输出要**挂在命令下面**（缩进 + 一个引出符），否则与正文混成一片。"""
    app, _ = _app(cols=60)
    app.on_event(_tool_event(result="total 8\naaa"))
    app.refresh()
    _feed(app, _press(0, 3) + _release(0, 3))
    body = app.transcript.slice(60, 0, 20)[1:]
    assert body[0].lstrip().startswith("⎿")
    assert body[0].startswith("  ")
    assert all(line.startswith("  ") for line in body if line.strip())


# --- 7. 照 CC 的两处形状（用户对照 CC 提出）-----------------------------


def test_pasted_multiline_input_has_no_continuation_marker():
    """用户对照 CC：粘贴多行进输入框，CC **没有**每行戴一个续行标记。

    pai 原来给第 2 行起戴 `… `（feature 12 为 `\\` 续行设计的），
    多行粘贴时它就成了一列噪音。改成**与提示符等宽的空白**，对齐但不出声。
    """
    app, _ = _app()
    app.editor.set_text("第一行\n第二行\n第三行")
    lines = app.editor.render(60)
    assert lines[0].startswith("›") or "›" in lines[0]
    for line in lines[1:]:
        assert "…" not in line
    # 续行与首行的正文**左对齐**
    from pai.modes.statusline import _ESCAPES, display_width
    head = _ESCAPES.sub("", lines[0])
    tail = _ESCAPES.sub("", lines[1])
    assert display_width(head) - display_width(head.lstrip("› ")) == \
        display_width(tail) - display_width(tail.lstrip(" "))


def test_the_collapsed_hint_follows_ccs_shape():
    """用户：「这里是什么呢，能参照下 cc 的实现吗」——指的是我自己编的 `^O/点击展开`。

    CC 的原文（`FileWriteTool/UI.tsx` + `CtrlOToExpand.tsx`）：
    `… +12 lines (ctrl+o to expand)`——**「+N 行」+ 括号里的快捷键**，
    不提「点击」（虽然 CC 的折叠块也能点）。
    """
    app, _ = _app(cols=80)
    app.on_event(_tool_event(result="\n".join(f"row{i}" for i in range(13))))
    line = app.transcript.slice(80, 0, 1)[0]
    assert "+12 行" in line
    assert "(^O 展开)" in line
    assert "/" not in line.split("+12 行")[1]      # 那个让人误读的斜杠没了
