"""外部命令 hook（feature 07 Task 6）：三种退出码 + 两条边界 + 一条铁律。

hook 用 tmp_path 里的**真脚本**，不 mock 子进程——退出码、stderr、超时这些
正是子进程边界上的东西，mock 掉就等于没测。

铁律：hook 自身超时或崩溃**绝不阻断工作**（design_gate.py 已有先例）。
门禁挂掉的代价应该是「这道门禁没生效」，不是「agent 干不了活」。
"""
import sys

from pai.core import hooks, permissions
from pai.core.permissions import RuleSet


def _hook(tmp_path, name: str, body: str, **kw) -> hooks.HookSpec:
    script = tmp_path / name
    script.write_text("import sys\n" + body, encoding="utf-8")
    # 用 sys.executable 起，不靠 shebang 与 PATH——那两样在 CI 上最容易飘
    return hooks.HookSpec(command=f'{sys.executable} "{script}"', **kw)


def _json_hook(tmp_path, name: str, decision: str, reason: str = "", **kw):
    body = (
        "import json\n"
        f"print(json.dumps({{'hookSpecificOutput': {{'hookEventName': 'PreToolUse',"
        f" 'permissionDecision': {decision!r}, 'permissionDecisionReason': {reason!r}}}}}))\n"
    )
    return _hook(tmp_path, name, body, **kw)


def test_exit_zero_json_decision_is_honored(tmp_path):
    spec = _json_hook(tmp_path, "gate.py", "deny", "档案没拍板")

    decision = hooks.run_pre_tool_use([spec], "bash", {"command": "ls"})

    assert decision.kind == "deny"
    assert "档案没拍板" in decision.reason


def test_exit_two_blocks_with_stderr_as_reason(tmp_path):
    spec = _hook(tmp_path, "block.py", "sys.stderr.write('这条路不许走')\nsys.exit(2)\n")

    decision = hooks.run_pre_tool_use([spec], "bash", {"command": "ls"})

    assert decision.kind == "deny"
    assert "这条路不许走" in decision.reason


def test_other_exit_codes_are_non_blocking(tmp_path):
    """非 0 非 2 = 非阻断错误，只告警继续。"""
    spec = _hook(tmp_path, "oops.py", "sys.stderr.write('脚本自己坏了')\nsys.exit(1)\n")
    warnings = []

    decision = hooks.run_pre_tool_use([spec], "bash", {"command": "ls"}, warn=warnings.append)

    assert decision is None
    assert warnings


def test_multiple_hooks_deny_beats_ask_beats_allow(tmp_path):
    allow = _json_hook(tmp_path, "a.py", "allow")
    ask = _json_hook(tmp_path, "b.py", "ask")
    deny = _json_hook(tmp_path, "c.py", "deny")

    assert hooks.run_pre_tool_use([allow, ask], "bash", {"command": "ls"}).kind == "ask"
    assert hooks.run_pre_tool_use([allow, ask, deny], "bash", {"command": "ls"}).kind == "deny"
    # 顺序不影响结果：取最严的，不是取最后一个
    assert hooks.run_pre_tool_use([deny, ask, allow], "bash", {"command": "ls"}).kind == "deny"


def test_hook_allow_cannot_override_deny_rule(tmp_path):
    """**边界一**：hook 不是万能开关，放行不了规则明令禁止的事。"""
    spec = _json_hook(tmp_path, "permissive.py", "allow", "我说行就行")
    rules = RuleSet.from_lists(deny=["Bash(rm *)"])

    decision = hooks.decide_with_hooks("bash", {"command": "rm -rf /"}, rules, hooks=[spec])

    assert decision.kind == "deny"


def test_hook_block_beats_allow_rule(tmp_path):
    """**边界二**：规则放行的事，hook 仍然拦得住。"""
    spec = _hook(tmp_path, "veto.py", "sys.stderr.write('我不同意')\nsys.exit(2)\n")
    rules = RuleSet.from_lists(allow=["Bash(rm *)"])

    decision = hooks.decide_with_hooks("bash", {"command": "rm -rf tmp"}, rules, hooks=[spec])

    assert decision.kind == "deny"
    assert "我不同意" in decision.reason


def test_hook_timeout_does_not_block_work(tmp_path):
    """铁律：超时按非阻断处理。卡住的门禁不该把 agent 一起卡住。"""
    spec = _hook(tmp_path, "slow.py", "import time\ntime.sleep(30)\n", timeout=0.3)
    warnings = []

    decision = hooks.run_pre_tool_use([spec], "bash", {"command": "ls"}, warn=warnings.append)

    assert decision is None
    assert any("超时" in w for w in warnings)


def test_hook_crash_does_not_block_work(tmp_path):
    spec = _hook(tmp_path, "boom.py", "raise RuntimeError('炸了')\n")
    warnings = []

    decision = hooks.run_pre_tool_use([spec], "bash", {"command": "ls"}, warn=warnings.append)

    assert decision is None
    assert warnings


def test_matcher_filters_by_tool_name(tmp_path):
    spec = _json_hook(tmp_path, "fsonly.py", "deny", "只管文件工具", matcher="read_*")

    assert hooks.run_pre_tool_use([spec], "read_file", {"path": "x"}).kind == "deny"
    assert hooks.run_pre_tool_use([spec], "bash", {"command": "ls"}) is None


def test_hook_receives_the_event_on_stdin(tmp_path):
    """hook 靠 stdin 拿到工具名与入参——拿不到就只能一刀切，做不了 design_gate 那种判定。"""
    body = (
        "import json\n"
        "ev = json.load(sys.stdin)\n"
        "sys.stderr.write(ev['tool_name'] + '|' + ev['tool_input']['command'])\n"
        "sys.exit(2)\n"
    )
    spec = _hook(tmp_path, "echo.py", body)

    decision = hooks.run_pre_tool_use([spec], "bash", {"command": "rm -rf /"})

    assert "bash|rm -rf /" in decision.reason


def test_no_hooks_means_no_opinion():
    assert hooks.run_pre_tool_use([], "bash", {"command": "ls"}) is None
    rules = RuleSet.from_lists(allow=["Bash(ls *)"])
    assert hooks.decide_with_hooks("bash", {"command": "ls"}, rules).kind == "allow"
    assert permissions.decide("bash", {"command": "ls"}, rules).kind == "allow"


# ---- 补齐 spec §6：hook 配置从 settings.json 读 ----
#
# 不接这根线的话 HookSpec 与 run_pre_tool_use 都只是库函数，没人调用——
# 「pai 能跑自己的 design_gate」（拍板问 3 的卖点）就是空话。


def _write_settings(path, payload):
    import json as _json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_loads_hooks_from_both_layers(tmp_path):
    home, project = tmp_path / "home", tmp_path / "proj"
    _write_settings(home / ".pai" / "settings.json", {
        "hooks": {"PreToolUse": [{"command": "user-gate", "matcher": "bash"}]}})
    _write_settings(project / ".pai" / "settings.json", {
        "hooks": {"PreToolUse": [{"command": "proj-gate", "timeout": 1.5}]}})

    specs = hooks.load_hooks(cwd=str(project), home=str(home))

    assert [(s.command, s.matcher) for s in specs] == [
        ("user-gate", "bash"), ("proj-gate", "*")]
    assert specs[1].timeout == 1.5


def test_malformed_hook_entries_are_skipped_not_fatal(tmp_path):
    home, project = tmp_path / "home", tmp_path / "proj"
    _write_settings(project / ".pai" / "settings.json", {
        "hooks": {"PreToolUse": [
            {"matcher": "bash"},              # 没有 command，跳过
            "这不是对象",                       # 类型不对，跳过
            {"command": "good-gate"},         # 好的那条照收
        ]}})
    warnings = []

    specs = hooks.load_hooks(cwd=str(project), home=str(home), warn=warnings.append)

    assert [s.command for s in specs] == ["good-gate"]
    assert len(warnings) == 2


def test_configured_hook_actually_blocks_a_tool_call(tmp_path, monkeypatch):
    """端到端：settings.json 里配一条 hook，真的拦下一次工具调用。"""
    import json as _json

    from fake_llm import FakeClient

    from pai.modes.once import run_once

    monkeypatch.chdir(tmp_path)
    gate = tmp_path / "gate.py"
    gate.write_text("import sys\nsys.stderr.write('门禁说不行')\nsys.exit(2)\n", encoding="utf-8")
    _write_settings(tmp_path / ".pai" / "settings.json", {
        "hooks": {"PreToolUse": [{"command": f'{sys.executable} "{gate}"'}]}})

    client = FakeClient([
        {"tool_calls": [("bash", _json.dumps({"command": "echo hi"}))]},
        {"content": "被拦了"},
    ])
    run_once("跑一下", client=client, model="fake", no_session=True, on_event=lambda _: None)

    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "门禁说不行" in tool_msg["content"]
