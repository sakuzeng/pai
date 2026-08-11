"""alt-screen 的端到端（feature 13 T7）：真 pai 进程 + 真 pty + 假 provider + 回放。

与 `test_e2e_tui.py` 同一套地基。**为什么非要 e2e**：feature 12/13 的教训是
「接缝上的 bug 离线测试结构上看不见」——本 task 写测试时就撞到两条：
录制器漏掉了 `TerminalSession` 的写、回放按换行数估屏幕高度（alt 屏一个换行都没有）。
两条都是离线单测**结构上**测不到的，因为它们在「谁写字节」和「怎么回放」的接缝上。
"""

import os
import time

import pytest

from fake_provider import turn
from pai.tui.replay import load, replay, to_text
from test_e2e_tui import Session, session  # noqa: F401 - session 是 fixture

pytestmark = pytest.mark.skipif(not hasattr(os, "openpty"), reason="需要 pty")


def _screen(s):
    return replay(load(s.record))


def test_a_full_turn_renders_with_the_dock_pinned_to_the_bottom(session, tmp_path):
    """整屏归 pai：上面是 transcript，下面是 dock，且 dock 贴在最后一行。"""
    s, _ = session([turn("我是 pai，可以帮你写代码。")])
    s.send("你好\r", until="我是 pai")
    screen = _screen(s)
    lines = screen.lines()
    assert "我是 pai" in "\n".join(lines)
    # 最后一行是 footer（cwd + 模式 在左、模型 在右）
    assert "deepseek" in lines[-1]
    # 倒数第二行是输入行；dock 与 transcript 之间有分隔线
    assert any("─" * 10 in line for line in lines[-6:])


def test_alt_screen_is_entered_exactly_once(session, tmp_path):
    """**重发 `?1049h` 会清屏闪白**（两个 macOS 终端实测）。所以只许发一次。"""
    s, _ = session([turn("好的。")])
    s.send("你好\r", until="好的")
    blob = "".join(r["data"] for r in load(s.record))
    assert blob.count("\x1b[?1049h") == 1
    # 清屏也只许有进 alt 那一次（此刻屏幕本来就是空的，擦不掉任何东西）；
    # 之后再清会让屏幕在整个渲染耗时里全黑。
    assert blob.count("\x1b[2J") == 1


def test_paging_up_moves_the_transcript_but_not_the_dock(session, tmp_path):
    """用户往回读历史时，dock（正在输入的那一行、正在跑什么）必须钉住不动。"""
    # 内容必须**超过一屏**才滚得动——不然这条测试测的是「什么都没发生」
    long_one = "第一次回答。\n" + "\n".join(f"甲{i}" for i in range(20))
    long_two = "第二次回答。\n" + "\n".join(f"乙{i}" for i in range(20))
    long_three = "第三次回答。\n" + "\n".join(f"丙{i}" for i in range(20))
    s, _ = session([turn(long_one), turn(long_two), turn(long_three)])
    s.send("问题一\r", until="甲19")
    s.send("问题二\r", until="乙19")
    before = _screen(s).lines()
    s.send("\x1b[5~")                       # PgUp
    after = _screen(s).lines()
    # footer 与输入行一格没动（**dock 本身会多出「已上滚」那一行，这是对的**——
    # 屏幕不动而内容还在来，不说出来就与「卡死了」无法区分）
    assert after[-1] == before[-1]
    assert after[-2] == before[-2]
    assert after[:6] != before[:6]          # 上面的内容变了
    assert "已上滚" in "\n".join(after)

    # **滚上去之后新内容到达，视口不许被拽回底部**——这是「用户正在读历史时
    # agent 还在说话」的真实场景，也是本条 e2e 的注入反证靶子。
    top = _screen(s).lines()[:4]
    s.send("问题三\r")
    time.sleep(2.0)
    s.drain(1.0)
    assert _screen(s).lines()[:4] == top
    assert "有新内容" in to_text(_screen(s))


def test_leaving_restores_the_shell_screen_and_leaves_a_session_hint(session, tmp_path):
    """退出时把屏幕原样还给 shell，并在**主屏**留一行「会话存哪了」。

    形态对齐 CC 的 `printResumeHint()`：先退 alt 再打，否则提示落在备用屏上，
    跟着屏幕一起消失。
    """
    s, _ = session([turn("好的。")])
    s.send("你好\r", until="好的")
    s.send("\x04")                          # Ctrl+D 退出
    time.sleep(1.0)
    s.drain(1.0)
    raw = s.raw.decode("utf-8", "replace")
    assert "\x1b[?1049l" in raw             # 屏幕还回去了
    assert "\x1b[?7h" in raw                # 自动折行也还回去了
    hint = raw.split("\x1b[?1049l", 1)[1]
    assert "会话已存" in hint                # 提示落在**主屏**上
    assert ".jsonl" in hint


def test_the_answer_is_wrapped_not_truncated(session, tmp_path):
    """alt 屏关掉了自动折行——长答案不自己折就是被右边界切掉，内容**丢了**。"""
    long_answer = "这是一句很长的话。" * 12
    s, _ = session([turn(long_answer)])
    s.send("说点长的\r", until="这是一句很长的话")
    text = to_text(_screen(s))
    assert text.count("这是一句很长的话") >= 10     # 全都在，只是分了几行
