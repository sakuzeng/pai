"""阶段 1 第 1-2 步：token 秤 + 警戒线 + 对话拍平机。

三个都是纯函数（进参数出结果，不联网不读文件），所以全部离线可测。
真实轨迹夹具（`REAL_TRAJECTORY` 等）住 tests/trajectories.py，出处与诚实边界写在那里。
"""

from pai.core.compaction import (
    CompactionSettings,
    estimate_tokens,
    serialize_conversation,
    should_compact,
)
# 真实轨迹夹具的家在 tests/trajectories.py（feature 40）：它被 6 个测试文件用，
# 住在这里等于「测试文件 A import 测试文件 B」
from trajectories import (
    REAL_TRAJECTORY,
    REAL_USAGE_STEPS,
    REAL_USAGE_TRAJECTORY,
)



# ---------- estimate_tokens ----------


def test_user_message_token_estimate():
    """官方系数：1 个英文字符 ≈ 0.3 token（refs/deepseek-api/quick_start/token_usage.md）。

    这条推翻了最初钉的 `400 字符 = 100 token`（chars/4）——那是通用经验值，
    官方给了 DeepSeek 自己的分词比例，没理由继续用估的。
    """
    msg = {"role": "user", "content": "a" * 400}
    assert estimate_tokens(msg) == 120  # 400 × 0.3


def test_system_and_tool_messages_counted_like_text():
    assert estimate_tokens({"role": "system", "content": "a" * 400}) == 120
    assert estimate_tokens({"role": "tool", "tool_call_id": "x", "content": "a" * 400}) == 120


def test_chinese_costs_twice_as_much_as_english():
    """1 个中文字符 ≈ 0.6 token，正好是英文的两倍。旧的一刀切 chars/4 对中文低估 2.4 倍。"""
    zh = estimate_tokens({"role": "user", "content": "中" * 400})
    en = estimate_tokens({"role": "user", "content": "a" * 400})
    assert zh == 240  # 400 × 0.6
    assert zh == 2 * en


def test_mixed_content_counted_per_character():
    """中英混排按字符分别计，不是按整条消息挑一个系数。"""
    assert estimate_tokens({"role": "user", "content": "中" * 100 + "a" * 100}) == 90  # 60+30


def test_cjk_punctuation_counted_as_chinese():
    """全角标点（，。「」）属于中文侧。中文正文里它们占比不低，算错会系统性偏低。"""
    assert estimate_tokens({"role": "user", "content": "，" * 100}) == 60
    assert estimate_tokens({"role": "user", "content": "," * 100}) == 30  # 半角是英文侧


def test_partial_token_rounds_up():
    """向上取整：3 个字符也得是 1 个 token，低估比高估危险（低估 = 压得太晚 = 爆窗口）。"""
    assert estimate_tokens({"role": "user", "content": "abc"}) == 1  # 0.9 → 1
    assert estimate_tokens({"role": "user", "content": ""}) == 0


def test_assistant_with_tool_calls_is_bigger():
    """tool_calls 的 arguments 是 JSON 字符串，必须算进去，否则整段轨迹严重低估。"""
    text_only = {"role": "assistant", "content": "a" * 400}
    with_calls = {
        "role": "assistant",
        "content": "a" * 400,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "write_file", "arguments": '{"path": "x.txt", "content": "hi"}'},
            }
        ],
    }
    assert estimate_tokens(with_calls) > estimate_tokens(text_only)


def test_assistant_with_null_content_does_not_crash():
    """loop.py 里 content=msg.content，模型只发 tool_calls 不说话时它就是 None。"""
    msg = {"role": "assistant", "content": None}
    assert estimate_tokens(msg) == 0

    with_calls = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "bash", "arguments": '{"command": "ls"}'},
            }
        ],
    }
    assert estimate_tokens(with_calls) > 0


def test_unknown_role_is_still_weighed(monkeypatch):
    """未知 role 也照常称重（R#5 裁决，推翻 D#8 的「记 0」）。

    D#6 定过：低估是唯一会炸窗口的方向，而记 0 是最极端的低估——
    一条 `developer` role 的长消息真在上下文里占着位置，秤上却是 0。
    宁可高估：按 content + tool_calls 与已知 role 同算法估。
    """
    known = estimate_tokens({"role": "user", "content": "a" * 400})
    assert estimate_tokens({"role": "developer", "content": "a" * 400}) == known
    assert estimate_tokens({"content": "a" * 400}) == known


def test_unknown_role_still_counts_its_tool_calls():
    """未知 role 上挂 tool_calls 是畸形输入，但畸形的那份 token 照样要付钱。"""
    weird = {
        "role": "developer",
        "content": None,
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": "x" * 2000}}],
    }
    assert estimate_tokens(weird) > 500


# ---------- should_compact ----------


def test_should_compact_threshold_is_strictly_greater():
    s = CompactionSettings(reserve_tokens=200)
    assert should_compact(800, 1000, s) is False  # 1000-200=800，正好压线不压
    assert should_compact(801, 1000, s) is True
    assert should_compact(0, 1000, s) is False


def test_should_compact_respects_disabled_flag():
    s = CompactionSettings(reserve_tokens=200, enabled=False)
    assert should_compact(999_999, 1000, s) is False


def test_should_compact_default_settings():
    s = CompactionSettings()  # reserve_tokens=16384
    assert should_compact(10, 64_000, s) is False
    assert should_compact(47_616, 64_000, s) is False  # 64000-16384，压线
    assert should_compact(47_617, 64_000, s) is True


def test_reserve_is_absolute_not_proportional():
    """预留量是绝对值，不随窗口缩放——这是它相对百分比阈值的全部意义。

    旧实现 `tokens > window * 0.8` 在大窗口上会过早触发：200k 窗口下 160k 就压，
    但那时离真正装不下还有 4 万 token 的余量，白白丢掉一次缓存和一段完整历史。
    """
    s = CompactionSettings(reserve_tokens=16_384)
    assert should_compact(170_000, 200_000, s) is False  # 旧的百分比算法会误判为 True
    assert should_compact(183_616, 200_000, s) is False  # 200000-16384，压线
    assert should_compact(183_617, 200_000, s) is True

    # 同一个 reserve，小窗口下相当于更大的比例——这正是想要的行为
    assert should_compact(48_000, 64_000, s) is True  # 64k 窗口下 48k 就该压了


def test_window_smaller_than_reserve_always_triggers():
    """已知退化情形：窗口本身小于预留量时恒为 True。

    此时压缩救不了（压完仍超线），会变成无限压缩循环——CC 因为没挡住这个，
    单会话出现过 3272 次连续失败（见 decisions 第 14 条）。
    should_compact 如实回答"你超线了"是对的，防循环属于上层熔断器的职责，
    随自动压缩一起实现。这条测试是把该缺口钉在明面上，不是认可它。
    """
    s = CompactionSettings(reserve_tokens=16_384)
    assert should_compact(0, 8_000, s) is True


# ---------- serialize_conversation ----------


def test_serialize_keeps_roles_and_tool_calls():
    text = serialize_conversation(
        [
            {"role": "user", "content": "写个文件"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "write_file", "arguments": '{"path": "x.txt"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "已写入 x.txt"},
        ]
    )
    assert "user:" in text
    assert "写个文件" in text
    assert "write_file" in text
    assert '{"path": "x.txt"}' in text
    assert "已写入 x.txt" in text
    assert "call_1" in text  # tool 结果要能对回是哪次调用


def test_serialize_skips_unknown_role():
    """拍平仍然跳过未知 role——与秤的裁决（R#5：照常估）刻意不一致。

    两处问的不是同一个问题：秤问「它占不占窗口」（占，所以要称），
    拍平问「要不要把它塞进摘要请求」（不认识的东西不塞）。
    """
    text = serialize_conversation([{"role": "developer", "content": "机密"}])
    assert text == ""


def test_serialize_truncates_long_content():
    """单条超长（多半是 tool 结果）按 5000 字符截断，且要说清截掉了多少。"""
    text = serialize_conversation([{"role": "tool", "tool_call_id": "c1", "content": "x" * 8000}])
    assert "[... 3000 more characters truncated]" in text
    assert text.count("x") == 5000


def test_serialize_truncation_limit_is_configurable():
    text = serialize_conversation(
        [{"role": "user", "content": "y" * 100}], max_chars=30
    )
    assert "[... 70 more characters truncated]" in text
    assert text.count("y") == 30


def test_serialize_truncates_long_tool_call_arguments():
    """一次 write_file 就能塞进几万字符的 arguments，它同样要被截。"""
    text = serialize_conversation(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "write_file", "arguments": "z" * 8000},
                    }
                ],
            }
        ]
    )
    assert "[... 3000 more characters truncated]" in text
    assert text.count("z") == 5000


# ---------- 真实轨迹 ----------


def test_real_trajectory_estimate_between_pure_english_and_pure_chinese():
    """真数据当考题：中英混排轨迹的估算，必须落在「全英文」与「全中文」两个边界之间。

    这个区间不是拍脑袋定的，是算法本身的数学下界与上界——只要系数用对、字符没漏算，
    结果必然落在里面。比写死一个数字更能抓真问题（漏算 arguments 会跌破下界）。
    """
    chars = sum(
        len(m.get("content") or "")
        + sum(
            len(c["function"]["name"]) + len(c["function"]["arguments"])
            for c in m.get("tool_calls") or []
        )
        for m in REAL_TRAJECTORY
    )
    total = sum(estimate_tokens(m) for m in REAL_TRAJECTORY)
    assert 0.3 * chars < total < 0.6 * chars


def test_real_trajectory_chinese_correction_is_material():
    """校准前后的差值要够大，否则这次改动不值当。

    旧算法（chars/4）对这条中英混排轨迹估出 161 token；官方系数下应显著更高。
    """
    total = sum(estimate_tokens(m) for m in REAL_TRAJECTORY)
    assert total > 161 * 1.3


def test_real_trajectory_every_message_counted():
    """9 条消息里没有一条被算成 0——role 拼写、None content 任一处漏了都会露馅。"""
    assert len(REAL_TRAJECTORY) == 9
    assert all(estimate_tokens(m) > 0 for m in REAL_TRAJECTORY)


def test_real_trajectory_serialize_is_lossless_enough():
    """拍平后摘要模型该看到的东西：任务、三次命令、那条 sed 失败、最终结论。"""
    text = serialize_conversation(REAL_TRAJECTORY)
    assert "创建 tri.txt" in text
    assert "printf" in text
    assert "undefined label" in text  # 失败信息不能被拍没，否则摘要会漏掉"踩过的坑"
    assert "perl -pi -e" in text
    assert "其余两行保持不动" in text
    assert text.count("call_00_") >= 6  # 3 次调用 + 3 条结果


def test_real_trajectory_serialize_shorter_than_raw_json():
    """拍平的意义之一：比直接 json.dumps 省掉一堆结构噪音。"""
    import json

    raw = json.dumps(REAL_TRAJECTORY, ensure_ascii=False)
    assert len(serialize_conversation(REAL_TRAJECTORY)) < len(raw)


# ---------- estimate_request_tokens ----------


def test_request_tokens_without_tools_equals_message_tokens():
    from pai.core.compaction import estimate_conversation_tokens, estimate_request_tokens

    msgs = [{"role": "user", "content": "你好 hello"}]
    assert estimate_request_tokens(msgs) == estimate_conversation_tokens(msgs)


def test_request_tokens_include_tool_schemas():
    """真实 prompt_tokens 含工具 schema——只估 messages 会系统性低估，且低估量恒定不随对话增长。"""
    from pai.core.compaction import estimate_conversation_tokens, estimate_request_tokens

    msgs = [{"role": "user", "content": "写个文件"}]
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "覆盖写文件",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }
    ]
    assert estimate_request_tokens(msgs, schemas) > estimate_conversation_tokens(msgs)


def test_request_tokens_real_tool_schemas_are_not_negligible():
    """pai 现有四个工具的 schema 开销必须有实感——这正是"估算 vs usage"对不上的主因。"""
    from pai.core.compaction import estimate_request_tokens
    from pai.core.tools import get_tools

    schemas = [t.schema() for t in get_tools().values()]
    assert estimate_request_tokens([], schemas) > 100



# 录制 REAL_USAGE_STEPS 时的工具 schema 快照，**刻意冻结**，不用 get_tools() 取活的。
# 理由：上面那些真实 token 数是在这套 schema 下测出来的；若测试读活 schema，
# 将来改一句工具描述就会让断言假失败，且报错说「误差过大」而不是「你改了工具描述」。
# 冻结后二者解耦：改工具不会打扰这条测试，而这条测试也不再假装能验证当前工具集。
FROZEN_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取一个文件的全部内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径（相对或绝对）"
                    }
                },
                "required": [
                    "path"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把内容写入文件（覆盖式，文件不存在则创建）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "写入的完整内容（会覆盖原文件）"
                    }
                },
                "required": [
                    "path",
                    "content"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "精确替换文件中的一段文本：old 必须在文件中唯一出现一次。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的文件路径"
                    },
                    "old": {
                        "type": "string",
                        "description": "要被替换的原文本，必须在文件中唯一出现一次"
                    },
                    "new": {
                        "type": "string",
                        "description": "替换后的新文本"
                    }
                },
                "required": [
                    "path",
                    "old",
                    "new"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在 shell 里执行一条命令并返回它的输出（stdout+stderr）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令"
                    }
                },
                "required": [
                    "command"
                ]
            }
        }
    }
]


def test_context_tokens_without_anchor_falls_back_to_pure_estimate():
    """首次请求没有 usage 可锚，只能纯估——那时上下文才几百 token，离阈值差几个数量级。"""
    from pai.core.compaction import context_tokens, estimate_request_tokens

    msgs = REAL_USAGE_TRAJECTORY[:2]
    schemas = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
    assert context_tokens(msgs, schemas) == estimate_request_tokens(msgs, schemas)


def test_context_tokens_ignores_everything_before_the_anchor():
    """锚之前的消息再大也不参与计算——这正是系统性误差被隔离掉的原因。"""
    from pai.core.compaction import context_tokens

    huge = [{"role": "user", "content": "x" * 100_000}]
    tail = [{"role": "tool", "tool_call_id": "c", "content": "ok"}]
    a = context_tokens(huge + tail, None, anchor=1000, anchor_index=1)
    b = context_tokens([{"role": "user", "content": "tiny"}] + tail, None, anchor=1000, anchor_index=1)
    assert a == b


def test_context_tokens_adds_only_the_tail_estimate():
    from pai.core.compaction import context_tokens, estimate_conversation_tokens

    msgs = REAL_USAGE_TRAJECTORY
    tail = msgs[4:]
    assert context_tokens(msgs, None, anchor=800, anchor_index=4) == 800 + estimate_conversation_tokens(tail)


def test_anchored_estimate_beats_pure_estimate_on_real_usage():
    """真实数据当考题：锚定法误差须 < 5%，而纯估算在同一批数据上错了 30% 以上。

    锚的构成 = 上一步真实 prompt_tokens + 该步真实 completion_tokens。
    加 completion_tokens 是因为紧随其后的那条 assistant 消息，其真实 token 数就是它——
    白送的精确值，不用估。
    """
    from pai.core.compaction import context_tokens, estimate_request_tokens

    schemas = FROZEN_TOOL_SCHEMAS  # 冻结的，不用 get_tools()——见常量处说明
    # 每步请求包含的消息数：2（system+user）、4、6
    sent_counts = [2, 4, 6]

    anchor = None
    anchor_index = 0
    for (usage, count) in zip(REAL_USAGE_STEPS, sent_counts):
        msgs = REAL_USAGE_TRAJECTORY[:count]
        real = usage["prompt_tokens"]
        predicted = context_tokens(msgs, schemas, anchor=anchor, anchor_index=anchor_index)
        if anchor is not None:  # 第一步无锚，不纳入精度考核
            assert abs(predicted - real) / real < 0.05, f"步 {usage['step']} 误差过大"
            assert abs(estimate_request_tokens(msgs, schemas) - real) / real > 0.30
        anchor = real + usage["completion_tokens"]
        anchor_index = count + 1  # +1：那条 assistant 消息已被 completion_tokens 覆盖


# ---------- AnchorBook ----------


class TestFindCutPoint:
    def _msgs(self, n):
        out = [{"role": "system", "content": "s"}]
        for i in range((n - 1) // 2):
            out.append({"role": "assistant", "content": None,
                        "tool_calls": [{"id": f"c{i}", "type": "function",
                                        "function": {"name": "bash", "arguments": "{}"}}]})
            out.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"})
        return out

    def test_cuts_at_anchor_keeping_recent_budget(self):
        from pai.core.compaction import find_cut_point

        msgs = self._msgs(9)                       # system + 4 轮 (assistant, tool)
        anchors = [(3, 100), (5, 300), (7, 600), (9, 1000)]
        # 从最新往回累计真实差值：9←7 是 400，>=350 即停 → 切在下标 7
        assert find_cut_point(msgs, anchors, keep_recent_tokens=350) == 7

    def test_never_starts_kept_segment_with_tool_result(self):
        """切点铁律：落在 role=tool 上就前移到该轮 assistant——绝不产生孤儿 tool_result。"""
        from pai.core.compaction import find_cut_point

        msgs = self._msgs(9)
        anchors = [(4, 100), (6, 300), (8, 600)]   # 锚故意落在 tool 消息下标上
        cut = find_cut_point(msgs, anchors, keep_recent_tokens=250)
        assert msgs[cut]["role"] != "tool"

    def test_returns_1_when_nothing_can_be_cut(self):
        """锚不足两个 / 预算大到全保留 → 返回 1（无可压）。调用方按锚数分流：
        锚不足两个是压缩节奏里的正常一步，走静默进度；锚已够两个才是真无可压，才升级为警告。"""
        from pai.core.compaction import find_cut_point

        msgs = self._msgs(9)
        assert find_cut_point(msgs, [], keep_recent_tokens=100) == 1
        assert find_cut_point(msgs, [(9, 50)], keep_recent_tokens=100) == 1
        anchors = [(3, 100), (9, 200)]
        assert find_cut_point(msgs, anchors, keep_recent_tokens=99999) == 1


class TestAnchorBook:
    def test_records_and_latest(self):
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        assert book.latest() == (None, 0)      # 无锚时 context_tokens 走纯估算
        book.record(3, 1000)                   # 第 1 轮后：messages 前 3 条 = 1000 真实 token
        book.record(5, 1075)
        assert book.latest() == (5, 1075)
        assert book.entries == [(3, 1000), (5, 1075)]

    def test_anchor_fields_are_named_and_ordered_like_entries(self):
        """02 终审 Minor#6：latest() 曾返回 (tokens, index)，与 entries 的
        (index, tokens) 相反——位置解包的调用方一旦记反就是静默错账。
        改成具名字段之后，序不再是调用方要背下来的隐式契约。"""
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        book.record(5, 1075)
        anchor = book.latest()
        assert anchor.index == 5
        assert anchor.tokens == 1075
        assert book.entries[-1].index == 5     # entries 与 latest() 同一种东西
        assert book.entries[-1].tokens == 1075

    def test_empty_book_latest_is_also_named(self):
        """无锚这条退化路径同样要能按名取——否则调用方还得为它写第二套解包。"""
        from pai.core.compaction import AnchorBook

        anchor = AnchorBook().latest()
        assert anchor.index is None
        assert anchor.tokens == 0

    def test_turn_cost_is_adjacent_difference(self):
        """D#32：第 N 轮新增消息的真实成本 = 相邻锚差值——实测 42/33/43 的那套语义。"""
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        book.record(3, 100)
        book.record(5, 142)
        book.record(7, 175)
        costs = [b - a for (_, a), (_, b) in zip(book.entries, book.entries[1:])]
        assert costs == [42, 33]

    def test_no_anchor_is_index_none_not_tokens_zero(self):
        """无锚这条退化路径的判据必须是 index is None，不能是 tokens == 0。

        锚簿空时 latest() 给 Anchor(None, 0)；调用方若拿 tokens 当锚传下去，
        context_tokens 会以为「真有个 0 token 的锚」而走锚定分支——
        工具 schema 那几百 token 就此从账上消失（锚定分支只估锚之后的消息）。
        两条路的结果不同，这条断言就是不同本身。
        """
        from pai.core.compaction import AnchorBook, context_tokens

        msgs = [{"role": "user", "content": "hi"}]
        schemas = [{"type": "function", "function": {"name": "bash",
                                                     "description": "x" * 400}}]
        latest = AnchorBook().latest()
        assert latest.index is None

        pure = context_tokens(msgs, schemas, anchor=None, anchor_index=0)
        as_if_anchored = context_tokens(msgs, schemas, anchor=latest.tokens,
                                        anchor_index=latest.index or 0)
        assert pure > as_if_anchored     # 差的就是被漏掉的工具 schema

    def test_reset_clears_everything(self):
        """压缩改写历史后旧锚全部作废（D#18/D#32 前提：append-only）。"""
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        book.record(3, 1000)
        book.reset()
        assert book.latest() == (None, 0)
        assert book.entries == []


# ---------- TestSummarize ----------


class TestSummarize:
    def _msgs(self):
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "建个文件"},
            {"role": "assistant", "content": "好的，done"},
        ]

    def test_flat_style_feeds_serialized_text_without_system(self):
        from fake_llm import FakeClient
        from pai.core.compaction import summarize

        client = FakeClient([{"content": "摘要文本", "usage": {"prompt_tokens": 10,
                             "completion_tokens": 5, "total_tokens": 15}}])
        text, usage = summarize(self._msgs(), client=client, model="fake", style="flat")
        assert text == "摘要文本"
        assert usage["total_tokens"] == 15
        sent = client.requests[0]["messages"]
        assert len(sent) == 2                       # system(指令) + user(拍平文本)
        assert "sys" not in sent[1]["content"]      # R#16：原 system 不进拍平文本
        assert "建个文件" in sent[1]["content"]
        assert "tools" not in client.requests[0]    # 摘要请求不带工具

    def test_raw_style_sends_original_messages(self):
        from fake_llm import FakeClient
        from pai.core.compaction import summarize

        client = FakeClient([{"content": "s", "usage": {"total_tokens": 1}}])
        summarize(self._msgs(), client=client, model="fake", style="raw")
        sent = client.requests[0]["messages"]
        assert {"role": "user", "content": "建个文件"} in sent   # 原消息原样在场
        assert sent[-1]["role"] == "user" and "摘要" in sent[-1]["content"]  # 末尾追加摘要指令
        assert all(m["role"] != "system" for m in sent)  # 仲裁 2026-08-09：raw 同样不带 system——原 system 会诱导「继续干活」

    def test_instructions_override_default(self):
        from fake_llm import FakeClient
        from pai.core.compaction import SUMMARY_INSTRUCTIONS, summarize

        client = FakeClient([{"content": "s", "usage": {}}])
        summarize(self._msgs(), client=client, model="fake", instructions="只保留文件名")
        joined = "".join(m["content"] for m in client.requests[0]["messages"])
        assert "只保留文件名" in joined and SUMMARY_INSTRUCTIONS[:8] not in joined


# ---------- TestCompactAndBreaker ----------


class TestCompactAndBreaker:
    def _msgs(self):
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "recent"},
        ]

    def test_compact_rebuilds_with_summary_as_user(self):
        from fake_llm import FakeClient
        from pai.core.compaction import compact

        client = FakeClient([{"content": "这是摘要",
                              "usage": {"prompt_tokens": 30, "completion_tokens": 12,
                                        "total_tokens": 42}}])
        new, summary, usage = compact(self._msgs(), cut=3, client=client, model="fake")
        assert summary == "这是摘要"
        assert usage["total_tokens"] == 42     # 摘要请求自己的 usage 也要透传给调用方入账
        assert new[0] == {"role": "system", "content": "sys"}       # system 原样保留
        assert new[1]["role"] == "user" and "这是摘要" in new[1]["content"]
        assert new[2:] == self._msgs()[3:]                           # 保留尾原样
        assert all(m["role"] != "tool" for m in new[:3])

    def test_verify_counts_failure_only_on_real_usage_still_over(self):
        """D#34：成败只认压缩后首次真实 usage；降回线内清零计数。"""
        from pai.core.compaction import (CompactionSettings, CompactionState,
                                         verify_compaction)

        settings = CompactionSettings(reserve_tokens=200)
        state = CompactionState(awaiting_verify=True)
        state = verify_compaction(950, 1000, settings, state)        # 仍超线（>800）
        assert state.failures == 1 and not state.awaiting_verify
        state.awaiting_verify = True
        state = verify_compaction(500, 1000, settings, state)        # 降回线内
        assert state.failures == 0

    def test_breaker_trips_after_three_consecutive_failures(self):
        from pai.core.compaction import (CompactionSettings, CompactionState,
                                         verify_compaction)

        settings = CompactionSettings(reserve_tokens=200)
        state = CompactionState()
        for _ in range(3):
            state.awaiting_verify = True
            state = verify_compaction(999, 1000, settings, state)
        assert state.tripped                                          # 第 3 次即熔断

    def test_tripped_is_one_way(self):
        """熔断置位后不因「这次降回线内」而回落（02 终审延后项）。

        实现靠 `state.tripped or failures >= MAX` 这个表达式兑现，此前只做过
        双重人工审查没有测试——而它一旦回落，熔断器就退化成「每三次歇一次」，
        CC 那种「单会话数千次连续压缩失败」的账重新打开（D#14）。
        """
        from pai.core.compaction import (CompactionSettings, CompactionState,
                                         verify_compaction)

        settings = CompactionSettings(reserve_tokens=200)
        state = CompactionState(failures=3, tripped=True, awaiting_verify=True)
        state = verify_compaction(500, 1000, settings, state)   # 降回线内，计数清零
        assert state.failures == 0
        assert state.tripped                                    # 但熔断不回落


# ---- 「还差多少 token 才切得动」（TODO「压缩链路的可验证性」第二条）----


def test_shortfall_says_how_much_history_is_still_missing():
    """`/compact` 在真实会话里几乎永远只得到「无可压」，而用户无从判断
    是坏了还是没到量。差额是可算的：最新锚与最早锚之间的真实差值 vs 门槛。"""
    from pai.core.compaction import Anchor, keep_recent_shortfall

    anchors = [Anchor(1, 1000), Anchor(3, 1500), Anchor(5, 1800)]
    assert keep_recent_shortfall(anchors, 20000) == 19200      # 门槛 20000 - 已累计 800
    assert keep_recent_shortfall(anchors, 800) == 0            # 刚好够：差额不是原因


def test_shortfall_of_a_single_anchor_is_the_whole_threshold():
    """锚不足两个时一个差值都算不出来——如实返回整个门槛，而不是 0（0 会被
    读成「够了」）。"""
    from pai.core.compaction import Anchor, keep_recent_shortfall

    assert keep_recent_shortfall([Anchor(1, 900)], 20000) == 20000
    assert keep_recent_shortfall([], 20000) == 20000
