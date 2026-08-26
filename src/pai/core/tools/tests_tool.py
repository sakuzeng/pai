"""`run_tests` 工具（feature 42 Task 2）：跑这个项目自己的测试。

为什么值得单立一个工具，而不是让模型走 bash（拍板问 1·A）。三条都是核实过的
结构性事实，不是「被问烦了」这种体感：

1. bash 默认超时 120s（`shell.TIMEOUT_SECONDS`），而本仓库全量跑 183s——
   今天就算用户点了「允许」，`bash ./test.sh` 也会在第 120 秒连同整个进程组被杀。
2. bash 的输出截断是**头部**截断，而 pytest 的判决在**尾部**：4000 字符正好
   把 `1534 passed` 那行扔掉，模型拿到一堆用例名却不知道过没过。
3. bash 结构上不参与目录边界（D#52），要靠 allow 白名单免掉询问就等于把边界
   让出去（D#76 刚拒过同族的做法）。

能自动放行的根据只有一条，也必须一直成立：**跑什么不由模型决定**。
命令来自 settings 的 `tests.command`，未配则按项目文件探测；模型能给的只有
「跑哪一部分」（`filter` / `path`）。哪天给它开了「传任意命令」的口子，
这个工具就退化成 bash 的别名，`EXEC` 那一档的放行也就失去了根据。
"""

import os
import shlex
from typing import Annotated, Optional, Tuple

from pai.core.tools import EXEC, capabilities_for, matcher_for, path_access_for, tool
from pai.core.tools.roots import path_semantics
from pai.core.tools.output import MAX_OUTPUT_CHARS, head_and_tail
from pai.core.tools.shell import Killed, run_process

# 默认超时。**这个数从哪来**（同「给照抄来的常数建一条检查习惯」那条）：
# 本仓库全量测试实测 183s，取 600s 是三倍余量；600 本身不是新数，它就是
# bash 那边 CC 与 dsh 两家收敛出的上限——「一条命令跑这么久还算合理」的公认线。
# 测试比一般命令长，所以这里取那条线的满值而不是 bash 的默认 120s。
DEFAULT_TIMEOUT_SECONDS = 600
# 上限：给大仓留的天花板，**未实测**。配得比这还大多半说明该拆测试集了。
MAX_TIMEOUT_SECONDS = 3600

# 探测表。顺序有意义：项目自己的入口脚本排最前——它比我们猜的跑法更权威
# （本仓库的 `./test.sh` 就带着「默认不打真实 API」这条花钱守卫，猜成
# `python3 -m pytest` 会把它绕过去）。
# 诚实边界：这是一张**硬编码的小表**，不认全世界。认不出来就报错指路，
# 不瞎猜——猜错的代价是跑了个不该跑的东西，比说「我不知道」糟得多。
_DETECT = (
    ("./test.sh", ("test.sh",), "项目自带的 ./test.sh"),
    ("python3 -m pytest", ("pyproject.toml", "setup.py", "setup.cfg",
                           "pytest.ini", "tox.ini", "tests"), "看起来是 Python 项目"),
    ("npm test", ("package.json",), "看起来是 Node 项目"),
    ("cargo test", ("Cargo.toml",), "看起来是 Rust 项目"),
    ("go test ./...", ("go.mod",), "看起来是 Go 项目"),
)

# 装配层注入的配置（形状照 `shell.set_default_timeout`：装配期写进来，
# 运行期现取）。None = 未配置。
_command: Optional[str] = None
_timeout: Optional[int] = None


def set_command(command: Optional[str]) -> None:
    """装配期注入 `tests.command`；传 None 显式清空（上一个装配的残留不许漂给下一个）。"""
    global _command
    _command = command


def set_timeout(seconds: Optional[int]) -> None:
    global _timeout
    _timeout = seconds


def timeout_seconds() -> int:
    return _timeout if _timeout is not None else DEFAULT_TIMEOUT_SECONDS


def resolve_command(root: str) -> Tuple[Optional[str], str]:
    """这个项目该怎么跑测试，返回 `(命令, 出处)`。纯函数，单独可测。

    出处要一起返回：模型看到 `0 passed` 时第一个该问的是「跑的是哪条命令」，
    而「这条命令是谁定的」决定了它该去改 settings 还是改测试。
    """
    if _command:
        return _command, "settings 的 tests.command"
    for command, markers, why in _DETECT:
        for marker in markers:
            if os.path.exists(os.path.join(root, marker)):
                return command, f"自动探测：{why}（{marker}）"
    return None, ""


# 这次调用真正要跑的那个根，与配套的 matcher（feature 43 抽进 `roots.py`）。
# 权限层与工具本体共用同一个 `test_root`——边界判的是它，跑也在它上面跑。
test_root, run_tests_matcher = path_semantics("path")


@tool
def run_tests(
    filter: Annotated[str, "可选：只跑名字匹配它的测试（按 pytest 的 -k 传递）"] = "",
    path: Annotated[str, "可选：只跑这个文件或目录下的测试。空 = 整个项目"] = "",
) -> str:
    """跑这个项目的测试（命令来自设置或自动探测，模型不能指定跑什么程序）。"""
    root = test_root({})                    # 边界判的是根，跑也在根上跑
    target = str(path or "")
    if target and not os.path.exists(os.path.join(root, target) if not os.path.isabs(target)
                                     else target):
        return f"错误：{target} 不存在（相对 {root}），未执行。"

    command, source = resolve_command(root)
    if not command:
        # 指路而不只报状态（同 bash 超时文案那条规矩）：说清去哪配、配什么
        return ("错误：认不出这个项目该怎么跑测试，也没有配置。"
                f"在 settings.json 里配 `tests.command`（如 "
                '`"tests": {"command": "./test.sh"}`）后再试。'
                f"（自动探测找过：{'、'.join(m for _, ms, _ in _DETECT for m in ms)}）")

    extra = []
    if filter:
        # 诚实边界：`-k` 是 pytest 的写法。`tests.command` 指向别的跑法时
        # 这个 flag 那边可能不认——已登记 TODO，不在这里假装通用。
        extra += ["-k", filter]
    if target:
        extra.append(target)
    full = command + ("".join(" " + shlex.quote(a) for a in extra) if extra else "")

    try:
        output, returncode = run_process(full, timeout_seconds(), cwd=root)
    except Killed as killed:
        return f"[跑的是 `{full}` —— {source}]\n{killed.message}"

    head = f"[跑的是 `{full}` —— {source}]"
    if not output.strip():
        return f"{head}\n(没有输出，退出码 {returncode})"
    # 保头保尾：判决在尾部（见 output.head_and_tail 的注释），这是本工具
    # 与 bash 最实质的一处差别
    return f"{head}\n{head_and_tail(output, MAX_OUTPUT_CHARS)}\n[退出码 {returncode}]"


# ---- 接线（feature 42 拍板问 3·A）----


matcher_for(run_tests)(run_tests_matcher)
path_access_for(run_tests, EXEC)(test_root)

# **显式写 False 而不是靠默认**：默认值是给「忘了声明」兜底的，而这里是
# 「想过了，结论是不行」——用户 2026-08-26 的原话是「别同时开两个 pytest，
# e2e 对时序敏感，并发跑会红得像回归」。两者行为相同，意图不同，
# 读代码的人该分得清（同 fs.py 两个写工具那段注释）。
capabilities_for(run_tests, read_only=False, concurrency_safe=False)
