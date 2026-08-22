"""skills：按需加载的能力扩展（feature 25，roadmap 阶段 6 子阶段一）。

一个 skill = 一个目录包 `<name>/SKILL.md`（或扁平 `<name>.md`）：frontmatter 里的
description 常驻上下文供模型匹配，正文只在被 `skill` 工具加载时进入对话——
渐进式披露。本模块只做纯逻辑（扫描/渲染/预算），不 import loop 内部，
不碰全局状态；装配在 modes 层。

三家对照见 knowledge/skills/ 四篇。本实现的取舍：
- 加载走专用 `skill` 工具（D#71，dsh 形态；偏离 R4#A4 的 pi「零新增工具」定向）；
- 同名冲突项目级赢（D#72，dsh 语义；CC 相反、pi 先到先得）；
- 缺 description / 坏 frontmatter 一律跳过并 warn（fail loud）——刻意不抄 CC 的
  「回退正文首段」：动工前反向对照（features/25 evidence）证实那条回退会把
  写坏的 frontmatter 伪装成正常 skill。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional
from xml.sax.saxutils import escape

from pai.core.memory import FRONTMATTER_MAX_LINES, parse_frontmatter
from pai.core.paths import project_skills_dir, user_skills_dir

# 目录里每条 description 的截断上限。取 dsh `catalogDescriptionMaxLength` 的默认值
# （500）；CC 2.1.88 是 250、官方文档现行 1536——三家里取中庸的一档，未实测校准。
MAX_CATALOG_DESC_CHARS = 500

# 目录总预算（字节）。取 CC 拿不到窗口信息时的兜底值 DEFAULT_CHAR_BUDGET=8000。
# pai 的窗口是 1M，按 CC 的「窗口 1%」算会大到失去约束意义，故用固定值。
MAX_CATALOG_BYTES = 8000

# 压缩后重挂的预算：CC 的 5k/25k token 按 4 字符/token 换算成字符数。
# 未实测校准（与 reserve_tokens 同一类「借来的经验值」，来源写在这儿备查）。
REATTACH_PER_SKILL_CHARS = 20_000
REATTACH_TOTAL_CHARS = 100_000

SKILL_FILE = "SKILL.md"

_KEBAB_OK = "abcdefghijklmnopqrstuvwxyz0123456789-"


@dataclass(frozen=True)
class Skill:
    """扫描产物：目录里的一行。刻意不含正文——目录轻/正文重分离（dsh 三层结构），
    正文由 `skill` 工具在被调用时从磁盘现读。"""

    name: str
    description: str
    path: Path                  # SKILL.md（或扁平 .md）的绝对路径
    base_dir: Path              # 相对资源的解析基准（目录包=包目录，扁平=所在目录）
    source: str                 # "user" | "project"
    model_invocable: bool = True


def _warn_name(name: str, warn: Callable[[str], None]) -> None:
    ok = name and all(c in _KEBAB_OK for c in name) and \
        not name.startswith("-") and not name.endswith("-") and "--" not in name
    if not ok:
        # 宽松语义（pi）：路径来自扫描结果而非由 name 反推，不合规不构成安全问题
        warn(f"skill 名 `{name}` 不符合 kebab-case（小写字母/数字/连字符），仍已加载")


def _load_one(path: Path, name: str, source: str,
              warn: Callable[[str], None]) -> Optional[Skill]:
    try:
        with path.open(encoding="utf-8") as f:
            head = "".join(line for _, line in zip(range(FRONTMATTER_MAX_LINES), f))
    except (OSError, UnicodeDecodeError) as e:
        warn(f"skill `{name}` 读不了（{type(e).__name__}），已跳过：{path}")
        return None
    fields = parse_frontmatter(head)
    description = fields.get("description", "").strip()
    if not description:
        warn(f"skill `{name}` 缺 description（frontmatter 缺失、损坏或没写），"
             f"已跳过：{path}")
        return None
    _warn_name(name, warn)
    return Skill(
        name=name,
        description=description,
        path=path,
        base_dir=path.parent,
        source=source,
        model_invocable=fields.get("disable-model-invocation", "").lower() != "true",
    )


def _scan_root(root: Path, source: str, warn: Callable[[str], None]) -> List[Skill]:
    """一个根目录下的直接子项：目录包优先于扁平文件；不递归更深层（dsh 语义）。"""
    if not root.is_dir():
        return []
    found: Dict[str, Skill] = {}
    entries = sorted(root.iterdir(), key=lambda p: p.name)
    for entry in entries:                                   # 先收目录包
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        skill_md = entry / SKILL_FILE
        if not skill_md.is_file():
            continue                                        # 更深层的嵌套刻意不找
        skill = _load_one(skill_md, entry.name, source, warn)
        if skill is not None:
            found[skill.name] = skill
    for entry in entries:                                   # 再收扁平 .md，同名让位
        if entry.name.startswith(".") or not entry.is_file():
            continue
        if not entry.name.endswith(".md"):
            continue
        name = entry.name[:-3]
        if name in found:
            continue
        skill = _load_one(entry, name, source, warn)
        if skill is not None:
            found[skill.name] = skill
    return list(found.values())


def scan_skills(*, cwd: Optional[Path] = None, home: Optional[Path] = None,
                warn: Optional[Callable[[str], None]] = None) -> List[Skill]:
    """扫两级目录，返回按名排序的 skills。同名项目级赢（D#72）。

    扫描只在装配期跑一次（pi 同款）；会话中途增删 skill 不生效，记在 TODO。
    坏文件 warn 后跳过，不抛——这段在启动路径上，一个坏 skill 不该让 pai 起不来。
    """
    warn = warn if warn is not None else (lambda _msg: None)
    merged: Dict[str, Skill] = {}
    for skill in _scan_root(user_skills_dir(home), "user", warn):
        merged[skill.name] = skill
    for skill in _scan_root(project_skills_dir(cwd), "project", warn):
        merged[skill.name] = skill                          # 后写覆盖 = 项目赢
    return sorted(merged.values(), key=lambda s: s.name)


# ---------------------------------------------------------------- 目录渲染

def render_catalog(skills: List[Skill], *,
                   max_desc_chars: int = MAX_CATALOG_DESC_CHARS,
                   max_bytes: int = MAX_CATALOG_BYTES) -> str:
    """`<available_skills>` 目录：只含模型可调的，按名排序，name+description，
    不含路径——工具形态下模型用名字调用，给路径只会诱导绕过工具直接 read
    （dsh 同款配对，见 K skills/dsh-skills.md）。空列表返回空串（不留空标签）。"""
    visible = [s for s in skills if s.model_invocable]
    if not visible:
        return ""
    lines = ["<available_skills>"]
    total = len(lines[0])
    truncated = False
    for s in sorted(visible, key=lambda x: x.name):
        desc = s.description
        if len(desc) > max_desc_chars:
            desc = desc[: max_desc_chars - 1] + "…"
        entry = (f"  <skill><name>{escape(s.name)}</name>"
                 f"<description>{escape(desc)}</description></skill>")
        if total + len(entry.encode("utf-8")) > max_bytes:
            truncated = True
            break
        lines.append(entry)
        total += len(entry.encode("utf-8"))
    if truncated:
        lines.append(f"  <note>目录超出预算已截断，共 {len(visible)} 个 skills，"
                     f"以上是按名排序的前 {len(lines) - 1} 个</note>")
    lines.append("</available_skills>")
    return "\n".join(lines)


# ---------------------------------------------------------------- 正文加载与重挂

def read_skill_body(skill: Skill) -> str:
    """当场重读磁盘并剥 frontmatter（dsh：注册表不缓存正文，改盘即生效）。"""
    text = skill.path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, min(len(lines), FRONTMATTER_MAX_LINES)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:]).strip("\n")
    return text.strip("\n")


def render_skill_block(skill: Skill, body: str) -> str:
    """发给模型的正文包装。相对路径基准必须随行——附属文件（脚本/参考）靠它解析。"""
    return (f'<skill_content name="{escape(skill.name)}">\n{body}\n</skill_content>\n'
            f"（本 skill 引用的相对路径以 {skill.base_dir} 为基准，"
            f"用 read_file/bash 访问时请拼成绝对路径。）")


class LoadedSkills:
    """本会话已加载过哪些 skill（压缩后重挂的依据，CC `addInvokedSkill` 对位）。

    装配期创建、跨轮持有（REPL 与 anchors 同款生命周期）；skill 工具执行期写入。
    只记名字与时刻不记正文——重挂时从磁盘现读（D#42「重新调用 loader = 重读磁盘」
    同一味药，顺带让中途改的文件生效）。
    """

    def __init__(self) -> None:
        # 单调序号不是时间戳：同一毫秒内连续两次 record 用 time.time() 会并列，
        # 「最近优先」的排序就退化成字典序运气
        self._seq = 0
        self._loaded_at: Dict[str, int] = {}

    def record(self, name: str) -> None:
        self._seq += 1
        self._loaded_at[name] = self._seq

    def names_recent_first(self) -> List[str]:
        return sorted(self._loaded_at, key=lambda n: self._loaded_at[n], reverse=True)

    def __bool__(self) -> bool:
        return bool(self._loaded_at)


def render_loaded_skills(loaded: LoadedSkills, catalog: Dict[str, Skill], *,
                         per_skill_chars: int = REATTACH_PER_SKILL_CHARS,
                         total_chars: int = REATTACH_TOTAL_CHARS) -> str:
    """压缩后重挂的正文段（CC `createSkillAttachmentIfNeeded` 对位）：
    最近加载优先；单个超限截头部保留（setup/usage 通常在头部——CC 注释原话）；
    总预算装不下的整条丢弃（不是再截短）。文件没了跳过。空结果返回空串。"""
    parts: List[str] = []
    used = 0
    for name in loaded.names_recent_first():
        skill = catalog.get(name)
        if skill is None:
            continue
        try:
            body = read_skill_body(skill)
        except (OSError, UnicodeDecodeError):
            continue
        if len(body) > per_skill_chars:
            # 提示语计入单篇预算：否则截过的正文照样超预算，最近一篇永远装不进总预算
            note = "\n…（超出重挂预算，已截断，可用 skill 工具重新加载全文）"
            body = body[:max(0, per_skill_chars - len(note))] + note
        if used + len(body) > total_chars:
            continue
        used += len(body)
        parts.append(render_skill_block(skill, body))
    if not parts:
        return ""
    return ("\n\n# 已加载的 skills（压缩前加载过，正文重新附上）\n\n"
            + "\n\n".join(parts))


def make_instructions(base: Callable[[], str], loaded: LoadedSkills,
                      catalog: Dict[str, Skill]) -> Callable[[], str]:
    """组合指令 loader：基础指令（memory.build_context）+ 已加载 skills 正文。

    重挂机制整个搭 D#42 的车（零 loop 改动）：loop 在压缩重建后会重新调用
    instructions loader（loop.py 压缩块），届时追踪器里已有本会话的加载记录，
    正文就跟着指令消息一起回到上下文。会话开头追踪器为空，行为与 base 一字不差。
    已知边界（spec 第 4 节如实声明）：压缩发生之前指令消息不更新
    （`_has_instructions` 短路），中途加载的正文只活在 tool_result 里——
    重挂只在压缩重建时兑现，而那恰好就是需要它的时刻。
    """
    def load() -> str:
        return base() + render_loaded_skills(loaded, catalog)
    return load
