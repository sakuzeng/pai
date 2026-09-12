"""工具调用折成组（feature 50，照 CC 2.1.88）。

CC 的 `utils/collapseReadSearch.ts::collapseReadSearchGroups` 把连续的可折叠工具（read / search /
list / bash / MCP 读搜 / 记忆读写）合成一个 `collapsed_read_search` 组，模型的非空文本
（`isTextBreaker`）与 edit / write（`isNonCollapsibleToolUse`）断组，没有最小组大小；
`components/messages/CollapsedReadSearchContent.tsx` 把组画成一行：跑着时转圈 + 现在时
「Reading 3 files…」+ 一行 `⎿` 当前工具提示，跑完 dim 的过去时「Read 3 files, ran 4 bash
commands (ctrl+o to expand)」；ctrl+o 的 verbose 下组内每条工具各自一行 + 完整结果。

pai 的对应：`ToolGroup` 收 ToolStart / ToolEnd 事件、给出摘要；`group_entry` 把它做成可展开的
transcript 条目。摘要词表按动作（读 / 搜 / 看 / 跑 / 记），与 dock 的 `_ACTIONS` 同源思路——
用户看到的是「做了什么」不是「调了哪个函数」。展开块加暗底（`theme.TOOL_BG`）：CC 的暗底是
光标选中行（`useSelectedMessageBg`），pai 没有光标行，点开就是它的「选中」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pai.core.events import ToolEnd, ToolStart
from pai.modes.statusline import _preview
from pai.tui import theme
from pai.tui.sanitize import sanitize_terminal_text
from pai.tui.transcript import TranscriptEntry, expandable_entry
from pai.tui.width import _truncate

# 工具名 → (动词, 量词)。**顺序就是摘要里的顺序**（照 CC：search、read、list、bash、… 固定序，
# 不按出现顺序——同一轮怎么交错，读出来都是同一句话的形状）。加工具时加一行。
ACTIONS: Dict[str, Tuple[str, str]] = {
    "search_files": ("搜", "次"),
    "read_file": ("读", "个文件"),
    "list_dir": ("看", "个目录"),
    "bash": ("跑", "条命令"),
    "run_tests": ("跑", "次测试"),
    "git_read": ("看", "次 git"),
    "remember": ("记", "条笔记"),
    "skill": ("用", "个 skill"),
}

# 断组的工具（CC `isNonCollapsibleToolUse`：edit / write）：改了什么是用户要看的节点，
# 折进「跑了 5 个工具」里就找不到了；问真人更是。认不得的工具（MCP 等）进组，
# 照 CC 把 MCP 读搜算 "Queried X"。
BREAKERS = frozenset({"write_file", "edit_file", "ask_user_question"})


def is_collapsible(name: str) -> bool:
    return name not in BREAKERS


@dataclass
class ToolCall:
    tool_call_id: str
    name: str
    args: dict
    result: Optional[str] = None       # None = 还没回来
    is_error: bool = False


class ToolGroup:
    """一组连续的可折叠工具调用。`active` 为真时是现在时 + 当前工具提示。"""

    def __init__(self) -> None:
        self.calls: List[ToolCall] = []
        self.active = True
        self.hint = ""                  # 最近一个工具的预览（路径 / 模式 / 命令），照 CC 的 ⎿ 行

    def start(self, event: ToolStart) -> None:
        self.calls.append(ToolCall(event.tool_call_id, event.name, dict(event.args or {})))
        self.hint = _preview(event.args or {}) or ""

    def end(self, event: ToolEnd) -> None:
        call = next((c for c in self.calls if c.tool_call_id == event.tool_call_id), None)
        if call is None:
            # 没见过 ToolStart 的结果：回放（只有 tool 消息）与被权限拦下的调用都走这里
            call = ToolCall(event.tool_call_id, event.name, dict(event.args or {}))
            self.calls.append(call)
            self.hint = _preview(event.args or {}) or ""
        call.result = event.result
        call.is_error = event.is_error

    def close(self) -> None:
        self.active = False
        self.hint = ""

    def summary(self) -> str:
        counts: Dict[str, int] = {}
        for call in self.calls:
            counts[call.name] = counts.get(call.name, 0) + 1
        ordered = [n for n in ACTIONS if n in counts] + [n for n in counts if n not in ACTIONS]
        parts = []
        for name in ordered:
            verb, unit = ACTIONS.get(name, ("调", f"次 {name}"))
            parts.append(f"{verb} {counts[name]} {unit}" if self.active
                         else f"{verb}了 {counts[name]} {unit}")
        text = "，".join(parts)
        return f"正在{text}" if self.active else text


_GUTTER = "  "          # 摘要行的 2 列 gutter（CC 跑完后转圈的位置留空）
_LEAD = "  ⎿ "          # 输出块的引出符（照 CC；非 emoji，宽度 1）
_INDENT = "    "


def _call_head(call: ToolCall, width: int) -> str:
    head = f"{theme.DETAIL} {call.name}"
    args = ", ".join(f"{k}={v!r}" for k, v in call.args.items())
    if args:
        head += f"({_truncate(args, max(8, width // 3))})"
    if call.is_error:
        head += " ✗"
    return _truncate(head, width)


def group_entry(group: ToolGroup, *, color: bool) -> TranscriptEntry:
    """组 → 可展开条目。渲染函数读的是 `group` 的**当前**状态：活轮次里组在变，
    调用方每次更新后要 `entry.invalidate()`（缓存 key 只含宽度与展开态）。"""

    def dim(text: str, width: int) -> str:
        return theme.paint(_truncate(text, width), theme.GREY, color=color)

    def render(width: int, expanded: bool) -> List[str]:
        # 跑着时现在时 + 省略号（CC：`{isActiveGroup && …} <CtrlOToExpand />`——提示两态都带）
        head = f"{_GUTTER}{group.summary()}{'…' if group.active else ''}"
        if not expanded:
            lines = [dim(f"{head} (^O 展开)", width)]
            if group.active and group.hint:
                lines.append(dim(f"{_LEAD}{group.hint}", width))
            return lines
        # 展开 = CC 的 verbose：每条工具一行头 + 完整输出（还没回来的说明一下），整块铺暗底
        out = [dim(f"{head} (^O 收起)", width)]
        room = max(8, width - len(_INDENT))
        for call in group.calls:
            out.append(theme.band(_call_head(call, width), width, theme.TOOL_BG, color=color))
            body = call.result if call.result is not None else "…还没回来"
            for i, line in enumerate(sanitize_terminal_text(body).split("\n")):
                for j, piece in enumerate(theme.wrap(line, room) or [""]):
                    lead = _LEAD if (i == 0 and j == 0) else _INDENT
                    out.append(theme.band(lead + piece, width, theme.TOOL_BG, color=color))
        return out

    return expandable_entry(render)
