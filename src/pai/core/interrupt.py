"""中断标志：Ctrl+C 要能打断跑飞的工具，而不只是停在步边界。

为什么是进程级单例而不是依赖注入（本仓库其他地方一律注入）：@tool 从函数签名生成
schema，给 bash 加个 flag 参数就会把它发给模型看。工具需要的运行期上下文只能从旁路进，
这是 @tool「schema 与代码同源」设计的直接代价，取舍记 decisions。

包 threading.Event 而不是裸 bool：TUI/流式阶段一定会有读输入的线程来置这个标志，
现在选可跨线程的类型，到时候不用回头改。
"""

from __future__ import annotations

import threading
from typing import Optional


class InterruptFlag:
    """置位后一直有效，直到显式 clear——一次 Ctrl+C 要贯穿「当前工具 + 本轮剩余工具 + 下一步」。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


_CURRENT = InterruptFlag()


def current() -> InterruptFlag:
    """永远返回可用对象，绝不返回 None——否则每个调用点都要判空。"""
    return _CURRENT


def set_current(flag: Optional[InterruptFlag]) -> None:
    """装配期注入；传 None = 卸载，换回一个干净的默认标志（测试复位靠它）。"""
    global _CURRENT
    _CURRENT = flag if flag is not None else InterruptFlag()
