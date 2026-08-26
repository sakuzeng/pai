"""`git_read` 工具（feature 42 Task 3）：只读的 git 子命令。

形状是拍板问 2·A：一个工具 + 子命令白名单，argv 由 pai 自己拼、**不过 shell**。
这一条是本模块的核心，值得说清它买到了什么：bash 那边靠拆分隔符 + 剥包装器
来判断「这条命令里有没有夹带」，那套挡得住手滑、挡不住 `$(...)` 与变量拼接
（`shell.py` 里写着「官方原话是基于前缀的匹配防不住刻意绕过」）。
argv 直传则连「有第二条命令」这个概念都不存在——`git status; rm -rf x`
在这里是三个被当成 pathspec 的字符串，不是一条要被拦下的命令。

flag 用**白名单**而不是黑名单（对拍板的一处收紧，记在档案 42）：
黑名单的失效方向是「漏写一个 → 放行一个洞」，白名单是「漏写一个 → 拒掉一个
合法 flag，模型收到一句话就能改」。与「判不出来就当不安全」同一条 doctrine。

写操作（add / commit / push / reset / checkout）一律不进白名单，仍走 bash 的 ask
——与 AGENTS「永远不要未经要求就 commit」一致。这条边界是故意画在这里的：
读 git 是理解代码的一部分，写 git 是改变仓库历史，两者该有不同的门。
"""

import os
import shlex
from typing import Annotated, List

from pai.core.tools import EXEC, capabilities_for, matcher_for, path_access_for, tool
from pai.core.tools.fs import path_matcher
from pai.core.tools.output import MAX_OUTPUT_CHARS, head_and_tail
from pai.core.tools.shell import Killed, run_process

# git 自己不快时（大仓 log、大 diff）也不该等太久；它不是测试，没有长跑的理由。
TIMEOUT_SECONDS = 60

# 吃 diff 选项的三个子命令要显式关掉外部 diff 驱动：仓库的 .gitattributes /
# config 能配 `diff.<name>.command`，那是一条「读一个仓库就跑到别人的程序」的路。
_DIFF_FAMILY = ("diff", "show", "log")

# 子命令 → 允许的 flag。名单不长是故意的：常用的都在，剩下的让模型收到
# 一句「允许的是这些」再改一次，比放开一个说不清后果的 flag 划算。
# 带值的写法（`--unified=3`）按 `=` 前那半比对，所以表里只写 flag 名。
SAFE_SUBCOMMANDS = {
    "status": {"-s", "--short", "-b", "--branch", "--long", "--porcelain"},
    "diff": {"--stat", "--numstat", "--shortstat", "--name-only", "--name-status",
             "--cached", "--staged", "-w", "--ignore-all-space", "-U", "--unified"},
    "log": {"--oneline", "--stat", "--name-only", "--name-status", "--graph",
            "--no-merges", "-n", "--max-count", "--format", "--pretty",
            "--author", "--since", "--until", "--reverse", "--follow"},
    "show": {"--stat", "--name-only", "--name-status", "--oneline",
             "--format", "--pretty"},
    "branch": {"-a", "--all", "-v", "--verbose", "-r", "--remotes",
               "--list", "--show-current"},
    "blame": {"-L", "-w", "--line-porcelain"},
    "ls-files": {"--cached", "--others", "--modified", "--deleted",
                 "--exclude-standard", "-s", "--stage"},
}

# 纯读、不碰索引的子命令。其余（status / diff）会刷新索引并要拿
# `.git/index.lock`，两个并发跑会撞锁——所以并发安全性**取决于这次跑的是哪个**。
PURE_READ_SUBCOMMANDS = frozenset({"log", "show", "branch", "blame", "ls-files"})


class Rejected(Exception):
    """参数没过白名单。带着已经组织好的、能让模型一步改对的话。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def build_argv(subcommand: str, args: str) -> List[str]:
    """把 (子命令, 参数串) 拼成 argv。纯函数，单独可测；不合规抛 `Rejected`。

    `--no-pager` 必须在子命令**之前**——它是全局 flag，放后面 git 不认。
    （管道下 git 本来也不分页，但依赖「它会自己判断」等于把行为交给环境。）
    """
    sub = (subcommand or "").strip()
    if sub not in SAFE_SUBCOMMANDS:
        raise Rejected(
            f"错误：`git {sub or '(空)'}` 不在只读白名单里。"
            f"可用的是：{'、'.join(sorted(SAFE_SUBCOMMANDS))}。"
            "写操作（add/commit/push/reset/checkout）刻意不提供，"
            "确实需要时请走 bash（那条路会问你一次）。")

    try:
        tokens = shlex.split(args or "")
    except ValueError as e:
        # 引号不闭合是模型的常见手滑，报出来它才改得动
        return _raise_bad_args(sub, f"参数解析失败（{e}）")

    allowed = SAFE_SUBCOMMANDS[sub]
    for token in tokens:
        if not token.startswith("-"):
            continue                        # pathspec / ref：交给 git 自己判
        name = token.split("=", 1)[0]
        if name not in allowed:
            raise Rejected(
                f"错误：`{token}` 不在 `git {sub}` 允许的选项里。"
                f"允许的是：{'、'.join(sorted(allowed))}。"
                "（能改 git 配置或换目标仓库的选项一律不放行，"
                "如 -c / -C / --git-dir / --exec-path / --output。）")

    argv = ["git", "--no-pager", sub]
    if sub in _DIFF_FAMILY:
        argv.append("--no-ext-diff")
    return argv + tokens


def _raise_bad_args(sub: str, why: str):
    raise Rejected(f"错误：`git {sub}` 的参数不合法：{why}。")


def repo_root(args: dict) -> str:
    """git 在哪跑。这个工具刻意**没有** path 参数（`-C` 也在拒绝名单里），
    所以永远是当前工作目录——权限层判的就是这一个路径。"""
    return os.path.abspath(os.getcwd())


@tool
def git_read(
    subcommand: Annotated[
        str,
        "只读的 git 子命令：status / diff / log / show / branch / blame / ls-files"],
    args: Annotated[str, "可选：该子命令的参数，如 `--oneline -n 10` 或 `-- src/x.py`"] = "",
) -> str:
    """跑一条只读的 git 命令（status/diff/log/show/branch/blame/ls-files）。"""
    try:
        argv = build_argv(subcommand, args)
    except Rejected as r:
        return r.message

    root = repo_root({})
    try:
        output, returncode = run_process(argv, TIMEOUT_SECONDS, cwd=root, shell=False)
    except Killed as killed:
        return killed.message
    except OSError as e:
        # git 没装 / 不可执行：这不是「命令失败」，是环境缺东西，说清楚
        return f"错误：起不来 git（{type(e).__name__}: {e}）。"

    if not output.strip():
        return f"(没有输出，退出码 {returncode})"
    # 保头保尾：`git log` / `git diff` 长起来同样是结论在两头（同 run_tests）
    return f"{head_and_tail(output, MAX_OUTPUT_CHARS)}\n[退出码 {returncode}]"


# ---- 接线 ----


@matcher_for(git_read)
def git_read_matcher(specifier: str, args: dict, require_all: bool, ctx) -> bool:
    """复用 fs 的路径匹配，比对的是仓库根（同 search / run_tests）。

    不挂的话吃 `default_matcher`——它比对**第一个参数值**，这里是 subcommand，
    于是路径 specifier 会拿 `"status"` 去比对，静默永不命中。
    裸名规则（`deny=["git_read"]`）不经 matcher，任何时候都能一刀关掉。
    """
    return path_matcher(specifier, {"path": repo_root(args)}, require_all, ctx)


path_access_for(git_read, EXEC)(repo_root)

# **能力标志收 input 的第一个真实用户**（`Capability` 的签名早就留着这一手，
# 注释里写的「pai 今天还没有这样的工具」到本轮为止成立）。
# 静态布尔在这里表达不了：全 True 会让两个 `git status` 并发去抢
# `.git/index.lock`，全 False 则白白放掉 `git log` 这类真能并发的。
capabilities_for(
    git_read,
    read_only=True,                         # 七个子命令都不改仓库内容
    concurrency_safe=lambda args: str(args.get("subcommand") or "") in PURE_READ_SUBCOMMANDS,
)
