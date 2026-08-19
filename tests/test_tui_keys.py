"""T2：原始字节 → 按键事件。

**必须是增量的**：真终端会把一个多字节字符、一条转义序列拆成两次 read 送达
（feature 12 反向对照里 pty 就是这么送的）。所以解码器带状态，喂多少认多少，
认不全的留在缓冲里等下一口。
"""

from pai.tui.keys import KeyDecoder


def keys(*chunks, flush=False, now=None):
    """`flush=True` 默认模拟「键盘已经静默够久」。

    feature 19 之后 `flush()` 多了一条时间判据（悬着的 ESC 要静默 ≥50ms 才
    判成 esc，否则那只是转义序列被拆包的间隙）。这里默认把时钟往前拨，
    于是既有测试断言的仍是它们本来的语义——「flush 时才裁决」，
    而不是被迫去关心毫秒。要测时间本身的，自己传 `now`。
    """
    clock = now if now is not None else _settled_clock()
    d = KeyDecoder(now=clock)
    out = []
    for chunk in chunks:
        out.extend(d.feed(chunk))
    if flush:
        clock.settle()
        out.extend(d.flush())
    return out


class _settled_clock:
    """默认时钟：`settle()` 一调就跳过静默阈值。"""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def settle(self) -> None:
        self.t += 1.0


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


# ---- feature 19 T1/T3：flush 认时间 + 同批到达的 ESC（2026-08-19）----


class _Clock:
    """假时钟：拆包间隙是毫秒级的，真 sleep 既慢又不稳。"""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_a_split_escape_sequence_is_not_settled_as_esc():
    """T1 的核心。

    TUI 干活期间每个事件都顺手 `driver.poll(timeout=0)`，于是转义序列被拆成
    两包到达时，第一包 `\\x1b` 进缓冲后下一次 poll 见「无新数据」就 flush，
    判成 Esc；随后到达的 `[`、`A` 被当普通字符插进输入框——用户按 ↑
    却在输入框里得到 `[A`，而那个假 Esc 若恰逢对话框弹出还会把框取消。
    """
    clock = _Clock()
    d = KeyDecoder(now=clock)

    assert d.feed(b"\x1b") == []
    assert d.flush() == [], "字节刚到就裁决 = 把拆包间隙当成了「用户按了 Esc」"

    keys = d.feed(b"[A")
    assert [k.name for k in keys] == ["up"]


def test_a_real_esc_still_settles_once_the_keyboard_goes_quiet():
    """治过头就成了另一个 bug：真按 Esc 必须还认得出来。

    判据的物理依据：真人按 Esc 与终端发转义序列，时间差是一个数量级
    （人 >100ms，序列 <1ms）。
    """
    clock = _Clock()
    d = KeyDecoder(now=clock)

    d.feed(b"\x1b")
    clock.advance(0.5)

    assert [k.name for k in d.flush()] == ["esc"]


def test_two_quick_escapes_produce_two_esc_keys():
    """T3：`\\x1b` 与后续字节同批到达时，此前被并吞成一个 `unknown`——
    连按两次 Esc 一个 esc 都不产生，于是对话框的 Esc 取消在快速操作下不可靠。"""
    clock = _Clock()
    d = KeyDecoder(now=clock)

    keys = d.feed(b"\x1b\x1b")
    clock.advance(0.5)
    keys += d.flush()

    assert [k.name for k in keys] == ["esc", "esc"]


def test_arrow_keys_arriving_in_one_packet_are_unaffected():
    """T3 的反向守卫：整包到达的方向键不许被这条新判据打散。"""
    clock = _Clock()
    d = KeyDecoder(now=clock)

    assert [k.name for k in d.feed(b"\x1b[A\x1b[B")] == ["up", "down"]


# ---- feature 19 T2：pasting 态自愈（2026-08-19）----


def test_a_lost_paste_end_does_not_kill_the_keyboard():
    """T2 的核心。

    `PASTE_END` 丢失（终端异常、断连、粘贴流被截）后，此前所有字节都进
    `_paste` 缓冲、`flush()` 也不复位——raw mode 下 ISIG 已关，Ctrl+C 只是
    普通字节，于是**连退出都做不到，只能 kill 进程**。

    自愈的用户视角：粘贴的内容照常进来了，只是晚了一点。
    """
    clock = _Clock()
    d = KeyDecoder(now=clock)

    d.feed(b"\x1b[200~")
    d.feed("粘了一半".encode("utf-8"))
    assert d.feed(b"x") == [], "还在粘贴态，普通字节该被吸收"

    clock.advance(2.0)                     # 键盘静默够久，201~ 显然不会来了
    recovered = d.flush()
    assert [k.name for k in recovered] == ["paste"]
    assert recovered[0].text == "粘了一半x"

    # 复位之后键盘要活过来
    assert [k.name for k in d.feed(b"a")] == ["char"]


def test_a_slow_paste_is_not_cut_in_half():
    """治过头就成了另一个 bug：分片慢的大段粘贴不许被误判成结束。

    阈值取 1s（比 ESC 那条大一个量级）：粘贴分片间隔在网络终端上可达数百毫秒，
    而真实的「201~ 永远不来」是分钟级的等待。
    """
    clock = _Clock()
    d = KeyDecoder(now=clock)

    d.feed(b"\x1b[200~")
    d.feed(b"first")
    clock.advance(0.3)                     # 分片之间的正常间隔
    assert d.flush() == [], "0.3s 还在正常分片范围内，不该切"

    d.feed(b"second")
    keys_out = d.feed(b"\x1b[201~")
    assert [(k.name, k.text) for k in keys_out] == [("paste", "firstsecond")]


def test_recovery_does_not_fire_for_an_empty_paste_buffer():
    """粘贴刚开始、一个字节都没到就静默，不该吐出一个空 paste 事件。"""
    clock = _Clock()
    d = KeyDecoder(now=clock)

    d.feed(b"\x1b[200~")
    clock.advance(2.0)

    assert d.flush() == []
