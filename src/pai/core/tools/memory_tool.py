"""remember：模型自己决定把什么写进自动记忆（官方语义：判断「对未来对话有没有用」）。

文件名叫 memory_tool 而不是 memory，是为了不和 pai.core.memory（读侧）撞名。

写盘位置走**注入点**而不是工具参数，两个理由叠加：@tool 只认标量参数（Path 会在装饰期
报错），而把目录做成 str 参数等于让模型自己挑写哪儿——那比路径穿越还糟。
装配层用 set_memory_dir 注入，与 interrupt/ask 同一套做法（D#40）。

**feature 10 起改成「一事一文件」**：一次 remember 写一篇带 frontmatter 的记忆
（`name` / `description` / `metadata.type` / `originSessionId` / `modified`），
同名再写是**更新**而不是新建重复的——CC 把这条写入纪律交给提示词，pai 交给工具。
写完重建 `MEMORY.md`：索引是各篇 frontmatter 的**投影**，不是需要打补丁的账本。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable, Optional, Tuple

from pai.core.memory import (
    MEMORY_INDEX,
    parse_frontmatter,
    render_index,
    scan_memories,
)
from pai.core.tools import tool
from pai.core.tools.fs import atomic_write

_DIR: Optional[Path] = None
# 工具不认识事件系统（core.events 是 loop 的词汇表，不该被工具依赖）——
# 装配层注入一个 (topic, path) 回调，由它去发 MemoryWritten 事件。
_NOTIFY: Optional[Callable[[str, Path], None]] = None
# 记忆能回指产生它的那次会话（照 CC 的 originSessionId）。同样是注入点：
# 工具不该反过来依赖 SessionLog。
_SESSION: Optional[str] = None

VALID_TYPES = ("user", "feedback", "project", "reference")   # 四态照 CC
DEFAULT_TYPE = "project"


def set_memory_dir(directory: Optional[Path]) -> None:
    global _DIR
    _DIR = Path(directory) if directory is not None else None


def set_notifier(fn: Optional[Callable[[str, Path], None]]) -> None:
    global _NOTIFY
    _NOTIFY = fn


def set_origin_session(session_id: Optional[str]) -> None:
    global _SESSION
    _SESSION = session_id or None


def current_memory_dir() -> Optional[Path]:
    return _DIR


def _safe_topic(topic: str) -> Optional[str]:
    """name 是模型生成的：只放行「单段、不含分隔符、不是 . 或 ..」的名字。

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


def _one_line(text: str) -> str:
    """description 要落在 frontmatter 的一行里——换行会把格式撑破。"""
    return " ".join((text or "").split())


def _split_existing(text: str) -> Tuple[dict, str]:
    """把已有文件拆成 (frontmatter 字段, 正文)。

    没有 frontmatter 的（06 时代的裸 bullet 文件）整篇算正文——于是下次写到它头上时
    就地补上 frontmatter，旧内容原样留着。这就是「不写迁移脚本」的兑现方式。
    """
    fields = parse_frontmatter(text)
    if not fields:
        return {}, text
    lines = text.splitlines()
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, "\n".join(lines[i + 1:]).lstrip("\n")
    return fields, ""


def _render_frontmatter(name: str, description: str, type_: str,
                        origin: str, modified: str) -> str:
    lines = ["---", f"name: {name}", f"description: {description}",
             "metadata:", f"  type: {type_}"]
    if origin:
        lines.append(f"  originSessionId: {origin}")   # 没有就整条不写，不写空值
    lines.append(f"  modified: {modified}")
    lines.append("---")
    return "\n".join(lines)


def _rebuild_index(directory: Path) -> None:
    """索引 = 各篇 frontmatter 的投影。**不带相对时间**（写进文件会腐坏，见 memory.render_index）。"""
    atomic_write(str(directory / MEMORY_INDEX), render_index(scan_memories(directory)))


@tool
def remember(
    name: Annotated[str, "记忆的名字，会成为文件名（如 构建约定 / 用户偏好）；不能含路径分隔符"],
    description: Annotated[str, "一句话说清这篇记忆讲什么——召回时靠它判断相关性，也会出现在记忆索引里"],
    fact: Annotated[str, "要记住的事实正文，写给未来的自己看"],
    type: Annotated[str, "记忆类型：user（用户是谁）/ feedback（怎么干活的指正）/ project（在做什么）/ reference（外部资源）；更新已有记忆时可留空表示不变"] = "",
) -> str:
    """把这次会话学到的、对未来对话有用的事实写进长期记忆（同名则更新那篇，不新建重复的）。"""
    if _DIR is None:
        return "错误：当前没有可写的记忆目录（装配层未注入）"
    safe = _safe_topic(name)
    if safe is None:
        return f"错误：name {name!r} 非法——只能是单段名字，不能含路径分隔符或 .."
    directory = _DIR
    target = directory / f"{safe}.md"
    modified = datetime.now().isoformat(timespec="seconds")

    try:
        directory.mkdir(parents=True, exist_ok=True)
        old_fields: dict = {}
        body = ""
        if target.is_file():
            old_fields, body = _split_existing(target.read_text(encoding="utf-8"))
        # originSessionId 记的是**产生**这篇记忆的会话，更新时不该被改写
        origin = old_fields.get("originSessionId") or (_SESSION or "")
        # 更新时不传 type 就沿用旧的。`@tool` 的默认值让「没传」与「传了 project」不可区分，
        # 所以默认值是空串——否则一次不带 type 的更新会把 feedback 静默降回 project
        # （2026-08-11 离线冒烟当场撞到）。
        kind = type if type in VALID_TYPES else (old_fields.get("type") or DEFAULT_TYPE)
        head = _render_frontmatter(safe, _one_line(description), kind, origin, modified)
        body = (body.rstrip("\n") + "\n\n" if body.strip() else "")
        atomic_write(str(target), f"{head}\n\n{body}{fact.strip()}\n")
        _rebuild_index(directory)
    except OSError as e:
        return f"错误：写记忆失败：{e}"
    if _NOTIFY is not None:
        _NOTIFY(safe, target)                 # 只有真写成功了才通知
    return f"已记住（{safe}）：{fact.strip()}"
