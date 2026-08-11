"""鼠标事件：SGR 1006 的形状，以及**把一批事件合并成一帧该做的事**。

编码与量级都是实测来的（features/16 evidence），不是照文档抄的：

| 实测 | 对实现的约束 |
|---|---|
| 一次滚动手势 **142 条**（6 秒，触控板惯性尤甚） | wheel 必须累加成一个 delta、**只重绘一次** |
| 拖动 **每跨一格一条**（153 条 / 148 个不同坐标） | 每条都带新信息，不能合并；但只有最后一条决定焦点在哪 |
| 触控板滚动**不移动指针**（坐标恒定） | wheel 的 col/row 是「指针此刻在哪」，用于命中测试 |

**为什么解析不放在这里而放在 `keys.py`**：鼠标序列与按键走同一条字节流、
同样会被 `os.read` 拆包，复用 `KeyDecoder` 已有的分片状态机才不会写第二套拼包逻辑。
本模块只定义事件与合并策略——两者都是纯函数，离线可测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

# 按钮位的含义（SGR 1006）。`&3` 取哪个键，高位是修饰：
BUTTON_MASK = 0b11        # 0=左 1=中 2=右，**3=没有按键**
NO_BUTTON = 0b11          # 低两位为 3：这一条是「纯移动」，不是拖动
DRAG_BIT = 32             # 按住移动
WHEEL_BIT = 64            # 滚轮；此时 `&3` 是方向：0=上 1=下


@dataclass(frozen=True)
class MouseEvent:
    """一次鼠标事件。列行**一律 0-based**——SGR 报的是 1-based，进来就换掉，
    免得两套坐标在代码里并存（那是坐标错位最常见的来源）。"""

    kind: str                 # press / release / drag / wheel
    button: int = 0
    col: int = 0
    row: int = 0
    delta: int = 0            # 只有 wheel 有：-1 向上、+1 向下


def parse(button: int, col: int, row: int, final: str) -> Optional[MouseEvent]:
    """把 SGR 的三个数字 + 结尾字符变成事件。认不出来返回 None（**不猜**）。"""
    if button & WHEEL_BIT:
        direction = button & BUTTON_MASK
        if direction not in (0, 1):
            return None                      # 横向滚动：本轮不支持，丢弃
        return MouseEvent(kind="wheel", col=col, row=row,
                          delta=-1 if direction == 0 else 1)
    if final == "m":
        return MouseEvent(kind="release", button=button & BUTTON_MASK, col=col, row=row)
    if button & DRAG_BIT:
        if button & BUTTON_MASK == NO_BUTTON:
            # **没按键的移动**（1003 下鼠标划过窗口就有）。当成拖动的后果是
            # 用户松手之后高亮还跟着鼠标走——2026-08-11 真跑打回来的。
            return MouseEvent(kind="move", col=col, row=row)
        return MouseEvent(kind="drag", button=button & BUTTON_MASK, col=col, row=row)
    return MouseEvent(kind="press", button=button & BUTTON_MASK, col=col, row=row)


def merge(events: List[MouseEvent]) -> List[MouseEvent]:
    """把一批事件压成「值得处理的那几条」。**这是实测倒逼出来的**。

    - **连续的 wheel 累加成一条**：实测一次手势 142 条，各画一帧 = 滑一下抽搐半秒；
      而滚动的语义可加，累加后结果完全一样。
    - **连续的 drag 只留最后一条**：焦点只关心「现在在哪」，中间过程无意义。
    - **press / release 一条不许丢、也不许重排**：它们是状态跃迁，顺序错了选区就废了。

    合并**不跨越状态跃迁**：`wheel wheel press wheel` 得到
    `wheel(-2) press wheel(-1)`——否则「按下之前滚的」与「按下之后滚的」会被算成同一次。
    """
    out: List[MouseEvent] = []
    for event in events:
        if out and event.kind == "wheel" and out[-1].kind == "wheel":
            last = out[-1]
            out[-1] = MouseEvent(kind="wheel", col=event.col, row=event.row,
                                 delta=last.delta + event.delta)
            continue
        if out and event.kind in ("drag", "move") and out[-1].kind == event.kind:
            out[-1] = event                  # 只留最后一条：焦点/指针只关心「现在在哪」
            continue
        out.append(event)
    return out
