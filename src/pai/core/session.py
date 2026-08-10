"""会话落盘：append-only JSONL，一次会话一个文件。

落点由 pai.core.paths 决定（`~/.pai/projects/<slug>/sessions/`），**不再写当前工作目录**——
pai 的立意是在别人的项目里跑，往人家仓库里拉一个 sessions/ 目录是不能接受的（feature 08）。

每条记录带 sessionId 与 cwd：集中存放之后，同一仓库的不同子目录会写进同一个目录，
不记 cwd 就再也分不出「这次是在哪跑的」。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Union

from pai.core.paths import sessions_dir


class SessionLog:
    def __init__(self, directory: Optional[Union[str, Path]] = None):
        # 默认值必须在函数体里取，不能写成 `directory=sessions_dir()`——
        # 默认参数在**函数定义时**求值，测试隔离 $HOME 之后就追不回来了
        # （feature 05 补漏五刚在 history_path_for 上栽过同款）
        d = Path(directory) if directory is not None else sessions_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex
        # 时间戳前缀保留（`ls` 按时间排序），短 id 去碰撞（关掉 R#15：
        # 原来精确到秒，同秒建两个 SessionLog 会写同一个文件）。
        # 与 CC 不同：CC 用纯 `<sessionId>.jsonl`，可读性让位于唯一性。
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = d / f"{stamp}-{self.session_id[:8]}.jsonl"
        self.cwd = str(Path.cwd().absolute())
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        record = {"ts": time.time(), "sessionId": self.session_id, "cwd": self.cwd, **record}
        line = json.dumps(record, ensure_ascii=False) + "\n"
        # 并发批里多个工具会同时回填结果（feature 11）。不加锁的话两条长记录可能
        # 交织成半行，而**半行 JSONL 是不可恢复的**——审计流一旦坏了，坏的是历史。
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
