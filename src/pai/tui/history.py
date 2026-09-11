"""resume 回放的条目形状（feature 48）。

照 CC 2.1.88：恢复的对话与活轮次走同一个渲染器（`screens/REPL.tsx` 把 `initialMessages`
直接当 `messages` 状态喂给同一个 `<Messages>`），所以这里**不另起一套渲染**——只定义
「回放项」的类型与两个活轮次也要用的条目工厂，渲染在 `TuiApp.replay` 里复用活轮次的函数。

类型住 tui 层而不是 modes 层，是因为 app 要认识它们，而 tui → modes 的反向依赖被
AST 守卫禁止（tests/test_docs_consistency.py）。消息怎么分类成回放项是 modes 的知识
（指令头、`!命令` 回显格式都是 loop/commands 造的），见 `modes/resume.py::history_items`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from pai.core.events import AssistantMessage, ToolEnd
from pai.tui import theme
from pai.tui.transcript import TranscriptEntry, dynamic_entry


@dataclass(frozen=True)
class UserLine:
    """真人说过的一句话（框架注入的 user 消息不算，见 modes/resume.py）。"""

    text: str


@dataclass(frozen=True)
class ShellLine:
    """`!命令` 及其输出（CC：UserBashInputMessage + UserBashOutputMessage）。"""

    command: str
    output: str


@dataclass(frozen=True)
class CompactedMark:
    """早前对话在这里被压缩成了摘要（CC：CompactBoundaryMessage）。摘要正文不画——
    CC 主屏也不画，只在 transcript 模式里给看。"""


HistoryItem = Union[UserLine, ShellLine, CompactedMark, AssistantMessage, ToolEnd]


def user_entry(text: str, *, color: bool) -> TranscriptEntry:
    """用户行：亮色色带、按宽度动态渲染、前面留一个空行分开轮次。

    活轮次（`TuiApp._submitted`）与回放共用这一份——两处各写一遍迟早漂，
    而用户行是长对话里最重要的导航锚点（用户 2026-08-11 指出）。
    """
    return dynamic_entry(lambda w: [""] + [
        theme.band(row, w, theme.USER_BG, color=color)
        for row in theme.wrap(f"{theme.PROMPT} {text}", w)])


def compacted_entry(*, color: bool) -> TranscriptEntry:
    line = f"{theme.COMPACTED} 早前对话已压缩为摘要（正文不回放）"
    return dynamic_entry(lambda w: [""] + [
        theme.paint(row, theme.GREY, color=color) for row in theme.wrap(line, w)])
