"""T15：假 provider 自身的测试。

它是别人的测试基建——**它错了会让被测代码假绿**，所以它自己也得被测
（同 tests/tui_screen.py 那条）。
"""

import json

from fake_provider import FakeProvider, turn
from openai import OpenAI


def client(provider):
    return OpenAI(api_key="not-a-real-key", base_url=provider.base_url)


def test_streaming_yields_content_character_by_character():
    """真实流式就是逐字符切的（K streaming/streaming-tool-calls.md 实测）。"""
    with FakeProvider([turn("你好世界")]) as p:
        chunks = list(client(p).chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}], stream=True))
    text = "".join(c.choices[0].delta.content or "" for c in chunks)
    assert text == "你好世界"
    assert len([c for c in chunks if c.choices[0].delta.content]) == 4


def test_usage_is_on_the_last_chunk_with_non_empty_choices():
    """D#58：`include_usage` 在 DeepSeek 上是空操作，usage 在末块且 choices 非空。

    照文档写成「choices 为空的独立块」会让 pai 的解析器被喂出假绿——
    它在真实环境里遇不到那个形状。
    """
    with FakeProvider([turn("x")]) as p:
        chunks = list(client(p).chat.completions.create(
            model="m", messages=[], stream=True))
    with_usage = [c for c in chunks if getattr(c, "usage", None)]
    assert len(with_usage) == 1
    assert with_usage[0].choices, "usage 块的 choices 必须非空（实测形状）"
    assert with_usage[0] is chunks[-1]


def test_tool_calls_are_merged_by_index_with_id_only_on_the_first_chunk():
    with FakeProvider([turn(tool_calls=[{"name": "bash",
                                         "arguments": {"command": "ls -la"}}])]) as p:
        chunks = list(client(p).chat.completions.create(
            model="m", messages=[], stream=True))
    heads = [c for c in chunks if c.choices[0].delta.tool_calls
             and c.choices[0].delta.tool_calls[0].id]
    assert len(heads) == 1                      # id 只在首块
    assert heads[0].choices[0].delta.tool_calls[0].function.name == "bash"
    arguments = "".join(
        tc.function.arguments or ""
        for c in chunks for tc in (c.choices[0].delta.tool_calls or []))
    assert json.loads(arguments) == {"command": "ls -la"}


def test_non_streaming_path_also_works():
    """召回的侧查询不走流式。"""
    with FakeProvider([turn("侧查询答案")]) as p:
        response = client(p).chat.completions.create(
            model="m", messages=[{"role": "user", "content": "q"}])
    assert response.choices[0].message.content == "侧查询答案"
    assert response.usage.total_tokens == 120


def test_script_is_consumed_in_order():
    with FakeProvider([turn("第一轮"), turn("第二轮")]) as p:
        c = client(p)
        first = c.chat.completions.create(model="m", messages=[])
        second = c.chat.completions.create(model="m", messages=[])
    assert first.choices[0].message.content == "第一轮"
    assert second.choices[0].message.content == "第二轮"


def test_exhausted_script_falls_back_instead_of_erroring():
    """脚本比真实轮数短是常态。回 500 会把「脚本没写够」伪装成「pai 崩了」。"""
    with FakeProvider([], exhausted="没词了") as p:
        response = client(p).chat.completions.create(model="m", messages=[])
    assert response.choices[0].message.content == "没词了"


def test_requests_are_recorded_for_assertions():
    """能断言「pai 发出去的请求长什么样」——工具 schema 有没有装上之类。"""
    with FakeProvider([turn("ok")]) as p:
        client(p).chat.completions.create(
            model="m", messages=[{"role": "user", "content": "问题"}],
            tools=[{"type": "function", "function": {"name": "bash"}}])
        assert p.requests[0]["messages"][0]["content"] == "问题"
        assert p.requests[0]["tools"][0]["function"]["name"] == "bash"
