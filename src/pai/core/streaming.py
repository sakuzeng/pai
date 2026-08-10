"""流式装配：把 chunk 序列装回一条与非流式同形状的响应。

**一次响应 = 一条 assistant 消息**，这条不许改。
CC 走 Anthropic 协议时把每个 content block 变成一条独立 assistant 记录、共享同一个
`message.id`，于是必须再写一个 `getAssistantMessageId` 把它们认回去，
否则上下文估算会重复计数（见 K source-walks/cc-streaming-tools.md 第四节）。
**那个补丁存在的唯一原因是那个建模选择**——不是流式的固有代价。
谁将来想为了「边流边显示」把这里拆成多条记录，先读这段。

装配规则全部来自真实探针（features/11 的 evidence/20260811-流式探针/），不是从文档推的：
DeepSeek 的实际行为与它自己的文档在 usage 这件事上就不一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

from pai.core.interrupt import InterruptFlag


@dataclass
class _Function:
    name: str = ""
    arguments: str = ""


@dataclass
class StreamedToolCall:
    """与 SDK 的 tool_call 同形状（`.id` / `.function.name` / `.function.arguments`），
    这样 loop 那一侧一个字都不用改。"""

    id: str = ""
    function: _Function = field(default_factory=_Function)


@dataclass
class StreamedResponse:
    """同形状替身：`.content` / `.tool_calls` 对齐 `response.choices[0].message`，
    `.usage` 是 dict（`compaction.usage_fields` 已覆盖 dict 分支，不用改它）。"""

    content: Optional[str] = None
    tool_calls: Optional[List[StreamedToolCall]] = None
    finish_reason: Optional[str] = None
    usage: dict = field(default_factory=dict)   # 空 dict = 这次没拿到（中断）
    interrupted: bool = False


def assemble(
    chunks: Iterable,
    *,
    on_delta: Optional[Callable[[str], None]] = None,
    flag: Optional[InterruptFlag] = None,
) -> StreamedResponse:
    """消费 chunk 迭代器，返回装配好的响应。`on_delta` 收到的是**增量文本**，不是全文。"""
    parts: List[str] = []
    calls: Dict[int, StreamedToolCall] = {}      # index -> 累积中的调用
    order: List[int] = []                        # 首次出现顺序；不拿 dict 顺序当契约
    finish_reason: Optional[str] = None
    usage: dict = {}

    for chunk in chunks:
        if flag is not None and flag.is_set():
            # 中断 = 没读到末块 = 没有 usage。不猜、不补，如实回空。
            # 被中断的请求服务端照样计费，本地少算是事实；掩盖它才是 bug。
            return StreamedResponse(content="".join(parts) or None, usage={},
                                    interrupted=True)

        # usage：**每块都看**，最后一个非空的赢。
        # 不许写成 `if not chunk.choices: usage = ...`——DeepSeek 的末块 choices 非空，
        # 那个分支永不触发（实测三方对照，include_usage 传不传都一样）；
        # 也不许写成「只看末块」——标准 OpenAI 会给一个 choices 为空的独立块。
        # 「每块都看」是唯一同时吃得下两种形状的写法。
        chunk_usage = _as_dict(getattr(chunk, "usage", None))
        if chunk_usage:
            usage = chunk_usage

        for choice in getattr(chunk, "choices", None) or []:
            delta = getattr(choice, "delta", None)
            if delta is not None:
                text = getattr(delta, "content", None)
                if text:
                    parts.append(text)
                    if on_delta is not None:
                        on_delta(text)
                # reasoning_content（DeepSeek 思考模式）**刻意不并进 content**：
                # 并进去等于把思考过程当答案发回给模型
                for frag in getattr(delta, "tool_calls", None) or []:
                    _merge_fragment(frag, calls, order)
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

    return StreamedResponse(
        content="".join(parts) or None,
        # None 而不是空列表：loop 用 `if not msg.tool_calls` 判终止没差别，
        # 但空数组会被原样写进 assistant_entry，把下一轮请求的形状弄脏
        tool_calls=[calls[i] for i in order] or None,
        finish_reason=finish_reason,
        usage=usage,
    )


def _merge_fragment(frag, calls: Dict[int, StreamedToolCall], order: List[int]) -> None:
    """按 `index` 归并，**不按 id**：`id` 与 `name` 只在该 index 的首块出现（实测），
    按 id 归并会把后续分片当成一堆没有 id 的新调用。

    `arguments` 只做字符串累加，**中途绝不解析**——实测 `{"city": "北京"}` 这 16 个字符
    分了 9 块发，拿任何中间态去 `json.loads` 都会炸，且炸点取决于分块位置。
    """
    index = getattr(frag, "index", None)
    if index is None:
        index = 0
    if index not in calls:
        calls[index] = StreamedToolCall(function=_Function())
        order.append(index)
    call = calls[index]
    if getattr(frag, "id", None):
        call.id = frag.id
    fn = getattr(frag, "function", None)
    if fn is not None:
        if getattr(fn, "name", None):
            call.function.name = fn.name
        if getattr(fn, "arguments", None):
            call.function.arguments += fn.arguments


def _as_dict(usage) -> dict:
    """与 `compaction.usage_fields` 同款的三条退化路径（pydantic / dict / namespace）。
    只透传不归一化——归一化会丢掉 DeepSeek 专有的 prompt_cache_hit/miss_tokens。"""
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return dict(usage)
    return {k: v for k, v in vars(usage).items() if not k.startswith("_")}
