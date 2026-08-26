"""工具的「这次调用碰哪个根目录」（feature 43 Task 1）。

`search_files` / `run_tests` / `git_read` 三个工具各自写过一份形状一模一样的
根解析 + 一份形状一模一样的 matcher 包装，两天内写出了三份。抽在这里。

抽的不只是重复代码，还有**两个容易各自写错的判断**：

一、空路径要回落到 cwd，不能回空串。回空串的后果是静默的：边界判定拿不到路径
就退回 ask，于是「不传 path」这个最常见的调用形态每次都弹窗，而没有任何测试
会因此变红（三个工具各有一条测试专门钉这个，就是因为它复发过三次）。

二、**没有路径参数的工具要无视 args**。`git_read` 的 schema 里没有 `path`，
但模型发来的 arguments 不受 schema 约束——它可以发任何东西。照单全收的话，
权限层会去判一个「这次调用根本不会碰」的路径，而 git 实际仍跑在 cwd
（`-C` 在它的拒绝名单里，它换不了目录）。判定的路径与实际跑的路径不是同一个，
比判错更糟：判错至少还是在判这次调用，这是在判另一次调用。
抽取之前这条只体现为「`repo_root` 的实现碰巧不读 args」，现在是一个显式参数。
"""

import os
from typing import Callable, Optional

from pai.core.tools import MatchContext, Matcher, PathGetter
from pai.core.tools.fs import path_matcher


def root_getter(param: Optional[str] = "path") -> PathGetter:
    """造一个 `get_path`：从 `args[param]` 取根，空则回落 cwd，绝对化。

    `param=None` = 这个工具没有路径参数，永远用 cwd（见模块 docstring 第二条）。
    """
    def get(args: dict) -> str:
        # 诚实边界（注入反证逼出来的，档案 43 devlog 有记）：`param` 那半是
        # **写给读代码的人看的，不是机制**。真正让 `param=None` 无视 args 的是
        # `args.get(None)` 本来就取不到任何东西——把 `param and` 删掉，
        # 行为一个字都不变，没有任何输入能把两者区分开。
        # 留着是因为「这个工具没有路径参数」该在代码里说出口；
        # 但别以为它在防什么，它防不住的东西 `args.get` 已经先挡了。
        value = str(args.get(param) or "") if (param and isinstance(args, dict)) else ""
        return os.path.abspath(value or os.getcwd())

    return get


def root_matcher(get_path: PathGetter) -> Matcher:
    """把 fs 的 `path_matcher` 包一层，先把默认根解出来再交给它。

    不能直接挂 `path_matcher`：它按 `args["path"]` 取路径，而这三个工具的
    path 可以为空（= cwd）或压根不存在。空串在那边被判成「取不到路径」直接
    返回 False——权限规则对最常见的调用形态静默失效。

    而漏挂 matcher 的后果更隐蔽：吃 `default_matcher`，它比对**第一个参数值**，
    于是路径 specifier 会拿 `pattern` / `filter` / `subcommand` 去比对，
    永远不命中。两种失效都不会让任何别的测试变红。
    """
    def match(specifier: str, args: dict, require_all: bool, ctx: MatchContext) -> bool:
        return path_matcher(specifier, {"path": get_path(args)}, require_all, ctx)

    return match


def path_semantics(param: Optional[str] = "path") -> "tuple":
    """一次给出 `(get_path, matcher)` 两件套——它们必须解出同一个根。

    分开造的话，第四个工具很可能只记得挂一个（这正是前三个工具里
    「getter 与 matcher 各写一份、且必须一致」的那处重复）。
    """
    get = root_getter(param)
    return get, root_matcher(get)
