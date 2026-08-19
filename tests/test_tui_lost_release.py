"""释放事件丢了怎么办（feature 16 收尾）。

用户 2026-08-11 连报三次「从后往前拖选不复制」，最后一张截图给了决定性线索：
**高亮还在**——而复制成功会清掉选区，所以是**释放事件没走到复制那一步**。

离线怎么喂都复现不了，说明它压根没送到（向上/向左拖很容易把指针带出窗口，
终端只在窗口内上报）。**所以修法不是猜它为什么丢，是别依赖它一定会来。**
"""

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.keys import KeyDecoder
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript, text_entry


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _app(rows=12, cols=60, lines=6):
    transcript, scroll, selection = Transcript(), ScrollState(), Selection()
    for i in range(lines):
        transcript.append(text_entry([f"第 {i} 行的内容 some text"]))
    renderer = AltScreenRenderer(write=lambda s: None, width=lambda: cols,
                                 height=lambda: rows, transcript=transcript,
                                 scroll=scroll, selection=selection)
    clock = Clock()
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll,
                 selection=selection, now=clock)
    app.dock._now = clock
    app.refresh()
    return app, clock


def _feed(app, data):
    return app.feed(data, KeyDecoder())


def _drag_backwards(app):
    """从第 3 行往上拖到第 1 行——**不发释放**（真终端里它可能丢了）。"""
    _feed(app, b"\x1b[<0;30;4M")
    for row in (3, 2, 1):
        _feed(app, f"\x1b[<32;5;{row}M".encode())


def test_a_lost_release_is_settled_by_the_next_press():
    """下一次按下时先给上一次收尾——不然那次选中就永远卡在「拖动中」。"""
    app, _ = _app()
    _drag_backwards(app)
    assert app.selection.dragging
    _feed(app, b"\x1b[<0;10;5M")
    assert app.dock.has_notice(), "上一次拖选没有被收尾复制"


def test_a_pause_copies_but_does_not_end_the_drag():
    """**停手 ≠ 松开，两者分不出来**——所以停手只能做「不破坏性」的事：
    把当前选中的先放进剪贴板并给个提示，**但不结束拖动、不清高亮**。

    第一版把停手当成结束，用户当场打回：「如果我慢慢的移动，我还在按就结束了」。
    """
    app, clock = _app()
    _drag_backwards(app)
    clock.now += 1.0
    app.tick()
    assert app.dock.has_notice()          # 剪贴板里已经有东西了
    assert app.selection.dragging          # 但这次拖动**没结束**
    assert app.selection.has_selection     # 高亮还在


def test_a_slow_drag_keeps_extending_after_a_pause():
    """慢慢拖：停一下、再接着拖，选区要继续长，而不是被截断。"""
    app, clock = _app()
    _feed(app, b"\x1b[<0;30;4M")
    _feed(app, b"\x1b[<32;20;3M")
    clock.now += 1.0
    app.tick()                             # 中途停了一下
    _feed(app, b"\x1b[<32;5;1M")           # 接着拖
    assert app.selection.dragging
    span = app.selection.bounds()
    assert span is not None and span[0].row == 0


def test_the_pause_copy_does_not_fire_while_still_moving():
    app, clock = _app()
    _drag_backwards(app)
    clock.now += 0.1
    app.tick()
    assert not app.dock.has_notice()


def test_the_same_selection_is_not_copied_twice():
    """停手不动时每一拍都复制一次 = 反复起子进程。内容没变就别再复制。"""
    app, clock = _app()
    _drag_backwards(app)
    clock.now += 1.0
    app.tick()
    copies = []
    app._copy_text = lambda text: copies.append(text)
    for _ in range(5):
        clock.now += 1.0
        app.tick()
    assert copies == []


def test_dragging_keeps_the_ticker_alive():
    """没人来敲这一下的话，收尾永远不会发生。"""
    app, _ = _app()
    _drag_backwards(app)
    assert app.needs_tick()


def test_a_normal_release_still_copies_immediately():
    """兜底不能把正常路径变慢：释放到了就当场复制，不等超时。"""
    app, _ = _app()
    _feed(app, b"\x1b[<0;30;4M")
    _feed(app, b"\x1b[<32;5;2M")
    _feed(app, b"\x1b[<0;5;2m")
    assert app.dock.has_notice()
    assert not app.selection.dragging


def test_a_lost_release_on_an_empty_selection_copies_nothing():
    app, clock = _app()
    _feed(app, b"\x1b[<0;10;3M")          # 只按下，没拖
    clock.now += 1.0
    app.tick()
    assert not app.dock.has_notice()


def test_a_press_after_a_lost_release_still_cleans_up():
    """真的丢了释放、用户也不再拖了——下一次按下时把上一次彻底收掉。

    注意断言的不是 `dragging` 为假：按下**本来就会开始新的一次**。
    要断言的是「上一次被收干净了，现在是全新的一次」——没有残留的选区。
    """
    app, clock = _app()
    _drag_backwards(app)
    clock.now += 1.0
    app.tick()
    assert app.selection.has_selection            # 收尾之前，旧选区还在
    _feed(app, b"\x1b[<0;10;5M")
    assert not app.selection.has_selection        # 收尾之后，只剩一个新锚点


def test_the_input_box_pause_copies_too():
    app, clock = _app()
    app.editor.set_text("hello world")
    app.refresh()
    row = app.renderer.input_row
    _feed(app, f"\x1b[<0;3;{row + 1}M".encode())
    _feed(app, f"\x1b[<32;8;{row + 1}M".encode())
    clock.now += 1.0
    app.tick()
    assert app.dock.has_notice()


# ---- feature 16 收尾：拖动期的渲染节流（2026-08-19，perf）----
#
# 实测数字（pai_playground/bench/drag_render.py，视口 100x40、120 条移动事件）：
#
#   事件到达方式      总耗时     终端写次数
#   一批到达         12.5ms        1
#   一条一批        206~263ms     121
#
# 单帧本身只要 1.1~1.7ms，且**不随 transcript 增大**（2000 条也只 1.71ms）——
# 所以瓶颈不是「渲染太慢」，是「帧数太多」。按 16ms 窗口合并后实测
# 27~35ms / 16 次写，快 7 倍多。pi 在同一位置的答案是
# `TuiBase.MIN_RENDER_INTERVAL_MS = 16`。


def _counting_app(rows=12, cols=60, lines=6):
    """与 `_app` 同构，但数「画了几帧」。"""
    frames = []
    transcript, scroll, selection = Transcript(), ScrollState(), Selection()
    for i in range(lines):
        transcript.append(text_entry([f"第 {i} 行的内容 some text"]))
    renderer = AltScreenRenderer(write=lambda s: None, width=lambda: cols,
                                 height=lambda: rows, transcript=transcript,
                                 scroll=scroll, selection=selection)
    clock = Clock()
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll,
                 selection=selection, now=clock)
    app.dock._now = clock
    original = renderer.draw

    def counting_draw(root):
        frames.append(1)
        return original(root)

    renderer.draw = counting_draw
    app.refresh()
    frames.clear()
    return app, clock, frames


def test_a_burst_of_drag_events_does_not_draw_a_frame_each():
    """拖选卡顿的根因是帧数太多，不是单帧太慢（数字见本节头部）。"""
    app, clock, frames = _counting_app()
    _feed(app, b"\x1b[<0;5;5M")                 # 按下
    frames.clear()

    decoder = KeyDecoder()
    for i in range(10):
        clock.now += 0.002                      # 2ms 一条，全落在同一个 16ms 窗口
        app.feed(f"\x1b[<32;{6 + i};5M".encode(), decoder)

    assert len(frames) <= 2, f"10 条 2ms 间隔的拖动事件画了 {len(frames)} 帧——没节流"


def test_the_last_drag_move_is_still_drawn():
    """节流必须有收尾的那一帧。

    否则用户松手时看到的高亮停在倒数第二个位置——比卡顿更糟，因为它是错的。
    `needs_tick()` 在拖动期间本来就为真（`_drag_at is not None`），正好推它。
    """
    app, clock, frames = _counting_app()
    _feed(app, b"\x1b[<0;5;5M")
    decoder = KeyDecoder()
    clock.now += 0.002
    app.feed(b"\x1b[<32;9;9M", decoder)         # 被节流压住
    frames.clear()

    clock.now += 0.1                            # 窗口过期
    assert app.needs_tick() is True
    app.tick()
    app.refresh()

    assert len(frames) >= 1, "收尾帧没画出来"


def test_a_slow_drag_still_draws_every_move():
    """慢慢拖时每一步都该跟手——节流窗口是 16ms，人手动不了那么快。"""
    app, clock, frames = _counting_app()
    _feed(app, b"\x1b[<0;5;5M")
    frames.clear()

    decoder = KeyDecoder()
    for i in range(3):
        clock.now += 0.05                       # 50ms 一条，远超窗口
        app.feed(f"\x1b[<32;{6 + i};5M".encode(), decoder)

    assert len(frames) == 3


def test_keystrokes_are_never_throttled():
    """治过头就成了另一个 bug：打字必须帧帧跟手，一个字都不许并。"""
    app, clock, frames = _counting_app()
    decoder = KeyDecoder()
    frames.clear()

    for ch in b"abc":
        clock.now += 0.001
        app.feed(bytes([ch]), decoder)

    assert len(frames) == 3
