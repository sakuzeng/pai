"""skill 工具：按名加载一个 skill 的完整说明（feature 25，D#71 工具形态）。

与 memory_tool 同一个注入模式：目录表与已加载追踪器都是装配期写、执行期只读
（feature 11 已核实此模式在线程并发下不构成竞争）。目录表不在这里扫描——
扫描是装配层的事，本模块只消费结果。
"""

from __future__ import annotations

import os
from typing import Annotated, Dict, Optional

from pai.core.skills import LoadedSkills, Skill, read_skill_body, render_skill_block
from pai.core.tools import READ, capabilities_for, path_access_for, tool

_CATALOG: Optional[Dict[str, Skill]] = None
_TRACKER: Optional[LoadedSkills] = None


def set_catalog(catalog: Optional[Dict[str, Skill]]) -> None:
    global _CATALOG
    _CATALOG = catalog


def set_tracker(tracker: Optional[LoadedSkills]) -> None:
    global _TRACKER
    _TRACKER = tracker


def get_catalog() -> Dict[str, Skill]:
    """当前目录表（含 disable-model-invocation 的——用户通道 /skill 要能看到它们）。"""
    return dict(_CATALOG) if _CATALOG else {}


def get_tracker() -> Optional[LoadedSkills]:
    return _TRACKER


@tool
def skill(name: Annotated[str, "要加载的 skill 名字，必须来自 available_skills 目录"]) -> str:
    """按名加载一个 skill 的完整说明。当任务与目录里某条 description 匹配时先调它再动手。"""
    if _CATALOG is None:
        return "错误：本会话没有配置任何 skill（skills 目录为空或未装配）。"
    entry = _CATALOG.get(name)
    if entry is None or not entry.model_invocable:
        # 「不存在」与「被 disable-model-invocation 隐藏」刻意说同一句话（dsh 语义）：
        # 分开说就是把被隐藏者的存在泄露给模型
        available = "、".join(sorted(n for n, s in _CATALOG.items() if s.model_invocable))
        return (f"错误：未知或不可用的 skill：{name}。"
                f"可用的有：{available or '（无）'}")
    try:
        body = read_skill_body(entry)
    except (OSError, UnicodeDecodeError) as e:
        return f"错误：skill `{name}` 读取失败（{type(e).__name__}: {e}）"
    if _TRACKER is not None:
        _TRACKER.record(name)
    return render_skill_block(entry, body)


@path_access_for(skill, READ)
def _skill_path(args: dict) -> str:
    """边界判定用的路径：已知名 → SKILL.md 真路径；未知名 → cwd。

    未知名返回 cwd 是刻意的：让边界放行、由工具自己报「未知 skill」——
    否则幻觉名字会撞出一段权限话术（R4#10 同款教训：错误要指向真因）。
    """
    entry = (_CATALOG or {}).get(str(args.get("name", "")))
    return str(entry.path) if entry is not None else os.getcwd()


capabilities_for(skill, read_only=True, concurrency_safe=True)
