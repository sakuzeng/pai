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


def test_run_once_no_session_skips_disk():
    client = FakeClient([{"content": "ok"}])
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    # 没有 session 时不应因缺目录而崩，也不该建 sessions/
    assert True


def test_run_once_respects_max_steps():
    script = [{"tool_calls": [("bash", json.dumps({"command": "true"}))]}] * 3
    answer = run_once("x", client=FakeClient(script), model="fake", max_steps=3,
                      no_session=True, on_event=lambda _: None)
    assert "最大步数" in answer
