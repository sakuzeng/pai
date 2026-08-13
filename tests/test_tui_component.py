"""T1：Component 契约与 Container。

契约照 pi 的四成员取两个必需的（render + invalidate），
理由见 K tui/pi-tui-main-screen.md 第二节。
"""

from pai.tui.component import CURSOR_MARKER, Container, Text
from pai.modes.statusline import display_width


def test_text_renders_one_line():
    assert Text("hello").render(20) == ["hello"]


def test_container_concatenates_children_in_order():
    c = Container([Text("a"), Text("b")])
    assert c.render(20) == ["a", "b"]


def test_container_passes_width_down():
    seen = []

    class Probe:
        def render(self, width):
            seen.append(width)
            return []

        def invalidate(self):
            pass

    Container([Probe(), Probe()]).render(37)
    assert seen == [37, 37]


def test_invalidate_reaches_every_descendant():
    calls = []

    class Probe:
        def render(self, width):
            return []

        def invalidate(self):
            calls.append(self)

    leaf = Probe()
    Container([Container([leaf])]).invalidate()
    assert calls == [leaf]


def test_container_mutation_api():
    a, b = Text("a"), Text("b")
    c = Container()
    c.add_child(a)
    c.add_child(b)
    c.remove_child(a)
    assert c.render(10) == ["b"]
    c.clear()
    assert c.render(10) == []


def test_cursor_marker_is_zero_width():
    """零宽是硬要求：它要能塞进任意一行而不改变该行的可见列数。

    APC 序列终端会忽略，但 pai 自己算宽度时也必须算成 0，
    否则输入框的光标列会往右漂一格。
    """
    assert display_width(CURSOR_MARKER) == 0
    assert display_width("ab" + CURSOR_MARKER + "cd") == 4
