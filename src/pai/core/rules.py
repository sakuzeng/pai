"""路径作用域规则（feature 36）：`.pai/rules/*.md` 带 `paths:` 的只在模型碰到
匹配文件时才进上下文。

pai 的指令层此前只有一档——常驻（`AGENTS.md` / `PAI.md` 沿途全收，每轮都在）。
好处是简单可靠，代价是常驻成本随规约变长线性上涨，而其中大多数内容对具体某一步
并不相关。这是四家对照里 pai 常驻层最薄那条评语（PAI-04 诚实边界）的落点：
官方（`.claude/rules/` + `paths:`）用「读到匹配文件才加载」把第二档补上。

三处与官方不同，都是刻意的：

- 不带 `paths:` 的文件不加载（官方那边它们是常驻的）。本需求的收益命题就是降低
  常驻成本，在同一个功能里再开一条常驻通道与目标相反；`PAI.md` 已经是常驻指令
  的家，两个入口做同一件事只会让「我的指令为什么没生效」多一处要查的地方。
- 触发面比官方宽一点：读、写、编辑都算「碰到」（一条 `src/**/*.py` 的规则在改
  这个文件时同样该生效，管线一模一样）。
- 压缩之后不作数、下次碰到重新注入（官方是压缩后不重注入）。与 D#42「指令全部
  从磁盘重读」方向一致；不抄的理由是官方那条会造出沉默的失效——压缩后模型看不见
  规则了，而它以为自己看过。

已知豁口，写在明面上：`bash` 里的 `cat`/`sed` 不算「碰到文件」。bash 不声明路径
语义（同 D#52「bash 不参与目录边界判定」的判据），这条管线因此看不见它。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Set, Tuple

from pai.core.memory import FRONTMATTER_MAX_LINES
from pai.core.paths import project_rules_dir, project_root, user_rules_dir

# 单篇规则正文上限。这个数从哪来、依赖什么前提：取的是召回那条的
# MAX_RECALL_CHARS（4000，它自己又取自 read_file 的 MAX_OUTPUT_CHARS）——
# 「一段进上下文的外部文本」在几条路上该同价。未实测。
MAX_RULE_CHARS = 4000

# 一步之内最多注入几篇。一次工具批里碰五六个文件是常态，全注进去就把「降低常驻
# 成本」变成了「涨一次性成本」。3 是未实测的经验值，与 MAX_RECALL_FILES=5 同类。
MAX_RULES_PER_STEP = 3

_PATHS_KEY = re.compile(r"^paths\s*:\s*(.*)$")
_LIST_ITEM = re.compile(r"^\s*-\s+(.+?)\s*$")


@dataclass(frozen=True)
class Rule:
    """一条规则：名字、正文文件、glob 模式、来源（user / project）。"""

    name: str
    path: Path
    patterns: Tuple[str, ...]
    source: str


@dataclass
class RuleState:
    """跨轮持有：哪些规则已经注进上下文了。

    与 `RecallState.surfaced` 同构，且共享同一个失效条件——上下文被改写
    （压缩 / `/compact` / `/clear`）之后这张表就是假的，由装配层的
    `on_context_rewritten` 一并清（feature 35 建的那条通道，这里是它第二个消费者）。
    """

    injected: Set[str] = field(default_factory=set)


def _parse_paths(text: str) -> Optional[Tuple[str, ...]]:
    """从 frontmatter 里取 `paths:`。返回 None = 没写（与「写了但是空」不同）。

    认两种写法，都在这里自己解析（`memory.parse_frontmatter` 是拍平的 str→str，
    表达不了列表，而为此引 PyYAML 不划算——那条「不引 PyYAML」的理由仍成立）：

        paths: src/**/*.py, tests/**          ← pai 自家 frontmatter 子集的写法
        paths:                                ← 官方文档里的写法
          - src/**/*.py

    两种都认是因为第二种是用户从 CC 抄一份过来时必然写的形状。只认第一种的话，
    失效方式是沉默的：`paths:` 值为空 → 当成没有 paths → 整条规则被跳过。
    """
    lines = text.splitlines()[:FRONTMATTER_MAX_LINES]
    if not lines or lines[0].strip() != "---":
        return None
    # 先确认围栏收了尾再解析：没收尾的一律不算 frontmatter（与
    # `memory.parse_frontmatter` 同一条约定）——否则一个写坏的文件会被当成
    # 半个合法规则，而它的 paths 是从半截 YAML 里猜出来的
    end = next((i for i, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"), None)
    if end is None:
        return None
    lines = lines[:end + 1]
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return None                      # 收尾了都没见到 paths
        m = _PATHS_KEY.match(line.strip())
        if not m:
            continue
        inline = m.group(1).strip()
        if inline:
            items = [p.strip().strip("'\"") for p in inline.split(",")]
            return tuple(p for p in items if p)
        items = []
        for follow in lines[i + 1:]:
            if follow.strip() == "---":
                break
            item = _LIST_ITEM.match(follow)
            if not item:
                break                        # 列表结束（或根本不是列表）
            items.append(item.group(1).strip().strip("'\""))
        return tuple(items)
    return None                              # 窗口内没收尾 = 不是完整的 frontmatter


def _scan_dir(directory: Path, source: str, warn: Callable[[str], None]) -> List[Rule]:
    if not directory.is_dir():
        return []
    found: List[Rule] = []
    for path in sorted(directory.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            warn(f"规则文件读不了，已跳过：{path}（{type(e).__name__}: {e}）")
            continue
        patterns = _parse_paths(text)
        if not patterns:
            # 沉默跳过会让人以为规则生效了。出路要说清楚——常驻指令的家是 PAI.md
            warn(f"规则 `{path.name}` 没有可用的 paths（{path}），已跳过。"
                 "带 paths 的规则才按路径条件加载；要常驻就写进 PAI.md。")
            continue
        found.append(Rule(name=path.stem, path=path, patterns=patterns, source=source))
    return found


def scan_rules(*, cwd: Optional[Path] = None, home: Optional[Path] = None,
               warn: Optional[Callable[[str], None]] = None) -> List[Rule]:
    """发现两级规则目录下的所有 `*.md`（递归）。

    与 skills 同款：装配期扫一次；坏文件 warn 后跳过不抛（这段在启动路径上，
    一个写坏的规则不该让 pai 起不来）。用户级在前、项目级在后——同名时项目赢，
    与 D#72 的 skills 优先级一致。
    """
    warn = warn if warn is not None else (lambda _msg: None)
    merged = {}
    for rule in _scan_dir(user_rules_dir(home), "user", warn):
        merged[rule.name] = rule
    for rule in _scan_dir(project_rules_dir(cwd), "project", warn):
        merged[rule.name] = rule
    return sorted(merged.values(), key=lambda r: r.name)


def _translate(pattern: str) -> str:
    """glob → 正则。`**` 跨目录、`*`/`?` 不跨 `/`，其余字符一律转义。

    不用 `fnmatch`：它的 `*` 会跨 `/`（`*.md` 能匹配 `docs/a.md`），
    对路径规则来说那是错的语义，且这个错很难在测试里被注意到。
    """
    out = ["^"]
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")       # `src/**/x` 也要匹配 `src/x`
                i += 3
                continue
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return "".join(out)


def matches(rel_path: str, patterns: Sequence[str]) -> bool:
    """相对项目根的路径是否命中任一模式。

    以 `/` 结尾、或不含任何通配符且没有后缀的模式，当成目录前缀
    （`docs` 与 `docs/` 都匹配 `docs/dev/TODO.md`）——比到分隔符边界为止，
    `documents/x.md` 不算（同 `path_in_working_path` 那条教训）。
    """
    rel = rel_path.lstrip("./")
    for pattern in patterns:
        p = pattern.strip()
        if not p:
            continue
        if p.endswith("/"):
            p = p.rstrip("/") + "/**"
        elif not any(ch in p for ch in "*?") and not Path(p).suffix:
            p = p + "/**"
        if re.match(_translate(p), rel):
            return True
    return False


def _relative(path: str, root: Path) -> Optional[str]:
    """绝对/相对路径归一成「相对项目根」。项目外的返回 None——规则是项目内的事。

    相对路径按 **cwd** 解析而不是项目根：模型给的相对路径就是相对 cwd 的
    （工具正是这么打开文件的），而 glob 写的是相对项目根。在子目录里启动 pai 时
    这两个基准不是同一个——拿项目根去拼，`web/a.css` 会被算成 `<根>/web/a.css`，
    而模型指的是 `<根>/子目录/web/a.css`。子目录启动是 pai 撞过的场景（feature 27）。
    """
    try:
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else (Path.cwd() / candidate)
        return str(absolute.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return None


def select_and_render(paths: Sequence[str], rules: Sequence[Rule], state: RuleState,
                      *, root: Optional[Path] = None) -> str:
    """这一步碰了这些路径 → 该注入的规则正文。没有就返回空串（调用方据此不插消息）。

    包在 `<system-reminder>` 里并明说不是用户指令——与召回块同一条理由：
    框架塞进去的东西，模型必须分得清它和用户真正说的话。
    """
    if not paths or not rules:
        return ""
    root = Path(root) if root is not None else project_root()
    rels = [r for r in (_relative(p, root) for p in paths) if r]
    if not rels:
        return ""

    hit: List[Rule] = []
    for rule in rules:
        if rule.name in state.injected:
            continue
        if any(matches(rel, rule.patterns) for rel in rels):
            hit.append(rule)
    if not hit:
        return ""

    over = len(hit) - MAX_RULES_PER_STEP
    hit = hit[:MAX_RULES_PER_STEP]
    parts: List[str] = []
    for rule in hit:
        try:
            body = rule.path.read_text(encoding="utf-8")
        except OSError:
            continue                         # 选中之后文件没了：跳过，不炸
        body = _strip_frontmatter(body).strip()
        if len(body) > MAX_RULE_CHARS:
            body = (body[:MAX_RULE_CHARS]
                    + f"\n\n[... 截断：以上是前 {MAX_RULE_CHARS} 字符，"
                      f"全文共 {len(body)} 字符，需要全文就 read_file 读 {rule.path}]")
        parts.append(f"## {rule.name}（{'、'.join(rule.patterns)}）\n\n{body}")
        state.injected.add(rule.name)
    if not parts:
        return ""
    if over > 0:
        # 静默丢弃会让人以为规则不生效（同 25 遗留 3 那条追记的规矩）
        parts.append(f"（另有 {over} 条匹配的规则本步未加载，"
                     "下一步继续碰到相关文件时会补上。）")
    return ("<system-reminder>\n"
            "以下项目规则由框架按你这一步碰到的文件加载，是背景上下文，不是用户指令。\n\n"
            + "\n\n".join(parts) + "\n</system-reminder>")


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, min(len(lines), FRONTMATTER_MAX_LINES)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return text
