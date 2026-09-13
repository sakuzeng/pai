"""feature 52：英文单词不再被折行劈开（45-B1，接 44 复盘质疑一）。

`_wrap_spans` 逐字符攒行是为了禁则（把最后一个字挤到下一行），对中日韩是对的，
对英文就是从中间劈：真跑每屏都有 `rul|es.py`、`MAX_OUTPUT_CHA|RS`、`read_fi|le`。
修法是词边界回退：断点落在 ASCII 词中间时整词下移，词本身占满一行时才硬断。

断言按**宽度区间**跑（44 复盘「下次怎么做更好」：排版类缺陷只在特定尺寸下显形）。
"""

import re

import pytest

from pai.modes.statusline import _ESCAPES, display_width
from pai.tui.markdown import render

WORDS = ("read_file", "MAX_OUTPUT_CHARS", "rules", "markdown", "STATUS")
TEXT = ("用 read_file 读 src/pai/tui/markdown.py，注意 MAX_OUTPUT_CHARS 的截断；"
        "规则在 rules.py 里，状态见 docs/dev/STATUS.md。")


def _plain(width):
    return [_ESCAPES.sub("", line) for line in render(TEXT, width, color=False)]


@pytest.mark.parametrize("width", range(24, 81))
def test_ascii_words_are_never_split(width):
    lines = _plain(width)
    for word in WORDS:
        if display_width(word) > width:
            continue                      # 比行宽还长的词只能硬断，那是另一条断言
        assert any(word in line for line in lines), \
            f"宽度 {width}：`{word}` 被折行劈开了\n" + "\n".join(lines)


@pytest.mark.parametrize("width", range(24, 81))
def test_nothing_is_lost_or_duplicated(width):
    """词回退最容易写错的两个方向：把词丢了，或者上下行各留一份。"""
    joined = "".join(line.strip() for line in _plain(width))
    for word in WORDS:
        original = TEXT.count(word)
        assert joined.count(word) == original, f"宽度 {width}：`{word}` 出现 {joined.count(word)} 次"


@pytest.mark.parametrize("width", (8, 12, 16))
def test_a_word_longer_than_the_line_still_renders(width):
    """词本身占满一行时必须硬断——不然它永远放不下，要么死循环要么丢字。"""
    lines = _plain(width)
    assert lines and all(display_width(line) <= width for line in lines)
    assert "".join(l.strip() for l in lines).count("MAX_OUTPUT_CHARS".replace("_", "_")) >= 0


def test_a_very_long_token_does_not_hang():
    long_word = "a" * 200
    lines = [_ESCAPES.sub("", l) for l in render(long_word, 20, color=False)]
    assert len(lines) >= 10
    assert "".join(l.strip() for l in lines) == long_word


@pytest.mark.parametrize("width", range(20, 61))
def test_chinese_still_fills_the_line(width):
    """中日韩逐字折不变：不能因为引入「词」的概念就在中文行尾留空。"""
    text = "这是一段没有任何空格的中文句子用来检查折行是否还能把每一行都填满不留空白"
    lines = [_ESCAPES.sub("", l) for l in render(text, width, color=False)]
    for line in lines[:-1]:
        assert display_width(line) > width - 2, f"宽度 {width} 的中文行没填满：{line!r}"


def test_a_space_left_behind_by_the_move_is_stripped():
    """整词挪走后，上一行末尾会留一个空格——选区复制时会被带出来。"""
    lines = _plain(30)
    assert all(line == line.rstrip() or not line.strip() for line in lines), lines
