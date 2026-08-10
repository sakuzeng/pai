"""流式装配器（feature 11 task 1）。

夹具剪裁自**真实探针**，出处：
docs/dev/features/11-20260811-streaming/evidence/20260811-流式探针/B_parallel_tool_calls.jsonl
（chunk#55-#75，只保留 tool_calls 相关字段）。编的字符串测不出「arguments 逐字符分片」
与「usage 在 choices 非空的末块上」这两个真实坑——它们正是这一层唯一会出错的地方。
"""

import json
from types import SimpleNamespace

from pai.core.interrupt import InterruptFlag
from pai.core.streaming import assemble


def _chunk(*, delta=None, finish_reason=None, usage=None, choices=None):
    """构造一个 chunk。SimpleNamespace 同构模拟 SDK 的 pydantic 对象。

    choices 显式传 [] 用于模拟标准 OpenAI 的「usage 独立块」形状——
    那个形状 DeepSeek 从来不发，但装配器不许只认一种。
    """
    if choices is None:
        choices = [SimpleNamespace(delta=SimpleNamespace(**(delta or {})),
                                   finish_reason=finish_reason, index=0)]
    return SimpleNamespace(choices=choices, usage=usage)


def _frag(index, *, id=None, name=None, arguments=None):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id, function=fn)


# 真实分片时序：id 与 name 只在该 index 的**首块**，arguments 逐字符发。
REAL_TOOL_FRAGMENTS = [
    _frag(0, id="call_00_U7xgjcyOxXvXbNTPOy2d8207", name="get_weather", arguments=""),
    _frag(0, arguments="{"), _frag(0, arguments='"'), _frag(0, arguments="city"),
    _frag(0, arguments='"'), _frag(0, arguments=": "), _frag(0, arguments='"'),
    _frag(0, arguments="北京"), _frag(0, arguments='"'), _frag(0, arguments="}"),
    _frag(1, id="call_01_i1QcRhY1WoHdH1peEnQ12146", name="get_population", arguments=""),
    _frag(1, arguments="{"), _frag(1, arguments='"'), _frag(1, arguments="city"),
    _frag(1, arguments='"'), _frag(1, arguments=": "), _frag(1, arguments='"'),
    _frag(1, arguments="上海"), _frag(1, arguments='"'), _frag(1, arguments="}"),
]

# 实测的 usage 形状：在**末块**上，且该块 choices **非空**（带 finish_reason）
DEEPSEEK_USAGE = {"prompt_tokens": 437, "completion_tokens": 129, "total_tokens": 566,
                  "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 437}


def _real_stream():
    for frag in REAL_TOOL_FRAGMENTS:
        yield _chunk(delta={"tool_calls": [frag]})
    yield _chunk(delta={}, finish_reason="tool_calls", usage=DEEPSEEK_USAGE)


def test_assembles_parallel_tool_calls_from_real_fragments():
    r = assemble(_real_stream())
    assert [tc.function.name for tc in r.tool_calls] == ["get_weather", "get_population"]
    assert [tc.id for tc in r.tool_calls] == [
        "call_00_U7xgjcyOxXvXbNTPOy2d8207", "call_01_i1QcRhY1WoHdH1peEnQ12146"]
    # arguments 必须拼完才是合法 JSON——中途任何一块都不是
    assert json.loads(r.tool_calls[0].function.arguments) == {"city": "北京"}
    assert json.loads(r.tool_calls[1].function.arguments) == {"city": "上海"}
    assert r.finish_reason == "tool_calls"


def test_tool_calls_are_merged_by_index_not_by_id():
    """归并键是 index：后续分片**根本没有 id**，按 id 归并会造出一堆空壳调用。"""
    chunks = [_chunk(delta={"tool_calls": [_frag(0, id="a", name="t", arguments="{")]}),
              _chunk(delta={"tool_calls": [_frag(0, arguments="}")]}),
              _chunk(delta={}, finish_reason="tool_calls")]
    r = assemble(iter(chunks))
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].id == "a"
    assert r.tool_calls[0].function.arguments == "{}"


def test_interleaved_fragments_are_still_merged_correctly():
    """实测 DeepSeek 是串行分片（index=0 发完才发 index=1），但协议允许交错。
    按 index 归并天然兼容两种——这条测试保证我们没有偷偷依赖那个观察。"""
    chunks = [
        _chunk(delta={"tool_calls": [_frag(0, id="a", name="x", arguments='{"v":')]}),
        _chunk(delta={"tool_calls": [_frag(1, id="b", name="y", arguments='{"v":')]}),
        _chunk(delta={"tool_calls": [_frag(0, arguments="1}")]}),
        _chunk(delta={"tool_calls": [_frag(1, arguments="2}")]}),
        _chunk(delta={}, finish_reason="tool_calls"),
    ]
    r = assemble(iter(chunks))
    assert [tc.id for tc in r.tool_calls] == ["a", "b"]
    assert json.loads(r.tool_calls[0].function.arguments) == {"v": 1}
    assert json.loads(r.tool_calls[1].function.arguments) == {"v": 2}


def test_usage_is_found_on_deepseek_shape_last_chunk():
    """DeepSeek 形状：usage 在末块，choices **非空**。

    惯用写法 `if not chunk.choices: usage = chunk.usage` 在这里**分支永不触发**，
    usage 恒为 None → 预算熔断与锚点一起静默哑掉。这是本模块最贵的一条实测。
    """
    assert assemble(_real_stream()).usage["total_tokens"] == 566


def test_usage_is_found_on_openai_shape_separate_chunk():
    """标准 OpenAI 形状：usage 在 choices 为空数组的独立块上。
    两种形状**都要取得到**——这是装配器唯一不许有分支偏好的地方。"""
    chunks = [_chunk(delta={"content": "hi"}),
              _chunk(delta={}, finish_reason="stop"),
              _chunk(choices=[], usage={"total_tokens": 42})]
    assert assemble(iter(chunks)).usage["total_tokens"] == 42


def test_usage_keeps_provider_specific_fields():
    """只透传不归一化：prompt_cache_hit_tokens 是缓存命中率的唯一来源
    （与 compaction.usage_fields 同一个理由）。"""
    assert assemble(_real_stream()).usage["prompt_cache_hit_tokens"] == 0


def test_content_deltas_are_streamed_out_in_order():
    seen = []
    r = assemble(iter([_chunk(delta={"content": "你"}), _chunk(delta={"content": "好"}),
                       _chunk(delta={}, finish_reason="stop", usage={"total_tokens": 1})]),
                 on_delta=seen.append)
    assert seen == ["你", "好"]
    assert r.content == "你好"


def test_reasoning_content_does_not_leak_into_content():
    """思考模式默认开（refs/deepseek-api/guides/thinking_mode.md），
    reasoning_content 是独立字段——混进 content 就等于把思考过程当答案发回给模型。"""
    r = assemble(iter([_chunk(delta={"reasoning_content": "想一下"}),
                       _chunk(delta={"content": "答案"}),
                       _chunk(delta={}, finish_reason="stop")]))
    assert r.content == "答案"


def test_pure_text_answer_has_no_tool_calls():
    """tool_calls 必须是 None 而不是空列表：loop 用 `if not msg.tool_calls` 判终止，
    但 assistant_entry 里带一个空 tool_calls 数组会让下一轮请求形状变脏。"""
    r = assemble(iter([_chunk(delta={"content": "done"}),
                       _chunk(delta={}, finish_reason="stop")]))
    assert r.tool_calls is None
    assert r.content == "done"


def test_interrupt_stops_consuming_and_reports_no_usage():
    """中断掐在流中途：拿不到末块 = 拿不到 usage（实测探针 F）。

    usage 必须是空 dict 而不是瞎猜一个——被中断的请求服务端照样计费，
    本地少算是事实；掩盖它才是 bug。
    """
    flag = InterruptFlag()
    consumed = []

    def stream():
        yield _chunk(delta={"content": "a"})
        consumed.append("a")
        flag.set()
        yield _chunk(delta={"content": "b"})
        consumed.append("b")
        yield _chunk(delta={}, finish_reason="stop", usage={"total_tokens": 99})
        consumed.append("end")

    r = assemble(stream(), flag=flag)
    assert r.interrupted is True
    assert r.usage == {}
    assert r.finish_reason is None
    assert "end" not in consumed        # 真的停止消费了，不是读完再丢


def test_no_flag_means_never_interrupted():
    r = assemble(iter([_chunk(delta={"content": "x"}, finish_reason="stop")]))
    assert r.interrupted is False


def test_fake_client_streaming_round_trips_through_the_assembler():
    """测试基建自检：FakeClient 造的 chunk 序列，装配回来必须等于脚本里写的那一轮。

    没有这条，fake_llm 的流式分支就是一段没人验证过的代码，
    后面所有 loop 流式测试都建在它上面。
    """
    from tests.fake_llm import FakeClient

    client = FakeClient([{"content": "你好世界", "usage": {"total_tokens": 7}}])
    r = assemble(client.chat.completions.create(model="m", messages=[], stream=True))
    assert r.content == "你好世界"
    assert r.usage["total_tokens"] == 7
    assert r.finish_reason == "stop"


def test_fake_client_streaming_can_emit_tool_calls():
    from tests.fake_llm import FakeClient

    client = FakeClient([{"tool_calls": [("bash", '{"command": "ls"}')]}])
    r = assemble(client.chat.completions.create(model="m", messages=[], stream=True))
    assert [tc.function.name for tc in r.tool_calls] == ["bash"]
    assert json.loads(r.tool_calls[0].function.arguments) == {"command": "ls"}
    assert r.finish_reason == "tool_calls"


def test_fake_client_can_emit_the_openai_usage_shape():
    """假 provider 要能造**两种** usage 形状，否则真实形状的那条测试无从对照。"""
    from tests.fake_llm import FakeClient

    client = FakeClient([{"content": "hi", "usage": {"total_tokens": 3},
                          "usage_shape": "openai"}])
    chunks = list(client.chat.completions.create(model="m", messages=[], stream=True))
    assert chunks[-1].choices == []          # OpenAI 形状：末块 choices 为空数组
    assert assemble(iter(chunks)).usage["total_tokens"] == 3
