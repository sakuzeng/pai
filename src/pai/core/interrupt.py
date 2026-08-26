"""中断标志：Ctrl+C 要能打断跑飞的工具，而不只是停在步边界。

为什么是进程级单例而不是依赖注入（本仓库其他地方一律注入）：@tool 从函数签名生成
schema，给 bash 加个 flag 参数就会把它发给模型看。工具需要的运行期上下文只能从旁路进，
这是 @tool「schema 与代码同源」设计的直接代价，取舍记 decisions。

包 threading.Event 而不是裸 bool：TUI/流式阶段一定会有读输入的线程来置这个标志，
现在选可跨线程的类型，到时候不用回头改。
"""

from __future__ import annotations

import contextlib
import signal
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


# ---- 「这段作用域里 Ctrl+C 只置标志」的三件套（feature 40 从 modes/interactive 搬来）----
#
# 搬家的理由与 `tui/width.py` 那次一样：它被两个消费者共用（交互主循环与
# 命令/shell 分流），而共用的东西住在其中一个消费者的文件里，本身就是位置错误。
# 论主题它也该在这儿——它讲的正是「中断怎么工作」，与本模块的 InterruptFlag 同题。

def _install_sigint(flag: InterruptFlag):
    """干活期间 Ctrl+C 只置标志：抛 KeyboardInterrupt 会把已完成的工作连同栈一起丢掉，
    而官方对中断的承诺恰恰是「保留迄今完成的工作」。"""
    try:
        return signal.signal(signal.SIGINT, lambda *_: flag.set())
    except ValueError:
        return None              # 不在主线程（如某些测试宿主）时装不上，退化为不可中断


def _restore_sigint(previous) -> None:
    if previous is not None:
        try:
            signal.signal(signal.SIGINT, previous)
        except ValueError:
            pass


@contextlib.contextmanager
def _interruptible(flag: InterruptFlag):
    """在这个作用域里，Ctrl+C 只置标志不抛异常——执行侧（loop / bash 轮询）自己找地方收尾。

    模型轮次与 `!命令` **两条路径都必须进来**：`!` 分支曾经漏在外面，
    于是 Ctrl+C 打断 `!sleep 300` 会把整个 REPL 带栈掀掉（同 401 炸会话那一类）。
    """
    flag.clear()
    previous = _install_sigint(flag)
    try:
        yield
    finally:
        _restore_sigint(previous)
