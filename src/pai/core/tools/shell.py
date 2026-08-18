"""bash 工具。阶段 4 会在这前面挂权限钩子（危险模式拦截）。

跑的是**独立进程组**（start_new_session）而不是直接 subprocess.run，为的是能整组收掉：
`sleep 30 & ...` 派生的孙进程不在直接子进程里，只 kill 子进程它会活下来继续烧机器
（tests/test_tools.py::test_bash_kills_whole_process_group_not_just_the_child 钉死这条）。
代价是命令拿不到终端的 SIGINT——所以中断必须由 pai 自己发（见 pai.core.interrupt）。
"""

import fnmatch
import os
import re
import signal
import subprocess
import time
from typing import Annotated, Optional, Tuple

from pai.core import interrupt
from pai.core.tools import matcher_for, tool

MAX_OUTPUT_CHARS = 4000
# 默认 120s：**不是拍脑袋，是两家独立收敛的结果**——CC（`timeouts.ts` 的
# DEFAULT_TIMEOUT_MS）与 dsh（`bash-local` 的 timeoutMs）各自定在 120s，
# 上限各自定在 600s。原先的 60s 扛不住一次完整测试跑（本仓库自己就要 106s）
# 或 `npm install`，撞墙时模型只能干等一分钟再失败一次。
# 上限与「模型自己传 timeout」尚未做，见 TODO「工具调用超时」。
TIMEOUT_SECONDS = 120
# 上限与默认值同源：CC 与 dsh 各自把上限定在 600s。模型可以传更大的数，
# 但**运行期真钳制**——CC 恰恰是反面教材：它 schema 描述里写了 max 却只有
# `timeout || default`，一个 Math.min 都没有，上限纯属君子协定。
MAX_TIMEOUT_SECONDS = 600
POLL_SECONDS = 0.1          # 中断响应粒度；再小只是空转，再大用户会觉得 Ctrl+C 没反应

# 我们起过的进程组，退出时统一收割。
# 为什么需要它：start_new_session 让命令脱离 pai 的进程组（那是能整组 killpg 的前提），
# 代价就是 pai 死了它们不跟着死——`!sleep 300 &` 会在你关掉 pai 之后继续占着机器。
# 对齐官方行为：「当 Claude Code 退出时，后台任务会自动清理」。
# 诚实边界：① `kill -9 pai` 时这段代码没机会跑，任何进程内方案都救不了；
# ② 登记的是 pgid，理论上存在「组早已结束、pgid 被系统重用」后误杀的窗口——
# 真实风险低（macOS pid 空间大、回绕慢）但不为零，记 TODO 而不是假装没有。
_SPAWNED_GROUPS: set = set()


def clamp_timeout(requested: int) -> int:
    """把模型传来的秒数收进 [1, MAX]；`0` 是「没传」的哨兵，退回默认值。

    用哨兵而不是 `None`：`@tool` 的 schema 生成器只认 str/int/float/bool
    （`PY_TO_JSON`），`Optional[int]` 会被它当场拒掉。改装饰器是动
    「schema 与代码同源」那块基石，为一个参数不值当。
    """
    if not requested:
        return TIMEOUT_SECONDS
    return min(int(requested), MAX_TIMEOUT_SECONDS)


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


def _wait(proc: subprocess.Popen, seconds: int) -> Tuple[Optional[str], Optional[str]]:
    """轮询等待，期间响应中断与超时；命中则抛 _Killed 带上要回给模型的话。

    秒数由调用方算好传进来（而不是在这里读模块全局）——模型可以传 timeout，
    「生效的那个值」必须只有一个来源，否则文案报的与实际用的会各说各话。
    """
    flag = interrupt.current()
    deadline = time.monotonic() + seconds
    while True:
        try:
            return proc.communicate(timeout=POLL_SECONDS)
        except subprocess.TimeoutExpired:
            pass                # 只是这一轮轮询到点，不是命令超时
        if flag.is_set():
            raise _Killed(_kill_and_collect(proc, "(已中断，命令与其整个进程组已被终止)"))
        if time.monotonic() >= deadline:
            # **给模型一条出路**：只说「杀了」的文案会让它原样重试、再撞一次同样的墙。
            # 三家都在这个语境里给下一步（dsh 把 run_in_background 写进工具描述、
            # CC 的 ripgrep 超时说「换更具体的路径或 pattern」）。pai 没有后台任务
            # 机制，所以给的是穷人版：起到后台 + 分次读日志。
            # 这段话只挂在超时上，**不挂在中断上**——中断是用户主动喊停，
            # 给它出路等于劝模型绕过用户（test_interrupt_message_does_not_offer_the_timeout_way_out）。
            raise _Killed(_kill_and_collect(
                proc,
                f"(命令超时 {seconds}s，命令与其整个进程组已被终止。"
                f"若这条命令本来就需要跑更久：拆成几段分别执行，"
                f"或改写成 `nohup 原命令 > /tmp/out.log 2>&1 &` 起到后台，"
                f"再用 read_file 分次查看 /tmp/out.log)"))


class _Killed(Exception):
    """内部控制流：把「已经组织好给模型的话」带出轮询循环。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@tool
def bash(
    command: Annotated[str, "要执行的 shell 命令"],
    timeout: Annotated[
        int,
        f"可选：超时秒数。不传用默认 {TIMEOUT_SECONDS}s；超过上限 {MAX_TIMEOUT_SECONDS}s "
        f"会被截到上限。命令确实要跑更久就起到后台，别指望调大这个数。",
    ] = 0,
) -> str:
    """在 shell 里执行一条命令并返回它的输出（stdout+stderr）。"""
    if timeout < 0:
        # 静默改用默认值 = 模型永远不知道自己传错了（「静默失败是 bug」）
        return f"错误：timeout 不能是负数（收到 {timeout}），命令未执行。"
    seconds = clamp_timeout(timeout)
    if interrupt.current().is_set():
        # 已经中断了还去起进程纯属浪费——正常路径下 loop 根本不会走到这里（它会
        # 直接回填「已取消」），这是防御性的第二道
        return "(已中断，命令未执行)"

    proc = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        _SPAWNED_GROUPS.add(os.getpgid(proc.pid))
    except ProcessLookupError:
        pass                    # 秒退的命令，组已经没了，本来也不用收割
    try:
        out, err = _wait(proc, seconds)
    except _Killed as killed:
        return killed.message

    output = _text(out) + _text(err)
    if not output:
        return f"(命令没有输出，退出码 {proc.returncode})"
    if len(output) > MAX_OUTPUT_CHARS:
        return output[:MAX_OUTPUT_CHARS] + f"\n\n[... 截断，共 {len(output)} 字符]"
    return output


# ---- 权限匹配（feature 07 Task 3）----
#
# 这一段是「权限系统是不是纸糊的」的分水岭。核心是一条不对称：
# allow 要求**每个子命令都匹配**，deny/ask 是**任一子命令命中**即算。
# 少了它，`allow=["Bash(ls *)"]` 会把 `ls && rm -rf /` 整条放行——
# 规则看着写了，实际等于没写。
#
# 匹配是**前缀 + 词边界**，不是子串：这挡得住手滑，挡不住对抗。
# 官方原话是「基于前缀的匹配防不住刻意绕过」，pai 照抄这个边界，不吹自己更强。

# 拆分：`&&` `||` `;` `|` `|&` `&` 换行。多字符的要排在单字符前面，
# 否则 `|&` 会先被 `|` 吃掉半个。
_SEPARATORS = re.compile(r"\|\||&&|\|&|[;|&\n]")

# **进程包装器**：原样跑后面那条命令，剥掉不改变语义。
PROCESS_WRAPPERS = ("timeout", "time", "nice", "nohup", "stdbuf", "xargs")

# **环境运行器**（`npx` / `docker exec` / `devbox run` …）明确**不剥**。
# 剥了等于承认「借个壳就能跑任意命令」；不剥的代价是官方也认的那个洞：
# `Bash(devbox run *)` 会放行 `devbox run rm -rf .`。两害相权取其轻，
# 并且用 test_env_runners_are_not_stripped_and_this_is_a_known_hole 把它钉在明面上。

_DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")


def split_commands(command: str) -> list:
    """按 shell 分隔符拆成子命令列表（纯函数，单独可测）。"""
    return [part.strip() for part in _SEPARATORS.split(command) if part.strip()]


def strip_wrappers(command: str) -> str:
    """剥掉不改变语义的进程包装器（纯函数，单独可测）。

    **带标志就不剥**：`xargs -n1 npm test` 的语义已经不是「原样跑 npm test」了，
    再剥就是把一条没审过的命令当成审过的。
    """
    tokens = command.split()
    while len(tokens) >= 2 and tokens[0] in PROCESS_WRAPPERS:
        head, rest = tokens[0], tokens[1:]
        if rest[0].startswith("-"):
            break
        # timeout 的时长是位置参数，不是标志，得跟着一起剥
        if head == "timeout" and len(rest) >= 2 and _DURATION.match(rest[0]):
            rest = rest[1:]
        tokens = rest
    return " ".join(tokens)


def match_one(specifier: str, command: str) -> bool:
    """单条子命令是否命中 specifier（纯函数，单独可测）。

    尾部 ` *` 与 `:*`（仅在模式末尾）等价，都表示**前缀 + 词边界**匹配：
    `ls *` 匹配 `ls` 与 `ls -la`，但不匹配 `lsof`。
    不带空格的 `ls*` 退回朴素通配，`lsof` 也算匹配——两种写法的区别是故意保留的。
    """
    pattern = specifier.strip()
    prefix = None
    if pattern.endswith(":*"):
        prefix = pattern[:-2].strip()
    elif pattern.endswith(" *"):
        prefix = pattern[:-2].strip()
    if prefix:
        return command == prefix or command.startswith(prefix + " ")
    return fnmatch.fnmatchcase(command, pattern)


@matcher_for(bash)
def bash_matcher(specifier: str, args: dict, require_all: bool, ctx) -> bool:
    """bash 的权限匹配：拆复合命令 → 剥包装器 → 逐条比对。

    `require_all` 由权限层按桶传：allow 传 True，deny/ask 传 False。
    `ctx`（路径锚点）用不上——shell 命令里的路径要不要管是 fs 工具的事。
    """
    parts = [strip_wrappers(p) for p in split_commands(str(args.get("command", "")))]
    if not parts:
        return False
    if require_all:
        return all(match_one(specifier, p) for p in parts)
    return any(match_one(specifier, p) for p in parts)


def reap_spawned() -> None:
    """收割本进程起过的所有命令进程组。装配层在退出时调用（见 pai.cli）。

    不在**命令返回时**收割，因为「命令返回」与「它派生的后台进程结束」是两件事——
    `sleep 300 &` 的父 shell 立刻就退了，要留到进程真的走人时才清。
    """
    while _SPAWNED_GROUPS:
        pgid = _SPAWNED_GROUPS.pop()
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass                # 组早没了 / 没权限：收割是尽力而为，绝不因此报错
