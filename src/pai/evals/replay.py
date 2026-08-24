"""会话轨迹 → 回放脚本的派生器（feature 32 T3）。

参照 dsh llm-replay 的核心思想（K evals/dsh-testing.md）：fixture 就是
持久化会话日志本身，不另造格式。粒度取舍已在 spec 记档：pai 会话 v1 存的
是装配后的消息，回放粒度就是整条 assistant 消息——不重建分片
（fake_provider 发流时本来就按字符重新切）。

含 compaction 的会话本轮拒绝：重建出的摘要消息不是模型当时真实说过的话，
拿它当回放脚本等于把评测建在合成物上（spec 第 3 节；dsh 对压缩回放另立
显式规则，pai 等真实需要再做）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

from pai.core.session import build_messages, load_session


@dataclass(frozen=True)
class ReplayPlan:
    """一次回放的全部输入：任务文本（录制会话的首条 user 消息）+
    fake_provider 脚本（与 tests/fake_provider.turn 同形的 dict 列表）。"""

    task: str
    script: List[dict]


def derive_replay(path: Union[str, Path]) -> ReplayPlan:
    """v1 会话文件 → ReplayPlan。v0/坏文件沿用 load_session 的拒绝语义。"""
    _, entries = load_session(path)
    if any(e.get("type") == "compaction" for e in entries):
        raise ValueError(
            "含 compaction 条目的会话不支持派生回放脚本（spec 32 第 3 节）："
            "重建摘要不是模型当时的真实输出。请换一份未压缩的轨迹。")
    messages, _ = build_messages(entries)
    task = next((m.get("content") for m in messages
                 if m.get("role") == "user" and m.get("content")), None)
    if task is None:
        raise ValueError("会话里没有 user 消息，派生不出回放任务文本。")
    script: List[dict] = []
    for m in messages:
        if m.get("role") != "assistant":
            continue
        calls = [{"name": tc["function"]["name"],
                  "arguments": json.loads(tc["function"]["arguments"] or "{}")}
                 for tc in (m.get("tool_calls") or [])]
        script.append({"content": m.get("content") or "",
                       "tool_calls": calls, "delay": 0.0})
    if not script:
        raise ValueError("会话里没有 assistant 消息，无脚本可派生。")
    return ReplayPlan(task=str(task), script=script)
