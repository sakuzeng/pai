"""modes/ 是接线层：不含业务逻辑，但接错线一样会坏，而且要打真实 API 才发现。

所以这里测的是「装配是否正确」——参数有没有原样传到 loop，而不是 loop 本身的行为。
"""

import json

from fake_llm import FakeClient

from pai.core.permissions import RuleSet
from pai.modes.once import run_once

# 本文件多数测试测的是「装配是否正确」，不是权限。feature 09 把默认兜底改成了
# 工作目录边界（写一律 ask、bash 一律 ask，once 下再降级为 deny），会把这些
# e2e 全部拦住。显式注入一个放行的规则集，让它们继续测自己该测的东西。
_OPEN = RuleSet.from_lists(default_decision="allow")


def test_run_once_wires_client_and_returns_answer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # SessionLog 默认写 ./sessions/
    client = FakeClient([{"content": "done"}])
    answer = run_once("x", client=client, model="fake", on_event=lambda _: None)
    assert answer == "done"
    # 工具 schema 必须被装上，否则模型无从调用工具
    assert client.requests[0]["tools"]


def test_run_once_passes_budget_through():
    """预算参数必须原样透传——接线层漏传等于熔断失效，而且静默。"""
    usage = {"prompt_tokens": 900, "completion_tokens": 100, "total_tokens": 1000}
    script = [{"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": usage}] * 5
    client = FakeClient(script)
    answer = run_once("x", client=client, model="fake", max_total_tokens=1500,
                      no_session=True, on_event=lambda _: None)
    assert "预算" in answer


def test_run_once_no_session_skips_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 若回归真建了目录，必须在这里暴露，而不是污染仓库根（R3#4）
    client = FakeClient([{"content": "ok"}])
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    assert not (tmp_path / "sessions").exists()


def test_cli_rejects_negative_max_tokens(monkeypatch):
    """--max-tokens -1 应在解析层报错（R3#10），而不是跑起来输出「累计 0 超过上限 -1」。"""
    import pytest

    import pai.cli as cli

    monkeypatch.setattr(cli, "run_once", lambda *a, **k: "不应执行到这里")
    monkeypatch.setattr("sys.argv", ["pai", "x", "--max-tokens", "-1"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2  # argparse parser.error 的约定退出码


def test_run_once_respects_max_steps():
    script = [{"tool_calls": [("bash", json.dumps({"command": "true"}))]}] * 3
    answer = run_once("x", client=FakeClient(script), model="fake", max_steps=3,
                      no_session=True, on_event=lambda _: None)
    assert "最大步数" in answer


def test_once_event_output_is_byte_identical(tmp_path, monkeypatch):
    """事件流改造的硬约束：once 模式打到屏幕上的字，与改造前一模一样。

    LEGACY 串抄自改造前的 loop.py:182，任何一个字的漂移都算行为变更。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.events import render_text

    events: list = []
    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "echo hi"}))]},
        {"content": "done"},
    ])
    answer = run_once("x", client=client, model="fake", no_session=True,
                      on_event=events.append, rules=_OPEN)

    printed = [text for text in (render_text(e) for e in events) if text is not None]
    assert printed == ["🔧 bash({'command': 'echo hi'}) → hi\n"]
    assert answer == "done"


def test_once_default_event_handler_prints_rendered_text(capsys, tmp_path, monkeypatch):
    """默认 on_event 必须是渲染器而不是 print——否则用户屏幕上是一串 dataclass repr。

    **2026-08-11（feature 11）改写**：期望值多了 `\n🤖 done\n`。
    这不是回归，是拍板问 2 明确选择的代价——「流式默认开、不加开关」会改变 once
    已交付的输出形态（答案从此由 modes.echo 逐字打，cli 不再在结尾补一句）。
    原期望值 `"🔧 …→ hi\n\n"` 留在这条注释里，方便回看到底变了什么。
    """
    monkeypatch.chdir(tmp_path)
    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "echo hi"}))]},
        {"content": "done"},
    ])
    run_once("x", client=client, model="fake", no_session=True, rules=_OPEN)
    out = capsys.readouterr().out
    # 三个 \n 的来源，逐个说清（这类断言最容易看着像凑出来的）：
    # ① bash 结果自带的换行；② rest() 按行渲染补的换行；③ echo 在 🤖 之前空一行。
    # 第三个换行与流式之前 cli 里 `print(f"\n🤖 {answer}")` 的空行是同一个，形态没变。
    assert out == "🔧 bash({'command': 'echo hi'}) → hi\n\n\n🤖 done\n"
    assert "ToolEnd(" not in out


def test_once_assembles_layered_instructions(tmp_path, monkeypatch):
    """装配层的职责：把 PAI.md 真的送到 loop 手里（接错线要打真实 API 才发现）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "PAI.md").write_text("这个项目用 pytest", encoding="utf-8")

    client = FakeClient([{"content": "好"}])
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)

    sent = client.requests[0]["messages"]
    assert any("这个项目用 pytest" in str(m["content"]) for m in sent)


# ---- feature 07 Task 7：ask 降级（拍板问 1）----


def test_ask_without_a_human_degrades_to_deny():
    """once 模式没有真人可问：ask 降级为 deny + 说明，模型可以换个做法继续。

    不降级为 allow 的理由（拍板问 1）：自动化正是最危险的场景，
    ask 规则在那里等于不存在的话，这条规则形同虚设。
    """
    from pai.core.gate import make_before_tool_call
    from pai.core.permissions import RuleSet

    gate = make_before_tool_call(
        RuleSet.from_lists(ask=["Bash(rm *)"]), asker=None)

    decision = gate("bash", {"command": "rm -rf tmp"})

    assert decision.kind == "deny"
    assert "无人可问" in decision.reason


def test_ask_with_a_human_asks_and_honors_the_answer():
    """同一条规则在 REPL 里是真的弹给人——同一套规则两种模式不同行为（拍板问 1）。"""
    from pai.core.gate import make_before_tool_call
    from pai.core.permissions import RuleSet

    asked = []

    def asker(question, options):
        asked.append((question, options))
        return options[0]              # 选「允许」

    gate = make_before_tool_call(RuleSet.from_lists(ask=["Bash(rm *)"]), asker=asker)
    assert gate("bash", {"command": "rm -rf tmp"}).kind == "allow"
    assert asked and "rm -rf tmp" in asked[0][0]

    refusing = make_before_tool_call(
        RuleSet.from_lists(ask=["Bash(rm *)"]), asker=lambda q, o: o[1])
    assert refusing("bash", {"command": "rm -rf tmp"}).kind == "deny"


def test_run_once_wires_the_permission_gate(tmp_path, monkeypatch):
    """接线层漏接就等于权限层没生效，且静默——所以专门钉一次。"""
    import json as _json

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pai").mkdir()
    (tmp_path / ".pai" / "settings.json").write_text(
        _json.dumps({"permissions": {"deny": ["Bash(rm *)"]}}), encoding="utf-8")

    script = [
        {"tool_calls": [("bash", _json.dumps({"command": "rm -rf 不存在的目录"}))]},
        {"content": "被拦了"},
    ]
    client = FakeClient(script)

    run_once("清理", client=client, model="fake", no_session=True, on_event=lambda _: None)

    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "bash(rm *)" in tool_msg["content"]


def test_run_once_wires_recall_when_memories_exist(tmp_path, monkeypatch):
    """接线层测试：有记忆时该先打一次侧查询，把选中的记忆注进主请求（feature 10）。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.memory import memory_dir

    from tests.test_memory_scan import write_memory
    from tests.test_recall import reply

    write_memory(memory_dir(), "甲", description="怎么跑测试", body="记忆正文在此")
    client = FakeClient([reply(["甲.md"]), {"content": "done"}])

    answer = run_once("问题", client=client, model="fake", rules=_OPEN,
                      no_session=True, on_event=lambda _: None)

    assert answer == "done"
    assert len(client.requests) == 2                    # 第 0 次是召回的侧查询
    main = json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert "记忆正文在此" in main


def test_run_once_without_memories_costs_no_extra_request(tmp_path, monkeypatch):
    """空记忆目录不该多花一次请求——短路是本功能的成本底线。"""
    monkeypatch.chdir(tmp_path)
    client = FakeClient([{"content": "done"}])
    run_once("问题", client=client, model="fake", rules=_OPEN,
             no_session=True, on_event=lambda _: None)
    assert len(client.requests) == 1


# ---------------------------------------------------------------------------
# feature 11 task 6：增量上屏 + 最终答案不打两遍
# ---------------------------------------------------------------------------


def test_stream_echo_writes_deltas_with_one_robot_prefix():
    import io

    from pai.core.events import AssistantMessage, MessageDelta
    from pai.modes.echo import make_stream_echo

    out = io.StringIO()
    handle = make_stream_echo(out)
    for piece in ("你", "好", "世界"):
        handle(MessageDelta(text=piece))
    handle(AssistantMessage(content="你好世界"))

    assert out.getvalue() == "\n🤖 你好世界\n"


def test_stream_echo_does_not_print_the_final_answer_twice():
    """`final` 的文本是模型说的，已经逐字流过 → 不重打。"""
    import io

    from pai.core.events import AgentEnd, AssistantMessage, MessageDelta
    from pai.modes.echo import make_stream_echo

    out = io.StringIO()
    handle = make_stream_echo(out)
    handle(MessageDelta(text="答案"))
    handle(AssistantMessage(content="答案"))
    handle(AgentEnd(reason="final", text="答案"))

    assert out.getvalue().count("答案") == 1


def test_stream_echo_still_prints_synthesized_endings():
    """`budget` / `max_steps` / `interrupted` 的文本是 loop 合成的，从没流过 → 必须打。
    不打的话「为什么停了」就彻底没人说了。"""
    import io

    from pai.core.events import AgentEnd
    from pai.modes.echo import make_stream_echo

    for reason, text in (("budget", "已达用量预算：…"),
                         ("max_steps", "达到最大步数（20），任务可能未完成。"),
                         ("interrupted", "已中断：…")):
        out = io.StringIO()
        make_stream_echo(out)(AgentEnd(reason=reason, text=text))
        assert text in out.getvalue(), reason


def test_stream_echo_closes_the_line_when_interrupted_mid_stream():
    """中断掐在流中途时不会有 AssistantMessage 事件——收尾换行得由 AgentEnd 补上，
    否则下一行提示符会接在半截答案后面。"""
    import io

    from pai.core.events import AgentEnd, MessageDelta
    from pai.modes.echo import make_stream_echo

    out = io.StringIO()
    handle = make_stream_echo(out)
    handle(MessageDelta(text="半截"))
    handle(AgentEnd(reason="interrupted", text="已中断：…"))

    assert out.getvalue().startswith("\n🤖 半截\n")


def test_stream_echo_falls_back_for_other_events():
    import io

    from pai.core.events import ToolEnd
    from pai.modes.echo import make_stream_echo

    out = io.StringIO()
    make_stream_echo(out)(ToolEnd(tool_call_id="t", name="bash", args={}, result="ok"))
    assert "🔧 bash" in out.getvalue()


def test_status_line_shows_multiple_running_tools():
    """并发批里多个工具同时在跑（feature 11）。

    `render_tool_line` 其实**早就**支持这个（`running` 是 dict，渲染时全部展开），
    只是 docstring 一直写着「pai 一次只跑一个工具，所以不做」——
    本条把行为钉死，顺带让那句过时的话不再有人信。
    """
    from pai.core.events import ToolStart
    from pai.modes.statusline import render_tool_line

    line = render_tool_line([
        ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}),
        ToolStart(tool_call_id="2", name="read_file", args={"path": "b.py"}),
    ], width=120)
    assert line.count("◐") == 2
    assert "a.py" in line and "b.py" in line
