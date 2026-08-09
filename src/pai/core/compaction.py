"""上下文压缩的地基三件套：token 秤、警戒线、对话拍平机。

阶段 1 的第 1-2 步。全是纯函数——不联网、不读文件、不改 messages——
这样第 3 步 find_cut_point 和最终的自动压缩才有可测的立足点。

刻意还没有的：find_cut_point（在哪下刀）、summarize（调模型摘要）、compact（把两者接起来）。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

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

# 只认 OpenAI 兼容协议里这四种 role。未知 role 一律记 0 且不拍平：
# 与其猜一个数，不如让它在下游明显缺失。
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


@dataclass
class AnchorBook:
    """真实 usage 锚点簿（D#32）：单锚只够判「该不该压」，切点计算需要完整列表。

    entries[i] = (锚覆盖到的 message 下标, 累计真实 token)；相邻差值 = 该轮真实成本。
    压缩会改写历史，必须 reset()——锚定法假设 append-only。
    """

    entries: list[tuple[int, int]] = field(default_factory=list)

    def record(self, message_index: int, real_tokens: int) -> None:
        self.entries.append((message_index, real_tokens))

    def latest(self) -> tuple[int | None, int]:
        if not self.entries:
            return None, 0
        index, tokens = self.entries[-1]
        return tokens, index

    def reset(self) -> None:
        self.entries.clear()


def estimate_tokens(message: Mapping[str, object]) -> int:
    """估一条消息的 token 数，中英文分别按官方系数计。

    计入 content 与每个 tool_call 的 name + arguments——arguments 是 JSON 字符串，
    一次 write_file 就可能几千字符，漏算它整条轨迹会低估一个数量级。
    不计 id / tool_call_id：它们是定长管道噪音，占比极小，计入只会让心智模型变复杂。
    """
    if message.get("role") not in KNOWN_ROLES:
        return 0

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
    1 = 无可压（锚不足 / 预算吞下全部历史），调用方按 spec 裁决走「不压 + 警告」。
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
