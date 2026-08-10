"""分层指令与自动记忆（feature 06）。

发现顺序是本模块唯一容易错又必须对的地方：官方语义是「向上遍历收集、拼接不覆盖、
越靠近 cwd 越晚被读到」，同目录内 local 排在后面。顺序错了不会报错，
只会让优先级悄悄反过来——所以逐条钉死。
"""
from pai.core import memory


def _write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_discovers_up_the_tree_root_first(tmp_path):
    _write(tmp_path / "PAI.md", "根")
    _write(tmp_path / "a" / "PAI.md", "中")
    _write(tmp_path / "a" / "b" / "PAI.md", "近")

    found = memory.discover(cwd=tmp_path / "a" / "b", home=tmp_path / "home")
    assert [p.read_text(encoding="utf-8") for p in found] == ["根", "中", "近"]


def test_local_comes_after_plain_in_same_dir(tmp_path):
    _write(tmp_path / "PAI.md", "共享")
    _write(tmp_path / "PAI.local.md", "私人")

    found = memory.discover(cwd=tmp_path, home=tmp_path / "home")
    assert [p.name for p in found] == ["PAI.md", "PAI.local.md"]


def test_user_level_comes_first(tmp_path):
    home = tmp_path / "home"
    _write(home / ".pai" / "PAI.md", "用户级")
    _write(tmp_path / "proj" / "PAI.md", "项目级")

    found = memory.discover(cwd=tmp_path / "proj", home=home)
    assert [p.read_text(encoding="utf-8") for p in found][:2] == ["用户级", "项目级"]


def test_subdirectory_files_are_not_loaded(tmp_path):
    """cwd 之下的文件不进启动上下文——模型要用时自己 read_file（官方同款语义）。"""
    _write(tmp_path / "PAI.md", "根")
    _write(tmp_path / "sub" / "PAI.md", "子目录")

    found = memory.discover(cwd=tmp_path, home=tmp_path / "home")
    assert [p.read_text(encoding="utf-8") for p in found] == ["根"]


def test_missing_files_are_skipped_silently(tmp_path):
    assert memory.discover(cwd=tmp_path, home=tmp_path / "home") == []


def test_agents_md_is_not_read(tmp_path):
    """问 2 的裁决要被钉死：AGENTS.md 写的是「给写 pai 的 AI 的规矩」，
    pai 自己当 agent 跑时读到会把开发规约当成任务指令。要用它请显式 @AGENTS.md 导入。
    """
    _write(tmp_path / "AGENTS.md", "先写测试跑红再写实现")
    _write(tmp_path / "CLAUDE.md", "别的 agent 的入口")

    assert memory.discover(cwd=tmp_path, home=tmp_path / "home") == []


# ---- task 2：@path 导入展开 ----


def test_import_is_relative_to_the_importing_file(tmp_path):
    """相对路径相对**含导入的那个文件**解析，不是 cwd——这条错了会在嵌套目录里全面失灵。"""
    _write(tmp_path / "a" / "PAI.md", "开头 @sub/x.md 结尾")
    _write(tmp_path / "a" / "sub" / "x.md", "被导入的内容")
    _write(tmp_path / "sub" / "x.md", "不该拿到这个")

    text = memory.expand_imports("开头 @sub/x.md 结尾", base=tmp_path / "a")
    assert "被导入的内容" in text
    assert "不该拿到这个" not in text


def test_import_recurses_up_to_four_hops(tmp_path):
    """「4 跳」从根文档起算：根里的 `@1.md` 就是第 1 跳，所以 4.md 是最后一层。

    （本条测试初版把上限写成 5 层，红出来的是测试自己的 off-by-one——记在 devlog。）
    """
    for i in range(1, 7):
        _write(tmp_path / f"{i}.md", f"第{i}层 @{i + 1}.md")

    text = memory.expand_imports("@1.md", base=tmp_path)
    for i in range(1, 5):
        assert f"第{i}层" in text, f"第 {i} 层应在深度上限内"
    assert "第5层" not in text, "超过 4 跳不再展开"
    assert "深度上限" in text, "停在上限要留一行提示，不能悄悄断掉"


def test_import_cycle_terminates(tmp_path):
    _write(tmp_path / "a.md", "A @b.md")
    _write(tmp_path / "b.md", "B @a.md")

    text = memory.expand_imports("@a.md", base=tmp_path)     # 不死循环、不爆栈
    assert "A" in text and "B" in text


def test_inline_code_and_fenced_blocks_are_not_imports(tmp_path):
    _write(tmp_path / "README.md", "不该被导入")
    source = "行内 `@README.md` 保持字面\n\n```\n@README.md\n```\n"

    text = memory.expand_imports(source, base=tmp_path)
    assert "不该被导入" not in text
    assert "`@README.md`" in text


def test_missing_import_leaves_a_note_not_an_exception(tmp_path):
    text = memory.expand_imports("@没有这个文件.md", base=tmp_path)
    assert "未找到" in text


def test_home_and_absolute_import_paths_work(tmp_path):
    home = tmp_path / "home"
    _write(home / ".pai" / "shared.md", "跨 worktree 共享的个人指令")
    target = _write(tmp_path / "abs.md", "绝对路径内容")

    text = memory.expand_imports("@~/.pai/shared.md", base=tmp_path, home=home)
    assert "跨 worktree 共享的个人指令" in text
    assert "绝对路径内容" in memory.expand_imports(f"@{target}", base=tmp_path)


def test_load_joins_files_in_discovery_order(tmp_path):
    _write(tmp_path / "PAI.md", "根规矩 @detail.md")
    _write(tmp_path / "detail.md", "细节")
    _write(tmp_path / "PAI.local.md", "私人偏好")

    text = memory.load_instructions(cwd=tmp_path, home=tmp_path / "home")
    assert text.index("根规矩") < text.index("私人偏好")
    assert "细节" in text                                     # 导入在拼接时就展开了


# ---- task 3：自动记忆的读取（项目 key + 两条上限） ----


def test_project_key_comes_from_git_root(tmp_path):
    """同一个仓库的所有子目录（含 worktree）共享一份记忆——官方语义。"""
    import subprocess

    repo = tmp_path / "repo"
    (repo / "src" / "deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    home = tmp_path / "home"
    top = memory.memory_dir(cwd=repo, home=home)
    deep = memory.memory_dir(cwd=repo / "src" / "deep", home=home)
    assert top == deep


def test_project_key_falls_back_to_project_root_outside_git(tmp_path):
    home = tmp_path / "home"
    a = memory.memory_dir(cwd=tmp_path / "a", home=home)
    b = memory.memory_dir(cwd=tmp_path / "b", home=home)
    assert a != b                                   # 非 git 目录各算各的
    assert home in a.parents


def test_memory_index_is_truncated_at_200_lines(tmp_path):
    index = tmp_path / "MEMORY.md"
    index.write_text("\n".join(f"第 {i} 行" for i in range(1, 401)), encoding="utf-8")

    text = memory.load_memory_index(tmp_path)
    assert "第 200 行" in text
    assert "第 201 行" not in text
    assert "截断" in text                            # 官方静默截断，pai 必须留提示


def test_memory_index_is_truncated_at_25kb(tmp_path):
    index = tmp_path / "MEMORY.md"
    # 10 行 × 每行 4KB：远不到 200 行就先撞 25KB 上限（「先到者为准」）
    index.write_text("\n".join("x" * 4000 for _ in range(10)), encoding="utf-8")

    text = memory.load_memory_index(tmp_path)
    assert len(text.encode("utf-8")) < 26 * 1024
    assert "截断" in text


def test_short_index_is_returned_whole_without_note(tmp_path):
    (tmp_path / "MEMORY.md").write_text("就一行", encoding="utf-8")
    text = memory.load_memory_index(tmp_path)
    assert text.strip() == "就一行"
    assert "截断" not in text


def test_topic_files_are_not_loaded_at_startup(tmp_path):
    (tmp_path / "MEMORY.md").write_text("索引：见 debugging.md", encoding="utf-8")
    (tmp_path / "debugging.md").write_text("很长的调试笔记", encoding="utf-8")

    text = memory.load_memory_index(tmp_path)
    assert "很长的调试笔记" not in text              # 模型要用时自己 read_file


def test_missing_memory_index_returns_empty(tmp_path):
    assert memory.load_memory_index(tmp_path / "不存在") == ""
