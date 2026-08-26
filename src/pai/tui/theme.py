"""配色与字形。TUI 里所有「长什么样」的决定集中在这里。

**两条硬约束，都是用户 2026-08-11 真跑撞出来的**：

1. **不用 emoji**。`🤖` 在用户终端上渲染成了方块——emoji 依赖字体覆盖，
   缺字变豆腐块，而且宽度在各终端不一致（有的按 1 列、有的按 2 列排版），
   一旦算错整行光标就漂。TUI 自己的字形一律用**文本呈现**的符号
   （U+25CF 这类），宽度确定、几乎所有等宽字体都有。
   注：`core/events.py` 的 `render_text` 里那些 emoji 是 05/06 交付的，
   属 scrollback 内容不归 TUI 管，本轮不动它们。

2. **上色必须可关**。非 tty 或设了 `NO_COLOR` 时一个转义符都不许吐，
   否则管道日志变乱码（同 `statusline.StatusLinePrinter` 的老规矩）。

配色取向：pai 用**青蓝**一系，刻意避开 CC 的橙与 pi 的紫——
学它们的机制，但不要看起来像它们的仿制品。
"""

from __future__ import annotations

import os

RESET = "\x1b[0m"

# 基础色（16 色，任何终端都有）
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
BLUE = "\x1b[34m"
GREY = "\x1b[90m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"

# 用户输入那一行的背景色带。**加粗不够**——一眼扫过去要能立刻定位「我问了什么」，
# 靠的是一块横贯整宽的底色，不是字重（用户 2026-08-11 两次指出后照 CC 改）。
# 236 是很暗的灰：在深色主题上刚好浮出来，不会把正文压住。
USER_BG = "\x1b[48;5;236m"

# 256 色的青蓝渐变，logo 流光用。从暗到亮，最后一档是高光。
RAMP = tuple(f"\x1b[38;5;{n}m" for n in (23, 30, 37, 44, 51, 87, 123, 159, 195))

# --- 字形（全部一列宽、非 emoji）----------------------------------------
ANSWER = "●"        # 模型的回答（CC 用的也是这个，而不是 emoji）
SUMMARY = "✳"       # 一轮跑完的摘要
QUEUE = "⧗"         # 排队中的追加消息
RULE = "─"          # dock 的分隔线
PROMPT = "›"        # 输入提示（沿用 05 交付的形状）
CONTINUATION = "…"  # 续行提示
DETAIL = "└"        # 活动区的明细行
SELECTED = "❯"      # 对话框里选中的那一项


def use_color(is_tty: bool) -> bool:
    return bool(is_tty) and not os.environ.get("NO_COLOR")


def paint(text: str, code: str, *, color: bool) -> str:
    """上色。`color=False` 时原样返回——**不是返回空色码，是一个字节都不加**。"""
    return f"{code}{text}{RESET}" if color and text else text


def wrap(text: str, width: int) -> "list":
    """按**显示列宽**折行（不是字符数）。

    为什么必须自己折：终端会替你折，但那样「我以为写了 1 行、实际占了 3 行」，
    dock 的相对光标移动全部错位——用户 2026-08-11 满屏阶梯就是这么来的。
    """
    from pai.tui.width import _ESCAPES, display_width

    if width <= 0:
        return [text]
    out = []
    for line in text.split("\n"):
        if not line:
            out.append("")
            continue
        buf, used, i = "", 0, 0
        while i < len(line):
            # 转义序列整段吞掉、**不占列**——按字符切会把 `\x1b` 当成 1 列，
            # 彩色文本的折行位置就全错了（而且会把序列切成两半变乱码）。
            m = _ESCAPES.match(line, i)
            if m:
                buf += m.group(0)
                i = m.end()
                continue
            w = display_width(line[i])
            if used + w > width:
                out.append(buf)
                buf, used = "", 0
            buf += line[i]
            used += w
            i += 1
        out.append(buf)
    return out


def band(text: str, width: int, code: str, *, color: bool) -> str:
    """把一行铺满整宽再上色——**底色要横贯整行**才形成「色带」。

    不补空格的话底色只包住文字，看起来是个歪歪扭扭的高亮块而不是一条带。
    """
    from pai.tui.width import display_width

    if not color:
        return text
    pad = max(0, width - display_width(text))
    return f"{code}{text}{' ' * pad}{RESET}"
