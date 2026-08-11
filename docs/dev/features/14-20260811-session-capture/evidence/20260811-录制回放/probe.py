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


# --- 花钱守卫 -----------------------------------------------------------

class WouldSpendMoney(RuntimeError):
    """探针要提交一行给模型了——那会真的发请求、真的花钱。"""


def send(fd, text, *, allow_submit=False):
    """替代裸 `os.write(fd, ...)`。

    **同一个错误犯了三次**（2026-08-11：反向对照一次、TUI 冒烟一次、录制一次），
    每次都是探针里带了个回车，把一行真提交给了模型——花钱且卡几分钟。
    靠记性挡不住，所以在这里挡：**要提交必须显式说 `allow_submit=True`**。

    只挡「提交给模型」的回车。`/命令` 与 `!shell` 不打模型，照常放行。
    """
    data = text.encode() if isinstance(text, str) else text
    if not allow_submit and data.endswith((b"\r", b"\n")):
        line = data.rstrip(b"\r\n").decode("utf-8", "replace")
        if not line.startswith(("/", "!")) and line.strip():
            raise WouldSpendMoney(
                f"这一行回车会把 {line!r} 提交给模型（真花钱）。"
                "确实要的话传 allow_submit=True；只想打字不提交就别带回车。")
    return os.write(fd, data)
