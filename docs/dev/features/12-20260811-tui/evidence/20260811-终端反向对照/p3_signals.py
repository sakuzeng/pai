"""Ctrl+C 两级 / resize 时提示符状态 / 干活时打字 的真 pty 观测。"""
import os, sys, time, select
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import spawn, set_winsize, show

def read_for(fd, secs):
    out = b""; t0 = time.time()
    while time.time() - t0 < secs:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try: chunk = os.read(fd, 65536)
            except OSError: break
            if not chunk: break
            out += chunk
    return out

pid, fd = spawn(24, 80)
show("A 启动", read_for(fd, 2.0))

os.write(fd, b"\x03"); show("B 空闲时第一次 Ctrl+C", read_for(fd, 1.2))
os.write(fd, b"\x03"); show("C 紧接第二次 Ctrl+C", read_for(fd, 1.2))

os.write(fd, "半行中文没回车".encode())
time.sleep(0.5)
set_winsize(fd, 24, 30)                      # 输入到一半缩窄窗口
show("D resize 到 30 列（输入框里有半行中文）", read_for(fd, 1.5))
set_winsize(fd, 24, 100)
show("E resize 到 100 列", read_for(fd, 1.5))

os.write(fd, b"\x15")                        # Ctrl+U 清行
os.write(fd, b"!sleep 3\n")
time.sleep(0.8)
os.write(fd, "agent 干活时打的字\n".encode())          # 干活期间打字 —— 去哪了？
show("F !sleep 3 期间打字", read_for(fd, 6.0))

os.write(fd, b"\x04")                        # Ctrl+D
show("G Ctrl+D", read_for(fd, 2.0))
try: os.waitpid(pid, 0)
except ChildProcessError: pass
