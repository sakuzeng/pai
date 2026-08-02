import json

from fake_llm import FakeClient

from pai.core.loop import run_agent
from pai.core.tools import get_tools


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


# ---------- usage 落盘 ----------

USAGE = {
    "prompt_tokens": 1200,
    "completion_tokens": 30,
    "total_tokens": 1230,
    "prompt_cache_hit_tokens": 1024,
    "prompt_cache_miss_tokens": 176,
}


def _read_session(session):
    return [json.loads(line) for line in session.path.read_text(encoding="utf-8").splitlines()]


def test_usage_is_logged_once_per_model_call(tmp_path):
    from pai.core.session import SessionLog

    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": USAGE},
        {"content": "ok", "usage": USAGE},
    ]
    session = SessionLog(tmp_path)
    run_agent("x", client=FakeClient(script), model="fake", tools=get_tools(),
              session=session, on_event=lambda _: None)

    usages = [r for r in _read_session(session) if r.get("type") == "usage"]
    assert len(usages) == 2
    assert [u["step"] for u in usages] == [1, 2]


def test_usage_record_carries_deepseek_cache_fields(tmp_path):
    """prompt_cache_hit/miss_tokens 是 DeepSeek 专有字段，必须原样透传——它是缓存命中率的唯一来源。"""
    from pai.core.session import SessionLog

    session = SessionLog(tmp_path)
    run_agent("x", client=FakeClient([{"content": "ok", "usage": USAGE}]), model="fake",
              tools=get_tools(), session=session, on_event=lambda _: None)

    usage = [r for r in _read_session(session) if r.get("type") == "usage"][0]
    assert usage["prompt_cache_hit_tokens"] == 1024
    assert usage["prompt_cache_miss_tokens"] == 176
    assert usage["model"] == "fake"
    # 本地估算与真实值并排落盘，才能离线校准 0.3/0.6 系数
    assert usage["estimated_prompt_tokens"] > 0


def test_usage_never_leaks_into_messages_sent_to_api(tmp_path):
    """usage 只进 session，绝不能挂到 message 上。

    多一个字段就改变了请求前缀，而 DeepSeek 的硬盘缓存要求"完整匹配缓存前缀单元"
    （refs/deepseek-api/guides/kv_cache.md）——污染消息等于把缓存命中率打到 0。
    """
    from pai.core.session import SessionLog

    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": USAGE},
        {"content": "ok", "usage": USAGE},
    ])
    run_agent("x", client=client, model="fake", tools=get_tools(),
              session=SessionLog(tmp_path), on_event=lambda _: None)

    for req in client.requests:
        for m in req["messages"]:
            assert "usage" not in m
            assert "type" not in m


def test_missing_usage_does_not_break_loop(tmp_path):
    """provider 不回 usage 时不能崩，也不该落空记录。"""
    from pai.core.session import SessionLog

    session = SessionLog(tmp_path)
    answer = run_agent("x", client=FakeClient([{"content": "ok"}]), model="fake",
                       tools=get_tools(), session=session, on_event=lambda _: None)
    assert answer == "ok"
    assert [r for r in _read_session(session) if r.get("type") == "usage"] == []


# ---------- 参数是合法 JSON 但不是对象 ----------


def test_non_object_arguments_feed_error_back_instead_of_crashing():
    """`null` / `[1,2]` / `"hi"` 都是合法 JSON，但 t.run(**args) 会在进入 Tool.run 的 try
    之前就抛 TypeError——防线修在函数内部，而这一击落在函数门口。

    打穿的是两条自家决策：decisions 第 2 条（任何分支都必须回填 tool 消息）与
    第 1 条（Tool.run 保证任何调用路径不漏）。
    """
    for bad in ("null", "[1, 2]", '"hello"', "42", "true"):
        client = FakeClient([
            {"tool_calls": [("bash", bad)]},
            {"content": "ok"},
        ])
        answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                           on_event=lambda _: None)
        assert answer == "ok", f"{bad} 让 loop 崩了"
        tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
        assert "错误" in tool_msg["content"], f"{bad} 没回填错误"


def test_non_object_arguments_still_pair_tool_call_id():
    """回填的错误消息仍须与 assistant 声明的 tool_call_id 严格配对，否则 API 层会报孤儿 tool_result。"""
    client = FakeClient([
        {"tool_calls": [("bash", "null")]},
        {"content": "ok"},
    ])
    run_agent("x", client=client, model="fake", tools=get_tools(), on_event=lambda _: None)
    msgs = client.requests[1]["messages"]
    assistant = [m for m in msgs if m["role"] == "assistant"][0]
    tool = [m for m in msgs if m["role"] == "tool"][0]
    assert tool["tool_call_id"] == assistant["tool_calls"][0]["id"]


# ---------- 预算熔断 ----------


def _budget_script(n, per_call_tokens):
    usage = {"prompt_tokens": per_call_tokens - 10, "completion_tokens": 10,
             "total_tokens": per_call_tokens}
    return [{"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": usage}
            for _ in range(n)]


def test_budget_stops_loop_before_next_request():
    """累计用量超预算就停，且在**发下一次请求之前**停——超支上限被钳制在一次请求内。"""
    client = FakeClient(_budget_script(10, 1000))
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       max_steps=10, max_total_tokens=2500, on_event=lambda _: None)

    assert "预算" in answer
    # 2500 预算 / 每次 1000：前两次累计 2000 未超，第三次后 3000 超 → 不再发第四次
    assert len(client.requests) == 3


def test_budget_not_exceeded_runs_to_completion():
    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))],
         "usage": {"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100}},
        {"content": "done", "usage": {"prompt_tokens": 90, "completion_tokens": 10,
                                      "total_tokens": 100}},
    ]
    client = FakeClient(script)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       max_total_tokens=10_000, on_event=lambda _: None)
    assert answer == "done"


def test_budget_none_means_unlimited():
    client = FakeClient(_budget_script(2, 1_000_000) + [{"content": "done"}])
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       max_steps=5, max_total_tokens=None, on_event=lambda _: None)
    assert answer == "done"


def test_budget_survives_provider_without_usage():
    """provider 不回 usage 时无从累计——不能崩。

    取舍：没有用量数据时预算无法生效，但 max_steps 仍然兜底。
    """
    client = FakeClient([{"tool_calls": [("bash", json.dumps({"command": "true"}))]}] * 3)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       max_steps=3, max_total_tokens=1, on_event=lambda _: None)
    assert "最大步数" in answer


def test_budget_stop_is_reported_with_numbers():
    """停在哪、花了多少必须说清楚，不能只说"停了"。"""
    client = FakeClient(_budget_script(5, 1000))
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       max_steps=5, max_total_tokens=1500, on_event=lambda _: None)
    assert "2000" in answer and "1500" in answer
