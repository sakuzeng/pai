"""装配一个 `before_tool_call`：规则 + hook + ask 的解析（feature 07 Task 7）。

为什么单独一个模块而不是塞进 permissions 或 hooks：
- `permissions` 只管规则与三态求值，它**不能** import hooks（hooks 反过来 import 它，会成环）；
- `hooks` 只管子进程协议；
- 「ask 遇到没有真人时怎么办」既不属于规则也不属于子进程，是**装配期**的决定
  （同一套规则在 once 与 REPL 下行为不同，正是拍板问 1 的结论）。

三件事各归各位之后，loop 只认「返回的 Decision 是不是 allow」，
连 ask 这个概念都不认识——模式差异就渗不进 loop。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence

from pai.core.boundary import WorkingDirs
from pai.core.hooks import HookSpec, decide_with_hooks
from pai.core.permissions import DONT_ASK, Decision, RuleSet

# (问题, 候选项) -> 用户选的那项。与 pai.core.tools.ask.Asker 同构，故意不 import：
# 权限问答与模型发起的 AskUserQuestion 是两条独立的通道，只是长得一样。
Asker = Callable[[str, List[str]], str]

ALLOW_LABEL = "允许这次"
DENY_LABEL = "拒绝"

NO_HUMAN_REASON = (
    "这条规则要求人工确认，而当前模式无人可问（拍板问 1：降级为拒绝，不是放行）。"
    "换个不需要确认的做法，或让用户在设置里改成 allow。"
)


# 参数值最多显示这么长。`write_file` 的 content 可能几千字符——整段倒进问题里，
# 用户根本看不到自己在批什么（2026-08-11 用户实测指出）。
MAX_ARG_CHARS = 160


def _describe(tool_name: str, args: dict) -> str:
    """把一次工具调用写成**人能读的问题**，不是 Python 的 repr。

    `repr()` 会把 shell 命令里的引号转义成 `\'`，一条正常的命令看起来像乱码——
    用户要看的是**命令本身**，不是字符串字面量。
    """
    if tool_name == "bash" and "command" in args:
        # 问号收在第一行，命令**独占一行**——问号跟在命令屁股后面会被当成命令的一部分
        return f"是否允许 {tool_name} 执行？\n$ {_clip(str(args['command']))}"
    if not args:
        return f"是否允许 {tool_name}？"
    parts = [f"{k}={_clip(str(v))}" for k, v in args.items()]
    return f"是否允许 {tool_name}（{'，'.join(parts)}）？"


def _clip(text: str) -> str:
    text = text.replace("\n", " ⏎ ")
    return text if len(text) <= MAX_ARG_CHARS else text[:MAX_ARG_CHARS] + "…"


def _ask_the_human(decision: Decision, tool_name: str, args: dict, asker: Asker) -> Decision:
    answer = asker(
        f"{_describe(tool_name, args)}\n{decision.reason}",
        [ALLOW_LABEL, DENY_LABEL],
    )
    if answer == ALLOW_LABEL:
        return Decision(kind="allow", reason=f"用户当场允许（{decision.reason}）",
                        rule=decision.rule)
    return Decision(kind="deny", reason=f"用户当场拒绝（{decision.reason}）", rule=decision.rule)


def make_before_tool_call(
    rules: RuleSet,
    hooks: Sequence[HookSpec] = (),
    tools: Optional[dict] = None,
    cwd: Optional[str] = None,
    home: Optional[str] = None,
    asker: Optional[Asker] = None,
    warn: Optional[Callable[[str], None]] = None,
    working_dirs: Optional[WorkingDirs] = None,
    mode=None,
) -> Callable[[str, dict], Decision]:
    """造一个交给 `run_agent(before_tool_call=...)` 的判定函数。

    `asker=None` 表示当前模式没有真人（once）：ask 降级为 deny + 说明。
    降级为 allow 是不行的——自动化正是最危险的场景，那样 ask 规则等于不存在。

    **`asker is None` 与 `mode == "dontAsk"` 是同一件事**（feature 09 Task 6）：
    D#48 当初把「无真人时降级」当成一个特例实现，其实它就是 CC 的 `dontAsk` 模式。
    这里让两者走同一段代码，once 的默认模式即 `dontAsk`。
    """

    def gate(tool_name: str, args: dict) -> Decision:
        # 模式**每次判定现取**，不能捕获成常量：`/mode` 与 shift+tab 要能当场改
        # （feature 12 T5）。收字符串（once 的老调用路径）也收可调用的
        # PermissionModeState，两者同源，不另开参数。
        current = mode() if callable(mode) else mode
        decision = decide_with_hooks(
            tool_name, args, rules, hooks=hooks,
            tools=tools, cwd=cwd, home=home, warn=warn,
            working_dirs=working_dirs, mode=current,
        )
        if decision.kind != "ask":
            return decision
        # dontAsk 不在求值链上：它是对**最终结果**的后处理。
        # 与「无真人可问」合流——两者对模型是同一件事（拿不到人的确认）。
        # asker 同样**每次判定现取**：TUI 会在装配之后把它换成对话框通道。
        # 烤成常量的后果 2026-08-11 真跑撞过——权限框走老路径调 `input()`，
        # 而 stdin 已在 raw mode，整个程序死住。
        current_asker = asker.get() if hasattr(asker, "get") else asker
        if current_asker is None or current == DONT_ASK:
            return Decision(
                kind="deny",
                reason=f"{decision.reason}；{NO_HUMAN_REASON}",
                rule=decision.rule,
            )
        return _ask_the_human(decision, tool_name, args, current_asker)

    return gate
