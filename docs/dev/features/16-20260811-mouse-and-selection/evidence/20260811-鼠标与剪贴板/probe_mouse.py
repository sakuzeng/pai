#!/usr/bin/env python3
"""鼠标上报 + OSC 52 剪贴板探针（feature 16 动工前反向对照）。

feature 13 的手工清单里，鼠标那一整块因为缺辅助功能授权**一条都没测到**。
现在授权有了，把欠的补上：1002 与 1003 到底吵到什么程度、SGR 1006 的真实字节、
以及 OSC 52 能不能写进剪贴板（决定剪贴板走哪条路）。
"""
import os
import select
import sys
import termios
import time
import tty

LOG = sys.argv[1]
MARKER = sys.argv[2] if len(sys.argv) > 2 else "PAI-OSC52-TEST"


def log(msg: str) -> None:
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")


def w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def collect(seconds: float) -> bytes:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    got = b""
    try:
        tty.setraw(fd)
        deadline = time.time() + seconds
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], max(0.0, deadline - time.time()))
            if not r:
                continue
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            got += chunk
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return got


def main() -> None:
    import base64
    log("=" * 64)
    log(f"鼠标/剪贴板探针 {time.strftime('%H:%M:%S')} "
        f"TERM_PROGRAM={os.environ.get('TERM_PROGRAM')} {os.environ.get('TERM_PROGRAM_VERSION')}")

    w("\x1b[?1049h\x1b[2J\x1b[H")
    w("=== A. OSC 52 写剪贴板 ===\r\n")
    payload = base64.b64encode(MARKER.encode()).decode()
    w(f"\x1b]52;c;{payload}\x07")
    log(f"[A] 已发 OSC 52，内容 {MARKER!r}（外部用 pbpaste 核对）")
    time.sleep(1.0)

    w("=== B. 只开 1002（按键+拖动才报）：请把鼠标在窗口里划几下，不要按键 ===\r\n")
    log("--- 检查点 B(1002，只移动不按键) ---")
    w("\x1b[?1002h\x1b[?1006h")
    b_bytes = collect(6.0)
    w("\x1b[?1002l")
    log(f"[B] 1002 下纯移动收到 {len(b_bytes)} 字节：{b_bytes[:200]!r}")

    w("\r\n=== C. 只开 1003（任何移动都报）：同样划几下 ===\r\n")
    log("--- 检查点 C(1003，只移动不按键) ---")
    w("\x1b[?1003h\x1b[?1006h")
    c_bytes = collect(6.0)
    log(f"[C] 1003 下纯移动收到 {len(c_bytes)} 字节：{c_bytes[:200]!r}")

    w("\r\n=== D. 1003 开着：请单击一次、然后按住拖一小段、再滚一下滚轮 ===\r\n")
    log("--- 检查点 D(点击/拖动/滚轮) ---")
    d_bytes = collect(10.0)
    w("\x1b[?1006l\x1b[?1003l\x1b[?1002l\x1b[?1000l")
    log(f"[D] 收到 {len(d_bytes)} 字节")
    for piece in d_bytes.split(b"\x1b")[:40]:
        if piece:
            log(f"     \\x1b{piece!r}")

    w("\x1b[?1049l")
    log("探针结束\n")
    print("MOUSE-PROBE-DONE")


if __name__ == "__main__":
    main()
