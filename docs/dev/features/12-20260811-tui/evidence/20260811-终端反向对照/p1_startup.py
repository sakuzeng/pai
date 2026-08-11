import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import spawn, drain, show, set_winsize
pid, fd = spawn(24, 80)
show("启动后 80 列", drain(fd, 3.0))
os.write(fd, b"/help\n"); show("/help", drain(fd, 2.0))
os.write(fd, b"/exit\n"); show("/exit", drain(fd, 2.0))
os.waitpid(pid, 0)
