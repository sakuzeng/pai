"""事件合并（feature 16 T2）——**本轮唯一由实测倒逼出来的设计**。

实测：一次滚动手势 6 秒 **142 条** wheel 事件（触控板惯性尤甚）。
pai 的一帧是整屏 diff，142 条各画一帧 = 两指滑一下屏幕抽搐半秒。
而离线测试里事件是一次性喂进去的，**看不出卡**——所以断言必须落在
「画了几帧」上，不能落在「滚动结果对不对」（两种写法的结果是一样的）。
"""

from typing import List

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.keys import KeyDecoder
from pai.tui.mouse import MouseEvent, merge
from pai.tui.scroll import ScrollState
from pai.tui.transcript import Transcript, text_entry


def _wheel(delta=-1, col=0, row=0):
    return MouseEvent(kind="wheel", col=col, row=row, delta=delta)


def test_a_burst_of_wheel_events_becomes_one():
    """142 是实测数字，不是随手编的。"""
    assert merge([_wheel() for _ in range(142)]) == [_wheel(delta=-142)]


def test_wheel_up_and_down_cancel_out():
    assert merge([_wheel(-1), _wheel(1), _wheel(-1)]) == [_wheel(delta=-1)]


def test_consecutive_drags_keep_only_the_last():
    """焦点只关心「现在在哪」，中间过程无意义。"""
    drags = [MouseEvent(kind="drag", col=c, row=1) for c in (3, 4, 5)]
    assert merge(drags) == [MouseEvent(kind="drag", col=5, row=1)]


def test_press_and_release_are_never_merged_or_reordered():
    """它们是状态跃迁——少一条或换个顺序，选区就废了。"""
    events = [MouseEvent(kind="press", col=1, row=1),
              MouseEvent(kind="drag", col=2, row=1),
              MouseEvent(kind="release", col=2, row=1),
              MouseEvent(kind="press", col=5, row=5)]
    assert merge(events) == events


def test_merging_does_not_cross_a_state_transition():
    """按下之前滚的和按下之后滚的，不许算成同一次。"""
    events = [_wheel(-1), _wheel(-1), MouseEvent(kind="press", col=1, row=1), _wheel(-1)]
    assert merge(events) == [_wheel(delta=-2),
                             MouseEvent(kind="press", col=1, row=1),
                             _wheel(delta=-1)]


def test_empty_batch():
    assert merge([]) == []


# --- 接线层：断言「画了几帧」，不是「滚到哪了」 ---------------------------


class CountingRenderer(AltScreenRenderer):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.draws = 0

    def draw(self, root):
        self.draws += 1
        super().draw(root)


def _app(rows=10):
    transcript, scroll = Transcript(), ScrollState()
    for i in range(200):
        transcript.append(text_entry([f"line{i}"]))
    renderer = CountingRenderer(write=lambda s: None, width=lambda: 40,
                                height=lambda: rows, transcript=transcript,
                                scroll=scroll)
    return TuiApp(renderer=renderer, transcript=transcript, scroll=scroll), renderer, scroll


def test_142_wheel_events_produce_exactly_one_frame():
    """**本 task 的核心断言。** 注入反证要打的就是它：
    改成逐条 scroll_by + draw，滚动结果一模一样、这条会红。"""
    app, renderer, scroll = _app()
    app.refresh()
    renderer.draws = 0
    app.feed(b"\x1b[<64;1;1M" * 142, KeyDecoder())
    assert renderer.draws == 1


def test_the_scroll_actually_moved_by_the_summed_delta():
    """合并不能把滚动本身吃掉。"""
    app, renderer, scroll = _app()
    app.refresh()
    before = scroll.scroll_top
    app.feed(b"\x1b[<64;1;1M" * 10, KeyDecoder())
    assert scroll.scroll_top < before


def test_the_scroll_state_machine_is_called_once_not_142_times():
    """**这条是 `merge()` 唯一守得住的性质**，也是它存在的全部理由。

    「142 条只画一帧」由 `app.feed` 的「末尾只 refresh 一次」保证——注入反证证明
    删掉 merge 它也不会红。所以 merge 必须有一条**只有它能满足**的断言，
    否则它就是一段不可证伪的代码（同 T4 那条：两道互相遮蔽的防线，
    等于没人知道哪道在生效）。
    """
    app, renderer, scroll = _app()
    app.refresh()
    calls = []
    original = scroll.scroll_by
    scroll.scroll_by = lambda delta: (calls.append(delta), original(delta))[1]
    app.feed(b"\x1b[<64;1;1M" * 142, KeyDecoder())
    assert len(calls) == 1
    assert calls[0] < 0
