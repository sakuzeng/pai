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

**符号链接双路径**（Task 4，照 CC 的 `getPathsForPermissionCheck`）：
一次算出「原始路径 + realpath 解析后路径」两条，全链共用。
- 边界判定要求**两条都在界内**（名字在界内不算数，真身也得在）；
- deny/ask 规则是**任一脏就拦**、allow 要求**两条都干净**（在 permissions 侧，
  正好是 feature 07 那个 `require_all` 的语义）。
- **工作目录本身也要用同一个函数解析**，否则误拒：工作目录给的是软链时，
  待查路径解析后永远匹配不上未解析的工作目录。

纯函数，不 import permissions（反向依赖：permissions 用它）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence


def _normalize(path: str) -> str:
    """绝对化 + 归一化。相对路径按**进程当前 cwd** 解析，理由见模块 docstring。

    这一步刻意**不** realpath：解析交给 `get_paths_for_permission_check`，
    它要同时留住原始路径与解析后路径两条。在这里就 realpath 会把原始路径弄丢。
    """
    return os.path.normpath(os.path.abspath(path))


def get_paths_for_permission_check(path: str) -> tuple:
    """一条路径展开成「原始 + realpath 解析后」两条，相同则去重成一条。

    照 CC：算一次、全链共用（CC 注释说不这么做是每次检查 30 次 syscall）。
    悬空软链、权限不足都不能炸——判定期拿到脏输入是常态，退回只用原始路径。
    """
    if not path:
        return ()
    norm = _normalize(path)
    try:
        real = os.path.realpath(norm)
    except OSError:
        return (norm,)
    return (norm,) if real == norm else (norm, real)


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

    def all_resolved(self) -> tuple:
        """工作目录也展开成双路径。不这么做会**误拒**：
        工作目录是软链时，待查路径 realpath 之后匹配不上未解析的工作目录
        （CC 注释举的例子是 macOS 的 `/System/Volumes/Data/...`）。"""
        out: list = []
        for base in self.all():
            out.extend(get_paths_for_permission_check(base))
        return tuple(dict.fromkeys(out))          # 去重且保序

    def _contains_one(self, path: str) -> bool:
        return any(path_in_working_path(path, base) for base in self.all_resolved())

    def contains(self, path: str) -> bool:
        """**两条路径都必须在界内**——名字在界内不算数，软链的真身也得在。"""
        candidates = get_paths_for_permission_check(path)
        if not candidates:
            return False
        return all(self._contains_one(p) for p in candidates)


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


# ---- 危险路径清单（Task 5，照 CC 的 DANGEROUS_FILES / DANGEROUS_DIRECTORIES）----
#
# 挡的是**持久化位点**：写进去之后，即使 pai 退出、即使权限规则改回来，
# 那段代码仍会在下一次开 shell / 下一次 git 操作时执行。
# 所以它必须 **bypass 免疫**——再怎么放行也拦。
#
# 只挡**写**不挡读：挡读会让 agent 连自己的配置都看不了，而读走漏的风险
# 由工作目录边界那层管（`~/.ssh` 本来就在界外）。

# 家目录下的具体文件
_DANGEROUS_HOME_FILES = (".bashrc", ".zshrc", ".bash_profile", ".zprofile", ".profile")
# 家目录下整个挡掉的子目录
_DANGEROUS_HOME_DIRS = (".ssh",)
# 任意位置只要路径里有这一段就挡（git hooks 在任何仓库里都是执行点；
# skills 目录同理——写进去的 SKILL.md 在后续会话自动指挥模型，用户级
# `~/.pai/skills` 与项目级 `<根>/.pai/skills` 一个模式全覆盖，feature 28 问 1·A）
_DANGEROUS_ANYWHERE = (os.path.join(".git", "hooks"), os.path.join(".pai", "skills"))


def dangerous_writes_description() -> list:
    """危险写清单的人话版（feature 33，09 遗留 3）：清单硬编码且此前完全
    不可见，用户撞上才知道——至少 `/permissions` 该列出来。逐条与
    `is_dangerous_write` 的判定同源（改判定记得改这里，有测试互钉）。"""
    return [
        f"~/ 下的 shell 配置文件：{'、'.join(_DANGEROUS_HOME_FILES)}",
        f"~/ 下整个目录：{'、'.join(_DANGEROUS_HOME_DIRS)}",
        f"任意位置含此路径段：{'、'.join(_DANGEROUS_ANYWHERE)}",
        "pai 自己的设置：任意 .pai/settings.json（否则改自己权限就是提权路径）",
    ]


def is_dangerous_write(path: str, home: Optional[str] = None) -> bool:
    """这个路径是不是「写进去就等于拿到后续执行权」的持久化位点。

    `~/.pai/settings.json` 也在内：不挡的话，「帮我把这条规则加进 settings」
    就是一条合法的提权路径——agent 改掉自己的权限规则，下一轮就畅通无阻了。
    项目级 `.pai/settings.json` 同理。
    """
    if not path:
        return False
    home_dir = _normalize(home) if home else os.path.expanduser("~")
    # 双路径都查：软链指向 ~/.bashrc 同样要拦（与 deny 规则同款「任一脏就拦」）
    for candidate in get_paths_for_permission_check(path):
        if any(seg in candidate for seg in _DANGEROUS_ANYWHERE):
            return True
        # pai 自己的设置文件（用户级与项目级）
        if os.path.basename(candidate) == "settings.json" and \
                os.path.basename(os.path.dirname(candidate)) == ".pai":
            return True
        rel_parts = candidate[len(home_dir):].lstrip(os.sep).split(os.sep) \
            if candidate.startswith(home_dir) else []
        if rel_parts:
            if len(rel_parts) == 1 and rel_parts[0] in _DANGEROUS_HOME_FILES:
                return True
            if rel_parts[0] in _DANGEROUS_HOME_DIRS:
                return True
    return False
