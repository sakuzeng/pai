"""会话 JSONL 落盘：每条消息一行，append-only。

这是审计/回放/压缩后原始数据保留的地基（对应面试陷阱题"压缩后原始数据还要吗"）。
阶段 1 做 compaction 时，被摘要的消息只从发给模型的视图里消失，这里的记录不动。
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class SessionLog:
    def __init__(self, directory: str | Path = "sessions"):
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = d / f"{stamp}.jsonl"

    def append(self, record: dict) -> None:
        record = {"ts": time.time(), **record}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
