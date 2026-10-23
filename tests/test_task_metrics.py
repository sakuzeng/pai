from __future__ import annotations

import json
from pathlib import Path

import pytest

from pai.evals.task_metrics import measure, summarize

REAL = Path(__file__).resolve().parents[1] / "evals/fixtures/20260824-greeting-file.jsonl"


def jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows))
    return path


def test_metrics_from_committed_real_chinese_trajectory(tmp_path: Path) -> None:
    events = jsonl(tmp_path / "events.jsonl", [
        {"event":"ToolStart","name":"write_file"},
        {"event":"ToolStart","name":"read_file"},
        {"event":"AgentEnd","reason":"final"}])
    m = measure(REAL, events)
    assert m["tokens"]["total"] == 3338
    assert m["tokens"]["prompt"] == 3227
    assert m["tokens"]["completion"] == 111
    assert m["toolAttempts"] == 2
    assert m["toolsStarted"] == 2
    assert m["requestsWithUsage"] == 3
    assert m["agentEnd"] == "final"
    assert m["humanPrompts"] is None


def test_missing_usage_and_event_stream_are_unknown(tmp_path: Path) -> None:
    session = jsonl(tmp_path / "session.jsonl", [
        {"type":"session","version":1},
        {"type":"message","message":{"role":"assistant","content":"完成"}}])
    m = measure(session, None)
    assert m["tokens"]["total"] is None
    assert m["tokens"]["reasoning"] is None
    assert m["usageCoverage"] == "incomplete"
    assert m["toolsStarted"] is None
    assert m["permissionDenials"] is None
    assert m["agentEnd"] == "unknown"


def test_denied_parallel_call_counts_as_attempt_not_execution(tmp_path: Path) -> None:
    session = jsonl(tmp_path / "session.jsonl", [
        {"type":"session","version":1},
        {"type":"message","message":{"role":"assistant","tool_calls":[
            {"id":"a","function":{"name":"read_file","arguments":"{}"}},
            {"id":"b","function":{"name":"bash","arguments":"{}"}}]}}])
    events = jsonl(tmp_path / "events.jsonl", [
        {"event":"PermissionDecided","tool_call_id":"a","kind":"allow"},
        {"event":"PermissionDecided","tool_call_id":"b","kind":"deny"},
        {"event":"ToolStart","tool_call_id":"a"},
        {"event":"AgentEnd","reason":"budget"}])
    m = measure(session, events)
    assert (m["toolAttempts"],m["toolsStarted"],m["permissionDenials"]) == (2,1,1)
    assert m["agentEnd"] == "budget"


@pytest.mark.parametrize("rows", [[], [{"type":"session","version":99}],
    [{"type":"session","version":1},{"type":"usage","total_tokens":-1}]])
def test_metrics_reject_broken_session_instead_of_reporting_zero(tmp_path: Path, rows: list[dict]) -> None:
    with pytest.raises(ValueError):
        measure(jsonl(tmp_path / "bad.jsonl", rows), None)


def test_invalid_json_is_not_silently_dropped(tmp_path: Path) -> None:
    path=tmp_path / "bad.jsonl"
    path.write_text('{"broken":')
    with pytest.raises(ValueError):
        measure(path, None)


def test_partial_usage_optional_fields_and_side_requests(tmp_path: Path) -> None:
    rows=[{"type":"session","version":1},
          {"type":"message","message":{"role":"assistant"}},
          {"type":"usage","prompt_tokens":3,"completion_tokens":2,"total_tokens":5},
          {"type":"message","message":{"role":"assistant"}}]
    m=measure(jsonl(tmp_path/'s.jsonl',rows),None)
    assert m['tokens']['total'] == 5
    assert m['usageCoverage'] == 'incomplete'
    rows.pop()
    rows.append({'type':'compaction','usage':{'total_tokens':8}})
    assert measure(jsonl(tmp_path/'s.jsonl',rows),None)['usageCoverage'] == 'incomplete'


def test_summary_keeps_budget_failures_and_unstarted_in_denominator() -> None:
    rows=[
      {"case":"fix","execution":"completed","agentEnd":"final","grade":{"status":"pass"},"durationMs":100,"metrics":{"tokens":{"total":12},"usageCoverage":"complete"}},
      {"case":"fix","execution":"completed","agentEnd":"budget","grade":{"status":"pass"},"durationMs":300,"metrics":{"tokens":{"total":24},"usageCoverage":"complete"}},
      {"case":"fix","execution":"not_started","agentEnd":"unknown","grade":{"status":"unavailable"}}]
    s=summarize(rows)
    assert (s['planned'],s['started'],s['completeSuccesses'],s['productPasses']) == (3,2,1,2)
    assert s['byCase']['fix']['durationMs'] == {'n':2,'median':200,'min':100,'max':300}
    assert s['byCase']['fix']['totalTokens']['median'] == 18
    assert s['completeSuccessRate'] == pytest.approx(1/3)
    assert s['productPassRate'] == pytest.approx(2/3)
