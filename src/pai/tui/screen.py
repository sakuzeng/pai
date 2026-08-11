"""最小终端模拟器：把 pai 写出去的字节还原成「屏幕上是什么」。

**两个用途共用同一份实现**（feature 14 拍板的要点）：
- 测试断言「屏幕上有什么」（此前它住在 tests/，只跟踪几何）；
- 回放录制并**渲染成图片**，让 AI 自己看得见界面（`replay.py`）。

两者共用的价值不在省代码：**测试里断言的屏幕，与出图看到的屏幕，是同一个东西**。
分成两份实现的话，「测试全绿」与「图上是对的」会各说各话。

**为什么需要它**：feature 12 的前置反向对照卡在「看得见字节、看不见屏幕」——
本机没有 tmux 也没有 pyte，探针进程是 pty 的另一端而不是终端模拟器
（见 features/12 evidence）。而 `dock 变矮不留残影`、`commit 不与 dock 叠影`
这类断言**在原始字节上没法验**：同一个效果有多种字节写法，断言字节等于把实现钉死。
所以这里把字节解释成屏幕，测试断言**屏幕内容**。

**诚实边界**：它只实现 dock 渲染器实际会发的序列，不是通用终端。
`strict=True`（测试用）遇到不认识的序列直接 `raise`——**故意的**：
静默忽略会让测试对着「模拟器没看懂所以当没发生」的假象变绿。
`strict=False`（回放真实录制用）则记进 `unknown` 计数，不打断回放——
真实终端流里什么都可能出现，回放到一半炸掉比少画一个色码更糟。
"""

from __future__ import annotations

import re
from typing import List, Optional

from pai.modes.statusline import display_width

_CSI = re.compile(r"\x1b\[(\??)([0-9;]*)([A-Za-z])")


class Cell:
    """一个格子：字符 + 当时生效的样式。样式必须跟着**格子**存，不能跟着行存——
    一行里前半截灰、后半截青是常态。"""

    __slots__ = ("char", "fg", "bg", "bold", "dim")

    def __init__(self, char: str = " ", fg=None, bg=None,
                 bold: bool = False, dim: bool = False) -> None:
        self.char, self.fg, self.bg = char, fg, bg
        self.bold, self.dim = bold, dim


class VirtualScreen:
    """固定行列的格子网格 + 光标 + 滚动出屏的行（scrollback）。

    宽字符占两格：第一格放字符，第二格放 `None` 占位。取行时跳过 None——
    不这么做的话「中文」会被当成两列宽却只占一个格子，列号从此全错。
    """

    def __init__(self, cols: int = 40, rows: int = 8, *, strict: bool = True) -> None:
        self.cols = cols
        self.rows = rows
        self.strict = strict
        self.unknown: List[str] = []
        self._grid: List[List[Optional[Cell]]] = [
            [Cell() for _ in range(cols)] for _ in range(rows)]
        self.row = 0
        self.col = 0
        self.scrollback: List[str] = []
        self.scrollback_cells: List[List[Optional[Cell]]] = []
        # 当前 SGR 状态。写字符时**拷进格子**——之后再改 SGR 不该回头改已写的字。
        self._fg = None
        self._bg = None
        self._bold = False
        self._dim = False

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
                    self._unsupported(f"转义序列 {data[i:i + 12]!r}")
                    i += 1
                    continue
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

    def _unsupported(self, what: str) -> None:
        if self.strict:
            raise AssertionError(f"未识别的{what}")
        self.unknown.append(what)

    def _csi(self, m: "re.Match") -> None:
        private, params, final = m.group(1), m.group(2), m.group(3)
        if private:                        # \x1b[?2026h / l —— 同步输出，对内容无影响
            if params not in ("2026", "2004", "25"):
                self._unsupported(f"私有序列 ?{params}{final}")
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
            self._sgr(params)          # SGR：只改样式，不动几何
        elif final == "K":
            if n == 2:
                self._grid[self.row] = [Cell() for _ in range(self.cols)]
            elif n == 0:
                for c in range(self.col, self.cols):
                    self._grid[self.row][c] = Cell()
            else:
                self._unsupported(f"EL 参数 {n}")
        else:
            self._unsupported(f"CSI {params}{final}")

    def _sgr(self, params: str) -> None:
        codes = [int(x) for x in params.split(";") if x.isdigit()] or [0]
        i = 0
        while i < len(codes):
            n = codes[i]
            if n == 0:
                self._fg = self._bg = None
                self._bold = self._dim = False
            elif n == 1:
                self._bold = True
            elif n == 2:
                self._dim = True
            elif n == 22:
                self._bold = self._dim = False
            elif 30 <= n <= 37 or 90 <= n <= 97:
                self._fg = n
            elif 40 <= n <= 47 or 100 <= n <= 107:
                self._bg = n
            elif n == 39:
                self._fg = None
            elif n == 49:
                self._bg = None
            elif n in (38, 48) and i + 2 < len(codes) and codes[i + 1] == 5:
                # 38;5;N / 48;5;N —— 256 色
                if n == 38:
                    self._fg = ("256", codes[i + 2])
                else:
                    self._bg = ("256", codes[i + 2])
                i += 2
            i += 1

    def _newline(self) -> None:
        if self.row + 1 >= self.rows:
            self.scrollback.append(self._line(0))
            self.scrollback_cells.append(self._grid[0])
            self._grid.pop(0)
            self._grid.append([Cell() for _ in range(self.cols)])
        else:
            self.row += 1

    def _put(self, ch: str) -> None:
        w = display_width(ch)
        if self.col + w > self.cols:       # 自动折行：真终端会这么干
            self.col = 0
            self._newline()
        self._grid[self.row][self.col] = Cell(
            ch, self._fg, self._bg, self._bold, self._dim)
        for extra in range(1, w):
            self._grid[self.row][self.col + extra] = None
        self.col += w

    # --- 读出 ---------------------------------------------------------

    def _line(self, row: int) -> str:
        return "".join(c.char for c in self._grid[row] if c is not None).rstrip()

    def cells(self) -> List[List[Optional[Cell]]]:
        """当前屏幕的格子矩阵（出图用）。"""
        return self._grid

    def all_cells(self) -> List[List[Optional[Cell]]]:
        """滚出屏的 + 屏幕上的——即用户翻 scrollback 能看到的全部。"""
        return self.scrollback_cells + self._grid

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
