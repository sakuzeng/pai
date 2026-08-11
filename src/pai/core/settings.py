"""两层 `settings.json` 的通用读取（用户级 + 项目级）。

`permissions.py` 有它自己的一份读取——**刻意不改它**（feature 13 plan）：
它工作正常且被 100+ 条测试盯着，为了「不重复」去动它是无谓风险。
两处读同一个文件这件事登记为遗留，等第三个读者出现时再合并。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pai.core import paths

SETTINGS_FILE = "settings.json"


def load_settings(cwd: Optional[str] = None, home: Optional[str] = None,
                  warn: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """读两层并浅合并：**后读的项目层覆盖用户层**（与权限层的分层顺序一致）。"""
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    home_path = Path(home) if home is not None else Path.home()
    merged: Dict[str, Any] = {}
    for path in (home_path / paths.USER_DIR / SETTINGS_FILE,
                 cwd_path / paths.USER_DIR / SETTINGS_FILE):
        for section, value in _read(path, warn).items():
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
