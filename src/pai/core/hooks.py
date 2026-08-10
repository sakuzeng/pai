"""外部命令 hook：把权限判定开放给仓库自己的脚本（feature 07 拍板问 3）。

**会自举**：pai 自己的 `guards/design_gate.py` 就是这样一个 hook，所以这里的
stdin 事件格式与 stdout 决策格式都照着它来——做完之后 pai 能跑自己的门禁。

三种退出码（官方协议）：
- `0`   ：解析 stdout 的 JSON，`permissionDecision` ∈ allow / ask / deny
- `2`   ：**阻断**，stderr 原样作为给模型的理由
- 其他 ：非阻断错误，只告警继续

**铁律：hook 自身超时或崩溃绝不阻断工作。** 门禁挂掉的代价是「这道门禁没生效」，
不是「agent 干不了活」——`design_gate.py` 结尾那个 `except: sys.exit(0)` 是同一条。
这条铁律有安全代价（杀掉 hook 进程就能绕过它），但反过来做的代价更大：
一个写错的钩子会让整个 agent 罢工，而那种情况下人往往直接把钩子全关了。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Callable, Optional, Sequence

from pai.core import paths, permissions
from pai.core.permissions import KINDS, Decision, RuleSet

DEFAULT_TIMEOUT = 5.0
BLOCK_EXIT_CODE = 2


@dataclass(frozen=True)
class HookSpec:
    """一条 PreToolUse hook 配置。`matcher` 是工具名 glob，`*` 表示全都管。"""

    command: str
    matcher: str = "*"
    timeout: float = DEFAULT_TIMEOUT

    def applies_to(self, tool_name: str) -> bool:
        return fnmatchcase(tool_name, self.matcher)


def _strictest(*decisions: Optional[Decision]) -> Optional[Decision]:
    """取最严的一个：deny > ask > allow。

    这既是「多个 hook 冲突时怎么办」的答案，也是两条边界的实现——
    hook 的 allow 压不过规则的 deny，规则的 allow 也压不过 hook 的阻断。
    一个函数同时兑现三件事，是因为它们本来就是同一条性质。
    """
    real = [d for d in decisions if d is not None]
    if not real:
        return None
    return min(real, key=lambda d: KINDS.index(d.kind) if d.kind in KINDS else len(KINDS))


def _parse_stdout(stdout: str) -> Optional[Decision]:
    """退出码 0 时读 stdout 的 JSON 决策。没有决策就是「没意见」，不是「放行」。"""
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None                     # 不是 JSON 就当没意见，别拿脏输出当决策
    if not isinstance(data, dict):
        return None
    # design_gate.py 用的是嵌套形式，顶层形式也认——两种都是官方文档里出现过的
    block = data.get("hookSpecificOutput")
    payload = block if isinstance(block, dict) else data
    kind = payload.get("permissionDecision")
    if kind not in KINDS:
        return None
    return Decision(kind=kind, reason=payload.get("permissionDecisionReason") or "")


def _run_one(
    spec: HookSpec, event: dict, warn: Optional[Callable[[str], None]]
) -> Optional[Decision]:
    try:
        proc = subprocess.run(
            spec.command,
            shell=True,
            input=json.dumps(event, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=spec.timeout,
        )
    except subprocess.TimeoutExpired:
        if warn:
            warn(f"hook 超时（{spec.timeout}s），按非阻断处理：{spec.command}")
        return None
    except OSError as e:               # 起不来（命令不存在、没权限）同样不阻断
        if warn:
            warn(f"hook 起不来（{e}），按非阻断处理：{spec.command}")
        return None

    if proc.returncode == 0:
        return _parse_stdout(proc.stdout)
    if proc.returncode == BLOCK_EXIT_CODE:
        reason = (proc.stderr or "").strip() or f"被 hook 阻断：{spec.command}"
        return Decision(kind="deny", reason=reason)
    if warn:
        warn(
            f"hook 退出码 {proc.returncode}（非阻断错误），继续：{spec.command}"
            + (f"\n{proc.stderr.strip()}" if proc.stderr else "")
        )
    return None


def run_pre_tool_use(
    hooks: Sequence[HookSpec],
    tool_name: str,
    args: dict,
    cwd: Optional[str] = None,
    warn: Optional[Callable[[str], None]] = None,
) -> Optional[Decision]:
    """按顺序跑所有匹配的 hook，返回最严的决策；没有任何决策则返回 None（无意见）。

    **返回 None 不等于 allow**：调用方要把「没意见」与「明确放行」分开，
    否则一个崩掉的 hook 就变成了一次放行。
    """
    event = {"tool_name": tool_name, "tool_input": args, "cwd": cwd or ""}
    verdicts = [
        _run_one(spec, event, warn) for spec in hooks if spec.applies_to(tool_name)
    ]
    return _strictest(*verdicts)


def decide_with_hooks(
    tool_name: str,
    args: dict,
    rules: RuleSet,
    hooks: Sequence[HookSpec] = (),
    tools: Optional[dict] = None,
    cwd: Optional[str] = None,
    home: Optional[str] = None,
    warn: Optional[Callable[[str], None]] = None,
    working_dirs=None,
    mode=None,
) -> Decision:
    """规则判定 + hook 判定，取最严的那个。`before_tool_call` 就装配自这里。"""
    base = permissions.decide(tool_name, args, rules, tools=tools, cwd=cwd, home=home,
                              working_dirs=working_dirs, mode=mode)
    hooked = run_pre_tool_use(hooks, tool_name, args, cwd=cwd, warn=warn)
    return _strictest(base, hooked) or base


HOOK_EVENT = "PreToolUse"


def load_hooks(
    cwd: Optional[str] = None,
    home: Optional[str] = None,
    warn: Optional[Callable[[str], None]] = None,
) -> list:
    """读两层 `settings.json` 的 `hooks.PreToolUse`，用户层在前、项目层在后。

    顺序其实不影响结果（`_strictest` 取最严的，与先后无关），保持它只是为了
    `/permissions` 那类展示读起来跟设置文件一致。

    坏条目**跳过并告警**，与坏 JSON 同样绝不弄挂 agent——一条写错的 hook
    不该让整个 agent 起不来。
    """
    from pai.core.permissions import SETTINGS_FILE, _read_settings   # 复用同一套读盘与容错

    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    home_path = Path(home) if home is not None else Path.home()
    user_dir = home_path / paths.USER_DIR

    specs = []
    for path in (user_dir / SETTINGS_FILE, cwd_path / paths.USER_DIR / SETTINGS_FILE):
        entries = (_read_settings(path, warn).get("hooks") or {}).get(HOOK_EVENT) or []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("command"):
                if warn:
                    warn(f"跳过无效的 {HOOK_EVENT} hook 条目（需要 command 字段）：{entry!r}（{path}）")
                continue
            specs.append(HookSpec(
                command=str(entry["command"]),
                matcher=str(entry.get("matcher") or "*"),
                timeout=float(entry.get("timeout") or DEFAULT_TIMEOUT),
            ))
    return specs
