"""T6：事件 → dock（活动区 / 队列区 / 状态行）。

形态参照 CC 实物截图（evidence/20260811-cc实物截图/说明.md）：
活动区把并发**按动作聚合计数**（工具多时不撑高 dock），状态行带转圈 + 已用时 + token。
"""

import json
from pathlib import Path

from pai.core.events import AgentEnd, AgentStart, ToolEnd, ToolStart
from pai.modes.statusline import display_width
from pai.tui.dock import Dock


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def make():
    clock = Clock()
    return Dock(now=clock), clock


def text_of(dock, width=60):
    return "\n".join(dock.render(width))


def test_idle_dock_has_no_activity_lines():
    dock, _ = make()
    assert dock.activity_lines(60) == []


def test_tool_start_shows_up_in_the_activity_area():
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}))
    assert "a.py" in text_of(dock)


def test_concurrent_tools_are_visible_at_the_same_time():
    """11 复盘质疑二：做了并发却看不见并发。这条是它的落点。"""
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}))
    dock.handle(ToolStart(tool_call_id="2", name="bash", args={"command": "npm test"}))
    summary = dock.activity_lines(60)[0]
    # 两个不同动作同时在跑：摘要行里两个都得在（这就是「看得见并发」）
    assert "读文件" in summary and "跑命令" in summary
    assert "a.py" in text_of(dock) and "npm test" in text_of(dock)


def test_same_tool_running_twice_shows_a_count_of_two():
    """并发跑同一个工具时，看得出是 2 个不是 1 个。"""
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}))
    dock.handle(ToolStart(tool_call_id="2", name="read_file", args={"path": "b.py"}))
    assert "读文件 2" in dock.activity_lines(60)[0]


def test_activity_summary_aggregates_by_action_not_one_line_per_tool():
    """照 CC：工具多时聚合成一行，不把 dock 撑高。"""
    dock, _ = make()
    for i in range(6):
        dock.handle(ToolStart(tool_call_id=str(i), name="read_file",
                              args={"path": f"f{i}.py"}))
    assert len(dock.activity_lines(60)) <= 4


def test_tool_end_removes_it_from_the_activity_area():
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="read_file", args={"path": "a.py"}))
    dock.handle(ToolEnd(tool_call_id="1", name="read_file",
                        args={"path": "a.py"}, result="ok"))
    assert dock.activity_lines(60) == []


def test_status_line_shows_elapsed_and_tokens():
    dock, clock = make()
    dock.handle(AgentStart(task="干活"))
    clock.advance(16)
    dock.note_usage(536)
    line = dock.status_line(60)
    assert "16s" in line and "536" in line


def test_status_line_shows_a_spinner_that_moves():
    dock, clock = make()
    dock.handle(AgentStart(task="干活"))
    first = dock.status_line(60)
    clock.advance(0.5)
    second = dock.status_line(60)
    assert first != second


def test_permission_mode_lives_in_the_footer_not_the_status_line():
    """模式只该在一个地方出现。

    此前状态行空闲时也占一行只写个 `default`，而 footer 里已经有了——
    用户 2026-08-11 的截图里就是那行孤零零的 `default`。
    """
    dock, _ = make()
    dock.set_mode("acceptEdits")
    dock.set_cwd("/tmp/x")
    assert dock.status_line(60) == ""                     # 空闲时不占行
    assert "acceptEdits" in dock.footer_lines(60)[0]


def test_status_line_appears_only_when_there_is_something_to_say():
    dock, clock = make()
    assert dock.status_line(60) == ""
    dock.handle(AgentStart(task="干活"))
    assert dock.status_line(60) != ""


def test_status_line_says_how_many_requests_are_waiting():
    """被抑制却不说，就是把「等待」变成「卡住」。"""
    dock, _ = make()
    dock.set_pending(2)
    assert "2" in dock.status_line(60)


def test_queue_area_shows_pending_steering_messages():
    """feature 18：这个数字的语义从「排队等本轮结束」变成「**待注入**」——
    干活期间会随每次 drain 在本轮内减少（补 2），不再是只在轮末归零。"""
    dock, _ = make()
    dock.set_queued(3)
    assert "3" in "\n".join(dock.queue_lines(60))


def test_agent_end_clears_activity_and_yields_a_summary_to_commit():
    """turn 跑完要在 scrollback 里留一行痕迹，不是清空了事（照 CC 的 `Cooked for …`）。"""
    dock, clock = make()
    dock.handle(AgentStart(task="干活"))
    dock.handle(ToolStart(tool_call_id="1", name="bash", args={"command": "x"}))
    clock.advance(408)
    dock.note_usage(12300)
    summary = dock.handle(AgentEnd(reason="final", text="done"))
    assert dock.activity_lines(60) == []
    assert summary is not None
    assert "6m" in summary and "48s" in summary
    assert "12.3k" in summary


def test_every_rendered_line_fits_the_terminal():
    dock, _ = make()
    dock.set_mode("bypassPermissions")
    dock.set_pending(9)
    dock.set_queued(2)
    dock.handle(AgentStart(task="x"))
    dock.handle(ToolStart(tool_call_id="1", name="bash",
                          args={"command": "回声测试中文宽度" * 12}))
    for width in (12, 24, 40, 80):
        for line in dock.render(width):
            assert display_width(line) <= width, (width, line)


def test_real_session_trajectory_drives_the_dock():
    """AGENTS.md 测试规约：至少一条测试拿真实会话轨迹当输入——
    编的字符串测不出中文、tool_calls.arguments 这类真实坑。"""
    raw = Path(__file__).with_name("fixtures").joinpath("real_turn.jsonl")
    records = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    dock, _ = make()
    dock.handle(AgentStart(task="读一下 README"))
    names = {}
    seen = 0
    for record in records:
        for call in record.get("tool_calls") or []:
            # arguments 是 **JSON 字符串**，不是 dict——编的字符串测不出这个坑
            args = json.loads(call["function"]["arguments"])
            names[call["id"]] = call["function"]["name"]
            dock.handle(ToolStart(tool_call_id=call["id"],
                                  name=call["function"]["name"], args=args))
            seen += 1
        if record.get("role") == "tool":
            cid = record["tool_call_id"]
            dock.handle(ToolEnd(tool_call_id=cid, name=names[cid],
                                args={}, result=record["content"]))
    assert seen >= 2
    assert dock.activity_lines(60) == []
    for line in dock.render(80):
        assert display_width(line) <= 80


# --- 视觉形态（用户真跑后指出「没有 TUI 的样子」）------------------------

def test_dock_has_a_separator_rule_above_the_input():
    """CC 与 pi 共同的视觉语汇：一条横线把 dock 与 scrollback 分开。

    没有它，dock 就是「又两行普通输出」，看不出是被接管的区域。
    """
    dock, _ = make()
    rule = dock.rule(20)
    assert len(rule) > 0
    assert display_width(rule) == 20


def test_footer_shows_cwd_and_model_and_context():
    dock, _ = make()
    dock.set_cwd("/tmp/paitest")
    dock.set_model("deepseek-v4-flash")
    dock.set_context(1234, 1_000_000)
    text = "\n".join(dock.footer_lines(70))
    assert "paitest" in text
    assert "deepseek-v4-flash" in text
    assert "1.0M" in text          # 窗口
    assert "%" in text             # 占用比例


def test_footer_right_aligns_the_model_side():
    dock, _ = make()
    dock.set_cwd("/tmp/paitest")
    dock.set_model("m")
    dock.set_context(0, 1000)
    line = dock.footer_lines(60)[0]
    assert display_width(line) == 60          # 恰好铺满，右侧贴边
    assert line.rstrip().endswith("0.0%/1.0k")
    assert line.startswith("/tmp/paitest")


def test_footer_degrades_gracefully_on_a_narrow_terminal():
    dock, _ = make()
    dock.set_cwd("/a/very/long/path/that/will/not/fit/anywhere")
    dock.set_model("some-very-long-model-name")
    dock.set_context(999, 1000)
    for width in (10, 20, 30):
        for line in dock.footer_lines(width):
            assert display_width(line) <= width


def test_cwd_is_shortened_with_a_tilde_for_home():
    import os
    dock, _ = make()
    dock.set_cwd(os.path.expanduser("~/somewhere"))
    assert "~" in dock.footer_lines(60)[0]


def test_render_includes_rule_and_footer():
    dock, _ = make()
    dock.set_cwd("/tmp/x")
    dock.set_model("m")
    dock.set_context(0, 1000)
    lines = dock.render(40)
    assert any(set(l) <= {"─"} and l for l in lines), lines   # 有分隔线
    assert any("m" in l for l in lines)


# --- 活动区做成 CC 那样（用户 2026-08-11 指定形态）------------------------

def test_activity_summary_carries_a_bullet_and_elapsed():
    """形如 `● 跑命令 1 · 11s…`——点 + 聚合计数 + 本轮已用时。"""
    dock, clock = make()
    dock.handle(AgentStart(task="x"))
    dock.handle(ToolStart(tool_call_id="1", name="bash", args={"command": "ls"}))
    clock.advance(11)
    head = dock.activity_lines(60)[0]
    assert head.startswith("●")
    assert "11s" in head and head.rstrip().endswith("…")


def test_shell_command_detail_is_prefixed_with_a_dollar():
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="bash", args={"command": "ls -la"}))
    detail = "\n".join(dock.activity_lines(60)[1:])
    assert "$ ls -la" in detail


def test_multiline_command_keeps_its_own_lines_aligned():
    """CC 把多行命令原样展开，续行缩进到与首行对齐——挤成一行就没法读了。"""
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="bash",
                          args={"command": "python3 - <<'PY'\np = 1\ns = 2\nPY"}))
    lines = dock.activity_lines(60)
    assert any(l.lstrip().startswith("└ $ python3") for l in lines)
    assert any("p = 1" in l for l in lines)
    assert any("s = 2" in l for l in lines)
    indents = [len(l) - len(l.lstrip()) for l in lines[2:] if l.strip()]
    assert len(set(indents)) == 1, lines          # 续行缩进一致


def test_long_command_is_capped_with_a_remainder_hint():
    dock, _ = make()
    dock.handle(ToolStart(tool_call_id="1", name="bash",
                          args={"command": "\n".join(f"line{i}" for i in range(40))}))
    lines = dock.activity_lines(80)
    assert len(lines) <= 10
    assert any("还有" in l and "行" in l for l in lines)


def test_each_tool_shows_its_own_elapsed_time():
    """并发时「谁跑了多久」是最要紧的信息——聚合计数说不出这个。"""
    dock, clock = make()
    dock.handle(AgentStart(task="x"))
    dock.handle(ToolStart(tool_call_id="1", name="bash", args={"command": "slow"}))
    clock.advance(9)
    dock.handle(ToolStart(tool_call_id="2", name="read_file", args={"path": "a.py"}))
    clock.advance(2)
    text = "\n".join(dock.activity_lines(70))
    assert "(11s)" in text          # 先起的那个
    assert "(2s)" in text           # 后起的那个


def test_activity_lines_still_fit_any_width():
    dock, _ = make()
    dock.handle(AgentStart(task="x"))
    dock.handle(ToolStart(tool_call_id="1", name="bash",
                          args={"command": "回声测试中文宽度" * 10 + "\n第二行也很长" * 10}))
    for width in (12, 24, 40, 80):
        for line in dock.activity_lines(width):
            assert display_width(line) <= width, (width, line)


def test_summary_line_is_dimmed_like_tool_lines():
    """摘要是元信息，与工具行同级压暗——让位给用户的问题与 pai 的答案。"""
    from pai.tui import theme

    dock = Dock(now=lambda: 0.0, color=True)
    dock.handle(AgentStart(task="x"))
    assert theme.GREY in dock.handle(AgentEnd(reason="final", text=""))
