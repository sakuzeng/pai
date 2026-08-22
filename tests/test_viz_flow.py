"""turn 分组与配对（feature 17 task 4）。

**唯一一处分组逻辑**：前端不重复实现（两份必然漂移，见 plan T7 决定 1），
所以这里是时间线正确性的全部地基。

至少一条测试拿真实轨迹当输入（AGENTS.md 测试规约）：`fixtures/real_session.jsonl`
是真跑出来的，编字符串编不出「一条 assistant 里两个并发工具调用」这种形状。
"""

from __future__ import annotations

import json
from pathlib import Path

from pai.viz.flow import load_flow

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")


# ---- 真实轨迹：一次「说一句 + 并发读两个文件」的完整回合

def test_real_session_groups_into_one_turn():
    flow = load_flow(FIXTURES / "real_session.jsonl")

    assert len(flow["turns"]) == 1
    turn = flow["turns"][0]
    assert turn["user"].startswith("先用一句话说说什么是流式输出")
    assert turn["unfinished"] is False


def test_real_session_pairs_both_parallel_tool_calls():
    """一条 assistant 里两个 read_file——**并发批**（feature 11）跑出来的真实形状。
    编的夹具里通常一条 assistant 只挂一个工具，配不出这个坑。"""
    turn = load_flow(FIXTURES / "real_session.jsonl")["turns"][0]

    tools = [s for s in turn["steps"] if s["kind"] == "tool"]
    assert len(tools) == 2
    assert [t["name"] for t in tools] == ["read_file", "read_file"]
    assert [t["args"]["path"] for t in tools] == ["hello.txt", "dup.txt"]
    assert "hello world" in tools[0]["result"]
    # 配对不许错位:两个调用的 id 必须各自对上自己的结果
    assert tools[0]["id"] != tools[1]["id"]
    assert all(t["id"].startswith("call_") for t in tools)


def test_real_session_reports_tokens_and_cache_hit():
    turn = load_flow(FIXTURES / "real_session.jsonl")["turns"][0]

    llm = [s for s in turn["steps"] if s["kind"] == "llm"]
    assert len(llm) == 2                       # 两步:发起调用 + 收到结果后作答
    assert llm[0]["model"] == "deepseek-v4-flash"
    assert llm[0]["in"] == 935 and llm[0]["out"] == 165
    assert llm[0]["cached"] == 256             # provider 给了两套缓存字段,取到即可
    assert turn["tokens_in"] == 935 + 1128     # 整个 turn 求和
    assert turn["tokens_out"] == 165 + 39


def test_llm_step_carries_the_assistant_text_and_its_tool_calls():
    turn = load_flow(FIXTURES / "real_session.jsonl")["turns"][0]

    first = [s for s in turn["steps"] if s["kind"] == "llm"][0]
    assert "流式输出" in first["content"]
    assert [c["name"] for c in first["tool_calls"]] == ["read_file", "read_file"]


def test_steps_are_in_wall_clock_order():
    """时间线是**时间**线:步骤必须按 ts 升序,否则页面上因果关系是乱的。"""
    turn = load_flow(FIXTURES / "real_session.jsonl")["turns"][0]
    stamps = [s["ts"] for s in turn["steps"]]
    assert stamps == sorted(stamps)


# ---- 构造夹具：真实轨迹覆盖不到的边界

def test_a_turn_that_never_ended_is_kept_and_flagged(tmp_path):
    """挂起/被杀的现场证据。丢弃它等于把「卡在哪」这个唯一线索删了(waku 同款处理)。"""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "跑一下测试"},
        {"ts": 2.0, "type": "usage", "step": 1, "model": "m",
         "prompt_tokens": 10, "completion_tokens": 2},
        {"ts": 3.0, "role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "function": {"name": "bash",
                                                  "arguments": '{"command": "./test.sh"}'}}]},
        # 到此为止——工具结果永远没回来
    ])

    turn = load_flow(path)["turns"][0]

    assert turn["unfinished"] is True
    pending = [s for s in turn["steps"] if s["kind"] == "tool"]
    assert pending == [], "结果没回来就不该凭空造一个 tool 步骤"
    assert turn["steps"][-1]["tool_calls"][0]["pending"] is True


def test_multiple_turns_split_on_each_user_message(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "system", "content": "sys"},
        {"ts": 2.0, "role": "user", "content": "第一问"},
        {"ts": 3.0, "role": "assistant", "content": "答一"},
        {"ts": 4.0, "role": "user", "content": "第二问"},
        {"ts": 5.0, "role": "assistant", "content": "答二"},
    ])

    flow = load_flow(path)

    assert [t["user"] for t in flow["turns"]] == ["第一问", "第二问"]
    assert all(t["unfinished"] is False for t in flow["turns"])
    assert flow["system"] == "sys"       # system 不属于任何 turn,单独拎出来


def test_broken_lines_are_skipped_and_counted(tmp_path):
    """进程被杀会留下半行 JSONL。**绝不因一行坏拒绝整个文件**——
    那等于「出过一次事故就再也看不了这次会话」。"""
    path = tmp_path / "s.jsonl"
    path.write_text(
        json.dumps({"ts": 1.0, "role": "user", "content": "问"}) + "\n"
        + '{"ts": 2.0, "role": "assist\n'          # 半行
        + json.dumps({"ts": 3.0, "role": "assistant", "content": "答"}) + "\n",
        encoding="utf-8")

    flow = load_flow(path)

    assert flow["skipped"] == 1
    assert len(flow["turns"]) == 1 and flow["turns"][0]["user"] == "问"


def test_missing_event_file_still_yields_turns(tmp_path):
    """Layer 2 之前的老会话没有 .events.jsonl,时间线照常(两块互不拖累,沿用 01 的原则)。"""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [{"ts": 1.0, "role": "user", "content": "问"},
                       {"ts": 2.0, "role": "assistant", "content": "答"}])

    flow = load_flow(path)

    assert flow["has_events"] is False
    assert len(flow["turns"]) == 1


def test_harness_events_land_inside_the_turn_they_belong_to(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "第一问"},
        {"ts": 4.0, "role": "assistant", "content": "答一"},
        {"ts": 5.0, "role": "user", "content": "第二问"},
        {"ts": 8.0, "role": "assistant", "content": "答二"},
    ])
    write_jsonl(tmp_path / "s.events.jsonl", [
        {"ts": 2.0, "event": "PermissionDecided", "tool_call_id": "c1",
         "name": "bash", "kind": "deny", "reason": "界外"},
        {"ts": 6.0, "event": "Compacted", "cut": 3, "before": 900, "after": 100},
    ])

    flow = load_flow(path)

    assert flow["has_events"] is True
    first, second = flow["turns"]
    assert [s["event"] for s in first["steps"] if s["kind"] == "event"] == ["PermissionDecided"]
    assert [s["event"] for s in second["steps"] if s["kind"] == "event"] == ["Compacted"]


def test_cleared_marks_the_start_of_a_new_conversation(tmp_path):
    """T3.5 的 ConversationCleared 要能被前端用来画分隔线——
    所以分组得把它标在**下一个 turn 头上**,而不是埋在上一个 turn 的步骤里。

    语义是「这一轮开启了一段新对话」,所以**第一轮天然为真**（它开启了第一段）。
    前端画分隔线的条件因此是 `starts_conversation and 不是第一张卡`——
    与其在数据里给首轮开特例,不如让语义一致、由渲染层跳过 index 0。
    """
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "第一问"},
        {"ts": 2.0, "role": "assistant", "content": "答一"},
        {"ts": 4.0, "role": "user", "content": "第二问"},   # 同一段对话的第二轮
        {"ts": 5.0, "role": "assistant", "content": "答二"},
        {"ts": 7.0, "role": "user", "content": "第三问"},   # /clear 之后,新的一段
        {"ts": 8.0, "role": "assistant", "content": "答三"},
    ])
    write_jsonl(tmp_path / "s.events.jsonl", [
        {"ts": 6.0, "event": "ConversationCleared", "kept": 1},
    ])

    turns = load_flow(path)["turns"]

    assert [t["starts_conversation"] for t in turns] == [True, False, True]
    # 清空标记不该同时留在上一轮的步骤里(否则分隔线会画重)
    assert not [s for s in turns[1]["steps"]
                if s["kind"] == "event" and s["event"] == "ConversationCleared"]


def test_empty_or_missing_file_is_not_an_error(tmp_path):
    assert load_flow(tmp_path / "nope.jsonl")["turns"] == []
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    assert load_flow(tmp_path / "empty.jsonl")["turns"] == []


# ---- 这两条是「拿真实会话跑一遍」跑出来的,不是想出来的（见 devlog T4）

def test_a_shell_only_turn_is_not_unfinished(tmp_path):
    """`!命令` 往 session 落一条 role=user 的记录(内容是命令与输出),**不经模型**,
    所以永远等不到 assistant。形状上它和真人提问一模一样。

    早先的判据「没有收尾的 assistant 就算未完成」把它全判成 ⚠——8 个真实会话里
    有 3 个是这种,「未完成」这个信号当场从证据退化成噪音。

    改判据:**真的开工了(有 llm 步骤)却没收尾**才算未完成。不靠匹配
    「我执行了命令」那句话——用户自己就能原样打出这几个字。
    出处:真实会话 20260811-082710 / 094346 / 134625。
    """
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "system", "content": "sys"},
        {"ts": 2.0, "role": "user", "content": "我执行了命令 `echo hi`，输出：\nhi\n"},
    ])

    turn = load_flow(path)["turns"][0]

    assert turn["unfinished"] is False
    assert turn["steps"] == []


def test_an_interrupted_turn_is_still_unfinished(tmp_path):
    """反向:真的开了工又断在半路,必须照旧标出来——上一条不能把这条也放过去。

    形状抄自真实会话 20260811-134308（用户中断了 bash）：
    usage → assistant(带 tool_calls) → tool 结果「(已取消，用户中断)」→ 没有收尾 assistant。
    """
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "写一个排序函数"},
        {"ts": 2.0, "type": "usage", "step": 1, "model": "m",
         "prompt_tokens": 1033, "completion_tokens": 20},
        {"ts": 3.0, "role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "bash",
                                                  "arguments": '{"command": "python x.py"}'}}]},
        {"ts": 4.0, "role": "tool", "tool_call_id": "c1", "content": "(已取消，用户中断)"},
    ])

    turn = load_flow(path)["turns"][0]

    assert turn["unfinished"] is True
    assert [s["kind"] for s in turn["steps"]] == ["llm", "tool"]


# ---- 端到端真跑后发现：观测流里三个事件与审计流重复（devlog T7）

def test_tool_lifecycle_events_merge_into_the_tool_step(tmp_path):
    """`ToolStart`/`ToolEnd` 与审计流的 tool 记录说的是同一件事,各画一行是重影。

    但它们带着审计流**没有**的两样东西:精确耗时（start→end,审计流只能拿
    「模型发出调用」到「结果落盘」,并发批里第二个工具的耗时会含第一个的）
    和 `is_error`。所以不是丢弃,是**合并进 tool 步骤**。
    """
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "问"},
        {"ts": 2.0, "type": "usage", "step": 1, "model": "m",
         "prompt_tokens": 10, "completion_tokens": 2},
        {"ts": 2.5, "role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "bash",
                                                  "arguments": '{"command": "ls"}'}}]},
        {"ts": 5.0, "role": "tool", "tool_call_id": "c1", "content": "错误：没这个目录"},
        {"ts": 6.0, "role": "assistant", "content": "查完了"},
    ])
    write_jsonl(tmp_path / "s.events.jsonl", [
        {"ts": 3.0, "event": "ToolStart", "tool_call_id": "c1", "name": "bash", "args": {}},
        {"ts": 4.2, "event": "ToolEnd", "tool_call_id": "c1", "name": "bash", "args": {},
         "result": "错误：没这个目录", "is_error": True},
    ])

    turn = load_flow(path)["turns"][0]

    events = [s for s in turn["steps"] if s["kind"] == "event"]
    assert [e["event"] for e in events] == [], "生命周期事件不该自己占一行"
    tool = next(s for s in turn["steps"] if s["kind"] == "tool")
    assert tool["ms"] == 1200, "耗时应取 ToolStart→ToolEnd 的精确值"
    assert tool["is_error"] is True


def test_assistant_message_event_is_not_shown_twice(tmp_path):
    """`AssistantMessage` 事件与审计流的 assistant 记录是同一条消息。"""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "问"},
        {"ts": 2.0, "role": "assistant", "content": "答"},
    ])
    write_jsonl(tmp_path / "s.events.jsonl", [
        {"ts": 2.1, "event": "AssistantMessage", "content": "答", "tool_call_names": []},
    ])

    steps = load_flow(path)["turns"][0]["steps"]

    assert [s["kind"] for s in steps] == ["llm"]


def test_tool_duration_falls_back_when_there_is_no_event_stream(tmp_path):
    """老会话没有观测流:退回「模型发出调用 → 结果落盘」的近似值,并标明是近似。
    没有耗时可显示比显示一个不知来路的数字好,但完全不显示又浪费了已有信息。"""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "问"},
        {"ts": 2.0, "role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": "{}"}}]},
        {"ts": 3.5, "role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"ts": 4.0, "role": "assistant", "content": "好"},
    ])

    tool = next(s for s in load_flow(path)["turns"][0]["steps"] if s["kind"] == "tool")

    assert tool["ms"] == 1500
    assert tool["ms_approx"] is True


def test_event_payload_never_collides_with_the_step_discriminator(tmp_path):
    """浏览器里看出来的 bug:页面显示「PermissionDecided bash → event」,应是「→ allow」。

    `PermissionDecided` **自己有一个 `kind` 字段**（allow/deny），
    而步骤的判别字段也叫 `kind`（llm/tool/event）——把事件字段平铺进步骤时后者覆盖了前者。
    修法不是给这一个事件开特例（下一个撞名的字段又会中招），
    而是**把事件载荷整体放进 `data`**,结构上不可能再撞。
    """
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "问"},
        {"ts": 3.0, "role": "assistant", "content": "答"},
    ])
    write_jsonl(tmp_path / "s.events.jsonl", [
        {"ts": 2.0, "event": "PermissionDecided", "tool_call_id": "c1",
         "name": "bash", "kind": "allow", "reason": "默认决策"},
    ])

    step = next(s for s in load_flow(path)["turns"][0]["steps"] if s["kind"] == "event")

    assert step["kind"] == "event"            # 步骤判别字段
    assert step["event"] == "PermissionDecided"
    assert step["data"]["kind"] == "allow"    # 事件自己的字段,原样保住
    assert step["data"]["name"] == "bash"
    assert "ts" not in step["data"], "ts 已在步骤上，别在载荷里重复一份"


def test_turn_totals_only_sum_what_is_meaningful_to_sum(tmp_path):
    """用户 2026-08-13 指出:把各步 `prompt_tokens` 相加当「计费」是错的——
    缓存命中的 token **便宜 50 倍**（0.02 vs 1 元/M，STATUS 实测），
    按同一口径相加既不是钱也不是上下文大小。

    所以只报三个加起来有意义的数：
    - `context`：**末步**的 prompt_tokens（不是求和）——离 1M 窗口还有多远、何时触发压缩；
    - `miss`：未命中输入之和（不重叠，且这才是真正贵的部分）；
    - `tokens_out`：输出之和（每次都是新生成的，不重叠，且输出从不打折）。
    """
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "问"},
        {"ts": 2.0, "type": "usage", "step": 1, "model": "m",
         "prompt_tokens": 1000, "completion_tokens": 50,
         "prompt_cache_hit_tokens": 200, "prompt_cache_miss_tokens": 800},
        {"ts": 2.5, "role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": "{}"}}]},
        {"ts": 3.0, "role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"ts": 4.0, "type": "usage", "step": 2, "model": "m",
         "prompt_tokens": 3978, "completion_tokens": 90,
         "prompt_cache_hit_tokens": 2029, "prompt_cache_miss_tokens": 1949},
        {"ts": 5.0, "role": "assistant", "content": "答"},
    ])

    turn = load_flow(path)["turns"][0]

    assert turn["context"] == 3978, "上下文是末步的输入量，不是各步相加"
    assert turn["miss"] == 800 + 1949, "未命中才是真正花钱的那部分，且它不重叠"
    assert turn["tokens_out"] == 50 + 90


def test_miss_falls_back_when_the_provider_omits_it(tmp_path):
    """`prompt_cache_miss_tokens` 是 DeepSeek 专有字段。别家不给就用
    `prompt_tokens - 命中` 兜底——算得出来就别显示成 0（0 会被读成「全命中」）。"""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"ts": 1.0, "role": "user", "content": "问"},
        {"ts": 2.0, "type": "usage", "step": 1, "model": "m",
         "prompt_tokens": 1000, "completion_tokens": 10,
         "prompt_tokens_details": {"cached_tokens": 256}},
        {"ts": 3.0, "role": "assistant", "content": "答"},
    ])

    turn = load_flow(path)["turns"][0]

    assert turn["miss"] == 744


def test_v1_session_files_are_normalized_before_grouping(tmp_path):
    """feature 24 换了会话格式（首行 header + 信封 + 消息嵌套），viz 的读边
    要归一化回扁平形状——不然真实 pai 写出的新会话在页面上一片空白，
    而手写扁平夹具的既有测试全绿（夹具绕过了 SessionLog，测不出这层）。"""
    from pai.core.session import SessionLog

    log = SessionLog(tmp_path)
    log.append({"role": "system", "content": "s"})
    log.append({"role": "user", "content": "真格式的问题"})
    log.append({"role": "assistant", "content": "真格式的回答"})
    log.append({"type": "usage", "step": 1, "prompt_tokens": 5,
                "completion_tokens": 2, "total_tokens": 7})
    flow = load_flow(log.path)
    assert len(flow["turns"]) == 1
    assert flow["turns"][0]["user"] == "真格式的问题"
