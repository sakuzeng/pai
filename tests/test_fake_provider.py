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


# ---- usage 要与真 provider 同形：prompt_tokens 随对话增长（feature 38）----


def test_prompt_tokens_grow_across_requests():
    """真 provider 的 `prompt_tokens` 是「这次请求发过去多少上下文」，随对话单调增长。
    假 provider 此前对每一轮都回同一个数（100/120），而那不是「不够真」这么软——

    pai 的锚点簿记的就是这个数，`find_cut_point` 靠**相邻锚的差值**反推切点。
    差值恒为 0 意味着：无论对话多长、无论 keep_recent 设多小，切点永远是「无可压」。
    压缩链路因此在 e2e 里结构上走不到——测量仪器自己把被测路径堵死了。
    """
    with FakeProvider([turn("一"), turn("二"), turn("三")]) as p:
        c = client(p)
        totals = []
        for _ in range(3):
            chunks = list(c.chat.completions.create(
                model="m", messages=[{"role": "user", "content": "hi"}], stream=True))
            usage = [ch.usage for ch in chunks if ch.usage][-1]
            totals.append(usage.prompt_tokens)

    assert totals == sorted(totals), f"prompt_tokens 必须单调不减，实际 {totals}"
    assert len(set(totals)) == 3, f"每轮都该长一点，实际 {totals}"


def test_a_turn_can_pin_its_own_usage():
    """要精确构造压缩场景（第几轮跨过阈值）时，得能按轮指定。
    不指定就走增长的默认值。"""
    with FakeProvider([turn("一", prompt_tokens=5000)]) as p:
        chunks = list(client(p).chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}], stream=True))
    usage = [ch.usage for ch in chunks if ch.usage][-1]
    assert usage.prompt_tokens == 5000
    assert usage.total_tokens == 5000 + usage.completion_tokens


def test_the_non_streaming_path_reports_usage_the_same_way():
    """召回的侧查询走非流式，它的 usage 同样要计进预算熔断——两条路不能各说各话。"""
    with FakeProvider([turn("一"), turn("二")]) as p:
        c = client(p)
        first = c.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}])
        second = c.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}])
    assert second.usage.prompt_tokens > first.usage.prompt_tokens
