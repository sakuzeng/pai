"""feature 48：`--resume` 之后旧对话要上屏，照 CC 的做法——同一份消息数组、同一个渲染器。

CC 2.1.88（反编译）：`ResumeConversation.tsx` 把 `loadConversationForResume()` 的结果当
`initialMessages` 喂给 `<REPL>`，`REPL.tsx` 用它初始化 `messages` 状态，活轮次与恢复的
消息走同一个 `<Messages>`；`shouldShowUserMessage` 把 isMeta 的 user 消息滤掉；
system prompt 每次 query 现算、转录里不存。pai 在这里对应三件事：
`modes/resume.py::history_items`（消息 → 回放项，纯函数）、`TuiApp.replay`（回放项 →
transcript 条目，复用活轮次的渲染函数）、`run_interactive` 在 resume 后重装配 system prompt。

真实轨迹：`tests/fixtures/resume_session.jsonl`（用户 2026-09-10 那次「看起来没恢复」的
原始会话，37 条，含 10 个并发工具批、一条规则注入、一条指令消息、结尾一条无回复的 user）。
"""

import json
from pathlib import Path

from fake_llm import FakeClient
from helpers import OPEN_RULES, scripted_reader

from pai.core.events import AssistantMessage, ToolEnd
from pai.core.loop import INSTRUCTION_HEADER
from pai.core.session import build_messages, load_session, trim_unfinished
from pai.modes.interactive import run_interactive
from pai.modes.resume import history_items
from pai.tui import theme
from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.history import CompactedMark, ShellLine, UserLine
from pai.tui.scroll import ScrollState
from pai.tui.transcript import Transcript

FIXTURE = Path(__file__).parent / "fixtures" / "resume_session.jsonl"
WIDE = 200      # 断言文本用足够宽的宽度渲染，免得折叠提示被截断


def _real_messages():
    _, entries = load_session(FIXTURE)
    msgs, ledger = build_messages(entries)
    msgs, _ = trim_unfinished(msgs, ledger)
    return msgs


def _alt_app(cols=60, rows=12):
    writes = []
    transcript, scroll = Transcript(), ScrollState()
    renderer = AltScreenRenderer(write=writes.append, width=lambda: cols,
                                 height=lambda: rows, transcript=transcript, scroll=scroll)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll, color=False)
    return app, transcript


def _all_text(transcript, width=WIDE):
    return "\n".join(transcript.slice(width, 0, transcript.total_lines(width)))


# ---- 消息 → 回放项（纯函数）--------------------------------------------------

def test_history_items_from_a_real_session():
    """真实轨迹：两句人话、一条最终回答、每条 tool 消息配成一个 ToolEnd；
    指令消息与规则注入不当用户话，system 不出现。"""
    msgs = _real_messages()
    items = history_items(msgs)

    users = [i for i in items if isinstance(i, UserLine)]
    assert [u.text[:8] for u in users] == ["分析一下当前项目", "现在在做什么呢"], users

    tools = [i for i in items if isinstance(i, ToolEnd)]
    assert len(tools) == sum(1 for m in msgs if m.get("role") == "tool")
    assert all(isinstance(t.args, dict) for t in tools)
    assert tools[0].name == "read_file" and "path" in tools[0].args, tools[0]
    assert tools[0].result.strip(), "工具结果要带回来，折叠行的首行与 +N 行都靠它"

    # 这份真实会话里一条最终回答都没有：整段是一次 run——第二问是干活时插进去的
    # （events 流里一条 SteeringInjected），run 在第 12 步被用量预算掐断（唯一的
    # AgentEnd，reason=budget）。所以回放里没有答案条目——这是真实形状，不是 bug；
    # 答案条目的渲染由下面的合成测试盯
    assert [i for i in items if isinstance(i, AssistantMessage)] == []
    assert isinstance(items[0], UserLine), "第一项是人的第一句话，不是 system 也不是指令"


def test_framework_injections_are_not_replayed_as_user_lines():
    """照 CC 的 isMeta：项目指令、规则/召回的 system-reminder 不画；
    压缩摘要画成一行标记（正文不回放）；`!命令` 拆回命令 + 输出；
    空白 assistant 不画（CC filterWhitespaceOnlyAssistantMessages 同款）。"""
    msgs = [
        {"role": "system", "content": "你是一个最小化的编码 agent。"},
        {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n一堆规矩"},
        {"role": "user", "content": "[早前对话的摘要，供延续任务用]\n以前聊过 X"},
        {"role": "user", "content": "<system-reminder>\n规则正文\n</system-reminder>"},
        {"role": "user", "content": "我执行了命令 `ls`，输出：\na\nb"},
        {"role": "user", "content": "真人说的话"},
        {"role": "assistant", "content": "  \n "},
        {"role": "assistant", "content": "回答"},
    ]
    assert history_items(msgs) == [
        CompactedMark(),
        ShellLine(command="ls", output="a\nb"),
        UserLine("真人说的话"),
        AssistantMessage("回答"),
    ]


def test_tool_rounds_pair_calls_with_results():
    """assistant 的 tool_calls 与随后的 tool 消息按 id 配对成 ToolEnd；
    arguments 是 JSON 串就解析成 dict，解析不了退化成 {'raw': …}（诚实边界：
    is_error 一律 False，tool 消息里分不出 loop 造的错，同 events.ToolEnd 注释）。"""
    msgs = [
        {"role": "assistant", "content": "我先看看", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "bash", "arguments": json.dumps({"command": "ls"})}},
            {"id": "c2", "type": "function",
             "function": {"name": "read_file", "arguments": "not json"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "a\nb"},
        {"role": "tool", "tool_call_id": "c2", "content": "错误：没有这个文件"},
    ]
    items = history_items(msgs)
    assert items[0] == AssistantMessage("我先看看", ("bash", "read_file"))
    assert items[1] == ToolEnd("c1", "bash", {"command": "ls"}, "a\nb")
    assert items[2].name == "read_file" and items[2].args == {"raw": "not json"}
    assert items[2].result == "错误：没有这个文件" and items[2].is_error is False


# ---- 回放项 → 备用屏 -------------------------------------------------------------

def test_replay_puts_the_conversation_on_the_alt_screen():
    app, transcript = _alt_app()
    app.replay(history_items(_real_messages()))
    text = _all_text(transcript)
    assert "分析一下当前项目是关于什么的呢" in text
    assert "现在在做什么呢" in text
    assert "read_file(" in text and "(^O 展开)" in text, "工具结果折叠成一行（照 CC）"
    assert "# 项目指令与记忆" not in text and "<system-reminder>" not in text
    assert "你是一个最小化的编码 agent" not in text, "system 不上屏"


def test_replay_does_not_touch_the_dock():
    """dock 的活动区是本进程的计数（feature 12），回放的是上一个进程干的活，不该算进去。"""
    app, _ = _alt_app()

    def boom(event):
        raise AssertionError(f"回放不该动 dock：{event}")

    app.dock.handle = boom
    app.replay(history_items(_real_messages()))


def test_replayed_tool_outputs_are_reachable_with_ctrl_o():
    """回放进来的工具输出也要能 ^O 展开——否则折叠行说的「(^O 展开)」是假话。"""
    app, transcript = _alt_app()
    app.replay(history_items(_real_messages()))
    before = transcript.total_lines(WIDE)
    app.expand_last()
    assert "没有更早的工具输出可展开了" not in _all_text(transcript)
    assert transcript.total_lines(WIDE) > before + 1, "应打出完整输出而不是一行提示"


def test_compacted_mark_shell_and_answer_render():
    app, transcript = _alt_app()
    app.replay([CompactedMark(), ShellLine(command="ls -la", output="total 8\na\nb"),
                AssistantMessage("回答正文")])
    text = _all_text(transcript)
    assert theme.ANSWER in text and "回答正文" in text, "答案戴圆点上屏（与活轮次同一个函数）"
    assert "已压缩" in text, "压缩位置要有一行标记（CC 的 CompactBoundaryMessage）"
    assert "! ls -la" in text, "`!命令` 画成命令行（CC 的 UserBashInputMessage）"
    assert "(^O 展开)" in text, "输出折叠（CC 非 verbose 时的 BashToolResultMessage）"
    assert "以前聊过" not in text


# ---- resume 之后 system prompt 与指令按当前环境重装配（照 CC：转录里不存 system prompt）----

def _write_session_with_stale_prompt(tmp_path):
    directory = tmp_path / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "20260910-120000-abcdef12.jsonl"
    lines = [
        {"type": "session", "version": 1, "id": "abcdef1234", "timestamp": "t",
         "cwd": str(tmp_path)},
        {"type": "message", "id": "s", "parentId": None,
         "message": {"role": "system", "content": "旧的 system prompt STALE"}},
        {"type": "message", "id": "i", "parentId": "s",
         "message": {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n旧指令 STALE"}},
        {"type": "message", "id": "u", "parentId": "i",
         "message": {"role": "user", "content": "上次的问题"}},
        {"type": "message", "id": "a", "parentId": "u",
         "message": {"role": "assistant", "content": "上次的回答"}},
    ]
    path.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n",
                    encoding="utf-8")
    return path


def test_resume_rebuilds_system_prompt_and_instructions_from_the_current_environment(
        tmp_path, monkeypatch):
    """此前提示语说「system prompt 都按当前环境重新装配」而代码没做：`run_agent` 只在
    messages 为空时造 system，`_inject_instructions` 见旧指令消息就跳过。
    照 CC（每次 query 现算 getSystemPrompt + getUserContext），恢复的只有对话。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "PAI.md").write_text("新的项目指令 FRESH\n", encoding="utf-8")
    path = _write_session_with_stale_prompt(tmp_path)

    client = FakeClient([{"content": "好"}])
    run_interactive(client=client, model="fake", reader=scripted_reader(["接着聊"]),
                    rules=OPEN_RULES, out=lambda _s: None, on_event=lambda _: None,
                    no_session=True, resume=str(path))

    sent = client.requests[0]["messages"]
    assert sent[0]["role"] == "system"
    assert "STALE" not in sent[0]["content"] and "你有这些工具" in sent[0]["content"]
    instr = [m for m in sent if m["role"] == "user"
             and str(m["content"]).startswith(INSTRUCTION_HEADER)]
    assert len(instr) == 1, instr
    assert "FRESH" in instr[0]["content"] and "STALE" not in instr[0]["content"]
    assert [m["content"] for m in sent if m["role"] in ("user", "assistant")][-3:] == [
        "上次的问题", "上次的回答", "接着聊"], "对话本身要原样带着"
