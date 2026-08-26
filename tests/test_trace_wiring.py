"""事件落盘的装配（feature 17 task 3）。

test_trace.py 测的是 EventTrace 自己；这里测**接线**——同 test_modes.py 的分工：
接线层不含逻辑，但接错一样会坏，且要真跑一轮才发现。

一条硬约束在最后：事件文件必须落在**会话文件旁边**，而不是当前工作目录、
更不是真实 `$HOME`。2026-08-10 那次「测试把数据写进用户真实 ~/.pai/history」
的教训是结构性的——新增落盘点就得有一条测试盯着它落在哪。
"""

from __future__ import annotations

import json

import pytest
from pathlib import Path

from fake_llm import FakeClient

from pai.core.paths import sessions_dir
from pai.core.permissions import RuleSet
from pai.modes.once import run_once

_OPEN = RuleSet.from_lists(default_decision="allow")


def events_of(directory: Path) -> list:
    files = list(directory.glob("*.events.jsonl"))
    assert len(files) == 1, f"应恰好一个事件文件，实际 {[f.name for f in files]}"
    return [json.loads(ln) for ln in files[0].read_text(encoding="utf-8").splitlines()]


def test_once_writes_the_event_stream_next_to_the_session(tmp_path, monkeypatch):
    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "echo hi"}))]},
        {"content": "好了"},
    ])

    run_once("改点东西", client=client, model="fake", rules=_OPEN, on_event=lambda _: None)

    directory = sessions_dir()
    rows = events_of(directory)
    kinds = [r["event"] for r in rows]
    # 分组边界必须齐全:没有 AgentStart/AgentEnd,viz 就切不出 turn
    assert kinds[0] == "AgentStart" and kinds[-1] == "AgentEnd"
    assert "ToolStart" in kinds and "ToolEnd" in kinds
    # 与会话文件同名配对
    session_file = next(p for p in directory.glob("*.jsonl") if ".events." not in p.name)
    assert (directory / f"{session_file.name[:-len('.jsonl')]}.events.jsonl").exists()


def test_events_carry_their_payload_not_just_the_type_name(tmp_path):
    """只落类型名等于只知道「发生过工具调用」,说不出调了什么——那不叫观测。"""
    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "echo hi"}))]},
        {"content": "好了"},
    ])

    run_once("x", client=client, model="fake", rules=_OPEN, on_event=lambda _: None)

    rows = events_of(sessions_dir())
    tool_end = next(r for r in rows if r["event"] == "ToolEnd")
    assert tool_end["name"] == "bash"
    assert tool_end["args"] == {"command": "echo hi"}
    assert "hi" in tool_end["result"]
    assert tool_end["tool_call_id"]      # 配对靠它,空了 viz 就配不上对


def test_no_session_means_no_event_file(tmp_path, monkeypatch):
    """`--no-session` 是「这次别落盘」,观测流也得跟着闭嘴。"""
    monkeypatch.chdir(tmp_path)
    client = FakeClient([{"content": "ok"}])

    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)

    assert not list(tmp_path.glob("**/*.events.jsonl"))
    assert not list(sessions_dir().glob("*.events.jsonl"))


def test_the_caller_supplied_handler_still_runs(tmp_path):
    """落盘是**加上去**的,不是取代:渲染器必须照常收到每个事件(compose 的意义)。"""
    seen = []
    client = FakeClient([{"content": "ok"}])

    run_once("x", client=client, model="fake", rules=_OPEN, on_event=seen.append)

    assert [type(e).__name__ for e in seen][0] == "AgentStart"
    assert any(type(e).__name__ == "AgentEnd" for e in seen)


def test_interactive_writes_one_event_file_for_the_whole_repl(tmp_path):
    """REPL 跨轮共用一个会话,事件流也该是一个文件——每轮一个文件的话,
    「这次对话都发生了什么」就得靠人肉拼。

    `/clear` 只截断 messages 不换 SessionLog,所以清屏之后仍写同一个文件。
    """
    from pai.modes.interactive import run_interactive

    lines = iter(["第一句", "/clear", "第二句", "/exit"])
    client = FakeClient([{"content": "答一"}, {"content": "答二"}])

    run_interactive(client=client, model="fake", rules=_OPEN,
                    reader=lambda _prompt="": next(lines),
                    out=lambda _s: None, on_event=lambda _e: None)

    rows = events_of(sessions_dir())          # 断言里含「恰好一个事件文件」
    starts = [r for r in rows if r["event"] == "AgentStart"]
    assert len(starts) == 2, "两轮对话应各有一个 AgentStart"
    assert [r["task"] for r in starts] == ["第一句", "第二句"]


# ---- feature 17 task 3.5：会话内的「分段」动作必须在观测流里留痕
# 分不出「新对话」的后果不是少个装饰:时间线会把 /clear 前后画成一段连贯对话,
# 而模型在后半段根本不记得前半段——学 harness 时最要紧的「上下文里有什么」就被画错了。

def _repl(lines, script, **kwargs):
    from pai.modes.interactive import run_interactive

    it = iter(lines)
    client = FakeClient(script)
    run_interactive(client=client, model="fake", rules=_OPEN,
                    reader=lambda _prompt="": next(it),
                    out=lambda _s: None, on_event=lambda _e: None, **kwargs)
    return events_of(sessions_dir())


def test_slash_clear_leaves_a_marker_in_the_event_stream(tmp_path):
    rows = _repl(["第一句", "/clear", "第二句", "/exit"],
                 [{"content": "答一"}, {"content": "答二"}])

    kinds = [r["event"] for r in rows]
    assert "ConversationCleared" in kinds
    # 位置要对:必须夹在两轮之间,否则前端画的分隔线会落错地方
    at = kinds.index("ConversationCleared")
    assert kinds[:at].count("AgentStart") == 1, "清空应发生在第一轮之后"
    assert kinds[at:].count("AgentStart") == 1, "清空应发生在第二轮之前"


def test_manual_compact_emits_the_same_event_as_the_automatic_one(tmp_path):
    """手动 /compact 此前只 out() 打印,观测流里一片空白——
    于是「上下文被换掉了」这件大事,自动压缩看得见、手动压缩看不见。"""
    from pai.core.compaction import CompactionSettings

    script = [
        {"content": "一", "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                                    "total_tokens": 110}},
        {"content": "二", "usage": {"prompt_tokens": 300, "completion_tokens": 10,
                                    "total_tokens": 310}},
        {"content": "这是摘要"},
    ]
    rows = _repl(["第一问", "第二问", "/compact", "/exit"], script,
                 compaction=CompactionSettings(keep_recent_tokens=1))

    compacted = [r for r in rows if r["event"] == "Compacted"]
    assert len(compacted) == 1
    assert compacted[0]["cut"] >= 1


def test_the_tui_path_also_writes_the_event_stream(tmp_path, monkeypatch):
    """**最重要的那条路**:真 tty 下 pai 进 TUI,而 TUI 自建 on_event 走 app.on_event。
    上面几条测试注入了 reader,全走纯 REPL,照不到这条路——真跑没有观测流也不会红。

    这里不起真 TUI(那要 pty),而是把 `_run_tui` 换成间谍真跑一次装配:
    断言的是**递到手里的对象**,不是源码文本。第一版的
    `"trace=" in getsource(...)` 连 `trace=None` 都命中(R4#T3 的点名例子)。
    """
    import inspect

    from pai.core.trace import EventTrace
    from pai.modes import interactive

    params = inspect.signature(interactive._run_tui).parameters
    assert "trace" in params, "_run_tui 必须接收落盘器,否则 TUI 下事件不落盘"
    # 装配处必须真的把它传进去(签名有、不传等于没有)——间谍替身收下全部 kwargs,
    # 真 _run_tui 被换掉,所以不需要 pty;`_use_tui` 一并换成恒真,逼装配走 TUI 分支
    handed = {}
    monkeypatch.setattr(interactive, "_use_tui", lambda reader: True)
    monkeypatch.setattr(interactive, "_run_tui", lambda **kw: handed.update(kw))
    interactive.run_interactive(client=object(), model="fake-model",
                                out=lambda s: None,
                                history_path=tmp_path / "hist")
    assert isinstance(handed.get("trace"), EventTrace), \
        f"TUI 分支拿到的 trace 不是落盘器:{handed.get('trace')!r}"


def test_tui_command_dispatch_carries_on_event(tmp_path):
    """回归钉子:`_dispatch_command` 曾用 `kw["on_event"]` 取一个没人传的键,
    KeyError 把整个 TUI 打崩(屏幕全空)。只有 pty e2e 照得到,而它慢。

    这条测试直接调 dispatch,让同类漏传在 0.1s 内变红。
    """
    from pai.core.events import ConversationCleared
    from pai.modes import interactive

    seen = []
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    anchors = interactive.AnchorBook()
    state = interactive.CompactionState()

    quit_ = interactive._dispatch_command(
        "/clear", commit=lambda _s: None, app=None, session=None,
        flag=interactive.InterruptFlag(), on_event=seen.append,
        messages=messages, anchors=anchors, state=state, tools={},
        client=None, model="fake", compaction=None, context_window=1000,
        rules=None, hooks=(), mode_state=None)

    assert quit_ is False
    assert [type(e) for e in seen] == [ConversationCleared]
    assert len(messages) == 1        # system 留着,其余清掉


def test_the_tui_path_swaps_the_event_sink(tmp_path, monkeypatch):
    """记忆/召回的事件通道在 TUI 起来之后必须换成走 app.on_event。

    两段各钉一头：装配处真把 EventSink 递给了 `_run_tui`（间谍替身，同上一条），
    以及 `_run_tui` 真的换了它——后半段靠在 `term.start()` 上引爆来跑到那一行，
    它之前全是纯构造。不断言源码文本（R4#T3 的教训），断言的是换完之后
    sink 指向谁。
    """
    from pai.modes import interactive

    handed = {}
    real_run_tui = interactive._run_tui        # 间谍装上之前先留住真身
    monkeypatch.setattr(interactive, "_use_tui", lambda reader: True)
    monkeypatch.setattr(interactive, "_run_tui", lambda **kw: handed.update(kw))
    interactive.run_interactive(client=object(), model="fake-model",
                                out=lambda s: None,
                                history_path=tmp_path / "hist")
    sink = handed.get("event_sink")
    assert isinstance(sink, interactive.EventSink), \
        f"TUI 分支拿到的 event_sink 不是可换持有者：{sink!r}"

    seen = []
    sink.set(seen.append)

    class _Stop(RuntimeError):
        pass

    # pytest 捕获的 stdin 没有 fileno()，而 TuiDriver 构造时就要一个——
    # 给个真 fd（不会被读：term.start() 就引爆了）
    class _Stdin:
        def fileno(self):
            return 0

    monkeypatch.setattr(interactive.sys, "stdin", _Stdin())
    monkeypatch.setattr(interactive.TerminalSession, "start",
                        lambda self: (_ for _ in ()).throw(_Stop()))
    handed.pop("out", None)
    with pytest.raises(_Stop):
        real_run_tui(out=lambda _s="": None, **handed)

    from pai.core.events import MemoryWritten

    sink(MemoryWritten(topic="t", path="/tmp/x.md"))
    assert seen == [], "换过之后 sink 还指着测试自己的列表，说明 _run_tui 没换"


def test_the_tui_path_also_feeds_the_state_listener(tmp_path, monkeypatch):
    """TUI 自建 `on_event`（走 app.on_event），外层 compose 到不了它——
    所以跨轮状态的作废监听器必须在那里单独挂一次（与 trace 同一个理由、同一处）。

    漏掉的后果是沉默的：TUI 下 `/clear` 之后召回不会重来，而界面上什么都看不出。

    钉法同上一条，且借它的力：`_run_tui` 在 `term.start()` 之前会把自建的
    `on_event` 塞进 `event_sink`（那是给装配期闭包用的可换持有者）。于是在
    `term.start()` 上引爆之后，sink 里装的**就是**那个自建 handler——
    喂它一条改写事件，监听器就该听见。不断言源码文本（R4#T3 的教训）。
    """
    from pai.core.events import ConversationCleared
    from pai.modes import interactive

    handed = {}
    real_run_tui = interactive._run_tui
    monkeypatch.setattr(interactive, "_use_tui", lambda reader: True)
    monkeypatch.setattr(interactive, "_run_tui", lambda **kw: handed.update(kw))
    interactive.run_interactive(client=object(), model="fake-model",
                                out=lambda s: None,
                                history_path=tmp_path / "hist")
    assert callable(handed.get("state_listener")), "装配处没把监听器递给 _run_tui"

    heard: list = []
    handed["state_listener"] = heard.append
    sink = handed["event_sink"]

    class _Stop(RuntimeError):
        pass

    class _Stdin:
        def fileno(self):
            return 0

    monkeypatch.setattr(interactive.sys, "stdin", _Stdin())
    monkeypatch.setattr(interactive.TerminalSession, "start",
                        lambda self: (_ for _ in ()).throw(_Stop()))
    handed.pop("out", None)
    with pytest.raises(_Stop):
        real_run_tui(out=lambda _s="": None, **handed)

    sink(ConversationCleared(kept=1))       # sink 里现在装的是 TUI 自建的 handler
    assert [type(e) for e in heard] == [ConversationCleared], \
        "TUI 自建的 on_event 没喂状态监听器——那条路上 /clear 之后召回不会重来"


def test_the_tui_uninstalls_the_heartbeat_on_the_way_out(tmp_path, monkeypatch):
    """心跳关着 app 与 driver，TUI 一退它俩就没了——不卸载的话，同一个进程里
    下一个跑命令的人每 0.1 秒去戳一次已经死掉的界面（feature 39）。

    钉法：在 `term.start()` 上引爆（那时心跳已经装上了），确认异常路径上
    `finally` 照样把它卸干净——正常退出那条路更不用说。
    """
    from pai.core import heartbeat
    from pai.modes import interactive

    handed = {}
    real_run_tui = interactive._run_tui
    monkeypatch.setattr(interactive, "_use_tui", lambda reader: True)
    monkeypatch.setattr(interactive, "_run_tui", lambda **kw: handed.update(kw))
    interactive.run_interactive(client=object(), model="fake-model",
                                out=lambda s: None,
                                history_path=tmp_path / "hist")

    class _Stop(RuntimeError):
        pass

    class _Stdin:
        def fileno(self):
            return 0

    monkeypatch.setattr(interactive.sys, "stdin", _Stdin())
    # 引爆点必须在心跳装上**之后**：它现在装在 `term.start()` 之后的 try 里
    # （与 finally 的卸载对称）。炸在 start 上的话，测的就是「装都没装」，
    # 而不是「装了但没卸」——第一版正是这么写的，改完实现后当场露馅。
    # 开场动画的 `time.sleep` 是 try 里第一个够得着的引爆点。
    monkeypatch.setattr(interactive.TerminalSession, "start", lambda self: None)
    monkeypatch.setattr(interactive.TerminalSession, "stop", lambda self: None)
    monkeypatch.setattr(interactive.time, "sleep",
                        lambda _s: (_ for _ in ()).throw(_Stop()))
    handed.pop("out", None)
    sentinel = heartbeat.Heartbeat(lambda: None)
    heartbeat.set_current(sentinel)
    with pytest.raises(_Stop):
        real_run_tui(out=lambda _s="": None, **handed)

    installed = heartbeat.current()
    assert installed is not sentinel, "TUI 压根没装自己的心跳"
    # 看私有字段是刻意的：卸载的契约字面就是「换回一个什么都不做的默认心跳」，
    # 而「什么都不做」在外部没有别的可观察形式——第一版写成「调一下看有没有回声」，
    # 结果心跳吞异常，卸没卸载都没有回声，那条断言等于没有。
    assert installed._on_beat is None, "退出后心跳还关着已经死掉的 app 与 driver"
