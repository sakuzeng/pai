"""外来文本进终端前的消毒。

工具输出与 `!命令` 输出是**外来字节**——`grep --color=always`、`cat Makefile`、
带进度条的命令都会带上 pai 没打算发的东西。原样写进终端有三类后果：

1. **光标移动 / 清屏类 CSI** 会打乱 dock 的相对定位基准。这与 feature 12
   「满屏阶梯」是同一类根因（那次是 pai 自己少数了几行，这次是别人替它多发了几个字节）。
2. **`\t` 在 pai 的整条宽度链上算 1 列**（`display_width` / `theme.wrap` /
   `_fit` / 选区切片），而真终端推进到 8 列 tab stop。
3. **`screen.py` 模拟器同样把 `\t` 当 1 格**，于是 e2e 断言的是一个真终端上
   不存在的画面——测试绿、真机坏。

**为什么消毒定在入口，而不是教每一层认识 tab**：tab 的宽度取决于**当前列**，
而 `display_width(片段)` 结构上拿不到列号，它不可能算对。在入口展开之后
下游全部自洽，模拟器与真终端也就不再分叉。

**边界是硬的**：只消毒「给终端看」的那一份。模型拿到的仍是原始输出——
命令真打印了什么，模型就该看见什么。
"""

from __future__ import annotations

import re

# 真终端的默认 tab stop。没有可配的必要：它是终端的默认值，不是 pai 的偏好。
TAB_STOP = 8

# 所有转义序列：CSI（`\x1b[...`）、OSC（`\x1b]...`，以 BEL 或 ST 收尾）、
# 以及 `\x1bX` 这类两字节序列。**连 SGR 一起剥是个取舍**：pai 自己给工具输出
# 上色（缩进 + 主题色），外来颜色会与它打架，而未闭合的 SGR 会漏进 pai 的界面。
# 代价是 `grep --color=always` 的高亮看不见——信息没丢，只是不着色。
_ESCAPE = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]"          # CSI
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"   # OSC，BEL 或 ST 收尾
    r"|\x1b[@-Z\\-_]"                  # 两字节转义
)

# 除 `\n` 之外的 C0 与 DEL。`\n` 是结构（pai 靠它数行），其余是噪音：
# `\r` 会让终端覆写本行（进度条），`\x07` 响铃，`\x0c` 换页。
_C0 = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitize_terminal_text(text: str) -> str:
    """把外来文本变成「可以安全写进终端」的样子。

    顺序不能反：**先剥转义再展开 tab**——`\x1b[31m` 这类序列里不含 tab，
    但序列若先被 `expandtabs` 当成普通字符参与列计数，展开位置就错了。
    展开按**行**做（`expandtabs` 本身就以 `\n` 重新起算），所以多行输出的
    第二行起也对得上。
    """
    if not text:
        return text
    text = _ESCAPE.sub("", text)
    text = text.expandtabs(TAB_STOP)
    return _C0.sub("", text)
