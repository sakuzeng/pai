#!/usr/bin/env python3
"""alt-screen 里改窗口大小会发生什么（feature 13 反向对照第二支）。

问三件事：
  1. alt 屏里 resize，SIGWINCH 还来不来、来几次
  2. 终端会不会替我把 alt 屏内容重排/保留（还是原样留在那儿等我重画）
  3. 变窄时超宽的那一行是被截断还是被折行
"""
import os
import signal
import sys
import time

LOG = sys.argv[1]
events = []


def log(msg: str) -> None:
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")


def w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def on_winch(signum, frame) -> None:  # noqa: ANN001, ARG001
    size = os.get_terminal_size()
    events.append((time.time(), size.columns, size.lines))


def main() -> None:
    signal.signal(signal.SIGWINCH, on_winch)
    size = os.get_terminal_size()
    log("=" * 64)
    log(f"resize 探针 {time.strftime('%H:%M:%S')} TERM_PROGRAM={os.environ.get('TERM_PROGRAM')}")
    log(f"起始尺寸 {size.columns}x{size.lines}")

    w("\x1b[?1049h\x1b[2J\x1b[H")
    w("ALT-RESIZE-1 短行\r\n")
    w("ALT-RESIZE-2 " + ("横向填充" * 12) + " 末尾标记END\r\n")  # 96 列宽的一行
    w("ALT-RESIZE-3 短行\r\n")
    w("--- 上面三行是 resize 之前画的，我不会重画它们 ---\r\n")
    log("--- 检查点 R1(alt 里已画 4 行，等外部改窗口大小) ---")
    time.sleep(6)

    log(f"收到 SIGWINCH {len(events)} 次：")
    for ts, cols, rows in events:
        log(f"  {time.strftime('%H:%M:%S', time.localtime(ts))} -> {cols}x{rows}")
    now = os.get_terminal_size()
    log(f"resize 后尺寸 {now.columns}x{now.lines}")
    w(f"\r\nAFTER-RESIZE 现在是 {now.columns}x{now.lines}（上面那几行我一个字节都没重画）\r\n")
    log("--- 检查点 R2(resize 之后，应用没有重画) ---")
    time.sleep(5)

    w("\x1b[?1049l")
    log("已退出 alt")
    print("RESIZE-PROBE-DONE")
    sys.stdout.flush()
    log("resize 探针结束\n")


if __name__ == "__main__":
    main()
