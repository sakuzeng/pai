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
        "content": '完成：已创建 tri.txt（四行"same same"），并把第二行改为"done"，其余两行保持不动。',
    },
]


# ---------- estimate_tokens ----------


def test_user_message_token_estimate():
    """官方系数：1 个英文字符 ≈ 0.3 token（refs/deepseek-api/quick_start/token_usage.md）。

    这条推翻了最初钉的 `400 字符 = 100 token`（chars/4）——那是通用经验值，
    对中文低估 2.4 倍。这里用官方系数。
    """
    msg = {"role": "user", "content": "a" * 100}
    assert estimate_tokens(msg) == 30  # 100 * 0.3 = 30


def test_chinese_message_token_estimate():
    """官方系数：1 个中文字符 ≈ 0.6 token（refs/deepseek-api/quick_start/token_usage.md）。"""
    msg = {"role": "user", "content": "代" * 100}
    assert estimate_tokens(msg) == 60  # 100 * 0.6 = 60


def test_empty_message():
    """空消息不花 token。"""
    assert estimate_tokens({"role": "user"}) == 0
    assert estimate_tokens({"role": "user", "content": ""}) == 0
    assert estimate_tokens({"role": "user", "content": None}) == 0


def test_unknown_role_returns_zero():
    """未知 role 一律 0。"""
    assert estimate_tokens({"role": "unknown", "content": "lots of text"}) == 0


def test_tool_calls_are_counted():
    """tool_calls 的 name 和 arguments 也算 token。"""
    msg = {
        "role": "assistant",
        "content": "calling",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "bash", "arguments": '{"command": "echo 代"}'},
            }
        ],
    }
    # content: "calling" = 7 * 0.3 = 2.1
    # name: "bash" = 4 * 0.3 = 1.2
    # arguments: '{"command": "echo 代"}' = 18 ASCII + 1 CJK = 18*0.3 + 1*0.6 = 6.0
    # total ≈ 9.3, ceiling = 10
    assert estimate_tokens(msg) == 10


# ---------- serialize_conversation ----------


def test_serialize_conversation():
    """拍平对话，保留 role 和结构。"""
    msgs = [
        {"role": "user", "content": "create file"},
        {"role": "assistant", "content": "done"},
    ]
    result = serialize_conversation(msgs)
    assert "user: create file" in result
    assert "assistant: done" in result


def test_serialize_excludes_unknown_roles():
    """未知 role 不出现。"""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "unknown", "content": "ignored"},
        {"role": "assistant", "content": "hi"},
    ]
    result = serialize_conversation(msgs)
    assert "user: hello" in result
    assert "assistant: hi" in result
    assert "unknown" not in result


def test_serialize_tool_calls():
    """tool_calls 单独一行，保留 id 和参数。"""
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "x.py"}'},
                }
            ],
        }
    ]
    result = serialize_conversation(msgs)
    assert "tool_call call_1" in result
    assert "read_file" in result
    assert "x.py" in result


def test_serialize_tool_results():
    """tool 消息单独一行，保留 call_id。"""
    msgs = [
        {"role": "tool", "tool_call_id": "call_1", "content": "result data"},
    ]
    result = serialize_conversation(msgs)
    assert "tool[call_1]: result data" in result


def test_serialize_truncates_long_fields():
    """超长字段截断。"""
    msgs = [
        {"role": "user", "content": "a" * 10000},
    ]
    result = serialize_conversation(msgs, max_chars=100)
    assert len(result) < 10000
    assert "more characters truncated" in result


# ---------- should_compact ----------


def test_should_compact_when_exceeded():
    """上下文超过阈值就压缩。"""
    settings = CompactionSettings(reserve_tokens=1000)
    # 窗口 10000，预留 1000 → 9000 的触发线
    assert not should_compact(9000, 10000, settings)  # 正好压线不动
    assert should_compact(9001, 10000, settings)      # 超一点就压


def test_should_compact_disabled():
    """disabled=False 时永不压。"""
    settings = CompactionSettings(reserve_tokens=100, enabled=False)
    assert not should_compact(999999, 10000, settings)


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

    def test_instructions_override_default(self):
        from fake_llm import FakeClient
        from pai.core.compaction import SUMMARY_INSTRUCTIONS, summarize

        client = FakeClient([{"content": "s", "usage": {}}])
        summarize(self._msgs(), client=client, model="fake", instructions="只保留文件名")
        joined = "".join(m["content"] for m in client.requests[0]["messages"])
        assert "只保留文件名" in joined and SUMMARY_INSTRUCTIONS[:8] not in joined
