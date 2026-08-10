"""权限层（feature 07）Task 1：规则解析与三态求值。

本文件钉死的核心不变量是**求值顺序 deny → ask → allow，第一个匹配决定**。
这是最容易被「优化成按特异性排序」的地方——改了不会有任何报错，
只会静默放开一个洞（更特异的 allow 把宽泛的 deny 翻掉）。
"""
import pytest

from pai.core import permissions
from pai.core.permissions import Rule, RuleSet
from pai.core.tools import Tool


def _fake_tool(name: str, matcher=None) -> Tool:
    """直接造 Tool 不过 @tool 注册表——避免测试互相污染全局 REGISTRY（抄 test_loop 的做法）。"""
    return Tool(
        name=name,
        description="假工具",
        parameters={"type": "object", "properties": {}, "required": []},
        func=lambda **kw: "",
        matcher=matcher,
    )


def test_parses_bare_tool_and_specifier():
    bare = permissions.parse_rule("Bash")
    assert (bare.tool, bare.specifier) == ("bash", None)

    scoped = permissions.parse_rule("Bash(git push *)")
    assert (scoped.tool, scoped.specifier) == ("bash", "git push *")

    # 大小写与空格容错：写规则的是人，不该因为多打一个空格就静默失效
    loose = permissions.parse_rule("  READ_FILE( ./x.txt )  ")
    assert (loose.tool, loose.specifier) == ("read_file", "./x.txt")


def test_deny_beats_more_specific_allow():
    """本 task 的核心：deny 宽泛、allow 特异，仍然 deny。"""
    rules = RuleSet.from_lists(deny=["Bash(aws *)"], allow=["Bash(aws s3 ls)"])

    assert permissions.decide("bash", {"command": "aws s3 ls"}, rules).kind == "deny"


def test_ask_beats_allow():
    rules = RuleSet.from_lists(
        ask=["Bash(git push *)"], allow=["Bash(git push origin main)"]
    )

    assert permissions.decide("bash", {"command": "git push origin main"}, rules).kind == "ask"


def test_first_match_in_order_wins_not_most_specific():
    """同一桶内按书写顺序取第一个命中，不按特异性重排。"""
    rules = RuleSet.from_lists(allow=["Bash(git *)", "Bash(git push origin main)"])

    decision = permissions.decide("bash", {"command": "git push origin main"}, rules)

    assert decision.kind == "allow"
    assert decision.rule.specifier == "git *"


def test_no_match_falls_back_to_default_decision():
    rules = RuleSet.from_lists(allow=["Bash(ls *)"])
    fallback = permissions.decide("bash", {"command": "cat x"}, rules)
    assert fallback.kind == "allow"
    assert fallback.rule is None          # 没有规则背这个锅

    for wanted in ("ask", "deny"):
        strict = RuleSet.from_lists(allow=["Bash(ls *)"], default_decision=wanted)
        assert permissions.decide("bash", {"command": "cat x"}, strict).kind == wanted


def test_tool_name_glob_matches_whole_name():
    everything = RuleSet.from_lists(deny=["*"])
    assert permissions.decide("bash", {"command": "x"}, everything).kind == "deny"
    assert permissions.decide("read_file", {"path": "x"}, everything).kind == "deny"

    prefix = RuleSet.from_lists(deny=["read_*"])
    assert permissions.decide("read_file", {"path": "x"}, prefix).kind == "deny"
    assert permissions.decide("bash", {"command": "x"}, prefix).kind == "allow"

    # 未锚定的 glob 直接拒绝解析：官方是「跳过并告警」，告警会被淹没，
    # 而一条以为生效的 deny 没生效比没写更危险
    with pytest.raises(ValueError):
        permissions.parse_rule("*_file")


def test_decision_carries_reason_and_rule():
    """拒绝要说得出「被哪条规则挡的、规则从哪来」——否则用户无从修。"""
    rules = RuleSet.from_lists(deny=["Bash(rm *)"], source="user")

    decision = permissions.decide("bash", {"command": "rm -rf /"}, rules)

    assert decision.kind == "deny"
    assert decision.rule == Rule(tool="bash", specifier="rm *", source="user")
    assert "rm *" in decision.reason
    assert "user" in decision.reason


# ---- Task 2：匹配语义下放给工具 ----
#
# 权限层只管三态与求值顺序，「这次调用算不算命中这条规则」一律问工具要。
# 与既有约束「调度靠能力标志不靠工具名 if-else」是同一条。


def test_default_matcher_globs_first_argument():
    """没挂 matcher 的工具吃默认实现：对第一个参数值做通配符匹配。"""
    tools = {"fake": _fake_tool("fake")}
    rules = RuleSet.from_lists(deny=["fake(secret*)"])

    assert permissions.decide("fake", {"path": "secret.txt"}, rules, tools=tools).kind == "deny"
    assert permissions.decide("fake", {"path": "public.txt"}, rules, tools=tools).kind == "allow"


def test_matcher_for_attaches_to_registered_tool():
    from pai.core.tools import REGISTRY, matcher_for, tool as tool_decorator

    @tool_decorator
    def demo_tool(path: str) -> str:
        """演示工具。"""
        return path

    try:
        assert REGISTRY["demo_tool"].matcher is None

        @matcher_for(demo_tool)
        def _match(specifier, args, require_all, ctx):
            return specifier == "yes"

        assert REGISTRY["demo_tool"].matcher is _match
        assert REGISTRY["demo_tool"].matches("yes", {"path": "x"}, require_all=False)
        assert not REGISTRY["demo_tool"].matches("no", {"path": "x"}, require_all=False)
    finally:
        REGISTRY.pop("demo_tool", None)

    # 挂到没注册的工具上要当场炸：默默不生效等于权限规则静默失效
    with pytest.raises(ValueError):
        matcher_for("从来没注册过")(lambda s, a, r: True)


def test_permission_layer_never_branches_on_tool_name():
    """白盒：给假工具挂自定义 matcher，断言权限层调的就是它（证明没有工具名 if-else）。"""
    calls = []

    def spy(specifier, args, require_all, ctx):
        calls.append((specifier, args, require_all))
        return True

    tools = {"weird": _fake_tool("weird", matcher=spy)}
    rules = RuleSet.from_lists(deny=["weird(anything)"])

    decision = permissions.decide("weird", {"x": "y"}, rules, tools=tools)

    assert decision.kind == "deny"
    assert calls == [("anything", {"x": "y"}, False)]


def test_require_all_flag_is_passed_through():
    """allow 判定要求**每个**子命令都匹配，deny/ask 是**任一**命中即算——不对称是故意的。"""
    seen = []

    def spy(specifier, args, require_all, ctx):
        seen.append((specifier, require_all))
        return False          # 一律不命中，好让三个桶都被问一遍

    tools = {"t": _fake_tool("t", matcher=spy)}
    rules = RuleSet.from_lists(deny=["t(a)"], ask=["t(b)"], allow=["t(c)"])

    permissions.decide("t", {"x": "1"}, rules, tools=tools)

    assert seen == [("a", False), ("b", False), ("c", True)]


# ---- Task 3：bash 匹配器（分水岭）----
#
# 这一组决定权限系统是不是纸糊的。默认决策一律设成 deny，
# 好让「规则没匹配上」与「规则匹配了」区分得开——default_decision 是 allow 的话，
# 没匹配上也是放行，测了等于没测。


def _bash(command: str, **buckets):
    buckets.setdefault("default_decision", "deny")
    return permissions.decide("bash", {"command": command}, RuleSet.from_lists(**buckets)).kind


def test_compound_command_requires_every_subcommand_to_match():
    """`allow=["Bash(ls *)"]` 时 `ls && rm -rf /` 不放行。这条漏了权限系统等于零。"""
    assert _bash("ls -la && ls -a", allow=["Bash(ls *)"]) == "allow"
    assert _bash("ls -la && rm -rf /", allow=["Bash(ls *)"]) == "deny"


def test_any_subcommand_matching_deny_blocks():
    """deny 是「任一子命令命中即拦」——与 allow 的「每个都要匹配」不对称，故意的。"""
    assert _bash("echo hi && rm -rf /", deny=["Bash(rm *)"], default_decision="allow") == "deny"


def test_all_separators_split():
    for sep in ("&&", "||", ";", "|", "|&", "&", "\n"):
        command = f"ls -a {sep} rm -rf /"
        # 没拆开的话整串会被 `ls *` 前缀匹配掉而放行——所以断言 deny 正是在证明拆开了
        assert _bash(command, allow=["Bash(ls *)"]) == "deny", f"分隔符 {sep!r} 没拆开"


def test_process_wrappers_are_stripped():
    for wrapped in ("timeout 30 npm test", "nice npm test", "xargs npm test"):
        assert _bash(wrapped, allow=["Bash(npm test *)"]) == "allow", wrapped

    # 带标志就不剥：`xargs -n1 ...` 的语义已经不是「原样跑那条命令」了
    assert _bash("xargs -n1 npm test", allow=["Bash(npm test *)"]) == "deny"


def test_env_runners_are_not_stripped_and_this_is_a_known_hole():
    """官方承认的洞，写成测试固定下来而不是假装没有。

    `devbox run` / `npx` / `docker exec` 这类**环境运行器**不剥离，后果就是
    `Bash(devbox run *)` 会把 `devbox run rm -rf .` 一起放行。
    剥了更糟（等于承认任意命令能借壳），所以照抄官方的保守取舍。
    """
    assert _bash("devbox run rm -rf .", allow=["Bash(devbox run *)"]) == "allow"


def test_word_boundary_before_star():
    assert _bash("ls -la", allow=["Bash(ls *)"]) == "allow"
    assert _bash("lsof", allow=["Bash(ls *)"]) == "deny"

    # 不带空格的 `ls*` 是朴素通配，两者都匹配
    assert _bash("ls -la", allow=["Bash(ls*)"]) == "allow"
    assert _bash("lsof", allow=["Bash(ls*)"]) == "allow"


def test_colon_star_suffix_equals_trailing_space_star():
    assert _bash("npm test --watch", allow=["Bash(npm test:*)"]) == "allow"
    assert _bash("npm test", allow=["Bash(npm test:*)"]) == "allow"
    assert _bash("npm testfoo", allow=["Bash(npm test:*)"]) == "deny"


# ---- Task 4：fs 匹配器（路径锚点）----
#
# 四种前缀四种含义，`/` 那条是官方自己标注的最大的坑：
# 它锚到「定义这条规则的设置文件」，不是文件系统根，也不是 cwd。


def _fs(tool_name, path, rules, cwd, home):
    return permissions.decide(
        tool_name, {"path": str(path)}, rules, cwd=str(cwd), home=str(home)
    ).kind


def test_double_slash_is_filesystem_absolute(tmp_path):
    anchor = tmp_path / "proj"
    home = tmp_path / "home"
    rules = RuleSet.from_lists(
        deny=["read_file(//etc/**)"], anchor=str(anchor), default_decision="allow"
    )

    assert _fs("read_file", "/etc/passwd", rules, anchor, home) == "deny"
    # `//` 是文件系统绝对路径，**不**跟着规则来源走
    assert _fs("read_file", anchor / "etc" / "passwd", rules, anchor, home) == "allow"


def test_tilde_is_home_relative(tmp_path):
    anchor = tmp_path / "proj"
    home = tmp_path / "home"
    rules = RuleSet.from_lists(
        deny=["read_file(~/.ssh/**)"], anchor=str(anchor), default_decision="allow"
    )

    assert _fs("read_file", home / ".ssh" / "id_rsa", rules, anchor, home) == "deny"
    assert _fs("read_file", anchor / ".ssh" / "id_rsa", rules, anchor, home) == "allow"


def test_single_slash_anchors_to_the_settings_source(tmp_path):
    """官方最大的坑：用户设置里的 `/secrets/**` 指 `~/.pai/secrets/**`，不是项目里的 secrets/。"""
    home = tmp_path / "home"
    project = tmp_path / "proj"
    rules = RuleSet.from_lists(
        deny=["read_file(/secrets/**)"],
        source="user",
        anchor=str(home / ".pai"),
        default_decision="allow",
    )

    assert _fs("read_file", home / ".pai" / "secrets" / "k.txt", rules, project, home) == "deny"
    # 同名的项目内目录**不**受这条用户级规则管——以为管了正是那个坑
    assert _fs("read_file", project / "secrets" / "k.txt", rules, project, home) == "allow"


def test_bare_filename_matches_at_any_depth(tmp_path):
    """不含 `/` 的裸文件名按 gitignore 语义：`read_file(.env)` ≡ `read_file(**/.env)`。"""
    cwd = tmp_path / "proj"
    home = tmp_path / "home"
    rules = RuleSet.from_lists(
        deny=["read_file(.env)"], anchor=str(cwd), default_decision="allow"
    )

    assert _fs("read_file", cwd / ".env", rules, cwd, home) == "deny"
    assert _fs("read_file", cwd / "a" / "b" / ".env", rules, cwd, home) == "deny"
    assert _fs("read_file", cwd / "env.txt", rules, cwd, home) == "allow"


def test_relative_pattern_anchors_to_cwd(tmp_path):
    cwd = tmp_path / "proj"
    home = tmp_path / "home"
    rules = RuleSet.from_lists(
        deny=["read_file(src/*.py)"], anchor=str(cwd), default_decision="allow"
    )

    assert _fs("read_file", cwd / "src" / "a.py", rules, cwd, home) == "deny"
    # 单星不跨目录分隔符——跨了的话 allow 规则会悄悄放宽一层
    assert _fs("read_file", cwd / "src" / "deep" / "a.py", rules, cwd, home) == "allow"
    assert _fs("read_file", tmp_path / "other" / "src" / "a.py", rules, cwd, home) == "allow"


def test_symlink_double_check_is_not_implemented(tmp_path):
    """**如实记录已知洞**：只看给定路径，不做 realpath 双路径检查。

    这是 TODO 不是设计——官方的做法是 allow 要求「给定路径与真实路径都干净」、
    deny 是「任一脏就拦」。pai 这轮没做，于是一条符号链接就能绕开 deny 规则。
    本测试断言的是**当前行为**，做了双路径检查之后它应该变红并被改写。
    """
    cwd = tmp_path / "proj"
    home = tmp_path / "home"
    secrets = cwd / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "k.txt").write_text("x", encoding="utf-8")
    link = cwd / "innocent.txt"
    link.symlink_to(secrets / "k.txt")

    rules = RuleSet.from_lists(
        deny=["read_file(/secrets/**)"], anchor=str(cwd), default_decision="allow"
    )

    assert _fs("read_file", secrets / "k.txt", rules, cwd, home) == "deny"
    assert _fs("read_file", link, rules, cwd, home) == "allow"       # ← 洞


# ---- Task 5：配置加载与裸名 deny 摘工具 ----
#
# 两层设置：~/.pai/settings.json（用户）与 <项目根>/.pai/settings.json（项目）。
# 任一层的 deny 都不能被另一层的 allow 翻掉——这是求值顺序的自然结果，
# 但跨层的情形要专门钉一次，因为「合并」的写法一不小心就会让后读的层整个覆盖前一层。

import json

from fake_llm import FakeClient

from pai.core.loop import run_agent


def _settings(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_loads_user_then_project_settings(tmp_path):
    home, project = tmp_path / "home", tmp_path / "proj"
    _settings(home / ".pai" / "settings.json", {"permissions": {"allow": ["Bash(ls *)"]}})
    _settings(project / ".pai" / "settings.json", {"permissions": {"deny": ["Bash(rm *)"]}})

    rules = permissions.load_rules(cwd=str(project), home=str(home))

    assert [(r.text(), r.source) for r in rules.allow] == [("bash(ls *)", "user")]
    assert [(r.text(), r.source) for r in rules.deny] == [("bash(rm *)", "project")]
    # 锚点不同：用户级锚在设置文件所在的 ~/.pai，项目级锚在**项目根**（不是 .pai 子目录）
    assert rules.allow[0].anchor == str(home / ".pai")
    assert rules.deny[0].anchor == str(project)


def test_deny_in_either_layer_beats_allow_in_the_other(tmp_path):
    home, project = tmp_path / "home", tmp_path / "proj"

    # 方向一：用户层 deny，项目层 allow
    _settings(home / ".pai" / "settings.json", {"permissions": {"deny": ["Bash(rm *)"]}})
    _settings(project / ".pai" / "settings.json", {"permissions": {"allow": ["Bash(rm -rf tmp)"]}})
    rules = permissions.load_rules(cwd=str(project), home=str(home))
    assert permissions.decide("bash", {"command": "rm -rf tmp"}, rules).kind == "deny"

    # 方向二：项目层 deny，用户层 allow
    _settings(home / ".pai" / "settings.json", {"permissions": {"allow": ["Bash(rm -rf tmp)"]}})
    _settings(project / ".pai" / "settings.json", {"permissions": {"deny": ["Bash(rm *)"]}})
    rules = permissions.load_rules(cwd=str(project), home=str(home))
    assert permissions.decide("bash", {"command": "rm -rf tmp"}, rules).kind == "deny"


def test_malformed_settings_does_not_crash(tmp_path):
    """坏 JSON 留告警、当空规则集——绝不能把 agent 弄挂。"""
    home, project = tmp_path / "home", tmp_path / "proj"
    (project / ".pai").mkdir(parents=True)
    (project / ".pai" / "settings.json").write_text("{ 这不是 json", encoding="utf-8")
    _settings(home / ".pai" / "settings.json", {"permissions": {"allow": ["Bash(ls *)"]}})

    warnings = []
    rules = permissions.load_rules(cwd=str(project), home=str(home), warn=warnings.append)

    assert warnings and "settings.json" in warnings[0]
    # 坏的那层被跳过，好的那层照读——一个坏文件不该连累另一层
    assert [r.text() for r in rules.allow] == ["bash(ls *)"]
    assert rules.deny == [] and rules.ask == []


def test_bare_name_deny_removes_tool_from_schema(tmp_path):
    """裸名 deny = 工具从模型视野里消失，不是「摆着但拦下来」。"""
    from pai.core.tools import get_tools

    client = FakeClient([{"content": "好的"}])
    rules = RuleSet.from_lists(deny=["Bash"])

    run_agent(
        "干点啥",
        client=client,
        model="fake",
        tools=permissions.visible_tools(get_tools(), rules),
        on_event=lambda _: None,
    )

    sent = [t["function"]["name"] for t in client.requests[0]["tools"]]
    assert "bash" not in sent
    assert "read_file" in sent          # 只摘被 deny 的那个，别误伤


def test_scoped_deny_keeps_tool_visible(tmp_path):
    """带 specifier 的 deny 是「保留工具、拦具体调用」——官方明确区分这两种。"""
    from pai.core.tools import get_tools

    client = FakeClient([{"content": "好的"}])
    rules = RuleSet.from_lists(deny=["Bash(rm *)"])

    run_agent(
        "干点啥",
        client=client,
        model="fake",
        tools=permissions.visible_tools(get_tools(), rules),
        on_event=lambda _: None,
    )

    sent = [t["function"]["name"] for t in client.requests[0]["tools"]]
    assert "bash" in sent


# ---- feature 09 Task 1：工具自我声明「碰哪个路径、是读是写」----
#
# 延续拍板问 2 的「语义下放给工具」：目录边界要知道这次调用碰的是哪个路径、是读是写，
# 而这两件事只有工具自己知道。**权限层不许按工具名分支**。
# bash 两个都不声明，所以它结构上就进不了边界判定——不是靠 if 判掉的。


def test_fs_tools_declare_path_and_access():
    from pai.core.tools import get_tools

    tools = get_tools()
    assert tools["read_file"].access == "read"
    assert tools["write_file"].access == "write"
    assert tools["edit_file"].access == "write"
    for name in ("read_file", "write_file", "edit_file"):
        assert tools[name].get_path is not None, name


def test_bash_declares_neither():
    """拍板问 2 的结构性落点：bash 进不了边界判定，因为它没声明，不是因为有个 if。"""
    from pai.core.tools import get_tools

    bash = get_tools()["bash"]
    assert bash.access is None
    assert bash.get_path is None
    assert not bash.participates_in_boundary()


def test_tool_without_declaration_does_not_participate():
    tools = {"fake": _fake_tool("fake")}
    assert not tools["fake"].participates_in_boundary()

    from pai.core.tools import get_tools

    assert get_tools()["read_file"].participates_in_boundary()


def test_get_path_reads_the_declared_argument():
    """取的是**声明的那个参数**，不是「第一个参数」——两者碰巧一致时最容易写错。"""
    from pai.core.tools import get_tools

    tools = get_tools()
    assert tools["read_file"].get_path({"path": "a.txt"}) == "a.txt"
    # edit_file 的签名是 (path, old, new)：确认取的是 path 而不是别的
    assert tools["edit_file"].get_path({"path": "b.txt", "old": "x", "new": "y"}) == "b.txt"
    # 参数缺失不炸——权限判定期拿到脏输入是常态（模型可能发来任何东西）
    assert tools["read_file"].get_path({}) == ""


def test_path_access_for_rejects_unregistered_tool():
    from pai.core.tools import path_access_for

    with pytest.raises(ValueError):
        path_access_for("从来没注册过", "read")(lambda args: "")
