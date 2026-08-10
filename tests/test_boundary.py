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
