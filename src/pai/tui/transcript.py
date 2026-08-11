"""会话文档：alt 屏下 pai 自己持有的那份「上面显示什么」。

**为什么存条目而不是存行**（feature 13 T2）：
main-screen 下 `commit(lines)` 收的是按当时宽度排好的行，打出去就归终端所有，
之后窗口怎么变都是终端的事。alt 屏下 pai 每帧都要重画整屏——窗口一变宽变窄，
存着的那些行就全是错的。所以这里存的是**能按宽度重新渲染的条目**。

**缓存归条目自己所有**，且 key 必须含宽度（照 pi `tui-plan.md:376`：
框架层再加一层缓存会因为「失效语义归组件所有」而陈旧）。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from pai.tui import theme


class TranscriptEntry:
    """一条会话内容。契约与 `Component.render(width) -> list[str]` 同构。

    单槽缓存（只记最近一个 key）足够：宽度与展开态都是低频变化，
    而多槽缓存要处理逐出策略，那是没有数字支撑的复杂度。

    **缓存 key 是 `(宽度, 展开态)` 而不只是宽度**（feature 16）：
    漏了展开态的症状是**点了没反应**——渲染函数换了、缓存还发着旧的行。
    这与 feature 13「缓存 key 必须含宽度」是同一个坑的第二次。
    """

    __slots__ = ("_render", "_key", "_lines", "expandable", "expanded")

    def __init__(self, render: Callable[..., List[str]], *,
                 expandable: bool = False) -> None:
        self._render = render
        self._key: Optional[tuple] = None
        self._lines: List[str] = []
        self.expandable = expandable
        self.expanded = False

    def toggle(self) -> None:
        """展开↔折叠。不可展开的条目上调用是无操作（点空白处不该炸）。"""
        if self.expandable:
            self.expanded = not self.expanded

    def render(self, width: int) -> List[str]:
        key = (width, self.expanded)
        if self._key != key:
            self._lines = list(self._render(width, self.expanded)
                               if self.expandable else self._render(width))
            self._key = key
        # 交出去的是副本：调用方就地改（比如往视口切片里追加）不该弄脏缓存
        return list(self._lines)

    def height(self, width: int) -> int:
        self.render(width)
        return len(self._lines)


def dynamic_entry(render: Callable[[int], List[str]]) -> TranscriptEntry:
    """渲染结果本身依赖宽度的条目（logo、色带、按宽度截断的工具行）。"""
    return TranscriptEntry(render)


def expandable_entry(render: Callable[[int, bool], List[str]]) -> TranscriptEntry:
    """可展开的条目（工具结果）。渲染函数收 `(宽度, 是否展开)`。

    「能点」的门槛从来不在命中测试，在**条目得记得自己是什么状态**——
    而这一步的错法（缓存 key 漏了状态）症状是「点了没反应」，很难反推。
    """
    return TranscriptEntry(render, expandable=True)


def text_entry(lines: List[str]) -> TranscriptEntry:
    """一段纯文本，**按显示列宽折行**。

    alt 屏下这一步不能省：终端的自动折行被关掉了（`?7l`），
    不自己折就是在右边界被截断——用户看不到的部分是**丢了**，不是「在下一行」。
    """
    frozen = list(lines)

    def render(width: int) -> List[str]:
        if width <= 0:
            return list(frozen)
        out: List[str] = []
        for line in frozen:
            out.extend(theme.wrap(line, width))
        return out

    return TranscriptEntry(render)


class Transcript:
    """append-only 的条目表 + 按宽度取视口。"""

    def __init__(self) -> None:
        self.entries: List[TranscriptEntry] = []

    def append(self, entry: TranscriptEntry) -> None:
        self.entries.append(entry)

    def clear(self) -> None:
        self.entries.clear()

    def total_lines(self, width: int) -> int:
        return sum(entry.height(width) for entry in self.entries)

    def owner_at(self, width: int, row: int) -> Optional[TranscriptEntry]:
        """第 `row` 个**逻辑行**属于哪个条目。**这就是 pai 的命中测试全部**。

        CC 需要一棵矩形树（`hit-test.ts`）是因为它的布局是二维的（flexbox 嵌套）；
        pai 的 transcript 是一串行，一维的映射就够。
        """
        if row < 0:
            return None
        seen = 0
        for entry in self.entries:
            n = entry.height(width)
            if seen <= row < seen + n:
                return entry
            seen += n
        return None

    def slice(self, width: int, top: int, height: int) -> List[str]:
        """取 [top, top+height) 这一段行。越界钳位而不是抛——
        视口位置是被 resize、dock 变高、内容变短同时推着走的，
        任何一处慢半拍都会越界，为此炸掉整个界面不划算。"""
        if height <= 0:
            return []
        top = max(0, top)
        out: List[str] = []
        seen = 0
        for entry in self.entries:
            lines = entry.render(width)
            end = seen + len(lines)
            if end > top:
                start = max(0, top - seen)
                out.extend(lines[start:start + (height - len(out))])
                if len(out) >= height:
                    break
            seen = end
        return out
