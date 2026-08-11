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
read_for(fd, 2.0)
os.write(fd, "半行中文没回车".encode()); time.sleep(0.5)
show("D0 打了半行（未回车）", read_for(fd, 0.8))
set_winsize(fd, 24, 30)
show("D resize 80→30 列（输入框里有半行中文）", read_for(fd, 1.5))
set_winsize(fd, 24, 100)
show("E resize 30→100 列", read_for(fd, 1.5))
os.write(fd, b"\x15")
os.write(fd, b"!sleep 3\n"); time.sleep(0.8)
os.write(fd, "干活时打的字".encode())   # 刻意不带回车：不提交给模型，也能看清它去了哪
show("F !sleep 3 期间打字（无回车）", read_for(fd, 6.0))
os.write(fd, b"\x15")
os.write(fd, b"\x04")
show("G Ctrl+D", read_for(fd, 2.0))
read_for(fd, 1.0)
os.kill(pid, 9)
try: os.waitpid(pid, 0)
except ChildProcessError: pass
