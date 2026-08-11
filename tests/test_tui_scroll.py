"""滚动状态机（feature 13 T3）：纯状态、零 IO。

语义抄 pi 的 `ScrollView`：**跟随末尾**是默认，手动往上滚就关掉它。
这条不是装饰——「流式输出时用户正在往回翻历史」是 alt 屏下每天都会发生的事，
不关跟随的话用户每滚一次就被新内容弹回底部。
"""

from pai.tui.scroll import PAGE_OVERLAP, ScrollState


def test_starts_following_the_end():
    s = ScrollState()
    s.update(content_height=100, viewport_height=10)
    assert s.following_end
    assert s.scroll_top == 90


def test_new_content_sticks_to_the_bottom_while_following():
    s = ScrollState()
    s.update(100, 10)
    s.update(120, 10)
    assert s.scroll_top == 110


def test_scrolling_up_turns_following_off():
    s = ScrollState()
    s.update(100, 10)
    s.scroll_by(-5)
    assert not s.following_end
    assert s.scroll_top == 85


def test_new_content_does_not_move_the_viewport_after_manual_scroll():
    """本 task 的核心：用户在读旧内容时，新内容不许把他弹走。"""
    s = ScrollState()
    s.update(100, 10)
    s.scroll_by(-30)
    top = s.scroll_top
    s.update(160, 10)
    assert s.scroll_top == top
    assert not s.following_end


def test_scrolling_back_to_the_bottom_reenables_following():
    s = ScrollState()
    s.update(100, 10)
    s.scroll_by(-5)
    s.scroll_by(5)
    assert s.following_end
    s.update(120, 10)
    assert s.scroll_top == 110


def test_to_end_reenables_following_and_clears_unseen():
    s = ScrollState()
    s.update(100, 10)
    s.scroll_by(-20)
    s.update(140, 10)
    assert s.has_unseen
    s.to_end()
    assert s.following_end and s.scroll_top == 130
    assert not s.has_unseen


def test_to_start_goes_to_the_top():
    s = ScrollState()
    s.update(100, 10)
    s.to_start()
    assert s.scroll_top == 0
    assert not s.following_end


def test_scroll_by_clamps_at_both_ends_and_returns_unused_delta():
    s = ScrollState()
    s.update(100, 10)          # max_top = 90，此刻在底部
    assert s.scroll_by(5) == 5         # 已经到底，5 行一点没用上
    s.to_start()
    assert s.scroll_by(-3) == -3       # 已经到顶
    assert s.scroll_by(-0) == 0
    s.to_end()
    assert s.scroll_by(-95) == -5      # 只走得动 90 行，剩 5 行还回去


def test_page_up_and_down_keep_an_overlap():
    """翻页留几行重叠——整屏换掉的话读者会丢失上下文。"""
    s = ScrollState()
    s.update(100, 10)
    s.page_up()
    assert s.scroll_top == 90 - (10 - PAGE_OVERLAP)
    s.page_down()
    assert s.scroll_top == 90


def test_page_up_still_moves_when_the_viewport_is_tiny():
    s = ScrollState()
    s.update(100, 3)           # 视口比重叠量还小
    before = s.scroll_top
    s.page_up()
    assert s.scroll_top < before


def test_viewport_growth_keeps_following_at_the_bottom():
    s = ScrollState()
    s.update(100, 10)
    s.update(100, 20)
    assert s.scroll_top == 80


def test_viewport_change_preserves_position_when_not_following():
    """dock 变高变矮、窗口 resize 都会改视口高度——用户读到哪儿不该因此跳。"""
    s = ScrollState()
    s.update(100, 10)
    s.scroll_by(-40)           # scroll_top = 50
    s.update(100, 20)
    assert s.scroll_top == 50
    assert not s.following_end


def test_content_shorter_than_viewport_stays_pinned_at_zero():
    s = ScrollState()
    s.update(3, 10)
    assert s.scroll_top == 0
    assert s.following_end
    assert not s.scrolled_up
    s.scroll_by(-5)
    assert s.scroll_top == 0
    assert not s.scrolled_up   # 没得滚 = 不该显示「已上滚」


def test_unseen_only_while_scrolled_away():
    s = ScrollState()
    s.update(100, 10)
    s.update(120, 10)
    assert not s.has_unseen    # 跟随态：新内容就在眼前
    s.scroll_by(-20)
    assert not s.has_unseen    # 刚滚上去，还没有新内容
    s.update(140, 10)
    assert s.has_unseen
