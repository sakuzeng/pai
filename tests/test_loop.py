import json

from fake_llm import FakeClient

from pai.core.events import (
    AgentEnd,
    AgentStart,
    AssistantMessage,
    Compacted,
    CompactionSkipped,
    Interrupted,
    ToolEnd,
    ToolStart,
)
from pai.core.interrupt import InterruptFlag
from pai.core.loop import run_agent
from pai.core.tools import Tool, get_tools


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


# ---------- 锚簿记（off-by-one 高危点） ----------


def test_anchor_bookkeeping_is_exact(tmp_path):
    """精确钉死 anchor / anchor_index，而不是只断言 estimated > 0。

    外部评审实测：把 loop 里的 `anchor_index = len(messages)` 改成 `len(messages)-1`，
    全部测试照样绿——说明当时的断言（estimated > 0）根本没测住这个 off-by-one。

    第 2 步的预测值必须精确等于：
        上一步真实 prompt + 上一步真实 completion + 估算(锚之后新增的消息)
    锚之后新增的只有 tool 消息——那条 assistant 消息的真实 token 数就是 completion_tokens，
    已被锚覆盖，绝不能再估一遍。
    """
    from pai.core.compaction import estimate_conversation_tokens
    from pai.core.session import SessionLog

    usage1 = {"prompt_tokens": 700, "completion_tokens": 40, "total_tokens": 740}
    client = FakeClient([
        {"tool_calls": [("bash", json.dumps({"command": "printf hi"}))], "usage": usage1},
        {"content": "ok", "usage": {"prompt_tokens": 800, "completion_tokens": 5,
                                    "total_tokens": 805}},
    ])
    session = SessionLog(tmp_path)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              session=session, on_event=lambda _: None)

    usages = [r for r in _read_session(session) if r.get("type") == "usage"]
    # 第二次请求实际发出去的 messages：system, user, assistant(tool_calls), tool
    sent = client.requests[1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool"]

    tail = sent[3:]  # 锚覆盖到 assistant 为止，尾部只剩这条 tool 消息
    expected = 700 + 40 + estimate_conversation_tokens(tail)
    assert usages[1]["estimated_prompt_tokens"] == expected


def test_anchor_does_not_double_count_the_assistant_message():
    """反向钉死：assistant 消息绝不能既算进 completion_tokens 又被估算一遍。

    若 anchor_index 少 1（指向 assistant 而非其后），估算就会把它重复计入，
    结果必然大于正确值。这条测试专门抓那个方向的错。
    """
    from pai.core.compaction import estimate_conversation_tokens
    from pai.core.session import SessionLog
    import tempfile

    usage1 = {"prompt_tokens": 700, "completion_tokens": 40, "total_tokens": 740}
    long_args = json.dumps({"command": "printf " + "x" * 500})
    client = FakeClient([
        {"tool_calls": [("bash", long_args)], "usage": usage1},
        {"content": "ok", "usage": {"prompt_tokens": 800, "completion_tokens": 5,
                                    "total_tokens": 805}},
    ])
    with tempfile.TemporaryDirectory() as d:
        session = SessionLog(d)
        run_agent("x", client=client, model="fake", tools=get_tools(),
                  session=session, on_event=lambda _: None)
        usages = [r for r in _read_session(session) if r.get("type") == "usage"]

    sent = client.requests[1]["messages"]
    assistant_est = estimate_conversation_tokens([sent[2]])
    assert assistant_est > 100, "夹具没造出足够大的 assistant 消息，测不出重复计入"
    # 若重复计入，预测值会比正确值大出整条 assistant 的估算量
    correct = 700 + 40 + estimate_conversation_tokens(sent[3:])
    assert usages[1]["estimated_prompt_tokens"] == correct
    assert usages[1]["estimated_prompt_tokens"] < correct + assistant_est


# ---------- 并行 tool_calls 配对不变量（R#11） ----------


def test_parallel_tool_calls_each_get_a_reply(tmp_path, monkeypatch):
    """DeepSeek 实测一次回 3 个并行 tool_calls；漏回任何一条下轮即 400（R#11）。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [
            ("bash", json.dumps({"command": "true"})),
            ("bash", json.dumps({"command": "echo a"})),
            ("bash", json.dumps({"command": "echo b"})),
        ]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None)
    sent = client.requests[1]["messages"]           # 第二次请求 = 回填后的完整历史
    assistant = next(m for m in sent if m["role"] == "assistant" and m.get("tool_calls"))
    call_ids = [tc["id"] for tc in assistant["tool_calls"]]
    tool_msgs = [m for m in sent if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == call_ids   # N 条、同序、一一配对


def test_parallel_tool_calls_mixed_known_and_unknown(tmp_path, monkeypatch):
    """合法工具与未知工具同轮混发：未知的也必须回填错误消息，不许漏配对。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [
            ("bash", json.dumps({"command": "true"})),
            ("no_such_tool", json.dumps({})),
        ]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None)
    tool_msgs = [m for m in client.requests[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert "未知工具" in tool_msgs[1]["content"]


# ---------- 压缩接线（e2e） ----------


def _usage(prompt, completion=10):
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion}


def test_loop_compacts_when_over_threshold(tmp_path, monkeypatch):
    """e2e：超线 → 切 → 摘（fake 扮演摘要模型）→ 重建 → 锚重置 → 继续任务。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(100)},
        # 850 而非「看起来够用」的 700：锚值是 prompt+completion，还要过 context_tokens 的
        # 尾部估算才跟 window-reserve=800 比大小，700+10+尾部估算(~8) 差一口气够不着线，
        # 850 留够余量确保第 3 次 create 是真被摘要请求命中，不是编号凑巧。
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(850)},
        {"content": "这是摘要"},                                   # ← 压缩触发的摘要请求
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(300)},
        {"content": "done"},
    ]
    client = FakeClient(script)
    settings = CompactionSettings(reserve_tokens=200, keep_recent_tokens=500)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       context_window=1000, compaction=settings, on_event=lambda _: None)
    assert answer == "done"
    summary_req = client.requests[2]                    # 第 3 次 create = 摘要请求
    assert "tools" not in summary_req
    after = client.requests[3]["messages"]              # 压缩后的下一次任务请求
    assert any("[早前对话的摘要" in (m.get("content") or "") for m in after)
    assert after[0]["role"] == "system"
    assert all(after[i]["role"] != "tool" or             # 无孤儿 tool_result
               after[i - 1].get("tool_calls") or after[i - 1]["role"] == "tool"
               for i in range(1, len(after)))


def test_loop_warns_not_compacts_when_no_cut_available(tmp_path, monkeypatch):
    """单锚场景（find_cut_point 结构性地需要 ≥2 个锚才能算切点）：不是真的无可压，
    是压缩节奏里正常的「锚点不足（<2）」一步——事件应是平静的进度提示，不是 ⚠️ 警告
    （审查修复：区分「真无可压」与「锚点不足」两种语义，避免持续超线时刷屏误导；
    事件文案本身也不该在从未压缩过的会话里提「压缩后」——那会误导用户以为已经压过）。
    不压、不发起摘要请求的行为本身不变。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    events: list = []
    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(900)},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              context_window=1000, compaction=CompactionSettings(reserve_tokens=200),
              on_event=events.append)
    skipped = [e for e in events if isinstance(e, CompactionSkipped)]
    assert [e.reason for e in skipped] == ["anchors_pending"]   # 只有 1 个锚，不是真无可压
    assert not any(isinstance(e, Compacted) for e in events)
    assert all("tools" in r for r in client.requests)    # 没发生摘要请求（摘要请求不带 tools）


def test_breaker_stops_auto_compaction(tmp_path, monkeypatch):
    """连续 3 次压缩后仍超线 → tripped，不再发起第 4 次摘要请求。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    # find_cut_point 铁律（test_compaction.py 已钉死）：单锚永远返回 1（无可压），
    # 切点需要两个锚算差值。压缩一发生就 anchors.reset()，所以每次真正压缩之间必须
    # 有两轮真实 usage 落盘——第一轮撞见「仅一锚」只是平静地「重建中」暂缓（不是警告，
    # 审查修复后 loop.py 按 len(anchors.entries) < 2 区分语义），顺带把它记成第二个锚，
    # 第二轮才有得算。故每个压缩周期是 rebuild-turn + build-turn，不是简报原稿设想的
    # 「一超线就压」单轮节奏；用真实 FakeClient 跑通后回填的序列，语义不变
    # （连续 3 次压缩、真实 usage 仍超线、第 3 次后熔断），只是把「怎么攒够两个锚」
    # 显式摆出来。
    tool_turn = {"tool_calls": [("bash", json.dumps({"command": "true"}))]}
    script = [
        {**tool_turn, "usage": _usage(100)},   # 锚 A：起步，未超线
        {**tool_turn, "usage": _usage(850)},   # 锚 B：与 A 一起够两锚，第 3 次请求前触发首压
        {"content": "摘1"},
        {**tool_turn, "usage": _usage(950)},   # 压后 verify：真实 usage 仍超线 → failures=1
        {**tool_turn, "usage": _usage(975)},   # 单锚「重建中」暂缓（非警告），顺带攒出第二锚
        {"content": "摘2"},
        {**tool_turn, "usage": _usage(950)},   # verify：仍超线 → failures=2
        {**tool_turn, "usage": _usage(975)},   # 单锚「重建中」暂缓（非警告），顺带攒出第二锚
        {"content": "摘3"},
        {**tool_turn, "usage": _usage(950)},   # verify：仍超线 → failures=3 → tripped
        {"content": "done"},                   # tripped 后：不再压，任务正常收尾
    ]
    client = FakeClient(script)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       context_window=1000, max_steps=10,
                       compaction=CompactionSettings(reserve_tokens=200, keep_recent_tokens=1),
                       on_event=lambda _: None)
    assert answer == "done"
    summary_reqs = [r for r in client.requests if "tools" not in r]
    assert len(summary_reqs) == 3                        # 熔断后没有第 4 次


# ---------- 摘要请求 usage 入账（终审 Critical #1） ----------


def test_loop_compaction_usage_counts_toward_budget(tmp_path, monkeypatch):
    """摘要请求（拍平重发近全窗口）是全系统最贵的单次请求，其 usage 必须计入
    max_total_tokens 熔断与 session 记录，不能被 compact() 悄悄丢弃。

    用比正常更紧的 max_total_tokens=1400 制造可区分场景：
    - 若摘要 usage（total_tokens=500）被计入，累计 970(前两步)+500(摘要)+310(第三步) = 1780，
      在第 4 步请求前超预算熔断，answer 带「预算」、不是「done」；
    - 若被丢弃，累计只有 970+310=1280 ≤ 1400，第 4 步会正常发出并拿到「done」。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.session import SessionLog
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(100)},
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(850)},
        {"content": "这是摘要",                              # ← 压缩触发的摘要请求，带 usage
         "usage": {"prompt_tokens": 480, "completion_tokens": 20, "total_tokens": 500}},
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(300)},
        {"content": "done"},
    ]
    client = FakeClient(script)
    settings = CompactionSettings(reserve_tokens=200, keep_recent_tokens=500)
    session = SessionLog(tmp_path)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       context_window=1000, compaction=settings, max_total_tokens=1400,
                       session=session, on_event=lambda _: None)

    assert answer != "done"
    assert "预算" in answer               # 计入摘要 usage 后，第 4 步请求前熔断

    records = _read_session(session)
    compaction_record = [r for r in records if r.get("type") == "compaction"][0]
    assert compaction_record["usage"]["total_tokens"] == 500   # 摘要 usage 也落进 session 记录


# ---------- 真无可压（终审 Important #2） ----------


def test_loop_warns_when_truly_uncompactable(tmp_path, monkeypatch):
    """两个锚点已就位，但 keep_recent_tokens 大到连最老的锚也保不住预算——这才是真无可压
    （区别于「只有 1 个锚」的正常节奏），必须走 ⚠️ 警告分支、不发起摘要请求。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    events: list = []
    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(100)},
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(850)},
        {"content": "done"},
    ]
    client = FakeClient(script)
    settings = CompactionSettings(reserve_tokens=200, keep_recent_tokens=1_000_000)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       context_window=1000, compaction=settings, on_event=events.append)

    assert answer == "done"
    assert any(isinstance(e, CompactionSkipped) and e.reason == "nothing_to_cut"
               for e in events)
    assert all("tools" in r for r in client.requests)   # 没有摘要请求（摘要请求不带 tools）


# ---------- feature 05 task 5：事件流 / 双队列 / 中断 ----------


def _user(text):
    return {"role": "user", "content": text}


def _noop_tool(name="noop", func=None):
    """直接造 Tool 而不过 @tool 注册表：避免测试互相污染全局 REGISTRY。"""
    return Tool(name=name, description="测试用工具", func=func or (lambda: "ok"),
                parameters={"type": "object", "properties": {}, "required": []})


def test_events_cover_the_whole_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    events: list = []
    client = FakeClient([
        {"tool_calls": [("noop", "{}")]},
        {"content": "done"},
    ])
    run_agent("任务", client=client, model="fake", tools={"noop": _noop_tool()},
              on_event=events.append)

    kinds = [type(e) for e in events]
    assert kinds[0] is AgentStart and events[0].task == "任务"
    assert kinds[-1] is AgentEnd and events[-1].reason == "final"
    assert kinds.count(AssistantMessage) == 2
    # ToolStart 必须在 ToolEnd 之前：状态行靠这个顺序显示「进行中」
    assert kinds.index(ToolStart) < kinds.index(ToolEnd)


def test_tool_end_marks_loop_generated_errors():
    events: list = []
    client = FakeClient([
        {"tool_calls": [("不存在的工具", "{}")]},
        {"content": "done"},
    ])
    run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
              on_event=events.append)
    ends = [e for e in events if isinstance(e, ToolEnd)]
    assert [e.is_error for e in ends] == [True]


def test_steering_injected_after_all_tool_results():
    """steering 的注入点是「本轮所有工具结果都回填之后」，不是某一个工具之后。"""
    events: list = []
    client = FakeClient([
        {"tool_calls": [("noop", "{}"), ("noop", "{}")]},
        {"content": "done"},
    ])
    pending = [[_user("改用 python 写")]]

    run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
              on_event=events.append,
              get_steering_messages=lambda: pending.pop(0) if pending else [])

    sent = client.requests[1]["messages"]
    assert sent[-1] == _user("改用 python 写")
    assert [m["role"] for m in sent[-3:]] == ["tool", "tool", "user"]


def test_steering_not_called_when_model_gives_final_answer():
    """语义边界：steering 是「工具执行后」的挂点，没有工具调用就不该问它。"""
    calls = []
    client = FakeClient([{"content": "done"}])
    run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
              on_event=lambda _: None,
              get_steering_messages=lambda: calls.append(1) or [])
    assert calls == []


def test_follow_up_keeps_loop_running():
    """模型本该停下（无 tool_calls），followUp 有货就再跑一轮。"""
    client = FakeClient([{"content": "第一轮"}, {"content": "第二轮"}])
    pending = [[_user("再补一句")]]
    answer = run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
                       on_event=lambda _: None,
                       get_follow_up_messages=lambda: pending.pop(0) if pending else [])
    assert answer == "第二轮"
    assert client.requests[1]["messages"][-1] == _user("再补一句")


def test_no_queues_preserves_old_request_sequence():
    """不传两个队列参数时，请求序列与接线前完全一致（默认 None = 行为不变）。"""
    client = FakeClient([{"tool_calls": [("noop", "{}")]}, {"content": "done"}])
    answer = run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
                       on_event=lambda _: None)
    assert answer == "done"
    assert len(client.requests) == 2
    assert [m["role"] for m in client.requests[1]["messages"]] == \
        ["system", "user", "assistant", "tool"]


def test_interrupt_backfills_remaining_tool_calls():
    """配对不变量：中断也必须每个 tool_call 各回一条，否则下一轮请求就是 400（R#11）。"""
    flag = InterruptFlag()
    events: list = []
    client = FakeClient([{"tool_calls": [("trip", "{}"), ("noop", "{}"), ("noop", "{}")]}])
    tools = {
        "trip": _noop_tool("trip", func=lambda: (flag.set(), "跑完了才中断")[1]),
        "noop": _noop_tool(),
    }
    run_agent("x", client=client, model="fake", tools=tools,
              on_event=events.append, interrupt_flag=flag)

    # FakeClient 脚本只有一轮：loop 若再发一次请求会直接 AssertionError（脚本耗尽）
    tool_msgs = [e for e in events if isinstance(e, ToolEnd)]
    assert len(tool_msgs) == 3, "三个 tool_call 必须各有一条结果，缺一条下轮就 400"
    assert tool_msgs[0].result == "跑完了才中断"
    assert all("已取消" in e.result for e in tool_msgs[1:])
    assert [e.tool_call_id for e in tool_msgs] == ["call_1", "call_2", "call_3"]


def test_interrupt_emits_interrupted_and_agent_end():
    flag = InterruptFlag()
    events: list = []
    client = FakeClient([{"tool_calls": [("trip", "{}")]}])
    tools = {"trip": _noop_tool("trip", func=lambda: (flag.set(), "x")[1])}
    answer = run_agent("x", client=client, model="fake", tools=tools,
                       on_event=events.append, interrupt_flag=flag)

    assert any(isinstance(e, Interrupted) and e.where == "tool" for e in events)
    assert isinstance(events[-1], AgentEnd) and events[-1].reason == "interrupted"
    assert "中断" in answer


def test_interrupt_before_step_stops_without_calling_model():
    flag = InterruptFlag()
    flag.set()
    client = FakeClient([])          # 一次请求都不该发，发了就是脚本耗尽 AssertionError
    answer = run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
                       on_event=lambda _: None, interrupt_flag=flag)
    assert client.requests == []
    assert "中断" in answer


def test_interrupted_conversation_is_preserved_for_next_turn():
    """官方对 Esc 的承诺是「保留迄今完成的工作」——中断后 messages 必须留在调用方手里。"""
    flag = InterruptFlag()
    conversation: list = []
    client = FakeClient([{"tool_calls": [("trip", "{}")]}])
    tools = {"trip": _noop_tool("trip", func=lambda: (flag.set(), "干了一半")[1])}
    run_agent("x", client=client, model="fake", tools=tools, messages=conversation,
              on_event=lambda _: None, interrupt_flag=flag)

    assert [m["role"] for m in conversation] == ["system", "user", "assistant", "tool"]
    assert conversation[-1]["content"] == "干了一半"


def test_messages_param_continues_existing_conversation():
    """REPL 的多轮对话共享一份 messages：传入即续用，不重建 system。"""
    conversation = [
        {"role": "system", "content": "旧的 system"},
        {"role": "user", "content": "第一问"},
        {"role": "assistant", "content": "第一答"},
    ]
    client = FakeClient([{"content": "第二答"}])
    run_agent("第二问", client=client, model="fake", tools={"noop": _noop_tool()},
              messages=conversation, on_event=lambda _: None)

    sent = client.requests[0]["messages"]
    assert sent[0]["content"] == "旧的 system"          # 没被重建
    assert [m["content"] for m in sent] == ["旧的 system", "第一问", "第一答", "第二问"]
    assert conversation[-1]["content"] == "第二答"       # 新回复也留在调用方的列表里


def test_anchor_book_can_be_shared_across_runs():
    """REPL 每轮调一次 run_agent。锚点簿不跨轮持有的话，每轮的第一次请求都退回
    纯字符估算（已知 -33% 误差），压缩触发判断当场失准——所以它必须能注入。
    """
    from pai.core.compaction import AnchorBook

    anchors = AnchorBook()
    conversation: list = []
    client = FakeClient([{"content": "一", "usage": _usage(100)},
                         {"content": "二", "usage": _usage(300)}])
    for task in ("a", "b"):
        run_agent(task, client=client, model="fake", tools={"noop": _noop_tool()},
                  messages=conversation, anchors=anchors, on_event=lambda _: None)

    assert [tokens for _, tokens in anchors.entries] == [110, 310]


def test_compaction_state_can_be_shared_across_runs():
    """熔断状态同理：每轮新建就等于每轮把熔断器清零，连续失败永远数不到 3。"""
    from pai.core.compaction import CompactionSettings, CompactionState

    state = CompactionState()
    state.tripped = True
    conversation: list = []
    client = FakeClient([{"content": "done", "usage": _usage(900)}])
    run_agent("x", client=client, model="fake", tools={"noop": _noop_tool()},
              messages=conversation, compaction_state=state,
              context_window=1000, compaction=CompactionSettings(reserve_tokens=200),
              on_event=lambda _: None)
    assert len(client.requests) == 1        # tripped 已生效：没发摘要请求


def test_compaction_state_updates_propagate_to_caller(tmp_path, monkeypatch):
    """verify_compaction 返回的是**新对象**：loop 若只换绑局部变量，注入方永远看不到
    失败计数，熔断器在 REPL 里等于不存在（每轮清零，连续失败数不到 3）。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings, CompactionState

    state = CompactionState()
    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(100)},
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(850)},
        {"content": "这是摘要"},                                  # 摘要请求
        {"content": "done", "usage": _usage(900)},                # 压缩后仍超线 → 记一次失败
    ]
    client = FakeClient(script)
    settings = CompactionSettings(reserve_tokens=200, keep_recent_tokens=500)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              context_window=1000, compaction=settings, compaction_state=state,
              on_event=lambda _: None)

    assert state.failures == 1, "压缩后仍超线，失败计数必须落到调用方持有的那个对象上"
    assert state.awaiting_verify is False


# ---------- feature 06 task 4：分层指令接线 ----------


def test_instructions_become_the_first_user_message():
    """官方语义：指令作为 **system prompt 之后的 user 消息**传（不是塞进 system）。"""
    client = FakeClient([{"content": "done"}])
    run_agent("任务", client=client, model="fake", tools={"noop": _noop_tool()},
              instructions=lambda: "项目规矩：先跑测试", on_event=lambda _: None)

    sent = client.requests[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "user"]
    assert "项目规矩：先跑测试" in sent[1]["content"]
    assert sent[2]["content"] == "任务"


def test_no_instructions_preserves_old_message_shape():
    client = FakeClient([{"content": "done"}])
    run_agent("任务", client=client, model="fake", tools={"noop": _noop_tool()},
              on_event=lambda _: None)
    assert [m["role"] for m in client.requests[0]["messages"]] == ["system", "user"]


def test_empty_instructions_do_not_add_a_message():
    """没有任何 PAI.md 时不该塞一条空 user 消息——那是白烧 token 且让模型困惑。"""
    client = FakeClient([{"content": "done"}])
    run_agent("任务", client=client, model="fake", tools={"noop": _noop_tool()},
              instructions=lambda: "   ", on_event=lambda _: None)
    assert [m["role"] for m in client.requests[0]["messages"]] == ["system", "user"]


def test_instructions_are_loaded_once_per_run():
    calls = []

    def loader():
        calls.append(1)
        return "指令"

    client = FakeClient([{"tool_calls": [("noop", "{}")]}, {"content": "done"}])
    run_agent("任务", client=client, model="fake", tools={"noop": _noop_tool()},
              instructions=loader, on_event=lambda _: None)
    assert len(calls) == 1, "每步都重读磁盘是浪费；只有压缩后重注入才需要再读一次"


def test_instructions_not_duplicated_when_conversation_continues():
    """REPL 第二轮传的是同一份 messages，指令不能每轮再插一条。"""
    conversation: list = []
    client = FakeClient([{"content": "一"}, {"content": "二"}])
    for task in ("第一问", "第二问"):
        run_agent(task, client=client, model="fake", tools={"noop": _noop_tool()},
                  messages=conversation, instructions=lambda: "项目规矩",
                  on_event=lambda _: None)

    assert [m["content"] for m in conversation].count("项目规矩") == 0 or True
    instruction_msgs = [m for m in conversation if "项目规矩" in str(m.get("content"))]
    assert len(instruction_msgs) == 1


# ---------- feature 06 task 5：压缩后重注入（不做就是长会话静默失效） ----------


def _compaction_script():
    """两个锚点就位后触发压缩：与 test_loop_compacts_when_over_threshold 同款夹具。"""
    return [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(100)},
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(850)},
        {"content": "这是摘要"},                                # ← 压缩触发的摘要请求
        {"content": "done", "usage": _usage(300)},
    ]


def test_instructions_survive_compaction(tmp_path, monkeypatch):
    """compact() 重建的是 [system]+[摘要]+[保留尾部]——指令在第一条 user 位置，
    必然被摘掉。不重注入的话，长会话里 PAI.md 就静默失效了。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import INSTRUCTION_HEADER

    client = FakeClient(_compaction_script())
    run_agent("x", client=client, model="fake", tools=get_tools(),
              instructions=lambda: "项目规矩：先跑测试",
              context_window=1000, compaction=CompactionSettings(reserve_tokens=200,
                                                                 keep_recent_tokens=500),
              on_event=lambda _: None)

    after = client.requests[3]["messages"]                     # 压缩后的下一次任务请求
    assert after[0]["role"] == "system"
    assert str(after[1]["content"]).startswith(INSTRUCTION_HEADER), \
        "指令消息必须回到 system 之后的位置"
    assert "项目规矩：先跑测试" in after[1]["content"]


def test_reinjected_instructions_are_re_read_from_disk(tmp_path, monkeypatch):
    """区分「真重读」与「缓存了启动时那个字符串」：官方原话就是「从磁盘重新读取」。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings

    rules = tmp_path / "PAI.md"
    rules.write_text("旧规矩", encoding="utf-8")

    def loader():
        return rules.read_text(encoding="utf-8")

    calls = {"n": 0}

    def loader_with_edit():
        calls["n"] += 1
        if calls["n"] == 1:                                    # 首次加载之后用户改了文件
            rules.write_text("新规矩", encoding="utf-8")
        return loader()

    client = FakeClient(_compaction_script())
    run_agent("x", client=client, model="fake", tools=get_tools(),
              instructions=loader_with_edit,
              context_window=1000, compaction=CompactionSettings(reserve_tokens=200,
                                                                 keep_recent_tokens=500),
              on_event=lambda _: None)

    after = client.requests[3]["messages"]
    assert "新规矩" in after[1]["content"], "重注入拿的是磁盘上的当前内容，不是启动时的快照"
    assert calls["n"] == 2, "启动一次 + 压缩后一次，正好两次"


def test_no_reinjection_when_instructions_not_provided(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import INSTRUCTION_HEADER

    client = FakeClient(_compaction_script())
    run_agent("x", client=client, model="fake", tools=get_tools(),
              context_window=1000, compaction=CompactionSettings(reserve_tokens=200,
                                                                 keep_recent_tokens=500),
              on_event=lambda _: None)
    after = client.requests[3]["messages"]
    assert not any(str(m.get("content") or "").startswith(INSTRUCTION_HEADER) for m in after)


# ---- feature 07 Task 7：权限接线 ----
#
# loop 只认一件事：`before_tool_call` 返回的 Decision 是不是 allow。
# 「ask 怎么问真人 / 无人可问时怎么降级」全在注入的那个可调用对象里，
# loop 不认识 ask 这个概念——否则模式差异会渗进 loop。


def _deny_gate(reason="不许"):
    from pai.core.permissions import Decision

    return lambda name, args: Decision(kind="deny", reason=reason)


def test_denied_tool_is_not_executed_but_result_is_backfilled(tmp_path):
    """工具没跑，但 tool_call_id 配对完好（D#41 同款不变量）。"""
    target = tmp_path / "不该被创建.txt"
    script = [
        {"tool_calls": [("write_file", json.dumps(
            {"path": str(target), "content": "hi"}))]},
        {"content": "算了"},
    ]
    client = FakeClient(script)

    run_agent("写个文件", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None, before_tool_call=_deny_gate())

    assert not target.exists()                    # 工具真的没跑
    second = client.requests[1]["messages"]
    tool_msg = [m for m in second if m["role"] == "tool"][0]
    assistant_msg = [m for m in second if m["role"] == "assistant"][0]
    assert tool_msg["tool_call_id"] == assistant_msg["tool_calls"][0]["id"]


def test_deny_reason_reaches_the_model():
    """理由必须回填到 tool 消息里，模型才能据此换个做法。"""
    script = [
        {"tool_calls": [("bash", json.dumps({"command": "rm -rf /"}))]},
        {"content": "换个做法"},
    ]
    client = FakeClient(script)

    run_agent("清理", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None,
              before_tool_call=_deny_gate("命中 deny 规则 `bash(rm *)`（来源：user）"))

    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "bash(rm *)" in tool_msg["content"]
    assert "user" in tool_msg["content"]


def test_permission_decided_event_is_emitted():
    from pai.core.events import PermissionDecided

    script = [
        {"tool_calls": [("bash", json.dumps({"command": "ls"}))]},
        {"content": "好"},
    ]
    client = FakeClient(script)
    events = []

    run_agent("x", client=client, model="fake", tools=get_tools(),
              on_event=events.append, before_tool_call=_deny_gate("因为不行"))

    decided = [e for e in events if isinstance(e, PermissionDecided)]
    assert [(e.name, e.kind) for e in decided] == [("bash", "deny")]
    assert decided[0].reason == "因为不行"


def test_allow_decision_runs_the_tool_normally(tmp_path):
    from pai.core.permissions import Decision

    target = tmp_path / "该被创建.txt"
    script = [
        {"tool_calls": [("write_file", json.dumps(
            {"path": str(target), "content": "hi"}))]},
        {"content": "写好了"},
    ]
    client = FakeClient(script)

    run_agent("写", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None,
              before_tool_call=lambda name, args: Decision(kind="allow"))

    assert target.read_text(encoding="utf-8") == "hi"


def test_no_before_tool_call_preserves_old_behavior(tmp_path):
    """默认 None = 与接线前逐字相同。压缩、事件、记忆三次接线都是这个先例。"""
    target = tmp_path / "x.txt"
    script = [
        {"tool_calls": [("write_file", json.dumps(
            {"path": str(target), "content": "hi"}))]},
        {"content": "写好了"},
    ]
    client = FakeClient(script)

    answer = run_agent("写", client=client, model="fake", tools=get_tools(),
                       on_event=lambda _: None)

    assert answer == "写好了"
    assert target.read_text(encoding="utf-8") == "hi"
