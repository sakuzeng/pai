import json

from fake_llm import FakeClient

from pai.loop import run_agent
from pai.tools import get_tools


def test_loop_tool_then_answer(tmp_path):
    target = tmp_path / "hello.txt"
    script = [
        {"tool_calls": [("write_file", json.dumps({"path": str(target), "content": "hi"}))]},
        {"content": "写好了"},
    ]
    client = FakeClient(script)
    answer = run_agent("写个文件", client=client, model="fake", tools=get_tools(),
                       on_event=lambda _: None)

    assert answer == "写好了"
    assert target.read_text(encoding="utf-8") == "hi"
    # 第二次请求里必须带上 tool 结果，且 tool_call_id 与 assistant 声明配对
    second = client.requests[1]["messages"]
    tool_msg = [m for m in second if m["role"] == "tool"][0]
    assistant_msg = [m for m in second if m["role"] == "assistant"][0]
    assert tool_msg["tool_call_id"] == assistant_msg["tool_calls"][0]["id"]


def test_loop_unknown_tool_feeds_error_back():
    script = [
        {"tool_calls": [("no_such_tool", "{}")]},
        {"content": "ok"},
    ]
    client = FakeClient(script)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       on_event=lambda _: None)
    assert answer == "ok"
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "未知工具" in tool_msg["content"]


def test_loop_bad_json_arguments_feeds_error_back():
    script = [
        {"tool_calls": [("bash", "{not json")]},
        {"content": "ok"},
    ]
    client = FakeClient(script)
    run_agent("x", client=client, model="fake", tools=get_tools(), on_event=lambda _: None)
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "不是合法 JSON" in tool_msg["content"]


def test_loop_max_steps_bailout():
    # 模型每轮都发工具调用，永不给最终答案 → max_steps 兜底
    script = [{"tool_calls": [("bash", json.dumps({"command": "true"}))]}] * 3
    client = FakeClient(script)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       max_steps=3, on_event=lambda _: None)
    assert "最大步数" in answer
