"""测试基建：一个最小终端模拟器，只认 dock 渲染器会发的那几种序列。

**为什么需要它**：feature 12 的前置反向对照卡在「看得见字节、看不见屏幕」——
本机没有 tmux 也没有 pyte，探针进程是 pty 的另一端而不是终端模拟器
（见 features/12 evidence）。而 `dock 变矮不留残影`、`commit 不与 dock 叠影`
这类断言**在原始字节上没法验**：同一个效果有多种字节写法，断言字节等于把实现钉死。
所以这里把字节解释成屏幕，测试断言**屏幕内容**。

**诚实边界**：它只实现 dock 渲染器实际会发的序列，不是通用终端。
遇到不认识的转义序列会 `raise`——**故意的**：静默忽略会让测试对着一个
「模拟器没看懂所以当没发生」的假象变绿。
"""

from __future__ import annotations

import re
from typing import List, Optional

from pai.modes.statusline import display_width

_CSI = re.compile(r"\x1b\[(\??)([0-9;]*)([A-Za-z])")


class VirtualScreen:
    """固定行列的字符网格 + 光标 + 滚动出屏的行（scrollback）。

    宽字符占两格：第一格放字符，第二格放 None 占位。取行时跳过 None——
    不这么做的话「中文」会被当成两列宽却只占一个格子，列号从此全错。
    """

    def __init__(self, cols: int = 40, rows: int = 8) -> None:
        self.cols = cols
        self.rows = rows
        self._grid: List[List[Optional[str]]] = [
            [" "] * cols for _ in range(rows)]
        self.row = 0
        self.col = 0
        self.scrollback: List[str] = []

    # --- 写入 ---------------------------------------------------------

    def write(self, data: str) -> None:
        i = 0
        while i < len(data):
            ch = data[i]
            if ch == "\x1b":
                if data[i + 1:i + 2] in ("_", "]"):
                    # APC / OSC：真终端会忽略（CURSOR_MARKER 靠的就是这一点），
                    # 以 BEL 结尾。整段吞掉，不占列。
                    end = data.find("\x07", i)
                    if end == -1:
                        raise AssertionError(f"未终止的 APC/OSC: {data[i:i + 12]!r}")
                    i = end + 1
                    continue
                m = _CSI.match(data, i)
                if not m:
                    raise AssertionError(f"未识别的转义序列: {data[i:i + 12]!r}")
                self._csi(m)
                i = m.end()
                continue
            if ch == "\r":
                self.col = 0
            elif ch == "\n":
                self._newline()
            elif ch == "\x07":
                pass                       # BEL：CURSOR_MARKER 的结尾，不占格
            else:
                self._put(ch)
            i += 1

    def _csi(self, m: "re.Match") -> None:
        private, params, final = m.group(1), m.group(2), m.group(3)
        if private:                        # \x1b[?2026h / l —— 同步输出，对内容无影响
            if params != "2026":
                raise AssertionError(f"未识别的私有序列: ?{params}{final}")
            return
        n = int(params) if params.isdigit() else (0 if final == "K" else 1)
        if final == "A":
            self.row = max(0, self.row - n)
        elif final == "B":
            self.row = min(self.rows - 1, self.row + n)
        elif final == "C":
            self.col = min(self.cols, self.col + n)
        elif final == "D":
            self.col = max(0, self.col - n)
        elif final == "G":
            self.col = max(0, min(self.cols, n - 1))     # 1-indexed
        elif final == "m":
            pass                       # SGR：颜色，对几何无影响
        elif final == "K":
            if n == 2:
                self._grid[self.row] = [" "] * self.cols
            elif n == 0:
                for c in range(self.col, self.cols):
                    self._grid[self.row][c] = " "
            else:
                raise AssertionError(f"未支持的 EL 参数: {n}")
        else:
            raise AssertionError(f"未识别的 CSI: {params}{final}")

    def _newline(self) -> None:
        if self.row + 1 >= self.rows:
            self.scrollback.append(self._line(0))
            self._grid.pop(0)
            self._grid.append([" "] * self.cols)
        else:
            self.row += 1

    def _put(self, ch: str) -> None:
        w = display_width(ch)
        if self.col + w > self.cols:       # 自动折行：真终端会这么干
            self.col = 0
            self._newline()
        self._grid[self.row][self.col] = ch
        for extra in range(1, w):
            self._grid[self.row][self.col + extra] = None
        self.col += w

    # --- 读出 ---------------------------------------------------------

    def _line(self, row: int) -> str:
        return "".join(c for c in self._grid[row] if c is not None).rstrip()

    def lines(self) -> List[str]:
        """当前屏幕内容，逐行右侧去空白。"""
        return [self._line(r) for r in range(self.rows)]

    def logical_lines(self) -> List[str]:
        """滚出屏的 + 屏幕上的，即用户翻 scrollback 能看到的全部内容。"""
        return self.scrollback + self.lines()

    def visible(self) -> List[str]:
        """去掉尾部空行的屏幕内容——断言里通常只关心「有字的那几行」。"""
        out = self.lines()
        while out and not out[-1]:
            out.pop()
        return out
