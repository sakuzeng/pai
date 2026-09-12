"""feature 50：工具调用折成组（照 CC 2.1.88 `collapseReadSearchGroups` + `CollapsedReadSearchContent`）。

- 连续的读 / 搜 / 看目录 / 跑命令 / 跑测试 / 看 git / 记笔记合成一组；模型的非空文本
  与写 / 改文件断组（CC `isTextBreaker` / `isNonCollapsibleToolUse`）。
- 跑着时一行现在时「正在读 2 个文件…」+ 一行 `⎿` 当前工具提示；跑完过去时
  「读了 2 个文件 (ctrl+o 展开)」，dim 灰、无常驻底色。
- 展开一级铺全部输出（CC verbose 形态），展开块加暗底（对应 CC 选中行的 messageActionsBackground）。
- 写 / 改文件各自一行，默认展开 diff（45-B2）。只在备用屏（transcript 归 pai）下分组；
  main-screen 下 scrollback 归终端，改不了已打出去的行，照旧逐条。
"""

from typing import List

from pai.core.events import AgentEnd, AgentStart, AssistantMessage, ToolEnd, ToolStart
from pai.tui import theme
from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.groups import ToolGroup, is_collapsible
from pai.tui.scroll import ScrollState
from pai.tui.transcript import Transcript

WIDE = 200


def _alt_app(cols=80, rows=24, color=False):
    writes: List[str] = []
    transcript, scroll = Transcript(), ScrollState()
    renderer = AltScreenRenderer(write=writes.append, width=lambda: cols,
                                 height=lambda: rows, transcript=transcript, scroll=scroll)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll, color=color)
    return app, transcript


def _text(transcript, width=WIDE):
    return "\n".join(transcript.slice(width, 0, transcript.total_lines(width)))


def _read(i, path="a.py", body="第一行\n第二行\n第三行"):
    return (ToolStart(tool_call_id=str(i), name="read_file", args={"path": path}),
            ToolEnd(tool_call_id=str(i), name="read_file", args={"path": path}, result=body))


# ---- 分组与文案（纯逻辑）---------------------------------------------------------

def test_collapsible_set_follows_cc():
    assert all(is_collapsible(n) for n in ("read_file", "search_files", "list_dir", "bash",
                                           "run_tests", "git_read", "remember"))
    assert not any(is_collapsible(n) for n in ("write_file", "edit_file", "ask_user_question"))
    assert is_collapsible("mcp__slack__search"), "认不得的工具也进组（CC：MCP 读搜算 Queried）"


def test_summary_counts_by_action_in_past_and_present_tense():
    g = ToolGroup()
    for i, (s, e) in enumerate([_read(1), _read(2, "b.py")]):
        g.start(s)
        g.end(e)
    g.start(ToolStart(tool_call_id="3", name="search_files", args={"pattern": "TODO"}))
    assert g.summary() == "正在搜 1 次，读 2 个文件"
    assert g.hint == "TODO" or "TODO" in g.hint
    g.end(ToolEnd(tool_call_id="3", name="search_files", args={"pattern": "TODO"}, result="x"))
    g.close()
    assert g.summary() == "搜了 1 次，读了 2 个文件"


def test_unknown_tools_get_a_generic_wording():
    g = ToolGroup()
    g.end(ToolEnd(tool_call_id="1", name="mcp__slack__search", args={}, result="r"))
    g.close()
    assert g.summary() == "调了 1 次 mcp__slack__search"


# ---- TuiApp：断组、活轮次、轮末 ------------------------------------------------------

def test_text_and_edits_break_groups():
    """[读, 读] 答案 [读] 改文件 [读] → 组、答案、组、改文件行、组、用时行。"""
    app, transcript = _alt_app()
    app.on_event(AgentStart(task="t"))
    for i in (1, 2):
        s, e = _read(i)
        app.on_event(s)
        app.on_event(e)
    app.on_event(AssistantMessage(content="先看看这两个", tool_call_names=()))
    s, e = _read(3)
    app.on_event(s)
    app.on_event(e)
    app.on_event(ToolStart(tool_call_id="4", name="edit_file", args={"path": "a.py"}))
    app.on_event(ToolEnd(tool_call_id="4", name="edit_file", args={"path": "a.py"},
                         result="已替换 1 处\n--- a.py\n+++ a.py\n-old\n+new"))
    s, e = _read(5)
    app.on_event(s)
    app.on_event(e)
    app.on_event(AgentEnd(reason="final", text="先看看这两个"))
    text = _text(transcript)
    assert "读了 2 个文件 (ctrl+o 展开)" in text, text
    assert "先看看这两个" in text
    assert text.count("读了 1 个文件 (ctrl+o 展开)") == 2, text
    assert "edit_file(" in text and "+new" in text, "改文件单独一行且默认展开 diff（45-B2）"
    assert "└ read_file(" not in text, "组里的工具不再逐条上屏"
    order = [text.index(s) for s in ("读了 2 个文件", "先看看这两个", "edit_file(", theme.SUMMARY)]
    assert order == sorted(order), "顺序：组 → 答案 → 改文件 → 用时"


def test_active_group_shows_present_tense_and_the_current_tool():
    app, transcript = _alt_app()
    app.on_event(AgentStart(task="t"))
    app.on_event(ToolStart(tool_call_id="1", name="read_file", args={"path": "docs/STATUS.md"}))
    text = _text(transcript)
    assert "正在读 1 个文件…" in text and "⎿ docs/STATUS.md" in text, text
    app.on_event(ToolEnd(tool_call_id="1", name="read_file", args={"path": "docs/STATUS.md"},
                         result="x"))
    app.on_event(AgentEnd(reason="final", text=""))
    text = _text(transcript)
    assert "读了 1 个文件 (ctrl+o 展开)" in text and "⎿" not in text, text


def test_expanding_a_group_lists_every_call_with_its_full_output_on_a_band():
    app, transcript = _alt_app(color=True)
    app.on_event(AgentStart(task="t"))
    for i, path in ((1, "a.py"), (2, "b.py")):
        s, e = _read(i, path, body="\n".join(f"{path} 第{n}行" for n in range(1, 8)))
        app.on_event(s)
        app.on_event(e)
    app.on_event(AgentEnd(reason="final", text=""))
    group = [e for e in transcript.entries if e.expandable][-1]
    group.toggle()
    text = _text(transcript)
    assert "读了 2 个文件 (ctrl+o 收起)" in text
    assert "a.py 第7行" in text and "b.py 第7行" in text, "一级展开就是全部输出（CC verbose）"
    assert theme.TOOL_BG in text, "展开块要有暗底（CC 选中行的 messageActionsBackground 对应物）"
    lines = _text(transcript).split("\n")
    head = next(l for l in lines if "读了 2 个文件" in l)
    assert theme.TOOL_BG not in head, "折叠/摘要行本身不铺底色（CC 折叠态是 dim）"


def test_no_color_means_no_escape_sequences():
    app, transcript = _alt_app(color=False)
    app.on_event(AgentStart(task="t"))
    s, e = _read(1)
    app.on_event(s)
    app.on_event(e)
    app.on_event(AgentEnd(reason="final", text=""))
    [g for g in transcript.entries if g.expandable][-1].toggle()
    assert "\x1b" not in _text(transcript)


def test_ctrl_o_toggles_the_latest_group_in_alt_screen():
    app, transcript = _alt_app()
    app.on_event(AgentStart(task="t"))
    s, e = _read(1)
    app.on_event(s)
    app.on_event(e)
    app.on_event(AgentEnd(reason="final", text=""))
    app.expand_last()
    assert "(ctrl+o 收起)" in _text(transcript)
    app.expand_last()
    assert "(ctrl+o 展开)" in _text(transcript)


def test_a_new_user_line_closes_a_dangling_group():
    """被打断的轮次（AgentEnd 也没来）：用户再说话时组必须定格成过去时。"""
    app, transcript = _alt_app()
    app.on_event(AgentStart(task="t"))
    app.on_event(ToolStart(tool_call_id="1", name="bash", args={"command": "ls"}))
    app._submitted("下一句")
    text = _text(transcript)
    assert "跑了 1 条命令" in text and "正在" not in text, text


def test_replay_groups_the_same_way():
    """48 的回放走同一条分组（CC：同一个渲染器）。真实轨迹：10 个并发工具批。"""
    from pathlib import Path

    from pai.core.session import build_messages, load_session, trim_unfinished
    from pai.modes.resume import history_items

    _, entries = load_session(Path(__file__).parent / "fixtures" / "resume_session.jsonl")
    msgs, led = build_messages(entries)
    msgs, _ = trim_unfinished(msgs, led)
    app, transcript = _alt_app()
    app.replay(history_items(msgs))
    text = _text(transcript)
    assert "└ read_file(" not in text
    assert "读了" in text and "个文件" in text and "(ctrl+o 展开)" in text, text
    assert "正在" not in text, "回放的组全部定格"
    # 第二个问题之前的组与之后的组分开：用户行是断点
    assert text.index("分析一下当前项目") < text.index("读了") < text.index("现在在做什么呢")
