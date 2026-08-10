"""remember：模型自己决定把什么写进自动记忆（官方语义：判断「对未来对话有没有用」）。

文件名叫 memory_tool 而不是 memory，是为了不和 pai.core.memory（读侧）撞名。

写盘位置走**注入点**而不是工具参数，两个理由叠加：@tool 只认标量参数（Path 会在装饰期
报错），而把目录做成 str 参数等于让模型自己挑写哪儿——那比路径穿越还糟。
装配层用 set_memory_dir 注入，与 interrupt/ask 同一套做法（D#40）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable, Optional

from pai.core.memory import MEMORY_INDEX
from pai.core.tools import tool

_DIR: Optional[Path] = None
# 工具不认识事件系统（core.events 是 loop 的词汇表，不该被工具依赖）——
# 装配层注入一个 (topic, path) 回调，由它去发 MemoryWritten 事件。
_NOTIFY: Optional[Callable[[str, Path], None]] = None


def set_memory_dir(directory: Optional[Path]) -> None:
    global _DIR
    _DIR = Path(directory) if directory is not None else None


def set_notifier(fn: Optional[Callable[[str, Path], None]]) -> None:
    global _NOTIFY
    _NOTIFY = fn


def current_memory_dir() -> Optional[Path]:
    return _DIR


def _safe_topic(topic: str) -> Optional[str]:
    """topic 是模型生成的：只放行「单段、不含分隔符、不是 . 或 ..」的名字。

    白名单式判断而不是黑名单过滤 `../`——过滤能被绕（`....//`），
    「必须等于自己的 basename」不能。
    """
    name = (topic or "").strip()
    if not name or name in (".", ".."):
        return None
    if "/" in name or "\\" in name or "\x00" in name:
        return None
    if Path(name).name != name:
        return None
    return name


@tool
def remember(
    topic: Annotated[str, "记忆主题，会成为文件名的一段，如 构建 / 调试 / 约定；不能含路径分隔符"],
    fact: Annotated[str, "要记住的一句话事实，写给未来的自己看"],
) -> str:
    """把这次会话学到的、对未来对话有用的事实写进长期记忆。"""
    if _DIR is None:
        return "错误：当前没有可写的记忆目录（装配层未注入）"
    name = _safe_topic(topic)
    if name is None:
        return f"错误：topic {topic!r} 非法——只能是单段名字，不能含路径分隔符或 .."
    directory = _DIR
    target = directory / f"{name}.md"
    stamp = datetime.now().strftime("%Y-%m-%d")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(f"- {stamp} {fact.strip()}\n")
        _ensure_indexed(directory, name)
    except OSError as e:
        return f"错误：写记忆失败：{e}"
    if _NOTIFY is not None:
        _NOTIFY(name, target)                 # 只有真写成功了才通知
    return f"已记住（{name}）：{fact.strip()}"


def _ensure_indexed(directory: Path, name: str) -> None:
    """索引里每个主题只留一行——MEMORY.md 有 200 行上限，别自己把它撑爆。"""
    index = directory / MEMORY_INDEX
    line = f"- [{name}]({name}.md)"
    existing = ""
    if index.is_file():
        existing = index.read_text(encoding="utf-8")
        if f"{name}.md" in existing:
            return
    header = "" if existing else "# 记忆索引\n\n"
    with index.open("a", encoding="utf-8") as f:
        f.write(f"{header}{line}\n")
