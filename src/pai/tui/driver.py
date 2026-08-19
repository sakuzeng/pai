"""TUI 主循环驱动：把 `TuiApp` 接到真实的 stdin / 终端上。

**它是本模块里唯一一段离线测不透的代码**——需要真 tty、真 raw mode、真 select。
所以刻意做薄：所有判断都在 `TuiApp`（可测），这里只负责
「读字节 → 交给 app → 把动作交给回调」。诚实边界写在这儿，别把它做厚。

**线程模型**：主线程持有 stdin、信号与 loop；并发工具留在线程池（feature 11 已如此）。
不把 REPL 挪到子线程——那会让 `signal.signal` 装不上（05 遗留），
`TerminalSession.start()` 会在非主线程时明确告警而不是静默退化。
"""

from __future__ import annotations

import os
import select
import sys
from typing import Callable, List, Optional, Tuple

from pai.tui.app import TuiApp
from pai.tui.keys import KeyDecoder

# 空闲时的轮询间隔。有它才有转圈动画与「停手 1500ms 放行对话框」——
# 两者都需要「没有输入也要醒一次」。
POLL_SECONDS = 0.1


class TuiDriver:
    """读 stdin、喂 app、吐动作。"""

    def __init__(self, app: TuiApp, *, fd: Optional[int] = None,
                 terminal=None) -> None:
        self.app = app
        self._fd = fd if fd is not None else sys.stdin.fileno()
        self._decoder = KeyDecoder()
        # resize 的重画落点（feature 19 T4）：SIGWINCH 处理器只置标志，
        # 真正重画在这里做——信号处理器里写 stdout 会与主线程的写重入。
        self._terminal = terminal

    def poll(self, timeout: float = POLL_SECONDS) -> List[Tuple[str, object]]:
        """等一小会儿；有输入就处理，没有就只重画（转圈/计时/抑制到期靠它推进）。"""
        if self._terminal is not None and self._terminal.take_resize_pending():
            # 标志取走就清，否则每个 poll 周期都白重画一遍
            # （feature 12 撞过一次「空闲每 100ms 白刷一帧」）。
            self._terminal.redraw_after_resize()
        try:
            ready, _, _ = select.select([self._fd], [], [], timeout)
        except (OSError, ValueError):
            return []
        if not ready:
            keys = self._decoder.flush()      # 悬着的单个 ESC 到此判定为 esc 键
            if keys:
                actions = [a for key in keys for a in self.app._key(key)]
                self.app.refresh()
                return actions
            if self.app.needs_tick():
                # 空闲时不重画：只有转圈、「抑制到期」、提示过期、拖动收尾
                # 这几件是随时间变的
                self.app.tick()
                self.app.refresh()
            return []
        try:
            data = os.read(self._fd, 4096)
        except OSError:
            return []
        if not data:
            return [("eof", None)]
        # **把已经排队的一并读干净再处理**：鼠标一次手势有上百条事件，
        # 分成很多批各一条送到的话，`mouse.merge` 的合并根本没机会生效
        # （它只在同一批里合并）。这里不等新数据，只捞已经到了的。
        while True:
            ready, _, _ = select.select([self._fd], [], [], 0)
            if not ready:
                break
            try:
                more = os.read(self._fd, 4096)
            except OSError:
                break
            if not more:
                break
            data += more
        return self.app.feed(data, self._decoder)

    def pump_until(self, done: Callable[[], bool],
                   on_action: Callable[[str, object], None]) -> None:
        """一直读到 `done()` 为真。

        用在两处：真人问答（等这一框被答掉）与 agent 干活期间（等本轮结束）。
        期间收到的动作交给 `on_action`——**提问期间敲的 `!命令` 就是这样被执行的**。
        """
        while not done():
            for kind, payload in self.poll():
                on_action(kind, payload)
