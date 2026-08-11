"""T9：配色与字形。

**两条硬约束**（都来自用户 2026-08-11 的真跑截图）：
1. `🤖` 在用户终端上渲染成方块——**TUI 自己的字形一律不用 emoji**，
   只用「文本呈现」的符号（U+25CF 这类），宽度确定、字体覆盖率高。
2. 上色必须可关：非 tty / `NO_COLOR` 时一个转义符都不许吐（否则日志变乱码）。
"""

import unicodedata

import pytest

from pai.modes.statusline import display_width
from pai.tui import theme


ALL_GLYPHS = [theme.ANSWER, theme.SUMMARY, theme.QUEUE, theme.RULE,
              theme.PROMPT, theme.CONTINUATION, theme.DETAIL, theme.SELECTED]


@pytest.mark.parametrize("glyph", ALL_GLYPHS)
def test_no_glyph_is_emoji_presentation(glyph):
    """emoji 字体缺字就变方块，且宽度各终端不一致。用户截图里 `🤖` 就是这么坏的。"""
    for ch in glyph:
        assert ord(ch) < 0x1F000, f"{glyph!r} 含 emoji 码位 U+{ord(ch):X}"
        assert unicodedata.east_asian_width(ch) not in ("W", "F"), \
            f"{glyph!r} 是宽字符，会让列宽算错"


@pytest.mark.parametrize("glyph", ALL_GLYPHS)
def test_every_glyph_is_exactly_one_column(glyph):
    assert display_width(glyph) == 1


def test_paint_adds_color_when_enabled():
    painted = theme.paint("x", theme.DIM, color=True)
    assert painted.startswith("\x1b[") and painted.endswith(theme.RESET)
    assert display_width(painted) == 1          # 转义符不占列


def test_paint_is_a_noop_when_disabled():
    """非 tty / NO_COLOR：一个转义符都不许吐。"""
    assert theme.paint("x", theme.DIM, color=False) == "x"


def test_use_color_respects_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert theme.use_color(is_tty=True) is False
    monkeypatch.delenv("NO_COLOR")
    assert theme.use_color(is_tty=True) is True
    assert theme.use_color(is_tty=False) is False
