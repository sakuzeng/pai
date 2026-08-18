"""输入归属仲裁：此刻谁拥有键盘。

**这是 feature 12 的核心**。它治的病是「asker 与 REPL 主循环共用一个阻塞 reader，
谁先 `read()` 谁拿到」——实际发生过 `!echo 我是命令` 被当成对问题的回答。
药方不是「让对话框把输入抢过去」，而是**把归属算出来**：一个仲裁函数 + 每个消费者
一个 is_active 开关。

语义照 CC（K tui/cc-input-ownership-and-modes.md 第一节）：**偏袒正在打字的人**。
注意这与 pai 自己 TODO 里凭官方文档推出的「问题框接管输入焦点」方向相反——
源码里 `getFocusedInputDialog()` 第三行就是 `if (isPromptInputActive) return undefined`。
"""

from __future__ import annotations

import time
from typing import Any, Callable, List, Optional

# 「编辑器拥有输入」的哨兵。用独立对象而不是 None——None 容易与「还没算」混淆。
EDITOR = object()

# 停手多久才放对话框出来。
# **这个数是从 CC 的 PROMPT_SUPPRESSION_MS 抄来的**，它带着 CC 的使用节奏假设
# （英文输入、桌面终端）。pai 跑中文输入法，一次上屏的停顿可能更长——
# 真实感受与这个值不符时该调，别当成物理常数。
# （TODO「给照抄来的常数建一条检查习惯」：抄来的数字要带着它的前提一起被看见。）
SUPPRESSION_MS = 1500


class _Pending:
    __slots__ = ("payload", "user_invoked")

    def __init__(self, payload: Any, user_invoked: bool) -> None:
        self.payload = payload
        self.user_invoked = user_invoked


class InputArbiter:
    """谁拥有输入。`owner()` 返回 `EDITOR` 或队首对话框的 payload。"""

    def __init__(self, *, suppression_ms: int = SUPPRESSION_MS,
                 now: Callable[[], float] = time.monotonic) -> None:
        self._suppression = suppression_ms / 1000.0
        self._now = now
        self._queue: List[_Pending] = []
        self._typing = False
        self._last_key_at = 0.0

    # --- 输入侧 -------------------------------------------------------

    def note_typing(self, text: str) -> None:
        """每次按键后调用。传当前输入框内容——**空白不算在打字**。"""
        self._typing = bool(text.strip())
        self._last_key_at = self._now()

    def enqueue(self, payload: Any, *, user_invoked: bool = False) -> None:
        """排一个要真人处理的东西。`user_invoked` 的不受抑制（是他自己唤出来的）。"""
        self._queue.append(_Pending(payload, user_invoked))

    def resolve(self, payload: Any = None) -> None:
        """处理掉一个。给了 `payload` 就**按身份移除**，不盲弹队首。

        现实里权限是按批串行判的，队列同时只会有一个，盲弹 `pop(0)` 碰巧不出错——
        但「结构上不可能出错」与「碰巧不出错」是两回事，而中断路径要撤的那一框
        未必是队首（R4#3）。撤一个已经不在队列里的，是 no-op：中断与作答
        可能前后脚到，误伤下一个框比什么都不做更糟。
        """
        if payload is None:
            if self._queue:
                self._queue.pop(0)
            return
        for i, pending in enumerate(self._queue):
            if pending.payload is payload:
                self._queue.pop(i)
                return

    # --- 判定 ---------------------------------------------------------

    def owner(self):
        if not self._queue:
            return EDITOR
        head = self._queue[0]
        if head.user_invoked or not self._suppressed():
            return head.payload
        return EDITOR

    def _suppressed(self) -> bool:
        return self._typing and (self._now() - self._last_key_at) <= self._suppression

    def is_suppressing(self) -> bool:
        """有东西在等、但因为用户在打字而没弹出来。

        **必须能被问出来**：被压住却不告诉用户，就是把「等待」变成「卡住」。
        CC 在输入框下方显示 `Waiting for permission…`，pai 的对应物在状态行。
        """
        return bool(self._queue) and self.owner() is EDITOR

    def pending_count(self) -> int:
        return len(self._queue)

    def current(self) -> Optional[Any]:
        owner = self.owner()
        return None if owner is EDITOR else owner
