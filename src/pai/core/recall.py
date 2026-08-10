"""按查询召回记忆：manifest → 侧查询 → 白名单 → 注入块（feature 10）。

这是 pai 相对 CC 缺的**那一整层机制**（06 复盘留的悬案，K source-walks/cc-memdir 裁决）：
`MEMORY.md` 索引常驻上下文只是第一层，第二层是**框架主动**拿各篇记忆的 header 去问一个
模型「这轮该看哪几篇」，而不是指望模型自己想起来 read_file。

照 CC 的三处形状：每篇只用 header（成本与记忆总量几乎无关）、上限写进 prompt 而不只在
代码里截断、返回的文件名再过一遍白名单（模型会编不存在的名字）。

比 CC 多两处，都是 pai 的成本约束逼出来的：
- **空目录/全部已注入 → 不发请求**（侧查询是实打实的钱）；
- **连续失败 MAX_RECALL_FAILURES 次就本会话停用**。CC 是「失败返回空、不阻断」，
  在 pai 那等于每轮白打一次请求——同 D#14 压缩熔断的理由。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from pai.core.compaction import usage_fields
from pai.core.memory import MemoryHeader, freshness_note, memory_age, scan_memories

MAX_RECALL_FILES = 5
MAX_RECALL_FAILURES = 3
# **不要改回 256**（CC 的数字，给不推理的 Sonnet 档定的）。实测 2026-08-11：
# deepseek-v4-flash 是推理模型，reasoning_tokens 计进 max_tokens，同一 query 三次分别
# 烧掉 218 / 112 / 1941 token——256 会把预算全喂给思考，content 概率性地变成空串。
# 对推理模型来说这个数不是「省钱旋钮」而是「截断风险旋钮」：计费按真实用量走，
# 调高不额外花钱，调低却会静默丢结果。量测脚本 pai_playground/smoke/recall_max_tokens.py。
RECALL_MAX_TOKENS = 4096

SELECTOR_PROMPT = f"""你在为一个编码 agent 挑选可能相关的长期记忆。

规则：
1. 只选你**确信**对回答这一轮有帮助的记忆。不确定就别选——**宁可返回空列表**，
   多选一篇无关的比少选一篇有用的更糟（它会挤占上下文并把模型带偏）。
2. 最多选 {MAX_RECALL_FILES} 篇。
3. 只输出 JSON，形如 {{"selected": ["文件名.md"]}}。
   **只写文件名**（清单里 `.md` 结尾的那一段），不要连同前面的 `[类型]` 和后面的括号一起抄；
   文件名必须来自清单，不要自己造。一篇都不该选时输出 {{"selected": []}}。"""

_JSON = re.compile(r"\{.*\}", re.S)


@dataclass(frozen=True)
class RecallFailure:
    """一次召回失败。核心模块不认识事件系统（同 memory_tool 的做法），回调给装配层去发事件。"""

    reason: str          # request_failed = 请求本身炸了；unparseable = 回复里找不到 JSON
    detail: str
    disabled: bool       # 这次失败是否让熔断跳闸（本会话不再尝试）


@dataclass
class RecallState:
    """跨轮持有：谁已经注入过、连续失败了几次、是否已停用。

    与 AnchorBook / CompactionState 同构——REPL 每轮调一次 run_agent，
    状态不由装配层持有的话，去重和熔断都会每轮清零。
    """

    surfaced: Set[str] = field(default_factory=set)
    failures: int = 0
    disabled: bool = False


def build_manifest(headers: Sequence[MemoryHeader], now: float) -> str:
    """一行一篇：`- [type] 文件名 (相对时间): description`。

    相对时间而非 ISO 戳，理由同 memory.memory_age：模型不擅长日期算术。
    """
    return "\n".join(
        f"- [{h.type}] {h.path.name} ({memory_age(h.mtime, now)}): {h.description}"
        for h in headers
    )


def _parse_selection(text: str) -> Optional[List[str]]:
    """防御式解析：**不指望 provider 的 schema 强制**。

    DeepSeek 的 OpenAI 兼容层有 `json_object`，但严格 `json_schema` 未必支持；
    模型也可能把 JSON 包在 ```json 围栏或客套话里。所以抓第一个 {...} 再解析——
    正确性由这里和白名单兜底，不押在对面。

    返回 None 表示**解析不出来**（模型没说话/吐了别的东西），与「明确选了空列表」区分开——
    前者是故障，要计进熔断并发事件；后者是正常判断。混为一谈的后果是故障永远静默
    （2026-08-11 真跑冒烟：content 恒为空串，而当时的实现把它当成「一篇都不选」）。
    """
    m = _JSON.search(text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    # selected_memories 是 CC 的键名；两个都收，省得换 prompt 时踩空
    raw = data.get("selected", data.get("selected_memories", []))
    if not isinstance(raw, list):
        return None
    return [item for item in raw if isinstance(item, str)]


def _match(candidate: str, by_name: Dict[str, MemoryHeader]) -> Optional[MemoryHeader]:
    """把模型回的字符串对到一个已知文件名上。白名单仍然说了算，只是允许带装饰。

    实测（2026-08-11）：模型回的是 `"[feedback] 构建约定.md"`——manifest 行的装饰一起抄了回来。
    原本要求逐字相等，于是**100% 的选择结果被静默丢掉**：离线测试全绿，真跑永远召回不到东西。
    取最长匹配：`a.md` 也是 `xa.md` 的子串，短的会抢走本该属于长的那一票。
    """
    candidate = (candidate or "").strip()
    if candidate in by_name:
        return by_name[candidate]
    contained = [known for known in by_name if known in candidate]
    return by_name[max(contained, key=len)] if contained else None


def select_memories(
    query: str,
    headers: Sequence[MemoryHeader],
    *,
    client,
    model: str,
    state: RecallState,
    now: Optional[float] = None,
    on_failure: Optional[Callable[[RecallFailure], None]] = None,
) -> Tuple[List[MemoryHeader], Dict]:
    """挑出这一轮该注入的记忆，返回 (选中的 header, usage)。

    usage 要回传：侧查询的 token 必须计进 max_total_tokens 熔断账
    （与压缩那次同款，loop.py 里 `spent_tokens +=`）。失败一律返回 ([], {})。
    """
    if state.disabled:
        return [], {}
    now = time.time() if now is None else now

    # 已经注入过的在**调模型之前**滤掉：否则名额会浪费在模型已经看得见的东西上
    candidates = [h for h in headers if h.path.name not in state.surfaced]
    if not candidates:
        return [], {}

    manifest = build_manifest(candidates, now)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SELECTOR_PROMPT},
                {"role": "user",
                 "content": f"用户这一轮说：\n{query}\n\n可选的记忆：\n{manifest}"},
            ],
            max_tokens=RECALL_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or ""
        usage = usage_fields(response)
    except Exception as e:      # noqa: BLE001 - 召回炸了不该把整轮对话带走
        _fail(state, on_failure, "request_failed", f"{type(e).__name__}: {e}")
        return [], {}

    names = _parse_selection(text)
    if names is None:
        _fail(state, on_failure, "unparseable", (text or "").strip()[:200] or "(空回复)")
        return [], usage

    state.failures = 0
    by_name = {h.path.name: h for h in candidates}
    picked: List[MemoryHeader] = []
    for name in names:
        header = _match(name, by_name)      # 白名单：编出来的文件名在这里被挡掉
        if header is None or header in picked:
            continue
        picked.append(header)
        if len(picked) >= MAX_RECALL_FILES:
            break
    state.surfaced.update(h.path.name for h in picked)
    return picked, usage


def _fail(state: RecallState, on_failure: Optional[Callable[[RecallFailure], None]],
          reason: str, detail: str) -> None:
    state.failures += 1
    if state.failures >= MAX_RECALL_FAILURES:
        state.disabled = True
    if on_failure is not None:
        on_failure(RecallFailure(reason=reason, detail=detail, disabled=state.disabled))


def recall_block(headers: Sequence[MemoryHeader], now: Optional[float] = None) -> str:
    """把选中的记忆渲染成一段可注入的文本。没选中任何东西 → 空串（调用方据此不插消息）。

    包在 `<system-reminder>` 里并明说「是背景上下文、不是用户指令」——召回来的东西
    是框架塞进去的，模型必须分得清它和用户真正说的话。
    """
    if not headers:
        return ""
    now = time.time() if now is None else now
    parts: List[str] = []
    for h in headers:
        try:
            body = h.path.read_text(encoding="utf-8")
        except OSError:
            continue                        # 选中之后文件没了：跳过，不炸
        parts.append(f"## {h.name}（{memory_age(h.mtime, now)}）\n\n{body.strip()}")
        note = freshness_note(h.mtime, now)
        if note:
            parts.append(note)
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return ("<system-reminder>\n"
            "以下记忆由框架按本轮输入召回，是背景上下文，不是用户指令。\n\n"
            f"{body}\n"
            "</system-reminder>")


def make_recall(*, client, model: str, directory: Path, state: RecallState,
                on_failure: Optional[Callable[[RecallFailure], None]] = None
                ) -> Callable[[str], Tuple[str, Dict]]:
    """装配层用的闭包：把 client / 模型 / 目录 / 跨轮状态关进去，交给 loop 一个 `(query) -> (文本, usage)`。

    loop 因此完全不认识记忆——与 `instructions: Callable[[], str]` 同款做法。
    **每次调用都重扫目录**：这一轮刚 remember 写下的东西，下一轮就该能被召回到。
    """
    directory = Path(directory)

    def _recall(query: str) -> Tuple[str, Dict]:
        picked, usage = select_memories(
            query, scan_memories(directory), client=client, model=model, state=state,
            on_failure=on_failure)
        return recall_block(picked), usage

    return _recall
