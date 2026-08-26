"""干活期间的心跳：长时间阻塞的工具每隔一小会儿给界面层一个喘气的机会。

治的是一个具体的体验缺陷（12 复盘质疑二）：TUI 只在「有事件到来时」顺手
poll 一次键盘，而一条跑 30 秒的 bash 命令期间一个事件都不发——用户打的字
没丢（在内核 tty 缓冲区等着），但屏幕一动不动，看起来像键盘死了。
在最需要反馈的时候没有反馈。

为什么是进程级单例而不是依赖注入（本仓库其他地方一律注入）：与
`core/interrupt.py` 一字不差的理由——`@tool` 从函数签名生成 schema，
给 bash 加个参数就会把它发给模型看。工具需要的运行期上下文只能从旁路进。

它不是 `AskerRef` / `EventSink` 那类可变持有者：那两个是装配期烤进闭包、
运行期要换的东西，而心跳每次现取（`current()`），不进任何闭包。
所以 TODO 那条「第三个可变持有者出现时抽泛型 Ref[T]」的触发条件在这里没满足。

边界：心跳是界面层的便利，不是正确性的一部分。回调炸了一律吞掉——
一个渲染 bug 不该把用户正在跑的命令连坐掉（同「工具错误不 throw」那条底线）。
"""

from __future__ import annotations

from typing import Callable, Optional


class Heartbeat:
    """包一个可选回调。默认什么都不做——没有界面的场景（once / 测试）不该付任何代价。"""

    def __init__(self, on_beat: Optional[Callable[[], None]] = None) -> None:
        self._on_beat = on_beat

    def beat(self) -> None:
        if self._on_beat is None:
            return
        try:
            self._on_beat()
        except Exception:      # noqa: BLE001 - 心跳炸了不许连累正在跑的工具
            pass


_CURRENT = Heartbeat()


def current() -> Heartbeat:
    """永远返回可用对象，绝不返回 None——否则每个调用点都要判空（同 interrupt）。"""
    return _CURRENT


def set_current(beat: Optional[Heartbeat]) -> None:
    """装配期注入；传 None = 卸载，换回一个什么都不做的默认心跳（测试复位靠它）。"""
    global _CURRENT
    _CURRENT = beat if beat is not None else Heartbeat()
