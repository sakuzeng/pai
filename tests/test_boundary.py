"""工作目录边界（feature 09 Task 2）：纯函数，先不接线。

用户那句话的直接落点：「我在当前目录下运行 pai，照理来说上级目录下应该是不能看的」。

两条最容易写错的：
1. **前缀不等于包含**——`/tmp/proj-evil` 不在 `/tmp/proj` 内，但 `startswith` 说在；
2. **边界是启动时的 cwd**，agent 中途 `cd` 出去不该把边界一起带跑（照 CC 的
   `getOriginalCwd()`）。
"""
import os

from pai.core.boundary import WorkingDirs, path_in_working_path, paths_all_inside


def test_path_inside_cwd_is_in_boundary(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)

    assert path_in_working_path(str(proj / "src" / "a.py"), str(proj))
    assert path_in_working_path(str(proj), str(proj))          # 目录自身算界内


def test_parent_directory_is_outside(tmp_path):
    """用户那句话的直接落点。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "outside.txt").write_text("x", encoding="utf-8")

    assert not path_in_working_path(str(tmp_path / "outside.txt"), str(proj))
    assert not path_in_working_path("/etc/passwd", str(proj))


def test_sibling_directory_is_outside(tmp_path):
    proj = tmp_path / "proj"
    other = tmp_path / "other"
    proj.mkdir()
    other.mkdir()

    assert not path_in_working_path(str(other / "x.py"), str(proj))


def test_prefix_is_not_enough(tmp_path):
    """`/tmp/proj-evil` **不在** `/tmp/proj` 内——但朴素 startswith 会说在。

    这是个真实的经典洞：边界判定写成字符串前缀比较，攻击者建一个
    `<项目名>-evil` 的同级目录就越界了。
    """
    proj = tmp_path / "proj"
    evil = tmp_path / "proj-evil"
    proj.mkdir()
    evil.mkdir()

    assert str(evil).startswith(str(proj))          # 朴素前缀比较会误判
    assert not path_in_working_path(str(evil / "x.py"), str(proj))


def test_additional_directories_extend_the_boundary(tmp_path):
    proj = tmp_path / "proj"
    extra = tmp_path / "shared"
    proj.mkdir()
    extra.mkdir()

    dirs = WorkingDirs(startup_cwd=str(proj), additional=(str(extra),))

    assert dirs.contains(str(proj / "a.py"))
    assert dirs.contains(str(extra / "b.py"))
    assert not dirs.contains(str(tmp_path / "c.py"))


def test_boundary_uses_startup_cwd_not_current_cwd(tmp_path, monkeypatch):
    """agent 中途 `cd` 出去，边界不跟着跑（照 CC 的 getOriginalCwd）。"""
    proj = tmp_path / "proj"
    elsewhere = tmp_path / "elsewhere"
    proj.mkdir()
    elsewhere.mkdir()

    monkeypatch.chdir(proj)
    dirs = WorkingDirs.from_startup()               # 在 proj 里建

    monkeypatch.chdir(elsewhere)                    # 跑到界外
    assert dirs.contains(str(proj / "a.py"))
    assert not dirs.contains(str(elsewhere / "b.py"))


def test_relative_paths_resolve_against_current_cwd_not_the_boundary(tmp_path, monkeypatch):
    """**与上一条配对，方向相反，两条都必须成立。**

    边界集合锚在启动 cwd，但**相对路径要按进程当前 cwd 解析**——因为工具真正
    打开的就是那个路径。若相对路径也按启动 cwd 解析，`cd /etc` 之后
    `read_file("passwd")` 会被算成 `<proj>/passwd`（界内、放行），
    而实际读到的是 `/etc/passwd`。那就成了一条 cd 逃逸。
    """
    proj = tmp_path / "proj"
    elsewhere = tmp_path / "elsewhere"
    proj.mkdir()
    elsewhere.mkdir()

    monkeypatch.chdir(proj)
    dirs = WorkingDirs.from_startup()

    monkeypatch.chdir(elsewhere)
    assert not dirs.contains("b.py")                # 解析成 <elsewhere>/b.py → 界外


def test_all_paths_must_be_inside(tmp_path):
    """`.every` 语义：任一条在界外就算越界（为 Task 4 的符号链接双路径铺路）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    dirs = WorkingDirs(startup_cwd=str(proj))

    assert paths_all_inside([str(proj / "a"), str(proj / "b")], dirs)
    assert not paths_all_inside([str(proj / "a"), "/etc/passwd"], dirs)
    assert not paths_all_inside([], dirs)           # 空 = 判不出来 = 不算界内


def test_empty_path_is_not_inside(tmp_path):
    """取不到路径时不能默认放行——`get_path` 拿到脏输入会返回空串。"""
    proj = tmp_path / "proj"
    proj.mkdir()

    assert not WorkingDirs(startup_cwd=str(proj)).contains("")


def test_dotdot_traversal_is_normalized(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)

    dirs = WorkingDirs(startup_cwd=str(proj))

    assert dirs.contains(str(proj / "src" / ".." / "a.py"))          # 归一化后仍在界内
    assert not dirs.contains(str(proj / ".." / "outside.txt"))       # 归一化后跑到界外


# ---- Task 4：符号链接双路径 ----
#
# CC 一次算出「原始路径 + realpath 解析后路径」两条，全链共用。
# 边界判定要求**两条都在界内**；deny/ask 规则是**任一脏就拦**（在 permissions 侧）。


def test_paths_for_permission_check_returns_both(tmp_path):
    from pai.core.boundary import get_paths_for_permission_check

    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    paths = get_paths_for_permission_check(str(link))

    assert str(link) in paths
    assert os.path.realpath(str(link)) in paths


def test_paths_for_permission_check_dedups_when_not_a_symlink(tmp_path):
    """不是软链时两条相同，去重成一条——省掉一半无谓的比较。"""
    from pai.core.boundary import get_paths_for_permission_check

    plain = tmp_path / "plain.txt"
    plain.write_text("x", encoding="utf-8")

    assert len(get_paths_for_permission_check(str(plain))) == 1


def test_symlink_out_of_boundary_is_outside(tmp_path):
    """界内的软链指向界外 → 越界。名字在界内不算数，真身也得在。"""
    proj = tmp_path / "proj"
    outside = tmp_path / "outside"
    proj.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    link = proj / "looks-local.txt"
    link.symlink_to(outside / "secret.txt")

    dirs = WorkingDirs(startup_cwd=str(proj))

    assert not dirs.contains(str(link))
    assert dirs.contains(str(proj / "genuine.txt"))


def test_working_dirs_are_resolved_the_same_way(tmp_path):
    """CC 注释标的坑：工作目录本身也要解析，否则**误拒**。

    工作目录给的是一条软链（`/tmp/link-proj` → `/tmp/real-proj`）时，
    待查路径 realpath 之后是 `/tmp/real-proj/...`，若拿它跟未解析的
    `/tmp/link-proj` 比就永远不匹配——把本该放行的全拒了。
    """
    real = tmp_path / "real-proj"
    real.mkdir()
    link = tmp_path / "link-proj"
    link.symlink_to(real)

    dirs = WorkingDirs.from_startup(cwd=str(link))

    assert dirs.contains(str(link / "a.py"))
    assert dirs.contains(str(real / "a.py"))        # 解析后的形式同样算界内


def test_broken_symlink_does_not_crash(tmp_path):
    """悬空软链不能把判定链炸掉——权限判定期拿到脏输入是常态。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    dangling = proj / "dangling.txt"
    dangling.symlink_to(proj / "不存在的目标.txt")

    dirs = WorkingDirs(startup_cwd=str(proj))

    assert dirs.contains(str(dangling))             # 目标不存在但仍在界内
