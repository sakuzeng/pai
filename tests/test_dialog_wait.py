"""真人问答的等待判据（R4#2 / R4#3，2026-08-18 评审）。

判据必须落在**这一框**上，不在仲裁器的显示状态上：`arbiter.current()` 在
「队列空（答完了）」与「非空但被打字压住（还没轮到显示）」两种语义完全不同的
状态下都返回 None。拿它当完成判据的后果是——用户正打字时弹的权限框
**一次都没显示就被判「未作答」**（对 gate 而言即拒绝），且框从未被 resolve，
1.5s 后以僵尸形态弹出接管键盘，它的答案再经共享 FIFO 错配给下一个问题。
"""

import pytest

from pai.modes.interactive import NO_ANSWER, await_dialog_answer
from pai.tui.app import TuiApp
from pai.tui.arbiter import InputArbiter
from pai.tui.dialog import Dialog
from pai.tui.keys import KeyDecoder
from pai.tui.renderer import DockRenderer
from pai.tui.screen import VirtualScreen


class Clock:
    """假时钟：抑制期靠它推进，不真 sleep（arbiter 早就支持注入 now）。"""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make(clock):
    screen = VirtualScreen(cols=48, rows=12)
    renderer = DockRenderer(write=screen.write, width=lambda: screen.cols)
    app = TuiApp(renderer=renderer, arbiter=InputArbiter(now=clock))
    app.refresh()
    return app


class ScriptedDriver:
    """镜像 `TuiDriver.pump_until` 的形状：done 为真才停，否则读一批喂给 app。

    脚本喂完 done 仍为假 = 等待方在死等——**当场炸掉**，别让测试挂住
    （挂死不红是本仓库已登记的老账，测试基建自己不许再犯）。
    """

    def __init__(self, app, steps) -> None:
        self.app = app
        self.steps = list(steps)      # bytes = 按键；callable = 让时间流逝
        self.polls = 0
        self.decoder = KeyDecoder()

    def pump_until(self, done, on_action) -> None:
        while not done():
            if not self.steps:
                raise AssertionError("脚本喂完了 done 仍为假——等待方在死等")
            self.polls += 1
            step = self.steps.pop(0)
            if callable(step):
                step()
                continue
            for kind, payload in self.app.feed(step, self.decoder):
                on_action(kind, payload)


def _permission_dialog():
    return Dialog(question="允许执行 rm -rf ./build 吗？",
                  options=["允许这次", "拒绝"], kind="permission")


def test_a_suppressed_dialog_does_not_end_the_wait():
    """**这条就是 R4#2 本身**：抑制期不许把等待判成结束。"""
    clock = Clock()
    app = make(clock)
    app.arbiter.note_typing("我正在打一条 steering 消息")     # 抑制期开始
    dialog = _permission_dialog()
    app.enqueue_dialog(dialog)

    assert app.arbiter.current() is None        # 旧判据此刻为真——那正是 bug

    driver = ScriptedDriver(app, [
        lambda: clock.advance(2.0),             # 用户停手，抑制到期
        b"1",                                   # 框这才显示，用户选「允许这次」
    ])
    answer = await_dialog_answer(driver, app, dialog, lambda *_: None)

    assert answer == "允许这次"
    assert driver.polls == 2                    # 真的等了，不是秒返


def test_interrupting_the_wait_leaves_no_zombie_dialog():
    """R4#3 上半：中断退出必须把框从队列里摘掉。

    不摘的后果不是「少答一次」——僵尸框会接管**全部**按键
    （`app._key` 里 `arbiter.current()` 非 None 就一律走对话框分支）。
    """
    clock = Clock()
    app = make(clock)
    dialog = _permission_dialog()
    app.enqueue_dialog(dialog)

    driver = ScriptedDriver(app, [b"\x03"])     # Ctrl+C
    answer = await_dialog_answer(driver, app, dialog, lambda *_: None)

    assert answer == NO_ANSWER
    assert app.arbiter.pending_count() == 0
    assert app.arbiter.current() is None


def test_an_abandoned_dialog_cannot_answer_the_next_question():
    """R4#3 下半：被中断那一框的结论，绝不能被**下一个**问题取走。"""
    clock = Clock()
    app = make(clock)

    first = _permission_dialog()
    app.enqueue_dialog(first)
    ScriptedDriver(app, [b"\x03"])
    assert await_dialog_answer(
        ScriptedDriver(app, [b"\x03"]), app, first, lambda *_: None) == NO_ANSWER

    second = Dialog(question="第二个问题：允许写入 config.json 吗？",
                    options=["允许这次", "拒绝"], kind="permission")
    app.enqueue_dialog(second)
    driver = ScriptedDriver(app, [b"2"])        # 用户对**这一个**明确选「拒绝」
    answer = await_dialog_answer(driver, app, second, lambda *_: None)

    assert answer == "拒绝"
    assert driver.polls == 1                    # 不是拿上一框的残留秒返


def test_the_caller_still_sees_commands_typed_during_a_question():
    """08 那条铁证不许回退：提问期间敲的 `!命令` 仍要交回主循环执行。"""
    clock = Clock()
    app = make(clock)
    dialog = Dialog(question="用哪个？", options=["A", "B"])
    app.enqueue_dialog(dialog)

    seen = []
    # `1\r` 而非 `1`：R4#16 拍板后提问框判整串（回车才裁决），首键直选只剩权限框
    driver = ScriptedDriver(app, [b"!echo hi\r", b"1\r"])
    answer = await_dialog_answer(
        driver, app, dialog, lambda kind, payload: seen.append((kind, payload)))

    assert seen == [("command", "!echo hi")]
    assert answer == "A"


def test_a_quit_command_during_a_question_ends_the_wait_without_a_zombie():
    """R4#15：dialog 期间敲 `/exit`，dispatch 返回的 quit 被丢弃——静默空操作。
    REPL 的 asker 同款逃生口是好使的（「/exit 退出」明明白白印在提示里），
    两处语义漂移。修法：`on_action` 返回 quit 时与 EOF 同款——连框一起撤。"""
    clock = Clock()
    app = make(clock)
    dialog = _permission_dialog()
    app.enqueue_dialog(dialog)

    driver = ScriptedDriver(app, [b"/exit\r"])
    answer = await_dialog_answer(
        driver, app, dialog,
        lambda kind, payload: kind == "command" and payload == "/exit")

    assert answer == NO_ANSWER, "退出不是作答——不许给 gate 一个像答案的东西"
    assert app.arbiter.pending_count() == 0, "框必须撤掉，不许留僵尸接管键盘"
    assert app.arbiter.current() is None
