"""外来文本进终端前的消毒（R4#6）。

工具输出与 `!命令` 输出是**外来字节**：`grep --color=always`、`cat Makefile`、
任何带进度条的命令都会带上 pai 没打算发的东西。此前它们**原样**写进 scrollback：

- 光标移动 / 清屏类 CSI（`\\x1b[5A`、`\\x1b[2J`）会打乱 dock 的相对定位基准——
  这正是 feature 12「满屏阶梯」的同一类根因，只是来源换成了工具输出；
- `\\t` 在 pai 的**整条宽度链**上算 1 列（`display_width` / `theme.wrap` / `_fit` /
  选区切片全是），而真终端推进到 8 列 tab stop → 折行位置、截断、选区列全错；
- **`screen.py` 模拟器同样把 `\\t` 当 1 格**，于是 e2e 断言的是一个真终端上
  不存在的画面：测试绿、真机坏。

修法定在**入口消毒**而不是「教每一层认识 tab」：tab 的宽度取决于**当前列**，
而 `display_width(片段)` 结构上拿不到列号——它不可能算对。展开之后下游全部自洽，
模拟器与真终端也就不再分叉。

**边界是硬的：只消毒给终端看的那一份，模型拿到的仍是原始输出**——
命令真打印了什么，模型该看见什么。
"""

from pai.tui.sanitize import TAB_STOP, sanitize_terminal_text


def test_tabs_are_expanded_to_real_tab_stops():
    """展开而不是替换成单个空格：真终端是跳到下一个 8 的倍数。"""
    assert TAB_STOP == 8
    assert sanitize_terminal_text("a\tb") == "a       b"
    assert sanitize_terminal_text("12345678\tx") == "12345678        x"
    assert sanitize_terminal_text("ab\tcd\tef") == "ab      cd      ef"


def test_tabs_are_expanded_per_line_not_across_the_whole_blob():
    """tab stop 从**每行行首**重新起算——按整块算的话第二行起全错。"""
    assert sanitize_terminal_text("a\tb\nc\td") == "a       b\nc       d"


def test_cursor_movement_and_erase_sequences_are_stripped():
    """这些是会打乱 dock 相对定位的那一类，必须剥干净。"""
    assert sanitize_terminal_text("前\x1b[5A后") == "前后"
    assert sanitize_terminal_text("前\x1b[2J后") == "前后"
    assert sanitize_terminal_text("前\x1b[Kx") == "前x"


def test_osc_sequences_are_stripped():
    """OSC 能改窗口标题，**OSC 52 还能写用户的剪贴板**——工具输出不该有这个权限。"""
    assert sanitize_terminal_text("前\x1b]0;新标题\x07后") == "前后"
    assert sanitize_terminal_text("前\x1b]52;c;aGk=\x07后") == "前后"


def test_colour_is_stripped_too_and_that_is_a_choice():
    """**取舍**：连 SGR 一起剥。

    pai 自己给工具输出上色（缩进 + 主题色），外来颜色会与它打架；
    而未闭合的 SGR 会漏进 pai 自己的界面。代价是 `grep --color=always`
    的高亮看不见了——信息没丢，只是不着色。
    """
    assert sanitize_terminal_text("\x1b[31m红\x1b[0m") == "红"


def test_newlines_survive_and_other_c0_does_not():
    """`\\n` 是结构（pai 靠它数行），其余 C0 是噪音。"""
    assert sanitize_terminal_text("一\n二") == "一\n二"
    assert sanitize_terminal_text("进度\r覆盖") == "进度覆盖"
    assert sanitize_terminal_text("响铃\x07x") == "响铃x"


def test_plain_text_is_returned_unchanged():
    """平时必须完全没有存在感——含中文与 emoji 的正常输出一个字节都不许动。"""
    for text in ["普通输出", "多行\n输出\n结尾", "emoji 🎉 与中文混排", ""]:
        assert sanitize_terminal_text(text) == text


def test_the_simulator_and_a_real_terminal_agree_after_sanitising():
    """消毒之后模拟器画出来的，才是真终端会画的。

    未消毒时模拟器把 `\\t` 当一格存下（`'a\\tb'`），真终端跳到第 8 列——
    e2e 断言的是一个真终端上不存在的画面。
    """
    from pai.tui.screen import VirtualScreen

    raw, clean = "a\tb", sanitize_terminal_text("a\tb")

    dirty_screen = VirtualScreen(cols=20, rows=2)
    dirty_screen.write(raw)
    clean_screen = VirtualScreen(cols=20, rows=2)
    clean_screen.write(clean)

    assert dirty_screen.visible()[0].rstrip() == "a\tb"          # 旧行为：一格
    assert clean_screen.visible()[0].rstrip() == "a       b"     # 真终端就是这样


# ---- 边界：只消毒给终端看的那一份 ----


def test_the_model_still_receives_the_raw_output(tmp_path):
    """**这条边界是硬的**：屏幕上剥掉的东西，上下文里必须原样留着。

    命令真打印了什么，模型就该看见什么——它可能正要根据 ANSI 码判断
    「这个工具是不是把颜色开着」，或者要把输出原样转贴给别处。
    消毒是**显示层**的事，不是内容层的。
    """
    from pai.modes.interactive import _run_shell

    messages: list = []
    screen: list = []
    _run_shell(r"printf 'a\tb\x1b[31mred\x1b[0m'", messages=messages,
               session=None, out=screen.append)

    shown = "\n".join(screen)
    assert "\t" not in shown and "\x1b" not in shown        # 屏幕上干净了

    context = [m["content"] for m in messages if m.get("role") == "user"][-1]
    assert "\t" in context and "\x1b[31m" in context        # 上下文里原样还在


def test_tool_output_is_sanitised_before_it_reaches_the_transcript():
    """接线断言：`^O` 展开工具输出走的也是消毒后的那一份。"""
    from pai.core.events import ToolEnd
    from pai.tui.app import _display_result

    event = ToolEnd(tool_call_id="c1", name="bash", args={"command": "cat Makefile"},
                    result="all:\tgcc -o out\n\x1b[2Jclean:\trm -f out", is_error=False)

    shown = _display_result(event)

    assert "\t" not in shown
    assert "\x1b" not in shown
    assert shown.startswith("all:    gcc -o out")
