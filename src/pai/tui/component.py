"""组件契约：`render(width) -> list[str]` 纯函数 + `invalidate()`。

契约取 pi 四成员里的两个必需项（K tui/pi-tui-main-screen.md 第二节）。
另两个（`handle_input` / `wants_key_release`）不在这里——pai 的输入不走「焦点组件收字节」，
走一个显式的仲裁函数（T3），理由见 features/12 的 spec G3。

**组件不持终端句柄、不写 IO**：这是全模块可测性的前提，别为了图方便破例。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

# 光标位置标记：APC（Application Program Command）序列，终端会忽略它、不占列宽。
# 焦点组件在光标该在的位置吐一个，渲染器找到它、算出可见列、剥掉，再把**硬件光标**
# 摆过去——这是中文 IME 候选框位置正确的唯一解法（roadmap 阶段 2 原则 3）。
# 形状照 APC 的通用写法（ESC _ ... BEL），内容用 pai 自己的私有标识。
CURSOR_MARKER = "\x1b_pai:c\x07"


class Component:
    """组件基类。子类至少要实现 `render`。

    用基类而不是 Protocol：Protocol 在 3.9 运行期不做结构检查，
    而这里想要的恰恰是「忘了实现 render 就当场报错」。
    """

    def render(self, width: int) -> List[str]:
        raise NotImplementedError

    def invalidate(self) -> None:
        """作废缓存的渲染状态。默认无缓存即无操作。"""


class Text(Component):
    """一行纯文本。宽度由调用方负责——超宽的守卫在 T8 统一做。"""

    def __init__(self, text: str = "") -> None:
        self.text = text

    def render(self, width: int) -> List[str]:
        return [self.text]


class Container(Component):
    """按顺序把子组件的行拼起来。视觉上透明——它自己不产生任何一行。"""

    def __init__(self, children: Optional[Sequence[Component]] = None) -> None:
        self.children: List[Component] = list(children) if children else []

    def add_child(self, component: Component) -> None:
        self.children.append(component)

    def remove_child(self, component: Component) -> None:
        if component in self.children:
            self.children.remove(component)

    def clear(self) -> None:
        self.children = []

    def invalidate(self) -> None:
        for child in self.children:
            child.invalidate()

    def render(self, width: int) -> List[str]:
        lines: List[str] = []
        for child in self.children:
            lines.extend(child.render(width))
        return lines


def extract_cursor(lines: List[str]):
    """找出 CURSOR_MARKER 的（行, 可见列），并把标记从行里剥掉。

    列用 `display_width` 算标记之前的可见文本——不是字符数。
    一个中文两列，按字符数算会让光标停在半个字上。

    两个渲染器共用同一份（feature 13）：dock 渲染器按**相对**光标移动摆它，
    alt 屏渲染器按**绝对**坐标摆它，但「标记在第几行第几列」的算法必须是同一个，
    否则中文 IME 候选框会在两种模式下飘到不同的地方。
    """
    from pai.modes.statusline import display_width

    for row, line in enumerate(lines):
        index = line.find(CURSOR_MARKER)
        if index == -1:
            continue
        col = display_width(line[:index])
        stripped = list(lines)
        stripped[row] = line[:index] + line[index + len(CURSOR_MARKER):]
        return stripped, (row, col)
    return lines, None
