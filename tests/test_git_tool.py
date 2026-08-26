"""`git_read` 工具（feature 42 Task 3）。

形状是拍板问 2·A：一个工具 + 子命令白名单，argv 由 pai 自己拼、**不过 shell**。
「不过 shell」不是省事，是把一整类攻击面从「要靠拆分匹配拦住」变成
「结构上构造不出来」——`git status; rm -rf x` 在这里根本不是一条命令，
是三个被当成 pathspec 的字符串。

实现时对拍板做了一处收紧并记在档案里：flag 从黑名单改成**按子命令的白名单**。
拍板时我把代价写成「黑名单漏一个 flag 就是一个洞」，白名单没有这个失效模式——
漏写只会让某个合法 flag 被拒（模型收到一句话就能改），方向反过来了。
"""
import json
import os
import subprocess

import pytest

from pai.core import permissions
from pai.core.permissions import RuleSet
from pai.core.tools import EXEC, all_tools, get_tools


def _repo(root):
    """造一个最小的真 git 仓库。用真 git 而不是伪造 .git：这个工具的全部行为
    都在「怎么调 git」上，伪造掉 git 就等于把被测的东西测没了。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    run = lambda *a: subprocess.run(a, cwd=str(root), env=env,
                                    capture_output=True, text=True, check=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    run("git", "add", "a.py")
    run("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "首条提交")
    return root


# ---- argv 怎么拼（纯函数，单独可测）----


def test_argv_never_goes_through_a_shell_and_disables_the_pager():
    """`--no-pager` 要在子命令**之前**——它是全局 flag，放后面 git 不认。"""
    from pai.core.tools.git_tool import build_argv

    assert build_argv("status", "") == ["git", "--no-pager", "status"]
    assert build_argv("status", "-s")[:4] == ["git", "--no-pager", "status", "-s"]


def test_diff_family_disables_external_diff_drivers():
    """`--no-ext-diff`：仓库的 .gitattributes/config 能配外部 diff 驱动，
    那是一条「读一个仓库就跑到别人的程序」的路。三个吃 diff 选项的子命令都要关。"""
    from pai.core.tools.git_tool import build_argv

    for sub in ("diff", "show", "log"):
        assert "--no-ext-diff" in build_argv(sub, "")


def test_a_write_subcommand_is_refused_and_says_where_to_go():
    """写操作一律不进白名单——与 AGENTS「永远不要未经要求就 commit」一致。"""
    from pai.core.tools.git_tool import git_read

    out = git_read(subcommand="commit", args="-m x")
    assert "错误" in out
    assert "commit" in out
    assert "bash" in out, "没告诉模型写操作该走哪条路（仍是 bash 的 ask）"


def test_dangerous_global_flags_are_refused():
    """git 自己的注入面：这些 flag 能借 git 跑任意命令或换掉目标仓库。

    `-c core.pager='sh -c …'`、`--exec-path` 换 git 子命令的查找路径、
    `-C` / `--git-dir` / `--work-tree` 直接把工作对象挪到边界之外。
    """
    from pai.core.tools.git_tool import git_read

    for bad in ("-c core.pager=x", "--exec-path=/tmp", "-C /etc",
                "--git-dir=/tmp/x", "--upload-pack=sh", "--output=/tmp/x"):
        out = git_read(subcommand="status", args=bad)
        assert "错误" in out, f"{bad} 没被拒"


def test_an_unlisted_flag_is_refused_and_the_message_lists_what_is_allowed():
    """白名单的失效方向：漏写只会让合法 flag 被拒，而错误文案要让模型一步改对。"""
    from pai.core.tools.git_tool import git_read

    out = git_read(subcommand="log", args="--这个flag不存在")
    assert "错误" in out
    assert "--oneline" in out, "没列出这个子命令允许的 flag"


def test_unbalanced_quotes_are_reported_not_raised():
    """错误路径：模型写出不闭合的引号是常态，要报出来而不是抛。"""
    from pai.core.tools.git_tool import git_read

    out = git_read(subcommand="status", args="'没闭合")
    assert "错误" in out


# ---- 真跑 git ----


def test_status_and_log_actually_run(tmp_path, monkeypatch):
    from pai.core.tools.git_tool import git_read

    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    assert "a.py" in git_read(subcommand="ls-files")
    assert "首条提交" in git_read(subcommand="log", args="--oneline")

    (repo / "a.py").write_text("print(2)\n", encoding="utf-8")
    assert "a.py" in git_read(subcommand="status", args="-s")
    assert "print(2)" in git_read(subcommand="diff")


def test_a_semicolon_cannot_smuggle_a_second_command(tmp_path, monkeypatch):
    """不过 shell 的实证。这条不是断言「被拦下了」，是断言**第二条命令根本没跑**。

    分隔符拆分匹配（bash 那边的做法）能拦住看得见的形态，拦不住 `$(...)`
    与变量拼接；argv 直传则连「有第二条命令」这个概念都不存在。
    """
    from pai.core.tools.git_tool import git_read

    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    git_read(subcommand="status", args="; touch 被注入了")
    assert not (repo / "被注入了").exists(), "分号后面的东西真的跑了"


def test_the_exit_code_is_reported(tmp_path, monkeypatch):
    """git 非 0 退出（不在仓库里、pathspec 不匹配）与「工具没跑」要分得开。"""
    from pai.core.tools.git_tool import git_read

    monkeypatch.chdir(tmp_path)             # 不是 git 仓库
    out = git_read(subcommand="status")
    assert "退出码" in out and "0]" not in out.splitlines()[-1]


# ---- 接线 ----


def test_the_tool_is_registered_and_its_schema_is_generated():
    fn = get_tools()["git_read"].schema()["function"]
    props = fn["parameters"]["properties"]
    assert set(props) == {"subcommand", "args"}
    assert fn["parameters"]["required"] == ["subcommand"]
    assert "status" in props["subcommand"]["description"], "schema 里没列出可用子命令"


def test_it_declares_exec_like_run_tests():
    t = all_tools()["git_read"]
    assert t.participates_in_boundary()
    assert t.access == EXEC, "它同样是起一个进程，写成 READ 是同一类谎的小号版本"


def test_concurrency_safety_depends_on_the_subcommand():
    """能力标志**收 input** 的第一个真实用户（框架早留了签名，一直没人用）。

    `log` / `show` 是纯读；`status` / `diff` 会刷新索引、要拿 `.git/index.lock`——
    两个并发跑会撞锁。静态布尔表达不了这个区别，只能二选一：
    全写 True 会真的撞锁，全写 False 则白白放掉可并发的那一半。
    """
    t = all_tools()["git_read"]
    assert t.read_only({"subcommand": "status"}) is True
    assert t.concurrency_safe({"subcommand": "log"}) is True
    assert t.concurrency_safe({"subcommand": "status"}) is False
    assert t.concurrency_safe({"subcommand": "diff"}) is False


def test_two_log_reads_batch_but_status_does_not():
    from pai.core.scheduler import partition

    class _Fn:
        def __init__(self, name, args):
            self.name, self.arguments = name, json.dumps(args)

    class _TC:
        def __init__(self, name, args):
            self.function = _Fn(name, args)

    both_log = partition([_TC("git_read", {"subcommand": "log"}),
                          _TC("git_read", {"subcommand": "log"})], all_tools())
    assert len(both_log) == 1 and both_log[0].parallel

    with_status = partition([_TC("git_read", {"subcommand": "status"}),
                             _TC("git_read", {"subcommand": "status"})], all_tools())
    assert len(with_status) == 2


def test_reading_git_inside_the_working_dir_is_allowed_without_asking(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = permissions.decide("git_read", {"subcommand": "status"},
                           RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "allow", d.reason


def test_a_deny_rule_can_still_turn_it_off(tmp_path, monkeypatch):
    """裸名 deny 要能关掉整个工具——这是用户唯一的总开关。"""
    monkeypatch.chdir(tmp_path)
    d = permissions.decide("git_read", {"subcommand": "status"},
                           RuleSet.from_lists(deny=["git_read"]), cwd=str(tmp_path))
    assert d.kind == "deny", d.reason
