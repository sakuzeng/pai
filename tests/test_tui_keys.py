"""T2：原始字节 → 按键事件。

**必须是增量的**：真终端会把一个多字节字符、一条转义序列拆成两次 read 送达
（feature 12 反向对照里 pty 就是这么送的）。所以解码器带状态，喂多少认多少，
认不全的留在缓冲里等下一口。
"""

from pai.tui.keys import KeyDecoder


def keys(*chunks, flush=False):
    d = KeyDecoder()
    out = []
    for chunk in chunks:
        out.extend(d.feed(chunk))
    if flush:
        out.extend(d.flush())
    return out


def names(*chunks, **kw):
    return [k.name for k in keys(*chunks, **kw)]


def test_printable_ascii_becomes_char_keys():
    assert [(k.name, k.text) for k in keys(b"ab")] == [
        ("char", "a"), ("char", "b")]


def test_multibyte_char_split_across_reads_is_reassembled():
    """真终端会这么送。按字节逐个 decode 会当场抛 UnicodeDecodeError。"""
    data = "中".encode("utf-8")
    assert [(k.name, k.text) for k in keys(data[:1], data[1:])] == [("char", "中")]


def test_enter_from_both_cr_and_lf():
    assert names(b"\r") == ["enter"]
    assert names(b"\n") == ["enter"]


def test_backspace_from_both_del_and_bs():
    assert names(b"\x7f") == ["backspace"]
    assert names(b"\x08") == ["backspace"]


def test_arrow_keys():
    assert names(b"\x1b[A\x1b[B\x1b[C\x1b[D") == ["up", "down", "right", "left"]


def test_home_and_end_in_both_common_encodings():
    assert names(b"\x1b[H\x1b[F") == ["home", "end"]
    assert names(b"\x1bOH\x1bOF") == ["home", "end"]
    assert names(b"\x1b[1~\x1b[4~") == ["home", "end"]


def test_delete_key():
    assert names(b"\x1b[3~") == ["delete"]


def test_shift_tab_is_csi_z():
    """权限模式轮转键（spec G5）。CC 在 Windows 无 VT mode 时才退回 meta+m，
    pai 目标平台是 macOS/Linux，只认这一个。"""
    assert names(b"\x1b[Z") == ["shift_tab"]


def test_control_keys():
    assert names(b"\x01\x05\x15\x0b\x17\x03\x04") == [
        "ctrl_a", "ctrl_e", "ctrl_u", "ctrl_k", "ctrl_w", "ctrl_c", "ctrl_d"]


def test_alt_word_navigation():
    assert names(b"\x1bb\x1bf") == ["word_left", "word_right"]


def test_escape_sequence_split_across_reads():
    assert names(b"\x1b", b"[", b"A") == ["up"]


def test_unknown_escape_is_dropped_not_typed():
    """按个 F5 不能往输入框里灌 `\\x1b[15~`。丢弃但留痕，供调试开关打出来。"""
    result = keys(b"\x1b[15~a")
    assert [k.name for k in result] == ["unknown", "char"]
    assert result[0].text == "\x1b[15~"


def test_lone_escape_only_becomes_esc_on_flush():
    """单独一个 ESC 与「转义序列的开头」在字节上分不开，只能靠「后面没有了」来判。"""
    assert names(b"\x1b") == []
    assert names(b"\x1b", flush=True) == ["esc"]


def test_bracketed_paste_is_one_key_with_the_whole_payload():
    result = keys("\x1b[200~粘贴的内容\x1b[201~".encode("utf-8"))
    assert [(k.name, k.text) for k in result] == [("paste", "粘贴的内容")]


def test_newlines_inside_paste_do_not_submit():
    """粘一段多行文本不该被当成敲了好几次回车。"""
    result = keys(b"\x1b[200~line1\r\nline2\x1b[201~")
    assert [k.name for k in result] == ["paste"]
    assert result[0].text == "line1\nline2"


def test_paste_split_across_reads():
    result = keys(b"\x1b[200~abc", b"def\x1b[201~")
    assert [(k.name, k.text) for k in result] == [("paste", "abcdef")]


def test_incomplete_paste_stays_buffered():
    assert names(b"\x1b[200~abc") == []
