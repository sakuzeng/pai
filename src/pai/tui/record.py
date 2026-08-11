"""录制 pai 写给终端的字节流。

**为什么要有**：feature 12 交付后的四轮视觉修正全靠用户截图往返——
pai 自己看不见「屏幕上最后长什么样」，于是每一个排版/配色问题都得等真人发现。
录下来 + 回放成图（`replay.py`），AI 才有可能先于用户看见问题。

**格式**：JSONL，一行一条。`{"t": 秒, "cols": N, "rows": N, "data": "..."}`。
尺寸每条都带——**resize 正是问题多发区**，回放时不知道当时多宽就还原不出来。
用自研极简格式而不是 asciinema：本机没装，且引入外部依赖与项目定位不符
（features/14 拍板问）。

**对 pai 的行为零影响**：只是在注入的 `write` 外面 tee 一层；
写录制文件失败一律吞掉——**录制坏了不能把会话带崩**。
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

ENV_VAR = "PAI_TUI_RECORD"


def record_path() -> Optional[str]:
    """录制默认关闭：只有显式设了环境变量才录。"""
    return os.environ.get(ENV_VAR) or None


class Recorder:
    """把每次写入连同当时的终端尺寸追加到 JSONL。"""

    def __init__(self, path: str, *, size: Callable[[], tuple],
                 now: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self._size = size
        self._now = now
        self._start = now()
        self._file = None
        try:
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._file = open(path, "w", encoding="utf-8")
        except OSError:
            self._file = None            # 录不成就当没开，不影响会话

    def wrap(self, write: Callable[[str], None]) -> Callable[[str], None]:
        """包一层 tee。返回的函数与原 `write` 行为完全一致。"""

        def teed(data: str) -> None:
            write(data)
            self.note(data)

        return teed

    def note(self, data: str) -> None:
        if self._file is None or not data:
            return
        try:
            cols, rows = self._size()
        except Exception:                # noqa: BLE001 - 拿不到尺寸也要能录
            cols, rows = 80, 24
        record = {"t": round(self._now() - self._start, 3),
                  "cols": cols, "rows": rows, "data": data}
        try:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()           # 会话被 kill 时也要留下已发生的部分
        except (OSError, ValueError):
            self._file = None            # 写坏了就停录，不再打扰会话

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
