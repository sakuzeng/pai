"""modes/ 是接线层：不含业务逻辑，但接错线一样会坏，而且要打真实 API 才发现。

所以这里测的是「装配是否正确」——参数有没有原样传到 loop，而不是 loop 本身的行为。
"""

import json

from fake_llm import FakeClient

from pai.modes.once import run_once


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
                      on_event=events.append)

    printed = [text for text in (render_text(e) for e in events) if text is not None]
    assert printed == ["🔧 bash({'command': 'echo hi'}) → hi\n"]
    assert answer == "done"


def test_once_default_event_handler_prints_rendered_text(capsys, tmp_path, monkeypatch):
    """默认 on_event 必须是渲染器而不是 print——否则用户屏幕上是一串 dataclass repr。"""
    monkeypatch.chdir(tmp_path)
    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "echo hi"}))]},
        {"content": "done"},
    ])
    run_once("x", client=client, model="fake", no_session=True)
    out = capsys.readouterr().out
    assert out == "🔧 bash({'command': 'echo hi'}) → hi\n\n"
    assert "ToolEnd(" not in out
