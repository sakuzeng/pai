import os, sys, time, select
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import spawn, set_winsize, show

pid, fd = spawn(24, 80, args=("python3", "/tmp/pai_sl_driver.py"))
out = b""
t0 = time.time(); resized = False
while time.time() - t0 < 8:
    if not resized and time.time() - t0 > 1.2:
        set_winsize(fd, 24, 40); resized = True
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
show("状态行原始字节（80 列，1.2s 后 resize 到 40 列）", out)
try: os.waitpid(pid, 0)
except ChildProcessError: pass
