"""单次任务模式：跑完即退出。对应 pi 的 print-mode。

这一层只做「接线」——把 config / tools / session 装配好交给 loop，不含业务逻辑。
client 与 model 可注入，因此这层也能离线测（否则接线错了要打真实 API 才发现）。
"""

from __future__ import annotations

from typing import Callable

from pai.config import context_window, make_client, model_name
from pai.core.compaction import CompactionSettings
from pai.core.gate import make_before_tool_call
from pai.core.hooks import load_hooks
from pai.core.loop import print_event, run_agent
from pai.core.events import AgentEvent, MemoryWritten
from pai.core.memory import build_context, memory_dir
from pai.core.permissions import RuleSet, load_rules, visible_tools
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
    rules: RuleSet | None = None,
) -> str:
    memory_tool.set_memory_dir(memory_dir())
    memory_tool.set_notifier(
        lambda topic, path: on_event(MemoryWritten(topic=topic, path=str(path))))
    # 权限（feature 07）。once 没有真人可问，asker 不传 = ask 降级为 deny（拍板问 1）。
    # rules 可注入（依赖注入优先）：不传时从两层 settings.json 读。
    # 测事件流/asker 那类 e2e 用它把权限调宽，免得被边界兜底拦住。
    rules = rules if rules is not None else load_rules(warn=print)
    hooks = load_hooks(warn=print)
    tools = visible_tools(get_tools(), rules)      # 裸名 deny 的工具压根不摆给模型
    return run_agent(
        task,
        client=client or make_client(),
        model=model or model_name(),
        tools=tools,
        max_steps=max_steps,
        max_total_tokens=max_total_tokens,
        session=None if no_session else SessionLog(),
        on_event=on_event,
        instructions=build_context,
        context_window=context_window(),
        compaction=CompactionSettings(),
        before_tool_call=make_before_tool_call(
            rules, hooks=hooks, tools=tools, asker=None, warn=print),
    )
