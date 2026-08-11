"""滚动状态机：纯状态、零 IO、离线可测。

语义照 pi 的 `ScrollView`（K source-walks/pi-alt-screen.md 第三节）：
**跟随末尾是默认**，手动往上滚就关掉跟随，滚回底部再打开。

为什么这件小事值一个模块：alt 屏下「新内容到达」与「用户正在往回读」会同时发生，
而这两件事对视口的要求正好相反。把判断散在渲染代码里，症状是
「用户每滚一次就被弹回底部」——而那时已经很难看出是谁把 scroll_top 改回去的。
"""

from __future__ import annotations

# 翻页时留几行重叠。抄自 pi `tui-alt-screen.ts` 的 PAGE_SCROLL_OVERLAP，
# 前提是「读者需要一点上下文来接上上一屏」——与终端无关，换个项目仍成立。
PAGE_OVERLAP = 4


class ScrollState:
    def __init__(self) -> None:
        self.scroll_top = 0
        self.following_end = True
        self.viewport_height = 0
        self.content_height = 0
        self._unseen = False

    # --- 每帧调 -------------------------------------------------------

    def update(self, content_height: int, viewport_height: int) -> None:
        """内容或视口变了。跟随态贴底；非跟随态**保住 scroll_top**。"""
        grew = content_height > self.content_height
        self.content_height = max(0, content_height)
        self.viewport_height = max(0, viewport_height)
        if self.following_end:
            self.scroll_top = self.max_top
        else:
            self.scroll_top = min(max(0, self.scroll_top), self.max_top)
            if grew:
                self._unseen = True
            if self.max_top == 0:
                # 内容缩短到装得下了：没得滚，等于回到了底部
                self.following_end = True
                self._unseen = False

    @property
    def max_top(self) -> int:
        return max(0, self.content_height - self.viewport_height)

    @property
    def scrolled_up(self) -> bool:
        """真的停在历史里（而不是「内容太少没得滚」）。状态行按这个显示。"""
        return self.max_top > 0 and self.scroll_top < self.max_top

    @property
    def has_unseen(self) -> bool:
        return self.scrolled_up and self._unseen

    # --- 操作 ---------------------------------------------------------

    def scroll_by(self, delta: int) -> int:
        """正数往下、负数往上。返回**没用掉的 delta**。

        返回值现在没人用（只有一个滚动区），但语义先立住：
        嵌套滚动区的链式冒泡就靠它，而事后改签名要动所有调用方。
        """
        if delta == 0:
            return 0
        start = self.max_top if self.following_end else self.scroll_top
        nxt = max(0, min(self.max_top, start + delta))
        moved = nxt - start
        self.scroll_top = nxt
        self._set_following(nxt >= self.max_top)
        return delta - moved

    def to_start(self) -> None:
        self.scroll_top = 0
        self._set_following(self.max_top == 0)

    def to_end(self) -> None:
        self.scroll_top = self.max_top
        self._set_following(True)

    def page_up(self) -> None:
        self.scroll_by(-self._page())

    def page_down(self) -> None:
        self.scroll_by(self._page())

    def _page(self) -> int:
        # 视口比重叠量还小时也必须动得了，否则 PgUp 看起来像坏了
        return max(1, self.viewport_height - PAGE_OVERLAP)

    def _set_following(self, following: bool) -> None:
        self.following_end = following
        if following:
            self._unseen = False
