"""目录结构：`list_dir` 工具与装配期注入共用的那份实现（feature 46）。

出处是 feature 45 的实测发现 A2：`pwd && ls` 是两次真跑里的**第一个**工具调用，
而 pai 没有任何工具能回答「这个项目长什么样」，于是它必然走 bash、必然弹窗。

一份实现两个消费者（拍板问 2·A）：装配期注入开场那份摘要、`list_dir` 兜底
会话中途新建的目录。分成两份写的话，「注入看到的」与「工具看到的」会各说各话。
"""
import json
import os

import pytest

from pai.core.tools import READ, all_tools, get_tools
from pai.core.tools.listing import MAX_ENTRIES, render_tree
from pai.tui.width import display_width


def _project(root):
    (root / "src" / "pai" / "core").mkdir(parents=True)
    (root / "src" / "pai" / "tui").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "pai" / "core" / "loop.py").write_text("", encoding="utf-8")
    (root / "src" / "pai" / "core" / "tools.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_loop.py").write_text("", encoding="utf-8")
    (root / "README.md").write_text("", encoding="utf-8")
    noise = root / "__pycache__"
    noise.mkdir()
    (noise / "x.pyc").write_text("", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("", encoding="utf-8")
    return root


# ---- 树本身 ----


def test_the_tree_shows_directories_and_files(tmp_path):
    _project(tmp_path)
    out = render_tree(str(tmp_path), depth=2)
    assert "src/" in out
    assert "tests/" in out
    assert "README.md" in out


def test_noise_directories_are_skipped(tmp_path):
    """复用 search_files 的 SKIP_DIRS（拍板问 3·A）——两处各写一份名单，
    迟早会出现「搜索跳过了但列目录列出来了」这种自相矛盾。"""
    from pai.core.tools.listing import SKIP_DIRS
    from pai.core.tools.search import SKIP_DIRS as SEARCH_SKIP

    assert SKIP_DIRS is SEARCH_SKIP, "两份名单不是同一个对象，早晚会漂"
    out = render_tree(str(_project(tmp_path)), depth=3)
    assert "__pycache__" not in out and ".git" not in out


def test_depth_limits_how_deep_it_goes(tmp_path):
    _project(tmp_path)
    shallow = render_tree(str(tmp_path), depth=1)
    deep = render_tree(str(tmp_path), depth=3)
    assert "loop.py" not in shallow, "depth=1 不该看到第三层的文件"
    assert "loop.py" in deep


def test_too_many_entries_are_capped_and_it_says_so(tmp_path):
    """截断了必须说清截了多少、去哪看（同 read_file / bash 超时那条规矩）。"""
    big = tmp_path / "many"
    big.mkdir()
    for i in range(MAX_ENTRIES + 40):
        (big / f"f{i}.txt").write_text("", encoding="utf-8")
    out = render_tree(str(big), depth=1)
    assert "未列出" in out or "截断" in out
    assert "list_dir" in out, "没告诉去哪看剩下的"


def test_entries_are_sorted_and_stable(tmp_path):
    """同一棵树渲染两次必须逐字相同——注入进 system prompt 的东西不稳定，
    每个会话的缓存前缀就不同（feature 22 护缓存前缀那条规矩）。"""
    _project(tmp_path)
    assert render_tree(str(tmp_path), depth=3) == render_tree(str(tmp_path), depth=3)


def test_directories_come_before_files(tmp_path):
    _project(tmp_path)
    lines = [l for l in render_tree(str(tmp_path), depth=1).split("\n") if l.strip()]
    kinds = [l.strip().endswith("/") for l in lines if not l.startswith("[")]
    assert kinds == sorted(kinds, reverse=True), f"目录没排在文件前面：{lines}"


# ---- 工具 ----


def test_list_dir_runs(tmp_path, monkeypatch):
    from pai.core.tools.listing import list_dir

    monkeypatch.chdir(_project(tmp_path))
    out = list_dir()
    assert "src/" in out and "tests/" in out


def test_list_dir_defaults_to_cwd(tmp_path, monkeypatch):
    from pai.core.tools.listing import list_dir

    monkeypatch.chdir(_project(tmp_path))
    assert list_dir() == list_dir(path=".")


def test_list_dir_reports_a_missing_path(tmp_path):
    """错误路径一。"""
    from pai.core.tools.listing import list_dir

    assert "错误" in list_dir(path=str(tmp_path / "nope"))


def test_list_dir_rejects_a_negative_depth(tmp_path, monkeypatch):
    """错误路径二：静默改用默认值 = 模型永远不知道自己传错了。"""
    from pai.core.tools.listing import list_dir

    monkeypatch.chdir(_project(tmp_path))
    assert "错误" in list_dir(depth=-1)


def test_list_dir_on_a_file_says_so(tmp_path, monkeypatch):
    """错误路径三：指着一个文件要目录树。"""
    from pai.core.tools.listing import list_dir

    monkeypatch.chdir(_project(tmp_path))
    assert "错误" in list_dir(path="README.md")


# ---- 接线 ----


def test_it_is_registered_with_a_generated_schema():
    fn = get_tools()["list_dir"].schema()["function"]
    props = fn["parameters"]["properties"]
    assert set(props) == {"path", "depth"}
    assert fn["parameters"]["required"] == []
    assert props["depth"]["type"] == "integer"


def test_it_declares_read_and_uses_the_shared_root_helpers():
    """照 feature 43 的 roots.py 接线，不写第四份「默认根解析 + matcher 包装」。"""
    t = all_tools()["list_dir"]
    assert t.participates_in_boundary()
    assert t.access == READ
    assert t.read_only({}) is True and t.concurrency_safe({}) is True


def test_listing_inside_the_working_dir_is_allowed_without_asking(tmp_path, monkeypatch):
    """本轮的核心：开场那一步不许再弹窗。"""
    from pai.core import permissions
    from pai.core.permissions import RuleSet

    monkeypatch.chdir(tmp_path)
    d = permissions.decide("list_dir", {}, RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "allow", d.reason


def test_listing_outside_the_working_dir_still_asks(tmp_path, monkeypatch):
    from pai.core import permissions
    from pai.core.permissions import RuleSet

    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-out"
    outside.mkdir()
    d = permissions.decide("list_dir", {"path": str(outside)},
                           RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "ask", d.reason
