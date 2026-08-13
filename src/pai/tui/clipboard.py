"""把文本写进剪贴板。**两条路，都不可靠，所以措辞要诚实。**

**实测前提**（features/16 evidence 第 1 条，本机 iTerm2 3.6.11）：
OSC 52（`\\x1b]52;c;<base64>\\x07`）**一个字都没写进剪贴板**——
BEL 与 ST 两种结尾都试过，剪贴板保持测试前的哨兵值，而且**完全静默**。
多数终端出于安全默认禁止应用写剪贴板，且拒绝时不给任何回应。

配合另一条实测（DECRQM 在 Terminal.app 完全不可用，见
[K alt-screen-and-mouse 第五节](../../../knowledge/tui/alt-screen-and-mouse.md)）
——**没法先问终端支不支持**——只能：

1. 本地优先走**系统剪贴板命令**（有退出码，成败判得出来）；
2. 只有在 ssh 里、或本地那条路全军覆没时，才发 OSC 52；
3. **走了 OSC 52 就不许说「已复制」**，只能说「已尝试」。

pi 只发 OSC 52（`tui-alt-screen.ts`）——**那在这台机器上是坏的**。
参照实现跑得通，不代表在你的终端上跑得通。
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

OSC52_PREFIX = "\x1b]52;c;"
TIMEOUT_SECONDS = 0.5          # 子进程卡住不能把界面拖死

# 按平台常见程度排；第一个「装了的」就用它。
_COMMANDS: List[List[str]] = [
    ["pbcopy"],                        # macOS
    ["wl-copy"],                       # Wayland
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
]


@dataclass(frozen=True)
class CopyResult:
    ok: bool
    path: str                  # system / osc52 / none
    message: str


def copy(text: str, *, run: Optional[Callable] = None,
         write: Optional[Callable[[str], None]] = None,
         env: Optional[Dict[str, str]] = None,
         which: Optional[Callable[[str], bool]] = None) -> CopyResult:
    """复制。全部依赖可注入，于是离线可测（不真的动系统剪贴板）。"""
    if not text:
        return CopyResult(False, "none", "")
    run = run or _run
    write = write or _noop
    env = os.environ if env is None else env
    which = which or (lambda cmd: shutil.which(cmd) is not None)

    # ssh 里 pbcopy 写的是**远程**的剪贴板，对用户毫无意义——直接走 OSC 52
    if not env.get("SSH_CONNECTION"):
        for argv in _COMMANDS:
            if not which(argv[0]):
                continue
            try:
                if run(argv, text, TIMEOUT_SECONDS) == 0:
                    return CopyResult(True, "system", f"已复制 {_lines(text)} 行")
            except Exception:            # noqa: BLE001 - 超时/起不来都当失败，继续兜底
                continue

    write(OSC52_PREFIX + base64.b64encode(text.encode()).decode() + "\x07")
    # **不说「已复制」**：实测这条路会静默失败，而我们无从判断
    return CopyResult(True, "osc52", f"已尝试复制 {_lines(text)} 行（OSC 52）")


def _lines(text: str) -> int:
    return text.count("\n") + 1


def _run(argv: List[str], text: str, timeout: float) -> int:
    proc = subprocess.run(argv, input=text.encode(), timeout=timeout,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.returncode


def _noop(_data: str) -> None:
    pass
