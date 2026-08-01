"""bash 工具。阶段 3 会在这前面挂权限钩子（危险模式拦截）。"""

import subprocess
from typing import Annotated

from pai.tools import tool

MAX_OUTPUT_CHARS = 4000


@tool
def bash(command: Annotated[str, "要执行的 shell 命令"]) -> str:
    """在 shell 里执行一条命令并返回它的输出（stdout+stderr）。"""
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    output = (proc.stdout or "") + (proc.stderr or "")
    if not output:
        return f"(命令没有输出，退出码 {proc.returncode})"
    if len(output) > MAX_OUTPUT_CHARS:
        return output[:MAX_OUTPUT_CHARS] + f"\n\n[... 截断，共 {len(output)} 字符]"
    return output
