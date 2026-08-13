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
class MessageDelta:
    """一轮内的增量文本。本文件开头写着「等阶段 5 真有『一轮内多次增量』再补」——就是它。

    `render_text` 对它返回 None，理由不是「默认不出声」而是**契约不合**：
    render_text 的契约是「返回一行」，而增量必须**不换行**地写出去。
    上屏因此由 modes 层负责（D#39 渲染下放）。
    """

    text: str


@dataclass(frozen=True)
class ToolStart:
    tool_call_id: str
    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PermissionDecided:
    """权限判定结果。在 ToolStart **之前**发出——被拦下的调用压根不会有 ToolStart。

    `kind` 是 loop 收到的最终三态。ask 到这里已经被装配层解析掉了
    （问过真人，或无人可问降级为 deny），loop 不认识 ask 这个概念。
    """

    tool_call_id: str
    name: str
    kind: str
    reason: str = ""


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
class RecallFailed:
    """记忆召回失败。CC 是「失败返回空、不阻断」且全静默；pai 要说出来——
    否则用户看到的只是「召回好像不生效」，而真实原因（provider 报错 / 回复没法解析）
    一点痕迹都不留（2026-08-11 真跑冒烟撞到的正是这个）。"""

    reason: Literal["request_failed", "unparseable"]
    detail: str
    disabled: bool          # 熔断是否已跳闸（本会话不再尝试）


@dataclass(frozen=True)
class ConversationCleared:
    """`/clear`：上下文被清空，同一次运行里就此开始一段**新对话**。

    feature 17 补上。此前 `/clear` 只截断内存里的 messages，两个流里都不留痕——
    于是观测页面会把清空前后画成一段连贯对话，而模型在后半段根本不记得前半段。
    「上下文里有什么」正是学 harness 时最要看清的东西，画错比不画更糟。

    与 `Compacted` 的区别：压缩是**换掉**上下文（有摘要接续），清空是**丢弃**上下文。
    """

    kept: int          # 保留下来的消息数（当前实现保留 system，即 1）


@dataclass(frozen=True)
class RecallInjected:
    """本轮召回选中并注入了哪几篇。feature 17 补上——此前**只有失败发事件**，
    成功是哑的：观测流里说得出「召回过」，说不出「召回了什么」。

    明确不选（`selected: []`）不发这个事件：那是正常结果，不是「注入了 0 篇」。
    """

    names: Tuple[str, ...]


@dataclass(frozen=True)
class MemoryWritten:
    topic: str
    path: str


@dataclass(frozen=True)
class Interrupted:
    # stream = 掐在模型输出中途（feature 11）。与另外两处的区别有实际后果：
    # 这一种**拿不到 usage**，所以那一步的消耗永远不会进账。
    where: Literal["tool", "step", "stream"]


@dataclass(frozen=True)
class AgentEnd:
    reason: Literal["final", "max_steps", "budget", "interrupted"]
    text: str


AgentEvent = Union[
    AgentStart,
    TurnStart,
    AssistantMessage,
    MessageDelta,
    PermissionDecided,
    ToolStart,
    ToolEnd,
    Compacted,
    CompactionSkipped,
    BreakerTripped,
    RecallFailed,
    RecallInjected,
    ConversationCleared,
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
    if isinstance(event, PermissionDecided):
        if event.kind == "allow":
            return None                  # 放行是常态，逐条打出来只会淹没真正要看的
        return f"🚫 权限拒绝 {event.name}：{event.reason}"
    if isinstance(event, Compacted):
        return f"🗜️ 压缩：切于 {event.cut}，估算 {event.before} → {event.after}"
    if isinstance(event, RecallFailed):
        tail = "，本会话不再尝试召回" if event.disabled else ""
        return f"⚠️ 记忆召回失败（{event.reason}）：{event.detail}{tail}"
    if isinstance(event, CompactionSkipped):
        if event.reason == "anchors_pending":
            return f"🗜️ 锚点不足（<2）无法定真实切点，本步暂缓压缩（估算 {event.estimated}）"
        return (f"⚠️ 上下文超线（估算 {event.estimated}）但无可压（超长单轮或预算吞下全部历史），"
                "不压，靠预算熔断兜底")
    if isinstance(event, BreakerTripped):
        return f"⚠️ 压缩连续失败 {event.failures} 次，自动压缩已熔断"
    if isinstance(event, ConversationCleared):
        return "🧹 已清空对话（保留 system）"
    if isinstance(event, RecallInjected):
        return f"🧠 召回 {len(event.names)} 篇记忆：{'、'.join(event.names)}"
    if isinstance(event, MemoryWritten):
        return f"🧠 已记住（{event.topic}）→ {event.path}"
    if isinstance(event, Interrupted):
        where = "工具执行被终止" if event.where == "tool" else "停在下一次请求之前"
        return f"⛔ 已中断：{where}，已完成的工作保留"
    return None
