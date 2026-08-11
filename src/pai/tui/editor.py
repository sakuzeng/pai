"""行编辑器：收按键、吐新状态，不碰终端、不做 IO。

替掉 readline（方案 A 全程 raw mode，readline 用不了）。
**已知回退**：`Ctrl+R` 增量搜索不做——拍板时就知道的代价，已登记 TODO。

光标是**字符索引**不是列号：一个中文是一个字符、两列。两者混用是中文终端 UI
第二常见的坑（第一是宽度），所以这里只在 `render` 里把索引换算成列。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from pai.tui import theme
from pai.tui.component import CURSOR_MARKER, Component
from pai.tui.keys import Key

_WORD_BREAK = " \t\n"


class LineEditor(Component):
    """一行（或 `\\` 续行出来的多行）输入。`handle` 返回非 None 表示这一行提交了。"""

    def __init__(self, *, prompt: str = "› ", continuation: str = "… ",
                 history: Optional[Sequence[str]] = None,
                 color: bool = False) -> None:
        self.color = color
        self.prompt = prompt
        self.continuation = continuation
        self.text = ""
        self.cursor = 0
        self._history: List[str] = list(history) if history else []
        self._hpos: Optional[int] = None      # None = 不在翻历史
        self._draft = ""                      # 翻历史前正在打的那半句

    # --- 输入 ---------------------------------------------------------

    def handle(self, key: Key) -> Optional[str]:
        name = key.name
        if name == "char":
            self._insert(key.text)
        elif name == "paste":
            self._insert(key.text)            # 粘贴内容里的换行不提交
        elif name == "enter":
            return self._enter()
        elif name == "backspace":
            if self.cursor:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
        elif name == "delete":
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        elif name == "left":
            self.cursor = max(0, self.cursor - 1)
        elif name == "right":
            self.cursor = min(len(self.text), self.cursor + 1)
        elif name in ("home", "ctrl_a"):
            self.cursor = 0
        elif name in ("end", "ctrl_e"):
            self.cursor = len(self.text)
        elif name == "ctrl_u":
            self.text = self.text[self.cursor:]
            self.cursor = 0
        elif name == "ctrl_k":
            self.text = self.text[:self.cursor]
        elif name == "ctrl_w":
            start = self._word_start()
            self.text = self.text[:start] + self.text[self.cursor:]
            self.cursor = start
        elif name == "word_left":
            self.cursor = self._word_start()
        elif name == "word_right":
            self.cursor = self._word_end()
        elif name == "up":
            self._history_step(-1)
        elif name == "down":
            self._history_step(1)
        # 其余（unknown / ctrl_c / esc / shift_tab …）不归编辑器管，交给上层仲裁
        return None

    def set_text(self, text: str) -> None:
        self.text = text
        self.cursor = len(text)

    def clear(self) -> None:
        self.text = ""
        self.cursor = 0
        self._hpos = None
        self._draft = ""

    # --- 内部 ---------------------------------------------------------

    def _insert(self, text: str) -> None:
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)

    def _enter(self) -> Optional[str]:
        if self.text.endswith("\\"):          # 05 已交付的续行语义，不做多行编辑器
            self.text = self.text[:-1] + "\n"
            self.cursor = len(self.text)
            return None
        line = self.text
        self.clear()
        return line

    def _word_start(self) -> int:
        i = self.cursor
        while i > 0 and self.text[i - 1] in _WORD_BREAK:
            i -= 1
        while i > 0 and self.text[i - 1] not in _WORD_BREAK:
            i -= 1
        return i

    def _word_end(self) -> int:
        i = self.cursor
        n = len(self.text)
        while i < n and self.text[i] in _WORD_BREAK:
            i += 1
        while i < n and self.text[i] not in _WORD_BREAK:
            i += 1
        return i

    def _history_step(self, delta: int) -> None:
        if not self._history:
            return
        if self._hpos is None:
            if delta > 0:
                return                        # 没在翻历史时按 ↓ 无事发生
            self._draft = self.text
            self._hpos = len(self._history)
        pos = self._hpos + delta
        if pos < 0:
            return                            # 顶到头就停住
        if pos >= len(self._history):
            self._hpos = None
            self.set_text(self._draft)        # 翻回来要能拿回正在打的那半句
            return
        self._hpos = pos
        self.set_text(self._history[pos])

    # --- 渲染 ---------------------------------------------------------

    def render(self, width: int) -> List[str]:
        lines = self.text.split("\n")
        before = self.text[:self.cursor]
        row = before.count("\n")
        col = len(before) - (before.rfind("\n") + 1)
        out: List[str] = []
        for i, line in enumerate(lines):
            prefix = theme.paint(self.prompt if i == 0 else self.continuation,
                                 theme.CYAN, color=self.color)
            if i == row:
                line = line[:col] + CURSOR_MARKER + line[col:]
            out.append(prefix + line)
        return out
