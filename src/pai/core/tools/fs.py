"""文件系统三件套：read / write / edit。edit 采用唯一精确替换（学 pi 的 edit 语义）。

写入一律**原子**：临时文件 + `os.replace`。理由不是洁癖——`open(path, "w")` 是
**先截断后写入**，进程若死在这两步之间（kill -9 / OOM / 断电），留下的是空文件或半截文件。
`edit_file` 尤其危险：它把原内容读进内存后同样要截断重写，**那一瞬间原文只存在于内存里**。
原子写把任何时刻的中断都收敛成两种结果：旧的完好，或新的完整。
"""

import os
import tempfile
from typing import Annotated

from pai.core.tools import tool

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
