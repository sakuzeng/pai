"""文件系统三件套：read / write / edit。edit 采用唯一精确替换（学 pi 的 edit 语义）。

写入一律**原子**：临时文件 + `os.replace`。理由不是洁癖——`open(path, "w")` 是
**先截断后写入**，进程若死在这两步之间（kill -9 / OOM），留下的是空文件或半截文件。
`edit_file` 尤其危险：它把原内容读进内存后同样要截断重写，**那一瞬间原文只存在于内存里**。
原子写把**进程死亡**的任何时刻收敛成两种结果：旧的完好，或新的完整。

诚实边界（R4#28）：这个承诺只到进程死亡为止，**掉电不在内**——没有 fsync，
断电时数据可能还在页缓存里，某些文件系统上 rename 的元数据先于数据落盘，
新文件可能是空壳。刻意不加：fsync 每次写都要付，而 pai 写的是代码文件，
掉电场景有 git 兜底。
"""

import os
import re
import tempfile
from typing import Annotated

from pai.core.boundary import get_paths_for_permission_check
from pai.core.tools import (
    READ,
    WRITE,
    MatchContext,
    capabilities_for,
    matcher_for,
    path_access_for,
    tool,
)

MAX_OUTPUT_CHARS = 4000


def atomic_write(path: str, content: str) -> None:
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


def _take_whole_lines(lines: list, budget: int) -> list:
    """按字符预算取整行，**至少取一行**。

    切在行中间会让「继续读用 offset=N」变成假话：那半行要么丢、要么在下一段里
    重复一遍，而两种错都不会让别的断言变红（feature 41 专门钉了一条测试）。
    至少取一行是为了单行超预算的病态文件——返回零行等于告诉模型「读完了」。
    """
    kept, size = [], 0
    for line in lines:
        if kept and size + len(line) > budget:
            break
        kept.append(line)
        size += len(line)
    return kept


@tool
def read_file(
    path: Annotated[str, "要读取的文件路径（相对或绝对）"],
    offset: Annotated[int, "可选：从第几行开始读（1 起）。0 = 从头读"] = 0,
    limit: Annotated[int, "可选：最多读几行。0 = 不限行数（仍受输出字符上限收口）"] = 0,
) -> str:
    """读取一个文件的内容，可用 offset/limit 只读其中一段（按行）。

    坐标系是**行**而不是字符（feature 41 拍板问 1）：模型定位代码时手里只有行号，
    字符坐标要它自己换算一遍。`0` 是「没传」的哨兵而不是 `None`——`@tool` 的
    schema 生成器只认 str/int/float/bool，`Optional[int]` 会被当场拒
    （同 `shell.clamp_timeout` 那条注释，那里为同一条约束用了同一个哨兵）。
    """
    if offset < 0 or limit < 0:
        # 静默改用默认值 = 模型永远不知道自己传错了（同 bash 的负 timeout）
        return f"错误：offset/limit 不能是负数（收到 offset={offset}, limit={limit}），未读取。"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content:
        return "(文件为空)"

    all_lines = content.splitlines(keepends=True)
    total_lines = len(all_lines)
    start = offset - 1 if offset > 0 else 0
    if start >= total_lines:
        # 回空串是最坏的答法：与「文件到这里就没了」无法区分，模型不知道该往回退多少
        return (f"错误：{path} 只有 {total_lines} 行，offset={offset} 已越过末尾"
                f"（全文共 {len(content)} 字符）。")

    end = total_lines if limit <= 0 else min(total_lines, start + limit)
    kept = _take_whole_lines(all_lines[start:end], MAX_OUTPUT_CHARS)
    body = "".join(kept)
    last = start + len(kept)

    # 从头读、且整个读完了：逐字返回原内容，一个脚注都不加——加 offset 之前
    # 这条路径返回什么，现在还返回什么。
    if start == 0 and last == total_lines and len(body) <= MAX_OUTPUT_CHARS:
        return body

    # 单行超预算的病态情况：行边界救不了它，只能按字符截并如实说这一行读不全。
    # 刻意不给 offset 出路——续读点在行内，本工具的坐标系表达不了（诚实边界，档案 41）。
    if len(kept) == 1 and len(body) > MAX_OUTPUT_CHARS:
        return (body[:MAX_OUTPUT_CHARS]
                + f"\n\n[... 截断：第 {last} 行单行就有 {len(body)} 字符，"
                  f"以上只是它的前 {MAX_OUTPUT_CHARS} 字符。这一行没法用 offset 续读，"
                  f"要看全行请用 bash（如 `sed -n '{last}p' 文件`）；"
                  f"别拿这份残缺内容直接去 edit_file]")

    # 提示语给出路而不只报状态（R#17，同 bash 超时文案那条规矩）：只说「截断了」
    # 的话，模型并不知道自己拿的是残缺视图，会照着它去 edit_file。
    where = f"以上是第 {start + 1}-{last} 行，全文共 {total_lines} 行、{len(content)} 字符"
    if last < total_lines:
        return (body + f"\n\n[... 截断：{where}。要看剩下的，"
                       f"用 read_file(offset={last + 1}) 继续读；"
                       f"别拿这份残缺内容直接去 edit_file]")
    return body + f"\n\n[{where}，已到文件末尾]"


@tool
def write_file(
    path: Annotated[str, "要写入的文件路径"],
    content: Annotated[str, "写入的完整内容（会覆盖原文件）"],
) -> str:
    """把内容写入文件（覆盖式，文件不存在则创建）。"""
    atomic_write(path, content)
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
    atomic_write(path, content.replace(old, new))
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
    """取工具参数里的路径并绝对化（**不** realpath——展开成双路径是调用方的事）。

    取的是**声明的那个参数名**，不是「参数字典的第一个值」：模型序列化
    `arguments` 时的键序不受任何约束，`{"content": …, "path": …}` 完全合法，
    取第一个值就会拿正文去比对路径 pattern，规则静默不命中
    （deny 落空 → bypass 模式下直接放行）。下面 `path_access_for` 那侧
    早就是按名取的，本函数是 2026-08-18 评审补上的同一条硬化。
    """
    value = str(args.get("path") or "")
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


# 调度用的能力标志（feature 11 Task 3）。read_file 是 pai 目前**唯一**的并发安全工具。
# 两个写工具显式写 False 而不是靠默认：默认值是给「忘了声明」兜底的，
# 而这里是「想过了，结论是不行」——两者行为相同，意图不同，读代码的人该分得清。
capabilities_for(read_file, read_only=True, concurrency_safe=True)
for _writer in (write_file, edit_file):
    capabilities_for(_writer, read_only=False, concurrency_safe=False)
