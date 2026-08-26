"""单次任务模式：跑完即退出。对应 pi 的 print-mode。

这一层只做「接线」——把 config / tools / session 装配好交给 loop，不含业务逻辑。
client 与 model 可注入，因此这层也能离线测（否则接线错了要打真实 API 才发现）。
装配序列自 feature 31 起收敛进 modes/assembly.py（与 interactive 共用一份），
本文件只剩 once 特有的差异点：无真人（asker=None、模式默认 dontAsk）、
单轮跑完即退（MCP 在 finally 关闭）。
"""

from __future__ import annotations

from typing import Callable, Optional

from pai.core.protocols import ChatClient
from pai.config import (context_window, keep_recent_tokens, make_client,
                        model_name, recall_model)
from pai.core import mcp
from pai.core.compaction import CompactionSettings
from pai.core.loop import build_system_prompt, run_agent
from pai.modes.assembly import assemble
from pai.modes.echo import make_stream_echo
from pai.core.events import AgentEvent
from pai.core.permissions import DONT_ASK, RuleSet
from pai.core.session import SessionLog
from pai.core.trace import EventTrace, compose
from pai.core.tools import get_tools


def run_once(
    task: str,
    *,
    max_steps: int = 20,
    max_total_tokens: int | None = None,
    no_session: bool = False,
    client: Optional[ChatClient] = None,
    model: str | None = None,
    on_event: Optional[Callable[[AgentEvent], None]] = None,
    rules: RuleSet | None = None,
    mode: str | None = None,
) -> str:
    # 默认值在函数体里取：模块导入时 sys.stdout 可能还没被测试替换掉
    on_event = on_event if on_event is not None else make_stream_echo()
    client = client or make_client()
    session = None if no_session else SessionLog()
    # 观测流落盘（feature 17）：与渲染器并联，不取代它。session 为 None
    # （--no-session）时不落——「这次别写盘」也包括观测流。compose 必须在
    # assemble 之前：memory/recall 的事件闭包捕获的是传进去的最终通道。
    if session is not None:
        on_event = compose(on_event, EventTrace(session))
    # 共用装配（feature 31）。once 没有真人：asker=None（ask 降级 deny，
    # 拍板问 1；信任门禁同理「无人可问」跳过项目级）；模式默认 dontAsk
    # （D#48 的显式化，见 gate.py），显式传 mode 可覆盖——
    # `--dangerously-skip-permissions` 就走这条。
    asm = assemble(
        client=client, tools=get_tools(), warn=print, on_event=on_event,
        session=session, recall_model=model or recall_model(),
        mode=mode if mode is not None else DONT_ASK, asker=None, rules=rules)
    # feature 33（09 遗留 2）：settings 配了 defaultMode 而 once 用不上时说一声
    # ——行为不变（无人可问只能 dontAsk），但静默会让用户以为配置生效了。
    if mode is None and asm.rules.mode_source is not None \
            and asm.rules.mode != DONT_ASK:
        print(f"⚠️ settings 配置的 defaultMode `{asm.rules.mode}`"
              f"（{asm.rules.mode_source}）在单次模式下未采用：无人可问，"
              "本次按 dontAsk 执行（需确认的调用一律拒绝）。"
              "要放开：进交互模式，或显式传 --permission-mode。")
    try:
        return run_agent(
            task,
            client=client,
            model=model or model_name(),
            tools=asm.tools,
            # prompt 按过滤后的实际工具集生成（feature 22）——模型看见几个就说几个
            system_prompt=build_system_prompt(
                asm.tools, skills_catalog=asm.skills_catalog),
            max_steps=max_steps,
            max_total_tokens=max_total_tokens,
            session=session,
            on_event=on_event,
            instructions=asm.instructions,
            recall=asm.recall,
            context_window=context_window(),
            compaction=CompactionSettings(keep_recent_tokens=keep_recent_tokens()),
            before_tool_call=asm.gate,
            on_context_rewritten=asm.on_context_rewritten,
        )
    finally:
        # once 跑完即退：MCP 子进程随 run 收尾（幂等，单个失败不拦下一个）
        mcp.close_all_mcp(asm.mcp_sessions)
