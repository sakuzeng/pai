"""resume 回放：恢复的 messages → 回放项（feature 48，纯函数，可离线测）。

照 CC 2.1.88 的 `utils/messages.ts::shouldShowUserMessage`（isMeta 的 user 消息不画）
与 `components/Messages.tsx` 的过滤。pai 的消息没有 isMeta 字段，注入消息靠它们各自的
固定头识别——都是 pai 自己造的：指令头（`loop.INSTRUCTION_HEADER`）、规则与召回块的
`<system-reminder>`、压缩摘要头（`session.SUMMARY_HEADER`）、`!命令` 回显
（`commands.shell_echo`）。所以这个函数住 modes 层：tui 不该认识 loop 与 commands
（AST 守卫），而 modes 本来就 import 它们。

tool 结果按 tool_call_id 配对（并发批的回填顺序由调度器定，不假设紧跟）；
半截回合在读取侧已由 `session.trim_unfinished` 配平，这里不重复判。
"""

from __future__ import annotations

import json
from typing import Dict, List

from pai.core.events import AssistantMessage, ToolEnd
from pai.core.loop import INSTRUCTION_HEADER
from pai.core.session import SUMMARY_HEADER
from pai.modes.commands import split_shell_echo
from pai.tui.history import CompactedMark, HistoryItem, ShellLine, UserLine

# 规则（core/rules.py）与召回（core/recall.py）两处注入块共用的外壳
REMINDER_OPEN = "<system-reminder>"


def history_items(messages: List[dict]) -> List[HistoryItem]:
    results: Dict[str, str] = {}
    for m in messages:
        if m.get("role") == "tool":
            results[str(m.get("tool_call_id"))] = _text(m)

    items: List[HistoryItem] = []
    for m in messages:
        role = m.get("role")
        text = _text(m)
        if role == "user":
            if text.startswith(INSTRUCTION_HEADER) or text.startswith(REMINDER_OPEN):
                continue                                   # CC 的 isMeta：框架注入不画
            if text.startswith(SUMMARY_HEADER):
                items.append(CompactedMark())
                continue
            shell = split_shell_echo(text)
            if shell is not None:
                items.append(ShellLine(command=shell[0], output=shell[1]))
                continue
            if text.strip():
                items.append(UserLine(text))
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            names = tuple(str((c.get("function") or {}).get("name", "")) for c in calls)
            # 空白回答不画：模型在调工具前吐的 "\n\n"（CC filterWhitespaceOnlyAssistantMessages 同款）
            if text.strip():
                items.append(AssistantMessage(text, names))
            for c in calls:
                cid = str(c.get("id"))
                fn = c.get("function") or {}
                items.append(ToolEnd(tool_call_id=cid, name=str(fn.get("name", "")),
                                     args=_parse_args(fn.get("arguments")),
                                     result=results.get(cid, "")))
        # system 不上屏；tool 已在配对里用掉
    return items


def _text(m: dict) -> str:
    content = m.get("content")
    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


def _parse_args(raw: object) -> dict:
    """`arguments` 在线上是 JSON 串；解析不了就原样包住——回放不该因一条坏参数整个失败。
    诚实边界同 `events.ToolEnd`：is_error 一律 False，tool 消息里分不出 loop 造的错。"""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw if isinstance(raw, str) and raw else "{}")
    except ValueError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": raw}
