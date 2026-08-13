"""事件流定型（feature 05 task 1）。

核心断言是「行为一字不变」：LEGACY_* 常量直接抄自改造前的 loop.py
（103/105/114/130/182 五处 on_event 调用点），render_text 必须逐字复现它们——
否则 once 模式的输出就在这次重构里悄悄漂了。
"""
import dataclasses

import pytest

from pai.core.events import (
    AgentEnd,
    AgentStart,
    AssistantMessage,
    BreakerTripped,
    Compacted,
    CompactionSkipped,
    Interrupted,
    ToolEnd,
    ToolStart,
    TurnStart,
    render_text,
)

# 改造前 loop.py 的原文（唯一事实源，改这里等于承认行为变了）
LEGACY_ANCHORS_PENDING = "🗜️ 锚点不足（<2）无法定真实切点，本步暂缓压缩（估算 987654）"
LEGACY_NOTHING_TO_CUT = (
    "⚠️ 上下文超线（估算 987654）但无可压（超长单轮或预算吞下全部历史），"
    "不压，靠预算熔断兜底"
)
LEGACY_COMPACTED = "🗜️ 压缩：切于 7，估算 987654 → 12345"
LEGACY_BREAKER = "⚠️ 压缩连续失败 3 次，自动压缩已熔断"
LEGACY_TOOL = "🔧 bash({'command': 'ls'}) → total 0"


def test_render_text_matches_legacy_strings():
    assert render_text(CompactionSkipped(reason="anchors_pending", estimated=987654)) \
        == LEGACY_ANCHORS_PENDING
    assert render_text(CompactionSkipped(reason="nothing_to_cut", estimated=987654)) \
        == LEGACY_NOTHING_TO_CUT
    assert render_text(Compacted(cut=7, before=987654, after=12345)) == LEGACY_COMPACTED
    assert render_text(BreakerTripped(failures=3)) == LEGACY_BREAKER
    assert render_text(ToolEnd(tool_call_id="call_1", name="bash",
                              args={"command": "ls"}, result="total 0", is_error=False)) \
        == LEGACY_TOOL


def test_render_text_returns_none_for_silent_events():
    # 这些事件是给 REPL/状态行用的，默认不打印——否则 once 模式会凭空多出几行
    silent = [
        AgentStart(task="写个脚本"),
        TurnStart(step=1),
        AssistantMessage(content="好的", tool_call_names=("bash",)),
        ToolStart(tool_call_id="call_1", name="bash", args={"command": "ls"}),
        AgentEnd(reason="final", text="完成"),
    ]
    for event in silent:
        assert render_text(event) is None, f"{type(event).__name__} 不该有默认输出"


def test_tool_end_truncates_long_result():
    long = "x" * 250
    rendered = render_text(ToolEnd(tool_call_id="c", name="bash", args={},
                                   result=long, is_error=False))
    assert rendered.endswith("…")
    assert "x" * 200 in rendered and "x" * 201 not in rendered

    exact = "y" * 200
    rendered = render_text(ToolEnd(tool_call_id="c", name="bash", args={},
                                   result=exact, is_error=False))
    assert not rendered.endswith("…"), "正好 200 字符不该加省略号（原逻辑是严格大于）"


def test_interrupted_has_its_own_line():
    # 中断是本轮新增行为，无历史包袱，但必须可见——不然用户按了 Ctrl+C 屏幕上什么都没有
    assert "中断" in render_text(Interrupted(where="tool"))
    assert "中断" in render_text(Interrupted(where="step"))


def test_events_are_frozen_dataclasses():
    event = TurnStart(step=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.step = 2


def test_recall_failed_renders_reason_and_says_when_it_stops_trying():
    """召回失败原本全静默——用户只看到「召回好像不生效」，看不到原因（2026-08-11 真跑撞到）。"""
    from pai.core.events import RecallFailed, render_text

    once = render_text(RecallFailed(reason="unparseable", detail="(空回复)", disabled=False))
    assert "召回" in once and "(空回复)" in once
    assert "不再" not in once

    tripped = render_text(RecallFailed(reason="request_failed", detail="RuntimeError: 超时",
                                       disabled=True))
    assert "超时" in tripped
    assert "不再" in tripped              # 熔断跳闸这件事必须说出来


def test_recall_injected_names_the_memories(tmp_path=None):
    """feature 17 task 2:成功召回也要说得出召回了什么。"""
    from pai.core.events import RecallInjected

    assert render_text(RecallInjected(names=("构建.md", "偏好.md"))) == \
        "🧠 召回 2 篇记忆：构建.md、偏好.md"


def test_recall_injected_is_frozen():
    import dataclasses as _dc

    from pai.core.events import RecallInjected

    with pytest.raises(_dc.FrozenInstanceError):
        RecallInjected(names=()).names = ("x",)


def test_steering_injected_says_what_went_in(tmp_path=None):
    """feature 18 T2.5：注入必须在界面上可见。

    `_extend` 原本只 append 进 messages 与 session，不发任何事件——于是用户
    插的话进了上下文而屏幕一无所知。CC 踩过同款并修了（`utils/messages.ts` 的
    `case 'queued_command'`：*"Previously this hardcoded isMeta:true, which hid
    user-typed messages"*）。
    """
    from pai.core.events import SteeringInjected

    assert render_text(SteeringInjected(texts=("改用 rg",))) == \
        "📨 已插入 1 条：改用 rg"
    assert render_text(SteeringInjected(texts=("改用 rg", "再看 tests/"))) == \
        "📨 已插入 2 条：改用 rg、再看 tests/"


def test_steering_injected_truncates_long_text():
    """插的话可能很长，状态区不能被一条消息撑爆（同 _preview 的既有做法）。"""
    from pai.core.events import SteeringInjected

    line = render_text(SteeringInjected(texts=("一" * 200,)))
    assert len(line) < 100
    assert line.endswith("…")


def test_steering_injected_is_frozen():
    import dataclasses as _dc

    from pai.core.events import SteeringInjected

    with pytest.raises(_dc.FrozenInstanceError):
        SteeringInjected(texts=()).texts = ("x",)
