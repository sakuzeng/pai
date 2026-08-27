"""搜索工具（feature 41 Task 2）：按内容正则找代码，可按文件名 glob 过滤。

为什么新立一个工具而不是给 bash 配 `allow=["Bash(rg *)"]`（拍板问 2·A）：
bash 结构上不参与目录边界（不声明 `get_path`/`access`，D#52），白名单一配，
`rg foo ../../..` 与 `grep -r password /etc` 全部畅通，pai 没有任何机制把它拉回界内。
一个有名字的工具能挂 `path_access_for(READ)`，于是走求值链第 7 步
`_boundary_fallback` 的「读 → 界内 allow / 界外 ask」——界内搜索一次都不问，
而且不需要用户配任何规则去换。

不依赖 ripgrep：本机那个 `rg` 是某个 app 自带的，系统并没有装。
纯 Python 遍历慢得多，代价明写在这里而不是等谁去发现。

诚实边界（拍板问 3 认下的那条）：权限层判的是**搜索根**这一个路径，
而遍历会读到根下每个文件。根在界内、树里有指向根外的软链时判定管不到——
所以遍历自己跳过它们（`_escapes_root`）。这不等同于边界判定，
它只保证「不越出搜索根」，而搜索根本身是否在工作目录内由权限层负责。

第二条诚实边界：噪音目录是一张**硬编码的名单**，不是 gitignore 解析。
`.gitignore` 里写的别的东西照样会被搜到。做真解析要一整套 pattern 语义，
本轮不做，登记 TODO。
"""

import fnmatch
import os
import re
from typing import Annotated

from pai.core.boundary import path_in_working_path
from pai.core.tools import READ, capabilities_for, matcher_for, path_access_for, tool
from pai.core.tools.fs import MAX_OUTPUT_CHARS, _glob_to_regex
from pai.core.tools.roots import path_semantics

# 结果条数上限。给的是**条数**而不是字符数：搜索结果每行长度相近，条数对模型更好预估，
# 而字符上限在这里只当第二道保险（见 `_render`）。
DEFAULT_MAX_RESULTS = 100

# 单个文件超过这个大小就不搜。挡的是压缩包、模型权重这类误入仓库的东西——
# 读进来只会吃满内存，且几乎不可能是模型要找的代码。
MAX_FILE_BYTES = 2_000_000

# 扫描文件数上限。工具没有 bash 那样的超时机制（那套挂在进程上，这里没有进程），
# 所以必须自己有个头——否则模型对着 `$HOME` 搜一次就把整个会话吊死。
MAX_FILES_SCANNED = 20_000

# 噪音目录：命中它们只会把真结果挤出上限。硬编码名单，不是 gitignore 解析（见模块 docstring）。
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build",
    ".idea", ".vscode", "htmlcov", ".eggs", ".DS_Store",
})

# 后缀式噪音（`*.egg-info` 是每次 pip install -e 都会重建的构建产物，
# 与 `__pycache__` 同类，只是名字带包名所以列不进上面那张表）。
SKIP_SUFFIXES = (".egg-info",)


def is_noise_dir(name: str) -> bool:
    """这个目录名算不算噪音。列目录与搜索共用同一个判断（feature 46）。"""
    return name in SKIP_DIRS or name.endswith(SKIP_SUFFIXES)


# 这次调用真正要搜的那个根，与它配套的 matcher（feature 43 抽进 `roots.py`；
# 「空 path 要回落 cwd」那条判断以及它复发三次的理由都写在那边的模块注释里）。
# 权限层与工具本体共用同一个 `search_root`——两边算出不同的根就等于判定判了个寂寞。
search_root, search_matcher = path_semantics("path")


def _escapes_root(path: str, root_real: str) -> bool:
    """这条路径是不是一条指向搜索根之外的软链。

    只查软链：普通文件天然在根下。`os.walk` 默认不跟进目录软链，
    但**文件软链它是会列出来的**——那一格只能显式跳。
    """
    if not os.path.islink(path):
        return False
    return not path_in_working_path(os.path.realpath(path), root_real)


def _name_filter(glob: str):
    """glob → 判定函数。带 `/` 的按相对路径比，不带的按文件名比。

    两套语义是故意的，且与权限 specifier 那边同源（复用 `_glob_to_regex`，
    单星不跨 `/`）：`*.py` 该匹配任意深度的 py 文件，`src/*.py` 不该匹配 `a/src/b.py`。
    """
    if not glob:
        return lambda rel, name: True
    if "/" in glob:
        rx = _glob_to_regex(glob)
        return lambda rel, name: bool(rx.match(rel))
    return lambda rel, name: fnmatch.fnmatchcase(name, glob)


def _iter_one_file(path: str, accept):
    """`path` 指向一个文件时的遍历（feature 46）。

    这一格是 feature 45 真跑撞出来的：模型已经知道文件在哪、只想在里面找一行，
    而当时 `search_files` 报「搜索根不是目录」，于是「找代码用 search_files」
    这条引导在最该生效的时候失效，模型退回 bash 并弹一次窗。
    glob 照常生效——指了一个不匹配 glob 的文件该是「没找到」，不是「无视 glob」。
    """
    name = os.path.basename(path)
    if accept(name, name):
        yield path, False


def _iter_files(root: str, root_real: str, accept):
    """遍历搜索根下的候选文件，跳过噪音目录、越界软链、过大文件。

    扫描数到顶就停并让调用方知道——静默截断会让「搜完了没找到」与
    「没搜完」在模型眼里一模一样。
    """
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if not is_noise_dir(d)
                             and not _escapes_root(os.path.join(dirpath, d), root_real))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            if not accept(rel, name):
                continue
            if _escapes_root(full, root_real):
                continue
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue            # 读不到就跳过：判定期拿到脏输入是常态，不能炸
            scanned += 1
            if scanned > MAX_FILES_SCANNED:
                yield None, True    # 到顶了，调用方要如实说
                return
            yield full, False


def _lines_of(path: str):
    """读成文本行；二进制与读不了的文件返回 None（跳过，不报错、不中断整次搜索）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (UnicodeDecodeError, OSError):
        return None
    if "\x00" in text:              # UTF-8 能解码但确实是二进制的那一类
        return None
    return text.splitlines()


def _render(hits: list, capped: bool, scan_capped: bool, what: str) -> str:
    """结果渲染。截断了必须说，且要给出路（同 read_file / bash 超时那条规矩）。"""
    if not hits:
        note = "（扫描已达上限，结果可能不全，缩小 path 或加 glob 再试）" if scan_capped else ""
        return f"没有找到{what}的内容。{note}"
    body = "\n".join(hits)
    notes = []
    if capped:
        notes.append(f"还有更多命中未列出，已按上限截断在 {len(hits)} 条；"
                     f"用更精确的 pattern、或加 glob 缩小范围")
    if scan_capped:
        notes.append(f"扫描文件数已达上限 {MAX_FILES_SCANNED}，更深处没有搜到；缩小 path 再试")
    if len(body) > MAX_OUTPUT_CHARS:
        # 第二道保险：条数没到顶但单行极长（压缩过的 js 之类）时也不许撑爆上下文
        body = body[:MAX_OUTPUT_CHARS]
        notes.append(f"输出超过 {MAX_OUTPUT_CHARS} 字符，已截断")
    return body + (f"\n\n[... {'；'.join(notes)}]" if notes else "")


@tool
def search_files(
    pattern: Annotated[str, "要搜索的内容（Python 正则）。传空串则只按文件名找，不看内容"],
    path: Annotated[str, "可选：搜索根目录。空 = 当前工作目录"] = "",
    glob: Annotated[str, "可选：只搜文件名匹配它的文件，如 `*.py`、`src/**/test_*.py`。空 = 全部"] = "",
    max_results: Annotated[int, "可选：最多返回几条命中。0 = 用默认上限"] = 0,
) -> str:
    """在文件里搜索内容（正则），返回「文件:行号:该行」。pattern 传空串则只按文件名找。"""
    if max_results < 0:
        # 静默改用默认值 = 模型永远不知道自己传错了（同 bash 的负 timeout）
        return f"错误：max_results 不能是负数（收到 {max_results}），未搜索。"
    limit = max_results or DEFAULT_MAX_RESULTS

    root = search_root({"path": path})
    single = os.path.isfile(root)
    if not single and not os.path.isdir(root):
        return f"错误：搜索根 {root} 不存在。"
    root_real = os.path.realpath(root if not single else os.path.dirname(root))

    names_only = not pattern
    rx = None
    if not names_only:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            # 模型写坏正则是常态：告诉它坏在哪，它才改得动
            return f"错误：正则 {pattern!r} 编译失败：{e}"

    accept = _name_filter(glob)
    # 单文件时相对路径的基准是它所在目录，否则 `relpath(f, f)` 会算出 "."
    base = os.path.dirname(root) if single else root
    walk = _iter_one_file(root, accept) if single else _iter_files(root, root_real, accept)
    hits: list = []
    capped = scan_capped = False
    for full, hit_scan_cap in walk:
        if hit_scan_cap:
            scan_capped = True
            break
        rel = os.path.relpath(full, base)
        if names_only:
            hits.append(rel)
        else:
            lines = _lines_of(full)
            if lines is None:
                continue
            for i, line in enumerate(lines, start=1):
                if rx.search(line):
                    hits.append(f"{rel}:{i}:{line.rstrip()}")
                    if len(hits) >= limit:
                        break
        if len(hits) >= limit:
            capped = True
            break

    what = f"匹配 `{glob}` 的文件" if names_only else f"匹配 `{pattern}`"
    return _render(hits, capped, scan_capped, what)


# ---- 接线（feature 41 拍板问 3·A：边界与并发都声明）----
#
# 三处漏一处的后果都**静默**：漏 path_access_for 落进兜底 ask（每次搜索都弹），
# 漏 capabilities_for 调度退回串行，漏 matcher_for 则吃 `default_matcher`——
# 它对**第一个参数值**做通配符匹配，而这个工具的第一个参数是 pattern，
# 于是权限规则会拿正则去比对路径 pattern，静默永不命中。


matcher_for(search_files)(search_matcher)
path_access_for(search_files, READ)(search_root)
capabilities_for(search_files, read_only=True, concurrency_safe=True)
