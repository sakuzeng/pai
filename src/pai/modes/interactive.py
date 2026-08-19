r"""交互模式：纯 REPL（对应 pi 的 interactive 模式，TUI 是阶段 2 后半程）。

与 once 一样，这层只做「接线 + 输入层」，业务在 core。三样东西是 REPL 独有的：

1. **跨轮持有状态**：messages / 锚点簿 / 熔断状态都在这里，每轮传给 run_agent。
   不这么做的话每轮第一次请求都退回纯字符估算（-33% 误差），熔断器也每轮清零。
2. **输入层**：历史（按工作目录分文件、连续重复只记一条）、`\` 续行、`!` shell 模式、
   `/` 命令——四条语义全部照官方 interactive-mode 章节
   （K knowledge/tui/claude-interactive-mode.md），做不到的（Shift+Enter、补全、
   转录查看器）在那篇笔记里逐条记了为什么。
3. **中断**：干活期间 SIGINT 只置标志不抛异常，loop 与 bash 各自在自己的检查点响应；
   空闲期间恢复默认处理器，于是 input() 照常抛 KeyboardInterrupt，走「两级 Ctrl+C」。

诚实边界：**纯 REPL 这条路上排队队列恒空**——input() 是阻塞的，agent 干活时
用户根本没法打字。真实输入源在 TUI 那条路上（`_run_tui` 的 `on_event` 里
每个事件顺手 `driver.poll(timeout=0)` 一次），feature 18 接的就是它。
"""

from __future__ import annotations

import contextlib
import hashlib
import time
import os
import signal
import sys
from pathlib import Path
from typing import Callable, List, Optional

from pai.config import context_window as default_context_window
from pai.config import make_client, model_name, recall_model
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
    Compacted,
    ConversationCleared,
    MemoryWritten,
    RecallFailed,
    RecallInjected,
    ToolEnd,
    ToolStart,
    render_text,
)
from pai.core.interrupt import InterruptFlag, set_current
from pai.core.gate import make_before_tool_call
from pai.core.hooks import load_hooks
from pai.core.loop import run_agent
from pai.core.permissions import (
    DEFAULT_MODE,
    MODE_CYCLE,
    MODES,
    PermissionModeState,
    RuleSet,
    load_rules,
    visible_tools,
)
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
from pai.core.recall import RecallState, make_recall
from pai.core.session import SessionLog
from pai.core.trace import EventTrace, compose
from pai.core.settings import alt_screen_enabled, load_settings, mouse_enabled
from pai.core.tools import Tool, ask, get_tools, memory_tool
from pai.modes.echo import make_stream_echo
from pai.modes.statusline import StatusLinePrinter
from pai.tui.app import (
    COMMAND, CYCLE_MODE, EOF, EXPAND, INTERRUPT, REDRAW, SUBMIT, TuiApp,
)
from pai.tui.dialog import CANCELLED, Dialog
from pai.tui.keys import KeyDecoder
from pai.tui.driver import TuiDriver
from pai.tui.sanitize import sanitize_terminal_text
from pai.tui.record import Recorder, RecordedStream, record_path
from pai.tui.altscreen import AltScreenRenderer
from pai.tui.renderer import DockRenderer
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript
from pai.tui.terminal import TerminalSession, tui_available
from pai.tui import theme

PROMPT = "› "
CONTINUATION_PROMPT = "… "
HISTORY_BASE = Path.home() / ".pai" / "history"

HELP = """可用命令：
  /help     这张表
  /status   上下文估算、锚点数、压缩熔断状态
  /memory   本次加载了哪些指令文件 + 自动记忆目录在哪
  /mode     查看/切换权限模式（TUI 里也可按 shift+tab 轮转）
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


def _use_tui(reader: Callable[..., str]) -> bool:
    """进不进 TUI。三个条件缺一不可：

    - 没注入 reader（注入了说明是测试或脚本在驱动，别抢它的 stdin）
    - stdin 是 tty（要 raw mode）
    - stdout 是 tty（要画得出来）——**这条判的是 stdout，与 CC 同口径**

    任何一条不成立就退回今天的 REPL：管道、CI、`pai | cat` 的行为一个字不变。
    """
    return (reader is input and sys.stdin.isatty() and tui_available())


def _read_line(reader: Callable[..., str]) -> str:
    r"""`\` + Enter 是唯一在所有终端都可用的多行方式（其余靠终端 key protocol，属 TUI）。"""
    line = reader(PROMPT)
    while line.endswith("\\"):
        line = line[:-1] + "\n" + reader(CONTINUATION_PROMPT)
    return line


class AskerRef:
    """**可变**的真人问答通道。

    存在的理由与 `PermissionModeState` 一模一样：`make_before_tool_call(..., asker=fn)`
    会把函数烤进闭包，于是 TUI 起来之后换不掉——2026-08-11 真跑时权限框因此走了
    REPL 的老 asker 去调 `input()`，而 stdin 已在 raw mode，**整个程序死住**。

    `get()` 返回 None 表示「现在没有真人」，与 `dontAsk` 合流（D#48/D#53）——
    这个包装不能把那条降级路径遮住。
    """

    def __init__(self, fn=None) -> None:
        self._fn = fn

    def get(self):
        return self._fn

    def set(self, fn) -> None:
        self._fn = fn

    def __call__(self, question: str, options: List[str]) -> str:
        if self._fn is None:
            raise RuntimeError("没有可问的真人")
        return self._fn(question, options)


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

    def rest(event: AgentEvent) -> None:
        """状态行优先接管工具事件，其余回落到按行渲染。"""
        if isinstance(event, (ToolStart, ToolEnd)) and printer.enabled:
            printer.handle(event)
            return
        text = render_text(event)
        if text is not None:
            out.write(text + "\n")
            out.flush()

    echo = make_stream_echo(out, fallback=rest)

    def handle(event: AgentEvent) -> None:
        # 状态行要在**结尾语打出来之前**擦掉，否则 `\r` 那行会留在屏幕上
        if isinstance(event, AgentEnd) and printer.enabled:
            printer.clear()
        echo(event)

    return handle


NO_ANSWER = "用户没有作答（跳过或取消），请自行判断或换个方式推进。"


def await_dialog_answer(driver, app, dialog, on_action) -> str:
    """等**这一框**被答掉，然后把结论取出来。

    判据落在框上，不在 `arbiter.current()` 上：后者在「队列空（答完了）」与
    「非空但被打字压住（还没轮到显示）」两种语义完全不同的状态下都是 None。
    拿它当完成判据就是 R4#2——用户正打字时弹的权限框一次都没显示就被判
    「未作答」（对 gate 而言即拒绝）。抑制期本函数照常读键盘：键进编辑器
    （正确），停手 1.5s 后框自然显示，不需要为抑制写任何特判。

    中断 / EOF 要**连框一起撤**（R4#3）：只置一个「不等了」的标志会把框留在
    队列里接管全部按键，用户事后答掉它，结论就流向了下一个问题。
    """
    def handle(kind, payload) -> None:
        on_action(kind, payload)
        if kind in (INTERRUPT, EOF):
            app.cancel_dialog(dialog)

    driver.pump_until(lambda: dialog.resolved, handle)
    answer = dialog.answer
    return NO_ANSWER if answer is None else answer


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
    # 必须在 model 被兜底成主模型**之前**算：否则注入的 model 永远非空，
    # PAI_RECALL_MODEL 就成了一条永远走不到的分支
    recall_model_name = model or recall_model()
    model = model or model_name()
    # ask_user_question 不在默认工具集里（once 没真人可问），交互模式显式加回来
    tools = tools if tools is not None else get_tools(
        list(get_tools()) + ["ask_user_question"])
    session = None if no_session else SessionLog()
    # 观测流落盘（feature 17）。**只在这里包一次**:session 整个 REPL 生命周期只建一次,
    # 下游三处 run_agent 调用共用同一个 on_event；`/clear` 只截断 messages 不换会话,
    # 所以不存在「换了会话事件还写旧文件」的问题(动工前专门核对过,plan 里认账的
    # 那条返工风险没有兑现)。
    # **一个 trace 对象两条路共用**:纯 REPL 走下面的 compose,TUI 自建 on_event
    # (走 app.on_event),所以必须把它单独递进去——否则日常用法(真 tty)整个不落盘。
    trace = EventTrace(session) if session is not None else None
    if trace is not None:
        on_event = compose(on_event, trace)
    context_window = context_window if context_window is not None else default_context_window()
    compaction = compaction if compaction is not None else CompactionSettings()
    history = history_path if history_path is not None else history_path_for()

    messages: List[dict] = []
    anchors = AnchorBook()
    state = CompactionState()
    # 一条队列装两种东西：要发给模型的话，与 `/`、`!` 这类要交给客户端执行的命令。
    # "all" 是问 3 拍板的注入模式（照 CC：两个 drain 点都是批量、每条各自一条消息）。
    steering = PendingMessageQueue("all")
    flag = InterruptFlag()
    set_current(flag)                      # bash 工具从这里看见中断
    asker_state = {"exit": False}
    # 装配期只放一个**可变持有者**：TUI 起来后要把它换成对话框通道。
    asker_ref = AskerRef(_make_asker(reader, out, asker_state))
    ask.set_asker(asker_ref)
    # 权限（feature 07）。REPL 有真人，所以 ask 走真人通道而不是降级为 deny（拍板问 1）。
    rules = rules if rules is not None else load_rules(warn=out)
    hooks = load_hooks(warn=out)
    tools = visible_tools(tools, rules)            # 裸名 deny 的工具压根不摆给模型
    # 模式必须是**可变持有者**：传字符串会被烤进 gate 的闭包，`/mode` 与 shift+tab
    # 就永远改不动了（feature 12 T5 动工前撞见的结构问题）。
    mode_state = PermissionModeState(mode or DEFAULT_MODE)
    gate = make_before_tool_call(
        rules, hooks=hooks, tools=tools, asker=asker_ref, warn=out, mode=mode_state)
    directory = memory_dir()
    memory_tool.set_memory_dir(directory)
    memory_tool.set_notifier(
        lambda topic, path: on_event(MemoryWritten(topic=topic, path=str(path))))
    memory_tool.set_origin_session(session.session_id if session is not None else None)
    # 召回状态**跨轮持有**（同 anchors / state）：REPL 每轮调一次 run_agent，
    # 状态不由这一层拿着，去重与失败熔断都会每轮清零。
    recall = make_recall(client=client, model=recall_model_name,
                         directory=directory, state=RecallState(),
                         on_failure=lambda f: on_event(RecallFailed(
                             reason=f.reason, detail=f.detail, disabled=f.disabled)),
                         on_selected=lambda names: on_event(RecallInjected(names=names)))

    common = dict(
        client=client, model=model, tools=tools, messages=messages, anchors=anchors,
        state=state, steering=steering, flag=flag, session=session,
        max_steps=max_steps, max_total_tokens=max_total_tokens,
        context_window=context_window, compaction=compaction, gate=gate,
        recall=recall, rules=rules, hooks=hooks, mode_state=mode_state,
        history=history, asker_state=asker_state, asker_ref=asker_ref, trace=trace,
    )
    if _use_tui(reader):
        _run_tui(out=out, **common)
        return

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
                               rules=rules, hooks=hooks, mode_state=mode_state,
                               on_event=on_event):
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

        try:
            _run_turn(line, client=client, model=model, tools=tools, messages=messages,
                      anchors=anchors, state=state, steering=steering, flag=flag,
                      session=session, on_event=on_event, out=out, max_steps=max_steps,
                      max_total_tokens=max_total_tokens, context_window=context_window,
                      compaction=compaction, before_tool_call=gate, recall=recall)
        except (EOFError, KeyboardInterrupt):
            raise                       # Ctrl+D / Ctrl+C 是正常控制流，不吞
        except Exception as e:          # noqa: BLE001 - REPL 这一层的价值就是「对话留着」
            # 06 遗留「同类问题第三次」：401 炸会话、Ctrl+C 打断 `!命令` 炸会话，
            # 两次都是「某条路径漏了保护」。兜在这里，让「哪条路径漏了」不再需要逐条排查。
            out(f"❌ 本轮出错：{type(e).__name__}: {e}\n（对话已保留，可以直接重试）")

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


def _run_turn(task: str, *, client, model, tools, messages, anchors, state, steering,
              flag, session, on_event, out, max_steps, max_total_tokens,
              context_window, compaction, before_tool_call=None, recall=None,
              on_queue_change: Optional[Callable[[int], None]] = None) -> None:
    with _interruptible(flag):
        answer = _guarded_run(
            out,
            task, client=client, model=model, tools=tools, messages=messages,
            anchors=anchors, compaction_state=state, interrupt_flag=flag,
            session=session, on_event=on_event, max_steps=max_steps,
            max_total_tokens=max_total_tokens, context_window=context_window,
            compaction=compaction,
            before_tool_call=before_tool_call,
            recall=recall,
            instructions=build_context,
            # 谓词把 `/`、`!` 滤掉且留在队列里——它们是给客户端执行的，
            # 当文本发给模型是 CC 明文禁止的那件事（feature 18 问 5/7）。
            # 纯 REPL 路径队列恒空（阻塞的 input 拿不到「干活时打字」），
            # 传进去也只是空转；真实输入源在 TUI 那条路上。
            get_steering_messages=_steering_source(steering, after_drain=on_queue_change),
        )
    # 不在这里打答案：流式已经逐字打过了（feature 11）。
    # 非 final 的结尾语（预算/步数/中断）由 modes.echo 按 AgentEnd.reason 负责打。


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
    # 给终端看的那一份要消毒（外来字节会打乱 dock 的相对定位、`\t` 全链算 1 列）；
    # **下面进 messages 的仍是原文**——命令真打印了什么，模型就该看见什么。
    out(sanitize_terminal_text(output))
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
                    compaction, context_window, rules=None, hooks=(),
                    mode_state=None, on_event=None) -> bool:
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
        # 观测流里必须留痕（feature 17）：清空前后是两段互不记得的对话，
        # 不发这个事件的话时间线会把它们画成连贯的一段
        if on_event is not None:
            on_event(ConversationCleared(kept=len(messages)))
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
    elif command == "/mode":
        _handle_mode(line, out=out, mode_state=mode_state)
    elif command == "/permissions":
        _show_permissions(out, rules, hooks, mode_state=mode_state)
    elif command == "/compact":
        _manual_compact(messages=messages, anchors=anchors, state=state,
                        client=client, model=model, compaction=compaction, out=out,
                        on_event=on_event)
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


def _manual_compact(*, messages, anchors, state, client, model, compaction, out,
                    on_event=None) -> None:
    cut = find_cut_point(messages, anchors.entries,
                         keep_recent_tokens=compaction.keep_recent_tokens)
    if cut <= 1:
        if len(anchors.entries) < 2:
            out("🗜️ 锚点不足（<2）：真实切点要靠相邻锚的差值反推，先聊两轮再压。")
        else:
            out("⚠️ 无可压：保留预算已吞下全部历史（或只剩一个超长轮次）。")
        return
    before = len(messages)
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
    # 与自动压缩发同一个事件:上下文被换掉这件事,不该因为「是人手动按的」就在观测流里消失
    if on_event is not None:
        on_event(Compacted(cut=cut, before=before, after=len(messages)))
    out(f"🗜️ 已压缩：切于 {cut}，消息 {before} → {len(messages)} 条，"
        f"摘要 {len(summary)} 字，摘要请求用了 {usage.get('total_tokens') or 0} token")


# ---------------------------------------------------------------------------
# TUI 主循环（feature 12）。非 tty / 注入 reader 时走不到这里——上面那条闸门挡着。
# ---------------------------------------------------------------------------

def _run_tui(*, out, client, model, tools, messages, anchors, state, steering, flag,
             session, max_steps, max_total_tokens, context_window, compaction, gate,
             recall, rules, hooks, mode_state, history, asker_state, asker_ref,
             trace=None) -> None:
    """scrollback 在上、dock 在下。

    与纯 REPL 的**唯一**语义差别在输入层：谁拥有键盘由 `InputArbiter` 算出来，
    而不是「谁先 read() 谁拿到」。跨轮状态、命令、shell 模式、压缩、召回全部照旧。
    """
    color = theme.use_color(is_tty=sys.stdout.isatty())
    # 录制默认关闭（feature 14）。开启后只是把写终端的字节 tee 一份，行为不变——
    # 有了它 AI 才看得见界面，不必每次让用户截图。
    path = record_path()
    recorder = Recorder(path, size=lambda: (term.columns, term.rows)) if path else None
    write = recorder.wrap(_stdout_write) if recorder else _stdout_write
    # 备用屏默认开（features/13 拍板），`.pai/settings.json` 的 `tui.altScreen` 可关。
    # 关掉就完全走 12 交付的 main-screen dock 那条路，一个 alt 序列都不发。
    _settings = load_settings(warn=out)
    alt = alt_screen_enabled(_settings, warn=out)
    use_mouse = mouse_enabled(_settings, warn=out)
    transcript, scroll = Transcript(), ScrollState()
    selection = Selection()
    if alt:
        renderer = AltScreenRenderer(write=write, width=lambda: term.columns,
                                     height=lambda: term.rows,
                                     transcript=transcript, scroll=scroll,
                                     selection=selection)
    else:
        renderer = DockRenderer(write=write, width=lambda: term.columns)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll,
                 selection=selection, history=_history_lines(history), color=color)
    app.editor.color = color
    def _on_resize() -> None:
        # 终端在 resize 时会自己挪动备用屏的内容（实测），所以不能只重画——
        # 要先把「上一帧屏幕上有什么」的记忆作废，逼出一次全量重绘。
        if hasattr(app.renderer, "invalidate"):
            app.renderer.invalidate()
        app.refresh()

    # 终端生命周期的写也走同一个 write：不然录制里会缺 `?1049h` 这类关键字节
    term = TerminalSession(on_resize=_on_resize, alt_screen=alt, mouse=use_mouse,
                           stream=RecordedStream(write))
    driver = TuiDriver(app)
    app.dock.set_mode(mode_state())
    app.dock.set_cwd(os.getcwd())
    app.dock.set_model(model)

    def refresh_context() -> None:
        """上下文占用：pai 早就在算（压缩用的就是它），只是此前没给人看。"""
        anchor, anchor_index = anchors.latest()
        used = context_tokens(messages, [t.schema() for t in tools.values()],
                              anchor=anchor, anchor_index=anchor_index)
        app.dock.set_context(used, context_window)

    refresh_context()

    def commit(text: str) -> None:
        app.commit(str(text))          # 拆换行与折行都在 app.commit 里做

    def ask_human(question: str, options: List[str]) -> str:
        """真人问答：排一个对话框，然后**继续读键盘**直到它被答掉。

        提问期间敲的 `!命令` / `/命令` 会经 handoff 交回这里执行——
        这正是 08 遗留那条铁证（`!echo 我是命令` 被当成答案）的修法。
        """
        # 权限框与提问框长得不一样（记号与配色都不同）。判据是选项——
        # `gate._ask_the_human` 固定传「允许这次 / 拒绝」。
        kind = "permission" if options and options[0].startswith("允许") else "question"
        dialog = Dialog(question=question, options=options, kind=kind, color=color)
        app.enqueue_dialog(dialog)

        def on_action(kind, payload):
            if kind == COMMAND:
                _dispatch_command(payload, commit=commit, out=commit, messages=messages,
                                  anchors=anchors, state=state, tools=tools,
                                  client=client, model=model, compaction=compaction,
                                  context_window=context_window, rules=rules,
                                  hooks=hooks, mode_state=mode_state, session=session,
                                  flag=flag, app=app, on_event=on_event)
            elif kind == INTERRUPT:
                flag.set()
            elif kind == EOF:
                asker_state["exit"] = True

        # 撤框与「等到有结论为止」都在 await_dialog_answer 里（那里可离线测）
        return await_dialog_answer(driver, app, dialog, on_action)

    # **一处换、两处生效**：`ask_user_question` 与权限 gate 用的是同一个持有者。
    # 只换其中一个正是 2026-08-11 那次卡死的根因。
    asker_ref.set(ask_human)

    def on_event(event) -> None:
        app.on_event(event)
        if trace is not None:
            trace(event)          # 观测流(feature 17):TUI 这条路不经过外层 compose
        # 干活期间也读键盘：字符本来就在内核 tty 缓冲区里等着（反向对照实测），
        # 只是纯 REPL 从不去读。这里每个事件顺手取一次。
        for kind, payload in driver.poll(timeout=0):
            if kind == SUBMIT:
                # feature 18 问 1（改 12 的拍板问 4）：干活时打的字**本轮就注入**，
                # 不再等本轮结束——照 CC 的默认值「人说话默认优先，机器说话默认等着」。
                # `/`、`!` 也走这里进队列（`app.py:407` 的 `not self.busy` 让它们成为
                # SUBMIT），注入时被谓词滤掉、本轮结束后交给客户端执行。
                steering.enqueue({"role": "user", "content": payload})
                app.dock.set_queued(_queue_size(steering))
            elif kind == INTERRUPT:
                flag.set()

    term.start()
    # **不能用 out（print）**：终端此刻在 raw mode，`\n` 不回列首，会打成阶梯状。
    for warning in term.warnings:
        commit(f"⚠️ {warning}")
    try:
        # 开场：logo 流光扫一遍再定格进 scrollback（动画只改配色，几何不动）
        app.start_intro()
        while app.intro_tick():
            time.sleep(0.04)
        app.commit([theme.paint(
            "/help 看命令 · shift+tab 切权限模式 · ^O 展开工具输出 · Ctrl+D 退出",
            theme.GREY, color=color)])
        app.refresh()
        pending_exit = False
        while True:
            actions = driver.poll()
            for kind, payload in actions:
                if kind == EOF:
                    return
                if kind == INTERRUPT:
                    if pending_exit:
                        return
                    pending_exit = True
                    commit("(输入已清空，再按一次 Ctrl+C 退出)")
                    continue
                pending_exit = False
                if kind == REDRAW:
                    app.refresh()
                elif kind == EXPAND:
                    app.expand_last()
                elif kind == CYCLE_MODE:
                    mode_state.cycle(bypass_available=True)
                    app.dock.set_mode(mode_state())
                    commit(theme.paint(f"[权限] 模式 → {mode_state()}", theme.YELLOW, color=color))
                elif kind == COMMAND:
                    if _dispatch_command(payload, commit=commit, out=commit,
                                         messages=messages, anchors=anchors,
                                         state=state, tools=tools, client=client,
                                         model=model, compaction=compaction,
                                         context_window=context_window, rules=rules,
                                         hooks=hooks, mode_state=mode_state,
                                         session=session, flag=flag, app=app,
                                         on_event=on_event):
                        return
                elif kind == SUBMIT:
                    _append_history(history, payload)
                    app.busy = True

                    def turn(task: str) -> None:
                        _run_turn(task, client=client, model=model, tools=tools,
                                  messages=messages, anchors=anchors, state=state,
                                  steering=steering, flag=flag, session=session,
                                  on_event=on_event, out=commit, max_steps=max_steps,
                                  max_total_tokens=max_total_tokens,
                                  context_window=context_window, compaction=compaction,
                                  before_tool_call=gate, recall=recall,
                                  # 补 2：本轮内 drain 掉多少，dock 的待决数就跟着减多少
                                  on_queue_change=app.dock.set_queued)

                    def queued_command(line: str) -> bool:
                        """返回真 = 该退出（`/exit`）；`_process_queue_after_turn` 据此停手。"""
                        if _dispatch_command(
                                line, commit=commit, out=commit, messages=messages,
                                anchors=anchors, state=state, tools=tools, client=client,
                                model=model, compaction=compaction,
                                context_window=context_window, rules=rules, hooks=hooks,
                                mode_state=mode_state, session=session, flag=flag,
                                app=app, on_event=on_event):
                            exiting["v"] = True
                        return exiting["v"]

                    exiting = {"v": False}
                    try:
                        turn(payload)
                        # 本轮结束后队列里可能还剩两种东西：被谓词滤下的 `/`、`!` 命令，
                        # 以及**最后一次 drain 之后**才敲进来的普通消息
                        # （`AgentEnd` 事件也会触发一次 poll）。followUp 删掉之后
                        # 没人兜它们了，这里就是 CC `useQueueProcessor` 那一档。
                        _process_queue_after_turn(steering, run_turn=turn,
                                                  dispatch=queued_command)
                    except (EOFError, KeyboardInterrupt):
                        raise
                    except Exception as e:      # noqa: BLE001 - 对话留着
                        commit(f"❌ 本轮出错：{type(e).__name__}: {e}（对话已保留）")
                    finally:
                        app.busy = False
                        app.dock.set_queued(_queue_size(steering))
                        refresh_context()
                        app.refresh()
                    if asker_state["exit"] or exiting["v"]:
                        return          # 排队的 `/exit` 与提问里退出走同一条收尾路径
    finally:
        term.stop()
        # `term.stop()` 之后才打——`?1049l` 之前写的东西留在备用屏上，跟着屏幕一起没了。
        # 形态对齐 CC 的 `printResumeHint()`（它也是先退 alt 再打）。
        # **不提示 `--resume`**：pai 还没有这个入口，提示不存在的命令比不提示更糟
        # （已登记 TODO，紧接着单独立项）。
        if session is not None:
            out(f"会话已存 {session.path}")
        app.renderer.clear()
        if recorder is not None:
            recorder.close()
        out("再见。")


def _dispatch_command(line: str, *, commit, app, session, flag, on_event, **kw) -> bool:
    """`/命令` 与 `!命令`。返回 True 表示要退出。"""
    if line.startswith("!"):
        with _interruptible(flag):
            try:
                _run_shell(line[1:].strip(), messages=kw["messages"],
                           session=session, out=commit)
            except KeyboardInterrupt:
                commit("⛔ 已中断")
        app.refresh()
        return False
    return _handle_command(line, out=commit, messages=kw["messages"],
                           anchors=kw["anchors"], state=kw["state"], tools=kw["tools"],
                           client=kw["client"], model=kw["model"],
                           compaction=kw["compaction"],
                           context_window=kw["context_window"], rules=kw["rules"],
                           hooks=kw["hooks"], mode_state=kw["mode_state"],
                           on_event=on_event)


MAX_QUEUE_ROUNDS = 8
"""本轮结束后最多处理几件排队的东西。

不是怕代码写错，是怕**真跑时用户一直在打字**：每起一轮新的又会 poll 到新输入，
理论上可以一直转下去。撞到上界就把剩下的留在队列里——下一轮结束时还会再处理一次，
消息不丢，只是晚一点。
"""


def _steering_source(queue, *, after_drain: Optional[Callable[[int], None]] = None):
    """注入侧的取数回调：滤掉命令 + **取完立刻报剩余量**。

    第二件事是补 2 那个缺陷的修法：`set_queued` 原本只在「干活期间 enqueue 时」
    与「本轮结束的 finally」被调用，而 `run_agent` 在本轮内 drain 掉队列之后
    没有任何人更新——界面会一直显示 drain 前的旧数字直到轮末。

    **为什么不挂在 `SteeringInjected` 事件上**：那条路只在 TUI 的 on_event 闭包里够得着，
    单测碰不到（只能靠 e2e），而这里是个纯工厂，剩余量能被直接断言。
    两者分工不同：事件负责**上屏可见**（transcript 与观测流），这里负责**计数准确**。
    """
    def take() -> List[dict]:
        drained = queue.drain(where=_for_model)
        if after_drain is not None:
            # 一条都没取走时也要报：否则 enqueue 之后那个数字就停在旧值了
            after_drain(_queue_size(queue))
        return drained
    return take


def _process_queue_after_turn(queue, *, run_turn: Callable[[str], None],
                              dispatch: Callable[[str], bool],
                              max_rounds: int = MAX_QUEUE_ROUNDS) -> int:
    """本轮结束后清空队列，返回处理了几件。

    对应 CC 的 `useQueueProcessor`（turn 之间那一档）。两种东西两种去处：
    **命令交客户端执行**（绝不能当文本发给模型），**消息起新一轮**。

    为什么这个函数必须存在：followUp 队列删掉之后，「最后一次 drain 之后才敲进来的字」
    没人兜了——`AgentEnd` 事件同样会触发一次 `driver.poll`，窗口小但真实存在。

    **与 CC 的一处偏离**：CC 把同 mode 的消息批量塞进一个新 query，
    pai 这里是一条消息一轮。因为 `run_agent(task)` 的 `task` 同时喂给
    `AgentStart` 与 `recall()`——把 N 条拼成一个字符串会把这两处一起弄脏。
    这条路上本来也只剩零星残余（两个注入出口已经批量取过了）。

    `dispatch` 返回真 = 该退出 REPL（`/exit`），**立即停手**，剩下的留在队列里
    由调用方收尾——用户说了退出，不该再起一轮新对话。
    """
    rounds = 0
    while rounds < max_rounds:
        item = queue.take_first()
        if item is None:
            break
        text = str(item.get("content") or "")
        rounds += 1
        if _for_model(item):
            run_turn(text)
        elif dispatch(text):
            break
    return rounds


def _for_model(message: dict) -> bool:
    """这条排队消息该发给模型吗？`/`、`!` 开头的不是——它们是给**客户端**执行的。

    CC 明文（`query.ts` mid-turn drain 处）：slash 命令 *must go through
    processSlashCommand after the turn ends, **not be sent to the model as text***。
    pai 的 `!` 同理（CC 那边 bash 模式命令也被排除在中途注入之外，只是滤在更下游）。

    **`lstrip()` 不能省**：用户敲空格再敲 `/` 是常事，按裸 `startswith` 判就漏了，
    那条命令会当文本发给模型——本函数是这条硬约束的唯一守门人。
    """
    return not str(message.get("content") or "").lstrip().startswith(("/", "!"))


def _queue_size(queue) -> int:
    """队列没有暴露长度（05 的 API 只有 enqueue/has_items/drain），这里只读内部表。

    不给 PendingMessageQueue 加公开方法：它是 05 交付的东西，
    「只加不改语义」的范围里，为一个显示需求改它的公开面不划算。
    """
    return len(queue._messages)


def _stdout_write(data: str) -> None:
    sys.stdout.write(data)
    sys.stdout.flush()


def _history_lines(path: Path) -> List[str]:
    """把 05 已交付的历史文件喂给编辑器的 ↑/↓（readline 没了，得自己读）。"""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
