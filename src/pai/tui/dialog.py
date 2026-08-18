"""对话框：权限 ask 与 AskUserQuestion 共用一套（gate.py 里两者本来就已合流）。

**它存在是为了关掉一条真实事故**：模型提问期间用户敲的 `!echo 我是命令`
被静默当成了对问题的回答（08 遗留的铁证）。所以这里有一条硬语义——
**以 `!` 或 `/` 开头的输入不是答案**，它经 `handoff()` 交回主循环去执行。

`Esc` 取消：提问框 = 没作答，权限框 = 拒绝本次调用。两者返回同一个 `CANCELLED`
哨兵，含义由 `kind` 区分——调用方知道自己排的是哪种。
"""

from __future__ import annotations

from typing import List, Optional

from pai.modes.statusline import display_width, _truncate
from pai.tui import theme
from pai.tui.component import Component
from pai.tui.keys import Key

# 「用户取消了」。用哨兵而不是 None——None 是「还没答」，两者必须分得开。
CANCELLED = object()

# 「还没有结论」。与 CANCELLED 同一条纪律的第二半：`_result` 上也要分得开
# 「没人答过」与「答了但结论是取消」——混起来就是 R4#2（没显示过的框被当成答完了）。
_UNSET = object()

_HANDOFF_PREFIXES = ("!", "/")


class Dialog(Component):
    """一个待真人处理的问题。`handle` 返回非 None 表示这一框有结论了。"""

    def __init__(self, *, question: str, options: List[str],
                 kind: str = "question", color: bool = False) -> None:
        self.color = color
        self.question = question
        self.options = list(options)
        self.kind = kind                      # "question" | "permission"
        self.selected = 0
        self.typed = ""
        self._result = _UNSET

    # --- 结论（R4#2/R4#3：答案跟着框走，不进共享 FIFO）-------------------

    @property
    def resolved(self) -> bool:
        """这一框有没有结论。**等待方唯一该看的东西**——
        `arbiter.current() is None` 在「答完了」与「被打字压住」两种情形下
        都为真，拿它当判据就是用户没见过框却被判未作答。"""
        return self._result is not _UNSET

    @property
    def answer(self) -> Optional[str]:
        """结论里的答案；取消与未作答都是 None（由 `resolved` 区分「答没答过」）。"""
        if self._result is _UNSET or self._result is CANCELLED:
            return None
        return self._result

    def settle(self, result) -> None:
        """记下结论。`result` 可以是 `CANCELLED`——取消是**有结论**，不是还在等。"""
        self._result = result

    # --- 输入 ---------------------------------------------------------

    def handle(self, key: Key):
        name = key.name
        if name == "esc":
            return CANCELLED
        if name == "char":
            if not self.typed and key.text.isdigit():
                index = int(key.text) - 1
                if 0 <= index < len(self.options):
                    return self.options[index]
                return None                   # 越界的数字直接忽略，别当成自由文本
            self.typed += key.text
        elif name == "paste":
            self.typed += key.text
        elif name == "backspace":
            self.typed = self.typed[:-1]
        elif name == "up":
            self.selected = max(0, self.selected - 1)
        elif name == "down":
            self.selected = min(len(self.options) - 1, self.selected + 1)
        elif name == "enter":
            if self.handoff() is not None:
                return None                   # 命令不是答案，等主循环来取
            if self.typed.strip():
                return self.typed
            return self.options[self.selected]
        return None

    def handoff(self) -> Optional[str]:
        """输入是要交回主循环执行的命令吗（`!` shell / `/` 命令）？

        这就是那条铁证的修法：提问期间敲命令，就是执行命令。
        纯 REPL 里做不到——那时 asker 和主循环抢的是同一个 `read()`。
        """
        text = self.typed.strip()
        return text if text.startswith(_HANDOFF_PREFIXES) else None

    def take_handoff(self) -> Optional[str]:
        command = self.handoff()
        if command is not None:
            self.typed = ""
        return command

    # --- 渲染 ---------------------------------------------------------

    def render(self, width: int) -> List[str]:
        # 权限框与提问框用不同的记号：一个是「要不要放你过去」，一个是「你选哪个」，
        # 用户扫一眼就该分得出。都不用 emoji（theme.py 第一条硬约束）。
        mark, accent = (("!", theme.YELLOW) if self.kind == "permission"
                        else ("?", theme.CYAN))
        head, *rest = self.question.split("\n")     # gate 传来的问题是多行的
        lines = [theme.paint(_truncate(f"{mark} {head}", width), accent + theme.BOLD,
                             color=self.color)]
        for extra in rest:
            lines.append(theme.paint(_truncate(f"  {extra}", width), theme.DIM,
                                     color=self.color))
        for i, option in enumerate(self.options):
            chosen = i == self.selected and not self.typed
            cursor = theme.SELECTED if chosen else " "
            text = _truncate(f" {cursor} {i + 1}. {option}", width)
            lines.append(theme.paint(text, accent if chosen else theme.GREY,
                                     color=self.color))
        hint = "↑↓ 选择 · 回车确认 · 数字直选 · Esc 取消"
        tail = f"   {self.typed}" if self.typed else f"   {hint}"
        lines.append(theme.paint(_truncate(tail, width), theme.DIM, color=self.color))
        return lines
