"""T4：对话框（权限 ask 与 AskUserQuestion 走同一套）。

**本 task 的存在理由是一条铁证**（08 遗留，2026-08-10 演示时真实发生）：
模型提问期间，用户敲的 `!echo 我是命令` 被静默当成了对问题的回答。
根因是「同一个输入流两个消费者抢」。这里的反例测试必须钉死：
**提问期间敲命令，就是执行命令。**
"""

from pai.tui.dialog import CANCELLED, Dialog
from pai.tui.keys import KeyDecoder
from pai.modes.statusline import display_width


def press(dialog, data):
    answers = []
    for key in KeyDecoder().feed(data):
        result = dialog.handle(key)
        if result is not None:
            answers.append(result)
    return answers


def q():
    return Dialog(question="用哪个方案？", options=["方案 A", "方案 B"])


def test_renders_question_and_options():
    text = "\n".join(q().render(40))
    assert "用哪个方案？" in text
    assert "方案 A" in text and "方案 B" in text


def test_arrow_keys_move_the_selection():
    d = q()
    assert d.selected == 0
    press(d, b"\x1b[B")
    assert d.selected == 1
    press(d, b"\x1b[B")
    assert d.selected == 1                    # 到底就停住，不绕回
    press(d, b"\x1b[A\x1b[A")
    assert d.selected == 0


def test_enter_answers_with_the_selected_option():
    d = q()
    press(d, b"\x1b[B")
    assert press(d, b"\r") == ["方案 B"]


def test_digit_keys_pick_directly():
    assert press(q(), b"2") == ["方案 B"]


def test_out_of_range_digit_is_ignored():
    assert press(q(), b"9") == []


def test_esc_cancels():
    assert press(q(), b"\x1b", ) == []        # 单个 ESC 要 flush 才成键
    d = q()
    decoder = KeyDecoder()
    decoder.feed(b"\x1b")
    assert [d.handle(k) for k in decoder.flush()] == [CANCELLED]


def test_free_text_is_allowed_so_the_human_is_not_locked_into_options():
    """真人想说别的就让他说——这条语义从 05 的 asker 继承下来，不许回退。"""
    d = q()
    assert press(d, "我要第三种".encode("utf-8")) == []
    assert press(d, b"\r") == ["我要第三种"]


def test_typing_then_backspacing_to_empty_returns_to_option_mode():
    d = q()
    press(d, b"x\x7f")
    assert press(d, b"\r") == ["方案 A"]


def test_bang_command_is_not_an_answer():
    """铁证反例一：`!echo 我是命令` 在提问期间必须是命令，不是答案。"""
    d = q()
    assert press(d, "!echo 我是命令".encode("utf-8")) == []
    assert d.handoff() == "!echo 我是命令"


def test_slash_command_is_not_an_answer():
    """铁证反例二：`/status` 同理。"""
    d = q()
    press(d, b"/status")
    assert d.handoff() == "/status"


def test_handoff_is_none_for_ordinary_text():
    d = q()
    press(d, "普通回答".encode("utf-8"))
    assert d.handoff() is None


def test_permission_dialog_cancel_means_deny():
    """权限框与提问框共用组件，但取消的含义不同，返回值要分得开。"""
    d = Dialog(question="允许 bash 跑 `rm -rf /`？", options=["允许", "拒绝"],
               kind="permission")
    decoder = KeyDecoder()
    decoder.feed(b"\x1b")
    assert [d.handle(k) for k in decoder.flush()] == [CANCELLED]
    assert d.kind == "permission"


def test_render_never_exceeds_width():
    d = Dialog(question="很长很长的问题" * 6, options=["选项" * 20, "短"])
    for line in d.render(24):
        assert display_width(line) <= 24


# --- 权限框的真实形状（gate 传来的问题是多行的）--------------------------

def test_multiline_question_renders_as_multiple_lines():
    """`gate._ask_the_human` 传的问题带 `\\n`（第二行是「为什么要问」）。
    按单行渲染会把换行符塞进一行里，终端上就是一坨。"""
    d = Dialog(question="是否允许 bash(command='ls')？\n`bash` 不参与工作目录边界判定",
               options=["允许这次", "拒绝"], kind="permission")
    lines = d.render(60)
    assert any("是否允许" in l for l in lines)
    assert any("不参与工作目录边界" in l for l in lines)
    assert not any("\n" in l for l in lines)


def test_selected_option_is_marked_and_the_others_are_not():
    d = q()
    lines = d.render(40)
    marked = [l for l in lines if "❯" in l]
    assert len(marked) == 1
    assert "方案 A" in marked[0]


def test_permission_dialog_uses_a_different_mark_than_a_question():
    perm = Dialog(question="允许吗", options=["允许这次", "拒绝"], kind="permission")
    ask = Dialog(question="选哪个", options=["A", "B"])
    assert perm.render(40)[0][0] != ask.render(40)[0][0]
