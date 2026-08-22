"""滚轮接线（feature 16 T3）：滚的是 pai 自己的 transcript。

**这条 feature 的全部起点**：13 交付后用户往上滚，看到的是终端 scrollback 里
自己之前几次运行的残留——因为 pai 不发鼠标上报，滚轮穿透给了终端。
"""

from typing import List

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import WHEEL_LINES, TuiApp
from pai.tui.keys import KeyDecoder
from pai.tui.renderer import DockRenderer
from pai.tui.scroll import ScrollState
from pai.tui.transcript import Transcript, text_entry

WHEEL_UP = b"\x1b[<64;1;1M"
WHEEL_DOWN = b"\x1b[<65;1;1M"


def _alt_app(rows=10, lines=200):
    transcript, scroll = Transcript(), ScrollState()
    for i in range(lines):
        transcript.append(text_entry([f"line{i}"]))
    renderer = AltScreenRenderer(write=lambda s: None, width=lambda: 40,
                                 height=lambda: rows, transcript=transcript,
                                 scroll=scroll)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll)
    app.refresh()
    return app, scroll


def _feed(app, data):
    return app.feed(data, KeyDecoder())


def test_wheel_up_scrolls_the_transcript():
    app, scroll = _alt_app()
    before = scroll.scroll_top
    _feed(app, WHEEL_UP)
    assert scroll.scroll_top == before - WHEEL_LINES


def test_wheel_down_scrolls_back():
    app, scroll = _alt_app()
    _feed(app, WHEEL_UP * 5)
    mid = scroll.scroll_top
    _feed(app, WHEEL_DOWN)
    assert scroll.scroll_top == mid + WHEEL_LINES


def test_wheel_up_turns_off_following():
    """用户往回读历史时，新内容不许把他弹走——复用 feature 13 的状态机。"""
    app, scroll = _alt_app()
    assert scroll.following_end
    _feed(app, WHEEL_UP)
    assert not scroll.following_end


def test_scrolling_back_to_the_bottom_restores_following():
    app, scroll = _alt_app()
    _feed(app, WHEEL_UP * 3)
    _feed(app, WHEEL_DOWN * 20)
    assert scroll.following_end


def test_wheel_over_the_dock_still_scrolls_the_transcript():
    """pai 只有一个滚动区：指针在哪都滚它（照 pi 的「没人消费就给 primary」）。"""
    app, scroll = _alt_app(rows=10)
    before = scroll.scroll_top
    _feed(app, b"\x1b[<64;5;10M")          # 行 10 = dock 那一带
    assert scroll.scroll_top == before - WHEEL_LINES


def test_wheel_does_nothing_in_dock_mode_and_does_not_crash():
    """main-screen 下 pai 不拥有屏幕；而终端可能残留着上个程序开的鼠标模式，
    字节照样会送进来——不许崩。"""
    writes: List[str] = []
    app = TuiApp(renderer=DockRenderer(write=writes.append, width=lambda: 40))
    app.commit("x")
    _feed(app, WHEEL_UP * 3)
    assert app.scroll.scroll_top == 0
    assert app.scroll.following_end


def test_wheel_line_count_is_documented_as_a_guess():
    """AGENTS 的照抄常数纪律：这个数从哪来必须写在旁边。

    保留源码断言（R4#T3 逐条处理时的裁决）：钉的对象是**注释本身**——
    「这个数没实测」这句话在不在源码里。行为测不出注释，扫源码是唯一手段。
    """
    import inspect

    import pai.tui.app as app_module

    source = inspect.getsource(app_module)
    # 找**定义点**而不是第一次出现（使用点在文件上方，抓错了会得到一段无关代码）
    at = source.index("WHEEL_LINES = ")
    head = source[max(0, at - 250):at]
    assert "无实测依据" in head or "凭手感" in head
