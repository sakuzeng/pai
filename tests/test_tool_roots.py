"""工具的「默认根解析 + matcher 包装」（feature 43 Task 1）。

三份形状一模一样的实现（`search_root` / `test_root` / `repo_root`，各配一个
同形的 matcher 包装）在两天内被写了出来。本轮抽成一处。

这是**纯结构改动，行为必须逐字不变**——所以本文件的主体不是「新代码对不对」，
而是一张对照表：抽取前的三份实现在这里原样重写一遍，逐个输入比对新旧结果。
「测试还绿」在这里不是判据（三个工具的既有测试本来就绿，抽错了它们多半还绿），
判据是「解析后的值逐字相等」。
"""
import os

import pytest

from pai.core.tools import MatchContext, all_tools


# 抽取前的三份实现，原样抄在这里当**对照组**。它们不许再被 src 引用——
# 抄一份进测试是为了让「行为不变」这句话有个可执行的落点，
# 而不是靠读 diff 确认。
def _old_search_root(args: dict) -> str:
    return os.path.abspath(str(args.get("path") or "") or os.getcwd())


def _old_test_root(args: dict) -> str:
    return os.path.abspath(str(args.get("path") or "") or os.getcwd())


def _old_repo_root(args: dict) -> str:
    return os.path.abspath(os.getcwd())


_CASES = [
    {},
    {"path": ""},
    {"path": "."},
    {"path": "sub"},
    {"path": "sub/deeper"},
    {"path": "/absolute/somewhere"},
    {"path": None},
    {"path": 0},                       # 模型发来的脏输入：假值该等同于「没传」
    {"pattern": "x"},                  # 别的参数不该影响
    {"subcommand": "status"},
]


@pytest.mark.parametrize("args", _CASES)
def test_the_extracted_getter_matches_the_old_ones_verbatim(args, tmp_path, monkeypatch):
    """逐字相等，不是「差不多」。"""
    monkeypatch.chdir(tmp_path)
    tools = all_tools()
    assert tools["search_files"].get_path(args) == _old_search_root(args), args
    assert tools["run_tests"].get_path(args) == _old_test_root(args), args


@pytest.mark.parametrize("args", _CASES)
def test_git_read_still_ignores_args_entirely(args, tmp_path, monkeypatch):
    """`git_read` 那份**本来就无视 args**，抽取后必须还无视。

    这条单独拎出来，是因为它是抽取里唯一一处「三份不完全一样」的地方——
    一不小心统一成「取 args 的 path」，就会出现一个真洞：权限层判的是
    args 里那个路径，而 git 实际跑在 cwd（`-C` 在拒绝名单里，它没法换目录）。
    判定的路径与实际跑的路径不是同一个，比判错更糟。
    """
    monkeypatch.chdir(tmp_path)
    assert all_tools()["git_read"].get_path(args) == _old_repo_root(args), args


@pytest.mark.parametrize("args", _CASES)
def test_the_extracted_matcher_matches_the_old_wrapping_verbatim(args, tmp_path, monkeypatch):
    """matcher 那半同理：包装后的结果要与「先解根再交给 path_matcher」逐字相同。"""
    from pai.core.tools.fs import path_matcher

    monkeypatch.chdir(tmp_path)
    ctx = MatchContext(cwd=str(tmp_path), home=str(tmp_path), anchor=str(tmp_path))
    specifiers = ["//" + str(tmp_path).lstrip("/") + "/**", "/**", "**/nope", str(tmp_path)]

    for name, old_getter in (("search_files", _old_search_root),
                             ("run_tests", _old_test_root),
                             ("git_read", _old_repo_root)):
        tool = all_tools()[name]
        for spec in specifiers:
            for require_all in (True, False):
                expected = path_matcher(spec, {"path": old_getter(args)}, require_all, ctx)
                actual = tool.matches(spec, args, require_all, ctx)
                assert actual == expected, (name, spec, require_all, args)


def test_a_tool_without_a_path_parameter_ignores_stray_args(tmp_path, monkeypatch):
    """抽取顺带堵上的一处：没有路径参数的工具，getter 必须无视 args。

    `git_read` 的 schema 里没有 `path`，但模型发来的 arguments 不受 schema 约束
    （它可以发任何东西）。若 getter 照单全收，权限层就会去判一个
    「这次调用根本不会碰」的路径——而 git 实际仍跑在 cwd。
    """
    from pai.core.tools.roots import root_getter

    monkeypatch.chdir(tmp_path)
    cwd_only = root_getter(param=None)
    assert cwd_only({"path": "/etc"}) == os.path.realpath(str(tmp_path))
