"""观测流落盘：把 loop 发的结构化事件追加成 JSONL，供 pai-viz 回放与实时点亮。

与 session.py 的分工是硬的，别混：

- session JSONL 是**审计流**——messages + usage，不可再生，是历史本身；
- 这里落的是**观测流**——harness 内部事件（权限判定、压缩、召回、熔断、中断），
  可再生（重跑一次就有），删了不损失历史。

生命周期不同的数据不该同文件，所以并排放 `<session 同名>.events.jsonl`
（features/17 问 3）。好处是既有消费者（压缩、将来的 --resume、evals）
一行都不用改——它们读 session 文件时不会撞见 12 种不认识的记录。

改造前这些事件只流过 on_event 渲染到终端，**过完就没了**：gate 判了什么、
压缩在第几步触发，事后完全无从查证。
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Union

from pai.core.events import AgentEvent, MessageDelta

EventHandler = Callable[[AgentEvent], None]


def _events_path(session_path: Path) -> Path:
    """`X.jsonl` → `X.events.jsonl`（同目录）。两个文件同名配对，viz 按名字找得到。"""
    return session_path.with_suffix(".events.jsonl")


class EventTrace:
    """可当 on_event 用的事件落盘器：`EventTrace(session)` 直接传给 loop。"""

    def __init__(self, session: Union["SessionLogLike", Path, str]) -> None:  # noqa: F821
        # SessionLog 或裸路径都收：装配处手里是 SessionLog，测试里给路径更省事
        raw = getattr(session, "path", session)
        self.path = _events_path(Path(raw))
        self._warned = False

    def __call__(self, event: AgentEvent) -> None:
        if isinstance(event, MessageDelta):
            # 增量正文最终会作为完整消息进 session 文件；在这儿再落一份，
            # 观测流就变成了第二份正文——量大且毫无新信息
            return
        record = {
            "event": type(event).__name__,
            "ts": time.time(),
            **dataclasses.asdict(event),
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            # 观测流挂了不能连累正事（同「工具错误不 throw」那条底线）。
            # 只告警一次：每步刷一行会把真正要看的输出淹掉。
            if not self._warned:
                self._warned = True
                print(f"⚠️ 事件落盘失败（{self.path}）：{e}；本会话不再提示",
                      file=sys.stderr)


def compose(*handlers: Optional[EventHandler]) -> EventHandler:
    """把若干 on_event 合成一个（渲染器 + 落盘器）。None 直接跳过。

    **不吞异常**：渲染器炸了就该炸，吞掉会让「界面不动」变成无声的谜。
    EventTrace 自己吞写失败是它对观测流的自我约束，不是这里的职责。
    """
    active = [h for h in handlers if h is not None]

    def fanout(event: AgentEvent) -> None:
        for handler in active:
            handler(event)

    return fanout
