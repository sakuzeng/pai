"""选区状态机（feature 16 T4）。

**pai 相对 CC 的简化点全在这一句上：选区锚在 transcript 的逻辑行号，不是屏幕行号。**

CC 的屏幕缓冲只有当前视口，所以它必须把「滚出视口的行」另存
（`scrolledOffAbove/Below` + 两条平行的软折行位图 + 翻页钳位后的锚点还原）——
`selection.ts` 里最难懂的字段全是为这件事。pai 持有整份文档，那一整块**不需要**。
"""

from pai.tui.selection import Point, Selection
from pai.tui.transcript import Transcript, text_entry


def _doc(*lines):
    doc = Transcript()
    for line in lines:
        doc.append(text_entry([line]))
    return doc


def test_press_alone_does_not_select_anything():
    """裸点击不许产生选区：否则单击会清掉剪贴板，还与「点击展开」打架。"""
    sel = Selection()
    sel.start(3, 5)
    assert not sel.has_selection
    assert sel.bounds() is None


def test_the_first_move_at_the_anchor_cell_does_not_count():
    """终端在按住时会发出与锚点同格的移动（亚像素抖动 / 一次 motion-release 对）。
    照 CC 的 `updateSelection`：这一条不算数，否则裸点击变成 1 格选区。"""
    sel = Selection()
    sel.start(3, 5)
    sel.update(3, 5)
    assert not sel.has_selection


def test_a_real_drag_creates_a_selection():
    sel = Selection()
    sel.start(3, 5)
    sel.update(3, 9)
    assert sel.has_selection
    assert sel.bounds() == (Point(3, 5), Point(3, 9))


def test_dragging_backwards_normalises():
    sel = Selection()
    sel.start(5, 8)
    sel.update(2, 1)
    assert sel.bounds() == (Point(2, 1), Point(5, 8))


def test_release_keeps_the_selection():
    sel = Selection()
    sel.start(1, 0)
    sel.update(1, 4)
    sel.finish()
    assert sel.has_selection
    assert not sel.dragging


def test_clear_drops_it():
    sel = Selection()
    sel.start(1, 0)
    sel.update(1, 4)
    sel.clear()
    assert not sel.has_selection


def test_a_new_press_starts_over():
    sel = Selection()
    sel.start(1, 0)
    sel.update(1, 4)
    sel.finish()
    sel.start(7, 2)
    assert not sel.has_selection


# --- 取文本 ---------------------------------------------------------------


def test_text_of_a_single_line_range():
    doc = _doc("abcdefghij")
    sel = Selection()
    sel.start(0, 2)
    sel.update(0, 5)
    assert sel.text(doc, 40) == "cdef"          # 端点**含**光标那一格（照 CC）


def test_text_across_lines_joins_with_newlines():
    doc = _doc("first line", "second line", "third line")
    sel = Selection()
    sel.start(0, 6)
    sel.update(2, 4)
    assert sel.text(doc, 40) == "line\nsecond line\nthird"


def test_text_strips_escape_sequences():
    """复制出去的必须是**人要的文本**，不是带颜色码的一坨。"""
    doc = _doc("\x1b[36m带颜色的字\x1b[0m")
    sel = Selection()
    sel.start(0, 0)
    sel.update(0, 9)
    assert "\x1b" not in sel.text(doc, 40)
    assert sel.text(doc, 40) == "带颜色的字"


def test_text_slices_by_display_column_not_character_index():
    """一个中文占两列。按字符数切会切出半个字，也会让列号从此全错。"""
    doc = _doc("中文abc")
    sel = Selection()
    # 「中文abc」的列：中=0-1、文=2-3、a=4、b=5、c=6
    sel.start(0, 0)
    sel.update(0, 4)                            # 列 0..4（闭区间）= 「中文a」
    # 若按**字符下标**切，[0:5] 会得到「中文abc」——两者不同才有鉴别力
    assert sel.text(doc, 40) == "中文a"


def test_a_column_landing_inside_a_wide_char_keeps_the_whole_char():
    doc = _doc("中文abc")
    sel = Selection()
    sel.start(0, 1)                             # 落在「中」的右半格
    sel.update(0, 2)
    assert sel.text(doc, 40) == "中文"


def test_trailing_whitespace_is_stripped_per_line():
    doc = _doc("abc        ", "def")
    sel = Selection()
    sel.start(0, 0)
    sel.update(1, 2)
    assert sel.text(doc, 40) == "abc\ndef"


def test_empty_selection_is_an_empty_string_not_a_space():
    sel = Selection()
    assert sel.text(_doc("abc"), 40) == ""


def test_content_far_outside_the_viewport_is_still_selectable():
    """**这条是「锚在逻辑行」的全部意义。**

    视口只有 10 行，而选的是第 100-101 行——用屏幕行号锚定的话，
    这个选区根本无法表达（屏幕上压根没有第 100 行）。
    """
    doc = _doc(*[f"line{i}" for i in range(200)])
    sel = Selection()
    sel.start(100, 0)
    sel.update(101, 6)                          # "line101" 占列 0..6
    assert sel.text(doc, 40) == "line100\nline101"


def test_out_of_range_rows_clamp_instead_of_raising():
    """内容会被 `/clear` 清掉、也会因为压缩而变短——选区可能指向已经不存在的行。"""
    doc = _doc("only")
    sel = Selection()
    sel.start(50, 0)
    sel.update(60, 3)
    assert sel.text(doc, 40) == ""
