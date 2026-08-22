"""把两个 JSONL 合并成「回合时间线」：分组、配对、求和。

**唯一一处 turn 分组逻辑**。前端不重复实现——同一套分组写两遍（Python 一遍、JS 一遍）
必然漂移，而本地文件解析是毫秒级的，页面重拉一次全量比维护两份便宜（plan T7 决定 1）。

读两个文件：
- `<X>.jsonl`        审计流：system / user / assistant / tool / usage
- `<X>.events.jsonl` 观测流：harness 事件（feature 17 T1 起才有，老会话没有）

两者按 `ts` 归并。纯函数（路径进、dict 出），所以离线可测，server 只做透传。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _read_jsonl(path: Path) -> "tuple[list, int]":
    """返回 (记录列表, 跳过的坏行数)。

    **绝不因一行坏拒绝整个文件**：进程被杀会留下半行 JSONL，而「出过一次事故就
    再也看不了这次会话」是不能接受的。跳过多少行如实报出去，页面显示计数。
    """
    if not path.exists():
        return [], 0
    rows, skipped = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            skipped += 1
    return rows, skipped


def events_path_for(session_path: Path) -> Path:
    return session_path.with_suffix(".events.jsonl")


def _kind_of(record: dict) -> str:
    """审计流混用两套判别字段（消息用 `role`、其余用 `type`）——这是已知的形状债
    （需求池 2026-08-10「CC 的 type 是顶层唯一判别式」那条）。这里统一收口，
    别让每个消费者各写一遍 `r.get('type', r.get('role'))`。
    """
    return record.get("type") or record.get("role") or "?"


# 观测流里与审计流**说同一件事**的三个事件。各画一行是重影，所以不单独成步：
# ToolStart/ToolEnd 合并进 tool 步骤（它们带着审计流没有的精确耗时与 is_error），
# AssistantMessage 直接丢（内容与 assistant 记录逐字相同）。
_MIRRORED_EVENTS = {"ToolStart", "ToolEnd", "AssistantMessage"}


def _new_turn(user: str, ts: float, starts: bool) -> dict:
    # `closed` 是内部账：结尾计算 unfinished 时才用得上，返回前会删掉
    # 三个「加起来有意义」的数（用户 2026-08-13 指出原来那个 in 之和没有意义：
    # 缓存命中便宜 50 倍，混在一起既不是钱也不是上下文大小）：
    #   context = **末步**的输入量（取最后一个，不是求和）→ 离窗口上限还有多远
    #   miss    = 未命中输入之和（不重叠，真正贵的那部分）
    #   tokens_out = 输出之和（每次都是新生成的，不重叠，且输出从不打折）
    # tokens_in / cached 仍保留在载荷里（原始账，供别处用），但页面不再当「计费」显示。
    return {"user": user, "ts": ts, "steps": [], "unfinished": False, "closed": False,
            "starts_conversation": starts, "tokens_in": 0, "tokens_out": 0,
            "cached": 0, "miss": 0, "context": 0, "ms": None}


def _tool_calls_of(record: dict) -> list:
    """assistant.tool_calls → 扁平的 {id, name, args}。

    `arguments` 是**字符串**（provider 就这么发的），解析失败时原样留着 raw——
    真实轨迹里出现过畸形 JSON，吞掉会让页面显示一个空参数表却说不出为什么。
    """
    out = []
    for call in record.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw = fn.get("arguments") or ""
        try:
            args = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            args = {}
        out.append({"id": call.get("id", ""), "name": fn.get("name", "?"),
                    "args": args, "raw": raw, "pending": True})
    return out


def _normalize_v1(rows: list) -> list:
    """v1 会话（feature 24：首行 header + 信封 + 消息嵌套）归一化回扁平形状——
    分组逻辑不用知道格式换过。扁平旧行原样透传（历史文件与手写夹具都还是它）。"""
    out = []
    for r in rows:
        if r.get("type") == "session":
            continue                       # header 不是时间线的一步
        if r.get("type") == "message" and isinstance(r.get("message"), dict):
            flat = dict(r["message"])
            flat["ts"] = r.get("ts")
            out.append(flat)
        else:
            out.append(r)
    return out


def load_flow(session_path: Path) -> dict:
    """一次会话的完整时间线。文件不存在/为空都不是错误——返回空 turns。"""
    session_path = Path(session_path)
    rows, skipped = _read_jsonl(session_path)
    rows = _normalize_v1(rows)
    events, ev_skipped = _read_jsonl(events_path_for(session_path))
    has_events = events_path_for(session_path).exists()

    for e in events:
        e["_is_event"] = True
    merged = sorted(rows + events, key=lambda r: r.get("ts") or 0.0)

    system: Optional[str] = None
    turns: list = []
    current: Optional[dict] = None
    pending_llm: Optional[dict] = None      # usage 先落、assistant 后落，这里等着合并
    by_call_id: dict = {}                   # tool_call_id → 它所属的 llm 步骤
    tool_spans: dict = {}                   # tool_call_id → ToolStart/ToolEnd 的精确区间
    owner_ts_of: dict = {}                  # tool_call_id → 发出它的那条 assistant 的 ts
    next_starts_conversation = True         # 第一个 turn 天然是新对话的开始

    def close(turn: dict) -> None:
        if turn["steps"]:
            turn["ms"] = int((turn["steps"][-1]["ts"] - turn["ts"]) * 1000)

    for record in merged:
        ts = record.get("ts") or 0.0

        if record.get("_is_event"):
            name = record.get("event")
            if name in _MIRRORED_EVENTS:
                if name == "ToolStart":
                    tool_spans.setdefault(record.get("tool_call_id"), {})["start"] = ts
                elif name == "ToolEnd":
                    span = tool_spans.setdefault(record.get("tool_call_id"), {})
                    span["end"] = ts
                    span["is_error"] = bool(record.get("is_error"))
                continue
            if name == "ConversationCleared":
                # 标在**下一个** turn 头上：前端要用它画分隔线，埋进上一个 turn
                # 的步骤里就画不到两段之间
                next_starts_conversation = True
                continue
            if current is not None:
                # 载荷整体放 `data`，**不平铺**：`PermissionDecided` 自己就有个 `kind`
                # 字段（allow/deny），平铺会被步骤判别字段 `kind`（llm/tool/event）
                # 覆盖——页面上显示成「bash → event」。给单个事件开特例挡不住下一个
                # 撞名的字段，套一层才是结构上不可能再撞（浏览器里看出来的，T7）。
                data = {k: v for k, v in record.items()
                        if k not in ("_is_event", "event", "ts")}
                current["steps"].append({"kind": "event", "event": name,
                                         "ts": ts, "data": data})
            continue

        kind = _kind_of(record)

        if kind == "system":
            system = record.get("content")
            continue

        if kind == "user":
            if current is not None:
                close(current)
            current = _new_turn(record.get("content") or "", ts, next_starts_conversation)
            next_starts_conversation = False
            pending_llm, by_call_id = None, {}
            turns.append(current)
            continue

        if current is None:
            # 会话以非 user 记录开头（截断的文件、或 once 模式没落 user 行）：
            # 造一个无名 turn 收留它们，丢掉等于让这些步骤凭空消失
            current = _new_turn("", ts, next_starts_conversation)
            next_starts_conversation = False
            turns.append(current)

        if kind == "usage":
            details = record.get("prompt_tokens_details") or {}
            prompt = record.get("prompt_tokens", 0)
            hit = (record.get("prompt_cache_hit_tokens")
                   or details.get("cached_tokens") or 0)
            # DeepSeek 直接给 miss；别家不给就减出来——算得出来就别显示成 0，
            # 0 会被读成「全命中」
            miss = record.get("prompt_cache_miss_tokens")
            if miss is None:
                miss = max(prompt - hit, 0)
            pending_llm = {
                "kind": "llm", "ts": ts, "step": record.get("step"),
                "model": record.get("model", ""),
                "in": prompt,
                "out": record.get("completion_tokens", 0),
                # provider 同时给两套缓存口径（实测夹具里两个都在），取到哪个算哪个
                "cached": hit,
                "miss": miss,
                "content": None, "tool_calls": [],
            }
            current["steps"].append(pending_llm)
            current["tokens_in"] += pending_llm["in"]
            current["tokens_out"] += pending_llm["out"]
            current["cached"] += pending_llm["cached"]
            current["miss"] += pending_llm["miss"]
            current["context"] = pending_llm["in"]     # 覆盖而非累加：要的是末步的值
            continue

        if kind == "assistant":
            calls = _tool_calls_of(record)
            if pending_llm is not None:
                pending_llm["content"] = record.get("content")
                pending_llm["tool_calls"] = calls
                owner = pending_llm
            else:
                # 没有配套 usage（中断、或 provider 没回 usage）：仍要看得见这条消息
                owner = {"kind": "llm", "ts": ts, "step": None, "model": "",
                         "in": 0, "out": 0, "cached": 0,
                         "content": record.get("content"), "tool_calls": calls}
                current["steps"].append(owner)
            for call in calls:
                by_call_id[call["id"]] = call
                owner_ts_of[call["id"]] = ts
            pending_llm = None
            if not calls:
                current["closed"] = True        # 不再调工具 = 这一轮说完了
            continue

        if kind == "tool":
            call = by_call_id.get(record.get("tool_call_id"))
            if call is not None:
                call["pending"] = False
            call_id = record.get("tool_call_id", "")
            span = tool_spans.get(call_id, {})
            if "start" in span and "end" in span:
                ms, approx = int((span["end"] - span["start"]) * 1000), False
            else:
                # 没有观测流时的近似：「模型发出调用 → 结果落盘」。
                # **并发批里这是偏大的**（第二个工具的区间含第一个），故标 approx，
                # 由页面说明白——显示一个不知来路的数字比不显示更糟。
                owner_ts = owner_ts_of.get(call_id)
                ms = int((ts - owner_ts) * 1000) if owner_ts is not None else None
                approx = ms is not None
            current["steps"].append({
                "kind": "tool", "ts": ts,
                "id": call_id,
                "name": (call or {}).get("name", "?"),
                "args": (call or {}).get("args", {}),
                "result": record.get("content") or "",
                "ms": ms, "ms_approx": approx,
                "is_error": span.get("is_error", False),
            })
            continue

    for turn in turns:
        close(turn)
        # 「未完成」= **真的开了工却没收尾**，不是「没有收尾的 assistant」。
        # 后者会把 `!命令` 的记录全判成未完成——它形状上就是一条 role=user
        # （内容是命令与输出），不经模型，永远等不到 assistant。8 个真实会话里
        # 有 3 个是这种，判据不改的话这个信号当场从证据退化成噪音（devlog T4）。
        # 不靠匹配「我执行了命令」那句话：用户自己就能原样打出这几个字。
        started = any(s["kind"] == "llm" for s in turn["steps"])
        turn["unfinished"] = started and not turn["closed"]
        del turn["closed"]

    return {
        "session": session_path.name,
        "system": system,
        "has_events": has_events,
        "skipped": skipped + ev_skipped,
        "turns": turns,
    }
