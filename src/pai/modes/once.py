"""单次任务模式：跑完即退出。对应 pi 的 print-mode。

这一层只做「接线」——把 config / tools / session 装配好交给 loop，不含业务逻辑。
client 与 model 可注入，因此这层也能离线测（否则接线错了要打真实 API 才发现）。
"""

from __future__ import annotations

from typing import Callable, Optional

from pai.config import context_window, make_client, model_name, recall_model
from pai.core.boundary import WorkingDirs
from pai.core.compaction import CompactionSettings
from pai.core.gate import make_before_tool_call
from pai.core.hooks import load_hooks
from pai.core.loop import build_system_prompt, run_agent
from pai.core.mcp import close_all_mcp, connect_configured_servers
from pai.modes.echo import make_stream_echo
from pai.core.events import AgentEvent, MemoryWritten, RecallFailed, RecallInjected
from pai.core.memory import build_context, memory_dir
from pai.core.paths import user_skills_dir
from pai.core.permissions import DONT_ASK, RuleSet, load_rules, visible_tools
from pai.core.recall import RecallState, make_recall
from pai.core.skills import (LoadedSkills, apply_project_trust, make_instructions,
                             render_catalog, scan_skills, user_skill_link_roots)
from pai.core.tools import memory_tool
from pai.core.tools import skill as skill_tool
from pai.core.session import SessionLog
from pai.core.trace import EventTrace, compose
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
    # 观测流落盘（feature 17）：与渲染器并联,不取代它。session 为 None（--no-session）
    # 时不落——「这次别写盘」也包括观测流。
    # 上面那些 lambda 按名字查 on_event,查的是**这次重绑之后**的值,于是
    # MemoryWritten / RecallFailed 一样进事件流(闭包捕获变量而非取值)。
    if session is not None:
        on_event = compose(on_event, EventTrace(session))
    # 记忆回指产生它的那次会话（照 CC 的 originSessionId）
    memory_tool.set_origin_session(session.session_id if session is not None else None)
    # 按查询召回（feature 10）。注入的 model 优先（离线测试就靠它），否则读 PAI_RECALL_MODEL。
    recall = make_recall(client=client, model=model or recall_model(),
                         directory=directory, state=RecallState(),
                         on_failure=lambda f: on_event(RecallFailed(
                             reason=f.reason, detail=f.detail, disabled=f.disabled)),
                         on_selected=lambda names: on_event(RecallInjected(names=names)))
    # 权限（feature 07）。once 没有真人可问，asker 不传 = ask 降级为 deny（拍板问 1）。
    # rules 可注入（依赖注入优先）：不传时从两层 settings.json 读。
    # 测事件流/asker 那类 e2e 用它把权限调宽，免得被边界兜底拦住。
    rules = rules if rules is not None else load_rules(warn=print)
    hooks = load_hooks(warn=print)
    tools = visible_tools(get_tools(), rules)      # 裸名 deny 的工具压根不摆给模型
    # skills（feature 25）：装配期扫一次，目录进 system prompt、正文走 skill 工具。
    # 模型没有任何可调的 skill（一个没有，或全被 disable-model-invocation）时把
    # 工具收走——摆一个必然空手而归的工具就是让模型撞空（与 INTERACTIVE_ONLY
    # 同一个道理；once 连 /skill 通道都没有，25 复核低 3）。
    # 信任门禁（feature 28 问 2·B）：once 无人可问，未信任的项目级 skills
    # 不加载 + warn 指路（在交互模式确认一次即可信任）。
    skills = apply_project_trust(scan_skills(warn=print), warn=print)
    loaded_skills = LoadedSkills()
    skill_tool.set_catalog({s.name: s for s in skills} if skills else None)
    skill_tool.set_tracker(loaded_skills)
    if not any(s.model_invocable for s in skills):
        tools = {n: t for n, t in tools.items() if n != "skill"}
    # MCP（feature 29）：配置 → 信任门禁（once 无人可问，未信任项目级跳过+warn）
    # → 连接（单 server 失败隔离）→ 桥接并表。并表后再过一次 visible_tools：
    # deny 裸名规则对 MCP 工具照常生效。setdefault = 不覆盖内置与先到者。
    mcp_sessions, mcp_tools = connect_configured_servers(warn=print)
    for mcp_tool in mcp_tools:
        tools.setdefault(mcp_tool.name, mcp_tool)
    tools = visible_tools(tools, rules)
    # 用户级 skills 根进边界（spec 第 3 节）：否则 once 下用户级 skill 的附属
    # 文件（read_file）被「界外 ask → 无真人 deny」拦死。软链 skill 的真身根
    # 一并进（feature 28 问 3·A，dotfiles 形态受信；项目级刻意不解析）。
    # 代价如实声明：这些目录下任何文件的读取从此免问。
    working_dirs = WorkingDirs.from_startup(
        None, additional=((str(user_skills_dir()),) + user_skill_link_roots(skills))
        if skills else ())
    try:
        return run_agent(
            task,
            client=client,
            model=model or model_name(),
            tools=tools,
            # prompt 按过滤后的实际工具集生成（feature 22）——模型看见几个就说几个
            system_prompt=build_system_prompt(
                tools, skills_catalog=render_catalog(skills)),
            max_steps=max_steps,
            max_total_tokens=max_total_tokens,
            session=session,
            on_event=on_event,
            # 组合 loader（feature 25）：压缩重建后 loop 重调 instructions，
            # 已加载 skills 的正文跟着指令消息回到上下文（重挂机制，spec 第 4 节）
            instructions=make_instructions(
                build_context, loaded_skills, {s.name: s for s in skills}),
            recall=recall,
            context_window=context_window(),
            compaction=CompactionSettings(),
            # once 没有真人：模式默认 dontAsk（D#48 的显式化，见 gate.py）。
            # 显式传 mode 可覆盖——`--dangerously-skip-permissions` 就走这条。
            before_tool_call=make_before_tool_call(
                rules, hooks=hooks, tools=tools, asker=None, warn=print,
                working_dirs=working_dirs,
                mode=mode if mode is not None else DONT_ASK),
        )
    finally:
        # once 跑完即退：MCP 子进程随 run 收尾（幂等，单个失败不拦下一个）
        close_all_mcp(mcp_sessions)
