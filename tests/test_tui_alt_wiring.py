"""接线（feature 13 T6）：两种渲染器共用同一个 app。

**12 交付的 main-screen 路径行为必须逐字节不变**——这是本 task 最容易砸的地方，
而砸了之后不会有任何东西自己变红（改坏的是「另一条路」）。
"""

from typing import List

from pai.core.events import AssistantMessage, ToolEnd
from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.keys import KeyDecoder
from pai.tui.renderer import DockRenderer
from pai.tui.scroll import ScrollState
from pai.tui.transcript import Transcript


def _alt_app(cols=30, rows=10, color=False):
    writes: List[str] = []
    transcript, scroll = Transcript(), ScrollState()
    renderer = AltScreenRenderer(
        write=writes.append, width=lambda: cols, height=lambda: rows,
        transcript=transcript, scroll=scroll)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll, color=color)
    return app, writes, transcript, scroll


def _dock_app(cols=30):
    writes: List[str] = []
    renderer = DockRenderer(write=writes.append, width=lambda: cols)
    return TuiApp(renderer=renderer), writes


# --- 落点分流 --------------------------------------------------------------


def test_alt_mode_keeps_committed_content_in_the_transcript():
    app, _, transcript, _ = _alt_app()
    app.commit("你好")
    assert transcript.total_lines(30) == 1


def test_dock_mode_hands_content_to_the_terminal_and_keeps_nothing():
    app, writes = _dock_app()
    app.commit("你好")
    assert "你好" in "".join(writes)
    assert app.transcript.total_lines(30) == 0     # main 下不留，留了就是白涨内存


def test_dock_mode_output_is_unchanged_by_the_entry_refactor():
    """12 交付的形态：内容当普通输出打出去、dock 在下面重画。"""
    app, writes = _dock_app()
    app.commit(["第一行", "第二行"])
    out = "".join(writes)
    assert "第一行\r\n第二行\r\n" in out


def test_answers_are_wrapped_to_width_in_alt_mode():
    """alt 屏关掉了终端的自动折行——不自己折就是被截断，内容**丢了**。"""
    app, _, transcript, _ = _alt_app(cols=10)
    app.on_event(AssistantMessage(content="a" * 25))
    assert transcript.total_lines(10) >= 3


def test_tool_lines_re_render_at_the_new_width():
    """工具行按宽度截断——存成行的话，窗口变宽后它永远保持着旧宽度的省略号。"""
    app, _, transcript, _ = _alt_app(cols=20)
    app.on_event(ToolEnd(tool_call_id="1", name="bash",
                         args={"command": "echo " + "x" * 200},
                         result="ok", is_error=False))
    narrow = transcript.slice(20, 0, 5)
    wide = transcript.slice(90, 0, 5)
    assert narrow != wide
    assert all(len(line) <= 200 for line in wide)


def test_user_input_band_re_renders_at_the_new_width():
    # 色带要**铺满整行**，所以必须开色才看得出宽度依赖（无色时它就是一行普通文字）
    app, _, transcript, _ = _alt_app(cols=20, color=True)
    app.editor.text = "问一句"
    app._submitted("问一句")
    assert transcript.slice(20, 0, 9) != transcript.slice(60, 0, 9)


# --- 滚动键 ---------------------------------------------------------------


def _feed(app, data: bytes):
    return app.feed(data, KeyDecoder())


def test_page_keys_scroll_the_transcript_in_alt_mode():
    app, _, transcript, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    assert scroll.following_end
    _feed(app, b"\x1b[5~")                      # PgUp
    assert not scroll.following_end
    top = scroll.scroll_top
    _feed(app, b"\x1b[6~")                      # PgDn
    assert scroll.scroll_top > top


def test_ctrl_home_and_ctrl_end_jump_to_the_ends():
    app, _, _, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    _feed(app, b"\x1b[1;5H")
    assert scroll.scroll_top == 0
    _feed(app, b"\x1b[1;5F")
    assert scroll.following_end


def test_plain_home_and_end_still_belong_to_the_editor():
    """`Home`/`End` 是行首行尾，不许被滚动抢走（照 CC：滚动走 Ctrl 组合）。"""
    app, _, _, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    _feed(app, "一二三".encode())
    _feed(app, b"\x1b[H")
    assert app.editor.cursor == 0
    assert scroll.following_end                 # 没有跳到 transcript 顶部


def test_scroll_keys_do_nothing_in_dock_mode():
    """main-screen 下滚动归终端，pai 不该假装自己能滚。

    断言「有没有路由到状态机」而不是「有没有写字节」——按任何键都会重画 dock，
    按字节数断言的话，测的是重画而不是滚动。
    """
    app, _ = _dock_app()

    class Spy:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            def record(*a, **kw):
                self.calls.append(name)
            return record

    app.scroll = spy = Spy()
    _feed(app, b"\x1b[5~")
    _feed(app, b"\x1b[1;5H")
    assert [c for c in spy.calls if c in ("page_up", "to_start")] == []


def test_typing_while_scrolled_up_does_not_yank_the_view_back():
    app, _, _, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    _feed(app, b"\x1b[5~")
    top = scroll.scroll_top
    _feed(app, "字".encode())
    assert scroll.scroll_top == top


def test_new_output_while_scrolled_up_does_not_yank_the_view_back():
    """本 task 的注入反证靶子：agent 还在说话，而用户正在读上面的历史。"""
    app, _, _, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    _feed(app, b"\x1b[5~")
    top = scroll.scroll_top
    app.commit("模型又说了一句")
    assert scroll.scroll_top == top


# --- 滚动指示 --------------------------------------------------------------


def test_status_line_shows_that_you_are_scrolled_up():
    app, _, _, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    assert "已上滚" not in app.dock.status_line(60)
    _feed(app, b"\x1b[5~")
    assert "已上滚" in app.dock.status_line(60)


def test_status_line_flags_unseen_content():
    app, _, _, scroll = _alt_app(rows=10)
    for i in range(40):
        app.commit(f"line{i}")
    app.refresh()
    _feed(app, b"\x1b[5~")
    assert "有新内容" not in app.dock.status_line(60)
    app.commit("新来的一句")
    assert "有新内容" in app.dock.status_line(60)
