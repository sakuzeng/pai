"""事件流：loop 对外只发结构化事件，怎么显示是上层的事。

改造前 loop 直接把拼好的中文字符串喂给 on_event，等于把渲染写死在核心里——
REPL 要按事件类型分流（工具行折叠、压缩提示单列、用量进状态栏）就无从下手。
参照 pi 的 AgentEvent（扁平 discriminated union），但**砍掉 message_update/turn_end**：
不流式的情况下它们与 AssistantMessage 同一时刻同一信息，为凑形状而设是虚的，
等阶段 5 真有「一轮内多次增量」再补。

render_text 是默认渲染器，逐字复现改造前的输出（tests/test_events.py 的 LEGACY_* 钉死）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple, Union

TOOL_RESULT_PREVIEW_CHARS = 200


@dataclass(frozen=True)
class AgentStart:
    task: str


@dataclass(frozen=True)
class TurnStart:
    step: int


@dataclass(frozen=True)
class AssistantMessage:
    content: Optional[str]
    tool_call_names: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolStart:
    tool_call_id: str
    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolEnd:
    tool_call_id: str
    name: str
    args: dict
    result: str
    # 诚实边界：只标得出 loop 自己造的错（参数非法 / 未知工具）。工具内部异常被
    # Tool.run 吸收成「错误：...」字符串，从这里分辨不出来——要分辨得改 Tool.run
    # 的返回契约，那是另一件事（TODO 已记）。
    is_error: bool = False


@dataclass(frozen=True)
class Compacted:
    cut: int
    before: int
    after: int


@dataclass(frozen=True)
class CompactionSkipped:
    # anchors_pending = 刚压完锚点簿被清空，等一轮真实 usage 就能续（正常两步节奏）
    # nothing_to_cut  = 真的无可压（超长单轮或保留预算吞下全部历史）
    reason: Literal["anchors_pending", "nothing_to_cut"]
    estimated: int


@dataclass(frozen=True)
class BreakerTripped:
    failures: int


@dataclass(frozen=True)
class MemoryWritten:
    topic: str
    path: str


@dataclass(frozen=True)
class Interrupted:
    where: Literal["tool", "step"]


@dataclass(frozen=True)
class AgentEnd:
    reason: Literal["final", "max_steps", "budget", "interrupted"]
    text: str


AgentEvent = Union[
    AgentStart,
    TurnStart,
    AssistantMessage,
    ToolStart,
    ToolEnd,
    Compacted,
    CompactionSkipped,
    BreakerTripped,
    MemoryWritten,
    Interrupted,
    AgentEnd,
]


def render_text(event: AgentEvent) -> Optional[str]:
    """默认渲染器：返回 None 表示这个事件默认不打印。

    None 而不是空串——空串会让 `print(render_text(e))` 吐出空行，
    「不打印」和「打印一个空行」是两回事。
    """
    if isinstance(event, ToolEnd):
        result = event.result
        ellipsis = "…" if len(result) > TOOL_RESULT_PREVIEW_CHARS else ""
        return f"🔧 {event.name}({event.args}) → {result[:TOOL_RESULT_PREVIEW_CHARS]}{ellipsis}"
    if isinstance(event, Compacted):
        return f"🗜️ 压缩：切于 {event.cut}，估算 {event.before} → {event.after}"
    if isinstance(event, CompactionSkipped):
        if event.reason == "anchors_pending":
            return f"🗜️ 锚点不足（<2）无法定真实切点，本步暂缓压缩（估算 {event.estimated}）"
        return (f"⚠️ 上下文超线（估算 {event.estimated}）但无可压（超长单轮或预算吞下全部历史），"
                "不压，靠预算熔断兜底")
    if isinstance(event, BreakerTripped):
        return f"⚠️ 压缩连续失败 {event.failures} 次，自动压缩已熔断"
    if isinstance(event, MemoryWritten):
        return f"🧠 已记住（{event.topic}）→ {event.path}"
    if isinstance(event, Interrupted):
        where = "工具执行被终止" if event.where == "tool" else "停在下一次请求之前"
        return f"⛔ 已中断：{where}，已完成的工作保留"
    return None
