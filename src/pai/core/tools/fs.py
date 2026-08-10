"""文件系统三件套：read / write / edit。edit 采用唯一精确替换（学 pi 的 edit 语义）。

写入一律**原子**：临时文件 + `os.replace`。理由不是洁癖——`open(path, "w")` 是
**先截断后写入**，进程若死在这两步之间（kill -9 / OOM / 断电），留下的是空文件或半截文件。
`edit_file` 尤其危险：它把原内容读进内存后同样要截断重写，**那一瞬间原文只存在于内存里**。
原子写把任何时刻的中断都收敛成两种结果：旧的完好，或新的完整。
"""

import os
import re
import tempfile
from typing import Annotated

from pai.core.boundary import get_paths_for_permission_check
from pai.core.tools import READ, WRITE, MatchContext, matcher_for, path_access_for, tool

MAX_OUTPUT_CHARS = 4000


def _atomic_write(path: str, content: str) -> None:
    """同目录临时文件 + os.replace（POSIX 上是原子改名）。

    临时文件必须与目标**同目录**：跨文件系统 rename 不是原子的，会退化成拷贝。
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".pai-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)   # 别把权限/可执行位弄丢
        os.replace(tmp, path)
    except BaseException:
        # 失败路径不留垃圾——半截的临时文件比没有更让人困惑
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@tool
def read_file(path: Annotated[str, "要读取的文件路径（相对或绝对）"]) -> str:
    """读取一个文件的全部内容。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content:
        return "(文件为空)"
    if len(content) > MAX_OUTPUT_CHARS:
        return content[:MAX_OUTPUT_CHARS] + f"\n\n[... 截断，共 {len(content)} 字符]"
    return content


@tool
def write_file(
    path: Annotated[str, "要写入的文件路径"],
    content: Annotated[str, "写入的完整内容（会覆盖原文件）"],
) -> str:
    """把内容写入文件（覆盖式，文件不存在则创建）。"""
    _atomic_write(path, content)
    return f"已写入 {path}（{len(content)} 字符）"


@tool
def edit_file(
    path: Annotated[str, "要编辑的文件路径"],
    old: Annotated[str, "要被替换的原文本，必须在文件中唯一出现一次"],
    new: Annotated[str, "替换后的新文本"],
) -> str:
    """精确替换文件中的一段文本：old 必须在文件中唯一出现一次。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    count = content.count(old)
    if count == 0:
        return f"错误：在 {path} 中找不到要替换的文本。请先 read_file 确认原文。"
    if count > 1:
        return f"错误：该文本在 {path} 中出现了 {count} 次，不唯一。请把 old 加长、带上下文以保证唯一。"
    _atomic_write(path, content.replace(old, new))
    return f"已在 {path} 中完成 1 处替换。"


# ---- 权限匹配（feature 07 Task 4）----
#
# 四种前缀四种含义，其中单斜杠那条是官方自己标注的最大的坑：
#
#   //path   文件系统绝对路径
#   ~/path   主目录
#   /path    **锚到写下这条规则的设置文件**——用户设置里的 /secrets/** 是
#            ~/.pai/secrets/**，不是项目里的 secrets/。以为它是文件系统根就错了。
#   path     含 `/` 则相对 cwd；不含 `/` 的裸文件名按 gitignore 语义任意深度匹配
#            （`read_file(.env)` ≡ `read_file(**/.env)`）。
#
# **符号链接双路径已实现**（feature 09 Task 4，关掉了 feature 07 的那个洞）：
# allow 要求「给定路径与真实路径都干净」、deny/ask「任一脏就拦」——
# 靠的就是 require_all，无需给匹配器加新参数。


def _glob_to_regex(pattern: str):
    """把 glob 编译成正则。**单星不跨 `/`**——跨了的话 allow 规则会悄悄放宽一层目录。"""
    out = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:[^/]*/)*")       # 任意层目录，含零层
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def expand_pattern(specifier: str, ctx: MatchContext) -> str:
    """把带前缀的 specifier 展开成一条绝对（或 `**/` 打头）的 glob（纯函数，单独可测）。"""
    p = specifier.strip()
    if p.startswith("//"):
        return "/" + p[2:].lstrip("/")
    if p.startswith("~/"):
        return os.path.join(ctx.home or os.path.expanduser("~"), p[2:])
    if p.startswith("/"):
        return os.path.join(ctx.anchor or ctx.cwd, p[1:])
    if "/" not in p:
        return "**/" + p
    return os.path.join(ctx.cwd, p[2:] if p.startswith("./") else p)


def target_path(args: dict, ctx: MatchContext) -> str:
    """取工具参数里的路径并绝对化（**不** realpath——展开成双路径是调用方的事）。"""
    value = str(next(iter(args.values()), ""))
    if not value:
        return ""
    if not os.path.isabs(value):
        value = os.path.join(ctx.cwd or os.getcwd(), value)
    return os.path.normpath(value)


def path_matcher(specifier: str, args: dict, require_all: bool, ctx: MatchContext) -> bool:
    """fs 三件套共用的路径匹配，**对符号链接的两条路径分别比对**（feature 09 Task 4）。

    `require_all` 在这里终于有了意义，且与 bash 那边是同一条不对称：
    - allow 判定（True）：**两条都干净**才放行——名字在 `src/` 下、真身在界外的软链
      不该被 `allow=["read_file(/src/**)"]` 放行；
    - deny/ask 判定（False）：**任一条脏**就拦。

    这正是官方符号链接规则的原话，也是 feature 07 spec 里
    「与官方符号链接规则的不对称是同一个思想」那句话的兑现。
    """
    paths = get_paths_for_permission_check(target_path(args, ctx))
    if not paths:
        return False
    pattern = _glob_to_regex(expand_pattern(specifier, ctx))
    hits = [bool(pattern.match(p)) for p in paths]
    return all(hits) if require_all else any(hits)


for _fs_tool in (read_file, write_file, edit_file):
    matcher_for(_fs_tool)(path_matcher)


# 目录边界的两项声明（feature 09 Task 1）。取的是**声明的那个参数**而不是
# 「第一个参数」——三件套碰巧都是 path 打头，写成「取第一个」在加第四个工具时会静默出错。
path_access_for(read_file, READ)(lambda args: str(args.get("path") or ""))
for _writer in (write_file, edit_file):
    path_access_for(_writer, WRITE)(lambda args: str(args.get("path") or ""))
