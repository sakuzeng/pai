"""驱动层（feature 16 收尾）。

**它此前一条测试都没有**（12 复盘质疑五），而这次的卡顿正出在它身上：
真终端里鼠标事件是一条一条到的，`poll` 一次 `select` + 一次 `os.read` 往往只拿到一两条，
于是 `mouse.merge` 的合并**根本没机会生效**——它只在同一批里合并。
离线测试永远是「一批很多条」，真终端是「很多批各一条」：
**测试喂数据的方式本身就是一个未被检验的假设。**
"""

import os

from pai.tui.driver import TuiDriver


class FakeApp:
    def __init__(self):
        self.batches = []
        self.ticks = 0
        self.refreshes = 0

    def feed(self, data, decoder):
        self.batches.append(data)
        return []

    def tick(self):
        self.ticks += 1

    def refresh(self):
        self.refreshes += 1

    def needs_tick(self):
        return True

    def _key(self, key):
        return []


def _pipe_with(chunks):
    r, w = os.pipe()
    for chunk in chunks:
        os.write(w, chunk)
    return r, w


def test_everything_already_waiting_is_read_into_one_batch():
    """一次手势的几十条事件要凑成**一批**交给 app，合并才有意义。"""
    app = FakeApp()
    r, w = _pipe_with([b"\x1b[<32;1;1M"] * 50)
    driver = TuiDriver(app, fd=r)
    driver.poll(timeout=0.01)
    os.close(w)
    os.close(r)
    assert len(app.batches) == 1
    assert app.batches[0].count(b"\x1b") == 50


def test_a_partial_sequence_is_not_split_across_batches():
    """读干净的同时不能把一条序列切两半——切了就得等下一次 poll 才拼得回来。"""
    app = FakeApp()
    r, w = _pipe_with([b"\x1b[<0;12", b";3M"])
    driver = TuiDriver(app, fd=r)
    driver.poll(timeout=0.01)
    os.close(w)
    os.close(r)
    assert app.batches == [b"\x1b[<0;12;3M"]


def test_the_idle_tick_lets_time_based_work_happen():
    """拖动收尾、提示过期这类「随时间发生的事」全靠这一拍。"""
    app = FakeApp()
    r, w = os.pipe()
    driver = TuiDriver(app, fd=r)
    driver.poll(timeout=0.01)
    os.close(w)
    os.close(r)
    assert app.ticks == 1
    assert app.refreshes == 1


# ---- feature 19 T4：主循环取走 resize 标志并重画（2026-08-19）----


class _FakeTerminal:
    def __init__(self) -> None:
        self.pending = False
        self.redraws = 0

    def take_resize_pending(self) -> bool:
        pending, self.pending = self.pending, False
        return pending

    def redraw_after_resize(self) -> None:
        self.redraws += 1


def test_a_pending_resize_is_redrawn_by_the_poll_loop():
    """信号处理器只置标志，重画必须有人接——不接就是「resize 后永不重画」的回退。"""
    r, _w = _pipe_with([])
    term = _FakeTerminal()
    term.pending = True
    driver = TuiDriver(FakeApp(), fd=r, terminal=term)

    driver.poll(timeout=0)

    assert term.redraws == 1


def test_no_pending_resize_means_no_extra_redraw():
    """平时不许白重画：每个 poll 周期都画一遍就是空转（feature 12 撞过一次
    「空闲每 100ms 白刷一帧」）。"""
    r, _w = _pipe_with([])
    term = _FakeTerminal()
    driver = TuiDriver(FakeApp(), fd=r, terminal=term)

    driver.poll(timeout=0)
    driver.poll(timeout=0)

    assert term.redraws == 0
