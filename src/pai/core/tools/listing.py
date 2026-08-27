"""目录结构：`list_dir` 工具 + 装配期注入共用的那份树渲染（feature 46）。

出处是 feature 45 的实测发现 A2：`pwd && ls` 是两次真跑里的**第一个**工具调用，
而 pai 没有任何工具能回答「这个项目长什么样」——于是它必然走 bash，
而 bash 结构上不参与目录边界（D#52），必然弹窗。开场第一步就打断用户。

拍板问 2·A 选了「装配期注入 + 工具兜底」两手都要：
- 注入让开场那一步**根本不发生**（模型读 system prompt 就知道了）；
- 工具兜底会话中途新建的目录——注入是一次性的，会过时，而它没别的办法重看一眼。

一份实现两个消费者：`render_tree` 同时被 `list_dir` 与装配层调用。
分成两份写的话，「注入里看到的」与「工具返回的」会各说各话，
而那种不一致最难查——两边都对，只是不是同一份事实。

噪音目录名单**直接复用 `search_files` 的那份对象**（不是抄一份）：
两处各写一份，迟早出现「搜索跳过了但列目录列出来了」这种自相矛盾。
"""

import os
from typing import Annotated, List

from pai.core.tools import READ, capabilities_for, matcher_for, path_access_for, tool
from pai.core.tools.roots import path_semantics
from pai.core.tools.search import SKIP_DIRS, is_noise_dir   # 同一份判断，见模块 docstring

# 一次最多列多少项。**未实测**，按「一屏多一点」定——注入进 system prompt 的
# 那份每个会话都要花这些 token，所以宁可少给、让模型需要时再用 list_dir 挖。
MAX_ENTRIES = 120
# **每个目录最多列几个文件**。没有这一条的话总预算会被单个大目录吃光：
# 本仓库第一版生成出来，`tests/` 的 60 个文件把 120 项占满，
# 而 `src/` 只显示到 `pai/`——摘要里没有一点源码结构，等于没写。
# 骨架比枚举重要，所以宁可每个目录只给几个样本。
MAX_FILES_PER_DIR = 8
# 默认深度 2。试过 3——在本仓库上更差：深的层次把预算吃光，`src/pai/` 反而
# 一个子目录都列不出来。这份摘要的职责是**知道有哪些地方**，不是完整地图；
# 往下挖交给 `list_dir`（system prompt 里那句引导正是为此）。
DEFAULT_DEPTH = 2
MAX_DEPTH = 6
INDENT = "  "


def _entries(path: str) -> tuple:
    """`(子目录名, 文件名)`，各自排好序。目录排在文件前面——
    看结构时先要骨架，文件是细节。"""
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return (), ()
    dirs, files = [], []
    for name in names:
        if is_noise_dir(name):
            continue
        full = os.path.join(path, name)
        # 软链不跟进：与 `search_files` 同一条理由，且列目录时跟进软链
        # 很容易把整个 home 拉进来
        if os.path.islink(full):
            files.append(name)
        elif os.path.isdir(full):
            dirs.append(name)
        else:
            files.append(name)
    return tuple(dirs), tuple(files)


def render_tree(root: str, depth: int = DEFAULT_DEPTH,
                max_entries: int = MAX_ENTRIES) -> str:
    """把一棵目录树渲染成文本。纯函数，同一棵树渲染两次逐字相同。

    **预算按层分配（广度优先），不按深度优先**。这一条是造它的时候撞出来的：
    第一版是深度优先 + 一个全局上限，在本仓库上跑出来的结果是 `src/` **整个没出现**
    ——字母序在前的 `docs/` `evals/` `knowledge/` `pai_playground/` 把 120 项吃光了，
    而提示语只说「还有 N 项未列出」。也就是说最重要的那个目录可以完全消失，
    且消失得看不出来。广度优先保证第一层永远完整，深的层次才去抢剩下的预算。

    稳定性是硬要求：这份文本会进 system prompt，而不稳定的前缀会让每个会话的
    缓存前缀都不同（feature 22「护住缓存前缀」那条规矩）。
    所以每一层都排序，绝不依赖 `os.listdir` 的返回顺序。
    """
    chosen = {}                 # 目录绝对路径 -> (子目录, 文件, 未列出的文件数)
    used, dropped = 0, 0
    frontier = [(root, 0)]
    while frontier and used < max_entries:
        nxt = []
        for path, level in frontier:
            dirs, files = _entries(path)
            take_dirs, take_files = [], []
            for name in dirs:
                if used >= max_entries:
                    dropped += 1
                    continue        # 目录被挤掉了，这条要计数（子树整个不见了）
                take_dirs.append(name)
                used += 1
                if level + 1 < depth:
                    nxt.append((os.path.join(path, name), level + 1))
            for name in files[:MAX_FILES_PER_DIR]:
                if used >= max_entries:
                    continue
                take_files.append(name)
                used += 1
            omitted_here = len(files) - len(take_files)
            dropped += omitted_here
            chosen[path] = (take_dirs, take_files, omitted_here)
        frontier = nxt

    lines: List[str] = []

    def render(path: str, level: int) -> None:
        picked = chosen.get(path)
        if picked is None:
            return
        take_dirs, take_files, rest = picked
        for name in take_dirs:
            lines.append(INDENT * level + name + "/")
            render(os.path.join(path, name), level + 1)
        for name in take_files:
            lines.append(INDENT * level + name)
        if rest > 0:
            lines.append(INDENT * level + f"…（另有 {rest} 个文件）")

    render(root, 0)
    if not lines:
        return "（空目录）"
    out = "\n".join(lines)
    if dropped:
        # 截断了必须说清截了多少、去哪看（同 read_file / bash 超时那条规矩）
        # 截断了必须说清截了多少、去哪看。**每个目录里省掉的文件也算进来**——
        # 只报全局那一笔的话，「每个目录都省了 50 个文件」会显示成「0 项未列出」。
        out += (f"\n[另有至少 {dropped} 项未列出（深度 {depth}，"
                f"每个目录最多列 {MAX_FILES_PER_DIR} 个文件）；"
                f'用 list_dir(path="子目录", depth=2) 看具体]')
    return out


@tool
def list_dir(
    path: Annotated[str, "可选：要看的目录。空 = 当前工作目录"] = "",
    depth: Annotated[int, "可选：往下看几层。0 = 用默认（2 层）"] = 0,
) -> str:
    """列出一个目录的结构（子目录与文件），用来了解项目长什么样。"""
    if depth < 0:
        # 静默改用默认值 = 模型永远不知道自己传错了（同 bash 的负 timeout）
        return f"错误：depth 不能是负数（收到 {depth}），未列出。"
    root = list_root({"path": path})
    if not os.path.exists(root):
        return f"错误：{root} 不存在。"
    if not os.path.isdir(root):
        return f"错误：{root} 是文件不是目录；要看内容用 read_file。"
    return render_tree(root, min(depth or DEFAULT_DEPTH, MAX_DEPTH))


# ---- 接线（照 feature 43 的 roots.py，不写第四份「默认根解析 + matcher 包装」）----

list_root, list_dir_matcher = path_semantics("path")
matcher_for(list_dir)(list_dir_matcher)
path_access_for(list_dir, READ)(list_root)
capabilities_for(list_dir, read_only=True, concurrency_safe=True)
