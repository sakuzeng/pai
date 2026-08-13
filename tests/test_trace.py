"""事件落盘（feature 17 task 1）。

session JSONL 是**审计流**（messages + usage，不可再生）；这里落的是**观测流**
（harness 内部事件，可再生）。两者生命周期不同故分文件，理由见 features/17 问 3。

核心约束三条，每条对应下面一组测试：
1. 现有 14 种事件全落、`MessageDelta` 不落（增量正文已在 session 文件里，落它等于写第二份正文）；
2. 事件文件名由 session 文件名推导，两个文件同名配对；
3. **写失败绝不炸 loop**——观测流挂了不能连累正事（同「工具错误不 throw」那条底线）。
"""
import dataclasses
import json

import pytest

from pai.core.events import (
    AgentEnd,
    AgentStart,
    AssistantMessage,
    BreakerTripped,
    Compacted,
    ConversationCleared,
    CompactionSkipped,
    Interrupted,
    MemoryWritten,
    MessageDelta,
    PermissionDecided,
    RecallFailed,
    RecallInjected,
    SteeringInjected,
    ToolEnd,
    ToolStart,
    TurnStart,
)
from pai.core.session import SessionLog
from pai.core.trace import EventTrace, compose

# 每种事件一个真实取值的样本。**这份清单就是「哪些事件会被落盘」的事实源**——
# 新增事件类型时若忘了加进来，test_every_event_type_is_covered 会红。
SAMPLES = [
    AgentStart(task="改一下 README"),
    TurnStart(step=3),
    AssistantMessage(content="好的", tool_call_names=("read_file",)),
    PermissionDecided(tool_call_id="call_1", name="bash", kind="deny", reason="界外写入"),
    ToolStart(tool_call_id="call_1", name="read_file", args={"path": "README.md"}),
    ToolEnd(tool_call_id="call_1", name="read_file", args={"path": "README.md"},
            result="内容", is_error=False),
    Compacted(cut=12, before=983616, after=20000),
    CompactionSkipped(reason="anchors_pending", estimated=987654),
    BreakerTripped(failures=3),
    ConversationCleared(kept=1),
    RecallFailed(reason="unparseable", detail="模型没说话", disabled=True),
    RecallInjected(names=("构建.md", "偏好.md")),
    SteeringInjected(texts=("改用 rg 搜", "顺便看下 tests/")),
    MemoryWritten(topic="偏好", path="~/.pai/memory/x.md"),
    Interrupted(where="stream"),
    AgentEnd(reason="final", text="改完了"),
]


def read_lines(path):
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]


def test_every_event_type_is_covered_by_samples():
    """样本清单必须覆盖 events.py 的全部事件类型（MessageDelta 除外，它刻意不落盘）。

    防的是「新增了一个事件，却没人决定它落不落盘」——那样它会静默缺席观测流。
    """
    from pai.core import events as ev_mod

    declared = {
        name for name, obj in vars(ev_mod).items()
        if dataclasses.is_dataclass(obj) and not name.startswith("_")
    }
    covered = {type(s).__name__ for s in SAMPLES}
    assert declared - covered == {"MessageDelta"}


def test_each_event_round_trips_with_its_type_name(tmp_path):
    trace = EventTrace(tmp_path / "s.jsonl")
    for sample in SAMPLES:
        trace(sample)

    rows = read_lines(tmp_path / "s.events.jsonl")
    assert len(rows) == len(SAMPLES)
    for row, sample in zip(rows, SAMPLES):
        assert row["event"] == type(sample).__name__
        assert isinstance(row["ts"], float)
        for field, value in dataclasses.asdict(sample).items():
            # 元组经 JSON 回来是 list——比较前对齐，别为了好看去改序列化
            expected = list(value) if isinstance(value, tuple) else value
            assert row[field] == expected, f"{type(sample).__name__}.{field}"


def test_message_delta_is_not_written(tmp_path):
    """增量正文已在 session 文件里；落它只会把观测流写成第二份正文（waku 同款处理）。"""
    trace = EventTrace(tmp_path / "s.jsonl")
    for _ in range(50):
        trace(MessageDelta(text="字"))
    assert not (tmp_path / "s.events.jsonl").exists()


def test_path_is_derived_from_the_session_file(tmp_path):
    session = SessionLog(directory=tmp_path)
    trace = EventTrace(session)
    assert trace.path.parent == session.path.parent
    assert trace.path.name == session.path.name.replace(".jsonl", ".events.jsonl")


def test_write_failure_never_raises_and_warns_exactly_once(tmp_path, capsys):
    """父目录是个文件 → 每次写都 OSError。loop 不能因此崩，而且不许每步刷一行噪音。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("我不是目录")
    trace = EventTrace(blocker / "s.jsonl")

    for _ in range(5):
        trace(TurnStart(step=1))          # 不抛就是通过

    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1, f"应恰好告警一行，实际 {len(err)} 行"
    assert "s.events.jsonl" in err[0]


def test_compose_fans_out_to_every_handler():
    seen_a, seen_b = [], []
    handler = compose(seen_a.append, seen_b.append)
    event = TurnStart(step=7)

    handler(event)

    assert seen_a == [event] and seen_b == [event]


def test_compose_skips_none_handlers():
    """装配处常有「有 out 就渲染，没有就不渲染」的分支，让 None 直接传进来更好写。"""
    seen = []
    compose(None, seen.append)(TurnStart(step=1))
    assert len(seen) == 1


def test_compose_does_not_swallow_handler_errors():
    """渲染器炸了就该炸——吞掉异常会让「界面不动」变成无声的谜。

    与 EventTrace 自己吞掉写失败不矛盾：那是观测流的自我约束，compose 是通用扇出。
    """
    def boom(_event):
        raise RuntimeError("渲染炸了")

    with pytest.raises(RuntimeError):
        compose(boom, lambda _e: None)(TurnStart(step=1))
