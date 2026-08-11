"""SGR 1006 鼠标事件解析（feature 16 T1）。

编码与量级都是**实测**来的，不是照文档抄的
（[features/16 evidence](../docs/dev/features/16-20260811-mouse-and-selection/evidence/20260811-鼠标与剪贴板/说明.md)）：
按下 `\\x1b[<0;列;行M`、拖动 `\\x1b[<32;…M`（每跨一格一条）、
滚轮 `\\x1b[<64;…M`/`<65`（**一次手势上百条**）。
"""

from pai.tui.editor import LineEditor
from pai.tui.keys import Key, KeyDecoder
from pai.tui.mouse import MouseEvent


def _events(*chunks: bytes):
    """按 chunk 逐次喂——真终端就是这么把一条序列拆开送达的。"""
    decoder = KeyDecoder()
    out = []
    for chunk in chunks:
        out.extend(decoder.feed(chunk))
    return out


def _mouse(*chunks: bytes):
    return [k.mouse for k in _events(*chunks) if k.name == "mouse"]


def test_press_is_zero_based():
    """SGR 报的是 1-based 列行，内部一律 0-based——混用是坐标错位的经典来源。"""
    assert _mouse(b"\x1b[<0;12;3M") == [
        MouseEvent(kind="press", button=0, col=11, row=2)]


def test_release_ends_with_lowercase_m():
    assert _mouse(b"\x1b[<0;12;3m") == [
        MouseEvent(kind="release", button=0, col=11, row=2)]


def test_drag_sets_bit_32():
    assert _mouse(b"\x1b[<32;5;9M") == [
        MouseEvent(kind="drag", button=0, col=4, row=8)]


def test_wheel_up_and_down():
    up, down = _mouse(b"\x1b[<64;1;1M\x1b[<65;1;1M")
    assert (up.kind, up.delta) == ("wheel", -1)
    assert (down.kind, down.delta) == ("wheel", 1)


def test_wheel_carries_the_pointer_position():
    """实测：触控板滚动**不移动指针**，所以坐标恒定——它表示「指针此刻在哪」，
    用途是命中测试（决定滚哪个区域）。"""
    (event,) = _mouse(b"\x1b[<64;104;22M")
    assert (event.col, event.row) == (103, 21)


def test_a_sequence_split_across_reads_is_reassembled():
    """实测一次 `os.read(4096)` 里有几百条事件——切在序列中间是**必然**不是偶然。"""
    assert _mouse(b"\x1b[<0;12", b";3M") == [
        MouseEvent(kind="press", button=0, col=11, row=2)]


def test_split_right_after_the_escape():
    assert _mouse(b"\x1b", b"[<32;5;9M") == [
        MouseEvent(kind="drag", button=0, col=4, row=8)]


def test_a_burst_of_wheel_events_all_come_through():
    burst = b"\x1b[<64;104;22M" * 142          # 实测：6 秒一次手势 142 条
    assert len(_mouse(burst)) == 142


def test_right_and_middle_buttons_are_kept():
    press = _mouse(b"\x1b[<2;1;1M")[0]
    assert press.button == 2


def test_unknown_mouse_encodings_are_discarded_not_guessed():
    """1015/1016 这类扩展编码 pai 不认——**丢弃，不猜**。"""
    keys = _events(b"\x1b[<0;12;3;99M")        # 多一个参数：不是 pai 认得的形状
    assert [k.name for k in keys if k.name == "mouse"] == []


def test_mouse_bytes_never_become_text():
    """漏成文本的话，滚一下滚轮输入框里就是一堆 `[<64;104;22M`。"""
    keys = _events(b"\x1b[<64;104;22M")
    assert all(k.name != "char" for k in keys)
    assert all("64" not in k.text for k in keys)


def test_mouse_keys_never_reach_the_editor():
    """**这条钉的是一个「恰好成立」的事实**：`LineEditor.handle` 是一串 elif、
    没有 catch-all 插入，所以鼠标事件落到最后什么也不做。
    将来谁顺手加个 `else: self._insert(key.text)`，鼠标字节就会哗哗打进输入框，
    而在本条测试出现之前，**没有任何东西会红**。
    """
    editor = LineEditor()
    editor.handle(Key("char", "你好"))
    before = (editor.text, editor.cursor)
    for chunk in (b"\x1b[<0;12;3M", b"\x1b[<32;13;3M", b"\x1b[<0;13;3m",
                  b"\x1b[<64;1;1M"):
        for key in _events(chunk):
            editor.handle(key)
    assert (editor.text, editor.cursor) == before
