"""任务评测计数；未知不伪装成 0，完成与产物正确分列。"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import statistics
from typing import Optional


def _rows(path: Optional[Path]) -> Optional[list[dict]]:
    if path is None or not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("轨迹记录必须是对象")
    return rows


def measure(session: Optional[Path], events: Optional[Path]) -> dict:
    rows = _rows(session)
    trace = _rows(events)
    attempts: Optional[int] = None
    requests = 0
    usages: list[dict] = []
    side = False
    if rows is not None:
        if not rows or rows[0].get("type") != "session" or rows[0].get("version") != 1:
            raise ValueError("需要 session v1")
        attempts = 0
        for r in rows[1:]:
            if r.get("type") == "message":
                msg = r["message"]
                if msg.get("role") == "assistant":
                    requests += 1
                    attempts += len(msg.get("tool_calls") or [])
            elif r.get("type") == "usage":
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    value = r.get(key)
                    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                        raise ValueError("非法 usage: " + key)
                usages.append(r)
            elif r.get("type") == "compaction":
                side = True
            else:
                raise ValueError("未知 session 条目")
    def total(key: str, subkey: Optional[str] = None) -> Optional[int]:
        values = [(u.get(key) or {}).get(subkey) if subkey else u.get(key) for u in usages]
        return sum(values) if values and all(isinstance(v, int) and v >= 0 for v in values) else None
    tokens = {"prompt": total("prompt_tokens"), "completion": total("completion_tokens"),
              "total": total("total_tokens"), "reasoning": total("completion_tokens_details", "reasoning_tokens"),
              "cacheHit": total("prompt_cache_hit_tokens")}
    complete = bool(requests and len(usages) == requests
                    and all(tokens[k] is not None for k in ("prompt", "completion", "total")) and not side)
    last = "unknown"
    if trace is not None:
        for event in trace:
            if event.get("event") == "AgentEnd":
                last = event["reason"]
            if event.get("event") in ("Compacted", "RecallInjected", "RecallFailed"):
                complete = False
    return {"tokens": tokens, "usageCoverage": "complete" if complete else "incomplete",
            "requestsWithUsage": len(usages), "assistantResponses": requests,
            "toolAttempts": attempts,
            "toolsStarted": sum(r.get("event") == "ToolStart" for r in trace) if trace is not None else None,
            "permissionDenials": sum(r.get("event") == "PermissionDecided" and r.get("kind") == "deny" for r in trace) if trace is not None else None,
            "agentEnd": last, "humanPrompts": None, "humanPromptsReason": "once has no human asker"}


def _stats(values: list[float]) -> dict:
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def summarize(records: list[dict]) -> dict:
    def successes(rows: list[dict]) -> int:
        return sum(r.get("execution") == "completed" and r.get("agentEnd") == "final"
                   and r.get("grade", {}).get("status") == "pass" for r in rows)
    by_case: dict = {}
    for case in sorted({r["case"] for r in records}):
        rows = [r for r in records if r["case"] == case]
        by_case[case] = {"planned": len(rows), "completeSuccesses": successes(rows),
                        "productPasses": sum(r.get("grade", {}).get("status") == "pass" for r in rows),
                        "completeSuccessRate": successes(rows) / len(rows),
                        "productPassRate": sum(r.get("grade", {}).get("status") == "pass" for r in rows) / len(rows),
                        "durationMs": _stats([r["durationMs"] for r in rows if "durationMs" in r]),
                        "totalTokens": _stats([r["metrics"]["tokens"]["total"] for r in rows
                            if r.get("metrics", {}).get("usageCoverage") == "complete"
                            and r["metrics"]["tokens"].get("total") is not None])}
    return {"planned": len(records), "started": sum(r.get("execution") != "not_started" for r in records),
            "completeSuccesses": successes(records),
            "completeSuccessRate": successes(records) / len(records) if records else None,
            "productPassRate": sum(r.get("grade", {}).get("status") == "pass" for r in records) / len(records) if records else None,
            "productPasses": sum(r.get("grade", {}).get("status") == "pass" for r in records),
            "executionCounts": dict(Counter(r["execution"] for r in records)),
            "agentEndCounts": dict(Counter(r.get("agentEnd", "unknown") for r in records)),
            "gradingCounts": dict(Counter(r.get("grade", {}).get("status", "unavailable") for r in records)),
            "byCase": by_case}
