"""两层 `settings.json` 的通用读取（用户级 + 项目级）。

自 feature 30 起这里是唯一的读盘 + 坏文件容错实现（`read_settings_layers`）：
feature 13 时记的「等第三个读者出现时再合并」在 mcp 成为第四个读者后兑现，
permissions / hooks / mcp / 本模块的 section 取值全部消费它。
通用信任门禁（`project_trust_gate`）也住这里——信任的对象就是项目级配置。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pai.core import paths

SETTINGS_FILE = "settings.json"


def load_settings(cwd: Optional[str] = None, home: Optional[str] = None,
                  warn: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """读两层并浅合并：后读的项目层覆盖用户层（与权限层的分层顺序一致）。"""
    merged: Dict[str, Any] = {}
    for _path, data in read_settings_layers(cwd=cwd, home=home, warn=warn):
        for section, value in data.items():
            if isinstance(value, dict) and isinstance(merged.get(section), dict):
                merged[section] = {**merged[section], **value}
            else:
                merged[section] = value
    return merged


def alt_screen_enabled(settings: Dict[str, Any],
                       warn: Optional[Callable[[str], None]] = None) -> bool:
    """`tui.altScreen`，默认 **True**。

    默认开的理由记在 features/13 的拍板里：pai 是自用学习项目，没有 CC 那层
    「外部用户」风险；默认不进的话这个功能等于没做（而 bug 会长期没人撞到）。
    非布尔值退回默认并告警——静默按默认走的话，用户会以为自己关掉了。
    """
    return _flag(settings, "altScreen", warn)


def mouse_enabled(settings: Dict[str, Any],
                  warn: Optional[Callable[[str], None]] = None) -> bool:
    """`tui.mouse`，默认 **True**（features/16 拍板）。

    关掉的代价说清楚：滚轮会重新穿透给终端，于是往上滚看到的是终端的 scrollback
    （用户之前几次运行的残留）——这正是 feature 16 存在的理由。
    留这个开关是因为 alt 屏 + 鼠标在个别终端组合下不可用（CC 为 tmux -CC 专门检测，
    pai 不做检测，出问题就靠它退回去）。
    """
    return _flag(settings, "mouse", warn)


def _flag(settings: Dict[str, Any], key: str,
          warn: Optional[Callable[[str], None]]) -> bool:
    value = (settings.get("tui") or {}).get(key, True)
    if isinstance(value, bool):
        return value
    if warn:
        warn(f"settings 里 tui.{key} 应是 true/false，收到 {value!r}，按默认（开）处理")
    return True


def bash_timeout_seconds(settings: Dict[str, Any],
                         warn: Optional[Callable[[str], None]] = None
                         ) -> Optional[int]:
    """`bash.timeoutSeconds`：bash 工具的默认超时（秒），None = 未配置。

    出处 TODO「工具调用超时」P1：CC 走 env var、dsh 走 settings section，
    pai 已有 settings 层，走这里与架构一致。合法域 1..MAX_TIMEOUT_SECONDS
    （600，与模型可传上限同一个数——默认值配得比它还大没有意义）；
    非法值 warn 回默认（fail loud，与 tui 开关、mcp timeout 同一条约定）。
    bool 要单独挡：它是 int 的子类，`true` 会被静默当成 1 秒。
    """
    value = (settings.get("bash") or {}).get("timeoutSeconds")
    if value is None:
        return None
    from pai.core.tools.shell import MAX_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, int) \
            or not 1 <= value <= MAX_TIMEOUT_SECONDS:
        if warn:
            warn(f"settings 里 bash.timeoutSeconds 应是 1..{MAX_TIMEOUT_SECONDS} "
                 f"的整数（秒），收到 {value!r}，按默认处理")
        return None
    return value


def additional_directories(settings: Dict[str, Any],
                           warn: Optional[Callable[[str], None]] = None
                           ) -> tuple:
    """`permissions.additionalDirectories`：工作目录边界的额外允许根。

    feature 33（H9）接线：这个键在 boundary 的 docstring 与 STATUS 里声称
    存在，实际从没接进装配——配了静默不生效，比没有更糟。`~` 展开；
    非列表 / 非字符串条目 warn 后忽略（fail-loud 约定）。
    """
    value = (settings.get("permissions") or {}).get("additionalDirectories")
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        if warn:
            warn(f"settings 里 permissions.additionalDirectories 应是字符串列表，"
                 f"收到 {value!r}，已忽略")
        return ()
    import os
    return tuple(os.path.expanduser(v) for v in value)


def _read(path: Path, warn: Optional[Callable[[str], None]]) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        if warn:
            warn(f"设置文件 {path} 不是合法 JSON（{e}），本层按空处理")
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------- 分层读取原语（feature 30）

def read_settings_layers(cwd=None, home=None, warn=None):
    """两层 settings.json 的原始内容：((用户层路径, dict), (项目层路径, dict))。

    这是仓库里唯一的「读 settings 文件 + 坏文件容错」实现（feature 30，问 1·A）：
    此前 permissions / hooks / mcp / 本模块各有一套，settings 读取者到第四个时
    合并阈值（本文件头注记的「等第三个读者」）已翻倍越过。section 解析刻意留在
    各消费方——权限的 RuleSet 组装、hooks 解析、mcpServers 校验都是各自的领域
    知识，这里只管读盘与告警一份实现。
    """
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    home_path = Path(home) if home is not None else Path.home()
    user_path = home_path / paths.USER_DIR / SETTINGS_FILE
    project_path = cwd_path / paths.USER_DIR / SETTINGS_FILE
    return ((user_path, _read(user_path, warn)),
            (project_path, _read(project_path, warn)))


# ---------------------------------------------------------------- 通用信任门禁（feature 30）

def project_trusted(marker: str, cwd=None, home=None) -> bool:
    """项目级配置的信任标记是否存在。标记住项目身份目录（~/.pai/projects/<slug>/），
    不进仓库——检入仓库的配置能声明任何东西，但塞不进信任标记（feature 28 拍板）。"""
    return (paths.project_dir(cwd, home) / marker).is_file()


def mark_project_trusted(marker: str, cwd=None, home=None) -> None:
    directory = paths.project_dir(cwd, home)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / marker).write_text("trusted\n", encoding="utf-8")


def project_trust_gate(items, *, marker: str, cwd=None, home=None,
                       ask=None, warn,
                       question, trust_option: str, refuse_option: str,
                       refused_note, unattended_note):
    """项目级条目的通用信任门禁（feature 30 问 2·A：skills 与 mcp 的三胞胎合一）。

    机制一份：已信任放行；有真人（ask）问一次、精确选中信任项才持久化标记、
    其余回答按拒绝且不持久化（下次再问）；无真人（once）丢弃项目级 + 提示。
    文案全部由适配方传入（question 收 (数量, 名单) 返回问题原文），两侧输出
    逐字不变——refactor 判据。条目须带 `source`（"user"|"project"）与 `name`。
    """
    project = [it for it in items if it.source == "project"]
    if not project or project_trusted(marker, cwd, home):
        return list(items)
    names = "、".join(it.name for it in project)
    if ask is not None:
        answer = ask(question(len(project), names), [trust_option, refuse_option])
        if answer == trust_option:
            mark_project_trusted(marker, cwd, home)
            return list(items)
        warn(refused_note(names))
        return [it for it in items if it.source != "project"]
    warn(unattended_note(names))
    return [it for it in items if it.source != "project"]
