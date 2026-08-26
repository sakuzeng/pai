"""`/命令` 与 `!shell` 模式：两条主循环共用的那一半（feature 40 从 interactive 抽出）。

抽出来的理由不是行数，是位置：这一簇被 REPL 主循环与 TUI 主循环**共用**，
而共用的东西住在其中一条循环所在的文件里本身就是位置错误
（与 feature 36 把宽度原语从 statusline 挪进 tui/width.py 是同一条判据）。

边界：这里只放「一条命令怎么执行、打什么字」，不放循环本身——
谁在读输入、什么时候算一轮结束，仍归 `interactive.py`。
命令要用到的跨轮状态（messages / 锚点簿 / 熔断状态 / 台账）一律由调用方传进来，
本模块不持有任何状态，也不认识 driver 与 app。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from pai.core.events import Compacted, ConversationCleared
from pai.core.compaction import (
    compact,
    context_tokens,
    find_cut_point,
    keep_recent_shortfall,
)
from pai.core.interrupt import _interruptible
from pai.core.loop import build_system_prompt, drop_instructions
from pai.core.memory import (
    AGENTS_FILE,
    LOCAL_FILE,
    MEMORY_INDEX,
    PROJECT_FILE,
    USER_DIR,
    discover,
    memory_dir,
)
from pai.core.paths import sessions_dir
from pai.core.permissions import MODE_CYCLE, MODES
from pai.core.rules import scan_rules
from pai.core.tools import Tool, get_tools
from pai.core.tools import skill as skill_tool
from pai.core.skills import read_skill_body
from pai.core.boundary import dangerous_writes_description
from pai.tui.sanitize import sanitize_terminal_text


HELP = """可用命令：
  /help     这张表
  /status   上下文估算、锚点数、压缩熔断状态
  /memory   本次加载了哪些指令文件 + 自动记忆目录在哪（`/memory reload` 重新读盘）
  /mode     查看/切换权限模式（TUI 里也可按 shift+tab 轮转）
  /permissions  当前生效的权限规则与各自来源
  /compact  手动压缩当前对话
  /skill    列出可用 skills；`/skill <名> [参数]` 加载并执行
  /clear    清空对话（保留 system）
  /exit     退出（等同 Ctrl+D）
其他输入直接发给模型；`!命令` 直接跑 shell 且不打模型；行尾 `\\` 续行。"""


def _expand_skill_line(line: str, out: Callable[[str], None]) -> Optional[str]:
    """`/skill [名 [参数]]` → 展开成要发给模型的任务文本（pi 的 /skill:name 形态）。

    返回 None 表示没有可跑的轮次（裸列表 / 未知名 / 读失败），提示已打给用户。
    目录表从工具模块取（装配层注入的同一份）；用户通道**不看** model_invocable——
    它只限模型自动加载（拍板问 4）。展开的加载同样计入重挂追踪器：
    用户显式加载的正文没理由比模型加载的低一等。
    """
    catalog = skill_tool.get_catalog()
    parts = line.split(None, 2)
    if len(parts) == 1:
        if not catalog:
            out("没有可用的 skill。放一个 `<名字>/SKILL.md` 到 ~/.pai/skills/ 或 <项目>/.pai/skills/ 即可。")
            return None
        out("可用 skills（`/skill <名> [参数]` 加载并执行）：")
        for name in sorted(catalog):
            desc = catalog[name].description
            out(f"  {name}  {desc[:80]}{'…' if len(desc) > 80 else ''}")
        return None
    name, args = parts[1], (parts[2] if len(parts) > 2 else "")
    entry = catalog.get(name)
    if entry is None:
        out(f"未知 skill：{name}。可用：{'、'.join(sorted(catalog)) or '（无）'}")
        return None
    try:
        body = read_skill_body(entry)
    except (OSError, UnicodeDecodeError) as e:
        out(f"skill `{name}` 读取失败（{type(e).__name__}: {e}）")
        return None
    tracker = skill_tool.get_tracker()
    if tracker is not None:
        tracker.record(name)
    block = (f'<skill name="{name}">\n{body}\n</skill>\n'
             f"（本 skill 引用的相对路径以 {entry.base_dir} 为基准。）")
    return f"{block}\n\n{args}" if args else block


def _handle_command(line: str, *, out, messages, anchors, state, tools, client, model,
                    compaction, context_window, rules=None, hooks=(),
                    mode_state=None, on_event=None, session=None,
                    ledger: Optional[List[Optional[str]]] = None,
                    rule_state=None) -> bool:
    """返回 True 表示要退出 REPL。"""
    command = line.split()[0]
    if command in ("/exit", "/quit"):
        return True
    if command == "/help":
        out(HELP)
    elif command == "/clear":
        del messages[1:]         # 保留 system；整段清掉会让下一轮重建，等价但更难解释
        if ledger is not None:
            del ledger[1:]       # 台账同步裁（feature 24）：不裁下次压缩 ledger[cut] 指错条目
        anchors.reset()
        state.failures, state.awaiting_verify, state.tripped = 0, False, False
        # 观测流里必须留痕（feature 17）：清空前后是两段互不记得的对话，
        # 不发这个事件的话时间线会把它们画成连贯的一段。
        # feature 37 起它还兼一职：召回去重表与规则注入表靠它作废
        # （`events.CONTEXT_REWRITING`）——`/clear` 比压缩更彻底，
        # 不清的话那几篇记忆此后再也不会被选中，且完全静默。
        if on_event is not None:
            on_event(ConversationCleared(kept=len(messages)))
        out("🧹 已清空对话（保留 system）")
    elif command == "/status":
        latest = anchors.latest()
        schemas = [t.schema() for t in tools.values()]
        estimated = context_tokens(messages, schemas,
                                   anchor=None if latest.index is None else latest.tokens,
                                   anchor_index=latest.index or 0)
        breaker = "已熔断" if state.tripped else f"正常（失败 {state.failures} 次）"
        out(f"📊 消息 {len(messages)} 条 | 估算 {estimated} token / 窗口 {context_window}"
            f" | 锚点 {len(anchors.entries)} 个 | 压缩：{breaker}")
    elif command == "/memory":
        if line.split()[1:2] == ["reload"]:
            # 06 task 4：`_inject_instructions` 认出已有指令消息就直接返回，
            # 连 loader 都不调——多轮 REPL 只在第一轮读盘。丢掉那条消息，
            # 下一轮的注入点就会重新读盘（压缩后的重注入走的也是这条路）。
            dropped = drop_instructions(messages, ledger if ledger is not None else [])
            out("🔄 指令消息已丢弃，下一轮重新读盘。" if dropped
                else "🔄 当前上下文里还没有指令消息，下一轮本来就会读盘。")
        _show_memory(out, rule_state=rule_state)
    elif command == "/mode":
        _handle_mode(line, out=out, mode_state=mode_state)
    elif command == "/permissions":
        _show_permissions(out, rules, hooks, mode_state=mode_state)
    elif command == "/compact":
        _manual_compact(messages=messages, anchors=anchors, state=state,
                        client=client, model=model, compaction=compaction, out=out,
                        on_event=on_event, session=session, ledger=ledger,
                        )
    elif command == "/skill":
        # 只有对话框 handoff 这类没有轮次机器的调用方会走到这里：
        # 列表照常给，「加载并执行」提示去空闲时做
        _expand_skill_line(line.split()[0], out)      # 裸列表（带名字也只列出提示）
        if len(line.split()) > 1:
            out("（提问/忙碌中无法启动 skill 轮次，请空闲时再 /skill <名>）")
    else:
        out(f"未知命令 {command}，/help 看可用命令")
    return False


def _handle_mode(line: str, *, out: Callable[[str], None], mode_state=None) -> None:
    """`/mode` —— 快捷键之外必须有的那条路径。

    CC 明说组合键在部分终端不可靠（Windows 无 VT mode 时 shift+tab 收不到），
    所以模式切换**命令与快捷键都要有**，不是二选一。
    """
    if mode_state is None:
        out("[权限] 模式未装配（该模式下模式不可切）")
        return
    parts = line.split()
    if len(parts) == 1:
        out(f"[权限] 当前模式：{mode_state()}")
        out(f"   可选：{', '.join(MODES)}")
        out(f"   shift+tab 轮转顺序：{' → '.join(MODE_CYCLE)}"
            "（dontAsk 不在环里：它与「无真人」是同一件事）")
        return
    try:
        out(f"[权限] 模式 → {mode_state.set(parts[1])}")
    except ValueError as e:
        out(f"❌ {e}")


def _show_permissions(out: Callable[[str], None], rules, hooks=(), *,
                      mode_state=None) -> None:
    """列出规则与来源。「被哪条规则挡的、那条从哪来」是用户能自己修的前提。"""
    if mode_state is not None:
        out(f"[权限] 当前模式：{mode_state()}")
    if rules is None:
        out("🔒 权限：未装配规则")
        return
    lines = [
        f"  {kind:5} {rule.text()}   （来源：{rule.source}）"
        for kind in ("deny", "ask", "allow")
        for rule in rules.bucket(kind)
    ]
    if not lines:
        out(f"🔒 权限：没有任何规则，一律按默认决策 `{rules.default_decision}`。"
            "规则写在 ~/.pai/settings.json 或 ./.pai/settings.json 的 permissions 里。")
        _show_boundary_caveats(out)     # 新用户恰好走这条分支，真话不能省
        return
    out("🔒 权限规则（求值顺序 deny → ask → allow，第一个匹配决定）：")
    for line in lines:
        out(line)
    out(f"  没有规则命中时按默认决策 `{rules.default_decision}`")
    _show_hooks(out, hooks)
    _show_boundary_caveats(out)


def _show_boundary_caveats(out: Callable[[str], None]) -> None:
    """feature 33（09 遗留 1 提示半边 + 遗留 3）：两件此前不可见的真话。

    bash 那条是本权限功能的主要失效模式（D#52）：洞不在默认路径（bash 默认
    ask），而在用户为了可用性必然配的 allow 白名单上——配了 `Bash(cat *)`，
    `cat ../../etc/passwd` 就畅通无阻。不说出来，用户会以为白名单是安全的。
    """
    from pai.core.boundary import dangerous_writes_description

    out("⚠️ bash 不参与工作目录边界（D#52）：给 bash 配 allow 白名单 = 白名单内")
    out("   的命令可以越界读写任何路径。要限制范围就别给 bash 配宽 allow。")
    out("🛡 危险写清单（写入永远确认，acceptEdits/bypass 都翻不过）：")
    for item in dangerous_writes_description():
        out(f"   - {item}")


def _show_hooks(out: Callable[[str], None], hooks) -> None:
    if not hooks:
        return
    out("🪝 PreToolUse hook（退出码 2 = 阻断，崩溃/超时不阻断）：")
    for spec in hooks:
        out(f"  {spec.matcher:8} {spec.command}   （超时 {spec.timeout}s）")


def _show_memory(out: Callable[[str], None], rule_state=None) -> None:
    """官方 /memory 的最小版。它首先是个调试工具：指令没生效时，
    第一步永远是确认文件到底有没有被加载——所以列的是路径与行数，不是内容。"""
    files = discover()
    if not files:
        out(f"📄 没有加载任何指令文件（找的是 {AGENTS_FILE} / {PROJECT_FILE} / "
            f"{LOCAL_FILE}，从当前目录向上逐级，外加 ~/{USER_DIR}/ 下的同名文件）")
    else:
        out("📄 已加载的指令文件（按加载顺序，后面的更靠近对话）：")
        for path in files:
            try:
                lines = len(path.read_text(encoding="utf-8").splitlines())
            except OSError:
                lines = 0
            out(f"  {path}（{lines} 行）")
    # 路径作用域规则（feature 36）：这层的失效方式天然是沉默的——规则没进上下文，
    # 模型照样给一个像样的回答。所以它必须能在这里被看见。没有规则时一节都不打。
    scoped = scan_rules(warn=lambda _m: None)
    if scoped:
        injected = rule_state.injected if rule_state is not None else set()
        out("📐 路径作用域规则（碰到匹配文件时才加载）：")
        for rule in scoped:
            mark = "（本会话已注入）" if rule.name in injected else ""
            out(f"  {rule.name}：{'、'.join(rule.patterns)}{mark}")
    directory = memory_dir()
    index = directory / MEMORY_INDEX
    state = "有索引" if index.is_file() else "还没有内容"
    out(f"🧠 自动记忆目录：{directory}（{state}）")
    # 会话也要列：这次需求的起点就是用户翻到那些文件、不知道它们是什么、在哪（feature 08）
    out(f"💾 会话记录目录：{sessions_dir()}")


def _manual_compact(*, messages, anchors, state, client, model, compaction, out,
                    on_event=None, session=None,
                    ledger: Optional[List[Optional[str]]] = None) -> None:
    cut = find_cut_point(messages, anchors.entries,
                         keep_recent_tokens=compaction.keep_recent_tokens)
    if cut <= 1:
        if len(anchors.entries) < 2:
            out("🗜️ 锚点不足（<2）：真实切点要靠相邻锚的差值反推，先聊两轮再压。")
        else:
            # 「无可压」分不清「坏了」与「还没到量」，而差额是算得出来的
            # （TODO「压缩链路的可验证性」：/compact 在真实会话里几乎永远走到这里）
            short = keep_recent_shortfall(anchors.entries, compaction.keep_recent_tokens)
            if short:
                out(f"⚠️ 无可压：还差约 {short} token 才切得动"
                    f"（保留门槛 {compaction.keep_recent_tokens}）。"
                    "继续聊几轮，或用 PAI_KEEP_RECENT_TOKENS 把门槛调小。")
            else:
                out("⚠️ 无可压：历史够长，但可切的锚点都落在开头（或只剩一个超长轮次）。")
        return
    before = len(messages)
    # firstKeptEntryId 要在 messages 被替换之前取（cut 是旧列表下标，feature 24）
    first_kept = ledger[cut] if ledger is not None and cut < len(ledger) else None
    try:
        messages[:], summary, usage = compact(messages, cut=cut, client=client,
                                              model=model)
    except Exception as e:   # noqa: BLE001 - 网络边界，什么都可能抛
        # `/compact` 是唯一碰网络的命令路径。此前它一路裸抛：REPL 下整个 while
        # 循环带栈掀掉、TUI 下大 try 只有 finally（终端复原了但对话没了）。
        # 而这恰恰是最不该丢上下文的时刻——用户按 `/compact` 正是因为上下文
        # 已经攒得很长。`messages` 无需回滚：替换发生在 compact 成功返回之后。
        out(f"⚠️ 压缩失败（{type(e).__name__}: {e}），历史未改动，可稍后重试。")
        return
    anchors.reset()                        # 历史被改写，旧锚全部作废（D#18/32）
    state.awaiting_verify = True           # 成败仍只认压缩后首次真实 usage（D#34）
    # 落盘与台账重建与自动压缩同款（feature 24）：/compact 此前根本不落盘，
    # resume 这类读盘重建的消费者一到就露馅
    comp_id = None
    if session is not None:
        comp_id = session.append({"type": "compaction", "step": 0, "cut": cut,
                                  "firstKeptEntryId": first_kept,
                                  "summary": summary, "usage": usage})
    if ledger is not None:
        ledger[:] = [ledger[0] if ledger else None, comp_id] + ledger[cut:]
    # 与自动压缩发同一个事件:上下文被换掉这件事,不该因为「是人手动按的」就在观测流里消失。
    # 它同样兼作跨轮状态的作废信号（feature 37，`events.CONTEXT_REWRITING`）
    if on_event is not None:
        on_event(Compacted(cut=cut, before=before, after=len(messages)))
    out(f"🗜️ 已压缩：切于 {cut}，消息 {before} → {len(messages)} 条，"
        f"摘要 {len(summary)} 字，摘要请求用了 {usage.get('total_tokens') or 0} token")


def _system_prompt() -> str:
    from pai.core.loop import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _run_shell(command: str, *, messages: List[dict], session, out,
               system_prompt: Optional[str] = None,
               ledger: Optional[List[Optional[str]]] = None) -> None:
    """`!命令`：不经模型直接跑，命令与输出都进上下文。

    官方 v2.1.186 起会在输出进上下文后**自动接话**，pai 默认不接——每次 `!` 都自动接话
    等于每次都花一次请求钱（官方自己也给了 respondToBashCommands 开关）。
    """
    if not command:
        out("用法：!<命令>")
        return
    bash: Tool = get_tools(["bash"])["bash"]
    output = bash.run(command=command)
    # 给终端看的那一份要消毒（外来字节会打乱 dock 的相对定位、`\t` 全链算 1 列）；
    # **下面进 messages 的仍是原文**——命令真打印了什么，模型就该看见什么。
    out(sanitize_terminal_text(output))
    entry = {"role": "user", "content": f"我执行了命令 `{command}`，输出：\n{output}"}
    # 入账走 loop._record（feature 24 关掉 23 的遗留：REPL 侧不再有自己的成对
    # append）；ledger 不传时用哑表——对齐语义由调用方负责
    from pai.core.loop import _record
    book = ledger if ledger is not None else []
    if not messages:
        # 首个动作就是 `!命令` 时由这里建 system：优先用装配层生成的（feature 22），
        # 不接线会建出常量、之后整个会话都换不掉
        _record(messages, {"role": "system",
                           "content": system_prompt if system_prompt is not None
                           else _system_prompt()}, session, book)
    _record(messages, entry, session, book)


def _dispatch_command(line: str, *, commit, app, session, flag, on_event, **kw) -> bool:
    """`/命令` 与 `!命令`。返回 True 表示要退出。"""
    if line.startswith("!"):
        with _interruptible(flag):
            try:
                _run_shell(line[1:].strip(), messages=kw["messages"],
                           session=session, out=commit,
                           system_prompt=build_system_prompt(
                               kw["tools"], skills_catalog=kw.get("skills_catalog")),
                           ledger=kw.get("ledger"))
            except KeyboardInterrupt:
                commit("⛔ 已中断")
        app.refresh()
        return False
    if line.split()[0] == "/skill" and len(line.split()) > 1:
        # 忙碌/对话框期敲的 /skill：展开后进 steering 队列——正在跑的轮次会把它
        # 当用户消息注入（feature 18 的两个出口），轮末残余由队列处理兜住
        steering = kw.get("steering")
        expanded = _expand_skill_line(line, commit)
        if expanded is not None and steering is not None:
            steering.enqueue({"role": "user", "content": expanded})
        return False
    return _handle_command(line, out=commit, messages=kw["messages"],
                           anchors=kw["anchors"], state=kw["state"], tools=kw["tools"],
                           client=kw["client"], model=kw["model"],
                           compaction=kw["compaction"],
                           context_window=kw["context_window"], rules=kw["rules"],
                           hooks=kw["hooks"], mode_state=kw["mode_state"],
                           on_event=on_event, session=session,
                           ledger=kw.get("ledger"),
                           rule_state=kw.get("rule_state"))
