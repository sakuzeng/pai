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

from pai.core.hooks import HookSpec, decide_with_hooks
from pai.core.permissions import Decision, RuleSet

# (问题, 候选项) -> 用户选的那项。与 pai.core.tools.ask.Asker 同构，故意不 import：
# 权限问答与模型发起的 AskUserQuestion 是两条独立的通道，只是长得一样。
Asker = Callable[[str, List[str]], str]

ALLOW_LABEL = "允许这次"
DENY_LABEL = "拒绝"

NO_HUMAN_REASON = (
    "这条规则要求人工确认，而当前模式无人可问（拍板问 1：降级为拒绝，不是放行）。"
    "换个不需要确认的做法，或让用户在设置里改成 allow。"
)


def _ask_the_human(decision: Decision, tool_name: str, args: dict, asker: Asker) -> Decision:
    detail = ", ".join(f"{k}={v!r}" for k, v in args.items())
    answer = asker(
        f"是否允许 {tool_name}({detail})？\n{decision.reason}",
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
) -> Callable[[str, dict], Decision]:
    """造一个交给 `run_agent(before_tool_call=...)` 的判定函数。

    `asker=None` 表示当前模式没有真人（once）：ask 降级为 deny + 说明。
    降级为 allow 是不行的——自动化正是最危险的场景，那样 ask 规则等于不存在。
    """

    def gate(tool_name: str, args: dict) -> Decision:
        decision = decide_with_hooks(
            tool_name, args, rules, hooks=hooks,
            tools=tools, cwd=cwd, home=home, warn=warn,
        )
        if decision.kind != "ask":
            return decision
        if asker is None:
            return Decision(
                kind="deny",
                reason=f"{decision.reason}；{NO_HUMAN_REASON}",
                rule=decision.rule,
            )
        return _ask_the_human(decision, tool_name, args, asker)

    return gate
