"""记忆：跨会话传递知识的两套机制（官方也是两套，见 K memory/claude-memory.md）。

1. **人写的分层指令**（本文件的 discover/load）：`~/.pai/PAI.md` → 向上递归的
   `PAI.md` → 同目录的 `PAI.local.md`。拼接不覆盖，越靠近 cwd 的越晚被读到。
2. **模型自写的自动记忆**：`MEMORY.md` 索引每会话加载（有上限），主题文件按需读。

刻意不读 `AGENTS.md` / `CLAUDE.md`（D#43）：那些文件写的是「给开发这个仓库的 AI 的
规矩」（先写测试跑红、留痕、档案门禁），pai 自己当 agent 跑时读到会把开发规约当成
任务指令。要用它们请在 PAI.md 里显式 `@AGENTS.md` 导入——主动权留给用户，
这也正是官方对 AGENTS.md 的处理方式。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from pai.core import paths as _paths

PROJECT_FILE = "PAI.md"
LOCAL_FILE = "PAI.local.md"
# 通用的 agent 规约文件（D#43 复议，2026-08-26 用户拍板）：pai 的立意是在**别人的**
# 项目里跑，那里的 AGENTS.md 就是该项目写给 agent 的规矩，是最该读的上下文。
# 原裁决「不读」的理由（「那是给写 pai 的 AI 的规矩」）只在本仓库成立。
# 排在 PROJECT_FILE 之前：同目录内后读到的更靠近对话，PAI.md 该压得住通用那份。
# 只翻这一条——CLAUDE.md 等别家入口照旧不读（要用就显式 @ 导入）。
AGENTS_FILE = "AGENTS.md"
USER_DIR = ".pai"

MAX_IMPORT_DEPTH = 4                    # 官方数字：最大 4 跳
# 代码块与行内代码里的 @path 是字面文本（官方语义）——先把它们挖掉再扫导入，
# 比在导入正则里写「前面不能是反引号」这类否定环视可靠得多
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# 路径到空白为止；结尾的标点不算路径的一部分（中文文档里 `@a.md，` 很常见）。
# `@` 必须在行首或空白之后：贴着字母的 `@` 是邮箱不是导入
# （`someone@example.com` 曾被改写成 `someone(@example.com 未找到)`）。
_IMPORT = re.compile(r"(?:^|(?<=\s))@([^\s`]+?)(?=[\s，。、）)]|$)", re.M)


def _looks_like_a_path(raw: str) -> bool:
    """还要「长得像路径」才算导入。

    光靠位置挡不住 `@tool` / `@property` / `@dataclass(frozen=True)` 这类
    装饰器名——它们同样出现在空白之后。而本仓库自己的规约里就写着
    「工具 schema 一律由 @tool 装饰器生成」，用户照着写一份 PAI.md，
    那句话每轮都会被悄悄改成「(@tool 未找到)」，且没有任何告警。

    判据取「含分隔符」而不是「文件存在」：后者会让写错路径的人
    连「未找到」这个诊断都拿不到。
    """
    return "/" in raw or "." in raw or raw.startswith("~")


def discover(*, cwd: Optional[Path] = None, home: Optional[Path] = None) -> List[Path]:
    """按加载顺序返回存在的指令文件：用户级 → 根 → … → cwd，同目录内 local 在后。

    两个参数都可注入：不注入就只能靠 chdir + 改 HOME 来测，那种测试既慢又互相干扰。

    cwd **之下**的子目录 pai 彻底不收集。这**不是**官方同款语义（原注释这么写是错的，
    2026-08-19 逐条对照官方 memory 文档时发现）：官方对子目录的 CLAUDE.md 是
    **框架懒加载**——启动时发现但不加载，等模型真去读那个目录里的文件时自动注入。
    也就是说那边仍是「框架主动」，只是延迟到需要时；pai 比它弱一档，是刻意的能力差
    （懒加载要一条「读文件时检查该目录有无 PAI.md」的管线，且注入时机不确定，
    与压缩锚点簿有交互）。写成「同款语义」会让人以为行为一致。
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    home = Path(home) if home is not None else Path.home()

    found: List[Path] = []
    for name in (AGENTS_FILE, PROJECT_FILE):
        user_level = home / USER_DIR / name
        if user_level.is_file():
            found.append(user_level)

    # 向上收集再反序：官方顺序是从文件系统根向下到 cwd，
    # 于是「越靠近你启动的位置，越晚被读到」——同名指令后者赢
    ancestors = [cwd, *cwd.parents]
    for directory in reversed(ancestors):
        for name in (AGENTS_FILE, PROJECT_FILE, LOCAL_FILE):
            candidate = directory / name
            if candidate.is_file():
                found.append(candidate)
    return found


def expand_imports(text: str, *, base: Path, home: Optional[Path] = None,
                   depth: int = 0, seen: FrozenSet[Path] = frozenset()) -> str:
    """展开 `@path` 导入。

    四条规则全部照官方（K memory/claude-memory.md 第二节）：
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
        if not _looks_like_a_path(raw):
            return match.group(0)      # 不是导入，原样留着（连诊断都不该打）
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


# 官方数字（K memory/claude-memory.md 第三节）：MEMORY.md 只加载前 200 行或 25KB，
# 先到者为准。上限只管索引——主题文件本来就不在启动时加载。
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25 * 1024
MEMORY_INDEX = "MEMORY.md"
PROJECTS_DIR = "projects"
MEMORY_SUBDIR = "memory"


def memory_dir(*, cwd: Optional[Path] = None, home: Optional[Path] = None) -> Path:
    """自动记忆目录。转调 pai.core.paths——路径规则只此一处（feature 08）。

    对外签名不变，所以 build_context / memory_tool 的调用点不用改。
    """
    return _paths.memory_dir(cwd=cwd, home=home)


# 扫描侧（feature 10）。两个数字都照 CC memoryScan.ts：
# 每文件只读前 30 行，于是 manifest 的输入成本与记忆总量**几乎无关**；总量截断 200 篇。
FRONTMATTER_MAX_LINES = 30
MAX_SCANNED = 200
LEGACY_TYPE = "legacy"                  # 06 时代的裸 bullet 文件，没 frontmatter 可读
DEFAULT_TYPE = "project"
_FIELD = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")


@dataclass(frozen=True)
class MemoryHeader:
    """一篇记忆的「头」：召回 manifest 与索引投影共用的那点信息，不含正文。"""

    path: Path
    name: str
    description: str
    type: str
    mtime: float
    origin_session_id: str = ""
    modified: str = ""


def parse_frontmatter(text: str) -> Dict[str, str]:
    """解析我们自己写的 frontmatter 子集，**不引 PyYAML**。

    认的形状：`---` 围栏 + `key: value` + 两空格缩进的 `metadata:` 块（拍平进同一个 dict）。
    引一个新依赖去解析自己产生的 6 行文本不划算；解析不认识的键原样收着而不是报错，
    这样 CC 那边多出来的字段（`node_type`）也不会把扫描弄红。

    只看前 FRONTMATTER_MAX_LINES 行：没在这个窗口里收尾的一律当没有 frontmatter，
    否则「只读前 30 行」这条成本约束就被解析器悄悄破坏了。
    """
    lines = text.splitlines()[:FRONTMATTER_MAX_LINES]
    if not lines or lines[0].strip() != "---":
        return {}
    fields: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        m = _FIELD.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if not raw:
            continue                    # `metadata:` 这类块头本身没有值，拍平后不占位
        fields[key] = _unquote(raw)
    return {}                           # 窗口内没见到收尾围栏 = 不是完整的 frontmatter


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _legacy_description(head: str) -> str:
    """旧文件没有描述，只能从正文里抠一句：跳过围栏与标题，去掉 bullet 前缀。"""
    for line in head.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---" or stripped.startswith("#"):
            continue
        return stripped.lstrip("-* ").strip()[:80]
    return ""


def scan_memories(directory: Path) -> List[MemoryHeader]:
    """扫记忆目录，返回按 mtime 新→旧排序、截断 MAX_SCANNED 的头列表。

    **排除 MEMORY.md**：它已经常驻上下文，再进 manifest 就是让召回器把名额浪费在
    模型已经看得见的东西上（CC 的 findRelevantMemories 同样显式排除）。
    读不了的文件跳过而不是抛：这段代码在启动路径上，一个坏文件不该让 pai 起不来。
    """
    directory = Path(directory)
    headers: List[MemoryHeader] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == MEMORY_INDEX or not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as f:
                head = "".join(islice(f, FRONTMATTER_MAX_LINES))
            mtime = path.stat().st_mtime
        except (OSError, UnicodeDecodeError):
            continue
        fields = parse_frontmatter(head)
        if fields:
            headers.append(MemoryHeader(
                path=path,
                name=fields.get("name") or path.stem,
                description=fields.get("description", ""),
                type=fields.get("type", DEFAULT_TYPE),
                mtime=mtime,
                origin_session_id=fields.get("originSessionId", ""),
                modified=fields.get("modified", ""),
            ))
        else:
            headers.append(MemoryHeader(
                path=path, name=path.stem, description=_legacy_description(head),
                type=LEGACY_TYPE, mtime=mtime))
    headers.sort(key=lambda h: h.mtime, reverse=True)
    return headers[:MAX_SCANNED]


INDEX_HEADER = ("# 记忆索引（本文件由 pai 自动生成，手改会被覆盖；"
                "要改请改对应记忆文件的 frontmatter）")


def _day_diff(mtime: float, now: float) -> int:
    """按**日历日**差，不用 86400 秒整除——否则昨晚 23:00 与今早 01:00 会算成同一天。"""
    return (datetime.fromtimestamp(now).date() - datetime.fromtimestamp(mtime).date()).days


def memory_age(mtime: float, now: float) -> str:
    """「今天」/「昨天」/「47 天前」——照 CC memoryAge.ts。

    为什么不是 ISO 时间戳：CC 的注释直说**模型不擅长日期算术**，原始时间戳不会触发
    「这条可能过期了」的推理，而「47 天前」会。
    """
    days = _day_diff(mtime, now)
    if days <= 0:
        return "今天"
    if days == 1:
        return "昨天"
    return f"{days} 天前"


def freshness_note(mtime: float, now: float) -> str:
    """>1 天才有话说（≤1 天时警告是噪音，CC 同款阈值）。

    动机是 CC 注释里写明的真实事故：**带 file:line 的引用会让一条过期声明听起来
    更权威，而不是更不权威**——所以警告必须点名 file:line 这种形态。
    """
    days = _day_diff(mtime, now)
    if days <= 1:
        return ""
    return (f"（这条记忆写于 {days} 天前。记忆是时间点观察，不是实时状态——"
            "其中关于代码行为的断言或 file:line 引用可能已经过期，"
            "当成事实之前先核对当前代码。）")


def render_index(headers: List[MemoryHeader], now: Optional[float] = None) -> str:
    """把扫描结果渲染成索引文本。空列表 → 空串（调用方据此不插那一节）。

    `now` 为 None 时**不渲染相对时间**：相对时间是渲染时刻的函数，写进持久文件就会腐坏，
    而「一条三个月前的记忆在文件里写着『今天』」正是新鲜度这条特性要防的东西。
    所以盘上那份 MEMORY.md 不带时间，进上下文的那份才带。
    """
    if not headers:
        return ""
    lines = [INDEX_HEADER, ""]
    for h in headers:
        line = f"- [{h.name}]({h.path.name})"
        if h.description:
            line += f" — {h.description}"
        if now is not None:
            line += f"（{memory_age(h.mtime, now)}）"
        lines.append(line)
    return "\n".join(lines) + "\n"


def load_memory_index(directory: Path, *, now: Optional[float] = None) -> str:
    """索引是**投影**：从各记忆文件的 frontmatter 现渲染，不读盘上的 MEMORY.md（feature 10）。

    这样删文件、手改 description 都不需要一致性代码——盘上那份是同一个函数的另一个出口。
    代价写在档案里：手编 MEMORY.md 会在下次 remember 时被覆盖。

    两条上限（200 行 / 25KB）保留。但**截断的性质变了**：有召回层之后，
    放不进常驻区不再等于「那条记忆不存在」，它仍然能被按需召回选中。
    """
    now = time.time() if now is None else now
    text = render_index(scan_memories(directory), now=now)
    if not text:
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
        entries = sum(1 for line in kept if line.startswith("- ["))
        body += (f"\n\n(常驻区只列得下最近 {entries} 篇，其余已截断；超过 {MAX_INDEX_LINES} 行"
                 f"或 {MAX_INDEX_BYTES // 1024}KB 的部分不在这里，会随每轮输入按需召回)")
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
