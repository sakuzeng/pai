"""挂死变红：给每条测试装一个 SIGALRM 兜底。

**这是测试基建自己的安全带。** `./test.sh` 在 2026-08-13 与 2026-08-18 各挂死
过一次（pty e2e 的父子退出竞态，父 pytest 阻塞着持有 `/dev/ptmx`），两次都是
人工 `kill` 才停。危害不在慢，在于**它不红也不超时**：CI 里表现成「一直在跑」，
本地表现成「我的改动把测试跑挂了」，两种都会把人引到错误的方向。

**为什么不引 pytest-timeout**：一个依赖换十几行不划算，而且本仓库目标平台
就是 macOS/Linux（`signal.SIGALRM` 在两边都有）。没有 SIGALRM 的平台上本模块
自动退化成空操作——**退化是无声的，但那条平台本来也跑不了 pty e2e**。

**诚实边界**：信号只送得进主线程，且卡在不可中断的系统调用里（`ps` STAT=`U`）
时送不进去。实测的那两次挂死里，父 pytest 处于可中断睡眠（STAT=`S`），
所以这张网兜得住——但它兜的是「父进程还在等」，不是所有形态的挂死。
"""

import signal

import pytest

# 60s 的依据：本仓库最慢的单条测试是 pty e2e，实测约 4s（19 条共 78s）；
# 整套 111s。给单条留 60s 是「绝不误伤正常测试」与「挂死别等太久」之间的取舍。
DEFAULT_TIMEOUT_SECONDS = 60


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "timeout_seconds(n): 这条测试的挂死预算（秒），默认 60；0 表示不设")


@pytest.fixture(autouse=True)
def hang_becomes_red(request):
    marker = request.node.get_closest_marker("timeout_seconds")
    seconds = int(marker.args[0]) if marker and marker.args else DEFAULT_TIMEOUT_SECONDS
    if not hasattr(signal, "SIGALRM") or seconds <= 0:
        yield
        return

    def _blow_up(signum, frame):
        raise TimeoutError(
            f"这条测试超过 {seconds}s 仍未结束——按挂死处理（tests/pai_test_timeout.py）。"
            "若它本来就该跑这么久，用 @pytest.mark.timeout_seconds(n) 单独加预算。")

    previous = signal.signal(signal.SIGALRM, _blow_up)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        # 顺序不能反：先撤定时器再还原处理器，否则中间那一瞬的信号会打到旧处理器上
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
