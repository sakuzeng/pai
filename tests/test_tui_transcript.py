"""Transcript：一份**按宽度重新渲染**的会话文档（feature 13 T2）。

为什么不能存行：今天 `app.commit(lines)` 收的是按**当时宽度**排好的行，
main-screen 下这没问题（打出去就归终端了，终端自己会折）；
alt 屏下 pai 每帧都要重画，窗口一变宽变窄，存着的行就全是错的。
"""

import pytest

from pai.tui.transcript import Transcript, TranscriptEntry, dynamic_entry, text_entry


def test_entry_renders_lines_for_a_width():
    entry = dynamic_entry(lambda w: [f"宽度是 {w}"])
    assert entry.render(30) == ["宽度是 30"]


def test_text_entry_wraps_by_display_width():
    """alt 屏里终端不再替你折行——不自己折就是被截断（内容丢失）。"""
    entry = text_entry(["abcdefghij"])
    assert entry.render(4) == ["abcd", "efgh", "ij"]
    assert entry.render(10) == ["abcdefghij"]


def test_text_entry_counts_chinese_as_two_columns():
    entry = text_entry(["中文中文"])
    assert entry.render(4) == ["中文", "中文"]


def test_same_width_is_served_from_cache():
    calls = []

    def render(width):
        calls.append(width)
        return ["x" * width]

    entry = dynamic_entry(render)
    entry.render(20)
    entry.render(20)
    assert calls == [20]


def test_changing_width_must_recompute():
    """本 task 的核心：缓存把旧宽度的行发出来 = resize 之后满屏错位。"""
    calls = []

    def render(width):
        calls.append(width)
        return ["x" * width]

    entry = dynamic_entry(render)
    assert entry.render(20) == ["x" * 20]
    assert entry.render(8) == ["x" * 8]
    assert calls == [20, 8]


def test_total_lines_follows_width():
    doc = Transcript()
    doc.append(text_entry(["abcdefghij"]))
    doc.append(text_entry(["ab"]))
    assert doc.total_lines(10) == 2
    assert doc.total_lines(4) == 4          # 第一条折成 3 行


def test_slice_takes_a_viewport_across_entry_boundaries():
    doc = Transcript()
    doc.append(text_entry(["one", "two"]))
    doc.append(text_entry(["three"]))
    doc.append(text_entry(["four"]))
    assert doc.slice(20, 1, 2) == ["two", "three"]


def test_slice_clamps_instead_of_raising():
    doc = Transcript()
    doc.append(text_entry(["one"]))
    assert doc.slice(20, 5, 3) == []        # top 越界
    assert doc.slice(20, 0, 99) == ["one"]  # height 超过剩余
    assert doc.slice(20, -3, 2) == ["one"]  # 负数
    assert doc.slice(20, 0, 0) == []


def test_empty_transcript_is_empty_not_an_error():
    doc = Transcript()
    assert doc.total_lines(20) == 0
    assert doc.slice(20, 0, 5) == []


def test_clear_drops_everything():
    doc = Transcript()
    doc.append(text_entry(["one"]))
    doc.clear()
    assert doc.total_lines(20) == 0


def test_entry_render_returns_a_copy_callers_cannot_corrupt_the_cache():
    """条目的行数组被交出去后如果被就地改了，缓存里那份就跟着烂了。"""
    entry = text_entry(["one"])
    got = entry.render(20)
    got.append("我是外面塞进来的")
    assert entry.render(20) == ["one"]


def test_render_width_zero_or_negative_does_not_hang():
    entry = text_entry(["abc"])
    assert entry.render(0) == ["abc"]


def test_entry_is_the_component_contract_shape():
    """与 `Component.render(width) -> list[str]` 同构，于是能被同一批工具消费。"""
    entry = text_entry(["one"])
    assert isinstance(entry, TranscriptEntry)
    assert callable(entry.render)
    with pytest.raises(TypeError):
        entry.render()          # 宽度是必需参数，不许有「默认宽度」这种东西
