"""T7：把组件粘起来的那一层。

最重要的两条在这里落地：
- **提问期间敲命令就是执行命令**（08 遗留的铁证反例）
- **干活时打的字进 followUp 队列**（拍板问 4）
"""

from pai.core.events import AgentEnd, AgentStart, ToolStart
from pai.tui import theme
from pai.tui.app import (
    COMMAND, CYCLE_MODE, EOF, EXPAND, INTERRUPT, SUBMIT, TuiApp,
)
from pai.tui.dialog import Dialog
from pai.tui.keys import KeyDecoder
from pai.tui.renderer import DockRenderer
from tests.tui_screen import VirtualScreen


def make(history=None, rows=12):
    screen = VirtualScreen(cols=48, rows=rows)
    renderer = DockRenderer(write=screen.write, width=lambda: screen.cols)
    app = TuiApp(renderer=renderer, history=history)
    app.refresh()
    return app, screen


def committed(screen):
    """只取「已上交 scrollback」的那部分——dock（分隔线及其下方）不算。"""
    out = []
    for line in screen.logical_lines():
        if line and set(line) <= {"─"}:
            break
        if line.strip():
            out.append(line)
    return out


def feed(app, data):
    return app.feed(data if isinstance(data, bytes) else data.encode("utf-8"),
                    KeyDecoder())


def test_typing_shows_up_in_the_dock():
    app, screen = make()
    feed(app, "你好")
    assert any("你好" in line for line in screen.visible())


def test_enter_submits_and_the_line_is_committed_to_scrollback():
    """提交的那行要留在 scrollback 里——否则用户翻历史看不到自己问过什么。"""
    app, screen = make()
    assert feed(app, "读一下 README\r") == [(SUBMIT, "读一下 README")]
    assert any("读一下 README" in line for line in screen.logical_lines())


def test_slash_command_is_reported_as_a_command():
    app, _ = make()
    assert feed(app, "/status\r") == [(COMMAND, "/status")]


def test_bang_command_is_reported_as_a_command():
    app, _ = make()
    assert feed(app, "!ls\r") == [(COMMAND, "!ls")]


def test_shift_tab_asks_for_a_mode_cycle():
    app, _ = make()
    assert feed(app, b"\x1b[Z") == [(CYCLE_MODE, None)]


def test_ctrl_c_and_ctrl_d():
    app, _ = make()
    assert feed(app, b"\x03") == [(INTERRUPT, None)]
    assert feed(app, b"\x04") == [(EOF, None)]


def test_ctrl_d_with_text_in_the_box_is_not_eof():
    app, _ = make()
    feed(app, "abc")
    assert feed(app, b"\x04") == []


def test_empty_enter_does_nothing():
    app, _ = make()
    assert feed(app, b"\r") == []


# --- 模态输入：08 遗留那条铁证 -----------------------------------------

def test_dialog_takes_over_the_input_position():
    app, screen = make()
    app.enqueue_dialog(Dialog(question="用哪个？", options=["A", "B"]))
    app.refresh()
    text = "\n".join(screen.visible())
    assert "用哪个？" in text


def test_bang_command_during_a_question_is_executed_not_answered():
    """铁证反例：2026-08-10 演示时 `!echo 我是命令` 被静默当成了对问题的回答。"""
    app, _ = make()
    dialog = Dialog(question="用哪个？", options=["A", "B"])
    app.enqueue_dialog(dialog)
    assert feed(app, "!echo 我是命令\r") == [(COMMAND, "!echo 我是命令")]
    assert dialog.resolved is False             # 没有被当成答案
    assert app.arbiter.current() is not None    # 问题还在，等真人答


def test_slash_command_during_a_question_is_executed_not_answered():
    app, _ = make()
    dialog = Dialog(question="用哪个？", options=["A", "B"])
    app.enqueue_dialog(dialog)
    assert feed(app, "/status\r") == [(COMMAND, "/status")]
    assert dialog.resolved is False


def test_answering_a_question_resolves_it():
    app, _ = make()
    dialog = Dialog(question="用哪个？", options=["A", "B"])
    app.enqueue_dialog(dialog)
    feed(app, b"2")
    assert dialog.resolved is True
    assert dialog.answer == "B"
    assert app.arbiter.current() is None


def test_typing_suppresses_a_pending_dialog_and_the_status_line_says_so():
    """照 CC：用户在打字就压住对话框，但**必须说出来**，不能静默。"""
    app, screen = make()
    feed(app, "半句话")
    app.enqueue_dialog(Dialog(question="用哪个？", options=["A", "B"]))
    app.refresh()
    text = "\n".join(screen.visible())
    assert "用哪个？" not in text                # 没弹出来
    assert "半句话" in text                       # 输入框还在
    assert "1 个请求在等" in text                 # 但说清楚了


# --- 干活期间 ----------------------------------------------------------

def test_typing_while_busy_still_reaches_the_input_box():
    app, screen = make()
    app.busy = True
    feed(app, "干活时打的字")
    assert any("干活时打的字" in line for line in screen.visible())


def test_enter_while_busy_is_a_submit_for_the_queue():
    """拍板问 4：排队，本轮结束后发（CC 的 queued commands）。"""
    app, _ = make()
    app.busy = True
    assert feed(app, "追加一句\r") == [(SUBMIT, "追加一句")]


def test_bang_command_while_busy_is_queued_not_run():
    """干活时不能插一条 shell 进去——那会打乱正在进行的工具调用。"""
    app, _ = make()
    app.busy = True
    assert feed(app, "!ls\r") == [(SUBMIT, "!ls")]


def test_queued_count_shows_up_in_the_dock():
    app, screen = make()
    app.dock.set_queued(2)
    app.refresh()
    assert any("已排队 2 条" in line for line in screen.visible())


# --- 事件 --------------------------------------------------------------

def test_tool_events_render_in_the_dock_not_in_scrollback():
    app, screen = make()
    app.on_event(AgentStart(task="干活"))
    app.on_event(ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}))
    assert any("a.py" in line for line in screen.visible())


def test_agent_end_commits_a_summary_line_to_scrollback():
    app, screen = make()
    app.on_event(AgentStart(task="干活"))
    app.on_event(AgentEnd(reason="final", text="done"))
    assert any("用时" in line for line in screen.logical_lines())


def test_history_is_wired_into_the_editor():
    app, _ = make(history=["上一句"])
    feed(app, b"\x1b[A")
    assert app.editor.text == "上一句"


# --- 空闲时不重画（真跑冒烟撞出来的）------------------------------------

def test_idle_dock_does_not_need_ticking():
    """空闲时每 100ms 白刷一帧，离线测试看不出来——它们从不走超时那条路。"""
    app, _ = make()
    assert app.needs_tick() is False


def test_a_running_turn_needs_ticking_for_the_spinner():
    app, _ = make()
    app.on_event(AgentStart(task="干活"))
    assert app.needs_tick() is True


def test_a_suppressed_dialog_needs_ticking_so_it_can_be_released():
    """抑制到期是「时间到了」而不是「有按键」，不 tick 就永远弹不出来。"""
    app, _ = make()
    feed(app, "半句话")
    app.enqueue_dialog(Dialog(question="用哪个？", options=["A", "B"]))
    assert app.needs_tick() is True


# --- 模型的回答必须上屏（用户真跑时发现完全没显示）------------------------

def test_the_model_answer_actually_reaches_the_screen():
    """**用户 2026-08-11 真跑时发现答案完全没显示**。

    根因：`render_text(AssistantMessage)` 返回 None（流式已逐字打过），
    而 TUI 的 on_event 又把 MessageDelta 跳过——两边都以为对方会打，于是谁都没打。
    离线测试没抓到是因为没有一条测试走完「delta → AssistantMessage」这条完整链路。
    """
    from pai.core.events import AssistantMessage, MessageDelta

    app, screen = make()
    app.on_event(AgentStart(task="hello"))
    for chunk in ["你好", "，我是", " pai"]:
        app.on_event(MessageDelta(text=chunk))
    app.on_event(AssistantMessage(content="你好，我是 pai"))
    assert any("你好，我是 pai" in line for line in screen.logical_lines())


def test_answer_is_committed_once_not_twice():
    from pai.core.events import AssistantMessage, MessageDelta

    app, screen = make()
    app.on_event(AgentStart(task="hi"))
    app.on_event(MessageDelta(text="答案"))
    app.on_event(AssistantMessage(content="答案"))
    app.on_event(AgentEnd(reason="final", text="答案"))
    hits = [l for l in screen.logical_lines() if "答案" in l]
    assert len(hits) == 1, hits


def test_a_synthesized_end_text_is_shown_even_without_deltas():
    """budget / max_steps / interrupted 的结尾语是 loop 合成的，从来没流过。"""
    app, screen = make()
    app.on_event(AgentStart(task="hi"))
    app.on_event(AgentEnd(reason="budget", text="⛽ 预算用尽"))
    assert any("预算用尽" in line for line in screen.logical_lines())


def test_tool_only_turn_shows_no_empty_answer():
    from pai.core.events import AssistantMessage

    app, screen = make()
    app.on_event(AgentStart(task="hi"))
    app.on_event(AssistantMessage(content=None, tool_call_names=("read_file",)))
    assert not any("🤖" in line for line in screen.logical_lines())


# --- commit 必须拆行 + 折行（用户 2026-08-11 排版崩掉的根因）---------------

def test_commit_splits_embedded_newlines():
    """工具结果是**一整个带 `\\n` 的字符串**。当成一行写出去，终端会自己折，
    而我的光标计算按「一行」算——于是满屏阶梯。"""
    app, screen = make()
    app.commit("第一行\n第二行\n第三行")
    assert screen.logical_lines()[:3] == ["第一行", "第二行", "第三行"]


def test_commit_wraps_lines_longer_than_the_terminal():
    """超宽行同理：终端自动折行 = 我以为写了 1 行、实际占了 3 行 = 光标错位。"""
    app, screen = make()
    app.commit("x" * 100)                      # 屏宽 48
    rows = [l for l in screen.logical_lines() if l.strip()]
    assert len(rows) >= 3
    for row in rows:
        assert len(row) <= 48


def test_commit_wraps_on_display_width_not_character_count():
    app, screen = make()
    app.commit("中" * 40)                       # 40 个中文 = 80 列，屏宽 48
    from pai.modes.statusline import display_width
    for row in screen.logical_lines():
        assert display_width(row) <= 48


def test_tool_result_is_collapsed_to_one_line_by_default():
    """CC 默认不展开工具输出。全量倒进 scrollback 会把对话冲走
    （用户截图里 `ls -la` 的结果占了半屏）。"""
    from pai.core.events import ToolEnd

    app, screen = make()
    app.on_event(ToolEnd(tool_call_id="1", name="bash", args={"command": "ls -la"},
                         result="total 0\n" + "\n".join(f"file{i}" for i in range(30))))
    body = committed(screen)
    assert len(body) == 1, body
    assert "bash" in body[0]
    assert "30" in body[0]                      # 说清楚折叠了多少行


def test_short_tool_result_is_not_padded_with_a_useless_hint():
    from pai.core.events import ToolEnd

    app, screen = make()
    app.on_event(ToolEnd(tool_call_id="1", name="read_file", args={"path": "a.py"},
                         result="ok"))
    body = committed(screen)
    assert len(body) == 1, body
    assert "还有" not in body[0]


def test_user_line_is_the_most_prominent_thing_on_screen():
    """**层级：用户 > agent > 工具**。

    2026-08-11 第一版把用户行做成了灰色——而工具行、提示行也是灰的，
    于是它成了整屏最不显眼的东西。可它是长对话里最重要的导航锚点：
    一眼扫下来要先找到「我问了什么」。方向搞反了。
    """
    from pai.core.events import ToolEnd

    app, screen = make()
    raw = []
    app.renderer._write = lambda d, _r=raw, _s=screen: (_r.append(d), _s.write(d))[0]
    app.color = True
    app.editor.color = True

    feed(app, "我问的话\r")
    user_line = "".join(raw)
    raw.clear()
    app.on_event(ToolEnd(tool_call_id="1", name="bash", args={}, result="x"))
    tool_line = "".join(raw)

    assert theme.USER_BG in user_line, "用户行要有整行背景色带——它是导航锚点"
    assert theme.USER_BG not in tool_line
    assert theme.GREY in tool_line, "工具行走灰，让位给用户与答案"


def test_the_user_band_spans_the_whole_terminal_width():
    """底色不铺满整宽就不是「色带」，是个歪歪扭扭的高亮块。"""
    from pai.modes.statusline import display_width

    screen = VirtualScreen(cols=48, rows=12)
    renderer = DockRenderer(write=screen.write, width=lambda: screen.cols)
    app = TuiApp(renderer=renderer, color=True)
    app.editor.color = True
    feed(app, "短问题\r")
    row = next(l for l in screen.logical_lines() if "短问题" in l)
    assert display_width(row.rstrip()) < 48        # 屏幕上文字本身是短的
    painted = theme.band("› 短问题", 48, theme.USER_BG, color=True)
    assert display_width(painted) == 48            # 但色带铺满整宽


def test_a_blank_line_separates_turns():
    """轮次之间留白。没有它，一屏文字糊成一片，用户找不到自己的问题在哪。"""
    app, screen = make()
    feed(app, "第一问\r")
    app.commit("● 答案")
    feed(app, "第二问\r")
    lines = screen.logical_lines()
    second = next(i for i, l in enumerate(lines) if "第二问" in l)
    assert lines[second - 1].strip() == "", lines


def test_user_line_and_agent_line_are_visually_distinct():
    """用户 2026-08-11 连提两次：两者长得一样。glyph 不同还不够，颜色也要分。"""
    from pai.core.events import AssistantMessage

    screen = VirtualScreen(cols=48, rows=12)
    renderer = DockRenderer(write=screen.write, width=lambda: screen.cols)
    app = TuiApp(renderer=renderer, color=True)
    app.editor.color = True
    raw = []
    renderer._write = lambda d, _r=raw, _s=screen: (_r.append(d), _s.write(d))[0]

    feed(app, "我说的话\r")
    app.on_event(AssistantMessage(content="它说的话"))
    emitted = "".join(raw)
    user_part = emitted.split("我说的话")[0][-20:]
    agent_part = emitted.split("它说的话")[0][-20:]
    assert user_part != agent_part, (user_part, agent_part)


# --- 甲：被折叠的工具结果要能展开（用户拍板「丙」：先做键盘展开）------------

def test_collapsed_line_says_how_to_expand():
    """折叠而不告诉用户怎么看全，等于把内容藏了。"""
    from pai.core.events import ToolEnd

    app, screen = make()
    app.on_event(ToolEnd(tool_call_id="1", name="bash", args={"command": "ls"},
                         result="\n".join(f"row{i}" for i in range(20))))
    line = committed(screen)[0]
    assert "19" in line and "^O" in line


def test_ctrl_o_expands_the_most_recent_collapsed_result():
    from pai.core.events import ToolEnd

    app, screen = make()
    app.on_event(ToolEnd(tool_call_id="1", name="bash", args={"command": "ls"},
                         result="\n".join(f"row{i}" for i in range(20))))
    assert feed(app, b"\x0f") == [(EXPAND, None)]
    app.expand_last()
    body = committed(screen)
    assert any("row19" in l for l in body)
    assert any("row0" in l for l in body)


def test_expanding_twice_walks_further_back():
    """连按两次看更早的一条——不然只能看最后一个工具，多工具的一轮里没用。"""
    from pai.core.events import ToolEnd

    app, screen = make()
    for i in (1, 2):
        app.on_event(ToolEnd(tool_call_id=str(i), name="bash", args={"command": f"c{i}"},
                             result=f"输出{i}\n第二行"))
    app.expand_last()
    app.expand_last()
    body = "\n".join(committed(screen))
    assert "输出2" in body and "输出1" in body


def test_expanding_with_nothing_collapsed_says_so():
    app, screen = make()
    app.expand_last()
    assert any("没有" in l for l in committed(screen))


def test_collapsed_history_is_bounded():
    """不能无限攒——一个长会话的工具输出全留在内存里是白涨。"""
    from pai.core.events import ToolEnd

    app, _ = make()
    for i in range(200):
        app.on_event(ToolEnd(tool_call_id=str(i), name="bash", args={},
                             result="a\nb"))
    assert len(app._collapsed) <= 32
