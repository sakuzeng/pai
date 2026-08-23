"""skill 工具：按名加载一个 skill 的完整说明（feature 25，D#71 工具形态）。

与 memory_tool 同一个注入模式：目录表装配期写、执行期只读（feature 11 已核实
此模式在线程并发下不构成竞争）。追踪器不同——`record` 在执行期写（工具声明
concurrency_safe 会进调度线程池），线程安全由 `LoadedSkills` 内部的锁保证
（25 复核低 2：此前这句注释把追踪器也说成「执行期只读」，不实）。
目录表不在这里扫描——扫描是装配层的事，本模块只消费结果。
"""

from __future__ import annotations

from typing import Annotated, Dict, Optional

from pai.core.skills import LoadedSkills, Skill, read_skill_body, render_skill_block
from pai.core.tools import boundary_exempt_for, capabilities_for, tool

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


# 边界豁免（feature 27，D#73）：入参只有名字、正文路径来自装配层扫描，
# 「读 SKILL.md 这个路径」的建模是三家参照里没有的孤例（CC 的 SkillTool 无
# getPath、dsh 的门是 isModelInvocable）。25 版的 path_access_for + 「未知名回
# cwd」绕法随之删除——那段绕法正是建模不合身的症状；子目录启动/软链正文
# 也不再撞权限话术。deny / 用户 ask 规则照常在前（豁免只影响兜底）。
boundary_exempt_for(skill)
capabilities_for(skill, read_only=True, concurrency_safe=True)
