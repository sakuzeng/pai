"""共享的真实会话轨迹夹具（feature 40 从 test_compaction.py 抽出来）。

AGENTS「测试」一节的规约：新增阶段模块至少要有一条测试拿真实会话轨迹当输入
——编的字符串测不出中文、`tool_calls.arguments` 这类真实坑。于是这几份轨迹
被越来越多的测试文件引用，最后长成了「测试文件 A import 测试文件 B」的形状
（实测 5 处，还分成 `from tests.test_compaction import` 与
`from test_compaction import` 两种写法）。夹具的家不该是某一个测试文件。

出处（都剥掉了 SessionLog 加的 `ts` 字段——`estimate_tokens` 面对的是发给 API
的消息格式，不含 ts）：

- `REAL_TRAJECTORY`：`pai_playground/sessions/20260802-224352.jsonl`
  （tri.txt 那次，含一条 sed 失败）
- `REAL_USAGE_TRAJECTORY` / `REAL_USAGE_STEPS`：同一批真跑里带 usage 的那次，
  三步的 prompt/completion 是真实读数，锚点相关的测试靠它反推。

诚实边界（TODO 旧账）：`pai_playground/` 已被 .gitignore 排除，所以这几份夹具的
原始出处不在版本库里——溯源链断在一个不入库的目录上。新夹具请按
`tests/fixtures/README.md` 的做法抄进版本库。
"""

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
