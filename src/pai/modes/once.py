"""单次任务模式：跑完即退出。对应 pi 的 print-mode。

这一层只做「接线」——把 config / tools / session 装配好交给 loop，不含业务逻辑。
client 与 model 可注入，因此这层也能离线测（否则接线错了要打真实 API 才发现）。
"""

from __future__ import annotations

from typing import Callable, Optional

from pai.config import context_window, make_client, model_name, recall_model
from pai.core.compaction import CompactionSettings
from pai.core.gate import make_before_tool_call
from pai.core.hooks import load_hooks
from pai.core.loop import run_agent
from pai.modes.echo import make_stream_echo
from pai.core.events import AgentEvent, MemoryWritten, RecallFailed
from pai.core.memory import build_context, memory_dir
from pai.core.permissions import DONT_ASK, RuleSet, load_rules, visible_tools
from pai.core.recall import RecallState, make_recall
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
    on_event: Optional[Callable[[AgentEvent], None]] = None,
    rules: RuleSet | None = None,
    mode: str | None = None,
) -> str:
    # 默认值在函数体里取：模块导入时 sys.stdout 可能还没被测试替换掉
    on_event = on_event if on_event is not None else make_stream_echo()
    directory = memory_dir()
    memory_tool.set_memory_dir(directory)
    memory_tool.set_notifier(
        lambda topic, path: on_event(MemoryWritten(topic=topic, path=str(path))))
    client = client or make_client()
    session = None if no_session else SessionLog()
    # 记忆回指产生它的那次会话（照 CC 的 originSessionId）
    memory_tool.set_origin_session(session.session_id if session is not None else None)
    # 按查询召回（feature 10）。注入的 model 优先（离线测试就靠它），否则读 PAI_RECALL_MODEL。
    recall = make_recall(client=client, model=model or recall_model(),
                         directory=directory, state=RecallState(),
                         on_failure=lambda f: on_event(RecallFailed(
                             reason=f.reason, detail=f.detail, disabled=f.disabled)))
    # 权限（feature 07）。once 没有真人可问，asker 不传 = ask 降级为 deny（拍板问 1）。
    # rules 可注入（依赖注入优先）：不传时从两层 settings.json 读。
    # 测事件流/asker 那类 e2e 用它把权限调宽，免得被边界兜底拦住。
    rules = rules if rules is not None else load_rules(warn=print)
    hooks = load_hooks(warn=print)
    tools = visible_tools(get_tools(), rules)      # 裸名 deny 的工具压根不摆给模型
    return run_agent(
        task,
        client=client,
        model=model or model_name(),
        tools=tools,
        max_steps=max_steps,
        max_total_tokens=max_total_tokens,
        session=session,
        on_event=on_event,
        instructions=build_context,
        recall=recall,
        context_window=context_window(),
        compaction=CompactionSettings(),
        # once 没有真人：模式默认 dontAsk（D#48 的显式化，见 gate.py）。
        # 显式传 mode 可覆盖——`--dangerously-skip-permissions` 就走这条。
        before_tool_call=make_before_tool_call(
            rules, hooks=hooks, tools=tools, asker=None, warn=print,
            mode=mode if mode is not None else DONT_ASK),
    )
