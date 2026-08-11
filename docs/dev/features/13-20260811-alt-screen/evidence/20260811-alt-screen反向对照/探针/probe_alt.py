#!/usr/bin/env python3
"""alt-screen 反向对照探针（feature 13 动工前）。

在真实终端里跑，测三件事：
  1. DECSET 1049 的进/出行为，以及**已在 alt 时再发 ?1049h** 会不会清屏
     （CC ink.tsx:324 注释点名 iTerm2 会清 = 闪烁源，而同文件 :962 又说「已在 alt 时是 no-op」）
  2. 各 DEC 私有模式的 DECRQM 实测支持情况（1049/1006/1002/1003/2026/...）
  3. 退出 alt 之后，shell 屏幕是不是原样

用法：probe_alt.py <日志路径> [--hold 秒]
脚本在若干检查点 sleep，外部用 AppleScript 抓屏对照。
"""
import os
import select
import sys
import termios
import time
import tty

LOG = sys.argv[1]
HOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0

MODES = [
    (7, "autowrap"),
    (1000, "mouse: press/release"),
    (1002, "mouse: button-drag"),
    (1003, "mouse: any-motion"),
    (1004, "focus reporting"),
    (1005, "mouse utf8 ext"),
    (1006, "mouse SGR ext"),
    (1015, "mouse urxvt ext"),
    (1016, "mouse SGR-pixels ext"),
    (1049, "alt screen (save cursor + clear)"),
    (2004, "bracketed paste"),
    (2026, "synchronized output"),
]

DECRQM_VALUES = {
    "0": "0=终端不认识这个模式",
    "1": "1=已设置(set)",
    "2": "2=未设置(reset)",
    "3": "3=永久设置",
    "4": "4=永久未设置",
}


def log(msg: str) -> None:
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")


def w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def query(mode: int, timeout: float = 0.6) -> str:
    """DECRQM: CSI ? <mode> $p  ->  CSI ? <mode> ; <value> $y"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = b""
    try:
        tty.setraw(fd)
        w(f"\x1b[?{mode}$p")
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], max(0.0, deadline - time.time()))
            if not r:
                break
            chunk = os.read(fd, 64)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b"$y"):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if not buf:
        return "无回复(超时)"
    txt = buf.decode("ascii", "replace")
    body = txt.lstrip("\x1b[?").rstrip("$y")
    parts = body.split(";")
    if len(parts) == 2:
        return f"{DECRQM_VALUES.get(parts[1], parts[1])}  [raw {txt!r}]"
    return f"无法解析 [raw {txt!r}]"


def cpr(timeout: float = 0.6) -> str:
    """CPR: CSI 6n -> CSI <row> ; <col> R。抓不到屏时用它反推终端做了什么。"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = b""
    try:
        tty.setraw(fd)
        w("\x1b[6n")
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], max(0.0, deadline - time.time()))
            if not r:
                break
            chunk = os.read(fd, 64)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b"R"):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if not buf:
        return "无回复(超时)"
    txt = buf.decode("ascii", "replace")
    body = txt.lstrip("\x1b[").rstrip("R")
    parts = body.split(";")
    if len(parts) == 2 and parts[0].isdigit():
        return f"行{parts[0]} 列{parts[1]}"
    return f"无法解析 [raw {txt!r}]"


def snapshot_label(name: str) -> None:
    log(f"--- 检查点 {name} @ {time.strftime('%H:%M:%S')} (hold {HOLD}s) ---")


def main() -> None:
    log("=" * 64)
    log(f"探针启动 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"TERM={os.environ.get('TERM')} TERM_PROGRAM={os.environ.get('TERM_PROGRAM')} "
        f"版本={os.environ.get('TERM_PROGRAM_VERSION')}")
    log(f"stdin.isatty={sys.stdin.isatty()} stdout.isatty={sys.stdout.isatty()}")

    log("\n[A] 进 alt 之前的模式状态（DECRQM）")
    for mode, desc in MODES:
        log(f"  ?{mode:<5} {desc:<34} {query(mode)}")

    # 主屏留下可辨认的标记，退出后要检查它们还在不在
    for i in range(1, 6):
        print(f"MAIN-BEFORE-{i} 这一行必须在退出 alt 之后原样还在")
    print("MAIN-BEFORE-末行")
    sys.stdout.flush()
    time.sleep(0.4)
    main_cursor = cpr()
    log(f"  进 alt 前主屏光标           {main_cursor}")

    log("\n[B] 发 ?1049h 进 alt")
    w("\x1b[?1049h")
    time.sleep(0.3)
    log(f"  进 alt 后查 ?1049          {query(1049)}")
    w("\x1b[2J\x1b[H")
    for i in range(1, 4):
        w(f"ALT-CONTENT-{i} 这是备用屏内容\r\n")
    w("ALT-第一阶段：此刻抓屏应只看到 ALT-CONTENT，看不到 MAIN-BEFORE\r\n")
    before_reenter = cpr()
    log(f"  alt 内已打 4 行，光标        {before_reenter}（预期 行5）")
    snapshot_label("B(在 alt，未重发 1049h)")
    time.sleep(HOLD)

    log("\n[C] **已在 alt 时再发一次 ?1049h**（CC 说 iTerm2 会当成清屏）")
    w("\x1b[?1049h")
    time.sleep(0.3)
    after_reenter = cpr()
    log(f"  重发 1049h 后光标           {after_reenter}"
        f"  →  行1=被当成「清屏+回原点」；仍是 {before_reenter}=真 no-op")
    w("AFTER-REENTER 这行是重发 1049h 之后打的\r\n")
    log(f"  重发后查 ?1049             {query(1049)}")
    snapshot_label("C(重发 1049h 之后：ALT-CONTENT 还在=no-op，没了=被清屏)")
    time.sleep(HOLD)

    log("\n[D] 在 alt 里开鼠标上报 1000/1002/1003/1006，查模式是否真被置上")
    w("\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h")
    time.sleep(0.2)
    for mode in (1000, 1002, 1003, 1006, 1016):
        log(f"  开启后查 ?{mode:<5}            {query(mode)}")
    w("MOUSE-ON 鼠标上报已开：现在点一下这个窗口\r\n")
    w("收到的字节会打在下面（SGR 1006 形如 \\x1b[<0;12;3M）\r\n")
    snapshot_label("D(等鼠标事件)")

    # 收鼠标字节
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    got = b""
    try:
        tty.setraw(fd)
        deadline = time.time() + HOLD * 2
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], max(0.0, deadline - time.time()))
            if not r:
                continue
            chunk = os.read(fd, 256)
            if not chunk:
                break
            got += chunk
            w(f"RECV {chunk!r}\r\n")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    log(f"  鼠标/键盘原始字节：{got!r}" if got else "  鼠标/键盘原始字节：（无，这段没收到输入）")

    w("\x1b[?1006l\x1b[?1003l\x1b[?1002l\x1b[?1000l")
    time.sleep(0.2)
    log(f"  关闭后查 ?1006             {query(1006)}")

    log("\n[E] 发 ?1049l 退出 alt")
    snapshot_label("E-前(仍在 alt)")
    time.sleep(1.0)
    w("\x1b[?1049l")
    time.sleep(0.3)
    # 先 CPR 再 DECRQM：Terminal.app 不认 DECRQM，那条不被识别的查询会在屏上留下
    # 一个可见字符、把光标推走一列——先查 DECRQM 会污染「光标是否原样还回」这条测量
    restored = cpr()
    log(f"  退出后主屏光标              {restored}（进 alt 前是 {main_cursor}；相等=光标被原样还回）")
    log(f"  退出后查 ?1049             {query(1049)}")
    print("MAIN-AFTER 退出 alt 之后打的第一行")
    sys.stdout.flush()
    snapshot_label("E-后(已回主屏：MAIN-BEFORE-1..5 应原样还在，ALT-CONTENT 应消失)")
    time.sleep(HOLD)

    log("\n探针结束\n")
    print("PROBE-DONE")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
