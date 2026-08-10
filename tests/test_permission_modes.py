"""权限模式四态（feature 09 Task 6）。

照 CC：**模式不是全局开关，是插在求值链特定位置的放行条件，且都有免疫项。**

  1 deny 规则          [bypass 免疫]
  2 危险路径写检查       [bypass 免疫]
  3 用户显式配的 ask 规则 [bypass 免疫]
  4 bypassPermissions → allow
  5 acceptEdits 且是写 且在界内 → allow
  6 allow 规则
  7 兜底（边界判定 / bash → ask）

第 3 步与第 7 步的区别是最容易实现错的地方：**用户显式写下的 ask 免疫，
兜底产生的 ask 不免疫**——否则 bypass 模式等于没有。两者都是 kind=="ask"，
区别只在 Decision.rule 是不是 None。
"""
import pytest

from pai.core import permissions
from pai.core.boundary import WorkingDirs
from pai.core.permissions import ACCEPT_EDITS, BYPASS, DEFAULT_MODE, DONT_ASK, RuleSet


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    (p / "src").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    return p


def _decide(proj, tool, args, mode=DEFAULT_MODE, rules=None):
    return permissions.decide(
        tool, args, rules if rules is not None else RuleSet(),
        working_dirs=WorkingDirs(startup_cwd=str(proj)),
        cwd=str(proj), home=str(proj.parent / "home"), mode=mode,
    )


def test_default_mode_is_the_baseline(proj):
    assert _decide(proj, "read_file", {"path": str(proj / "src" / "a.py")}).kind == "allow"
    assert _decide(proj, "write_file",
                   {"path": str(proj / "a.py"), "content": "x"}).kind == "ask"


def test_accept_edits_allows_writes_inside_boundary(proj):
    kind = _decide(proj, "write_file",
                   {"path": str(proj / "src" / "a.py"), "content": "x"},
                   mode=ACCEPT_EDITS).kind
    assert kind == "allow"


def test_accept_edits_still_respects_boundary(proj):
    """**模式不免边界**（照 CC 的 `mode === 'acceptEdits' && isInWorkingDir`）。"""
    outside = proj.parent / "outside" / "x.py"
    assert _decide(proj, "write_file", {"path": str(outside), "content": "x"},
                   mode=ACCEPT_EDITS).kind == "ask"


def test_accept_edits_still_respects_dangerous_paths(proj):
    home = proj.parent / "home"
    (home / ".pai").mkdir(parents=True, exist_ok=True)
    assert _decide(proj, "write_file", {"path": str(home / ".bashrc"), "content": "x"},
                   mode=ACCEPT_EDITS).kind == "ask"


def test_accept_edits_does_not_touch_bash(proj):
    """acceptEdits 只管 edits——bash 仍然走兜底 ask。"""
    assert _decide(proj, "bash", {"command": "ls"}, mode=ACCEPT_EDITS).kind == "ask"


def test_bypass_allows_fallback_ask(proj):
    """兜底产生的 ask（界外读、写、bash）在 bypass 下放行。"""
    outside = proj.parent / "outside" / "x.py"
    assert _decide(proj, "read_file", {"path": str(outside)}, mode=BYPASS).kind == "allow"
    assert _decide(proj, "write_file", {"path": str(outside), "content": "x"},
                   mode=BYPASS).kind == "allow"
    assert _decide(proj, "bash", {"command": "rm -rf /"}, mode=BYPASS).kind == "allow"


def test_bypass_is_immune_to_deny_rules(proj):
    """**免疫一**。"""
    rules = RuleSet.from_lists(deny=["Bash(rm *)"])
    assert _decide(proj, "bash", {"command": "rm -rf /"}, mode=BYPASS, rules=rules).kind == "deny"


def test_bypass_is_immune_to_explicit_ask_rules(proj):
    """**免疫二——最容易实现错的一条**。

    用户显式写下的 ask 规则在 bypass 下仍然问（CC 注释：must be respected even in
    bypass mode），而兜底产生的 ask 放行。两者都是 kind=="ask"。
    """
    rules = RuleSet.from_lists(ask=["Bash(git push *)"])

    assert _decide(proj, "bash", {"command": "git push origin main"},
                   mode=BYPASS, rules=rules).kind == "ask"
    # 同一次调用里，没被显式规则命中的 bash 仍然放行 —— 这就是两者的区别
    assert _decide(proj, "bash", {"command": "ls"}, mode=BYPASS, rules=rules).kind == "allow"


def test_bypass_is_immune_to_dangerous_paths(proj):
    """**免疫三**。"""
    home = proj.parent / "home"
    (home / ".pai").mkdir(parents=True, exist_ok=True)
    assert _decide(proj, "write_file", {"path": str(home / ".bashrc"), "content": "x"},
                   mode=BYPASS).kind == "ask"


def test_dont_ask_turns_ask_into_deny_without_asking(proj):
    """dontAsk 不在求值链上，是对最终结果的后处理——且**不调用 asker**。"""
    from pai.core.gate import make_before_tool_call

    asked = []
    gate = make_before_tool_call(
        RuleSet(), working_dirs=WorkingDirs(startup_cwd=str(proj)),
        cwd=str(proj), asker=lambda q, o: asked.append(q) or o[0], mode=DONT_ASK)

    assert gate("bash", {"command": "ls"}).kind == "deny"
    assert gate("read_file", {"path": str(proj / "src" / "a.py")}).kind == "allow"
    assert asked == []          # 一次都没问


def test_no_human_is_equivalent_to_dont_ask(proj):
    """`asker is None`（once 无真人）与 `mode == dontAsk` 走同一段代码（D#48 显式化）。"""
    from pai.core.gate import make_before_tool_call

    kw = dict(working_dirs=WorkingDirs(startup_cwd=str(proj)), cwd=str(proj))
    no_human = make_before_tool_call(RuleSet(), asker=None, **kw)
    dont_ask = make_before_tool_call(RuleSet(), asker=lambda q, o: o[0],
                                     mode=DONT_ASK, **kw)

    assert no_human("bash", {"command": "ls"}).kind == dont_ask("bash", {"command": "ls"}).kind


def test_mode_from_settings(tmp_path):
    import json

    home, project = tmp_path / "home", tmp_path / "proj"
    for d, mode in ((home / ".pai", DONT_ASK), (project / ".pai", ACCEPT_EDITS)):
        d.mkdir(parents=True)
        (d / "settings.json").write_text(
            json.dumps({"permissions": {"defaultMode": mode}}), encoding="utf-8")

    rules = permissions.load_rules(cwd=str(project), home=str(home))

    assert rules.mode == ACCEPT_EDITS          # 项目层覆盖用户层


def test_invalid_mode_in_settings_falls_back_with_warning(tmp_path):
    import json

    project = tmp_path / "proj"
    (project / ".pai").mkdir(parents=True)
    (project / ".pai" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "乱写的"}}), encoding="utf-8")
    warnings = []

    rules = permissions.load_rules(cwd=str(project), home=str(tmp_path / "home"),
                                   warn=warnings.append)

    assert rules.mode == DEFAULT_MODE
    assert warnings


def test_unknown_mode_is_rejected_at_the_api(proj):
    with pytest.raises(ValueError):
        _decide(proj, "bash", {"command": "ls"}, mode="乱写的")
