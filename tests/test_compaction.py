"""阶段 1 第 1-2 步：token 秤 + 警戒线 + 对话拍平机。

三个都是纯函数（进参数出结果，不联网不读文件），所以全部离线可测。
REAL_TRAJECTORY 是 pai_playground/sessions/20260802-224352.jsonl 的真实运行记录
（tri.txt 那次，含一条 sed 失败），剥掉了 SessionLog 加的 ts 字段——
estimate_tokens 面对的是发给 API 的消息格式，不含 ts。
"""

from pai.core.compaction import (
    CompactionSettings,
    estimate_tokens,
    serialize_conversation,
    should_compact,
)

REAL_TRAJECTORY = [
    {
        "role": "system",
        "content": (
            "你是一个最小化的编码 agent。你有这些工具：bash（跑命令）、read_file（读文件）、"
            "write_file（覆盖写文件）、edit_file（精确替换文件里的一段文本）。"
            "改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。"
            "一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。"
        ),
    },
    {
        "role": "user",
        "content": "创建 tri.txt，内容为四行，每行都是 same same；然后把第二行改成 done，其他两行不动",
    },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_00_S3O2fUaAdiUp1NK9i4I83476",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"command": "printf \'same same\\\\nsame same\\\\nsame same\\\\nsame same\\\\n\' > tri.txt && cat tri.txt"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_00_S3O2fUaAdiUp1NK9i4I83476",
        "content": "same same\nsame same\nsame same\nsame same\n",
    },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_00_YCn1gLUHFgglAcSvbncA7158",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"command": "sed -i \'2s/.*/done/\' tri.txt && cat tri.txt"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_00_YCn1gLUHFgglAcSvbncA7158",
        "content": "sed: 2: \"tri.txt\n\": undefined label 'ri.txt'\n",
    },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_00_cWNCJkkCSGv031Ujv9kG8115",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"command": "perl -pi -e \'s/.*/done/ if $. == 2\' tri.txt && cat tri.txt"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_00_cWNCJkkCSGv031Ujv9kG8115",
        "content": "same same\ndone\nsame same\nsame same\n",
    },
    {
        "role": "assistant",
        "content": "完成：已创建 tri.txt（四行“same same”），并把第二行改为“done”，其余两行保持不动。",
    },
]


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


def test_unknown_role_returns_zero():
    assert estimate_tokens({"role": "developer", "content": "a" * 400}) == 0
    assert estimate_tokens({"content": "a" * 400}) == 0


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


# ---------- context_tokens：以真实 usage 为锚 ----------

# 取自 pai_playground/sessions/20260802-235657.jsonl，一次真实的 3 步运行
# （创建 usage_check.txt 并读回）。已剥掉 ts。
REAL_USAGE_TRAJECTORY = [
    {
        "role": "system",
        "content": "你是一个最小化的编码 agent。你有这些工具：bash（跑命令）、read_file（读文件）、write_file（覆盖写文件）、edit_file（精确替换文件里的一段文本）。改代码时优先用 edit_file 做精确修改，而不是用 bash 或整文件覆盖。一步步来，看到工具结果再决定下一步。任务完成后用一句话简短总结。",
    },
    {"role": "user", "content": "创建 usage_check.txt，写入三行：alpha、beta、gamma，然后读出来确认"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_00_ET_aXcRr8wrZF8BXFrnDTGK2905",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": '{"path": "usage_check.txt", "content": "alpha\\nbeta\\ngamma\\n"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_00_ET_aXcRr8wrZF8BXFrnDTGK2905",
        "content": "已写入 usage_check.txt（17 字符）",
    },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_00_ET_LwPBKwDO0NBNfX5TixAb9254",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "usage_check.txt"}'},
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_00_ET_LwPBKwDO0NBNfX5TixAb9254",
        "content": "alpha\nbeta\ngamma\n",
    },
    {"role": "assistant", "content": "已创建 usage_check.txt 并读出确认内容为 alpha、beta、gamma 三行。"},
]

# provider 实际回传的三步用量
REAL_USAGE_STEPS = [
    {"step": 1, "prompt_tokens": 732, "completion_tokens": 67},
    {"step": 2, "prompt_tokens": 821, "completion_tokens": 46},
    {"step": 3, "prompt_tokens": 885, "completion_tokens": 21},
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
    from pai.core.tools import get_tools

    schemas = [t.schema() for t in get_tools().values()]
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
