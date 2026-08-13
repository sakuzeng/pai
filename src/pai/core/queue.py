"""排队消息：用户在 agent 干活期间/结束时想追加的话，先落在这里。

两条队列语义不同（抄自 pi agent.ts:123 的 PendingMessageQueue，代码独立写）：
- steering：agent 干活中途转向。注入点在**每轮工具结果全部回填之后**，
  用 "all" 模式一次全灌——用户连打三句通常是同一个转向意图，拆开逐轮注入反而错乱。
- followUp：agent 本该停下时排队续问。注入点在**模型不再发 tool_calls、即将返回**处，
  用 "single" 模式一条一轮——每条各触发一轮，中间还可能被中断。

诚实边界：**steering 至今没有真实输入源**，只有 followUp 有。

原因分两段。纯 REPL 阶段是物理上做不到——`input()` 阻塞着，agent 干活时用户没法打字。
TUI 交付（feature 12/13/16）之后这个限制没了，用户确实能在干活时打字，
但那条路仍然只接 followUp（`modes/interactive.py` 的 SUBMIT 分支进 `follow_up.enqueue`）：
followUp 接上就是纯收益，steering 还要处理「插在哪不会劈开 tool_calls 与它的结果」，
本轮没做。原来这里写的是「等 TUI/流式才通电」——**TUI 到了，这句没兑现**，
2026-08-12 按实况改写，免得注释与现实各说各话。

现状：**结构就位、注入点由 loop 备好、注入位置靠测试（假回调）钉死、没有调用方。**
"""

from __future__ import annotations

from typing import List, Literal

QueueMode = Literal["all", "single"]
_MODES = ("all", "single")


class PendingMessageQueue:
    def __init__(self, mode: QueueMode) -> None:
        if mode not in _MODES:
            # 静默降级成某个模式，行为就会随手一改而变——报错指向真因（对齐 @tool）
            raise ValueError(f"未知队列模式 {mode!r}：只认 {list(_MODES)}")
        self.mode: QueueMode = mode
        self._messages: List[dict] = []

    def enqueue(self, message: dict) -> None:
        self._messages.append(message)

    def has_items(self) -> bool:
        return bool(self._messages)

    def drain(self) -> List[dict]:
        """按模式取出待注入消息；空队列返回 []（不抛、不返回 None）。"""
        if self.mode == "all":
            drained = self._messages[:]      # 切片而非引用：调用方 append 不该改到队列
            self._messages = []
            return drained
        if not self._messages:
            return []
        return [self._messages.pop(0)]

    def clear(self) -> None:
        self._messages = []
