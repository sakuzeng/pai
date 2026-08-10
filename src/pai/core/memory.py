"""记忆：跨会话传递知识的两套机制（官方也是两套，见 K claude-docs/memory.md）。

1. **人写的分层指令**（本文件的 discover/load）：`~/.pai/PAI.md` → 向上递归的
   `PAI.md` → 同目录的 `PAI.local.md`。拼接不覆盖，越靠近 cwd 的越晚被读到。
2. **模型自写的自动记忆**：`MEMORY.md` 索引每会话加载（有上限），主题文件按需读。

刻意不读 `AGENTS.md` / `CLAUDE.md`（D#43）：那些文件写的是「给开发这个仓库的 AI 的
规矩」（先写测试跑红、留痕、档案门禁），pai 自己当 agent 跑时读到会把开发规约当成
任务指令。要用它们请在 PAI.md 里显式 `@AGENTS.md` 导入——主动权留给用户，
这也正是官方对 AGENTS.md 的处理方式。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import FrozenSet, List, Optional

PROJECT_FILE = "PAI.md"
LOCAL_FILE = "PAI.local.md"
USER_DIR = ".pai"

MAX_IMPORT_DEPTH = 4                    # 官方数字：最大 4 跳
# 代码块与行内代码里的 @path 是字面文本（官方语义）——先把它们挖掉再扫导入，
# 比在导入正则里写「前面不能是反引号」这类否定环视可靠得多
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# 路径到空白为止；结尾的标点不算路径的一部分（中文文档里 `@a.md，` 很常见）
_IMPORT = re.compile(r"@([^\s`]+?)(?=[\s，。、）)]|$)")


def discover(*, cwd: Optional[Path] = None, home: Optional[Path] = None) -> List[Path]:
    """按加载顺序返回存在的指令文件：用户级 → 根 → … → cwd，同目录内 local 在后。

    两个参数都可注入：不注入就只能靠 chdir + 改 HOME 来测，那种测试既慢又互相干扰。
    cwd **之下**的子目录不收集——官方同款语义，模型要用时自己 read_file。
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    home = Path(home) if home is not None else Path.home()

    found: List[Path] = []
    user_level = home / USER_DIR / PROJECT_FILE
    if user_level.is_file():
        found.append(user_level)

    # 向上收集再反序：官方顺序是从文件系统根向下到 cwd，
    # 于是「越靠近你启动的位置，越晚被读到」——同名指令后者赢
    ancestors = [cwd, *cwd.parents]
    for directory in reversed(ancestors):
        for name in (PROJECT_FILE, LOCAL_FILE):
            candidate = directory / name
            if candidate.is_file():
                found.append(candidate)
    return found


def expand_imports(text: str, *, base: Path, home: Optional[Path] = None,
                   depth: int = 0, seen: FrozenSet[Path] = frozenset()) -> str:
    """展开 `@path` 导入。

    四条规则全部照官方（K claude-docs/memory.md 第二节）：
    相对路径相对**含导入的那个文件**解析（不是 cwd）、最多 4 跳、代码块与行内代码里的
    不算导入、缺文件不抛。加了一条官方没有的：环检测——A↔B 互导入必须终止。
    """
    base = Path(base)
    home = Path(home) if home is not None else Path.home()

    spans = [m.span() for m in _CODE.finditer(text)]

    def in_code(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    def replace(match: "re.Match") -> str:
        if in_code(match.start()):
            return match.group(0)
        raw = match.group(1)
        target = _resolve(raw, base=base, home=home)
        if depth >= MAX_IMPORT_DEPTH:
            return f"(@{raw} 未展开：已达导入深度上限 {MAX_IMPORT_DEPTH})"
        if target in seen:
            return f"(@{raw} 未展开：循环导入)"
        if not target.is_file():
            # 指令加载不该弄挂 agent；留痕比静默丢弃有用得多
            return f"(@{raw} 未找到)"
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as e:
            return f"(@{raw} 读取失败：{e})"
        return expand_imports(content, base=target.parent, home=home,
                              depth=depth + 1, seen=seen | {target})

    return _IMPORT.sub(replace, text)


def _resolve(raw: str, *, base: Path, home: Path) -> Path:
    if raw.startswith("~/"):
        return home / raw[2:]
    path = Path(raw)
    return path if path.is_absolute() else base / path


def load_instructions(*, cwd: Optional[Path] = None, home: Optional[Path] = None) -> str:
    """按发现顺序读取全部指令文件、展开导入、拼成一段文本。"""
    parts: List[str] = []
    for path in discover(cwd=cwd, home=home):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parts.append(f"# {path}\n\n{expand_imports(raw, base=path.parent, home=home)}")
    return "\n\n".join(parts)


# 官方数字（K claude-docs/memory.md 第三节）：MEMORY.md 只加载前 200 行或 25KB，
# 先到者为准。上限只管索引——主题文件本来就不在启动时加载。
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25 * 1024
MEMORY_INDEX = "MEMORY.md"
PROJECTS_DIR = "projects"
MEMORY_SUBDIR = "memory"


def memory_dir(*, cwd: Optional[Path] = None, home: Optional[Path] = None) -> Path:
    """自动记忆目录：`~/.pai/projects/<key>/memory/`。

    key 由 **git 仓库根**决定——同一仓库的所有子目录与 worktree 共享一份记忆
    （官方语义）。不在 git 仓库里就退回该目录本身，各算各的。
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    home = Path(home) if home is not None else Path.home()
    root = _git_root(cwd) or cwd
    key = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:16]
    return home / USER_DIR / PROJECTS_DIR / key / MEMORY_SUBDIR


def _git_root(start: Path) -> Optional[Path]:
    """自己往上找 .git，不调 `git rev-parse`——加载指令是启动路径，不该起子进程。"""
    for directory in [start, *start.parents]:
        if (directory / ".git").exists():
            return directory
    return None


def load_memory_index(directory: Path) -> str:
    """读 MEMORY.md，按行数与字节两条上限截断（先到者为准）。

    官方是**静默**截断——超出部分「会话开始时不加载」，用户无从知道。
    pai 留一行提示：静默丢内容会让人以为模型忘了事，实际是根本没读到。
    """
    index = Path(directory) / MEMORY_INDEX
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        return ""

    lines = text.splitlines()
    truncated = False
    if len(lines) > MAX_INDEX_LINES:
        lines = lines[:MAX_INDEX_LINES]
        truncated = True

    kept: List[str] = []
    used = 0
    for line in lines:
        cost = len(line.encode("utf-8")) + 1
        if used + cost > MAX_INDEX_BYTES:
            truncated = True
            break
        kept.append(line)
        used += cost

    body = "\n".join(kept)
    if truncated:
        body += (f"\n\n(以上为 {MEMORY_INDEX} 的前 {len(kept)} 行；"
                 f"超过 {MAX_INDEX_LINES} 行或 {MAX_INDEX_BYTES // 1024}KB 的部分已截断，"
                 "需要时用 read_file 直接读该文件)")
    return body


def build_context(*, cwd: Optional[Path] = None, home: Optional[Path] = None) -> str:
    """装配层的唯一入口：分层指令 + 自动记忆索引拼成一段文本。

    返回空串表示「什么都没有」——调用方据此决定不插那条 user 消息。
    每次调用都重读磁盘：压缩后的重注入靠的就是这一点（官方原话是「从磁盘重新读取」），
    顺带让用户中途改 PAI.md 立即生效。
    """
    parts: List[str] = []
    instructions = load_instructions(cwd=cwd, home=home)
    if instructions.strip():
        parts.append(instructions)
    index = load_memory_index(memory_dir(cwd=cwd, home=home))
    if index.strip():
        parts.append(f"## 自动记忆（{MEMORY_INDEX} 索引；主题文件用 read_file 按需读）\n\n{index}")
    return "\n\n".join(parts)
