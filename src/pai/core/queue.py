"""排队消息：用户在 agent 干活期间/结束时想追加的话，先落在这里。

两条队列语义不同（抄自 pi agent.ts:123 的 PendingMessageQueue，代码独立写）：
- steering：agent 干活中途转向。注入点在**每轮工具结果全部回填之后**，
  用 "all" 模式一次全灌——用户连打三句通常是同一个转向意图，拆开逐轮注入反而错乱。
- followUp：agent 本该停下时排队续问。注入点在**模型不再发 tool_calls、即将返回**处，
  用 "single" 模式一条一轮——每条各触发一轮，中间还可能被中断。

诚实边界：纯 REPL 的 input() 是阻塞的，agent 干活时用户根本没法打字，
所以 REPL 阶段只有 followUp 有真实输入源，steering 的注入位置靠测试（假回调）钉死，
等 TUI/流式才通电。
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
