"""权限层：规则解析与 allow / ask / deny 三态求值（feature 07 阶段 4）。

**求值顺序是本模块唯一不许动的东西**：deny → ask → allow，桶内按书写顺序取第一个命中，
特异性不参与排序。看起来「更特异的规则应该赢」很合理，但那会让
`deny=["Bash(aws *)"] + allow=["Bash(aws s3 ls)"]` 变成放行——
一个不会报错、不会变红、只在被人利用时才现形的洞。
`test_deny_beats_more_specific_allow` 就是钉这一条的。

没有任何规则命中时走 `default_decision`（默认 `allow`）：与压缩、事件、记忆三次接线
一致的先例——不配置就等于没接过线。这有安全代价，是 spec 里如实标注的自主判断，
想要白名单模式的人把它配成 `ask` / `deny`。
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from pai.core import paths
from pai.core.boundary import WorkingDirs, is_dangerous_write
from pai.core.tools import READ, WRITE, MatchContext, all_tools, default_matcher

SETTINGS_FILE = "settings.json"

# 三态。顺序即求值顺序，别按字母排。
KINDS = ("deny", "ask", "allow")

# `default_decision` 的第四种取值（feature 09，**新默认**）：
# 兜底不是常量而是**一个函数**——读 → 界内 allow / 界外 ask；写 → 一律 ask；
# 不参与边界的工具（bash）→ ask。照 CC（`filesystem.ts` 第 6 步与第 12 步），
# 那边根本没有「默认决策常量」这个东西。
# 配成 "allow" 可退回 feature 07 的老行为（向后兼容）。
WORKING_DIR = "workingdir"
DEFAULT_DECISIONS = KINDS + (WORKING_DIR,)

# 权限模式（feature 09 Task 6，照 CC 的四个对外可用模式；`plan` 与 ant-only 的
# `auto` 不做，见 spec 非目标）。
# **模式不是全局开关，是插在求值链特定位置的放行条件，且都有免疫项**——
# 完整链见 decide() 的注释。
DEFAULT_MODE = "default"
ACCEPT_EDITS = "acceptEdits"          # 工作目录内的写自动放行；仍受边界与危险路径约束
DONT_ASK = "dontAsk"                  # 一切 ask 直接变 deny（不在链上，是 gate 的后处理）
BYPASS = "bypassPermissions"          # 全放行，但 deny/显式 ask/危险路径三条免疫
MODES = (DEFAULT_MODE, ACCEPT_EDITS, DONT_ASK, BYPASS)

# shift+tab 的轮转表（feature 12 T5）。**是数据不是 if 链**——`plan` 单独立项时
# 只需在这里插一行（本档案问 2 的改判要求）。照 CC 的 getNextPermissionMode，
# 但去掉两个：`plan`（本轮不做）与 `dontAsk`（D#53 它与「无真人」合流，
# 不该出现在给真人按的快捷键上；CC 的注释同样写着它「尚未暴露在 UI 环里」）。
MODE_CYCLE = (DEFAULT_MODE, ACCEPT_EDITS, BYPASS)

# 需要额外可用性判定才进环的档。危险档不是白给的：不可用就跳过，不是报错。
_GATED_MODES = {BYPASS: "bypass_available"}


def next_mode(current: str, *, bypass_available: bool = False) -> str:
    """轮转到下一个模式。不在环里的（含未知值）一律回 `default`。"""
    available = {"bypass_available": bypass_available}
    try:
        start = MODE_CYCLE.index(current)
    except ValueError:
        return DEFAULT_MODE
    for step in range(1, len(MODE_CYCLE) + 1):
        candidate = MODE_CYCLE[(start + step) % len(MODE_CYCLE)]
        gate_key = _GATED_MODES.get(candidate)
        if gate_key is None or available[gate_key]:
            return candidate
    return DEFAULT_MODE


class PermissionModeState:
    """**可变**的当前模式。

    存在的理由：`make_before_tool_call(..., mode="default")` 会把值烤进闭包，
    于是 `/mode` 与 shift+tab 运行时改不动（feature 12 T5 动工前撞见）。
    它可调用（`state()` 返回当前模式），gate 因此既能收字符串也能收它。
    """

    def __init__(self, mode: str = DEFAULT_MODE) -> None:
        self.set(mode)

    def __call__(self) -> str:
        return self.mode

    def set(self, mode: str) -> str:
        if mode not in MODES:
            raise ValueError(f"未知权限模式 {mode!r}，只认 {MODES}")
        self.mode = mode
        return self.mode

    def cycle(self, *, bypass_available: bool = False) -> str:
        return self.set(next_mode(self.mode, bypass_available=bypass_available))

# "Bash" / "Bash(git push *)"：工具名后可选一个括号包起来的 specifier。
# specifier 内部允许任意字符（含括号，如 Bash(echo (x))），所以贪婪匹配到最后一个 `)`。
_RULE_RE = re.compile(r"^(?P<tool>[^(]+?)\s*(?:\(\s*(?P<spec>.*?)\s*\))?$", re.S)


@dataclass(frozen=True)
class Rule:
    """一条权限规则。

    `anchor` 是**写下这条规则的设置文件所在目录**，由 `source` 决定
    （user → `~/.pai`，project → 项目根）。路径型 specifier 的单斜杠前缀锚在它上面，
    所以它必须跟着规则走，不能在判定时现推。
    """

    tool: str
    specifier: Optional[str] = None
    source: str = "project"
    anchor: str = ""

    def text(self) -> str:
        return self.tool if self.specifier is None else f"{self.tool}({self.specifier})"

    def matches_tool(self, tool_name: str) -> bool:
        return fnmatch.fnmatchcase(tool_name, self.tool)


@dataclass(frozen=True)
class Decision:
    """三态判定结果。`rule` 为 None 表示没有规则命中、走的默认决策。"""

    kind: str
    reason: str = ""
    rule: Optional[Rule] = None


@dataclass
class RuleSet:
    deny: list[Rule] = field(default_factory=list)
    ask: list[Rule] = field(default_factory=list)
    allow: list[Rule] = field(default_factory=list)
    default_decision: str = WORKING_DIR
    mode: str = DEFAULT_MODE
    # defaultMode 来自哪个设置文件；None = 用户没配（feature 33，09 遗留 2：
    # once 强制 dontAsk 时要能分清「默认」与「用户配了但用不上」，后者得告警）
    mode_source: Optional[str] = None

    def bucket(self, kind: str) -> list[Rule]:
        return getattr(self, kind)

    @classmethod
    def from_lists(
        cls,
        deny: Optional[list[str]] = None,
        ask: Optional[list[str]] = None,
        allow: Optional[list[str]] = None,
        source: str = "project",
        anchor: str = "",
        default_decision: str = WORKING_DIR,
    ) -> "RuleSet":
        """从字符串规则建 RuleSet（测试与单层配置用；跨层合并见 Task 5 的 load_rules）。"""
        if default_decision not in DEFAULT_DECISIONS:
            raise ValueError(
                f"default_decision 只能是 {DEFAULT_DECISIONS} 之一，得到 {default_decision!r}")
        return cls(
            deny=[parse_rule(t, source, anchor) for t in (deny or [])],
            ask=[parse_rule(t, source, anchor) for t in (ask or [])],
            allow=[parse_rule(t, source, anchor) for t in (allow or [])],
            default_decision=default_decision,
        )


def parse_rule(text: str, source: str = "project", anchor: str = "") -> Rule:
    """解析 `"Bash"` / `"Bash(git push *)"`。工具名大小写不敏感，内外空格容错。"""
    m = _RULE_RE.match(text.strip())
    if not m or not m.group("tool").strip():
        raise ValueError(f"规则语法错误：{text!r}（期望 `工具名` 或 `工具名(specifier)`）")

    tool = m.group("tool").strip().lower()
    # 未锚定的 glob（`*_file`）直接拒绝：官方的做法是跳过并告警，但告警会被日志淹没，
    # 而一条以为生效却没生效的 deny 比压根没写更危险——让它在解析期就炸出来。
    if tool.startswith("*") and tool != "*":
        raise ValueError(
            f"规则 {text!r} 的工具名 glob 未锚定：只允许 `*`（全部）或 `前缀*` 形式"
        )

    spec = m.group("spec")
    return Rule(
        tool=tool,
        specifier=spec.strip() if spec is not None else None,
        source=source,
        anchor=anchor,
    )


def _specifier_matches(
    tool_name: str,
    specifier: str,
    args: dict,
    require_all: bool,
    tools: dict,
    ctx: MatchContext,
) -> bool:
    """匹配语义**下放给工具**（拍板问 2）：权限层这里不许出现任何工具名分支。

    工具没注册（或调用方给的 tools 里没有）时退回默认实现——判不出来就按最朴素的
    通配符判，总好过静默放行。
    """
    tool = tools.get(tool_name)
    if tool is None:
        return default_matcher(specifier, args, require_all, ctx)
    return tool.matches(specifier, args, require_all, ctx)


def _first_match(
    kind: str,
    tool_name: str,
    args: dict,
    rules: RuleSet,
    tools: dict,
    cwd: str,
    home: str,
) -> Optional[Rule]:
    # allow 要「每个子命令都匹配」才算命中，deny/ask 是「任一命中」即算。
    # 这个不对称就是权限系统的牙齿：少了它，`ls && rm -rf /` 会被 `Bash(ls *)` 放行。
    require_all = kind == "allow"
    for rule in rules.bucket(kind):
        if not rule.matches_tool(tool_name):
            continue
        # 裸规则（无 specifier）= 该工具的所有调用
        ctx = MatchContext(anchor=rule.anchor or cwd, cwd=cwd, home=home)
        if rule.specifier is None or _specifier_matches(
            tool_name, rule.specifier, args, require_all, tools, ctx
        ):
            return rule
    return None


def _dangerous_write_check(
    tool_name: str, args: dict, tools: dict, home: str
) -> Optional[Decision]:
    """写持久化位点（shell 配置、`.git/hooks`、`~/.ssh`、pai 自己的 settings）一律要确认。

    返回 `None` 表示「不是危险写入，继续往下判」。
    **这条 bypass 免疫**：allow 规则与 `default_decision="allow"` 都翻不过它，
    因为它排在规则命中之后、返回之前。
    """
    tool = tools.get(tool_name)
    if tool is None or tool.access != WRITE or tool.get_path is None:
        return None
    path = tool.get_path(args)
    if not is_dangerous_write(path, home=home):
        return None
    return Decision(
        kind="ask",
        reason=f"`{path}` 是持久化位点（写进去会在 pai 退出后继续生效），必须确认",
    )


def _boundary_fallback(
    tool_name: str, args: dict, tools: dict, working_dirs: WorkingDirs
) -> Decision:
    """`workingdir` 兜底：**这就是 CC 那个「默认不是常量而是函数」**。

    读 → 界内 allow / 界外 ask；写 → 一律 ask（CC 的写路径兜底没有目录放行那一步）；
    **不参与边界的工具（bash）→ ask**——它没声明 `get_path`，边界判定结构上碰不到它，
    所以只能落到最保守的一档。这是拍板问 2「不做 bash 边界」的直接代价。
    """
    tool = tools.get(tool_name)
    if tool is not None and tool.boundary_exempt:
        # 边界豁免（feature 27，D#73）：入参无路径语义、路径由 pai 自算的工具
        # （目前只有 skill）兜底放行。deny / 危险写 / 用户 ask 规则在求值链
        # 前面已查过，走到这里说明都没命中。
        return Decision(kind="allow",
                        reason=f"`{tool_name}` 声明了边界豁免（路径由 pai 自算，入参无路径语义）")
    if tool is None or not tool.participates_in_boundary():
        return Decision(
            kind="ask",
            reason=f"`{tool_name}` 不参与工作目录边界判定（未声明路径语义），按最保守处理",
        )

    path = tool.get_path(args)
    if tool.access == READ:
        if working_dirs.contains(path):
            return Decision(kind="allow", reason="在工作目录内")
        return Decision(
            kind="ask",
            reason=f"`{path}` 在工作目录之外（{working_dirs.startup_cwd}）",
        )
    # 写：界内界外都问。照 CC——写没有「目录放行」那一步。
    return Decision(kind="ask", reason=f"写入 `{path}` 需要确认")


def decide(
    tool_name: str,
    args: dict,
    rules: RuleSet,
    tools: Optional[dict] = None,
    cwd: Optional[str] = None,
    home: Optional[str] = None,
    working_dirs: Optional[WorkingDirs] = None,
    mode: Optional[str] = None,
) -> Decision:
    """按 CC 的求值链判定。**顺序不许改**，每一步的位置都有理由：

    | 步 | 检查 | bypass 免疫？ |
    |---|---|---|
    | 1 | deny 规则 | ✅ |
    | 2 | 危险路径写检查 | ✅ |
    | 3 | **用户显式配的** ask 规则 | ✅ |
    | 4 | `bypassPermissions` → allow | — |
    | 5 | `acceptEdits` 且是写 且在界内 → allow | — |
    | 6 | allow 规则 | — |
    | 7 | 兜底（边界判定 / 未声明路径语义的工具 → ask） | ❌ |

    **第 3 步与第 7 步都产出 `ask`，但待遇不同**：前者是用户写下的规则
    （`Decision.rule` 非 None），bypass 也要问；后者是兜底，bypass 放行。
    混同两者的话 bypass 模式要么等于没有、要么变成万能开关。

    `mode` 不传时取 `rules.mode`（配置文件里的 defaultMode）。
    `dontAsk` 不在本链上——它是 `gate.py` 对最终结果的后处理。
    """
    if tools is None:
        tools = all_tools()
    cwd = cwd if cwd is not None else os.getcwd()
    home = home if home is not None else os.path.expanduser("~")
    mode = mode if mode is not None else rules.mode
    if mode not in MODES:
        raise ValueError(f"未知权限模式 {mode!r}，只认 {MODES}")
    dirs = working_dirs if working_dirs is not None else WorkingDirs.from_startup(cwd)

    def _rule_decision(kind: str, rule: Rule) -> Decision:
        return Decision(
            kind=kind,
            reason=f"命中 {kind} 规则 `{rule.text()}`（来源：{rule.source}）",
            rule=rule,
        )

    # 1. deny 规则——最先，且什么都翻不过它
    rule = _first_match("deny", tool_name, args, rules, tools, cwd, home)
    if rule is not None:
        return _rule_decision("deny", rule)

    # 2. 危险路径写检查（持久化位点）
    blocked = _dangerous_write_check(tool_name, args, tools, home)
    if blocked is not None:
        return blocked

    # 3. 用户**显式配的** ask 规则
    rule = _first_match("ask", tool_name, args, rules, tools, cwd, home)
    if rule is not None:
        return _rule_decision("ask", rule)

    # 4. bypassPermissions：走到这里说明三条免疫都没命中
    if mode == BYPASS:
        return Decision(kind="allow", reason=f"权限模式 `{BYPASS}`")

    # 5. acceptEdits：只免掉「写一律 ask」，**不免边界**（照 CC 的 && isInWorkingDir）
    tool = tools.get(tool_name)
    if mode == ACCEPT_EDITS and tool is not None and tool.access == WRITE \
            and tool.get_path is not None and dirs.contains(tool.get_path(args)):
        return Decision(kind="allow", reason=f"权限模式 `{ACCEPT_EDITS}`（工作目录内）")

    # 6. allow 规则
    rule = _first_match("allow", tool_name, args, rules, tools, cwd, home)
    if rule is not None:
        return _rule_decision("allow", rule)

    # 7. 兜底
    if rules.default_decision == WORKING_DIR:
        return _boundary_fallback(tool_name, args, tools, dirs)
    return Decision(
        kind=rules.default_decision,
        reason=f"没有规则命中，按默认决策 `{rules.default_decision}`",
        rule=None,
    )


# ---- Task 5：配置加载与裸名 deny 摘工具 ----
#
# 读盘与坏文件容错（「坏文件绝不弄挂 agent」的铁律）自 feature 30 起住
# core/settings.read_settings_layers——settings 读取者曾多到四处，合并成一份。


def load_rules(
    cwd: Optional[str] = None,
    home: Optional[str] = None,
    warn: Optional[Callable[[str], None]] = None,
) -> RuleSet:
    """读 `~/.pai/settings.json`（用户）+ `<cwd>/.pai/settings.json`（项目）合成一个 RuleSet。

    **两层的锚点不一样**，这不是笔误：用户级锚在设置文件所在的 `~/.pai`，
    项目级锚在**项目根**（不是 `.pai` 子目录）。所以用户设置里的 `/secrets/**`
    是 `~/.pai/secrets/**`，项目设置里的 `/src/**` 是 `<项目根>/src/**`。

    合并是**追加**不是覆盖：任一层的 deny 都进 deny 桶，而 deny 桶最先求值，
    所以「任一层 deny 都翻不过来」是求值顺序的自然结果，不需要额外逻辑。
    """
    # 读盘走统一原语（feature 30）；本函数只留自己的领域知识——锚点与 RuleSet 组装
    from pai.core.settings import read_settings_layers

    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    home_path = Path(home) if home is not None else Path.home()
    user_dir = home_path / paths.USER_DIR
    (user_path, user_data), (project_path, project_data) = read_settings_layers(
        cwd=cwd_path, home=home_path, warn=warn)

    layers = (
        ("user", user_dir, user_path, user_data),
        ("project", cwd_path, project_path, project_data),
    )

    merged = RuleSet()
    for source, anchor, path, data in layers:
        perms = data.get("permissions") or {}
        for kind in KINDS:
            for text in perms.get(kind) or []:
                try:
                    merged.bucket(kind).append(parse_rule(text, source, str(anchor)))
                except ValueError as e:
                    # 单条规则写错只丢这一条，别连累同一层的其他规则
                    if warn:
                        warn(f"跳过无法解析的规则 {text!r}（{path}）：{e}")
        wanted = perms.get("defaultDecision")
        if wanted in DEFAULT_DECISIONS:
            merged.default_decision = wanted       # 后读的层（项目）覆盖前一层
        wanted_mode = perms.get("defaultMode")
        if wanted_mode is not None:
            if wanted_mode in MODES:
                merged.mode = wanted_mode
                merged.mode_source = str(path)
            elif warn:
                warn(f"未知权限模式 {wanted_mode!r}（{path}），按 `{DEFAULT_MODE}` 处理；"
                     f"可选：{MODES}")
    return merged


def visible_tools(tools: dict, rules: RuleSet) -> dict:
    """把**裸名 deny** 的工具从发给模型的工具集里摘掉。

    带 specifier 的 deny 不摘（保留工具、拦具体调用）——官方明确区分这两种，
    区别是实打实的：`deny=["Bash"]` 该让模型压根不知道有 bash 这回事，
    `deny=["Bash(rm *)"]` 则该让模型照常用 bash、只在 rm 上碰壁。
    """
    hidden = {
        name
        for name in tools
        if any(r.specifier is None and r.matches_tool(name) for r in rules.deny)
    }
    return {n: t for n, t in tools.items() if n not in hidden}
