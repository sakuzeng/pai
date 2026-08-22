"""pai 用户级路径的唯一事实源（feature 08 task 1）。

对齐 CC 的布局：`~/.pai/projects/<可读 slug>/{memory,sessions}/`。
slug 用**全路径连字符**而不是哈希——用户翻 `~/.pai` 时要一眼看出是哪个项目
（起因就是他问「`2b0a92ef14633a56` 又是什么鬼」）。
"""
import subprocess

from pai.core import paths


def test_slug_is_the_dashed_absolute_path(tmp_path):
    assert paths.project_slug(cwd=tmp_path / "Users" / "x" / "proj").endswith("-Users-x-proj")


def test_slug_uses_the_git_root(tmp_path):
    """同一仓库的子目录与 worktree 共享一份数据（官方语义）。"""
    repo = tmp_path / "repo"
    (repo / "src" / "deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    assert paths.project_slug(cwd=repo) == paths.project_slug(cwd=repo / "src" / "deep")


def test_slug_falls_back_to_cwd_outside_git(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert paths.project_slug(cwd=a) != paths.project_slug(cwd=b)


def test_slug_keeps_chinese_path_as_is(tmp_path):
    d = tmp_path / "我的项目"
    d.mkdir()
    assert "我的项目" in paths.project_slug(cwd=d)


def test_known_slug_collision_is_documented(tmp_path):
    """**把已知缺陷钉成测试**：`/a-b/c` 与 `/a/b-c` 撞成同一个 slug。

    这不是在测正确性，是给未来想「顺手修好」的人留话——CC 就是这么拼的，
    一旦加转义，目录名就不再和 CC 长得一样，而「可读、与 CC 一致」正是本需求的诉求。
    真实碰撞概率极低，已登记 TODO。改这条之前先读 features/08 的 spec。
    """
    one = (tmp_path / "a-b" / "c")
    two = (tmp_path / "a" / "b-c")
    one.mkdir(parents=True); two.mkdir(parents=True)
    assert paths.project_slug(cwd=one) == paths.project_slug(cwd=two)


def test_project_dir_layout(tmp_path):
    home = tmp_path / "home"
    d = paths.project_dir(cwd=tmp_path / "proj", home=home)
    assert d.parent == home / ".pai" / "projects"
    assert paths.memory_dir(cwd=tmp_path / "proj", home=home) == d / "memory"
    assert paths.sessions_dir(cwd=tmp_path / "proj", home=home) == d / "sessions"


# ---- task 2/3：memory 与 session 都改用 paths ----


def test_memory_dir_now_lives_under_the_readable_slug(tmp_path):
    """从 16 位哈希换成可读 slug——用户翻 ~/.pai 时要认得出是哪个项目。"""
    from pai.core import memory

    home = tmp_path / "home"
    d = memory.memory_dir(cwd=tmp_path / "proj", home=home)
    assert "-" in d.parent.name and len(d.parent.name) > 16
    assert d == paths.memory_dir(cwd=tmp_path / "proj", home=home)


def test_session_defaults_to_the_project_sessions_dir(tmp_path, monkeypatch):
    """整个需求的初衷：**跑 pai 不该往当前目录拉一坨 sessions/**。"""
    from pai.core.session import SessionLog

    workdir = tmp_path / "别人的项目"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    log = SessionLog()
    log.append({"role": "user", "content": "x"})

    assert not (workdir / "sessions").exists(), "当前工作目录里不该出现 sessions/"
    assert log.path.parent == paths.sessions_dir()


def test_session_directory_param_still_works(tmp_path):
    from pai.core.session import SessionLog

    log = SessionLog(tmp_path / "custom")
    assert log.path.parent == tmp_path / "custom"


def test_the_header_carries_session_id_and_cwd(tmp_path, monkeypatch):
    """08 把会话集中存放之后，不记 cwd 就是净信息丢失——
    同一仓库的不同子目录会写进同一个目录，再也分不出这次是在哪跑的。
    v1（feature 24）后身份归 header 一次说清，不再每条记录重复。"""
    import json

    from pai.core.session import SessionLog

    monkeypatch.chdir(tmp_path)
    log = SessionLog(tmp_path / "s")
    log.append({"role": "user", "content": "x"})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    header, entry = json.loads(lines[0]), json.loads(lines[1])

    assert header["cwd"] == str(tmp_path.absolute())
    assert header["id"] == log.session_id
    assert entry["ts"]
    assert "cwd" not in entry and "sessionId" not in entry, \
        "身份信息不再每条重复——header 一次说清（v1）"


def test_same_second_sessions_do_not_collide(tmp_path):
    """R#15 旧账：文件名精确到秒，同秒建两个 SessionLog 会写同一个文件。"""
    from pai.core.session import SessionLog

    a, b = SessionLog(tmp_path / "s"), SessionLog(tmp_path / "s")
    assert a.path != b.path
    assert a.session_id != b.session_id


def test_filename_keeps_the_timestamp_prefix(tmp_path):
    """与 CC 不同的取舍：CC 用纯 `<sessionId>.jsonl`，pai 保留时间戳前缀，
    于是集中存放后 `ls` 仍按时间排序——一个目录里几十个会话，按时间排比认 uuid 容易。"""
    import re

    from pai.core.session import SessionLog

    name = SessionLog(tmp_path / "s").path.name
    assert re.match(r"^\d{8}-\d{6}-[0-9a-f]+\.jsonl$", name), name
