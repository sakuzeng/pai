"""启动 logo 与它的流光动画。

**设计取向**：CC 用橙、pi 用紫，pai 取青蓝——学它们的机制，别看起来像仿制品。
字形用半块字符（`▀▄█`）而不是实心方块拼的巨字：同样的 3 行高度，
半块能表达笔画粗细，看起来是「设计过的」而不是「用 # 拼的」。

**动画怎么做的**：一束高光从左扫到右，**同一份字形、每帧只改配色**。
于是「动画」这件事离线完全可测（帧在变、几何不变、关色后无转义符），
不需要真终端。这条约束反过来也保证了动画不会把布局搞乱。

**已知风险**：`█▀▄` 的 East Asian Width 是 `A`（ambiguous）。
iTerm2 默认按 1 列渲染（pai 的 `display_width` 也按 1 列算），
但用户若开了「ambiguous 按双宽」，logo 会被撑成两倍宽。
只影响 logo 这一块的观感，不影响 dock 布局——它一画完就 commit 进 scrollback 了。
"""

from __future__ import annotations

from typing import List

from pai.tui.width import _ESCAPES, _truncate, display_width
from pai.tui.theme import BOLD, DIM, RAMP, RESET, paint

# 3 行 × 13 列。每行宽度必须完全一致，否则流光会歪。
ROWS = (
    "█▀▀▄ ▄▀▀▄ ▀█▀",
    "█▄▄▀ █▄▄█  █ ",
    "█    █  █ ▀█▀",
)
WIDTH = len(ROWS[0])
INDENT = "  "
SUBTITLE = "从零实现的编码 agent"

# 高光扫完全程（含扫进来与扫出去的拖尾）所需的帧数。
FRAMES = WIDTH + len(RAMP) * 2


def strip(row: str) -> str:
    """剥掉转义序列，只留字形——测试用它断言「动的只有颜色」。"""
    return _ESCAPES.sub("", row)


def render(frame: int = 0, *, color: bool = True) -> List[str]:
    """一帧 logo。`color=False` 时原样返回字形，不含任何转义符。"""
    if not color:
        return list(ROWS)
    head = frame % FRAMES - len(RAMP)          # 高光此刻在第几列（可为负 = 还没进场）
    out: List[str] = []
    for row in ROWS:
        buf = []
        for column, char in enumerate(row):
            if char == " ":
                buf.append(char)
                continue
            distance = abs(column - head)
            buf.append(RAMP[max(0, len(RAMP) - 1 - distance)] + char)
        out.append("".join(buf) + RESET)
    return out


def banner(width: int, frame: int = 0, *, color: bool = True) -> List[str]:
    """整块开场：logo + 副标题。**放不下就退化成一行**，绝不撑破终端。"""
    if width < WIDTH + len(INDENT) * 2:
        return [_truncate(f"pai · {SUBTITLE}", width)]
    lines = [INDENT + row for row in render(frame, color=color)]
    subtitle = INDENT + SUBTITLE
    if display_width(subtitle) <= width:
        lines.append(paint(subtitle, DIM, color=color))
    return lines


def settled(width: int, *, color: bool = True) -> List[str]:
    """动画收尾的那一帧：整块统一成高亮色，不再有高光。

    它是要 commit 进 scrollback 的那份——**scrollback 里的东西不会再重画**，
    所以不能留一个「高光正扫到一半」的姿态在那儿。
    """
    if width < WIDTH + len(INDENT) * 2:
        return [_truncate(f"pai · {SUBTITLE}", width)]
    bright = RAMP[-2]
    lines = [INDENT + paint(row, BOLD + bright, color=color) for row in ROWS]
    subtitle = INDENT + SUBTITLE
    if display_width(subtitle) <= width:
        lines.append(paint(subtitle, DIM, color=color))
    return lines
