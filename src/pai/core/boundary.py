"""工作目录边界（feature 09）：pai 允许 agent 碰哪些目录。

这一层补的是 feature 07 缺的**策略**——07 交付了规则引擎（三态求值、匹配下放），
但兜底是个常量 `allow`，于是不配置就等于没有权限层。
CC 的对应实现里根本没有「默认决策常量」：兜底是 `in_working_dir ? allow : ask`
（`filesystem.ts` 第 6 步与第 12 步）。本模块提供那个 `in_working_dir`。

**两条最容易写错的，都钉了测试**：

1. **前缀不等于包含**。`/tmp/proj-evil`.startswith(`/tmp/proj`) 是 True，
   但它显然不在 `/tmp/proj` 里。必须比到**路径分隔符边界**。
2. **边界锚在启动 cwd，相对路径却按当前 cwd 解析**——两者不同是故意的：
   - 边界用启动 cwd（照 CC 的 `getOriginalCwd()`）：agent 中途 `cd` 出去不该
     把边界一起带跑；
   - 相对路径用当前 cwd：工具真正打开的就是那个路径。若也按启动 cwd 解析，
     `cd /etc` 后 `read_file("passwd")` 会被算成 `<proj>/passwd`（界内、放行），
     而实际读到 `/etc/passwd`——一条 cd 逃逸。

纯函数，不 import permissions（反向依赖：permissions 用它）。
符号链接双路径在 Task 4 补——本模块此刻只看给定路径。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence


def _normalize(path: str) -> str:
    """绝对化 + 归一化。相对路径按**进程当前 cwd** 解析，理由见模块 docstring。

    刻意不 realpath：符号链接双路径是 Task 4 的事，只做一半比不做更误导。
    """
    return os.path.normpath(os.path.abspath(path))


def path_in_working_path(path: str, working_path: str) -> bool:
    """`path` 是否落在 `working_path` 之内（含相等）。

    比到**分隔符边界**，不是字符串前缀——否则 `/tmp/proj-evil` 会被判成
    在 `/tmp/proj` 内（`test_prefix_is_not_enough` 钉死这条）。
    """
    if not path or not working_path:
        return False                    # 判不出来就不算界内，不默认放行
    target = _normalize(path)
    base = _normalize(working_path)
    if target == base:
        return True
    return target.startswith(base.rstrip(os.sep) + os.sep)


@dataclass(frozen=True)
class WorkingDirs:
    """允许 agent 活动的目录集合：启动 cwd + 配置里的 additionalDirectories。

    `startup_cwd` 在**装配期**捕获一次（`from_startup()`），此后进程 `cd` 到哪
    都不改变它——这正是 CC `getOriginalCwd()` 的语义。
    """

    startup_cwd: str
    additional: tuple = field(default_factory=tuple)

    @classmethod
    def from_startup(
        cls, cwd: Optional[str] = None, additional: Sequence[str] = ()
    ) -> "WorkingDirs":
        return cls(
            startup_cwd=_normalize(cwd if cwd is not None else os.getcwd()),
            additional=tuple(_normalize(d) for d in additional),
        )

    def all(self) -> tuple:
        return (self.startup_cwd,) + tuple(self.additional)

    def contains(self, path: str) -> bool:
        return any(path_in_working_path(path, base) for base in self.all())


def paths_all_inside(paths: Iterable[str], dirs: WorkingDirs) -> bool:
    """**每一条**路径都必须在界内（CC 用 `.every`）。

    空集合返回 False：拿不到任何可判定的路径时，「判不出来」不等于「没问题」。
    Task 4 的符号链接双路径会用到这条——原始路径与 realpath 解析后的路径
    都必须干净，任一在界外就算越界。
    """
    checked = [p for p in paths if p]
    if not checked:
        return False
    return all(dirs.contains(p) for p in checked)
