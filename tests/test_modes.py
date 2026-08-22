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


# --- feature 12 T5：/mode 命令 -------------------------------------------

def _cmd(line, mode_state):
    """`_handle_command` 要一堆跨轮状态，这里只关心 /mode 那一支。"""
    from pai.core.compaction import AnchorBook, CompactionSettings, CompactionState
    from pai.modes.interactive import _handle_command

    out = []
    _handle_command(line, out=out.append, messages=[], anchors=AnchorBook(),
                    state=CompactionState(), tools={}, client=None, model="m",
                    compaction=CompactionSettings(), context_window=1000,
                    mode_state=mode_state)
    return "\n".join(out)


def test_no_emoji_in_tui_authored_lines():
    """D#63：界面自己的文案不用 emoji（字体缺字 + 宽度不确定）。

    2026-08-11 靠**自己回放出图**发现的第一个问题——`🔐 权限模式 →` 是 feature 12
    我自己写的 TUI 侧文案，违反了我自己立的规矩。
    （`render_text` 与 `_handle_command` 里那些是 05/06 交付的 scrollback 内容，
    本轮不动，见 theme.py 的声明。）

    保留源码断言（R4#T3 逐条处理时的裁决）：这是 lint 型测试，钉的是
    **源码字面量的字符集**；行为版要把每条渲染路径都跑到才等价，枚举不完——
    扫源码反而是更强的那个。
    """
    import inspect

    from pai.modes import interactive

    source = inspect.getsource(interactive._run_tui)
    for ch in source:
        assert ord(ch) < 0x1F000, f"_run_tui 里出现 emoji: {ch!r}"


def test_mode_command_shows_the_current_mode_and_the_cycle():
    from pai.core.permissions import PermissionModeState

    text = _cmd("/mode", PermissionModeState("acceptEdits"))
    assert "acceptEdits" in text
    assert "dontAsk" in text          # 明说它不在环里，别让人以为漏了


def test_mode_command_switches():
    from pai.core.permissions import PermissionModeState

    state = PermissionModeState("default")
    _cmd("/mode bypassPermissions", state)
    assert state() == "bypassPermissions"


def test_mode_command_rejects_unknown_and_keeps_the_old_mode():
    from pai.core.permissions import PermissionModeState

    state = PermissionModeState("default")
    assert "❌" in _cmd("/mode 没听说过", state)
    assert state() == "default"


def test_permissions_command_shows_the_current_mode():
    """关掉 TODO 那条小修：用户看不到自己在哪个模式下。"""
    from pai.core.permissions import PermissionModeState
    from pai.modes.interactive import _show_permissions

    out = []
    _show_permissions(out.append, None, mode_state=PermissionModeState("acceptEdits"))
    assert "acceptEdits" in "\n".join(out)


# --- feature 12 T8：主循环兜底 -------------------------------------------

def test_repl_survives_an_unexpected_exception_in_a_turn(tmp_path, monkeypatch):
    """06 遗留「同类问题第三次」：任何逃逸异常都该回到提示符，而不是掀掉会话。

    注意别把 EOFError（Ctrl+D 正常退出）也吞掉——下一条测试钉这个。
    """
    monkeypatch.chdir(tmp_path)
    from pai.modes import interactive

    monkeypatch.setattr(interactive, "_run_turn",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("底层炸了")))
    lines = iter(["随便问点什么", "/exit"])
    out = []
    interactive.run_interactive(client=FakeClient([]), model="fake",
                                reader=lambda _p="": next(lines), out=out.append,
                                on_event=lambda _e: None, no_session=True,
                                rules=_OPEN, history_path=tmp_path / "h")
    text = "\n".join(out)
    assert "本轮出错" in text and "RuntimeError" in text
    assert "再见。" in text                    # 会话活到了正常退出


def test_ctrl_d_still_exits_and_is_not_swallowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pai.modes import interactive

    def reader(_prompt=""):
        raise EOFError

    out = []
    interactive.run_interactive(client=FakeClient([]), model="fake", reader=reader,
                                out=out.append, on_event=lambda _e: None,
                                no_session=True, rules=_OPEN,
                                history_path=tmp_path / "h")
    assert "再见。" in "\n".join(out)


# --- feature 12 交付后的严重回归：权限框走了老 asker，TUI 下必然卡死 ----------

def test_gate_asker_can_be_swapped_after_assembly():
    """**2026-08-11 用户真跑卡死**：`gate` 在装配期捕获了 REPL 的老 asker，
    而 TUI 只换了 `ask.set_asker`。于是权限询问走老路径调 `input()`——
    stdin 此刻在 raw mode，Enter 发的是 `\\r` 不是 `\\n`，`input()` 永远等不到行尾，
    Ctrl+C 也因为 ISIG 关了而只是个普通字节。**整个程序死住，退都退不出去。**

    根因与 T5 那条模式的一模一样：**装配期捕获 = 运行时改不动**。
    所以 asker 也必须走可变持有者。
    """
    from pai.core.gate import make_before_tool_call
    from pai.core.permissions import RuleSet
    from pai.modes.interactive import AskerRef

    # 「换之前走的是老 asker」这半边此前从没被验证过：那行断言写成
    # `reason.endswith("老 asker") or True`——`reason` 里根本不带 asker 的答案
    # （它是「用户当场拒绝（命中 ask 规则 …）」），所以那句断言本身就是错的，
    # 而 `or True` 让它永远不会红。真正可观测的证据是「老 asker 有没有被问到」。
    asked: list = []

    def old_asker(question, options):
        asked.append("old")
        return "老 asker"                       # 不是「允许这次」→ 应判 deny

    ref = AskerRef(old_asker)
    gate = make_before_tool_call(RuleSet.from_lists(ask=["bash(*)"]), asker=ref)

    first = gate("bash", {"command": "ls"})
    assert asked == ["old"], "换之前该问老 asker"
    assert first.kind == "deny"

    ref.set(lambda q, o: "允许这次")
    second = gate("bash", {"command": "ls"})
    assert second.kind == "allow", (first, second)


def test_asker_ref_reports_whether_a_human_is_available():
    """`asker=None` 与 `dontAsk` 合流（D#48/D#53）。持有者必须能表达「现在没有真人」，
    否则 once 那条降级路径会被这个包装破坏。"""
    from pai.core.gate import make_before_tool_call
    from pai.core.permissions import RuleSet
    from pai.modes.interactive import AskerRef

    gate = make_before_tool_call(RuleSet.from_lists(ask=["bash(*)"]), asker=AskerRef(None))
    assert gate("bash", {"command": "ls"}).kind == "deny"


# ---- feature 22（R4#E2）：装配层传生成的 system prompt ----


def test_once_sends_a_prompt_built_from_its_actual_tools(tmp_path, monkeypatch):
    """once 的工具集没有 ask_user_question（无真人可问），prompt 里也不许有——
    常量时代它反过来：REPL 明明有这个工具，prompt 却只报四个名字。"""
    monkeypatch.chdir(tmp_path)
    client = FakeClient([{"content": "好"}])
    run_once("x", client=client, model="fake", no_session=True,
             on_event=lambda _: None, rules=_OPEN)
    system = client.requests[0]["messages"][0]["content"]
    assert "bash" in system and "edit_file" in system
    assert "ask_user_question" not in system
    # 判别断言：装配必须传**生成的** prompt——上面三条对旧常量恰好也全真
    from pai.core.loop import SYSTEM_PROMPT
    assert system != SYSTEM_PROMPT, "once 还在发常量，说明装配没接线"


def test_interactive_sends_a_prompt_that_admits_ask_user_question(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pai.modes import interactive

    lines = iter(["随便说点", "/exit"])
    client = FakeClient([{"content": "好"}])
    interactive.run_interactive(client=client, model="fake",
                                reader=lambda _p="": next(lines),
                                out=lambda _s: None, on_event=lambda _e: None,
                                no_session=True, rules=_OPEN,
                                history_path=tmp_path / "h")
    system = client.requests[0]["messages"][0]["content"]
    assert "ask_user_question" in system, "REPL 真有这个工具，prompt 不许再瞒着"
