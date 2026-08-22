"""选区：纯状态机 + 取文本。不碰终端、不碰渲染。

**锚在 transcript 的逻辑行号，不是屏幕行号。** 这一句就是 pai 相对 CC 的全部简化：

CC 的屏幕缓冲只有当前视口，所以拖到边缘自动滚时，「滚出视口的那些行」必须另存
（`selection.ts` 的 `scrolledOffAbove` / `scrolledOffBelow` + 两条平行的软折行位图
+ `virtualAnchorRow` 的钳位还原）——那是它最难懂的一块。
pai 持有整份文档，滚动只改「显示哪一段」，选区跟着内容走，**那一整块不需要**。

代价也说清楚：选区绑在**行号**上，而行号会因为压缩（改写历史）、`/clear`、
以及 **resize** 而失效——逻辑行本身是按宽度折行的产物，宽度一变同一个
(row,col) 就指向别的文字，「锚在逻辑行故免疫 resize」的旧说法不成立（R4#20），
`app.handle_resize` 因此在 resize 时清掉选区。
取文本时越界一律钳位返回空，不抛。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pai.modes.statusline import _ESCAPES, display_width


@dataclass(frozen=True)
class Point:
    """transcript 的逻辑行号 + **显示列**（不是字符下标：一个中文占两列）。"""

    row: int
    col: int


class Selection:
    def __init__(self) -> None:
        self.anchor: Optional[Point] = None
        self.focus: Optional[Point] = None
        self.dragging = False

    # --- 状态跃迁 -------------------------------------------------------

    def start(self, row: int, col: int) -> None:
        """按下。**只记锚点，不产生选区**——裸点击不该选中任何东西
        （否则单击会清掉剪贴板，还与「点击展开」抢同一个动作）。"""
        self.anchor = Point(row, col)
        self.focus = None
        self.dragging = True

    def update(self, row: int, col: int) -> None:
        """拖动：只更新焦点。

        **「裸点击不产生选区」这条防线只在 `bounds()` 里**（锚点=焦点即无选区）。
        CC 在这里另有一道 guard（同格的第一次移动不算数），因为它的 `hasSelection`
        判的是「focus 非空」；pai 判的是「两点不等」，那道 guard 是冗余的——
        **注入反证证明了它删掉也不会有任何测试变红**，于是删掉：
        两道互相遮蔽的防线，等于没人知道哪道在生效。
        """
        if not self.dragging or self.anchor is None:
            return
        self.focus = Point(row, col)

    def finish(self) -> None:
        """松开。**保留**选区（高亮还在、还能复制），只结束拖动态。"""
        self.dragging = False

    def clear(self) -> None:
        self.anchor = self.focus = None
        self.dragging = False

    # --- 查询 -----------------------------------------------------------

    @property
    def has_selection(self) -> bool:
        return self.bounds() is not None

    def bounds(self) -> Optional[Tuple[Point, Point]]:
        """归一化成 (起点, 终点)，两端都**含**。"""
        if self.anchor is None or self.focus is None:
            return None
        a, f = self.anchor, self.focus
        if (a.row, a.col) == (f.row, f.col):
            return None
        return (a, f) if (a.row, a.col) < (f.row, f.col) else (f, a)

    def text(self, transcript, width: int) -> str:
        """选中的**纯文本**：剥净转义序列、逐行去尾部空白、`\\n` 连接。

        剥转义序列不是洁癖：复制出去的东西要能直接粘进别处，
        带着 `\\x1b[36m` 粘到编辑器里就是一坨乱码。
        """
        span = self.bounds()
        if span is None:
            return ""
        start, end = span
        lines = transcript.slice(width, start.row, end.row - start.row + 1)
        if not lines:
            return ""
        out: List[str] = []
        for offset, line in enumerate(lines):
            plain = _ESCAPES.sub("", line)
            lo = start.col if offset == 0 else 0
            hi = end.col + 1 if offset == end.row - start.row else None
            out.append(_slice_columns(plain, lo, hi).rstrip())
        return "\n".join(out)


def _slice_columns(text: str, start: int, end: Optional[int]) -> str:
    """按**显示列**切片。落在宽字符中间的边界向外扩到整字——
    切出半个字的话，复制出来的是一个残缺码位，粘到哪儿都是错的。"""
    out = []
    col = 0
    for ch in text:
        w = display_width(ch)
        if col + w > start and (end is None or col < end):
            out.append(ch)
        col += w
        if end is not None and col >= end:
            break
    return "".join(out)
