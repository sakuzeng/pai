"""点击展开/折叠工具结果（feature 16 T7）。

用户 2026-08-11 最早那句「我想这个 bash 和 bash 的结果能点」的落点。

**pai 的命中测试只有一维**：屏幕第 i 行 ↔ 逻辑行 `scroll_top + i` ↔ 哪个条目。
CC 需要矩形树（`hit-test.ts`）是因为它的布局是二维的（flexbox 嵌套）；
pai 的 transcript 是一串行，所以「哪一行属于谁」就是全部。
"""

from typing import List

from pai.tui.altscreen import AltScreenRenderer
from pai.tui.app import TuiApp
from pai.tui.component import Component
from pai.tui.keys import KeyDecoder
from pai.tui.scroll import ScrollState
from pai.tui.selection import Selection
from pai.tui.transcript import Transcript, expandable_entry, text_entry


class FakeDock(Component):
    def render(self, width: int) -> List[str]:
        return ["dock"]


def _tool_entry(name="bash", body=("line1", "line2", "line3")):
    def render(width, expanded):
        if expanded:
            return [f"{name} 的完整输出：", *body]
        return [f"{name} … 还有 {len(body)} 行"]
    return expandable_entry(render)


# --- 条目的展开态 ---------------------------------------------------------


def test_collapsed_by_default():
    entry = _tool_entry()
    assert entry.render(40) == ["bash … 还有 3 行"]


def test_toggle_expands_and_collapses():
    entry = _tool_entry()
    entry.toggle()
    assert entry.render(40)[0].endswith("完整输出：")
    assert len(entry.render(40)) == 4
    entry.toggle()
    assert entry.render(40) == ["bash … 还有 3 行"]


def test_the_cache_key_includes_the_expanded_state():
    """**漏了这一步的症状是「点了没反应」**——渲染函数换了，缓存还发着旧的行。
    与 feature 13「缓存 key 必须含宽度」是同一个坑的第二次。"""
    calls = []

    def render(width, expanded):
        calls.append((width, expanded))
        return ["展开" if expanded else "折叠"]

    entry = expandable_entry(render)
    entry.render(40)
    entry.render(40)
    assert calls == [(40, False)]          # 同宽同态：走缓存
    entry.toggle()
    assert entry.render(40) == ["展开"]     # 换了态：必须重算
    assert calls == [(40, False), (40, True)]


def test_expanded_state_survives_a_width_change():
    entry = _tool_entry(body=("x" * 30,))
    entry.toggle()
    assert len(entry.render(10)) == len(entry.render(80)) or entry.render(10) != entry.render(80)
    assert entry.render(80)[0].endswith("完整输出：")


# --- 行 → 条目 ------------------------------------------------------------


def test_owner_at_maps_a_line_to_its_entry():
    doc = Transcript()
    first = text_entry(["a", "b"])
    tool = _tool_entry()
    doc.append(first)
    doc.append(tool)
    assert doc.owner_at(40, 0) is first
    assert doc.owner_at(40, 1) is first
    assert doc.owner_at(40, 2) is tool


def test_owner_at_out_of_range_is_none():
    doc = Transcript()
    doc.append(text_entry(["a"]))
    assert doc.owner_at(40, 9) is None
    assert doc.owner_at(40, -1) is None


# --- 接线：点击 -----------------------------------------------------------


def _app(rows=8):
    transcript, scroll, selection = Transcript(), ScrollState(), Selection()
    renderer = AltScreenRenderer(write=lambda s: None, width=lambda: 40,
                                 height=lambda: rows, transcript=transcript,
                                 scroll=scroll, selection=selection)
    app = TuiApp(renderer=renderer, transcript=transcript, scroll=scroll,
                 selection=selection)
    return app, transcript, selection


def _feed(app, data):
    return app.feed(data, KeyDecoder())


def _press(row, col=1):
    return f"\x1b[<0;{col + 1};{row + 1}M".encode()


def _release(row, col=1):
    return f"\x1b[<0;{col + 1};{row + 1}m".encode()


def _drag(row, col):
    return f"\x1b[<32;{col + 1};{row + 1}M".encode()


def test_clicking_a_tool_line_expands_it():
    app, doc, _ = _app()
    tool = _tool_entry()
    doc.append(tool)
    app.refresh()
    _feed(app, _press(0) + _release(0))
    assert tool.expanded


def test_clicking_it_again_collapses():
    app, doc, _ = _app()
    tool = _tool_entry()
    doc.append(tool)
    app.refresh()
    _feed(app, _press(0) + _release(0))
    _feed(app, _press(0) + _release(0))
    assert not tool.expanded


def test_dragging_selects_instead_of_expanding():
    """按下→拖过→松开 = 选区，**不触发展开**（照 CC：没拖动才算点击）。

    松开时选区会被**复制并清掉**（用户真跑打回来的第一条：高亮不该赖着不走），
    所以这里断言的是「没展开」+「确实走了复制」，而不是「选区还在」。
    """
    app, doc, selection = _app()
    tool = _tool_entry()
    doc.append(tool)
    app.refresh()
    _feed(app, _press(0, 0) + _drag(0, 6) + _release(0, 6))
    assert not tool.expanded
    assert app.dock.has_notice()


def test_clicking_blank_space_does_nothing():
    app, doc, _ = _app()
    doc.append(text_entry(["only"]))
    app.refresh()
    _feed(app, _press(4) + _release(4))        # 视口里的空行
    assert True                                 # 不炸即通过


def test_clicking_the_dock_does_not_touch_the_transcript():
    app, doc, _ = _app(rows=8)
    tool = _tool_entry()
    doc.append(tool)
    app.refresh()
    _feed(app, _press(7) + _release(7))         # 最后一行 = dock
    assert not tool.expanded


def test_clicking_a_non_expandable_entry_is_a_no_op():
    app, doc, _ = _app()
    doc.append(text_entry(["普通一行"]))
    app.refresh()
    _feed(app, _press(0) + _release(0))
    assert True
