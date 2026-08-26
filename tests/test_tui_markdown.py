"""模型回答的 markdown 渲染（feature 44）。

只在 TUI 上做（拍板问 1·A）：那里答案是一次性 commit 的，与流式没有冲突，
且 transcript 能按宽度重排。REPL / once 仍是原文——那两条路是管道友好的定位。

本文件第一条是**逐字比对整体输出**。出处是 feature 43 复盘学到的那条：
片段断言查的是「有没有」，逐字断言查的才是「是不是只有」——43 那轮的空文件头
噪音就是因为 14 条断言全在看别处才漏掉的。
"""
import re

import pytest

from pai.tui.markdown import render
from pai.tui.width import _ESCAPES, display_width


SAMPLE = """# 标题

这是**粗体**与`代码`。

- 第一项
- 第二项

| 名字 | 值 |
| --- | ---: |
| 中文 | 42 |

```python
def f():
    return 1
```
"""


def test_the_whole_rendering_verbatim():
    """整体逐字比对。改任何一处排版都会红——这正是它要买的东西。"""
    assert render(SAMPLE, 40, color=False) == [
        "标题",
        "━━━━",
        "",
        "这是粗体与代码。",
        "",
        "• 第一项",
        "• 第二项",
        "",
        " 名字  值",
        " ----  --",
        " 中文  42",
        "",
        "┌─ python",
        "│ def f():",
        "│     return 1",
        "└─",
    ]


# ---- 表格：这一格的全部价值就在对齐 ----


def test_a_mixed_width_table_really_aligns():
    """中英混排要真的对齐。判据是「每一行的 display_width 相等」，不是「看起来还行」。

    用 `len()` 算列宽的话，「中文」会被算成 2 而不是 4 列，整张表往左塌——
    这正是 md 表格原文在中英混排下对不齐的原因，也是本功能要修的那一个。
    """
    text = "| name | 说明 |\n| --- | --- |\n| a | 很长的中文说明 |\n| 中文名 | x |\n"
    lines = render(text, 80, color=False)
    widths = {display_width(line) for line in lines if line}
    assert len(widths) == 1, f"各行宽度不一致：{widths}"


def test_table_columns_start_at_the_same_column_on_every_row():
    """比「等宽」更强的一条：每一列的起始列号在每一行都相同。

    等宽可以靠尾部补空格蒙混过去（首列宽了、次列窄了，总宽照样相等），
    而列起点相同才是「对齐」的定义。
    """
    text = "| a | bb |\n| --- | --- |\n| 中文 | c |\n| d | 很长很长 |\n"
    lines = [ln for ln in render(text, 80, color=False) if ln]

    starts = []
    for line in lines:
        if set(line.strip()) <= {"-"}:
            continue                        # 分隔行不参与（它没有单元格内容）
        col, found = 0, []
        prev_blank = True
        for ch in line:
            if prev_blank and ch != " ":
                found.append(col)
            prev_blank = ch == " "
            col += display_width(ch)
        starts.append(found)
    assert len(set(map(tuple, starts))) == 1, f"列起点不一致：{starts}"


def test_a_too_wide_table_is_compressed_not_overflowed():
    """窄屏时按列压缩 + 单元格截断（拍板问 4·A），绝不许溢出。

    溢出的后果不是难看：终端一折，`app` 那边「我以为写了 1 行」就错了，
    正是 feature 12「满屏阶梯」的成因。
    """
    text = ("| 很长的列名一 | 很长的列名二 | 很长的列名三 |\n"
            "| --- | --- | --- |\n"
            "| 内容内容内容内容 | 内容内容内容内容 | 内容内容内容内容 |\n")
    lines = render(text, 30, color=False)
    assert lines, "表格被吃掉了"
    for line in lines:
        assert display_width(line) <= 30, f"溢出：{display_width(line)} > 30 —— {line!r}"
    assert any("…" in line for line in lines), "截断了却没有省略号，丢得看不见"


def test_the_same_table_reflows_when_the_width_changes():
    """TUI 独有的那一条：窗口拉宽，被截掉的信息要回来。"""
    text = "| 名字 | 说明 |\n| --- | --- |\n| a | 这是一段很长很长很长的说明文字 |\n"
    narrow = render(text, 24, color=False)
    wide = render(text, 100, color=False)

    assert any("…" in line for line in narrow)
    assert not any("…" in line for line in wide), "宽屏还在截断"
    assert "这是一段很长很长很长的说明文字" in "\n".join(wide)


def test_a_pipe_line_without_a_separator_row_is_not_a_table():
    """没有分隔行就不是表格，得当普通段落**原样**透出。

    断言整行逐字相等而不是「竖线还在」（第一版就是那么写的，注入反证没红才发现）：
    把它当成表格渲染的话，「竖线」照样在，只是被拆成了单元格重排——
    内容没丢但话被改了，而弱断言看不出这个区别。
    """
    text = "这行里有 | 竖线 | 但它不是表格\n"
    assert render(text, 60, color=False) == ["这行里有 | 竖线 | 但它不是表格"]


# ---- 代码块 ----


def test_inline_rules_do_not_touch_code_block_content():
    """代码块里的 `**` 与 `|` 是代码，不是 md 标记。吃掉它们就是改了模型的输出。"""
    text = "```\na = b ** 2 | mask\n```\n"
    out = "\n".join(render(text, 40, color=False))
    assert "a = b ** 2 | mask" in out


def test_an_unclosed_fence_still_renders_its_content():
    """模型的输出被 token 上限截断时，围栏是不闭合的。

    此时把「没收完的代码块」整段吃掉是最坏的做法——用户看到的是空白，
    而内容其实在。宁可当成一个开着的代码块渲染出来。
    """
    text = "```python\ndef f():\n    return 1\n"
    out = "\n".join(render(text, 40, color=False))
    assert "def f():" in out and "return 1" in out


def test_long_code_lines_wrap_instead_of_being_cut():
    """代码宁可折行也不许截断——截断的代码复制出去是坏的。"""
    text = "```\n" + "x = " + "1234567890" * 6 + "\n```\n"
    lines = render(text, 30, color=False)
    body = "".join(line[2:] for line in lines if line.startswith("│"))
    assert "1234567890" * 6 in body
    for line in lines:
        assert display_width(line) <= 30


# ---- 行内与上色 ----


def test_no_escape_bytes_at_all_when_color_is_off():
    """theme 的既有硬约束：非 tty / NO_COLOR 时一个转义符都不许吐。"""
    out = "\n".join(render(SAMPLE, 40, color=False))
    assert "\x1b" not in out


def test_color_changes_bytes_but_not_a_single_column():
    """上色不许改变任何一行的显示宽度——改了的话表格就在有色终端上塌了。"""
    plain = render(SAMPLE, 40, color=False)
    painted = render(SAMPLE, 40, color=True)
    assert "\x1b" in "\n".join(painted)
    assert [display_width(x) for x in plain] == [display_width(x) for x in painted]
    assert [_ESCAPES.sub("", x) for x in painted] == plain


def test_inline_markers_are_stripped_not_left_as_text():
    """「预览而不是原文」的字面意思：`**` 与反引号不该出现在渲染结果里。"""
    out = "\n".join(render("这是**粗体**与`代码`与*斜体*。\n", 40, color=False))
    assert "**" not in out and "`" not in out and "*" not in out
    assert "粗体" in out and "代码" in out and "斜体" in out


def test_unmatched_inline_markers_are_left_alone():
    """落单的标记不是语法，是内容。吃掉它就是改了模型的话。"""
    out = "\n".join(render("2 ** 3 = 8，还有一个孤零零的 ` 反引号\n", 40, color=False))
    assert "2 ** 3 = 8" in out
    assert "`" in out


# ---- 其余块级 ----


def test_headings_are_distinguishable_without_color():
    """标题在没有颜色时也要看得出是标题——靠下面那条线，不靠字重。

    h1/h2 用粗线、h3+ 用细线：级别差异也不能只靠颜色表达。
    """
    h1 = render("# 一级\n", 40, color=False)
    h3 = render("### 三级\n", 40, color=False)
    assert h1 == ["一级", "━━━━"]
    assert h3 == ["三级", "────"]


def test_nested_lists_indent_one_level():
    out = render("- 外层\n  - 内层\n", 40, color=False)
    assert out == ["• 外层", "  ◦ 内层"]


def test_ordered_lists_keep_their_own_numbers():
    """模型写 `3.` 就是想说第三条，不许重新编号。"""
    out = render("3. 第三\n4. 第四\n", 40, color=False)
    assert out == ["3. 第三", "4. 第四"]


def test_a_long_list_item_wraps_aligned_under_its_text():
    """续行要对齐到正文下面，不是顶格——顶格会让人以为是新的一项。"""
    out = render("- " + "很长" * 20 + "\n", 20, color=False)
    assert out[0].startswith("• ")
    for line in out[1:]:
        assert line.startswith("  "), f"续行没对齐：{line!r}"
    for line in out:
        assert display_width(line) <= 20


def test_blockquote_and_rule():
    out = render("> 引用一句\n\n---\n", 10, color=False)
    assert out[0] == "│ 引用一句"
    assert out[-1] == "─" * 10


def test_nothing_is_lost(tmp_path):
    """总守卫：渲染器把内容弄丢，比不渲染糟得多。

    拿一段用上了每种语法的文本，逐个断言「实义词」都还在。
    这条挡的是「某个分支忘了 append」这类错——它不会让别的断言变红，
    因为别的断言都在看自己那一块。
    """
    text = ("# 甲\n\n段落乙\n\n- 丙\n- 丁\n\n| 戊 | 己 |\n| --- | --- |\n| 庚 | 辛 |\n\n"
            "> 壬\n\n```\n癸\n```\n\n普通的尾巴\n")
    out = "\n".join(render(text, 60, color=False))
    for word in ("甲", "段落乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸", "普通的尾巴"):
        assert word in out, f"渲染把 {word} 弄丢了"


def test_closing_punctuation_never_starts_a_line():
    """中文禁则的「避头」：闭合标点不许出现在行首。

    这条是真跑看出来的——宽 40 时一段中文折成了「…这样写」/「，然后一个表格。」，
    逗号顶在行首。中文排版里那是硬伤，而所有既有断言都在看宽度，没有一条在看
    第一个字符是什么。
    """
    text = "这是一段中文，它会在某个位置折行，看标点会不会跑到行首。\n"
    for width in range(8, 40):
        for line in render(text, width, color=False):
            assert not line[:1] or line[0] not in "，。、；：？！）", \
                f"width={width} 时标点顶到了行首：{line!r}"


def test_avoiding_a_line_start_never_drops_or_duplicates_a_character():
    """避头是把字挤下来，不是删掉或复制——这类改动最容易在边界上丢一个字。"""
    text = "甲乙丙丁，戊己庚辛。壬癸子丑，寅卯辰巳。\n"
    for width in range(6, 30):
        joined = "".join(render(text, width, color=False))
        assert joined == text.strip(), f"width={width} 时字符对不上：{joined!r}"


def test_a_single_newline_is_a_hard_break_not_a_soft_one():
    """模型写下的换行就是想换行——不按 CommonMark 的「软换行合成一段」。

    这条是既有 e2e 撞出来的：一条 21 行的答案被合成一段之后，内容一个字没丢，
    但结构没了（滚动测试因此滚不动，因为屏幕上不再有那么多行）。
    对话文本与文档文本在这一点上取向相反，而这里是对话。
    """
    out = render("第一行\n第二行\n第三行\n", 40, color=False)
    assert out == ["第一行", "第二行", "第三行"]


def test_plain_text_without_any_markdown_is_untouched():
    """回归守卫：一段没有任何 md 语法的文字，渲染前后一模一样。

    绝大多数回答就是这样的文字。这条要是红了，说明渲染器在给普通话加戏。
    """
    text = "第一段。\n\n第二段，里面有 a-b 和 3.5 这种像标记又不是标记的东西。\n"
    assert render(text, 60, color=False) == [
        "第一段。", "", "第二段，里面有 a-b 和 3.5 这种像标记又不是标记的东西。"]


# ---- 接线到 app ----


def _app(color=False, markdown=True):
    """用真的 AltScreenRenderer（它 `keeps_transcript`，答案才会进 transcript）。

    这里要的是「渲染结果按宽度重算」这条性质，而它只在 alt 屏那条路上成立——
    main-screen 下 commit 出去的行 pai 就够不着了（feature 13 的形态）。
    """
    from pai.tui.app import TuiApp
    from pai.tui.altscreen import AltScreenRenderer
    from pai.tui.scroll import ScrollState
    from pai.tui.selection import Selection
    from pai.tui.transcript import Transcript

    transcript, scroll, selection = Transcript(), ScrollState(), Selection()
    renderer = AltScreenRenderer(write=lambda _d: None, width=lambda: 40,
                                 height=lambda: 20, transcript=transcript,
                                 scroll=scroll, selection=selection)
    return TuiApp(renderer=renderer, transcript=transcript, scroll=scroll,
                  selection=selection, color=color, markdown=markdown)


def test_the_answer_goes_through_markdown_and_reflows_with_width():
    """答案要走渲染，且是 `dynamic_entry`——表格跟着窗口宽度重排靠的就是这个。

    存成一份定死的行数组的话，拉宽窗口表格不会变，而那正是拍板问 4 里
    「截掉的信息会回来」那条承诺的落点。
    """
    from pai.core.events import AssistantMessage

    app = _app()
    app.on_event(AssistantMessage(
        content="| a | 说明 |\n| --- | --- |\n| 1 | 很长很长很长很长的说明 |\n"))
    entry = app.transcript.entries[-1]

    narrow = "\n".join(entry.render(24))
    wide = "\n".join(entry.render(90))
    assert "…" in narrow
    assert "很长很长很长很长的说明" in wide


def test_the_answer_still_wears_its_dot():
    from pai.core.events import AssistantMessage
    from pai.tui import theme

    app = _app()
    app.on_event(AssistantMessage(content="一句话"))
    lines = app.transcript.entries[-1].render(40)
    assert lines[0].startswith(theme.ANSWER + " ")


def test_continuation_lines_align_under_the_first():
    """圆点是个 gutter：后续行缩进到正文下面，不顶格。"""
    from pai.core.events import AssistantMessage

    app = _app()
    app.on_event(AssistantMessage(content="- 甲\n- 乙\n"))
    lines = app.transcript.entries[-1].render(40)
    assert lines[0].startswith("● • 甲")
    assert lines[1] == "  • 乙"


def test_markdown_can_be_turned_off():
    """逃生口：渲染要是把什么弄拧了，用户得有办法退回原文（同 tui.altScreen / tui.mouse）。"""
    from pai.core.events import AssistantMessage

    app = _app(markdown=False)
    app.on_event(AssistantMessage(content="# 标题\n\n**粗**"))
    text = "\n".join(app.transcript.entries[-1].render(40))
    assert "# 标题" in text and "**粗**" in text


def test_the_setting_defaults_to_on_and_rejects_garbage():
    from pai.core.settings import markdown_enabled

    assert markdown_enabled({}) is True
    assert markdown_enabled({"tui": {"markdown": False}}) is False
    warned = []
    assert markdown_enabled({"tui": {"markdown": "yes"}}, warn=warned.append) is True
    assert warned
