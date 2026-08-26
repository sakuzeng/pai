"""装配收敛（feature 31）：once 与 interactive 共用的装配序列，一份实现。

此前 `once.run_once` 与 `interactive.run_interactive` 各自手抄同一套接线
（rules/hooks → skills 信任 → MCP 信任与并表 → boundary → gate → memory →
recall），feature 25/28/29 三轮都要同步改两处。收敛后模式层只注入差异点：
asker（once 无人可问传 None）、权限模式（once 传字符串、interactive 传
PermissionModeState 可变持有者）、warn 与事件通道。

依赖约束照 AGENTS「架构约束」：只依赖 core 各模块与注入回调，不 import
loop.py 内部（system prompt 的构建留在各模式层）。MCP 调用走 `mcp.` 模块
属性而非顶层 from-import——调用点才解析属性，测试打得了桩
（tests/test_assembly.py 与 test_mcp.py 的 `mcp_mod.…` 同口径）。
MCP 关闭不在本模块：连接的生命周期归调用方的单出口 finally（29 遗留 7）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from pai.core.protocols import ChatClient
from pai.core import mcp
from pai.core.boundary import WorkingDirs
from pai.core.events import MemoryWritten, RecallFailed, RecallInjected
from pai.core.gate import make_before_tool_call
from pai.core.hooks import load_hooks
from pai.core.memory import build_context, memory_dir
from pai.core.paths import user_skills_dir
from pai.core.permissions import RuleSet, load_rules, visible_tools
from pai.core.recall import RecallState, make_recall
from pai.core.skills import (LoadedSkills, Skill, apply_project_trust,
                             make_instructions, render_catalog, scan_skills,
                             user_skill_link_roots)
from pai.core.settings import (additional_directories, bash_timeout_seconds,
                               load_settings)
from pai.core.tools import memory_tool
from pai.core.tools import shell
from pai.core.tools import skill as skill_tool


@dataclass
class Assembly:
    """装配产物：模式层拿它去接 run_agent / 主循环。"""

    rules: RuleSet
    hooks: list
    tools: Dict[str, object]
    skills: List[Skill]
    skills_catalog: str
    instructions: Callable[[], str]
    loaded_skills: LoadedSkills
    working_dirs: WorkingDirs
    mcp_sessions: list
    recall: Callable
    gate: Callable
    on_context_rewritten: Callable[[], None]


def assemble(*, client: ChatClient, tools: Dict[str, object],
             warn: Callable[[str], None],
             on_event: Callable, session, recall_model: str, mode,
             asker=None, rules: Optional[RuleSet] = None) -> Assembly:
    """共用装配序列。参数即两模式的差异点：

    - `asker`：once 传 None（skills/MCP 信任门禁与权限 ask 都按「无人可问」
      降级），interactive 传装配期 asker（AskerRef，TUI 起来前是 reader 版）；
    - `mode`：once 传字符串（默认 DONT_ASK 由调用方算好——D#48/D#53 合流），
      interactive 传 PermissionModeState 可变持有者，gate 两种都认；
    - `on_event`：必须是已与观测流 compose 过的最终通道——memory/recall 的
      事件闭包捕获的就是这个值，传早了事件进不了落盘流。
    """
    # 权限与 hook（feature 07/09）。rules 可注入（依赖注入优先，测试靠它调宽）。
    rules = rules if rules is not None else load_rules(warn=warn)
    hooks = load_hooks(warn=warn)
    # bash 默认超时可配置（settings `bash.timeoutSeconds`）。未配置传 None
    # 显式清空——上一个装配的残留不许漂给下一个。
    merged_settings = load_settings(warn=warn)
    shell.set_default_timeout(bash_timeout_seconds(merged_settings, warn=warn))
    # 边界的额外允许根（feature 33 H9：文档声称已久、实际首次接线）
    extra_dirs = additional_directories(merged_settings, warn=warn)
    tools = visible_tools(tools, rules)      # 裸名 deny 的工具压根不摆给模型
    # skills（feature 25/28）：装配期扫一次；项目级过信任门禁；模型没有任何
    # 可调的 skill（一个没有，或全被 disable-model-invocation）时把工具收走
    # ——摆一个必然空手而归的工具就是让模型撞空（25 复核低 3）。
    # /skill 用户通道不受影响，它走 get_catalog 不走工具集。
    skills = apply_project_trust(scan_skills(warn=warn), ask=asker, warn=warn)
    loaded_skills = LoadedSkills()
    skill_tool.set_catalog({s.name: s for s in skills} if skills else None)
    skill_tool.set_tracker(loaded_skills)
    if not any(s.model_invocable for s in skills):
        tools = {n: t for n, t in tools.items() if n != "skill"}
    # MCP（feature 29）：配置 → 信任门禁 → 连接（单 server 失败 warn 隔离）
    # → 桥接并表。setdefault = 不覆盖内置与先到者；并表后再过一次
    # visible_tools，deny 裸名规则对 MCP 工具照常生效。
    mcp_sessions, mcp_tools, mcp_failed = mcp.connect_configured_servers(
        ask=asker, warn=warn)
    for mcp_tool in mcp_tools:
        tools.setdefault(mcp_tool.name, mcp_tool)
    tools = visible_tools(tools, rules)
    # 连接失败告知模型（29 遗留 6）：只 warn 给用户的话，模型会反复试不存在的
    # 工具名。搭 instructions 的车而不是 system prompt——零管线新增，且指令
    # 消息在压缩重建后会重注入，告知不随压缩丢失。无失败时逐字不变。
    base_instructions = build_context
    if mcp_failed:
        note = ("\n\n# MCP server 连接失败\n\n以下已配置的 MCP server 本次"
                f"连接失败，其工具不可用：{'、'.join(mcp_failed)}"
                "（具体原因见启动告警）。不要调用它们的工具。")
        def base_instructions() -> str:
            return build_context() + note
    # 用户级 skills 根进边界（25 spec 第 3 节）：否则附属文件的 read_file 被
    # 「界外 ask」拦住（once 下直接 deny）。软链真身根一并进（28 问 3·A，
    # dotfiles 受信；项目级刻意不解析）。代价如实声明：这些目录从此免问读。
    working_dirs = WorkingDirs.from_startup(
        None, additional=extra_dirs
        + (((str(user_skills_dir()),) + user_skill_link_roots(skills))
           if skills else ()))
    gate = make_before_tool_call(rules, hooks=hooks, tools=tools, asker=asker,
                                 warn=warn, working_dirs=working_dirs, mode=mode)
    # 记忆（阶段 3 + feature 10）：目录/通知/会话回指都走注入点。
    directory = memory_dir()
    memory_tool.set_memory_dir(directory)
    memory_tool.set_notifier(
        lambda topic, path: on_event(MemoryWritten(topic=topic, path=str(path))))
    memory_tool.set_origin_session(session.session_id if session is not None else None)
    # 召回（feature 10）：状态跟随本次装配的生命周期（REPL 跨轮持有，
    # 去重与失败熔断不清零；once 单轮即弃）。
    recall_state = RecallState()
    recall = make_recall(client=client, model=recall_model, directory=directory,
                         state=recall_state,
                         on_failure=lambda f: on_event(RecallFailed(
                             reason=f.reason, detail=f.detail, disabled=f.disabled)),
                         on_selected=lambda names: on_event(RecallInjected(names=names)))
    def on_context_rewritten() -> None:
        """上下文被改写（自动压缩 / `/compact` / `/clear`）之后要作废的东西。

        目前只有召回的去重表：`surfaced` 记的是「这几篇已经在上下文里」，
        压缩会把它们切进摘要、`/clear` 会整段删掉，那句话就成了假的——
        而 `surfaced` 还拦着它们不再被选中，于是召回在长会话里静默衰减到零
        （10 遗留 6，用户 2026-08-26 拍板选「上下文被改写就全清」）。
        代价：那几篇可能被再召回一次，多花一次注入的 token。
        """
        recall_state.surfaced.clear()

    return Assembly(
        rules=rules, hooks=hooks, tools=tools, skills=skills,
        skills_catalog=render_catalog(skills),
        # 组合指令 loader（feature 25）：压缩重建后 loop 重调 instructions，
        # 已加载 skills 的正文跟着指令消息回到上下文（重挂，零 loop 改动）
        instructions=make_instructions(base_instructions, loaded_skills,
                                       {s.name: s for s in skills}),
        loaded_skills=loaded_skills, working_dirs=working_dirs,
        mcp_sessions=mcp_sessions, recall=recall, gate=gate,
        on_context_rewritten=on_context_rewritten)
