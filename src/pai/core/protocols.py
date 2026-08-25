"""跨模块共用的结构化类型（Protocol）。

存在的理由（R#14）：`run_agent(client=…)`、`summarize(client=…)`、`run_once(client=…)`
全都是裸的无注解参数，而「client 是什么」恰恰是依赖注入这条设计线的核心——
离线测试塞的是 `tests/fake_llm.FakeClient`，真跑塞的是 `openai.OpenAI`，
两者唯一的共同契约就是这里写下的这几行。写成 Protocol 而不是基类：
两边谁也不该 import 对方，结构化子类型正是为这种缝设计的（鸭子类型，静态可查）。

刻意只描述 pai 真正用到的那一条路径 `client.chat.completions.create(...)`：
Protocol 描述得越宽，能通过的实现越少，而 pai 并不想约束 provider SDK 的其余部分。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Completions(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """返回值刻意是 Any：非流式时是 provider 的响应对象、流式时是块迭代器，
        两者的具体形状由 SDK 定义且各家不同——在这里假装知道它反而会说谎。
        真正读它的地方（`core/streaming.py`、`usage_fields`）自己做防御性取字段。
        """


@runtime_checkable
class Chat(Protocol):
    completions: Completions


@runtime_checkable
class ChatClient(Protocol):
    """OpenAI 兼容 client 的最小面：只有 `chat.completions.create`。"""

    chat: Chat
