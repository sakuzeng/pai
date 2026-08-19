"""收割 pty 子进程：有界等待，不裸 `waitpid` 死等。

**先说清这不是什么**：本文件**没有**复现、也**没有**修掉 `./test.sh` 那条
间歇性挂死（2026-08-13、2026-08-18 各一次）。**根因至今未确诊。**

曾经的推断是「子进程卡在往 pty 写（缓冲区满、父进程不读了），父进程卡在
`waitpid`，两边互等」，三个观测看起来能对上（父进程持有 `/dev/ptmx`、
fake_provider 端口仍 LISTEN 而 teardown 顺序里 close 排在 provider.stop 前面、
装上测试级超时后那条被报成 ERROR 即抛在 teardown 里）。
**但这个推断实测站不住**：下面第一条测试构造了「子进程猛写 pty 写到缓冲区满」，
裸 `waitpid` 照样收得掉——`SIGKILL` 本来就能杀掉阻塞在 pty 写上的进程。
（这条纠正本身是注入反证抓出来的：换回旧实现，测试**不红**。）

所以留在这里的是**防御性硬化**而不是修复：把无界等待换成有界等待。
理由是这个测试基建的失败模式就是「挂住」，无界等待在这里没有存在价值。
下面两条测试如实只钉它们真钉得住的东西——**别把它们当成那条挂死的守卫**。
"""

import os
import pty
import time

from test_e2e_tui import reap_pty_child


def test_reaping_cleans_up_a_child_that_is_busy_writing():
    """子进程正在猛写 pty 时，收割要收得干净、不留僵尸。

    诚实边界：这条**在修改前也是绿的**（`SIGKILL` 能杀掉阻塞在写上的进程）。
    它钉的是「收割器在真实形态下工作正常」，**不是**「死锁被修好了」。
    """
    pid, fd = pty.fork()
    if pid == 0:                                  # 子进程：拼命写，永不退出
        try:
            while True:
                os.write(1, b"x" * 4096)
        except BaseException:
            pass
        os._exit(0)

    time.sleep(0.3)                               # 让它把 pty 缓冲区写满
    reap_pty_child(pid, fd, timeout=5.0)
    os.close(fd)

    try:
        os.waitpid(pid, os.WNOHANG)
        reaped = False
    except ChildProcessError:
        reaped = True
    assert reaped, "子进程没被收割，会留成僵尸"


def test_reaping_is_bounded_even_when_the_child_never_appears():
    """**这条才是硬化本身**：收不到就在预算内返回，不许无界等下去。

    传一个不是自己子进程的 pid，`waitpid` 会抛 `ChildProcessError`；
    真正被钉住的是「函数有一条 deadline」这个结构——裸 `os.waitpid(pid, 0)`
    的版本连这条路都走不到。
    """
    pid, fd = pty.fork()
    if pid == 0:
        os._exit(0)

    time.sleep(0.2)
    start = time.monotonic()
    reap_pty_child(pid, fd, timeout=1.0)
    reap_pty_child(pid, fd, timeout=1.0)          # 第二次：已经被收走了，不许抛也不许等满
    elapsed = time.monotonic() - start
    os.close(fd)

    assert elapsed < 2.0, f"耗时 {elapsed:.1f}s——退化成死等了"
