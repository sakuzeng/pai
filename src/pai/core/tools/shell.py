"""bash 工具。阶段 3 会在这前面挂权限钩子（危险模式拦截）。"""

import subprocess
from typing import Annotated

from pai.core.tools import tool

MAX_OUTPUT_CHARS = 4000
TIMEOUT_SECONDS = 60


def _text(x) -> str:
    # TimeoutExpired 挂载的输出在部分 Python 版本里是 bytes，text=True 也不例外
    if isinstance(x, (bytes, bytearray)):
        return x.decode(errors="replace")
    return x or ""


@tool
def bash(command: Annotated[str, "要执行的 shell 命令"]) -> str:
    """在 shell 里执行一条命令并返回它的输出（stdout+stderr）。"""
    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as e:
        # 后台进程占住管道会白等到超时，但已产出的输出就挂在异常对象上——
        # 抹掉它，模型只看到「超时零输出」，必然误判重试（R3#3，实测复现）
        partial = _text(e.stdout) + _text(e.stderr)
        note = f"(命令超时 {TIMEOUT_SECONDS}s 被终止——若含后台进程，它可能仍在运行)"
        return f"{partial}\n{note}" if partial.strip() else note
    output = (proc.stdout or "") + (proc.stderr or "")
    if not output:
        return f"(命令没有输出，退出码 {proc.returncode})"
    if len(output) > MAX_OUTPUT_CHARS:
        return output[:MAX_OUTPUT_CHARS] + f"\n\n[... 截断，共 {len(output)} 字符]"
    return output
