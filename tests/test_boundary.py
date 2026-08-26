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


# ---- Task 5：危险路径清单（bypass 免疫）----
#
# 照 CC 的 DANGEROUS_FILES / DANGEROUS_DIRECTORIES：**持久化位点**写不进去。
# 「bypass 免疫」= 即使 default_decision=allow、即使有 allow 规则命中，写这些仍要拦。
# 只挡写不挡读——挡读会让 agent 连自己的配置都看不了。


def _dangerous(path, home=None):
    from pai.core.boundary import is_dangerous_write

    return is_dangerous_write(str(path), home=str(home) if home else None)


def test_shell_configs_are_dangerous(tmp_path):
    home = tmp_path / "home"
    for name in (".bashrc", ".zshrc", ".profile"):
        assert _dangerous(home / name, home), name


def test_git_hooks_are_protected(tmp_path):
    """`.git/hooks/**` 是持久化位点：写进去就是下次 git 操作时任意代码执行。"""
    proj = tmp_path / "proj"

    assert _dangerous(proj / ".git" / "hooks" / "pre-commit")
    assert _dangerous(proj / "nested" / ".git" / "hooks" / "post-merge")
    assert not _dangerous(proj / ".git" / "config")      # 只挡 hooks，不是整个 .git


def test_ssh_dir_is_protected(tmp_path):
    home = tmp_path / "home"

    assert _dangerous(home / ".ssh" / "authorized_keys", home)
    assert _dangerous(home / ".ssh" / "id_rsa", home)


def test_pai_settings_is_protected(tmp_path):
    """防 agent 改自己的权限规则（CC 的 isClaudeSettingsPath 同款）。

    不挡这个的话，「让 agent 帮我把这条规则加进 settings.json」就成了
    一条合法的提权路径。
    """
    home = tmp_path / "home"

    assert _dangerous(home / ".pai" / "settings.json", home)
    assert _dangerous(tmp_path / "proj" / ".pai" / "settings.json", home)


def test_ordinary_paths_are_not_dangerous(tmp_path):
    proj = tmp_path / "proj"

    assert not _dangerous(proj / "src" / "main.py")
    assert not _dangerous(proj / "README.md")


# ---- EXEC：执行类工具的第三档（feature 42 拍板问 3·A）----
#
# 起因：`access` 只有 READ / WRITE 两档，而「跑测试」既不是读也不是写。
# 写成 READ 行为对、语义错（下一个人会以为它只读，而它跑任意项目代码）；
# 不声明则落进兜底 ask，每次跑测试都弹窗。新开一档是为了让这个字段不说谎。
# EXEC 的语义定成「起一个进程」，不是「碰一个文件」——这条分界线在下一个
# 执行类工具到来时是可判的。


def _exec_tool(name="_exec_probe", path_getter=None):
    """造一个声明了 EXEC 的工具，不进全局 REGISTRY（抄 test_permissions 的做法）。"""
    from pai.core.tools import EXEC, Tool

    return Tool(
        name=name,
        description="假的执行类工具",
        parameters={"type": "object", "properties": {}, "required": []},
        func=lambda **kw: "",
        get_path=path_getter or (lambda args: str(args.get("path") or "")),
        access=EXEC,
    )


def test_exec_participates_in_the_boundary():
    """漏了这条，EXEC 工具会落进「未声明路径语义 → ask」，与不声明毫无区别。"""
    assert _exec_tool().participates_in_boundary()


def test_exec_inside_the_working_dir_is_allowed(tmp_path):
    from pai.core import permissions
    from pai.core.permissions import RuleSet

    tools = {"_exec_probe": _exec_tool()}
    d = permissions.decide("_exec_probe", {"path": str(tmp_path)},
                           RuleSet.from_lists(), tools=tools, cwd=str(tmp_path))
    assert d.kind == "allow", d.reason


def test_exec_outside_the_working_dir_still_asks(tmp_path):
    """另一半。只做前一半的话 EXEC 就成了「在任意目录起进程」的通道。"""
    from pai.core import permissions
    from pai.core.permissions import RuleSet

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    tools = {"_exec_probe": _exec_tool()}
    d = permissions.decide("_exec_probe", {"path": str(outside)},
                           RuleSet.from_lists(), tools=tools, cwd=str(tmp_path))
    assert d.kind == "ask", d.reason


def test_accept_edits_does_not_let_exec_sneak_in(tmp_path):
    """连带复核一：`acceptEdits` 免的是「写一律 ask」那一档，不是「执行」。

    第 5 步查的是 `access == WRITE`。若哪天有人把它放宽成「不是 READ 就算」，
    `acceptEdits` 会顺手把执行也免掉——而用户按下那个模式时想的是「别再问我
    改文件的事」，不是「随便跑东西」。

    要让这条**可观察**得挑对场景（第一版挑错了，注入反证没红才发现）：
    界外的话第 5 步自带的 `dirs.contains` 已经挡住，放宽与否都进不去；
    界内的话兜底本来就 allow，两条路殊途同归。唯一能把两者分开的是
    **兜底不是 `workingdir` 的时候**——`default_decision="deny"` 下，
    第 5 步是 allow、第 7 步是 deny，放宽就会把 deny 变成 allow。
    """
    from pai.core import permissions
    from pai.core.permissions import ACCEPT_EDITS, RuleSet
    from pai.core.tools import WRITE, Tool

    strict = RuleSet.from_lists(default_decision="deny")
    tools = {"_exec_probe": _exec_tool()}
    d = permissions.decide("_exec_probe", {"path": str(tmp_path)},
                           strict, tools=tools, cwd=str(tmp_path), mode=ACCEPT_EDITS)
    assert d.kind == "deny", f"acceptEdits 把执行也免掉了：{d.reason}"

    # 反向守卫：同样场景下**写**必须照旧被 acceptEdits 放行，否则这条测试
    # 就不是在钉「EXEC 不蹭」，而是在钉「第 5 步坏了」。
    writer = Tool(name="_w2", description="假写工具",
                  parameters={"type": "object", "properties": {}, "required": []},
                  func=lambda **kw: "", get_path=lambda a: str(a.get("path") or ""),
                  access=WRITE)
    d_w = permissions.decide("_w2", {"path": str(tmp_path)}, strict,
                             tools={"_w2": writer}, cwd=str(tmp_path), mode=ACCEPT_EDITS)
    assert d_w.kind == "allow", d_w.reason


def test_dangerous_write_check_still_only_looks_at_writes(tmp_path, monkeypatch):
    """连带复核二：危险写检查只管 WRITE，新档位不该让它多管或少管。

    拿一个真的持久化位点当路径：EXEC 工具在那里起进程不是「写进去」，
    不该被这条拦（它拦的是内容落盘）；而它对 WRITE 的判断必须一个字不变。
    """
    from pai.core import permissions
    from pai.core.permissions import RuleSet
    from pai.core.tools import WRITE, Tool

    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    target = str(home / ".ssh" / "config")

    writer = Tool(name="_write_probe", description="假写工具",
                  parameters={"type": "object", "properties": {}, "required": []},
                  func=lambda **kw: "", get_path=lambda a: str(a.get("path") or ""),
                  access=WRITE)
    d_write = permissions.decide("_write_probe", {"path": target},
                                 RuleSet.from_lists(), tools={"_write_probe": writer},
                                 cwd=str(tmp_path), home=str(home))
    assert d_write.kind == "ask" and "持久化位点" in d_write.reason

    tools = {"_exec_probe": _exec_tool()}
    d_exec = permissions.decide("_exec_probe", {"path": target},
                                RuleSet.from_lists(), tools=tools,
                                cwd=str(tmp_path), home=str(home))
    # 界外，所以仍是 ask——但理由必须是边界，不是「持久化位点」
    assert "持久化位点" not in d_exec.reason, d_exec.reason


def test_path_access_for_accepts_exec_and_still_rejects_garbage():
    """连带复核三：声明入口要认得新档位，也要继续挡住拼错的档位名。"""
    import pytest as _pytest

    from pai.core.tools import EXEC, REGISTRY, path_access_for, tool

    @tool
    def _exec_decl_probe(a: str) -> str:
        """探针。"""
        return a

    path_access_for(_exec_decl_probe, EXEC)(lambda args: str(args.get("a") or ""))
    assert REGISTRY["_exec_decl_probe"].access == EXEC

    with _pytest.raises(ValueError):
        path_access_for(_exec_decl_probe, "execute")(lambda args: "")
    REGISTRY.pop("_exec_decl_probe", None)
