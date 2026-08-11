"""工具调用状态行（feature 05 task 8，来源：用户提供的 CC 截图）。

契约是纯函数 `render_tool_line(events, width) -> str`——组件不持终端句柄，
与 roadmap 已拍板的 TUI 设计原则 1 同构，TUI 阶段可直接复用。
"""
import unicodedata

from pai.core.events import ToolEnd, ToolStart
from pai.modes.statusline import display_width, render_tool_line


def _end(name, result="ok", is_error=False, call_id="c"):
    return ToolEnd(tool_call_id=call_id, name=name, args={}, result=result, is_error=is_error)


def test_completed_tools_fold_by_name_with_count():
    events = [_end("bash") for _ in range(14)] + [_end("read_file") for _ in range(3)]
    line = render_tool_line(events, width=200)
    assert "✓ bash ×14" in line
    assert "✓ read_file ×3" in line


def test_single_call_has_no_count_suffix():
    assert render_tool_line([_end("bash")], width=200) == "✓ bash"


def test_running_tool_comes_first_with_arg_preview():
    events = [
        _end("bash", call_id="done"),
        ToolStart(tool_call_id="running", name="bash", args={"command": "echo 一"}),
    ]
    line = render_tool_line(events, width=200)
    assert line.startswith("◐ bash: echo 一")
    assert "✓ bash" in line
    assert line.index("◐") < line.index("✓")


def test_finished_tool_is_no_longer_running():
    events = [
        ToolStart(tool_call_id="c1", name="bash", args={"command": "ls"}),
        _end("bash", call_id="c1"),
    ]
    line = render_tool_line(events, width=200)
    assert "◐" not in line
    assert line == "✓ bash"


def test_error_tool_gets_cross_mark():
    events = [_end("bash"), _end("未知", is_error=True)]
    line = render_tool_line(events, width=200)
    assert "✗ 未知" in line and "✓ bash" in line


def test_truncates_by_terminal_columns_not_characters():
    """本 task 的核心：中文占两列。按字符数截断的实现在这里必红。"""
    events = [ToolStart(tool_call_id="c", name="bash",
                        args={"command": "回显一段很长很长很长很长的中文命令"})]
    line = render_tool_line(events, width=20)
    assert display_width(line) <= 20
    # 反证：同样内容按「字符数 ≤ 20」截会超出列宽
    assert len(line) < 20, "中文行的字符数必然小于列宽，否则说明没按列算"


def test_display_width_counts_east_asian_wide_as_two():
    assert display_width("abc") == 3
    assert display_width("中文") == 4
    assert display_width("a中b") == 4
    # 与标准库口径一致（W/F 算两列），不是自己拍的
    assert all(unicodedata.east_asian_width(c) in ("W", "F") for c in "中文")


def test_empty_events_render_empty_string():
    assert render_tool_line([], width=80) == ""


def test_no_color_unless_asked():
    events = [_end("bash")]
    assert "\x1b[" not in render_tool_line(events, width=80)
    assert "\x1b[" in render_tool_line(events, width=80, color=True)


def test_other_events_are_ignored():
    from pai.core.events import AgentStart, TurnStart

    events = [AgentStart(task="x"), TurnStart(step=1), _end("bash")]
    assert render_tool_line(events, width=80) == "✓ bash"


def test_colored_line_is_also_width_limited():
    """彩色路径同样要受列宽约束——而真 tty 上走的正是彩色路径。

    ANSI 转义符不占列宽，所以必须先按可见文本截断再上色，不能拿带转义符的串去量宽度。
    """
    import re

    events = [ToolStart(tool_call_id="c", name="bash",
                        args={"command": "回显一段很长很长很长很长的中文命令"})]
    colored = render_tool_line(events, width=20, color=True)
    visible = re.sub(r"\x1b\[[0-9;]*m", "", colored)
    assert display_width(visible) <= 20
    assert "\x1b[" in colored


def test_parts_beyond_width_are_dropped_not_cut_mid_escape():
    events = [_end(f"工具{i}") for i in range(10)]
    line = render_tool_line(events, width=24, color=True)
    import re

    visible = re.sub(r"\x1b\[[0-9;]*m", "", line)
    assert display_width(visible) <= 24


# ---- 接进 REPL：tty 走原地刷新，非 tty 走滚动行 ----


class _FakeStream:
    def __init__(self, tty):
        self.chunks: list = []
        self._tty = tty

    def isatty(self):
        return self._tty

    def write(self, text):
        self.chunks.append(text)

    def flush(self):
        pass

    @property
    def text(self):
        return "".join(self.chunks)


def test_default_handler_falls_back_to_scrolling_lines_off_tty():
    """管道/CI 里绝不能吐 \\r 与转义符——日志会变成乱码。"""
    from pai.modes.interactive import make_event_handler

    stream = _FakeStream(tty=False)
    handle = make_event_handler(stream=stream)
    handle(ToolStart(tool_call_id="c", name="bash", args={"command": "ls"}))
    handle(_end("bash", result="总共 0"))
    assert "🔧 bash" in stream.text
    assert "\r" not in stream.text and "\x1b[" not in stream.text


def test_default_handler_uses_inplace_statusline_on_tty():
    from pai.modes.interactive import make_event_handler

    stream = _FakeStream(tty=True)
    handle = make_event_handler(stream=stream)
    handle(ToolStart(tool_call_id="c", name="bash", args={"command": "ls"}))
    assert "\r\x1b[K" in stream.text
    assert "◐ bash: ls" in stream.text
    assert "🔧" not in stream.text          # 状态行开着就不再滚动重复一遍


def test_statusline_is_cleared_when_the_turn_ends():
    from pai.core.events import AgentEnd
    from pai.modes.interactive import make_event_handler

    stream = _FakeStream(tty=True)
    handle = make_event_handler(stream=stream)
    handle(ToolStart(tool_call_id="c", name="bash", args={"command": "ls"}))
    handle(AgentEnd(reason="final", text="好"))
    assert stream.chunks[-1] == "\r\x1b[K"   # 一轮结束把状态行擦掉，别粘在屏幕上


def test_display_width_ignores_escape_sequences():
    """转义序列不占列。

    今天状态行不会撞上（它**先按可见文本截断再上色**），但 TUI 的 CURSOR_MARKER
    是嵌在组件文本里的 APC 序列，宽度算错光标列就漂。pi 的 visibleWidth 同样
    显式处理 APC（K source-walks/pi-tui-main-screen.md 第六节）。
    """
    assert display_width("\x1b[36m中文\x1b[0m") == 4          # CSI（颜色）
    assert display_width("ab\x1b_pai:c\x07cd") == 4           # APC（CURSOR_MARKER）
    assert display_width("\x1b]8;;http://x\x07链接\x1b]8;;\x07") == 4   # OSC（超链接）


def test_display_width_of_plain_text_is_unchanged_by_escape_stripping():
    """回归护栏：既有调用方全部传纯文本，剥转义不许改变它们的结果。"""
    for text in ("", "abc", "中文", "a中b", "◐ read_file: a.py", "🎉"):
        assert display_width(text) == sum(
            2 if __import__("unicodedata").east_asian_width(c) in ("W", "F") else 1
            for c in text)
