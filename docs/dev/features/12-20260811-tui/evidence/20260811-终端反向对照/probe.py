"""TUI 反向对照：在真 pty 里跑 pai REPL，抓原始字节。

不提交任何 prompt——只碰终端行为，不花钱。
"""
import os, pty, select, signal, struct, sys, termios, fcntl, time, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def set_winsize(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

def spawn(rows=24, cols=80, args=("pai",)):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(REPO)
        os.environ["TERM"] = "xterm-256color"
        os.execvp(args[0], list(args))
    set_winsize(fd, rows, cols)
    return pid, fd

def drain(fd, timeout=1.0):
    out = b""
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            end = time.time() + 0.35
    return out

def show(label, data):
    print(f"\n===== {label} =====")
    print(repr(data.decode("utf-8", "replace"))[:2400])
