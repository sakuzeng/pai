"""pai 用户级路径的唯一事实源：`~/.pai/projects/<slug>/{memory,sessions}/`。

布局对齐 CC（`~/.claude/projects/-Users-.../`）。起因是用户翻自己的 `~/.pai` 时问
「`2b0a92ef14633a56` 又是什么鬼，为什么不和 cc 一致」——哈希目录名谁也认不出来。

为什么独立成模块而不是塞进 memory.py：`session.py` 也要用，而 session 比 memory 更底层、
不该反向依赖它；塞 config.py 则会让「env 与 client 工厂」变成杂物间。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

USER_DIR = ".pai"
PROJECTS_DIR = "projects"
MEMORY_SUBDIR = "memory"
SESSIONS_SUBDIR = "sessions"


def user_dir(home: Optional[Path] = None) -> Path:
    return (Path(home) if home is not None else Path.home()) / USER_DIR


def _git_root(start: Path) -> Optional[Path]:
    """自己往上找 `.git`，不调 `git rev-parse`——这在启动路径上，不该为此起子进程。"""
    for directory in [start, *start.parents]:
        if (directory / ".git").exists():
            return directory
    return None


def project_slug(cwd: Optional[Path] = None) -> str:
    """项目标识：**git 仓库根**的绝对路径，把分隔符换成 `-`（完全照 CC）。

    取 git 根而非 cwd，是为了让同一仓库的子目录与 worktree 共享一份数据（官方语义）。
    中文路径原样保留——文件系统支持，转义反而不可读。

    **已知碰撞**：`/a-b/c` 与 `/a/b-c` 都变成 `-a-b-c`。CC 有同样的问题（它就是这么拼的）。
    真实概率极低，且一旦加转义目录名就不再和 CC 长得一样，反而丢掉本需求的核心诉求。
    `tests/test_paths.py::test_known_slug_collision_is_documented` 把这条钉成了测试——
    想「顺手修好」的人会先撞见它并读到理由。
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    root = _git_root(cwd) or cwd
    return str(root.absolute()).replace(os.sep, "-")


def projects_root(home: Optional[Path] = None) -> Path:
    """所有项目的父目录。pai 自己只写 `project_dir`（当前项目），
    但 viz 要跨项目列会话——`pai` 与 `pai-viz` 常常不在同一个目录起。"""
    return user_dir(home) / PROJECTS_DIR


def project_dir(cwd: Optional[Path] = None, home: Optional[Path] = None) -> Path:
    return projects_root(home) / project_slug(cwd)


def memory_dir(cwd: Optional[Path] = None, home: Optional[Path] = None) -> Path:
    return project_dir(cwd, home) / MEMORY_SUBDIR


def sessions_dir(cwd: Optional[Path] = None, home: Optional[Path] = None) -> Path:
    return project_dir(cwd, home) / SESSIONS_SUBDIR
