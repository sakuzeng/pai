"""排队消息：用户在 agent 干活期间敲的字，先落在这里。

**pai 只有一条消息队列**（feature 18 拍板问 2）。这是与 pi 的分道点：pi 用两个对象
（steeringQueue / followUpQueue）表达两种时机，把「什么时候发」推给集成方；
pai 照 CC 的交互式实情——用户输入默认就是「中途注入」，不需要任何手势去表达它。
被拒的那一半也记在案：CC 的 `next` 在「模型这轮不调工具」时会退化成新开一轮，
pai 不退化（见 loop 的两个出口）。取舍全文见 features/18 与 decisions。

两种 drain 模式各有其用，不是凑数：

- **"all"（注入用）**：一次全灌。用户连打三句通常是同一个转向意图，拆开逐轮注入反而错乱；
  CC 实测两个 drain 点也都是批量（`query.ts` mid-turn 拿快照整批转 attachment、
  `queueProcessor.ts` 用 dequeueAllMatching），且**每条各自一条消息**，不合并。
- **"single"（取命令用）**：一条一轮。照 CC `queueProcessor.ts` 对 slash/bash 的处理——
  它给的理由是逐条的错误隔离、退码、进度 UI。

**队列里混着两种东西**：要发给模型的普通消息，和 `/`、`!` 这类**给客户端执行**的命令。
后者绝不能当文本发给模型（CC 明文：*not be sent to the model as text*），
所以 `drain(where=...)` 收谓词——注入侧滤掉命令且**把它们留在队列里**，
等本轮结束由 modes 层逐条取走执行。对应 CC 的 `dequeueAllMatching(predicate)`。

注入点在 loop 里有两处（feature 18 前置缺陷的修法）：每轮工具结果全部回填之后、
以及模型不再发 tool_calls 即将返回处。少了第二处，模型某轮直接作答时队列会永久卡死。
"""

from __future__ import annotations

from typing import Callable, List, Literal, Optional

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

    def drain(self, where: Optional[Callable[[dict], bool]] = None) -> List[dict]:
        """按模式取出消息；空队列返回 []（不抛、不返回 None）。

        `where` 只取匹配的，**不匹配的按原顺序留在队列里**——这是「命令留到本轮结束」
        的落点（feature 18 问 7）。single 模式下队首不匹配就往后找，不是返回 []：
        否则一条 `/help` 能把它后面的所有消息永久堵住。
        """
        if self.mode == "all":
            if where is None:
                drained = self._messages[:]  # 切片而非引用：调用方 append 不该改到队列
                self._messages = []
                return drained
            drained = [m for m in self._messages if where(m)]
            self._messages = [m for m in self._messages if not where(m)]
            return drained
        for i, m in enumerate(self._messages):
            if where is None or where(m):
                return [self._messages.pop(i)]
        return []

    def take_first(self) -> Optional[dict]:
        """取走队首（FIFO，**不看模式也不看谓词**）；空队列返回 None。

        给「本轮结束后清空队列」用：那里要严格按用户敲的顺序逐条走——
        消息起新一轮、命令交客户端执行，两种混排时不许重排
        （CC 的 `processQueueIfReady` 同样是先 peek 队首、再按队首的种类决定怎么处理）。
        """
        return self._messages.pop(0) if self._messages else None

    def clear(self) -> None:
        self._messages = []
