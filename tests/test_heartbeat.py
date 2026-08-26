"""干活期间的心跳（feature 39）。

它存在的理由只有一个：长命令跑着的时候，主线程正堵在 `shell._wait` 的轮询循环里，
而界面层需要一个「喘气」的机会去读键盘、重绘。形状照 `core/interrupt.py`——
理由也一样：`@tool` 从函数签名生成 schema，给 bash 加参数就会把它发给模型看，
工具需要的运行期上下文只能从旁路进。
"""
import time

from pai.core import heartbeat


def test_default_heartbeat_is_a_no_op():
    """永远返回可用对象，绝不返回 None——否则每个调用点都要判空（同 interrupt）。"""
    heartbeat.set_current(None)
    heartbeat.current().beat()          # 不炸即通过


def test_beat_calls_the_injected_callback():
    beats = []
    heartbeat.set_current(heartbeat.Heartbeat(lambda: beats.append(1)))
    try:
        heartbeat.current().beat()
        heartbeat.current().beat()
    finally:
        heartbeat.set_current(None)
    assert beats == [1, 1]


def test_a_crashing_heartbeat_does_not_take_the_tool_down():
    """心跳是界面层的便利，不是正确性的一部分：它自己炸了，命令必须照跑。

    反过来（不吞）意味着一个渲染 bug 能把用户正在跑的命令连坐掉——
    这与「工具错误不 throw」是同一条底线。
    """
    def boom():
        raise RuntimeError("渲染器炸了")

    heartbeat.set_current(heartbeat.Heartbeat(boom))
    try:
        heartbeat.current().beat()      # 不许抛
    finally:
        heartbeat.set_current(None)


def test_a_long_command_beats_while_it_waits():
    """真跑一条命令：等待期间心跳要真的跳，而且跳的次数与时长对得上。

    钉次数而不只是「跳过」：只断言「至少一次」的话，一个「只在命令结束后跳一次」
    的实现同样能过——而那正好是本 feature 要修的那个病（事件到来时才 poll）。
    """
    from pai.core.tools.shell import POLL_SECONDS, bash

    beats = []
    heartbeat.set_current(heartbeat.Heartbeat(lambda: beats.append(time.monotonic())))
    try:
        bash(command="sleep 1")
    finally:
        heartbeat.set_current(None)

    assert len(beats) >= int(1.0 / POLL_SECONDS) - 2, (
        f"1 秒的命令只跳了 {len(beats)} 次，粒度对不上（POLL_SECONDS={POLL_SECONDS}）")
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert max(gaps) < 0.5, f"心跳之间空了 {max(gaps):.2f}s，界面会明显卡住"


def test_a_fast_command_does_not_need_a_beat():
    """秒退的命令一次都不跳也没关系——不许为了「跳过」而人为拖慢。"""
    from pai.core.tools.shell import bash

    beats = []
    heartbeat.set_current(heartbeat.Heartbeat(lambda: beats.append(1)))
    try:
        started = time.monotonic()
        bash(command="true")
    finally:
        heartbeat.set_current(None)
    assert time.monotonic() - started < 0.5
