"""bash 工具。阶段 4 会在这前面挂权限钩子（危险模式拦截）。

跑的是**独立进程组**（start_new_session）而不是直接 subprocess.run，为的是能整组收掉：
`sleep 30 & ...` 派生的孙进程不在直接子进程里，只 kill 子进程它会活下来继续烧机器
（tests/test_tools.py::test_bash_kills_whole_process_group_not_just_the_child 钉死这条）。
代价是命令拿不到终端的 SIGINT——所以中断必须由 pai 自己发（见 pai.core.interrupt）。
"""

import os
import signal
import subprocess
import time
from typing import Annotated, Optional, Tuple

from pai.core import interrupt
from pai.core.tools import tool

MAX_OUTPUT_CHARS = 4000
TIMEOUT_SECONDS = 60
POLL_SECONDS = 0.1          # 中断响应粒度；再小只是空转，再大用户会觉得 Ctrl+C 没反应


def _text(x) -> str:
    # TimeoutExpired 挂载的输出在部分 Python 版本里是 bytes，text=True 也不例外
    if isinstance(x, (bytes, bytearray)):
        return x.decode(errors="replace")
    return x or ""


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()             # 组已消失或没权限，至少收掉直接子进程


def _kill_and_collect(proc: subprocess.Popen, note: str) -> str:
    """杀整组后把已产出的输出收回来。

    抹掉部分输出会让模型看到「零输出」而误判重试（R3#3 实测复现）——
    杀掉写端之后 communicate 才能读到 EOF，所以顺序是先杀后收，不能反。
    """
    _kill_group(proc)
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        out, err = "", ""       # SIGKILL 之后还收不到 EOF 只能放弃，不能挂死工具
    partial = _text(out) + _text(err)
    return f"{partial}\n{note}" if partial.strip() else note


def _wait(proc: subprocess.Popen) -> Tuple[Optional[str], Optional[str]]:
    """轮询等待，期间响应中断与超时；命中则抛 _Killed 带上要回给模型的话。"""
    flag = interrupt.current()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while True:
        try:
            return proc.communicate(timeout=POLL_SECONDS)
        except subprocess.TimeoutExpired:
            pass                # 只是这一轮轮询到点，不是命令超时
        if flag.is_set():
            raise _Killed(_kill_and_collect(proc, "(已中断，命令与其整个进程组已被终止)"))
        if time.monotonic() >= deadline:
            raise _Killed(_kill_and_collect(
                proc, f"(命令超时 {TIMEOUT_SECONDS}s，命令与其整个进程组已被终止)"))


class _Killed(Exception):
    """内部控制流：把「已经组织好给模型的话」带出轮询循环。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@tool
def bash(command: Annotated[str, "要执行的 shell 命令"]) -> str:
    """在 shell 里执行一条命令并返回它的输出（stdout+stderr）。"""
    if interrupt.current().is_set():
        # 已经中断了还去起进程纯属浪费——正常路径下 loop 根本不会走到这里（它会
        # 直接回填「已取消」），这是防御性的第二道
        return "(已中断，命令未执行)"

    proc = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        out, err = _wait(proc)
    except _Killed as killed:
        return killed.message

    output = _text(out) + _text(err)
    if not output:
        return f"(命令没有输出，退出码 {proc.returncode})"
    if len(output) > MAX_OUTPUT_CHARS:
        return output[:MAX_OUTPUT_CHARS] + f"\n\n[... 截断，共 {len(output)} 字符]"
    return output
