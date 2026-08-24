"""feature 29 · MCP client：协议层（T1）/ 桥接层（T2）/ 配置与信任（T3）/ 装配（T4）。

全部离线：假 MCP server 是 tests/fake_mcp_server.py（零依赖 stdio 子进程，
血统是动工前反向对照的探针）；假 LLM 走 tests/fake_llm.py。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pai.core.mcp import MCPError, MCPSession

FAKE_SERVER = str(Path(__file__).parent / "fake_mcp_server.py")


def _session(mode: str = "normal", **env) -> MCPSession:
    return MCPSession(
        name="fake",
        command=sys.executable,
        args=[FAKE_SERVER],
        env={"FAKE_MCP_MODE": mode, **env},
    )


@pytest.fixture
def session():
    made: list[MCPSession] = []

    def start(mode: str = "normal", **env) -> MCPSession:
        s = _session(mode, **env)
        s.start()
        made.append(s)
        return s

    yield start
    for s in made:
        s.close()


# ---------------------------------------------------------------- T1 · 协议层

def test_handshake_and_discovery(session):
    s = session()
    assert s.state == "connected"
    names = [t["name"] for t in s.tools]
    assert names == ["echo_token", "always_fails"]
    assert s.tools[0]["description"] == "返回固定暗号。"
    assert s.tools[0]["inputSchema"]["type"] == "object"


def test_discovery_drains_pagination(session):
    s = session("paginate")
    names = [t["name"] for t in s.tools]
    assert names == ["echo_token", "always_fails", "page_two_tool"]


def test_call_tool_returns_raw_result(session):
    s = session()
    result = s.call_tool("echo_token", {})
    texts = [b.get("text") for b in result["content"] if b.get("type") == "text"]
    assert texts == ["FAKE-MCP-TOKEN-4711", "第二个文本块"]


def test_call_tool_iserror_raises_with_detail(session):
    s = session()
    with pytest.raises(MCPError) as exc:
        s.call_tool("always_fails", {})
    assert "FAKE-FAILURE-8181" in str(exc.value)


def test_call_tool_protocol_error_raises(session):
    s = session()
    with pytest.raises(MCPError) as exc:
        s.call_tool("no_such_tool", {})
    assert "unknown tool" in str(exc.value)


def test_call_tool_timeout(session):
    s = session("slow-call", FAKE_MCP_SLOW_SECONDS="5")
    with pytest.raises(MCPError) as exc:
        s.call_tool("echo_token", {}, timeout_ms=300)
    assert "超时" in str(exc.value)


def test_server_death_fails_calls_and_marks_state(session):
    s = session("die-after-list")
    # 进程在 tools/list 应答后退出（发现成功、随后死掉）；调用必须快速失败
    with pytest.raises(MCPError):
        s.call_tool("echo_token", {}, timeout_ms=2000)
    assert s.state == "failed"


def test_death_during_discovery_fails_start(session=None):
    s = _session("die-after-init")
    with pytest.raises(MCPError):
        s.start()
    assert s.state in ("failed", "closed")
    s.close()


def test_dirty_stdout_lines_are_tolerated(session):
    s = session("dirty-stdout")
    assert s.state == "connected"
    result = s.call_tool("echo_token", {})
    assert result["content"][0]["text"] == "FAKE-MCP-TOKEN-4711"


def test_bad_command_fails_loud_not_crash():
    s = MCPSession(name="broken", command="/nonexistent/not-a-command", args=[])
    with pytest.raises(MCPError):
        s.start()
    assert s.state == "failed"
    s.close()                                  # 幂等，不抛


def test_close_is_idempotent_and_kills_process(session):
    s = session()
    proc = s._proc
    s.close()
    s.close()
    assert s.state == "closed"
    assert proc.poll() is not None


# ---------------------------------------------------------------- T2 · 桥接

from pai.core.mcp import (  # noqa: E402
    MAX_MCP_DESC_CHARS,
    MAX_MCP_OUTPUT_CHARS,
    bridge_tools,
    public_tool_name,
)


def test_public_name_normalizes_and_lowercases():
    assert public_tool_name("probe", "echo_token") == "mcp__probe__echo_token"
    # 大写与非法字符：小写化后归一成下划线（权限规则解析时小写化，须对齐）
    assert public_tool_name("Probe", "Echo.Token!") == "mcp__probe__echo_token_"


def test_public_name_overlong_gets_deterministic_hash():
    long_raw = "t" * 100
    name = public_tool_name("srv", long_raw)
    assert len(name) <= 64
    assert name == public_tool_name("srv", long_raw)         # 确定性
    # \0 分隔：拼起来相同、切分不同的两组不能同名
    assert public_tool_name("a", "b__" + "x" * 80) != \
        public_tool_name("a__b", "x" * 80 + "__")


def test_public_name_all_non_ascii_gets_hash_not_collision():
    """功能测试 20260824 低 2：纯非 ASCII 名（如中文）归一化后信息量归零
    （全变 `_`），同 server 任意两个必撞名、第二个被跳过——中文名 server
    功能上只剩一个工具。这类名字也走 hash 兜底保区分；ASCII 名不受影响
    （上两条测试钉着原行为）。"""
    a = public_tool_name("srv", "中文工具")
    b = public_tool_name("srv", "另个名字")
    assert a != b, "纯中文名不该撞名"
    assert a == public_tool_name("srv", "中文工具")          # 确定性
    ok_chars = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    for n in (a, b):
        assert len(n) <= 64 and set(n) <= ok_chars           # API 合法性不回退


def test_bridge_produces_pai_tools(session):
    s = session()
    tools = bridge_tools(s, warn=lambda _m: None)
    names = [t.name for t in tools]
    assert names == ["mcp__fake__echo_token", "mcp__fake__always_fails"]
    assert tools[0].parameters["type"] == "object"            # schema 原样透传
    # 未声明路径语义、未声明豁免 → 兜底 ask（拍板问 3 的结构落点）
    assert tools[0].get_path is None and tools[0].boundary_exempt is False


def test_bridged_tool_joins_text_and_placeholders_nontext(session):
    s = session()
    tools = {t.name: t for t in bridge_tools(s, warn=lambda _m: None)}
    out = tools["mcp__fake__echo_token"].run()
    assert "FAKE-MCP-TOKEN-4711\n第二个文本块" in out         # join("\n") 不丢块间界
    assert "[image: image/png" in out                          # 非 text 占位不静默丢


def test_bridged_tool_iserror_becomes_error_string(session):
    s = session()
    tools = {t.name: t for t in bridge_tools(s, warn=lambda _m: None)}
    out = tools["mcp__fake__always_fails"].run()
    assert out.startswith("错误：")
    assert "FAKE-FAILURE-8181" in out                          # 细节到模型，循环不断


class _StubSession:
    """桥接层单测用：不起真进程，直接喂 tools/call 结果。"""

    def __init__(self, tools, result=None, error=None):
        self.name = "stub"
        self.tools = tools
        self._result = result
        self._error = error

    def call_tool(self, raw_name, arguments, timeout_ms=0):
        if self._error is not None:
            raise self._error
        return self._result


def test_description_sanitized_and_truncated():
    dirty = "正常描述" + "\U000e0041\U000e0042" + "很" * 3000   # Unicode Tag 藏字 + 超长
    stub = _StubSession([{"name": "t", "description": dirty,
                          "inputSchema": {"type": "object"}}])
    tools = bridge_tools(stub, warn=lambda _m: None)
    desc = tools[0].description
    assert "\U000e0041" not in desc                            # Tag 字符剥掉（CC 同课）
    assert len(desc) <= MAX_MCP_DESC_CHARS
    assert desc.startswith("正常描述")


def test_output_char_budget_truncates_with_note():
    huge = "长" * (MAX_MCP_OUTPUT_CHARS + 500)
    stub = _StubSession([{"name": "big", "description": "d",
                          "inputSchema": {"type": "object"}}],
                        result={"content": [{"type": "text", "text": huge}]})
    tools = bridge_tools(stub, warn=lambda _m: None)
    out = tools[0].run()
    assert len(out) <= MAX_MCP_OUTPUT_CHARS + 200              # 提示行的余量
    assert "已截断" in out


def _write_settings(root: Path, servers: dict) -> None:
    import json as _json
    path = root / ".pai" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps({"mcpServers": servers}), encoding="utf-8")


def test_load_mcp_servers_two_layers_project_wins(tmp_path):
    from pai.core.mcp import load_mcp_servers
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write_settings(home, {"shared": {"command": "user-cmd"},
                           "mine": {"command": "u", "args": ["-x"],
                                    "env": {"K": "V"}, "timeout": 5000}})
    _write_settings(proj, {"shared": {"command": "proj-cmd"}})
    servers = load_mcp_servers(cwd=proj, home=home, warn=lambda _m: None)
    by_name = {s.name: s for s in servers}
    assert by_name["shared"].command == "proj-cmd"             # 项目赢（D#72 同语义）
    assert by_name["shared"].source == "project"
    assert by_name["mine"].source == "user"
    assert by_name["mine"].args == ["-x"] and by_name["mine"].env == {"K": "V"}
    assert by_name["mine"].timeout_ms == 5000


def test_load_mcp_servers_skips_bad_entries_with_warn(tmp_path):
    from pai.core.mcp import DEFAULT_CALL_TIMEOUT_MS, load_mcp_servers
    home = tmp_path / "home"
    _write_settings(home, {
        "Bad Name!": {"command": "x"},                # name 不合法
        "nocmd": {},                                  # 缺 command
        "httpish": {"command": "x", "type": "http"},  # v1 只认 stdio
        "tiny": {"command": "x", "timeout": 500},     # <1000 回默认（CC 语义）+ warn
        "good": {"command": "x", "type": "stdio"},
    })
    warnings: list[str] = []
    servers = load_mcp_servers(cwd=tmp_path / "proj", home=home,
                               warn=warnings.append)
    names = sorted(s.name for s in servers)
    assert names == ["good", "tiny"]
    assert {s.name: s for s in servers}["tiny"].timeout_ms == DEFAULT_CALL_TIMEOUT_MS
    # 功能测试 20260824 低 1：回默认可以，静默不行——同函数其余坏配置都 warn，
    # 用户配 `"timeout": 500` 却按 60s 跑而不吭声，与「静默失败是 bug」相冲
    assert any("tiny" in w and "timeout" in w for w in warnings), \
        "timeout 非法值回默认必须 warn"
    assert len(warnings) == 4


def test_load_mcp_servers_bad_json_warns_layer_skipped(tmp_path):
    from pai.core.mcp import load_mcp_servers
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write_settings(home, {"ok": {"command": "x"}})
    bad = proj / ".pai" / "settings.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{烂掉的", encoding="utf-8")
    warnings: list[str] = []
    servers = load_mcp_servers(cwd=proj, home=home, warn=warnings.append)
    assert [s.name for s in servers] == ["ok"]                 # 坏层跳过，好层照用
    assert warnings


def test_mcp_trust_once_drops_project_servers_and_warns(tmp_path):
    from pai.core.mcp import apply_mcp_trust, load_mcp_servers
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write_settings(home, {"mine": {"command": "u"}})
    _write_settings(proj, {"theirs": {"command": "p"}})
    servers = load_mcp_servers(cwd=proj, home=home, warn=lambda _m: None)
    warnings: list[str] = []
    kept = apply_mcp_trust(servers, cwd=proj, home=home, warn=warnings.append)
    assert [s.name for s in kept] == ["mine"]
    assert any("theirs" in w and "未信任" in w for w in warnings)


def test_mcp_trust_dialog_yes_persists_no_skips(tmp_path):
    from pai.core.mcp import apply_mcp_trust, load_mcp_servers
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write_settings(proj, {"theirs": {"command": "p"}})
    servers = load_mcp_servers(cwd=proj, home=home, warn=lambda _m: None)
    # 拒绝：不加载、不持久化（下次再问）
    kept = apply_mcp_trust(servers, cwd=proj, home=home,
                           ask=lambda _q, options: options[1],
                           warn=lambda _m: None)
    assert kept == []
    # 信任：加载 + 持久化，第二次装配不再问
    asked: list[str] = []

    def trust(question, options):
        asked.append(question)
        return options[0]

    kept2 = apply_mcp_trust(servers, cwd=proj, home=home, ask=trust,
                            warn=lambda _m: None)
    assert [s.name for s in kept2] == ["theirs"]
    assert len(asked) == 1 and "theirs" in asked[0]
    kept3 = apply_mcp_trust(servers, cwd=proj, home=home,
                            ask=lambda *_: pytest.fail("信任后不该再问"),
                            warn=lambda _m: None)
    assert [s.name for s in kept3] == ["theirs"]


def test_bridge_skips_public_name_collision_with_warn():
    stub = _StubSession([
        {"name": "Echo.Token", "description": "a", "inputSchema": {"type": "object"}},
        {"name": "echo_token", "description": "b", "inputSchema": {"type": "object"}},
    ])
    warnings: list[str] = []
    tools = bridge_tools(stub, warn=warnings.append)
    assert len(tools) == 1                                     # 归一化后撞名，后者让位
    assert warnings and "echo_token" in warnings[0]


# ---------------------------------------------------------------- T4 · 权限与装配

import json as _json  # noqa: E402
import sys as _sys  # noqa: E402

from pai.core.permissions import RuleSet, decide  # noqa: E402
from tests.fake_llm import FakeClient  # noqa: E402


def _bridged_tools_dict(session) -> dict:
    from pai.core.mcp import bridge_tools
    return {t.name: t for t in bridge_tools(session, warn=lambda _m: None)}


def test_decide_mcp_tool_defaults_to_ask(session):
    """拍板问 3：无 get_path 无豁免 → 兜底「未声明路径语义 → ask」（CC 同构）。"""
    tools = _bridged_tools_dict(session())
    d = decide("mcp__fake__echo_token", {}, RuleSet(), tools=tools)
    assert d.kind == "ask"


def test_allow_rule_server_glob_passes(session):
    """server 级放行 `mcp__<server>__*`：Rule.matches_tool 的 fnmatch 白拿。"""
    tools = _bridged_tools_dict(session())
    d = decide("mcp__fake__echo_token", {},
               RuleSet.from_lists(allow=["mcp__fake__*"]), tools=tools)
    assert d.kind == "allow"
    d2 = decide("mcp__fake__echo_token", {},
                RuleSet.from_lists(deny=["mcp__fake__*"],
                                   allow=["mcp__fake__*"]), tools=tools)
    assert d2.kind == "deny"                   # deny 最先，翻不过


def _mcp_settings(root, mode: str = "normal") -> None:
    path = root / ".pai" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps({"mcpServers": {"fake": {
        "command": _sys.executable, "args": [FAKE_SERVER],
        "env": {"FAKE_MCP_MODE": mode}}}}), encoding="utf-8")


def test_once_wires_mcp_tools_end_to_end(tmp_path, monkeypatch):
    """装配全链：用户级配置 → 连接 → 桥接进工具集 → 模型调用拿到结果。
    once 是 dontAsk，须 allow 规则放行（与 CC 非交互 --allowedTools 同构）。"""
    from pai.modes.once import run_once
    _mcp_settings(Path.home())
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    script = [
        {"tool_calls": [("mcp__fake__echo_token", _json.dumps({}))]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_once("x", client=client, model="fake", no_session=True,
             rules=RuleSet.from_lists(allow=["mcp__fake__*"]),
             on_event=lambda _: None)
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "mcp__fake__echo_token" in tool_names
    tool_msgs = [m for m in client.requests[-1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "FAKE-MCP-TOKEN-4711" in tool_msgs[0]["content"]


def test_once_mcp_denied_by_default_in_dontask(tmp_path, monkeypatch):
    """没有 allow 规则时：兜底 ask → dontAsk 降级拒绝（拍板问 3 的连带后果，
    如实钉住——这是与 CC 一致的行为，不是缺陷）。"""
    from pai.modes.once import run_once
    _mcp_settings(Path.home())
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    script = [
        {"tool_calls": [("mcp__fake__echo_token", _json.dumps({}))]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_once("x", client=client, model="fake", no_session=True,
             on_event=lambda _: None)
    tool_msgs = [m for m in client.requests[-1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "权限被拒绝" in tool_msgs[0]["content"]
    assert "FAKE-MCP-TOKEN-4711" not in tool_msgs[0]["content"]


def test_once_untrusted_project_mcp_skipped(tmp_path, monkeypatch):
    """项目级配置过 28 式门禁：once 无人可问 → 不连接 + 工具不出现。"""
    from pai.modes.once import run_once
    proj = tmp_path / "proj"
    _mcp_settings(proj)                        # 项目级
    proj.mkdir(exist_ok=True)
    monkeypatch.chdir(proj)
    client = FakeClient([{"content": "done"}])
    run_once("x", client=client, model="fake", no_session=True,
             on_event=lambda _: None)
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "mcp__fake__echo_token" not in tool_names


def test_repl_wires_mcp_tools(tmp_path, monkeypatch):
    """interactive 装配：用户级 server 的工具进请求工具集。"""
    from tests.test_skills import _repl
    _mcp_settings(Path.home())
    client, _ = _repl(["问一句"], [{"content": "答"}], tmp_path, monkeypatch)
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "mcp__fake__echo_token" in tool_names


# ---------------------------------------------------------------- T5 · loop 级

import copy  # noqa: E402


def test_loop_with_real_trajectory_and_mcp_tool(session):
    """AGENTS 规约：新阶段模块至少一条测试拿真实会话轨迹当输入——
    REAL_TRAJECTORY 做底，模型在真实对话延续里调 MCP 工具、结果进上下文。"""
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools
    from tests.test_compaction import REAL_TRAJECTORY
    s = session()
    tools = get_tools(["bash", "read_file"])
    tools.update(_bridged_tools_dict(s))
    script = [
        {"tool_calls": [("mcp__fake__echo_token", "{}")]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    messages = copy.deepcopy(REAL_TRAJECTORY)
    answer = run_agent("继续", client=client, model="fake", tools=tools,
                       messages=messages, max_steps=4, on_event=lambda _: None)
    assert answer == "done"
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert any("FAKE-MCP-TOKEN-4711" in (m.get("content") or "") for m in tool_msgs)


# ---------------------------------------------------------------- 29 复核清账

def test_reader_survives_unhashable_id(session):
    """29 复核低 1：server 回 `"id": [1]` 这类脏应答不能弄死 reader 线程——
    死了之后所有调用退化成超时挂等，「脏输入容忍」的承诺就打折了。"""
    s = session("bad-id-noise")
    assert s.state == "connected"
    result = s.call_tool("echo_token", {}, timeout_ms=3000)
    texts = [b.get("text") for b in result["content"] if b.get("type") == "text"]
    assert texts[0] == "FAKE-MCP-TOKEN-4711"


def test_connect_helper_closes_sessions_on_unexpected_error(tmp_path, monkeypatch):
    """29 复核低 4：桥接层冒出非 MCPError 异常时，已启动的 session 不许泄漏——
    异常照样往上抛（不是吞），但子进程必须先收掉。"""
    from pai.core import mcp as mcp_mod
    home = tmp_path / "home"
    _write_settings(home, {"fake": {"command": sys.executable,
                                    "args": [FAKE_SERVER],
                                    "env": {"FAKE_MCP_MODE": "normal"}}})
    made: list = []
    real_session = mcp_mod.MCPSession

    class Recording(real_session):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

    monkeypatch.setattr(mcp_mod, "MCPSession", Recording)
    monkeypatch.setattr(mcp_mod, "bridge_tools",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        mcp_mod.connect_configured_servers(cwd=tmp_path / "proj", home=home,
                                           warn=lambda _m: None)
    assert made, "场景必须真的起过 session，否则本测试在测空气"
    assert all(s.state == "closed" for s in made)


def test_repl_mcp_trust_dialog_loads_and_persists(tmp_path, monkeypatch):
    """29 复核低 5a：interactive 装配级信任问答——答「信任」后工具进请求、
    标记持久化（28 的 skills 有同款 repl 测试，29 此前只有 apply 级单测）。"""
    from pai.core import paths
    from tests.test_skills import _repl
    proj = tmp_path / "proj"
    _write_settings(proj, {"fake": {"command": sys.executable,
                                    "args": [FAKE_SERVER],
                                    "env": {"FAKE_MCP_MODE": "normal"}}})
    client, printed = _repl(["1", "问一句"], [{"content": "答"}],
                            tmp_path, monkeypatch)
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "mcp__fake__echo_token" in tool_names
    assert (paths.project_dir(proj) / "mcp_trusted").is_file()


def test_once_broken_server_warns_and_continues(tmp_path, monkeypatch):
    """29 复核低 5b：server 起不来 → warn、run 照常、mcp 工具不混入
    （此前只有 session 级测试，装配级靠冒烟——补成回归）。"""
    from pai.modes.once import run_once
    _write_settings(Path.home(), {"broken": {"command": "/nonexistent/no-cmd"}})
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    client = FakeClient([{"content": "done"}])
    answer = run_once("x", client=client, model="fake", no_session=True,
                      on_event=lambda _: None)
    assert answer == "done"
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert not any(n.startswith("mcp__") for n in tool_names)


def test_once_config_timeout_reaches_call(tmp_path, monkeypatch):
    """29 复核低 5c：settings 的 `timeout` 字段全链生效——慢 server 在配置
    超时处快速回填错误，而不是挂到 server 睡醒。"""
    import time

    from pai.modes.once import run_once
    _write_settings(Path.home(), {"slow": {
        "command": sys.executable, "args": [FAKE_SERVER],
        "env": {"FAKE_MCP_MODE": "slow-call", "FAKE_MCP_SLOW_SECONDS": "10"},
        "timeout": 1000}})
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    script = [
        {"tool_calls": [("mcp__slow__echo_token", "{}")]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    started = time.time()
    run_once("x", client=client, model="fake", no_session=True,
             rules=RuleSet.from_lists(allow=["mcp__slow__*"]),
             on_event=lambda _: None)
    assert time.time() - started < 5, "配置超时 1s，不该等 server 睡满 10s"
    tool_msgs = [m for m in client.requests[-1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs and tool_msgs[0]["content"].startswith("错误：")
    assert "超时" in tool_msgs[0]["content"]
