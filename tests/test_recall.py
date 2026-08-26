"""按查询召回（feature 10 Task 4/5）：manifest → 侧查询 → 白名单 → 注入块。

照 CC findRelevantMemories 的形状，但多一层 pai 特有的东西：**侧查询是实打实的钱**，
所以空目录不发请求、连续失败就停用，且 usage 必须能回传给预算熔断。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pai.core.memory import scan_memories
from pai.core.recall import (
    MAX_RECALL_FAILURES,
    MAX_RECALL_FILES,
    RECALL_MAX_TOKENS,
    RecallState,
    build_manifest,
    make_recall,
    recall_block,
    select_memories,
)

from tests.fake_llm import FakeClient
from helpers import recall_reply as reply, write_memory


def ts(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


NOW = ts("2026-08-11 10:00")


class RaisingClient:
    """模拟网络/额度异常：召回炸了不该把整轮对话带走。"""

    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        raise RuntimeError("连接超时")


def test_manifest_line_carries_type_age_and_description(tmp_path: Path):
    write_memory(tmp_path, "构建", description="用 ./test.sh 跑测试",
                 type_="feedback", mtime=ts("2026-06-25 10:00"))
    line = build_manifest(scan_memories(tmp_path), now=NOW).strip()
    assert line == "- [feedback] 构建.md (47 天前): 用 ./test.sh 跑测试"


def test_empty_directory_short_circuits_without_a_request(tmp_path: Path):
    client = FakeClient([])
    picked, usage = select_memories("随便问点什么", scan_memories(tmp_path),
                                    client=client, model="fake", state=RecallState(), now=NOW)
    assert picked == [] and usage == {}
    assert client.requests == []            # 0 篇记忆时连请求都不该发——这是钱


def test_already_surfaced_files_are_filtered_before_the_request(tmp_path: Path):
    write_memory(tmp_path, "旧的", description="上一轮已经注入过了")
    write_memory(tmp_path, "新的", description="这轮才可能用上")
    client = FakeClient([reply(["新的.md"])])
    state = RecallState(surfaced={"旧的.md"})

    select_memories("问题", scan_memories(tmp_path), client=client, model="fake",
                    state=state, now=NOW)

    sent = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert "新的.md" in sent
    assert "旧的.md" not in sent            # 5 个名额不浪费在已经在上下文里的东西上


def test_everything_already_surfaced_means_no_request(tmp_path: Path):
    write_memory(tmp_path, "甲")
    client = FakeClient([])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(surfaced={"甲.md"}), now=NOW)
    assert picked == [] and client.requests == []


def test_whitelist_rejects_hallucinated_filenames(tmp_path: Path):
    write_memory(tmp_path, "真的")
    client = FakeClient([reply(["真的.md", "我编的.md"])])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert [h.path.name for h in picked] == ["真的.md"]


def test_caps_at_max_recall_files(tmp_path: Path):
    for i in range(MAX_RECALL_FILES + 3):
        write_memory(tmp_path, f"m{i}")
    client = FakeClient([reply([f"m{i}.md" for i in range(MAX_RECALL_FILES + 3)])])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert len(picked) == MAX_RECALL_FILES   # prompt 里写了上限，代码这里再兜一层


def test_defensive_json_parsing_survives_fenced_output(tmp_path: Path):
    """不靠 provider 的 schema 强制：DeepSeek 兼容层未必支持严格 json_schema。"""
    write_memory(tmp_path, "甲")
    client = FakeClient([{"content": '好的：\n```json\n{"selected": ["甲.md"]}\n```\n'}])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert [h.name for h in picked] == ["甲"]


def test_unparseable_reply_degrades_to_empty(tmp_path: Path):
    write_memory(tmp_path, "甲")
    client = FakeClient([{"content": "我不想输出 JSON"}])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert picked == []


def test_client_exception_degrades_to_empty_without_raising(tmp_path: Path):
    write_memory(tmp_path, "甲")
    picked, usage = select_memories("问题", scan_memories(tmp_path), client=RaisingClient(),
                                    model="fake", state=RecallState(), now=NOW)
    assert picked == [] and usage == {}


def test_disables_after_consecutive_failures(tmp_path: Path):
    """CC 是「失败返回空、不阻断」；在 pai 那等于每轮白打一次请求，所以要熔断。"""
    write_memory(tmp_path, "甲")
    client = RaisingClient()
    state = RecallState()
    headers = scan_memories(tmp_path)
    for _ in range(MAX_RECALL_FAILURES + 2):
        select_memories("问题", headers, client=client, model="fake", state=state, now=NOW)
    assert state.disabled
    assert client.calls == MAX_RECALL_FAILURES


def test_success_resets_the_failure_count(tmp_path: Path):
    write_memory(tmp_path, "甲")
    headers = scan_memories(tmp_path)
    state = RecallState(failures=MAX_RECALL_FAILURES - 1)
    select_memories("问题", headers, client=FakeClient([reply(["甲.md"])]),
                    model="fake", state=state, now=NOW)
    assert state.failures == 0 and not state.disabled


def test_returns_usage_so_the_budget_can_count_it(tmp_path: Path):
    write_memory(tmp_path, "甲")
    client = FakeClient([reply(["甲.md"], usage={"total_tokens": 123})])
    _, usage = select_memories("问题", scan_memories(tmp_path), client=client,
                               model="fake", state=RecallState(), now=NOW)
    assert usage.get("total_tokens") == 123


def test_selected_files_are_recorded_as_surfaced(tmp_path: Path):
    write_memory(tmp_path, "甲")
    state = RecallState()
    select_memories("问题", scan_memories(tmp_path), client=FakeClient([reply(["甲.md"])]),
                    model="fake", state=state, now=NOW)
    assert state.surfaced == {"甲.md"}


def test_prompt_carries_the_two_denoising_rules(tmp_path: Path):
    """CC 的选择器提示里写着「不确定就别选，宁可返回空」与「最多 5 篇」——
    写进 prompt 而不只在代码里截断，因为它约束的是模型的判断倾向。"""
    write_memory(tmp_path, "甲")
    client = FakeClient([reply([])])
    select_memories("问题", scan_memories(tmp_path), client=client, model="fake",
                    state=RecallState(), now=NOW)
    sent = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert "宁可" in sent and "空" in sent
    assert str(MAX_RECALL_FILES) in sent
    assert client.requests[0]["max_tokens"] == RECALL_MAX_TOKENS


# ---- Task 5：注入块 ----


def test_block_is_wrapped_in_a_system_reminder(tmp_path: Path):
    write_memory(tmp_path, "甲", description="d", body="正文内容")
    block = recall_block(scan_memories(tmp_path), now=NOW)
    assert block.startswith("<system-reminder>") and block.rstrip().endswith("</system-reminder>")
    assert "正文内容" in block                  # 召回是把**全文**塞进上下文


def test_block_declares_it_is_background_not_an_instruction(tmp_path: Path):
    write_memory(tmp_path, "甲")
    block = recall_block(scan_memories(tmp_path), now=NOW)
    assert "背景" in block and "不是用户指令" in block


def test_block_warns_about_stale_memories(tmp_path: Path):
    write_memory(tmp_path, "旧", mtime=ts("2026-06-25 10:00"))
    assert "file:line" in recall_block(scan_memories(tmp_path), now=NOW)


def test_block_does_not_warn_about_fresh_memories(tmp_path: Path):
    write_memory(tmp_path, "新", mtime=ts("2026-08-11 09:00"))
    assert "file:line" not in recall_block(scan_memories(tmp_path), now=NOW)


def test_block_is_empty_when_nothing_was_selected():
    assert recall_block([], now=NOW) == ""     # 空串 → loop 不插消息


# ---- Task 7：装配层闭包 + 真实轨迹 ----


def test_make_recall_returns_block_and_usage(tmp_path: Path):
    from pai.core.recall import make_recall

    write_memory(tmp_path, "甲", description="d", body="记忆正文")
    client = FakeClient([reply(["甲.md"], usage={"total_tokens": 7})])
    recall = make_recall(client=client, model="fake", directory=tmp_path, state=RecallState())

    text, usage = recall("问题")
    assert "记忆正文" in text
    assert usage["total_tokens"] == 7


def test_make_recall_on_empty_directory_costs_nothing(tmp_path: Path):
    from pai.core.recall import make_recall

    client = FakeClient([])
    recall = make_recall(client=client, model="fake", directory=tmp_path, state=RecallState())
    assert recall("问题") == ("", {})
    assert client.requests == []


def test_real_trajectory_query_flows_through_recall_and_compaction(tmp_path: Path):
    """真数据当输入（AGENTS.md 测试规约）：真实中文 query 走一遍召回，
    注入块再进压缩的体积计算——编的字符串测不出中文与真实消息结构这类坑。"""
    from pai.core.compaction import context_tokens, find_cut_point
    from pai.core.recall import make_recall

    from trajectories import REAL_USAGE_TRAJECTORY

    write_memory(tmp_path, "usage-check", description="创建文件再读回的老套路")
    query = [m for m in REAL_USAGE_TRAJECTORY if m["role"] == "user"][0]["content"]
    client = FakeClient([reply(["usage-check.md"])])
    recall = make_recall(client=client, model="fake", directory=tmp_path, state=RecallState())

    text, _ = recall(query)
    assert "usage-check" in text
    # 真实中文 query 原样进了 manifest 请求，没在拼串处被吃掉
    assert query in json.dumps(client.requests[0]["messages"], ensure_ascii=False)

    messages = [dict(m) for m in REAL_USAGE_TRAJECTORY] + [{"role": "user", "content": text}]
    assert context_tokens(messages, []) > context_tokens(list(REAL_USAGE_TRAJECTORY), [])
    assert find_cut_point(messages, [], keep_recent_tokens=50) <= len(messages)


# ---- 2026-08-11 真跑冒烟抓到的两个 bug（遗留 1 的兑现） ----


def test_max_tokens_leaves_room_for_reasoning_tokens():
    """**别把这个数改回 256**。实测（pai_playground/smoke/recall_max_tokens.py）：

    `deepseek-v4-flash` 是推理模型，`reasoning_tokens` **计进 `max_tokens`**——
    同一个 query 三次，reasoning 分别烧掉 218 / 112 / 1941 token。
    CC 那个 256 是给不推理的 Sonnet 档定的，照抄过来的后果是
    **预算被思考吃光、`content` 恒为空字符串**，而且是概率性的（有时刚好够）。

    对推理模型来说 `max_tokens` 不是「省钱旋钮」而是「截断风险旋钮」——
    实际计费按真实用量走，把上限调高不额外花钱，调低却会静默丢结果。
    """
    assert RECALL_MAX_TOKENS >= 2048


def test_selection_tolerates_manifest_line_decoration(tmp_path: Path):
    """真实模型会把 manifest 行的装饰一起抄回来：实测回的是 `"[feedback] 构建约定.md"`。

    白名单原本要求逐字相等，于是**100% 的选择结果被静默丢掉**——
    离线测试全绿，真跑却永远召回不到任何东西。
    """
    write_memory(tmp_path, "构建约定", type_="feedback")
    client = FakeClient([reply(["[feedback] 构建约定.md (今天)"])])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert [h.name for h in picked] == ["构建约定"]


def test_whitelist_still_rejects_decorated_hallucinations(tmp_path: Path):
    """放宽匹配不等于放弃白名单：装饰里找不到已知文件名的，照样丢掉。"""
    write_memory(tmp_path, "真的")
    client = FakeClient([reply(["[project] 我编的.md (今天)"])])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert picked == []


def test_longest_match_wins_when_one_filename_contains_another(tmp_path: Path):
    """子串匹配的经典坑：`a.md` 也是 `xa.md` 的子串，得取最长的那个。"""
    write_memory(tmp_path, "a")
    write_memory(tmp_path, "xa")
    client = FakeClient([reply(["[project] xa.md"])])
    picked, _ = select_memories("问题", scan_memories(tmp_path), client=client,
                                model="fake", state=RecallState(), now=NOW)
    assert [h.name for h in picked] == ["xa"]


def test_unparseable_reply_counts_as_a_failure(tmp_path: Path):
    """「模型没说话」与「模型明确说一篇都不选」必须分得开——

    前者是故障（真跑时 content 恒为空就属于这类），后者是正常判断。
    混为一谈的后果：故障永远触发不了熔断，也永远发不出事件，用户看不到任何异常。
    """
    write_memory(tmp_path, "甲")
    state = RecallState()
    select_memories("问题", scan_memories(tmp_path), client=FakeClient([{"content": ""}]),
                    model="fake", state=state, now=NOW)
    assert state.failures == 1


def test_explicit_empty_selection_is_not_a_failure(tmp_path: Path):
    write_memory(tmp_path, "甲")
    state = RecallState()
    select_memories("问题", scan_memories(tmp_path), client=FakeClient([reply([])]),
                    model="fake", state=state, now=NOW)
    assert state.failures == 0


def test_failures_notify_the_assembly_layer(tmp_path: Path):
    """召回失败必须能被看见（压缩那边的熔断至少会发 CompactionSkipped，召回原本全静默）。

    工具/核心模块不认识事件系统——照 memory_tool 的做法回调出去，由装配层发事件。
    """
    write_memory(tmp_path, "甲")
    seen: list = []
    state = RecallState()
    headers = scan_memories(tmp_path)
    for _ in range(MAX_RECALL_FAILURES):
        select_memories("问题", headers, client=RaisingClient(), model="fake",
                        state=state, now=NOW, on_failure=seen.append)

    assert [f.reason for f in seen] == ["request_failed"] * MAX_RECALL_FAILURES
    assert "连接超时" in seen[0].detail
    assert [f.disabled for f in seen] == [False, False, True]   # 最后一次带上「已停用」


def test_prompt_tells_the_model_to_return_bare_filenames(tmp_path: Path):
    """从源头减少歧义：manifest 行前面有 `[type]`，不说清楚模型就会连着抄。"""
    write_memory(tmp_path, "甲")
    client = FakeClient([reply([])])
    select_memories("问题", scan_memories(tmp_path), client=client, model="fake",
                    state=RecallState(), now=NOW)
    sent = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert ".md" in sent and "只写文件名" in sent


# ---- feature 17 task 2：成功召回也要发事件（此前只有失败发事件，成功是哑的）

def test_successful_recall_reports_which_memories_were_injected(tmp_path: Path):
    """「召回选了哪几篇」此前一点痕迹都不留:失败有 RecallFailed,成功什么都没有。

    观测流里少了这一条,页面上就只能显示「召回过」而说不出「召回了什么」。
    """
    write_memory(tmp_path, "甲", description="第一篇")
    write_memory(tmp_path, "乙", description="第二篇")
    seen = []
    recall = make_recall(client=FakeClient([reply(["甲.md", "乙.md"])]), model="m",
                         directory=tmp_path, state=RecallState(),
                         on_selected=lambda names: seen.append(names))

    recall("问题")

    assert seen == [("甲.md", "乙.md")]


def test_no_event_when_nothing_is_selected(tmp_path: Path):
    """明确不选是正常结果,不是「注入了 0 篇」——发个空事件只会在页面上刷噪音。"""
    write_memory(tmp_path, "甲", description="第一篇")
    seen = []
    recall = make_recall(client=FakeClient([reply([])]), model="m", directory=tmp_path,
                         state=RecallState(), on_selected=lambda names: seen.append(names))

    recall("问题")

    assert seen == []


def test_no_event_when_the_side_query_fails(tmp_path: Path):
    """失败路径归 on_failure 管,不许两个回调同时响。"""
    write_memory(tmp_path, "甲", description="第一篇")
    seen, failures = [], []
    recall = make_recall(client=FakeClient([{"content": "我不想输出 JSON"}]), model="m",
                         directory=tmp_path, state=RecallState(),
                         on_failure=failures.append, on_selected=seen.append)

    recall("问题")

    assert seen == [] and len(failures) == 1


# ---- 单篇字符上限（2026-08-19 走读发现，PAI-04 诚实边界）----


def test_a_huge_memory_is_truncated_before_it_reaches_the_context(tmp_path: Path):
    """`MAX_RECALL_FILES = 5` 只限篇数，正文是整篇读进来的：写一篇特别长的记忆，
    召回一次就把它整个顶进上下文，而估算的尾部预算根本没算它。
    工具输出在源头截到 4000 字符，召回这条路此前不走任何截断。"""
    from pai.core.recall import MAX_RECALL_CHARS

    write_memory(tmp_path, "长", description="d", body="正" * (MAX_RECALL_CHARS * 3))
    block = recall_block(scan_memories(tmp_path), now=NOW)
    assert len(block) < MAX_RECALL_CHARS * 2, "整篇塞进来就等于没有上限"
    assert "截断" in block, "截断必须说出来（静默失败是 bug）"
    assert str(MAX_RECALL_CHARS) in block


def test_a_normal_memory_is_not_touched(tmp_path: Path):
    """反向守卫：没超上限的一个字都不许动——召回的价值就是全文。"""
    write_memory(tmp_path, "甲", description="d", body="正文内容")
    block = recall_block(scan_memories(tmp_path), now=NOW)
    assert "正文内容" in block and "截断" not in block
