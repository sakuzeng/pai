"""路径作用域规则（feature 36）：`.pai/rules/*.md` 带 `paths:` 的只在模型碰到
匹配文件时才进上下文。

这一层的失效方式天然是沉默的——规则没进上下文，模型照样会给出一个看起来合理的
回答。所以每条「该注入」的测试旁边都配一条「不该注入」的反向守卫。
"""
import re
from pathlib import Path

from pai.core import rules as rules_mod
from pai.core.rules import Rule, RuleState, matches, scan_rules, select_and_render


def write_rule(directory: Path, name: str, *, paths=None, body="规则正文",
               block_form=False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    head = ""
    if paths is not None:
        if block_form:
            items = "\n".join(f"  - {p}" for p in paths)
            head = f"---\npaths:\n{items}\n---\n\n"
        else:
            head = f"---\npaths: {', '.join(paths)}\n---\n\n"
    path = directory / f"{name}.md"
    path.write_text(head + body, encoding="utf-8")
    return path


# ---- Task 1：发现与 paths 解析 ----


def test_scans_project_and_user_rules(tmp_path):
    write_rule(tmp_path / ".pai" / "rules", "项目规则", paths=["src/**"])
    write_rule(tmp_path / "home" / ".pai" / "rules", "用户规则", paths=["*.py"])

    found = scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=lambda _s: None)
    assert sorted(r.name for r in found) == ["用户规则", "项目规则"]


def test_scans_recursively(tmp_path):
    """官方是递归发现——规则多了必然要分目录放。"""
    write_rule(tmp_path / ".pai" / "rules" / "前端", "样式", paths=["web/**"])

    found = scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=lambda _s: None)
    assert [r.name for r in found] == ["样式"]


def test_both_paths_spellings_parse_the_same(tmp_path):
    """行内逗号是 pai 自家 frontmatter 子集的写法，YAML 列表块是官方文档里的写法。
    只认前者的话，从 CC 抄一份规则过来会**静默**变成「没有 paths」。"""
    a = write_rule(tmp_path / ".pai" / "rules", "甲", paths=["src/**/*.py", "tests/**"])
    b = write_rule(tmp_path / ".pai" / "rules", "乙", paths=["src/**/*.py", "tests/**"],
                   block_form=True)
    assert a.exists() and b.exists()

    found = {r.name: r.patterns for r in
             scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=lambda _s: None)}
    assert found["甲"] == ("src/**/*.py", "tests/**")
    assert found["乙"] == found["甲"]


def test_a_rule_without_paths_is_skipped_with_a_warning(tmp_path):
    """偏离官方（那边它们是常驻的）：本需求的收益命题就是降低常驻成本，
    在同一个功能里再开一条常驻通道与目标相反。warn 要给出路。"""
    write_rule(tmp_path / ".pai" / "rules", "没写paths", paths=None)

    said = []
    found = scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=said.append)
    assert found == []
    assert len(said) == 1 and "PAI.md" in said[0]


def test_broken_files_do_not_explode(tmp_path):
    directory = tmp_path / ".pai" / "rules"
    directory.mkdir(parents=True)
    (directory / "坏.md").write_text("---\npaths: [未闭合\n没有收尾围栏", encoding="utf-8")
    (directory / "空.md").write_text("", encoding="utf-8")

    said = []
    assert scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=said.append) == []
    assert len(said) == 2                      # 两个都要说，不许沉默跳过


def test_no_rules_directory_is_not_an_error(tmp_path):
    assert scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=lambda _s: None) == []


# ---- Task 2：glob 匹配 ----


def test_double_star_crosses_directories():
    assert matches("src/a/b/c.py", ("src/**/*.py",))
    assert matches("src/a.py", ("src/**/*.py",))
    assert not matches("src/a/b.txt", ("src/**/*.py",))


def test_single_star_does_not_cross_a_slash():
    assert matches("readme.md", ("*.md",))
    assert not matches("docs/readme.md", ("*.md",))
    assert matches("docs/readme.md", ("docs/*.md",))


def test_a_directory_pattern_matches_everything_under_it():
    assert matches("docs/dev/TODO.md", ("docs/",))
    assert matches("docs/dev/TODO.md", ("docs",))
    assert not matches("documents/x.md", ("docs",))     # 到分隔符边界为止


def test_question_mark_matches_one_char_not_a_slash():
    assert matches("a1.py", ("a?.py",))
    assert not matches("a/1.py", ("a?1.py",))


def test_special_regex_chars_are_literal():
    assert matches("a+b.py", ("a+b.py",))
    assert not matches("aab.py", ("a+b.py",))


def test_double_star_translation_is_load_bearing():
    """注入反证：`**` 若被翻成 `[^/]*`（不跨目录），下面这条就会变成不匹配。
    这条测试是为了证明上面那批不是走过场——翻译表改坏了它必红。"""
    assert matches("src/a/b/c.py", ("src/**/*.py",))
    assert re.match(rules_mod._translate("src/**/*.py"), "src/a/b/c.py")
    assert not re.match(rules_mod._translate("src/*/*.py"), "src/a/b/c.py")


# ---- Task 3：选择与渲染 ----


def _rules(tmp_path, **specs):
    directory = tmp_path / ".pai" / "rules"
    for name, (paths, body) in specs.items():
        write_rule(directory, name, paths=paths, body=body)
    return scan_rules(cwd=tmp_path, home=tmp_path / "home", warn=lambda _s: None)


def test_a_touched_path_pulls_in_its_rule(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    found = _rules(tmp_path, 前端=(["web/**"], "样式一律用 rem"))
    block = select_and_render(["web/a/style.css"], found, RuleState(), root=tmp_path)
    assert "样式一律用 rem" in block
    assert block.startswith("<system-reminder>")
    assert "不是用户指令" in block


def test_an_untouched_rule_never_shows_up(tmp_path, monkeypatch):
    """反向守卫，也是这层机制存在的全部理由：不相关就不该占上下文。"""
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    found = _rules(tmp_path, 前端=(["web/**"], "样式一律用 rem"))
    assert select_and_render(["src/loop.py"], found, RuleState(), root=tmp_path) == ""
    assert select_and_render([], found, RuleState(), root=tmp_path) == ""


def test_a_rule_is_not_injected_twice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    found = _rules(tmp_path, 前端=(["web/**"], "样式一律用 rem"))
    state = RuleState()
    assert select_and_render(["web/a.css"], found, state, root=tmp_path)
    assert select_and_render(["web/b.css"], found, state, root=tmp_path) == ""


def test_clearing_the_state_lets_it_come_back(tmp_path, monkeypatch):
    """压缩把它切走之后，「已经在上下文里」就是假的（同 RecallState.surfaced）。"""
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    found = _rules(tmp_path, 前端=(["web/**"], "样式一律用 rem"))
    state = RuleState()
    select_and_render(["web/a.css"], found, state, root=tmp_path)
    state.injected.clear()
    assert "样式一律用 rem" in select_and_render(["web/b.css"], found, state, root=tmp_path)


def test_paths_outside_the_project_never_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    found = _rules(tmp_path, 任何=(["**"], "正文"))
    assert select_and_render(["/etc/passwd"], found, RuleState(), root=tmp_path) == ""


def test_a_huge_rule_is_truncated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    from pai.core.rules import MAX_RULE_CHARS

    found = _rules(tmp_path, 长=(["**"], "正" * (MAX_RULE_CHARS * 2)))
    block = select_and_render(["a.py"], found, RuleState(), root=tmp_path)
    assert "截断" in block and str(MAX_RULE_CHARS) in block
    assert len(block) < MAX_RULE_CHARS * 2


def test_too_many_rules_in_one_step_says_so(tmp_path, monkeypatch):
    """一次工具批碰五六个文件是常态。截了要说——静默丢弃会让人以为规则不生效。"""
    monkeypatch.chdir(tmp_path)      # 相对路径按 cwd 解析（同真实使用）
    from pai.core.rules import MAX_RULES_PER_STEP

    specs = {f"规则{i}": (["**"], f"正文{i}") for i in range(MAX_RULES_PER_STEP + 2)}
    found = _rules(tmp_path, **specs)
    block = select_and_render(["a.py"], found, RuleState(), root=tmp_path)
    assert block.count("## 规则") == MAX_RULES_PER_STEP
    assert "另有 2 条" in block


def test_relative_paths_resolve_against_cwd_not_the_project_root(tmp_path, monkeypatch):
    """模型给的相对路径是相对 cwd 的（工具就是这么打开文件的），而 glob 是相对
    项目根的。在子目录里启动 pai 时这两个基准不是同一个——拿项目根去拼相对路径，
    `web/a.css` 会被算成 `<根>/web/a.css`，而模型指的是 `<根>/子目录/web/a.css`。

    子目录启动是 pai 撞过的场景（feature 27 就是它）。"""
    (tmp_path / "子目录" / "web").mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "子目录")
    found = _rules(tmp_path, 前端=(["子目录/web/**"], "样式一律用 rem"))

    block = select_and_render(["web/a.css"], found, RuleState(), root=tmp_path)
    assert "样式一律用 rem" in block, "相对路径要按 cwd 解析再折回项目根"
