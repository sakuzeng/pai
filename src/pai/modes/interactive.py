r"""交互模式：纯 REPL（对应 pi 的 interactive 模式，TUI 是阶段 2 后半程）。

与 once 一样，这层只做「接线 + 输入层」，业务在 core。三样东西是 REPL 独有的：

1. **跨轮持有状态**：messages / 锚点簿 / 熔断状态都在这里，每轮传给 run_agent。
   不这么做的话每轮第一次请求都退回纯字符估算（-33% 误差），熔断器也每轮清零。
2. **输入层**：历史（按工作目录分文件、连续重复只记一条）、`\` 续行、`!` shell 模式、
   `/` 命令——四条语义全部照官方 interactive-mode 章节
   （K knowledge/claude-docs/interactive-mode.md），做不到的（Shift+Enter、补全、
   转录查看器）在那篇笔记里逐条记了为什么。
3. **中断**：干活期间 SIGINT 只置标志不抛异常，loop 与 bash 各自在自己的检查点响应；
   空闲期间恢复默认处理器，于是 input() 照常抛 KeyboardInterrupt，走「两级 Ctrl+C」。

诚实边界：纯 REPL 的 input() 是阻塞的，agent 干活时用户根本没法打字，
所以只有 followUp 队列有真实输入源，steering 传 None（结构与注入点已在 loop 里备好，
等 TUI/流式才通电）。
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import signal
import sys
from pathlib import Path
from typing import Callable, List, Optional

from pai.config import context_window as default_context_window
from pai.config import make_client, model_name
from pai.core.compaction import (
    AnchorBook,
    CompactionSettings,
    CompactionState,
    compact,
    context_tokens,
    find_cut_point,
)
from pai.core.events import (
    AgentEnd,
    AgentEvent,
    MemoryWritten,
    ToolEnd,
    ToolStart,
    render_text,
)
from pai.core.interrupt import InterruptFlag, set_current
from pai.core.gate import make_before_tool_call
from pai.core.hooks import load_hooks
from pai.core.loop import run_agent
from pai.core.permissions import RuleSet, load_rules, visible_tools
from pai.core.paths import sessions_dir
from pai.core.memory import (
    LOCAL_FILE,
    MEMORY_INDEX,
    PROJECT_FILE,
    USER_DIR,
    build_context,
    discover,
    memory_dir,
)
from pai.core.queue import PendingMessageQueue
from pai.core.session import SessionLog
from pai.core.tools import Tool, ask, get_tools, memory_tool
from pai.modes.statusline import StatusLinePrinter

PROMPT = "› "
CONTINUATION_PROMPT = "… "
HISTORY_BASE = Path.home() / ".pai" / "history"

HELP = """可用命令：
  /help     这张表
  /status   上下文估算、锚点数、压缩熔断状态
  /memory   本次加载了哪些指令文件 + 自动记忆目录在哪
  /permissions  当前生效的权限规则与各自来源
  /compact  手动压缩当前对话
  /clear    清空对话（保留 system）
  /exit     退出（等同 Ctrl+D）
其他输入直接发给模型；`!命令` 直接跑 shell 且不打模型；行尾 `\\` 续行。"""


def history_path_for(*, base: Optional[Path] = None, cwd: Optional[str] = None) -> Path:
    """历史按工作目录分文件（官方语义）：不同项目的输入历史不该互相污染。

    base 默认 None 再在函数体里取 HISTORY_BASE，**不能**写成 `base=HISTORY_BASE`——
    默认参数在**函数定义时**求值，之后再改模块常量就追不回来了
    （2026-08-10 被测试隔离的防护测试当场抓到）。
    """
    base = base if base is not None else HISTORY_BASE
    key = hashlib.sha1((cwd or os.getcwd()).encode("utf-8")).hexdigest()[:16]
    return base / key


def _append_history(path: Path, line: str) -> None:
    """连续两次相同的输入只记一条（官方语义：↑ 直接跳到上一个*不同*的提示）。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_text(encoding="utf-8").splitlines()
            if existing and existing[-1] == line:
                return
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass                    # 历史写不进去不该弄挂 REPL


def _is_real_terminal_input(reader: Callable[..., str]) -> bool:
    """只有真人坐在真终端前才挂 readline：注入 reader 的测试路径碰进程级 readline
    状态会让测试互相串，管道里更是没有 ↑/↓ 可言。"""
    return reader is input and sys.stdin.isatty()


def _read_history_into_readline(history: Path) -> None:
    """把我们自己写的历史文件喂给 readline，↑/↓ 与 Ctrl+R 才有东西可翻。

    只在真实交互路径调用：注入 reader 的测试路径碰进程级 readline 状态会让测试互相串。
    macOS 系统 Python 的 readline 是 libedit 后端，历史文件格式与 GNU readline 略有差异，
    读失败按「没有历史」处理，不该因此弄挂 REPL。
    """
    try:
        import readline
    except ImportError:
        return                      # Windows 等无 readline 的平台：↑/↓ 退化，其余照常
    try:
        readline.read_history_file(str(history))
    except OSError:
        pass                        # 文件不存在或格式不认，都当作没有历史


def _read_line(reader: Callable[..., str]) -> str:
    r"""`\` + Enter 是唯一在所有终端都可用的多行方式（其余靠终端 key protocol，属 TUI）。"""
    line = reader(PROMPT)
    while line.endswith("\\"):
        line = line[:-1] + "\n" + reader(CONTINUATION_PROMPT)
    return line


def _make_asker(reader: Callable[..., str], out: Callable[[str], None], state: dict):
    """真人问答通道。

    asker 与 REPL 主循环**共用同一个 reader**——模型一提问，它就去读下一行 stdin，
    而用户此刻敲的可能是 `/exit` 或别的命令。不处理的话那行会被静默当成答案交给模型
    （2026-08-10 演示时实际发生过：`!echo 我是命令` 被当成了对问题的回答）。
    所以给三条出路：空行跳过、`/exit` 退出、其他 `/命令` 提示后重读。
    """
    def ask_human(question: str, options: List[str]) -> str:
        out(f"❓ {question}")
        for i, option in enumerate(options, 1):
            out(f"  {i}. {option}")
        out("  （输入序号或自己的话；直接回车 = 跳过不答；/exit 退出）")
        while True:
            answer = reader(PROMPT).strip()
            if answer in ("/exit", "/quit"):
                # 不能抛异常：EOFError 会被 Tool.run 的 except Exception 吞成错误字符串，
                # KeyboardInterrupt 又会一路掀出 run_interactive。用标志让主循环收尾。
                state["exit"] = True
                return "用户选择退出，本次提问未作答。"
            if not answer:
                return "用户跳过了这个问题（没有作答），请自行判断或换个方式推进。"
            if answer.startswith("/"):
                out("  （提问期间不支持 / 命令；请作答、直接回车跳过，或 /exit 退出）")
                continue
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1]
            return answer        # 用户想说别的就让他说，别把真人锁进选项里
    return ask_human


def make_event_handler(stream=None, *, enabled: Optional[bool] = None
                      ) -> Callable[[AgentEvent], None]:
    """REPL 的默认事件处理器：真 tty 上把工具进度压成一行原地刷新，其余情况退回滚动行。

    两条路径不并存——状态行开着还滚动打一遍 🔧，同一件事会在屏幕上出现两次。
    管道/CI 里绝不能吐 `\r` 与转义符，否则日志变乱码（printer 自己判 isatty）。
    """
    out = stream if stream is not None else sys.stdout
    printer = StatusLinePrinter(stream=out, enabled=enabled)

    def handle(event: AgentEvent) -> None:
        if isinstance(event, (ToolStart, ToolEnd)) and printer.enabled:
            printer.handle(event)
            return
        if isinstance(event, AgentEnd) and printer.enabled:
            printer.clear()
        text = render_text(event)
        if text is not None:
            out.write(text + "\n")
            out.flush()

    return handle


def run_interactive(
    *,
    client=None,
    model: Optional[str] = None,
    tools: Optional[dict] = None,
    reader: Callable[..., str] = input,
    out: Callable[[str], None] = print,
    on_event: Optional[Callable[[AgentEvent], None]] = None,
    max_steps: int = 20,
    max_total_tokens: Optional[int] = None,
    no_session: bool = False,
    context_window: Optional[int] = None,
    compaction: Optional[CompactionSettings] = None,
    history_path: Optional[Path] = None,
    rules: Optional[RuleSet] = None,
    mode: Optional[str] = None,
) -> None:
    on_event = on_event if on_event is not None else make_event_handler()
    client = client or make_client()
    model = model or model_name()
    # ask_user_question 不在默认工具集里（once 没真人可问），交互模式显式加回来
    tools = tools if tools is not None else get_tools(
        list(get_tools()) + ["ask_user_question"])
    session = None if no_session else SessionLog()
    context_window = context_window if context_window is not None else default_context_window()
    compaction = compaction if compaction is not None else CompactionSettings()
    history = history_path if history_path is not None else history_path_for()

    messages: List[dict] = []
    anchors = AnchorBook()
    state = CompactionState()
    follow_up = PendingMessageQueue("single")
    flag = InterruptFlag()
    set_current(flag)                      # bash 工具从这里看见中断
    asker_state = {"exit": False}
    human_asker = _make_asker(reader, out, asker_state)
    ask.set_asker(human_asker)
    # 权限（feature 07）。REPL 有真人，所以 ask 走真人通道而不是降级为 deny（拍板问 1）。
    rules = rules if rules is not None else load_rules(warn=out)
    hooks = load_hooks(warn=out)
    tools = visible_tools(tools, rules)            # 裸名 deny 的工具压根不摆给模型
    gate = make_before_tool_call(
        rules, hooks=hooks, tools=tools, asker=human_asker, warn=out, mode=mode)
    memory_tool.set_memory_dir(memory_dir())
    memory_tool.set_notifier(
        lambda topic, path: on_event(MemoryWritten(topic=topic, path=str(path))))

    if _is_real_terminal_input(reader):
        _read_history_into_readline(history)

    out("pai 交互模式。/help 看命令，Ctrl+D 退出。")
    pending_exit = False
    while True:
        try:
            line = _read_line(reader)
        except EOFError:
            break
        except KeyboardInterrupt:
            # 空闲时的两级 Ctrl+C（官方语义）：第一次清输入，第二次退出
            if pending_exit:
                break
            pending_exit = True
            out("(输入已清空，再按一次 Ctrl+C 退出)")
            continue
        pending_exit = False

        line = line.strip()
        if not line:
            continue

        if line.startswith("/"):
            if _handle_command(line, out=out, messages=messages, anchors=anchors,
                               state=state, tools=tools, client=client, model=model,
                               compaction=compaction, context_window=context_window,
                               rules=rules, hooks=hooks):
                break
            continue

        _append_history(history, line)

        if line.startswith("!"):
            # 也要进可中断作用域：Ctrl+C 打断 `!sleep 300` 时让 bash 看见标志、
            # 自己杀掉进程组并回填结果，而不是抛 KeyboardInterrupt 掀掉整个 REPL
            with _interruptible(flag):
                try:
                    _run_shell(line[1:].strip(), messages=messages,
                               session=session, out=out)
                except KeyboardInterrupt:
                    # 信号可能落在装处理器之前/之后的缝隙里（或非主线程装不上），
                    # 这是最后一道：宁可少收一条输出，也不能让 REPL 死掉
                    out("⛔ 已中断")
            continue

        _run_turn(line, client=client, model=model, tools=tools, messages=messages,
                  anchors=anchors, state=state, follow_up=follow_up, flag=flag,
                  session=session, on_event=on_event, out=out, max_steps=max_steps,
                  max_total_tokens=max_total_tokens, context_window=context_window,
                  compaction=compaction, before_tool_call=gate)

        if asker_state["exit"]:      # 用户在模型提问时选了 /exit——本轮收尾后再退
            break

    out("再见。")


@contextlib.contextmanager
def _interruptible(flag: InterruptFlag):
    """在这个作用域里，Ctrl+C 只置标志不抛异常——执行侧（loop / bash 轮询）自己找地方收尾。

    模型轮次与 `!命令` **两条路径都必须进来**：`!` 分支曾经漏在外面，
    于是 Ctrl+C 打断 `!sleep 300` 会把整个 REPL 带栈掀掉（同 401 炸会话那一类）。
    """
    flag.clear()
    previous = _install_sigint(flag)
    try:
        yield
    finally:
        _restore_sigint(previous)


def _run_turn(task: str, *, client, model, tools, messages, anchors, state, follow_up,
              flag, session, on_event, out, max_steps, max_total_tokens,
              context_window, compaction, before_tool_call=None) -> None:
    with _interruptible(flag):
        answer = _guarded_run(
            out,
            task, client=client, model=model, tools=tools, messages=messages,
            anchors=anchors, compaction_state=state, interrupt_flag=flag,
            session=session, on_event=on_event, max_steps=max_steps,
            max_total_tokens=max_total_tokens, context_window=context_window,
            compaction=compaction,
            before_tool_call=before_tool_call,
            # steering 在纯 REPL 无输入源（阻塞的 input 拿不到「干活时打字」），
            # 只接 followUp；注入点已在 loop 里备好，等 TUI/流式通电
            instructions=build_context,
            get_follow_up_messages=follow_up.drain,
        )
    if answer is not None:
        out(f"🤖 {answer}")


def _guarded_run(out: Callable[[str], None], *args, **kwargs):
    """401 / 超时 / 限流不该把整个会话带栈掀掉——once 崩了无所谓（本就跑完即退），
    REPL 崩了等于把上下文一起丢掉（冒烟实测撞到过）。返回 None 表示这轮没有答案。"""
    try:
        return run_agent(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - REPL 的价值就是「对话留着」
        out(f"❌ 请求失败：{type(e).__name__}: {e}\n（对话已保留，可以直接重试或换个说法）")
        return None


def _install_sigint(flag: InterruptFlag):
    """干活期间 Ctrl+C 只置标志：抛 KeyboardInterrupt 会把已完成的工作连同栈一起丢掉，
    而官方对中断的承诺恰恰是「保留迄今完成的工作」。"""
    try:
        return signal.signal(signal.SIGINT, lambda *_: flag.set())
    except ValueError:
        return None              # 不在主线程（如某些测试宿主）时装不上，退化为不可中断


def _restore_sigint(previous) -> None:
    if previous is not None:
        try:
            signal.signal(signal.SIGINT, previous)
        except ValueError:
            pass


def _run_shell(command: str, *, messages: List[dict], session, out) -> None:
    """`!命令`：不经模型直接跑，命令与输出都进上下文。

    官方 v2.1.186 起会在输出进上下文后**自动接话**，pai 默认不接——每次 `!` 都自动接话
    等于每次都花一次请求钱（官方自己也给了 respondToBashCommands 开关）。
    """
    if not command:
        out("用法：!<命令>")
        return
    bash: Tool = get_tools(["bash"])["bash"]
    output = bash.run(command=command)
    out(output)
    entry = {"role": "user", "content": f"我执行了命令 `{command}`，输出：\n{output}"}
    if not messages:
        messages.append({"role": "system", "content": _system_prompt()})
        if session:
            session.append(messages[0])
    messages.append(entry)
    if session:
        session.append(entry)


def _system_prompt() -> str:
    from pai.core.loop import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _handle_command(line: str, *, out, messages, anchors, state, tools, client, model,
                    compaction, context_window, rules=None, hooks=()) -> bool:
    """返回 True 表示要退出 REPL。"""
    command = line.split()[0]
    if command in ("/exit", "/quit"):
        return True
    if command == "/help":
        out(HELP)
    elif command == "/clear":
        del messages[1:]         # 保留 system；整段清掉会让下一轮重建，等价但更难解释
        anchors.reset()
        state.failures, state.awaiting_verify, state.tripped = 0, False, False
        out("🧹 已清空对话（保留 system）")
    elif command == "/status":
        anchor, anchor_index = anchors.latest()
        schemas = [t.schema() for t in tools.values()]
        estimated = context_tokens(messages, schemas, anchor=anchor, anchor_index=anchor_index)
        breaker = "已熔断" if state.tripped else f"正常（失败 {state.failures} 次）"
        out(f"📊 消息 {len(messages)} 条 | 估算 {estimated} token / 窗口 {context_window}"
            f" | 锚点 {len(anchors.entries)} 个 | 压缩：{breaker}")
    elif command == "/memory":
        _show_memory(out)
    elif command == "/permissions":
        _show_permissions(out, rules, hooks)
    elif command == "/compact":
        _manual_compact(messages=messages, anchors=anchors, state=state,
                        client=client, model=model, compaction=compaction, out=out)
    else:
        out(f"未知命令 {command}，/help 看可用命令")
    return False


def _show_permissions(out: Callable[[str], None], rules, hooks=()) -> None:
    """列出规则与来源。「被哪条规则挡的、那条从哪来」是用户能自己修的前提。"""
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
        return
    out("🔒 权限规则（求值顺序 deny → ask → allow，第一个匹配决定）：")
    for line in lines:
        out(line)
    out(f"  没有规则命中时按默认决策 `{rules.default_decision}`")
    _show_hooks(out, hooks)


def _show_hooks(out: Callable[[str], None], hooks) -> None:
    if not hooks:
        return
    out("🪝 PreToolUse hook（退出码 2 = 阻断，崩溃/超时不阻断）：")
    for spec in hooks:
        out(f"  {spec.matcher:8} {spec.command}   （超时 {spec.timeout}s）")


def _show_memory(out: Callable[[str], None]) -> None:
    """官方 /memory 的最小版。它首先是个调试工具：指令没生效时，
    第一步永远是确认文件到底有没有被加载——所以列的是路径与行数，不是内容。"""
    files = discover()
    if not files:
        out(f"📄 没有加载任何指令文件（找的是 {PROJECT_FILE} / {LOCAL_FILE}，"
            f"从当前目录向上逐级，外加 ~/{USER_DIR}/{PROJECT_FILE}）")
    else:
        out("📄 已加载的指令文件（按加载顺序，后面的更靠近对话）：")
        for path in files:
            try:
                lines = len(path.read_text(encoding="utf-8").splitlines())
            except OSError:
                lines = 0
            out(f"  {path}（{lines} 行）")
    directory = memory_dir()
    index = directory / MEMORY_INDEX
    state = "有索引" if index.is_file() else "还没有内容"
    out(f"🧠 自动记忆目录：{directory}（{state}）")
    # 会话也要列：这次需求的起点就是用户翻到那些文件、不知道它们是什么、在哪（feature 08）
    out(f"💾 会话记录目录：{sessions_dir()}")


def _manual_compact(*, messages, anchors, state, client, model, compaction, out) -> None:
    cut = find_cut_point(messages, anchors.entries,
                         keep_recent_tokens=compaction.keep_recent_tokens)
    if cut <= 1:
        if len(anchors.entries) < 2:
            out("🗜️ 锚点不足（<2）：真实切点要靠相邻锚的差值反推，先聊两轮再压。")
        else:
            out("⚠️ 无可压：保留预算已吞下全部历史（或只剩一个超长轮次）。")
        return
    before = len(messages)
    messages[:], summary, usage = compact(messages, cut=cut, client=client, model=model)
    anchors.reset()                        # 历史被改写，旧锚全部作废（D#18/32）
    state.awaiting_verify = True           # 成败仍只认压缩后首次真实 usage（D#34）
    out(f"🗜️ 已压缩：切于 {cut}，消息 {before} → {len(messages)} 条，"
        f"摘要 {len(summary)} 字，摘要请求用了 {usage.get('total_tokens') or 0} token")
