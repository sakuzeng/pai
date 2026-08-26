"""终端列宽原语：`display_width` / `_truncate` / `_ESCAPES`（feature 12 T1 的落点）。

它此前住在 `modes/statusline.py`，而 `pai/tui/` 的九个模块都要用它——
形成 tui → modes 的依赖（无环，但方向是反的：宽度是 TUI 的地基，
不是状态行的私产）。T6 把状态行搬进 dock 时就该一并挪，本次补上。
`statusline` 从这里 import，方向翻正：modes → tui。

知识锚点：knowledge/tui/terminal-width.md。
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

ELLIPSIS = "…"


# 转义序列不占列。三类都要认：
#   CSI  \x1b[...字母      颜色、光标移动
#   OSC  \x1b]...\x07      超链接
#   APC  \x1b_...\x07      TUI 的 CURSOR_MARKER（pai.tui.component）
# 状态行自己撞不上（它先按可见文本截断再上色），但 TUI 组件会把 CURSOR_MARKER
# 嵌进文本里——宽度算错，硬件光标就摆错列，中文 IME 候选框跟着漂。
# pi 的 visibleWidth 同样显式处理 APC（K tui/pi-tui-main-screen.md 第六节）。
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[\]_][^\x07]*\x07")


def display_width(text: str) -> int:
    """终端列宽，不是字符数：东亚宽字符（W/F）占两列，转义序列占零列。

    按 len() 截断的话，一行中文会实际占掉两倍宽度把终端撑破行——这是中文终端 UI
    最常见的一个坑，也是本模块唯一真正需要动脑的地方。

    契约（R4#6 残余）：**调用方必须先消毒**（`tui/sanitize.py`），本函数对 `\\t`
    按 1 列计——这是错的，但结构上算不对：tab 的真实宽度取决于它落在第几列，
    而这里只拿得到片段。入口消毒（展开 `\\t`）之后正常路径上不会有 tab 到达这里；
    绕过消毒直接调用，宽度就是错的。

    组合记号（Mn/Me）与格式字符（Cf，含 ZWJ/零宽空格）计 0 列（R4#19 最小修，
    2026-08-22 拍板）：终端把它们叠在基字符上或根本不画。诚实边界：ZWJ emoji
    序列仍算错（各成员按 2 列相加，真实终端画 2 列）——那要 UAX#29 字素归组，
    拍板选了不引依赖的最小修，测试里有一条钉住这个已知错误。
    """
    visible = _ESCAPES.sub("", text)
    return sum(_char_width(c) for c in visible)


def _char_width(c: str) -> int:
    if unicodedata.category(c) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def _truncate(text: str, width: int) -> str:
    """按列宽截断并留出省略号的位置。"""
    if display_width(text) <= width:
        return text
    if width <= 1:
        return ELLIPSIS[:width]
    kept: List[str] = []
    used = 0
    for char in text:
        w = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if used + w > width - 1:            # 给 ELLIPSIS 留一列
            break
        kept.append(char)
        used += w
    return "".join(kept) + ELLIPSIS
