"""T3：输入归属仲裁 —— 本次要治的病就在这里。

病是「asker 与 REPL 主循环共用一个阻塞 reader，谁先 read() 谁拿到」，
实际发生过 `!echo 我是命令` 被当成了对问题的回答（08 遗留的铁证）。
药方照 CC：**一个仲裁函数**算出此刻谁拥有输入，消费者只有 is_active 开关；
且仲裁**偏袒正在打字的人**（K tui/cc-input-ownership-and-modes.md 第一节）。
"""

from pai.tui.arbiter import EDITOR, InputArbiter


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, ms):
        self.t += ms / 1000.0


def make(**kw):
    clock = Clock()
    return InputArbiter(now=clock, **kw), clock


def test_editor_owns_input_when_nothing_is_pending():
    a, _ = make()
    assert a.owner() is EDITOR


def test_dialog_owns_input_when_the_input_box_is_empty():
    a, _ = make()
    a.enqueue("权限框")
    assert a.owner() == "权限框"


def test_typing_suppresses_pending_dialogs():
    """CC 的语义：输入框非空就把对话框压住。"""
    a, _ = make()
    a.note_typing("半句话")
    a.enqueue("权限框")
    assert a.owner() is EDITOR


def test_dialog_appears_after_the_typing_lull():
    a, clock = make(suppression_ms=1500)
    a.note_typing("半句话")
    a.enqueue("权限框")
    clock.advance(1499)
    assert a.owner() is EDITOR
    clock.advance(2)
    assert a.owner() == "权限框"


def test_clearing_the_input_releases_immediately():
    """清空输入就是「我不打了」，不必再等 1500ms。"""
    a, _ = make()
    a.note_typing("半句话")
    a.enqueue("权限框")
    a.note_typing("")
    assert a.owner() == "权限框"


def test_whitespace_only_input_does_not_count_as_typing():
    a, _ = make()
    a.note_typing("   ")
    a.enqueue("权限框")
    assert a.owner() == "权限框"


def test_each_keystroke_restarts_the_lull():
    a, clock = make(suppression_ms=1500)
    a.note_typing("a")
    a.enqueue("权限框")
    clock.advance(1400)
    a.note_typing("ab")
    clock.advance(1400)
    assert a.owner() is EDITOR


def test_user_invoked_dialogs_are_not_suppressed():
    """用户自己唤出来的东西（选择器/确认框）不该被自己正在打的字压住。"""
    a, _ = make()
    a.note_typing("半句话")
    a.enqueue("模式选择器", user_invoked=True)
    assert a.owner() == "模式选择器"


def test_pending_count_is_visible_so_it_is_not_silent():
    """被压住时必须能说出「N 个请求在等」——静默是这条设计里最不能接受的部分。"""
    a, _ = make()
    a.note_typing("半句话")
    a.enqueue("权限框")
    a.enqueue("提问框")
    assert a.owner() is EDITOR
    assert a.pending_count() == 2
    assert a.is_suppressing() is True


def test_not_suppressing_when_there_is_nothing_to_suppress():
    a, _ = make()
    a.note_typing("半句话")
    assert a.is_suppressing() is False


def test_dialogs_are_answered_in_order():
    a, _ = make()
    a.enqueue("第一个")
    a.enqueue("第二个")
    assert a.owner() == "第一个"
    a.resolve()
    assert a.owner() == "第二个"
    a.resolve()
    assert a.owner() is EDITOR


def test_time_is_injected_so_tests_never_sleep():
    a, clock = make(suppression_ms=10)
    a.note_typing("x")
    a.enqueue("框")
    assert a.owner() is EDITOR
    clock.advance(11)
    assert a.owner() == "框"


def test_resolve_removes_the_named_item_not_whichever_is_first():
    """按身份移除，不盲弹队首。

    现实里权限是按批**串行**判的，队列同时只会有一个，所以盲弹 `pop(0)`
    碰巧不出错——但「结构上不可能出错」与「碰巧不出错」是两回事，
    而中断路径要撤的恰恰可能不是队首（R4#3）。
    """
    arbiter = InputArbiter()
    first, second = object(), object()
    arbiter.enqueue(first)
    arbiter.enqueue(second)

    arbiter.resolve(second)

    assert arbiter.pending_count() == 1
    assert arbiter.owner() is first


def test_resolve_without_an_argument_still_pops_the_head():
    """既有调用方（`_dialog_key`）不传参数，语义不变。"""
    arbiter = InputArbiter()
    first, second = object(), object()
    arbiter.enqueue(first)
    arbiter.enqueue(second)

    arbiter.resolve()

    assert arbiter.owner() is second


def test_resolving_something_already_gone_is_a_no_op():
    """撤一个已经被答掉的框不该误伤下一个——中断与作答可能前后脚到。"""
    arbiter = InputArbiter()
    only = object()
    arbiter.enqueue(only)
    arbiter.resolve(only)

    arbiter.resolve(only)

    assert arbiter.pending_count() == 0
