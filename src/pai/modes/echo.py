"""增量文本上屏（feature 11 task 6）。

为什么不放进 `events.render_text`：那个函数的契约是「返回一行」，
而流式增量必须**不换行**地写出去。契约不合，所以上屏归 modes 层（D#39 渲染下放）。

**最终答案不许打两遍**。流式之前，`cli.py` 与 `interactive._run_turn` 在结尾各打一句
`🤖 {answer}`；流式之后那段文字已经逐字打过了。区分靠 `AgentEnd.reason`：

- `final` —— 文本**是模型说的**，已经流过 → 不重打；
- `budget` / `max_steps` / `interrupted` —— 文本**是 loop 合成的**，从来没流过 → 必须打。

这条规则是本模块存在的全部理由，改它之前先想清楚这两类文本的来源不同。
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from pai.core.events import AgentEnd, AgentEvent, AssistantMessage, MessageDelta, render_text

ROBOT_PREFIX = "🤖 "


def make_stream_echo(stream=None, *,
                     fallback: Optional[Callable[[AgentEvent], None]] = None
                     ) -> Callable[[AgentEvent], None]:
    """返回一个事件处理器：增量逐字写，其余交给 `fallback`（默认按 render_text 打一行）。

    `fallback` 让 REPL 能把状态行插在中间——它先处理 ToolStart/ToolEnd，
    剩下的再回落到这里的默认渲染。
    """
    out = stream if stream is not None else sys.stdout
    # 用可变容器而不是 nonlocal：这个处理器可能被跨轮复用，状态得跟着处理器走
    streaming = {"active": False}

    def default_render(event: AgentEvent) -> None:
        text = render_text(event)
        if text is not None:
            out.write(text + "\n")
            out.flush()

    handle_rest = fallback if fallback is not None else default_render

    def handle(event: AgentEvent) -> None:
        if isinstance(event, MessageDelta):
            if not streaming["active"]:
                out.write("\n" + ROBOT_PREFIX)     # 每条消息只戴一次帽子
                streaming["active"] = True
            out.write(event.text)
            out.flush()
            return
        if isinstance(event, AssistantMessage):
            if streaming["active"]:
                out.write("\n")                    # 把这条消息收尾，后面的事件从新行开始
                out.flush()
                streaming["active"] = False
            return
        if isinstance(event, AgentEnd):
            # 中断掐在流中途时不会有 AssistantMessage 事件，这里补收尾
            if streaming["active"]:
                out.write("\n")
                out.flush()
                streaming["active"] = False
            if event.reason != "final" and event.text:
                out.write(event.text + "\n")
                out.flush()
            return
        handle_rest(event)

    return handle
