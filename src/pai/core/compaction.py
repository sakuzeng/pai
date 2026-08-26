"""上下文压缩全链路：token 秤、警戒线、真实 usage 锚簿、切点、摘要、重建、熔断。

阶段 1 全部落地：estimate_tokens/context_tokens 做估算与锚定，should_compact 是警戒线，
AnchorBook/find_cut_point 按真实 usage 差值定切点，summarize/compact 负责摘要与重建，
CompactionState/verify_compaction 是压缩失败熔断器（D#34）。loop.py 负责接线触发。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, NamedTuple, Optional, Sequence

from pai.core.protocols import ChatClient

# 官方换算系数，来源 refs/deepseek-api/quick_start/token_usage.md：
# "1 个英文字符 ≈ 0.3 个 token""1 个中文字符 ≈ 0.6 个 token"。
# 不用通用的 chars/4（=0.25）：它对英文低估 17%、对中文低估 2.4 倍，而低估会让压缩来得太晚。
# 仍是估算——官方同句写明"每一次实际处理 token 数量以模型返回为准"，
# 精确值等 usage 回传接上后再校准（官方还提供离线 tokenizer，见同一文档）。
TOKENS_PER_CJK_CHAR = 0.6
TOKENS_PER_ASCII_CHAR = 0.3

# 判为"中文侧"的码位区间。含全角标点（U+3000-303F 的，。、《》与 U+FF00-FFEF 的全角形式）——
# 中文正文里它们占比不低，划错会系统性偏低。
CJK_RANGES = (
    (0x3000, 0x303F),  # CJK 标点
    (0x3400, 0x4DBF),  # 扩展 A
    (0x4E00, 0x9FFF),  # 基本汉字
    (0xF900, 0xFAFF),  # 兼容汉字
    (0xFF00, 0xFFEF),  # 全角形式
)

# 单个字段拍平时的截断长度。挡的是一条 read_file 或 bash 结果吃掉整个摘要预算。
MAX_CHARS_PER_FIELD = 5000

# OpenAI 兼容协议里的四种 role。它只管一件事：拍平时跳过不认识的 role
# （不认识的东西不塞进摘要请求）。
# 秤不看它——未知 role 照常按 content 估（R#5 裁决 2026-08-25，推翻 D#8 的「记 0」）：
# 记 0 是最极端的低估，而 D#6 定过低估是唯一会炸窗口的方向。
KNOWN_ROLES = frozenset({"system", "user", "assistant", "tool"})


@dataclass(frozen=True)
class CompactionSettings:
    """reserve_tokens 是绝对预留量，不是比例；enabled=False 时永不自动压（调试/评测用）。

    16384 覆盖的是「压缩后下一轮还能干活」所需的空间：一轮回复 + 几个工具结果。
    用绝对值是因为这个需求与窗口多大无关——百分比阈值在大窗口上会白白早压
    （见 docs/dev/decisions.md 第 13 条）。

    注意它不是按模型输出上限算的：deepseek-v4-flash 输出上限 384K，
    但摘要实际长度远小于此（CC 统计其摘要 p99.99 为 17,387 token）。
    这个数目前无实测依据，待 usage 落盘后用真实摘要长度校准。

    keep_recent_tokens 照 pi，与 reserve 同样待实测校准。
    """

    reserve_tokens: int = 16384
    enabled: bool = True
    keep_recent_tokens: int = 20000


class Anchor(NamedTuple):
    """一个锚点：锚覆盖到的 message 下标 + 该下标处的累计真实 token。

    具名而不是裸 tuple（02 终审 Minor#6 的落点）：`latest()` 曾返回
    `(tokens, index)` 而 `entries` 存 `(index, tokens)`，两处序相反，
    位置解包的调用方记反了不会有任何东西变红。按名取值之后，
    序不再是调用方要背下来的隐式契约；仍是 tuple，`find_cut_point`
    那样的位置解包与既有断言照常工作。
    """

    index: Optional[int]
    tokens: int


@dataclass
class AnchorBook:
    """真实 usage 锚点簿（D#32）：单锚只够判「该不该压」，切点计算需要完整列表。

    entries[i] = Anchor(锚覆盖到的 message 下标, 累计真实 token)；
    相邻差值 = 该轮真实成本。
    压缩会改写历史，必须 reset()——锚定法假设 append-only。
    """

    entries: list[Anchor] = field(default_factory=list)

    def record(self, message_index: int, real_tokens: int) -> None:
        self.entries.append(Anchor(message_index, real_tokens))

    def latest(self) -> Anchor:
        if not self.entries:
            return Anchor(None, 0)
        return self.entries[-1]

    def reset(self) -> None:
        self.entries.clear()


def estimate_tokens(message: Mapping[str, object]) -> int:
    """估一条消息的 token 数，中英文分别按官方系数计。

    计入 content 与每个 tool_call 的 name + arguments——arguments 是 JSON 字符串，
    一次 write_file 就可能几千字符，漏算它整条轨迹会低估一个数量级。
    不计 id / tool_call_id：它们是定长管道噪音，占比极小，计入只会让心智模型变复杂。

    role 一概不看（R#5 裁决 2026-08-25）：不认识的 role 也真在上下文里占位置，
    记 0 是最极端的低估，与 D#6「低估是唯一会炸窗口的方向」直接冲突。
    宁可高估。拍平那边照旧跳过未知 role——那问的是另一个问题（见 KNOWN_ROLES）。
    """
    # content 可能是 None：模型只发 tool_calls 不说话时，loop.py 就是这么落盘的。
    text = str(message.get("content") or "")
    for call in _tool_calls(message):
        fn = call.get("function") or {}
        text += str(fn.get("name") or "") + str(fn.get("arguments") or "")

    return math.ceil(_estimate_text_tokens(text))


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return any(lo <= code <= hi for lo, hi in CJK_RANGES)


def _estimate_text_tokens(text: str) -> float:
    cjk = sum(1 for c in text if _is_cjk(c))
    return cjk * TOKENS_PER_CJK_CHAR + (len(text) - cjk) * TOKENS_PER_ASCII_CHAR


def estimate_conversation_tokens(messages: Iterable[Mapping[str, object]]) -> int:
    return sum(estimate_tokens(m) for m in messages)


def estimate_request_tokens(
    messages: Iterable[Mapping[str, object]],
    tool_schemas: Iterable[Mapping[str, object]] | None = None,
) -> int:
    """估一次请求的输入规模，含工具 schema。

    provider 回传的 prompt_tokens 算的是整个请求，工具 schema 也在里面。只估 messages
    会系统性低估一个近似恒定的量（pai 现有四个工具约几百 token），对话越短这个偏差占比越大。
    要和 window 比大小、要和 usage 对账，比的都该是这个数，不是 estimate_conversation_tokens。
    """
    total = estimate_conversation_tokens(messages)
    if tool_schemas:
        total += math.ceil(
            _estimate_text_tokens(json.dumps(list(tool_schemas), ensure_ascii=False))
        )
    return total


def context_tokens(
    messages: Sequence[Mapping[str, object]],
    tool_schemas: Iterable[Mapping[str, object]] | None = None,
    *,
    anchor: int | None = None,
    anchor_index: int = 0,
) -> int:
    """当前上下文有多大——有 provider 回传的真实值就以它为锚，只估锚之后新增的部分。

    anchor 是一个已知精确的 token 数，覆盖 messages[:anchor_index] 与工具 schema；
    调用方通常传「上一步的 prompt_tokens + completion_tokens」，因为紧随其后的那条
    assistant 消息，其真实 token 数就是 completion_tokens——白送的精确值。

    这样做的意义不是让估算变准，而是**让它只作用在很短的尾部**：本地估算对 DeepSeek
    实测系统性低估约 1.5 倍（见 docs/dev/devlog.md），这个倍率乘在几十个 token 上无害，
    乘在几十万上就是灾难。首次请求没有锚可依，那时上下文才几百 token，离阈值差几个数量级。

    与 estimate_request_tokens 的分工：这个函数管"该不该压"（绝对值必须准），
    estimate_tokens 管"在哪下刀"（只需相对准，均匀偏差不影响切点）。
    """
    if anchor is None:
        return estimate_request_tokens(messages, tool_schemas)
    return anchor + estimate_conversation_tokens(messages[anchor_index:])


def should_compact(tokens: int, window: int, settings: CompactionSettings) -> bool:
    """严格大于才压：正好压线不动手，避免在阈值上反复横跳。

    已知退化情形：window <= reserve_tokens 时恒为 True，此时压缩救不了场。
    防无限压缩循环是上层熔断器的职责（随自动压缩实现），不在这里挡——
    这个函数只负责如实回答"超没超线"。
    """
    if not settings.enabled:
        return False
    return tokens > window - settings.reserve_tokens


def find_cut_point(
    messages: Sequence[Mapping[str, object]],
    anchors: Sequence[tuple[int, int]],
    *,
    keep_recent_tokens: int = 20000,
) -> int:
    """在哪下刀（D#32）：从最新锚往回累计真实差值，够 keep_recent_tokens 即停。

    只在锚点边界下刀——真实成本只能按轮次反推，粒度天然对齐。返回保留段起点；
    1 = 无可压（锚不足两个 / keep_recent_tokens 吞下全部历史）。调用方按锚数分流：
    锚不足两个是压缩节奏里的正常一步，走静默进度；锚已够两个才是真无可压，才升级为警告。
    落点若是 tool 消息则前移，绝不让保留段以孤儿 tool_result 开头。
    """
    if len(anchors) < 2:
        return 1
    _, latest_total = anchors[-1]
    cut = 1
    for index, total in reversed(anchors[:-1]):
        if latest_total - total >= keep_recent_tokens:
            cut = index
            break
    while 0 < cut < len(messages) and messages[cut].get("role") == "tool":
        cut -= 1                       # 前移方向 = 多保留，宁多勿孤儿
    return max(cut, 1)


def keep_recent_shortfall(anchors: Sequence[Anchor], keep_recent_tokens: int) -> int:
    """还差多少 token，历史才够长到切得动。0 = 差额不是原因（够长了）。

    `find_cut_point` 的门槛是「最新锚与某个更早的锚之间的真实差值 ≥ keep_recent」，
    所以能拿到的最大差值就是最新锚减最早锚。锚不足两个时一个差值都算不出来，
    如实返回整个门槛——返回 0 会被读成「够了」。

    存在的理由是 `/compact` 的提示语（TODO「压缩链路的可验证性」）：
    「无可压」三个字分不清「坏了」与「还没到量」，用户只能猜。
    """
    if len(anchors) < 2:
        return keep_recent_tokens
    span = anchors[-1].tokens - anchors[0].tokens
    return max(0, keep_recent_tokens - span)


def serialize_conversation(
    messages: Iterable[Mapping[str, object]],
    max_chars: int = MAX_CHARS_PER_FIELD,
) -> str:
    """把消息列表拍平成纯文本，喂给摘要模型。

    保留 role、工具名、参数、tool_call_id 的对应关系——摘要模型要能看出
    "谁调了什么、结果是啥、哪一步失败过"。超长字段就地截断并标注截掉了多少，
    让模型知道自己看到的是残缺内容。
    """
    lines: list[str] = []
    for message in messages:
        role = message.get("role")
        if role not in KNOWN_ROLES:
            continue

        content = message.get("content") or ""
        if role == "tool":
            call_id = message.get("tool_call_id") or "?"
            lines.append(f"tool[{call_id}]: {_truncate(str(content), max_chars)}")
            continue

        if content:
            lines.append(f"{role}: {_truncate(str(content), max_chars)}")

        for call in _tool_calls(message):
            fn = call.get("function") or {}
            name = fn.get("name") or "?"
            args = _truncate(str(fn.get("arguments") or ""), max_chars)
            lines.append(f"{role}: [tool_call {call.get('id') or '?'}] {name}({args})")

    return "\n".join(lines)


def _tool_calls(message: Mapping[str, object]) -> list[Mapping[str, object]]:
    calls = message.get("tool_calls") or []
    return [c for c in calls if isinstance(c, Mapping)]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n[... {len(text) - max_chars} more characters truncated]"


SUMMARY_INSTRUCTIONS = (
    "你在为一段编码 agent 的对话历史写交接摘要，续任者只靠它接着干活。必须保留：\n"
    "1) 用户的请求与意图 2) 关键技术概念 3) 检查/修改过的文件与重要代码片段\n"
    "4) 出过的错误与修法 5) 未完成的待办 6) 当前正在做的事。\n"
    "只输出摘要正文，不要评论任务本身，更不要继续执行任务。"
)


def usage_fields(response: Any) -> dict:
    """取 provider 回传的 usage 字段；没有就返回空 dict。

    response 只能是 Any（R#14 的另一半）：非流式是 SDK 的响应对象、流式装配后是
    pai 自己的结构，各家 SDK 的类型也不通用——写死任何一个都是在说谎，
    所以这里全靠下面三条退化路径做防御性取值。

    只透传不归一化——归一化会丢掉 DeepSeek 专有的 prompt_cache_hit/miss_tokens，
    而那正是缓存命中率的唯一来源。
    SDK 回的是 pydantic 对象（非标字段也在里面），model_dump 拿得全；
    退化路径覆盖 dict 与 SimpleNamespace。
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return dict(usage)
    return {k: v for k, v in vars(usage).items() if not k.startswith("_")}


def summarize(
    messages: Sequence[Mapping[str, object]],
    *,
    client: ChatClient,
    model: str,
    style: str = "flat",
    instructions: str | None = None,
) -> tuple[str, dict]:
    """调模型生成摘要。style 由实测裁决默认值（spec 问 1）：flat=拍平，raw=原样发。

    不带 tools——摘要请求绝不该触发工具调用；这也是「继续干活」误解的第一道防线。
    """
    prompt = instructions or SUMMARY_INSTRUCTIONS
    if style == "flat":
        body = serialize_conversation(m for m in messages if m.get("role") != "system")
        request: list[dict] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"待摘要的对话记录：\n{body}"},
        ]
    elif style == "raw":
        request = [dict(m) for m in messages if m.get("role") != "system"]
        request.append({"role": "user", "content": f"停下手头任务。{prompt}\n现在输出上面全部对话的摘要。"})
    else:
        raise ValueError(f"未知 style: {style!r}（只认 flat / raw）")

    response = client.chat.completions.create(model=model, messages=request)
    text = response.choices[0].message.content or ""
    return text, usage_fields(response)


MAX_COMPACT_FAILURES = 3   # 对齐 CC（D#14）：没有熔断时真实事故是数千次连续失败


@dataclass
class CompactionState:
    """熔断状态机（D#34）：压缩后不立即判成败，等首次真实 usage 回传。"""

    failures: int = 0
    awaiting_verify: bool = False
    tripped: bool = False


def verify_compaction(
    prompt_tokens: int,
    window: int,
    settings: CompactionSettings,
    state: CompactionState,
) -> CompactionState:
    """压缩后首次真实 prompt_tokens 才是裁决依据——估算在此刻低估 33%，信它必炸（D#34）。"""
    still_over = prompt_tokens > window - settings.reserve_tokens
    failures = state.failures + 1 if still_over else 0
    return CompactionState(
        failures=failures,
        awaiting_verify=False,
        tripped=state.tripped or failures >= MAX_COMPACT_FAILURES,
    )


def compact(
    messages: Sequence[Mapping[str, object]],
    *,
    cut: int,
    client: ChatClient,
    model: str,
    style: str = "flat",
    instructions: str | None = None,
) -> tuple[list[dict], str, dict]:
    """切 + 摘 + 重建。调用方随后必须 anchors.reset() 并置 state.awaiting_verify。

    摘要消息用 user role：OpenAI 兼容协议下多条 system 支持度参差，user 前缀最稳。

    返回 (rebuilt, summary, usage)：usage 是摘要请求自己的真实用量，调用方必须把它并入
    max_total_tokens 预算与会话统计——摘要请求拍平重发近全窗口，是全系统最贵的单次请求，
    丢掉它的账会让预算熔断与会话统计都对不上实际花费。
    """
    summary, usage = summarize(
        messages[:cut], client=client, model=model, style=style, instructions=instructions
    )
    from pai.core.session import _summary_message

    rebuilt: list[dict] = [dict(messages[0])]
    # 包装文本的唯一出处在 session._summary_message——resume 重建要逐字一致
    rebuilt.append(_summary_message(summary))
    rebuilt.extend(dict(m) for m in messages[cut:])
    return rebuilt, summary, usage
