"""搜索工具（feature 41 Task 2）。

上游需求：找代码此前只能走 bash，而 bash 默认 ask、会被问到烦；一旦配 allow
白名单绕开询问，bash 就绕过了工作目录边界（D#52 的已知洞）。新立一个有名字的
工具，是为了让它能挂 `path_access_for` / `capabilities_for`——权限层与调度器
认得它，于是「界内不问」与「可并发」都不必靠用户配规则换。

本文件分三段：搜索行为本身、错误路径、以及**接线**。第三段看着像元测试，
其实是最要紧的：漏声明的后果是静默的（边界那边退回 ask，调度那边退回串行），
不钉住的话回归时没有任何东西会变红。
"""
import json
import os
import re

import pytest

from pai.core import permissions
from pai.core.permissions import RuleSet
from pai.core.tools import READ, all_tools, get_tools


def _tree(root):
    """一棵最小但踩到各种坑的树：中文、噪音目录、子目录同名符号。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir()
    (root / "src" / "loop.py").write_text(
        "def run_agent():\n    pass\n\n\ndef helper():\n    return 1\n", encoding="utf-8")
    (root / "src" / "tools.py").write_text(
        "def run_agent_shim():\n    # 中文注释：调用 run_agent\n    pass\n", encoding="utf-8")
    (root / "notes.md").write_text("文档里也写着 run_agent 这个名字\n", encoding="utf-8")
    noise = root / "__pycache__"
    noise.mkdir()
    (noise / "loop.cpython-39.pyc").write_text("run_agent 编译产物\n", encoding="utf-8")
    return root


# ---- 搜索行为 ----


def test_finds_matches_and_reports_file_and_line(tmp_path):
    """一条命中要能直接跳过去：文件、行号、原行三样缺一不可。

    只回文件名的话模型还得再 read_file 一次去找位置——那正是本轮要省掉的一轮。
    """
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    out = search_files(pattern=r"def run_agent\b", path=str(tmp_path))

    assert "src/loop.py:1:" in out.replace(str(tmp_path) + os.sep, "")
    assert "def run_agent():" in out


def test_glob_filters_which_files_are_searched(tmp_path):
    """glob 是文件名过滤，不是内容过滤——限定 *.py 后 md 里的同名字样不该出现。"""
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    out = search_files(pattern="run_agent", path=str(tmp_path), glob="*.py")

    assert "loop.py" in out
    assert "notes.md" not in out


def test_noise_directories_are_skipped(tmp_path):
    """__pycache__ 这类目录里的命中是噪音：它会把真结果挤出上限。"""
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    out = search_files(pattern="run_agent", path=str(tmp_path))

    assert "__pycache__" not in out


def test_an_empty_pattern_lists_the_files_matching_the_glob(tmp_path):
    """空 pattern = 只按文件名找（「permissions.py 在哪」是日常开发的高频问题）。

    不做这一格的话，找文件仍然只能回去走 bash，而那正是本轮要收回来的活。
    """
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    out = search_files(pattern="", path=str(tmp_path), glob="*.py")

    assert "loop.py" in out and "tools.py" in out
    assert "notes.md" not in out


def test_binary_files_are_skipped_not_crashed_on(tmp_path):
    """二进制文件读进来会 UnicodeDecodeError——工具错误不 throw，但也不该少读别的文件。"""
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01run_agent\xff\xfe")
    out = search_files(pattern="run_agent", path=str(tmp_path))

    assert "loop.py" in out          # 别的文件照样搜到
    assert "blob.bin" not in out


def test_max_results_caps_the_output_and_says_so(tmp_path):
    """截断了必须说，且要给出路——同 read_file / bash 超时那条规矩。"""
    from pai.core.tools.search import search_files

    root = tmp_path / "many"
    root.mkdir()
    for i in range(30):
        (root / f"f{i}.py").write_text("needle\n", encoding="utf-8")

    out = search_files(pattern="needle", path=str(root), max_results=5)
    assert len([ln for ln in out.splitlines() if ":1:" in ln]) == 5
    assert "截断" in out or "更多" in out


def test_a_file_that_decodes_but_holds_nul_bytes_is_also_skipped(tmp_path):
    """二进制的第二格：NUL 是合法的 UTF-8 码点，解码这一关拦不住它。

    这条测试是注入反证逼出来的——删掉 NUL 检查时上一条测试照样绿，
    因为它那个文件里的 `\xff\xfe` 让 UnicodeDecodeError 先接管了。
    实现没错，是覆盖漏了一格（K engineering/mutation-testing-pitfalls 第五条：
    反证不红时先怀疑实现，查下来实现是对的，那就是测试的问题）。
    """
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    (tmp_path / "nul.dat").write_bytes("\x00run_agent\x00".encode("utf-8"))
    out = search_files(pattern="run_agent", path=str(tmp_path))

    assert "loop.py" in out
    assert "nul.dat" not in out


def test_many_matches_inside_one_file_still_respect_max_results(tmp_path):
    """上限是**总条数**上限，不是「每个文件一条」。

    同样是注入反证逼出来的：删掉文件内那个 break 时，上一条测试照样绿——
    它那 30 个文件每个只有一处命中，外层的 break 就够了。
    一个文件里多处命中才走得到内层，而那正是真实代码库的常态。
    """
    from pai.core.tools.search import search_files

    (tmp_path / "one.py").write_text("needle\n" * 50, encoding="utf-8")
    out = search_files(pattern="needle", path=str(tmp_path), max_results=5)

    assert len([ln for ln in out.splitlines() if ln.startswith("one.py:")]) == 5


def test_no_match_says_so_instead_of_returning_nothing(tmp_path):
    """空结果与「工具没跑」在模型眼里必须分得开。"""
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    out = search_files(pattern="绝不会出现的字样", path=str(tmp_path))
    assert out.strip()
    assert "没有" in out or "0" in out


def test_symlinks_pointing_outside_the_search_root_are_skipped(tmp_path):
    """拍板问 3 认下的那条诚实边界的兑现。

    权限层判的是**搜索根**这一个路径，而遍历会读到根下每个文件。根在界内、
    树里有一条指向界外的软链时，判定管不到——所以遍历自己得跳过它。
    不跳的话，`search_files(path=".")` 就成了读取任意目录的通道，
    而且是在权限层已经放行之后，没有任何一层还会看它。
    """
    from pai.core.tools.search import search_files

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("run_agent 的秘密\n", encoding="utf-8")

    inside = _tree(tmp_path / "inside")
    os.symlink(str(outside), str(inside / "escape"))
    # 目录软链那条 `os.walk(followlinks=False)` 本来就不会跟进——只测它等于
    # 让这条测试因为错的理由变绿（K engineering/mutation-testing-pitfalls）。
    # **文件软链** os.walk 是会列出来的，那才是真正需要显式跳过的那一格。
    os.symlink(str(outside / "secret.py"), str(inside / "src" / "escape.py"))

    out = search_files(pattern="run_agent", path=str(inside))
    assert "loop.py" in out
    assert "escape" not in out, "指向搜索根之外的文件软链没被跳过"
    assert "secret" not in out, "指向搜索根之外的软链没被跳过"


def test_a_single_file_can_be_the_search_root(tmp_path):
    """path 指向一个文件时就搜那个文件（feature 46，45-A2 实测发现）。

    真跑里模型第三次走 bash 干的正是这件事：`grep -n 'X' src/.../output.py`
    ——它已经知道文件在哪，只想在里面找一行，而 `search_files` 当场报
    「搜索根不是目录」。于是「找代码用 search_files」这条引导在最该生效的
    时候失效，模型只能退回 bash（并弹一次窗）。
    """
    from pai.core.tools.search import search_files

    f = tmp_path / "one.py"
    f.write_text("alpha\nbeta = 2\ngamma\n", encoding="utf-8")

    out = search_files(pattern=r"beta", path=str(f))
    assert "one.py:2:beta = 2" in out


def test_searching_a_single_file_finds_nothing_gracefully(tmp_path):
    from pai.core.tools.search import search_files

    f = tmp_path / "one.py"
    f.write_text("alpha\n", encoding="utf-8")
    out = search_files(pattern="不存在的字样", path=str(f))
    assert "没有找到" in out


def test_a_single_file_root_still_respects_the_glob(tmp_path):
    """给了 glob 又指了一个不匹配的文件：该是「没找到」，不是「无视 glob」。"""
    from pai.core.tools.search import search_files

    f = tmp_path / "one.py"
    f.write_text("beta\n", encoding="utf-8")
    assert "没有找到" in search_files(pattern="beta", path=str(f), glob="*.md")
    assert "one.py:1:beta" in search_files(pattern="beta", path=str(f), glob="*.py")


def test_directory_behaviour_is_byte_for_byte_unchanged(tmp_path):
    """回归守卫：吃单个文件这件事，不许改变它吃目录时的任何一个字。"""
    from pai.core.tools.search import search_files

    _tree(tmp_path)
    assert search_files(pattern="run_agent", path=str(tmp_path), glob="*.py") == (
        "src/loop.py:1:def run_agent():\n"
        "src/tools.py:1:def run_agent_shim():\n"
        "src/tools.py:2:    # 中文注释：调用 run_agent")


# ---- 错误路径 ----


def test_a_bad_regex_is_reported_not_raised(tmp_path):
    """错误路径一：模型写坏正则是常态，要告诉它坏在哪，而不是抛。"""
    from pai.core.tools.search import search_files

    out = search_files(pattern="([unclosed", path=str(tmp_path))
    assert "错误" in out
    assert "正则" in out


def test_a_missing_search_root_is_reported(tmp_path):
    """错误路径二：搜索根不存在。

    这条原本还断言「path 是文件也算错」，那一半在 feature 46 被**刻意放开**了
    ——feature 45 真跑证明它挡住的是一个合法且高频的用法（在已知文件里找一行），
    于是模型被逼回 bash。放开之后这里只剩「不存在」一种错。
    """
    from pai.core.tools.search import search_files

    out = search_files(pattern="x", path=str(tmp_path / "nope"))
    assert "错误" in out and "不存在" in out


def test_a_negative_max_results_is_reported_not_silently_ignored():
    """错误路径三：静默改用默认值 = 模型永远不知道自己传错了（同 bash 的负 timeout）。"""
    from pai.core.tools.search import search_files

    assert "错误" in search_files(pattern="x", max_results=-1)


# ---- 接线（漏声明的后果是静默的，所以必须机器钉住）----


def test_the_tool_is_registered_in_the_default_set():
    assert "search_files" in get_tools()
    assert "search_files" in all_tools()


def test_the_schema_is_generated_from_the_signature():
    """0 哨兵与默认值的落点：只有 pattern 是必填。"""
    fn = get_tools()["search_files"].schema()["function"]
    props = fn["parameters"]["properties"]
    assert set(props) == {"pattern", "path", "glob", "max_results"}
    assert fn["parameters"]["required"] == ["pattern"]
    assert props["max_results"]["type"] == "integer"
    assert all(props[k]["description"] for k in props)


def test_it_declares_path_semantics_so_the_boundary_can_see_it():
    """漏了这两项声明，`participates_in_boundary()` 就是 False，兜底直接 ask。"""
    t = all_tools()["search_files"]
    assert t.participates_in_boundary()
    assert t.access == READ


def test_the_declared_path_resolves_the_default_root(tmp_path, monkeypatch):
    """不传 path 时 getter 必须回落到 cwd，不能回空串。

    回空串的话边界判定拿不到路径，`paths_all_inside(())` 为假 → 兜底 ask，
    于是「不传 path 的搜索每次都被问」——而这是模型最常见的调用形态。
    这条 bug 只会表现为「怎么老问我」，不会让任何别的测试变红。
    """
    monkeypatch.chdir(tmp_path)
    t = all_tools()["search_files"]
    assert os.path.abspath(t.get_path({"pattern": "x"})) == os.path.realpath(str(tmp_path))


def test_it_declares_capabilities_so_the_scheduler_can_batch_it():
    """漏了这两项，调度**静默**退回串行——慢，且没有任何东西会变红。"""
    t = all_tools()["search_files"]
    assert t.read_only({"pattern": "x"}) is True
    assert t.concurrency_safe({"pattern": "x"}) is True


def test_it_batches_in_parallel_next_to_read_file():
    """接到真调度器上验一遍：声明对了不等于批得起来。"""
    from pai.core.scheduler import partition

    class _Fn:
        def __init__(self, name, args):
            self.name, self.arguments = name, json.dumps(args)

    class _TC:
        def __init__(self, name, args):
            self.function = _Fn(name, args)

    batches = partition(
        [_TC("search_files", {"pattern": "x"}), _TC("read_file", {"path": "a.py"})],
        all_tools(),
    )
    assert len(batches) == 1 and batches[0].parallel is True


def test_searching_inside_the_working_dir_is_allowed_without_asking(tmp_path, monkeypatch):
    """本轮的核心验收：界内搜索一次都不问，且不需要用户配任何 allow 规则。

    走的是求值链第 7 步 `_boundary_fallback` 的「读 → 界内 allow」。
    """
    monkeypatch.chdir(tmp_path)
    d = permissions.decide(
        "search_files", {"pattern": "x", "path": str(tmp_path)},
        RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "allow", d.reason

    # 不传 path 的形态同样不问（模型最常见的调用）
    d2 = permissions.decide(
        "search_files", {"pattern": "x"}, RuleSet.from_lists(), cwd=str(tmp_path))
    assert d2.kind == "allow", d2.reason


def test_searching_outside_the_working_dir_still_asks(tmp_path, monkeypatch):
    """另一半：界外要问。只做前一半的话这个工具就成了越界读取的通道。"""
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()

    d = permissions.decide(
        "search_files", {"pattern": "x", "path": str(outside)},
        RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "ask", d.reason


def test_a_deny_rule_can_target_the_search_root(tmp_path, monkeypatch):
    """matcher 复用 fs 的 path_matcher：规则里的路径 specifier 要对搜索根生效。

    没挂 matcher 的话吃的是 `default_matcher`（对**第一个参数值**做通配符匹配），
    而这个工具的第一个参数是 pattern——规则会拿正则去比对路径 pattern，静默不命中。
    """
    monkeypatch.chdir(tmp_path)
    secrets = tmp_path / "secrets"
    secrets.mkdir()

    rules = RuleSet.from_lists(deny=["search_files(//%s/**)" % str(secrets).lstrip("/")])
    d = permissions.decide(
        "search_files", {"pattern": "x", "path": str(secrets / "sub")},
        rules, cwd=str(tmp_path))
    assert d.kind == "deny", d.reason
