import os, sys, time, select
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import spawn, set_winsize
def drain(fd, secs):
    t0=time.time()
    while time.time()-t0<secs:
        r,_,_=select.select([fd],[],[],0.2)
        if r:
            try:
                if not os.read(fd,65536): break
            except OSError: break
os.environ["PAI_TUI_RECORD"] = "/tmp/pai_rec.jsonl"
pid, fd = spawn(22, 92)
drain(fd, 3.0)
os.write(fd, b"/help\r"); drain(fd, 1.2)          # 命令，不打模型
os.write(fd, b"\x1b[Z"); drain(fd, 0.8)           # shift+tab 切模式
os.write(fd, b"!echo hello && echo world\r"); drain(fd, 1.5)   # shell，不打模型
os.write(fd, "中文输入测试".encode()); drain(fd, 0.8)          # 只打字，不回车
os.write(fd, b"\x04"); drain(fd, 1.5)
try: os.waitpid(pid, 0)
except ChildProcessError: pass
print("recorded:", os.path.getsize("/tmp/pai_rec.jsonl"), "bytes")
