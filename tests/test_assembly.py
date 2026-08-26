"""装配收敛（feature 31）。

先钉验收 3：MCP 关闭从 atexit 改单出口 finally——REPL 无论正常退出（EOF）
还是异常上抛，`close_all_mcp` 都必须在 run_interactive 返回前确定性执行。
修前红：atexit 注册的关闭在函数返回时不触发，断言先于解释器退出跑到。

打桩走 `pai.core.mcp` 的模块属性（与 test_mcp.py 的 `mcp_mod.…` 用法同口径）：
装配方在调用点解析属性，测试才替换得掉。
"""
from pathlib import Path

import pytest
from fake_llm import FakeClient

from helpers import OPEN_RULES, scripted_reader
from pai.core import mcp
from pai.core.events import (Compacted, ConversationCleared, ToolEnd)
from pai.core.permissions import RuleSet
from pai.modes.interactive import run_interactive



def _patch_mcp(monkeypatch, closed):
    marker = object()
    monkeypatch.setattr(mcp, "connect_configured_servers",
                        lambda **_kw: ([marker], [], []))
    monkeypatch.setattr(mcp, "close_all_mcp", closed.extend)
    return marker


def test_repl_closes_mcp_sessions_before_returning(monkeypatch):
    closed: list = []
    marker = _patch_mcp(monkeypatch, closed)

    run_interactive(client=FakeClient([]), model="fake", reader=scripted_reader([]),
                    out=lambda _s="": None, on_event=lambda _e: None,
                    no_session=True, rules=OPEN_RULES)
    assert closed == [marker], "run_interactive 返回前必须已关闭 MCP sessions"


def test_repl_closes_mcp_sessions_when_loop_raises(monkeypatch):
    """finally 与 atexit 的另一半差别：异常路径也得关（try/finally 天然覆盖）。"""
    closed: list = []
    marker = _patch_mcp(monkeypatch, closed)

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        run_interactive(client=FakeClient([]), model="fake",
                        reader=scripted_reader([Boom]),
                        out=lambda _s="": None, on_event=lambda _e: None,
                        no_session=True, rules=OPEN_RULES)
    assert closed == [marker]


def test_assemble_applies_bash_timeout_from_settings(monkeypatch, tmp_path):
    """settings 的 bash.timeoutSeconds 经装配层落到 shell 默认超时；
    没配置时显式清空（上一个装配的残留不许漂给下一个）。"""
    import json

    from pai.core import mcp as mcp_mod
    from pai.core.tools import get_tools, shell
    from pai.modes.assembly import assemble

    monkeypatch.setattr(mcp_mod, "connect_configured_servers",
                        lambda **_kw: ([], [], []))
    home = Path.home()                      # conftest 已隔离
    p = home / ".pai" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bash": {"timeoutSeconds": 240}}), encoding="utf-8")

    assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
             on_event=lambda _e: None, session=None, recall_model="fake",
             mode="dontAsk", rules=OPEN_RULES)
    assert shell.default_timeout_seconds() == 240

    p.write_text("{}", encoding="utf-8")
    assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
             on_event=lambda _e: None, session=None, recall_model="fake",
             mode="dontAsk", rules=OPEN_RULES)
    assert shell.default_timeout_seconds() == shell.TIMEOUT_SECONDS


def test_assemble_applies_tests_settings(monkeypatch, tmp_path):
    """settings 的 tests.command / tests.timeoutSeconds 经装配层落到 run_tests。

    这条测试的出处是 feature 33 H9 的教训：`additionalDirectories` 在文档与
    STATUS 里声称存在、实际从没接进装配——配了静默不生效，比没有这个键更糟。
    每加一个配置键就补一条接线测试，是那次教训唯一可执行的落点。
    """
    import json

    from pai.core import mcp as mcp_mod
    from pai.core.tools import get_tools, tests_tool
    from pai.modes.assembly import assemble

    monkeypatch.setattr(mcp_mod, "connect_configured_servers",
                        lambda **_kw: ([], [], []))
    home = Path.home()                      # conftest 已隔离
    p = home / ".pai" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"tests": {"command": "./my-tests.sh",
                                       "timeoutSeconds": 42}}), encoding="utf-8")

    assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
             on_event=lambda _e: None, session=None, recall_model="fake",
             mode="dontAsk", rules=OPEN_RULES)
    assert tests_tool.resolve_command(str(tmp_path))[0] == "./my-tests.sh"
    assert tests_tool.timeout_seconds() == 42

    p.write_text("{}", encoding="utf-8")
    assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
             on_event=lambda _e: None, session=None, recall_model="fake",
             mode="dontAsk", rules=OPEN_RULES)
    assert tests_tool.timeout_seconds() == tests_tool.DEFAULT_TIMEOUT_SECONDS
    tests_tool.set_command(None)
    tests_tool.set_timeout(None)


def test_assemble_wires_additional_directories_into_boundary(monkeypatch, tmp_path):
    """feature 33（H9）：settings 的 permissions.additionalDirectories 落到
    WorkingDirs——此前只存在于文档里，配了静默不生效。"""
    import json

    from pai.core import mcp as mcp_mod
    from pai.core.tools import get_tools
    from pai.modes.assembly import assemble

    monkeypatch.setattr(mcp_mod, "connect_configured_servers",
                        lambda **_kw: ([], [], []))
    extra = tmp_path / "extra-root"
    extra.mkdir()
    p = Path.home() / ".pai" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"permissions": {"additionalDirectories": [str(extra)]}}),
        encoding="utf-8")

    asm = assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
                   on_event=lambda _e: None, session=None, recall_model="fake",
                   mode="dontAsk", rules=OPEN_RULES)
    assert str(extra) in asm.working_dirs.additional


# ---- 事件通道是可换的持有者：TUI 起来之后记忆/召回的事件要跟着走 ----


def test_memory_and_recall_events_follow_the_swapped_sink(monkeypatch):
    """TUI 下 MemoryWritten / RecallFailed 曾直打 stdout，弄花 dock
    （出处：feature 17 T3.5 顺带发现，feature 12/13 就存在）。

    根因是装配期把 `on_event` 烤进了闭包：TUI 是在装配之后才建起来的，
    它自建的 `on_event`（走 app.on_event）换不进去。与 2026-08-11 那次
    asker 卡死同一个形状，所以修法也照 AskerRef —— 事件通道走可变持有者。
    """
    from pai.core import mcp as mcp_mod
    from pai.core.tools import get_tools, memory_tool
    from pai.modes.assembly import assemble
    from pai.modes.interactive import EventSink

    monkeypatch.setattr(mcp_mod, "connect_configured_servers",
                        lambda **_kw: ([], [], []))
    early: list = []
    late: list = []
    sink = EventSink(early.append)

    asm = assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
                   on_event=sink, session=None, recall_model="fake",
                   mode="dontAsk", rules=OPEN_RULES)

    sink.set(late.append)                      # TUI 起来了，换通道

    memory_tool._NOTIFY("话题", Path("/tmp/x.md"))
    assert [type(e).__name__ for e in late] == ["MemoryWritten"]
    assert early == [], "换了通道之后不该再有事件流回旧的（默认渲染器 = 打进 stdout）"

    # 召回失败走同一条通道（on_failure 闭包也是装配期烤进去的）
    from pai.core.recall import RecallFailure

    def _fail(_query, _memories, *, on_failure=None, **_kw):
        on_failure(RecallFailure(reason="request_failed", detail="侧查询炸了",
                                 disabled=False))
        return [], {}

    monkeypatch.setattr("pai.core.recall.select_memories", _fail)
    asm.recall("随便问一句")
    assert [type(e).__name__ for e in late] == ["MemoryWritten", "RecallFailed"]
    assert early == []


# ---- 上下文被改写 → 召回去重表作废（10 遗留 6 + 复核新发现的 /clear 半边）----


def test_rewriting_the_context_lets_a_recalled_memory_be_picked_again(tmp_path, monkeypatch):
    """`RecallState.surfaced` 记的是「这几篇已经在上下文里」——压缩会把它们切掉、
    `/clear` 会把它们整段删掉，那句话就成了假的，而这几篇从此再也不会被选中
    （静默的单调衰减）。

    feature 37 起这件事走事件而不是注入回调：装配层给出的是一个**事件监听器**，
    收到 `CONTEXT_REWRITING` 里的事件就作废跨轮状态。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.memory import memory_dir
    from pai.modes.assembly import assemble
    from helpers import write_memory
    from helpers import recall_reply as reply

    write_memory(memory_dir(), "甲", description="怎么跑测试", body="记忆正文在此")
    client = FakeClient([reply(["甲.md"]), reply(["甲.md"]), reply(["甲.md"])])
    asm = assemble(client=client, tools={}, warn=lambda _s: None,
                   on_event=lambda _e: None, session=None, recall_model="fake",
                   mode="dontAsk", rules=OPEN_RULES)

    assert "记忆正文在此" in asm.recall("问题")[0]
    assert asm.recall("再问")[0] == "", "已注入过的不该再选一遍（这是对的）"
    asm.state_listener(Compacted(cut=3, before=900, after=200))
    assert "记忆正文在此" in asm.recall("三问")[0], "上下文被改写之后必须能重来"


# ---- 路径作用域规则接线（feature 36 Task 5）----


def _write_rule(tmp_path, name="前端", paths="web/**", body="样式一律用 rem"):
    directory = tmp_path / ".pai" / "rules"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(
        f"---\npaths: {paths}\n---\n\n{body}", encoding="utf-8")


def _assemble(tmp_path):
    from pai.modes.assembly import assemble

    return assemble(client=FakeClient([]), tools={}, warn=lambda _s: None,
                    on_event=lambda _e: None, session=None, recall_model="fake",
                    mode="dontAsk", rules=OPEN_RULES)


def test_assembly_wires_the_rule_pipeline(tmp_path, monkeypatch):
    """装配期扫一次（同 skills），跨轮持有注入表。"""
    monkeypatch.chdir(tmp_path)
    _write_rule(tmp_path)
    asm = _assemble(tmp_path)

    assert asm.on_paths_touched(("src/loop.py",)) == "", "不相关的路径不该拉进规则"
    assert "样式一律用 rem" in asm.on_paths_touched(("web/a.css",))
    assert asm.on_paths_touched(("web/b.css",)) == "", "同一条不重复注入"


def test_rewriting_the_context_lets_a_rule_be_injected_again(tmp_path, monkeypatch):
    """压缩把它切走之后「已经在上下文里」就是假的——与召回去重表同一条通道
    （`events.CONTEXT_REWRITING` 那条判据，feature 37 起走事件）。"""
    monkeypatch.chdir(tmp_path)
    _write_rule(tmp_path)
    asm = _assemble(tmp_path)

    assert "样式一律用 rem" in asm.on_paths_touched(("web/a.css",))
    assert asm.on_paths_touched(("web/b.css",)) == ""
    asm.state_listener(ConversationCleared(kept=1))
    assert "样式一律用 rem" in asm.on_paths_touched(("web/c.css",))


def test_no_rules_directory_costs_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    asm = _assemble(tmp_path)
    assert asm.on_paths_touched(("web/a.css",)) == ""


def test_repl_passes_the_rule_callback_to_run_agent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    captured: dict = {}

    def fake_run_agent(*args, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("pai.modes.interactive.run_agent", fake_run_agent)
    run_interactive(client=FakeClient([{"content": "ok"}]), model="fake",
                    reader=scripted_reader(["问一句"]), out=lambda _s="": None,
                    on_event=lambda _e: None, no_session=True, rules=OPEN_RULES)
    assert callable(captured.get("on_paths_touched"))


def test_once_passes_the_rule_callback_to_run_agent(monkeypatch, tmp_path):
    from pai.modes.once import run_once

    monkeypatch.chdir(tmp_path)
    captured: dict = {}

    def fake_run_agent(*args, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("pai.modes.once.run_agent", fake_run_agent)
    run_once("x", client=FakeClient([{"content": "ok"}]), model="fake",
             no_session=True, on_event=lambda _: None)
    assert callable(captured.get("on_paths_touched"))


def test_a_real_turn_pulls_the_rule_in_after_reading_a_matching_file(tmp_path, monkeypatch):
    """纵切：真跑一轮 REPL（假 client + 真工具 + 真装配），模型 read_file 一个
    匹配文件之后，第二次请求里必须带着规则正文。

    单元接线全绿而纵切坏掉是这个仓库反复踩的形状（feature 12 三条被打回的 bug
    全在接缝上），所以这条必须存在。"""
    import json

    monkeypatch.chdir(tmp_path)
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "a.css").write_text("body{}", encoding="utf-8")
    _write_rule(tmp_path)

    client = FakeClient([
        {"tool_calls": [("read_file", json.dumps({"path": "web/a.css"}))]},
        {"content": "看完了"},
    ])
    run_interactive(client=client, model="fake", reader=scripted_reader(["看看样式"]),
                    out=lambda _s="": None, on_event=lambda _e: None,
                    no_session=True, rules=OPEN_RULES)

    second = json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert "样式一律用 rem" in second, "读了匹配文件，规则就该在下一次请求里"
    first = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert "样式一律用 rem" not in first, "读到之前一个字都不该进上下文"


def test_the_listener_ignores_events_that_did_not_rewrite_anything(tmp_path, monkeypatch):
    """反向守卫：一个普通的工具结束不该把去重表清掉——那等于每步都重付一次
    注入的钱，而且没有任何东西会变红。"""
    monkeypatch.chdir(tmp_path)
    _write_rule(tmp_path)
    asm = _assemble(tmp_path)

    assert "样式一律用 rem" in asm.on_paths_touched(("web/a.css",))
    asm.state_listener(ToolEnd(tool_call_id="1", name="read_file", args={},
                               result="ok", is_error=False))
    assert asm.on_paths_touched(("web/b.css",)) == "", "没改写上下文就不许清"


def test_clearing_the_conversation_really_lets_recall_come_back(tmp_path, monkeypatch):
    """纵切：真跑两轮 REPL，中间 `/clear`。第一轮召回过的那篇记忆，
    `/clear` 之后必须能重新被选中——这条走的是完整的事件链
    （`_handle_command` 发 `ConversationCleared` → 装配层的监听器 → `surfaced`）。

    复核 feature 35 时正是在这条路上发现「`/clear` 没清」的（TODO 只登记了压缩
    那一半），所以它值得一条纵切而不只是单元测试。"""
    import json

    monkeypatch.chdir(tmp_path)
    from pai.core.memory import memory_dir
    from helpers import write_memory
    from helpers import recall_reply as reply

    write_memory(memory_dir(), "甲", description="怎么跑测试", body="记忆正文在此")
    client = FakeClient([reply(["甲.md"]), {"content": "一"},
                         reply(["甲.md"]), {"content": "二"}])
    run_interactive(client=client, model="fake", rules=OPEN_RULES,
                    reader=scripted_reader(["第一问", "/clear", "第二问"]),
                    out=lambda _s="": None, on_event=lambda _e: None,
                    no_session=True)

    turns = [r for r in client.requests if "tools" in r]        # 主请求带 tools
    assert len(turns) == 2
    second = json.dumps(turns[1]["messages"], ensure_ascii=False)
    assert "记忆正文在此" in second, "/clear 之后那篇记忆必须能重新召回"


