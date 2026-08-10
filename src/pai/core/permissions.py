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
from pai.core.boundary import WorkingDirs
from pai.core.tools import READ, MatchContext, all_tools, default_matcher

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


def _boundary_fallback(
    tool_name: str, args: dict, tools: dict, working_dirs: WorkingDirs
) -> Decision:
    """`workingdir` 兜底：**这就是 CC 那个「默认不是常量而是函数」**。

    读 → 界内 allow / 界外 ask；写 → 一律 ask（CC 的写路径兜底没有目录放行那一步）；
    **不参与边界的工具（bash）→ ask**——它没声明 `get_path`，边界判定结构上碰不到它，
    所以只能落到最保守的一档。这是拍板问 2「不做 bash 边界」的直接代价。
    """
    tool = tools.get(tool_name)
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
) -> Decision:
    """按 deny → ask → allow 求值，第一个匹配决定。顺序不许改，理由见模块 docstring。

    `tools` / `cwd` / `home` / `working_dirs` 都可注入（离线可测、白盒断言用）。
    """
    if tools is None:
        tools = all_tools()
    cwd = cwd if cwd is not None else os.getcwd()
    home = home if home is not None else os.path.expanduser("~")
    for kind in KINDS:
        rule = _first_match(kind, tool_name, args, rules, tools, cwd, home)
        if rule is not None:
            return Decision(
                kind=kind,
                reason=f"命中 {kind} 规则 `{rule.text()}`（来源：{rule.source}）",
                rule=rule,
            )
    if rules.default_decision == WORKING_DIR:
        dirs = working_dirs if working_dirs is not None else WorkingDirs.from_startup(cwd)
        return _boundary_fallback(tool_name, args, tools, dirs)
    return Decision(
        kind=rules.default_decision,
        reason=f"没有规则命中，按默认决策 `{rules.default_decision}`",
        rule=None,
    )


# ---- Task 5：配置加载与裸名 deny 摘工具 ----


def _read_settings(path: Path, warn: Optional[Callable[[str], None]]) -> dict:
    """读一层设置。**坏文件绝不弄挂 agent**：告警 + 当作空规则集。

    这条与 hook 的「自身异常不阻断工作」是同一条铁律：权限配置写错了，
    代价应该是「这层规则没生效」，不是「pai 起不来」。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}                       # 没有这个文件是常态，不是错误
    try:
        data = json.loads(text)
    except ValueError as e:
        if warn:
            warn(f"权限设置 {path} 不是合法 JSON（{e}），本层规则按空处理")
        return {}
    return data if isinstance(data, dict) else {}


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
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    home_path = Path(home) if home is not None else Path.home()
    user_dir = home_path / paths.USER_DIR

    layers = (
        ("user", user_dir, user_dir / SETTINGS_FILE),
        ("project", cwd_path, cwd_path / paths.USER_DIR / SETTINGS_FILE),
    )

    merged = RuleSet()
    for source, anchor, path in layers:
        perms = _read_settings(path, warn).get("permissions") or {}
        for kind in KINDS:
            for text in perms.get(kind) or []:
                try:
                    merged.bucket(kind).append(parse_rule(text, source, str(anchor)))
                except ValueError as e:
                    # 单条规则写错只丢这一条，别连累同一层的其他规则
                    if warn:
                        warn(f"跳过无法解析的规则 {text!r}（{path}）：{e}")
        wanted = perms.get("defaultDecision")
        if wanted in KINDS:
            merged.default_decision = wanted       # 后读的层（项目）覆盖前一层
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
