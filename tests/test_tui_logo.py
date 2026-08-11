"""T9：启动 logo 与它的流光动画。

动画是**一束高光从左扫到右**：同一份字形，每帧只改配色。
所以「动画」这件事离线完全可测——测的是「帧在变、宽度不变、关色后无转义符」。
"""

import pytest

from pai.modes.statusline import display_width
from pai.tui import logo


def test_logo_is_a_block_of_lines_with_uniform_width():
    rows = logo.render(frame=0, color=False)
    assert len(rows) >= 3
    widths = {display_width(r) for r in rows}
    assert len(widths) == 1, f"logo 各行宽度不一致：{widths}"


def test_logo_fits_a_narrow_terminal_by_falling_back_to_a_wordmark():
    """窄终端不该被 logo 撑破行——放不下就退化成一行字。"""
    for width in (10, 20, 30):
        for line in logo.banner(width, frame=0, color=False):
            assert display_width(line) <= width


def test_frames_differ_so_the_shimmer_actually_moves():
    a = logo.render(frame=0, color=True)
    b = logo.render(frame=logo.FRAMES // 2, color=True)
    assert a != b


def test_shimmer_changes_only_color_never_geometry():
    """高光扫过时字形不能动——动的只有颜色。"""
    plain = [logo.strip(r) for r in logo.render(frame=0, color=True)]
    for frame in range(logo.FRAMES):
        assert [logo.strip(r) for r in logo.render(frame=frame, color=True)] == plain


def test_no_escape_codes_when_color_is_off():
    for frame in (0, 3, 7):
        for row in logo.render(frame=frame, color=False):
            assert "\x1b" not in row


def test_frames_wrap_around():
    assert logo.render(frame=0, color=True) == logo.render(frame=logo.FRAMES, color=True)


def test_banner_includes_a_subtitle_line():
    text = "\n".join(logo.banner(80, frame=0, color=False))
    assert logo.SUBTITLE in text


def test_narrow_fallback_still_names_the_program():
    """退化成一行时字形没了，必须留下「pai」这三个字母，否则用户不知道在跑什么。"""
    assert "pai" in "\n".join(logo.banner(12, frame=0, color=False))


def test_settled_frame_has_no_moving_highlight():
    """要 commit 进 scrollback 的那份不能停在「高光扫到一半」的姿态上——
    scrollback 里的东西不会再重画。"""
    a = logo.settled(80, color=True)
    b = logo.settled(80, color=True)
    assert a == b
    assert [logo.strip(r) for r in a][:3] == ["  " + r for r in logo.ROWS]
