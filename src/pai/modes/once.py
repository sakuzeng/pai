"""单次任务模式：跑完即退出。对应 pi 的 print-mode。

这一层只做「接线」——把 config / tools / session 装配好交给 loop，不含业务逻辑。
client 与 model 可注入，因此这层也能离线测（否则接线错了要打真实 API 才发现）。
"""

from __future__ import annotations

from typing import Callable

from pai.config import context_window, make_client, model_name
from pai.core.compaction import CompactionSettings
from pai.core.loop import print_event, run_agent
from pai.core.events import AgentEvent, MemoryWritten
from pai.core.memory import build_context, memory_dir
from pai.core.tools import memory_tool
from pai.core.session import SessionLog
from pai.core.tools import get_tools


def run_once(
    task: str,
    *,
    max_steps: int = 20,
    max_total_tokens: int | None = None,
    no_session: bool = False,
    client=None,
    model: str | None = None,
    on_event: Callable[[AgentEvent], None] = print_event,
) -> str:
    memory_tool.set_memory_dir(memory_dir())
    memory_tool.set_notifier(
        lambda topic, path: on_event(MemoryWritten(topic=topic, path=str(path))))
    return run_agent(
        task,
        client=client or make_client(),
        model=model or model_name(),
        tools=get_tools(),
        max_steps=max_steps,
        max_total_tokens=max_total_tokens,
        session=None if no_session else SessionLog(),
        on_event=on_event,
        instructions=build_context,
        context_window=context_window(),
        compaction=CompactionSettings(),
    )
