"""鼠标的端到端（feature 16 T9）：真 pai 进程 + 真 pty + **实测抓到的真实字节**。

喂进去的不是我编的序列，是 2026-08-11 从真 iTerm2 里录到的形状
（features/16 evidence）：按下 `\\x1b[<0;列;行M`、拖动 `\\x1b[<32;…M`、
滚轮 `\\x1b[<64;…M`，以及**一次手势 142 条**这个量级。
"""

import os
import time

import pytest

from fake_provider import turn
from pai.tui.replay import load, replay, to_text
from test_e2e_tui import Session, session  # noqa: F401 - session 是 fixture

pytestmark = pytest.mark.skipif(not hasattr(os, "openpty"), reason="需要 pty")

WHEEL_UP = b"\x1b[<64;10;5M"


def _screen(s):
    return replay(load(s.record))


def test_mouse_tracking_is_enabled_exactly_once_and_disabled_on_exit(session, tmp_path):
    s, _ = session([turn("好的。")])
    s.send("你好\r", until="好的")
    blob = "".join(r["data"] for r in load(s.record))
    assert blob.count("\x1b[?1006h") == 1
    s.send("\x04")                                  # Ctrl+D
    time.sleep(1.0)
    s.drain(1.0)
    raw = s.raw.decode("utf-8", "replace")
    # **先关鼠标再退备用屏**：顺序反了，事件会漏进 shell
    assert raw.index("\x1b[?1006l") < raw.index("\x1b[?1049l")


def test_a_burst_of_wheel_events_scrolls_the_transcript(session, tmp_path):
    """142 是实测数字。滚上去之后**看到的必须是本次会话的内容**，
    而不是终端 scrollback 里更早的东西——这正是本 feature 的起点。"""
    long_answer = "第一段。\n" + "\n".join(f"甲{i}" for i in range(30))
    s, _ = session([turn(long_answer), turn("第二段。")])
    s.send("问一句\r", until="甲29")
    before = _screen(s).lines()
    s.send(WHEEL_UP * 142)
    time.sleep(0.6)
    s.drain(0.6)
    after = _screen(s).lines()
    assert after[:4] != before[:4]                  # 上面的内容变了
    assert after[-1] == before[-1]                  # dock 的最后一行没动
    assert "已上滚" in "\n".join(after)


def test_dragging_highlights_and_copies(session, tmp_path):
    """按下 → 拖过 → 松开：屏幕上出现反显，且走了复制那条路。"""
    s, _ = session([turn("可以复制的一行文本。")])
    s.send("你好\r", until="可以复制的一行")
    text = to_text(_screen(s))
    row = next(i for i, line in enumerate(text.split("\n")) if "可以复制的一行" in line)
    s.send(f"\x1b[<0;3;{row + 1}M".encode())        # 按下
    s.send(f"\x1b[<32;12;{row + 1}M".encode())      # 拖过
    s.send(f"\x1b[<0;12;{row + 1}m".encode())       # 松开
    time.sleep(0.5)
    s.drain(0.5)
    blob = "".join(r["data"] for r in load(s.record))
    assert "\x1b[7m" in blob                        # 反显出现过


# ---- feature 20：拖动的端到端帧数（2026-08-19）----


def test_a_fast_drag_is_batched_into_a_handful_of_frames(session, tmp_path):
    """一次快速拖选，真 pai 进程只画个位数的帧。

    诚实边界（重要）：**这条钉的不是 feature 16 的渲染节流。**
    交付 20 时做过对照实验（40 条拖动事件，真 pty）：

    | 事件间隔 | 有节流 | 无节流 |
    |---|---|---|
    | 0ms  |  6 |  7 |
    | 10ms | 71 | 67 |
    | 30ms | 75 | 70 |

    两列没有差别——这个基建造不出「逐条到达且间隔 <16ms」那种形态：事件要么
    被一次 `os.read` 全读进来（0ms 那档），要么实际间隔已经超过 16ms 窗口
    （节流本就不该生效）。

    交付时逐层做了注入反证，确认它到底钉住什么：拆掉节流 → 不红；
    拆掉 driver 的「读干净再处理」→ 不红（60 条事件约 720 字节，
    一次 `os.read(4096)` 就全拿到了）；只让每个鼠标事件都 refresh → 不红。
    **只有把 `_merge_mouse_runs` 一起拆掉才会红**——所以它钉的是
    「鼠标事件按批合并 + 每批只 refresh 一次」这两条合起来的效果。

    一帧 = 一条写记录（已实测：首帧与后续帧都是 1 条）。
    """
    s, _ = session([turn("可以拖选的一行文本。")])
    s.send("你好\r", until="可以拖选的一行")
    text = to_text(_screen(s))
    row = next(i for i, line in enumerate(text.split("\n"))
               if "可以拖选的一行" in line) + 1

    s.send(f"\x1b[<0;3;{row}M".encode())            # 按下
    s.drain(0.3)
    before = len(load(s.record))

    moves = 60
    for i in range(moves):                          # 一口气送出，不给间隔
        s.send(f"\x1b[<32;{4 + i % 40};{row}M".encode(), wait=0)
    s.drain(0.6)
    frames = len(load(s.record)) - before

    s.send(f"\x1b[<0;40;{row}m".encode())           # 松开
    s.drain(0.4)

    assert frames < moves // 4, (
        f"{moves} 条拖动事件写了 {frames} 次终端——鼠标事件的批合并没生效")
    assert "\x1b[7m" in "".join(r["data"] for r in load(s.record)), \
        "一次反显都没画出来"
