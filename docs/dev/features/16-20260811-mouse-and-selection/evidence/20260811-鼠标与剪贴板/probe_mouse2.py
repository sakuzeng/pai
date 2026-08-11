#!/usr/bin/env python3
"""鼠标探针 v2：**按事件类型计数**，不再保存原始前缀。

v1 的缺陷（feature 16 evidence 第 3 条）：只记前 200 字节，而那三段的开头恰好
全是滚轮事件，于是「1002 与 1003 差多少」「点击/拖动长什么样」两个真正要测的
问题一个都没答上——**工具保存的是原始前缀，而我要的是按类型计数**。
"""
import os
import re
import select
import sys
import termios
import time
import tty
from collections import Counter

LOG = sys.argv[1]
SGR = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")


def log(msg: str) -> None:
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")


def w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def kind(button: int, final: bytes) -> str:
    if button & 64:
        return "滚轮上" if (button & 3) == 0 else "滚轮下"
    if button & 32:
        return f"拖动(按钮{button & 3})"
    if final == b"m":
        return f"松开(按钮{button & 3})"
    return f"按下(按钮{button & 3})"


def phase(name: str, modes: str, seconds: float) -> None:
    w(f"\r\n=== {name} ===\r\n")
    w(f"\x1b[?{modes}h\x1b[?1006h" if modes else "")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    got = b""
    try:
        tty.setraw(fd)
        deadline = time.time() + seconds
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], max(0.0, deadline - time.time()))
            if r:
                chunk = os.read(fd, 8192)
                if not chunk:
                    break
                got += chunk
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if modes:
            w(f"\x1b[?{modes}l")
    events = SGR.findall(got)
    counts = Counter(kind(int(b), f) for b, _, _, f in events)
    positions = {(x, y) for _, x, y, _ in events}
    log(f"[{name}] {len(got)} 字节 / {len(events)} 条事件 / {len(positions)} 个不同坐标")
    for k, n in counts.most_common():
        log(f"     {k:>14}  {n} 条")
    leftover = SGR.sub(b"", got)
    if leftover.strip():
        log(f"     非鼠标字节：{leftover[:120]!r}")


def main() -> None:
    log("=" * 64)
    log(f"鼠标探针 v2 {time.strftime('%H:%M:%S')} "
        f"{os.environ.get('TERM_PROGRAM')} {os.environ.get('TERM_PROGRAM_VERSION')}")
    w("\x1b[?1049h\x1b[2J\x1b[H")
    w("接下来三段，每段 6 秒。**请严格按提示做，不要提前动**。\r\n")
    time.sleep(3)
    phase("1·只开1002·只移动指针（不要滚、不要点）", "1002", 6)
    phase("2·只开1003·只移动指针（不要滚、不要点）", "1003", 6)
    phase("3·开1003·只点击与拖动（不要滚）", "1003", 8)
    w("\x1b[?1049l")
    log("探针 v2 结束\n")
    print("MOUSE-PROBE-V2-DONE")


if __name__ == "__main__":
    main()
