"""分层指令与自动记忆（feature 06）。

发现顺序是本模块唯一容易错又必须对的地方：官方语义是「向上遍历收集、拼接不覆盖、
越靠近 cwd 越晚被读到」，同目录内 local 排在后面。顺序错了不会报错，
只会让优先级悄悄反过来——所以逐条钉死。
"""
from pai.core import memory

from helpers import write_memory


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
    """cwd 之下的文件不进启动上下文。注意这不是官方同款语义：官方是框架懒加载
    （读到那个目录里的文件时才注入），pai 是彻底不收集——刻意的能力差，
    理由见 `discover` 的 docstring。"""
    _write(tmp_path / "PAI.md", "根")
    _write(tmp_path / "sub" / "PAI.md", "子目录")

    found = memory.discover(cwd=tmp_path, home=tmp_path / "home")
    assert [p.read_text(encoding="utf-8") for p in found] == ["根"]


def test_missing_files_are_skipped_silently(tmp_path):
    assert memory.discover(cwd=tmp_path, home=tmp_path / "home") == []


def test_agents_md_is_read(tmp_path):
    """D#43 复议（06 复盘质疑三，用户 2026-08-26 拍板）：原裁决「不读 AGENTS.md」
    的理由是「那是给写 pai 的 AI 的规矩」——那条理由只在**本仓库**成立。
    pai 的立意是在别人的项目里跑，那里的 AGENTS.md 恰恰是该项目写给 agent 的规矩。
    """
    _write(tmp_path / "AGENTS.md", "别人项目写给 agent 的规矩")

    found = memory.discover(cwd=tmp_path, home=tmp_path / "home")
    assert [p.name for p in found] == ["AGENTS.md"]


def test_pai_md_comes_after_agents_md_in_the_same_dir(tmp_path):
    """同目录内的顺序 = 优先级：后读到的更靠近对话。PAI.md 是 pai 自己的入口，
    它该压得住通用的 AGENTS.md（与 local 排在 plain 之后同一条规矩）。"""
    _write(tmp_path / "AGENTS.md", "通用")
    _write(tmp_path / "PAI.md", "pai 专用")
    _write(tmp_path / "PAI.local.md", "私人")

    found = memory.discover(cwd=tmp_path, home=tmp_path / "home")
    assert [p.name for p in found] == ["AGENTS.md", "PAI.md", "PAI.local.md"]


def test_other_agents_entry_files_are_still_not_read(tmp_path):
    """复议只翻了 AGENTS.md 这一条：CLAUDE.md 是另一家的入口文件，照旧不读
    （要用它就显式 @CLAUDE.md 导入）。"""
    _write(tmp_path / "CLAUDE.md", "别的 agent 的入口")

    assert memory.discover(cwd=tmp_path, home=tmp_path / "home") == []


def test_user_level_agents_md_is_read_too(tmp_path):
    """用户级目录同款：~/.pai/AGENTS.md 也算数，排在 ~/.pai/PAI.md 之前。"""
    home = tmp_path / "home"
    _write(home / ".pai" / "AGENTS.md", "用户级通用")
    _write(home / ".pai" / "PAI.md", "用户级 pai")

    found = memory.discover(cwd=tmp_path, home=home)
    assert [p.name for p in found] == ["AGENTS.md", "PAI.md"]


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


# 下面四条自 feature 10 起改写：索引不再是「原样读 MEMORY.md」，而是从各记忆文件的
# frontmatter 现渲染的**投影**。两条上限与「不静默丢内容」的规矩原样保留。

def test_memory_index_is_truncated_at_200_lines(tmp_path):
    for i in range(250):
        write_memory(tmp_path, f"m{i:03d}", mtime=1_700_000_000 + i)

    text = memory.load_memory_index(tmp_path)
    entries = [line for line in text.splitlines() if line.startswith("- [")]
    assert len(entries) <= memory.MAX_INDEX_LINES
    assert "m249" in text                            # 最新的留在常驻区
    assert "m000" not in text                        # 最老的被挤出去
    assert "截断" in text                            # 官方静默截断，pai 必须留提示


def test_memory_index_is_truncated_at_25kb(tmp_path):
    # 10 篇 × 每篇 4KB 描述：远不到 200 行就先撞 25KB 上限（「先到者为准」）
    for i in range(10):
        write_memory(tmp_path, f"m{i}", description="x" * 4000)

    text = memory.load_memory_index(tmp_path)
    assert len(text.encode("utf-8")) < 26 * 1024
    assert "截断" in text


def test_short_index_is_returned_whole_without_note(tmp_path):
    write_memory(tmp_path, "就一条", description="短索引应原样返回")
    text = memory.load_memory_index(tmp_path)
    assert "短索引应原样返回" in text
    assert "截断" not in text


def test_memory_bodies_are_not_loaded_at_startup(tmp_path):
    write_memory(tmp_path, "debugging", description="调试要点一句话", body="很长的调试笔记正文")

    text = memory.load_memory_index(tmp_path)
    assert "调试要点一句话" in text                   # 描述进常驻区
    assert "很长的调试笔记正文" not in text           # 正文不进——它由召回按需注入


def test_missing_memory_index_returns_empty(tmp_path):
    assert memory.load_memory_index(tmp_path / "不存在") == ""


# ---- R4#7：@ 只在「像导入」的位置才算导入（2026-08-19 评审）----


def test_an_email_address_is_not_an_import(tmp_path):
    """`@` 前面贴着字母就不是导入语法。

    此前 `someone@example.com` 被改写成 `someone(@example.com 未找到)`——
    而这段文本每轮都会作为指令消息注入，模型读到的是被悄悄改过的规约，
    且没有任何告警。
    """
    text = "联系 someone@example.com 获取权限。"

    assert memory.expand_imports(text, base=tmp_path, home=tmp_path) == text


def test_a_decorator_is_not_an_import(tmp_path):
    """`@tool` 这类装饰器名不含路径分隔符，不该被当成文件。

    本仓库自己的规约里就写着「工具 schema 一律由 @tool 装饰器生成」——
    用户照着写一份 PAI.md，这句话就会被改写掉。
    `@dataclass(frozen=True)` 更糟：连括号一起被吃进「未找到」里。
    """
    for text in ["工具用 @tool 装饰器注册。",
                 "用 @dataclass(frozen=True) 定义事件。",
                 "只读属性用 @property。"]:
        assert memory.expand_imports(text, base=tmp_path, home=tmp_path) == text


def test_a_path_shaped_target_is_still_an_import(tmp_path):
    """治过头就成了另一个 bug：真导入必须照常工作。"""
    (tmp_path / "child.md").write_text("子文件内容", encoding="utf-8")

    assert "子文件内容" in memory.expand_imports(
        "见 @child.md 的说明。", base=tmp_path, home=tmp_path)
    assert "子文件内容" in memory.expand_imports(
        "@child.md", base=tmp_path, home=tmp_path)          # 行首


def test_a_path_shaped_but_missing_target_still_reports(tmp_path):
    """诊断不能丢：写错路径的人需要知道自己写错了。"""
    out = memory.expand_imports("见 @docs/nope.md 的说明。", base=tmp_path, home=tmp_path)

    assert "未找到" in out
