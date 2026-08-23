"""feature 25 · skills：扫描层（T1）/ 索引层（T2）/ 工具层（T3）……

规约对齐 AGENTS：全部离线、tmp_path 隔离、不碰真实 $HOME
（conftest 的 autouse fixture 已结构性隔离，但测试仍显式传 cwd/home——
路径默认值属于被测行为的，单独钉）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pai.core import paths
from pai.core.skills import Skill, scan_skills


def _write_skill(root: Path, name: str, description: str = "一句描述",
                 body: str = "正文第一行", extra_front: str = "",
                 flat: bool = False) -> Path:
    """造一个 skill：默认目录包 `<name>/SKILL.md`，flat=True 时造 `<name>.md`。"""
    if flat:
        path = root / f"{name}.md"
    else:
        path = root / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = f"---\ndescription: {description}\n{extra_front}---\n" if description else "---\n---\n"
    path.write_text(front + body + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- T1 · 路径

def test_skills_paths_live_in_paths_module(tmp_path):
    """路径规则只此一处（feature 08）：用户级 ~/.pai/skills，项目级 <git根>/.pai/skills。"""
    home = tmp_path / "home"
    assert paths.user_skills_dir(home) == home / ".pai" / "skills"
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "src" / "deep"
    sub.mkdir(parents=True)
    # 子目录里启动也拿到仓库根的 skills（与 project_slug 的项目定义一致）
    assert paths.project_skills_dir(sub) == repo / ".pai" / "skills"


def test_project_skills_dir_without_git_uses_cwd(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert paths.project_skills_dir(plain) == plain / ".pai" / "skills"


# ---------------------------------------------------------------- T1 · 扫描

def test_scan_finds_directory_bundle_skill(tmp_path):
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "deploy-notes", description="部署须知")
    found = scan_skills(cwd=tmp_path / "proj", home=home)
    assert [s.name for s in found] == ["deploy-notes"]
    s = found[0]
    assert s.description == "部署须知"
    assert s.source == "user"
    assert s.path.name == "SKILL.md"
    assert s.base_dir == s.path.parent
    assert s.model_invocable is True


def test_scan_finds_flat_markdown_skill(tmp_path):
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "one-liner", flat=True)
    found = scan_skills(cwd=tmp_path / "proj", home=home)
    assert [s.name for s in found] == ["one-liner"]
    assert found[0].base_dir == found[0].path.parent


def test_scan_project_beats_user_on_same_name(tmp_path):
    """拍板问 3：同名项目级赢（dsh 语义，越具体越优先）。"""
    home, proj = tmp_path / "home", tmp_path / "proj"
    _write_skill(home / ".pai" / "skills", "conv", description="用户级")
    _write_skill(proj / ".pai" / "skills", "conv", description="项目级")
    found = scan_skills(cwd=proj, home=home)
    assert len(found) == 1
    assert found[0].description == "项目级"
    assert found[0].source == "project"


def test_scan_directory_bundle_beats_flat_file_in_same_root(tmp_path):
    home = tmp_path / "home"
    root = home / ".pai" / "skills"
    _write_skill(root, "dup", description="目录包")
    _write_skill(root, "dup", description="扁平", flat=True)
    found = scan_skills(cwd=tmp_path / "proj", home=home)
    assert len(found) == 1
    assert found[0].description == "目录包"


def test_scan_skips_missing_description_and_warns(tmp_path):
    """fail loud（evidence P1 的直接结论）：缺 description 跳过并提示，
    刻意不抄 CC 的「回退正文首段」——那条回退把写坏的 frontmatter 伪装成正常 skill。"""
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "no-desc", description="")
    warnings: list[str] = []
    found = scan_skills(cwd=tmp_path / "proj", home=home, warn=warnings.append)
    assert found == []
    assert len(warnings) == 1
    assert "no-desc" in warnings[0] and "description" in warnings[0]


def test_scan_skips_broken_frontmatter_and_warns(tmp_path):
    """坏 frontmatter（围栏没收尾）按「没有 frontmatter」处理 → 无 description → 跳过。"""
    home = tmp_path / "home"
    path = home / ".pai" / "skills" / "broken" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\ndescription: [烂掉的\n正文\n", encoding="utf-8")
    warnings: list[str] = []
    found = scan_skills(cwd=tmp_path / "proj", home=home, warn=warnings.append)
    assert found == []
    assert warnings, "坏 frontmatter 必须有提示，不许静默消失"


def test_scan_reads_disable_model_invocation(tmp_path):
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "manual-only",
                 extra_front="disable-model-invocation: true\n")
    found = scan_skills(cwd=tmp_path / "proj", home=home)
    assert found[0].model_invocable is False


def test_scan_warns_on_non_kebab_name_but_still_loads(tmp_path):
    """名字校验宽松（pi 语义）：warn 不拒载。路径来自扫描结果，name 不反推路径，无穿越面。"""
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "Bad_Name", description="大写下划线")
    warnings: list[str] = []
    found = scan_skills(cwd=tmp_path / "proj", home=home, warn=warnings.append)
    assert [s.name for s in found] == ["Bad_Name"]
    assert any("Bad_Name" in w for w in warnings)


def test_scan_ignores_deeper_nesting_and_hidden_entries(tmp_path):
    """不递归更深层（dsh 语义，pi 的递归发现记遗留）；`.` 开头目录跳过。"""
    home = tmp_path / "home"
    root = home / ".pai" / "skills"
    _write_skill(root / "outer" / "inner", "nested")     # outer/ 里没有 SKILL.md
    _write_skill(root, ".hidden")
    found = scan_skills(cwd=tmp_path / "proj", home=home)
    assert found == []


def test_scan_missing_roots_yield_empty(tmp_path):
    assert scan_skills(cwd=tmp_path / "nowhere", home=tmp_path / "nohome") == []


def test_scan_frontmatter_name_is_ignored(tmp_path):
    """名字来源照三家共识与 evidence P2：目录名就是名字，frontmatter name 只是显示项。"""
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "dir-name",
                 extra_front="name: totally-different\n")
    found = scan_skills(cwd=tmp_path / "proj", home=home)
    assert [s.name for s in found] == ["dir-name"]


# ---------------------------------------------------------------- T2 · 目录渲染

from pai.core.skills import (  # noqa: E402
    MAX_CATALOG_DESC_CHARS,
    render_catalog,
)


def _mk(name: str, description: str = "描述", invocable: bool = True,
        tmp: Path = Path("/tmp")) -> Skill:
    return Skill(name=name, description=description, path=tmp / name / "SKILL.md",
                 base_dir=tmp / name, source="user", model_invocable=invocable)


def test_catalog_lists_name_and_description_sorted():
    text = render_catalog([_mk("b-skill", "乙"), _mk("a-skill", "甲")])
    assert text.startswith("<available_skills>")
    assert text.index("a-skill") < text.index("b-skill")
    assert "<description>甲</description>" in text


def test_catalog_has_no_file_paths():
    """工具形态下目录不给路径（dsh 配对）：给了只会诱导模型绕过工具直接 read。"""
    text = render_catalog([_mk("x")])
    assert "/tmp" not in text and "SKILL.md" not in text


def test_catalog_escapes_xml():
    text = render_catalog([_mk("esc", description='含 <tag> & "引号"')])
    assert "&lt;tag&gt;" in text and "&amp;" in text
    assert "<tag>" not in text


def test_catalog_excludes_disable_model_invocation():
    text = render_catalog([_mk("hidden", invocable=False), _mk("shown")])
    assert "hidden" not in text and "shown" in text


def test_catalog_empty_returns_empty_string():
    assert render_catalog([]) == ""
    assert render_catalog([_mk("h", invocable=False)]) == ""


def test_catalog_caps_each_description():
    text = render_catalog([_mk("long", description="很" * 900)])
    assert "很" * (MAX_CATALOG_DESC_CHARS + 1) not in text
    assert "…" in text


def test_catalog_total_budget_truncates_with_hint():
    many = [_mk(f"skill-{i:03d}", description="占" * 400) for i in range(60)]
    text = render_catalog(many)
    assert len(text.encode("utf-8")) < 10_000
    assert "已截断" in text and "60 个" in text


# ---------------------------------------------------------------- T2 · prompt 装配

from pai.core.loop import build_system_prompt  # noqa: E402


def test_prompt_without_catalog_is_byte_identical():
    """feature 22 既有不变量的延伸：不传 skills_catalog 时输出逐字节不变（护缓存前缀）。"""
    tools = {"bash": None, "read_file": None}
    assert build_system_prompt(tools) == build_system_prompt(tools, skills_catalog=None)
    assert "skill" not in build_system_prompt(tools)


def test_prompt_appends_catalog_when_skill_tool_present():
    tools = {"bash": None, "skill": None}
    catalog = render_catalog([_mk("deploy-notes", "部署须知")])
    text = build_system_prompt(tools, skills_catalog=catalog)
    assert "<available_skills>" in text and "deploy-notes" in text
    assert "skill 工具" in text          # 指导语点名工具


def test_prompt_ignores_catalog_when_skill_tool_absent():
    """目录跟着工具走：没有 skill 工具的装配（受限工具集）不该出现调不动的目录。"""
    tools = {"bash": None}
    catalog = render_catalog([_mk("deploy-notes")])
    assert build_system_prompt(tools, skills_catalog=catalog) == build_system_prompt(tools)


def test_prompt_ignores_empty_catalog():
    tools = {"bash": None, "skill": None}
    assert build_system_prompt(tools, skills_catalog="") == build_system_prompt(tools)


# ---------------------------------------------------------------- T3 · skill 工具

from pai.core.tools import READ, all_tools  # noqa: E402
from pai.core.tools import skill as skill_mod  # noqa: E402


@pytest.fixture
def skill_env(tmp_path):
    """扫一个真目录、注入工具模块，测完复原（注入点是进程级，同 memory_tool 的测法）。"""
    home = tmp_path / "home"
    _write_skill(home / ".pai" / "skills", "alpha", description="甲技能",
                 body="# Alpha\n照此办理。")
    _write_skill(home / ".pai" / "skills", "manual-only", description="只许人调",
                 extra_front="disable-model-invocation: true\n", body="人调正文")
    skills = scan_skills(cwd=tmp_path / "proj", home=home)
    tracker = skill_mod.LoadedSkills()
    skill_mod.set_catalog({s.name: s for s in skills})
    skill_mod.set_tracker(tracker)
    try:
        yield {"skills": {s.name: s for s in skills}, "tracker": tracker,
               "tool": all_tools()["skill"]}
    finally:
        skill_mod.set_catalog(None)
        skill_mod.set_tracker(None)


def test_skill_tool_returns_body_with_base_dir_note(skill_env):
    out = skill_env["tool"].run(name="alpha")
    assert '<skill_content name="alpha">' in out
    assert "照此办理。" in out
    assert "description: 甲技能" not in out          # frontmatter 剥掉
    assert str(skill_env["skills"]["alpha"].base_dir) in out


def test_skill_tool_rereads_disk_each_call(skill_env):
    """dsh 语义：不缓存正文，改盘即生效。"""
    first = skill_env["tool"].run(name="alpha")
    skill_env["skills"]["alpha"].path.write_text(
        "---\ndescription: 甲技能\n---\n改过的正文\n", encoding="utf-8")
    second = skill_env["tool"].run(name="alpha")
    assert "照此办理。" in first and "改过的正文" in second


def test_skill_tool_unknown_name_lists_available(skill_env):
    out = skill_env["tool"].run(name="no-such")
    assert "未知或不可用" in out and "alpha" in out
    assert "权限" not in out                        # R4#10 教训：不撞权限话术


def test_skill_tool_hides_disable_model_invocation(skill_env):
    """模型调被隐藏的 skill：与未知同一句话，不泄露它的存在（dsh 语义）。"""
    out = skill_env["tool"].run(name="manual-only")
    assert "未知或不可用" in out
    assert "manual-only" not in out.replace("未知或不可用的 skill：manual-only", "")


def test_skill_tool_records_into_tracker(skill_env):
    assert not skill_env["tracker"]
    skill_env["tool"].run(name="alpha")
    assert skill_env["tracker"].names_recent_first() == ["alpha"]
    skill_env["tool"].run(name="no-such")           # 失败不记
    assert skill_env["tracker"].names_recent_first() == ["alpha"]


def test_skill_tool_without_catalog_says_no_skills(tmp_path):
    skill_mod.set_catalog(None)
    out = all_tools()["skill"].run(name="alpha")
    assert "没有配置任何 skill" in out


def test_skill_tool_capabilities_and_boundary_declarations(skill_env):
    tool = skill_env["tool"]
    assert tool.read_only({"name": "alpha"}) is True
    assert tool.concurrency_safe({"name": "alpha"}) is True
    # feature 27：skill 不参与路径边界——正文路径由装配层扫描自算，入参只有名字。
    # 「读 SKILL.md 这个路径」的建模是三家参照里没有的孤例（CC 的 SkillTool 无
    # getPath、dsh 的门是 isModelInvocable 策略位），豁免位显式声明。
    assert tool.get_path is None and tool.access is None
    assert tool.boundary_exempt is True


# ---------------------------------------------------------------- T4 · 边界与 once 接线

import json  # noqa: E402

from pai.core.boundary import WorkingDirs  # noqa: E402
from pai.core.permissions import RuleSet, decide  # noqa: E402
from tests.fake_llm import FakeClient  # noqa: E402


def test_decide_allows_skill_tool_via_boundary_exemption(skill_env, tmp_path):
    """feature 27（25 复核高 2）：skill 工具兜底放行走豁免位，不再依赖 skills 根
    在不在边界里——子目录启动、软链正文这类「路径在界外」的形态不再撞权限话术。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    dirs = WorkingDirs.from_startup(str(proj))       # 不含任何 skills 根
    d = decide("skill", {"name": "alpha"}, RuleSet(), tools=all_tools(),
               working_dirs=dirs)
    assert d.kind == "allow"


def test_decide_skill_exemption_yields_to_deny_and_ask_rules(skill_env, tmp_path):
    """豁免只作用于兜底（求值链第 7 步）：deny 规则与用户显式 ask 规则照常在前。
    豁免位用错等于在权限层开洞，这条钉优先级不许倒。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    dirs = WorkingDirs.from_startup(str(proj))
    d = decide("skill", {"name": "alpha"}, RuleSet.from_lists(deny=["skill"]),
               tools=all_tools(), working_dirs=dirs)
    assert d.kind == "deny"
    d2 = decide("skill", {"name": "alpha"}, RuleSet.from_lists(ask=["skill"]),
                tools=all_tools(), working_dirs=dirs)
    assert d2.kind == "ask" and d2.rule is not None


def test_decide_skill_attachments_still_walk_the_boundary(skill_env, tmp_path):
    """豁免只给 skill 工具自己；附属文件走 read_file 仍按既有边界判——
    这就是用户级根仍须进 additional 的理由（25 遗留 6 的声明不变）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    user_root = paths.user_skills_dir(tmp_path / "home")
    ref = user_root / "alpha" / "references.md"
    bare = WorkingDirs.from_startup(str(proj))
    d = decide("read_file", {"path": str(ref)}, RuleSet(), tools=all_tools(),
               working_dirs=bare)
    assert d.kind == "ask"
    with_root = WorkingDirs.from_startup(str(proj), additional=(str(user_root),))
    d2 = decide("read_file", {"path": str(ref)}, RuleSet(), tools=all_tools(),
                working_dirs=with_root)
    assert d2.kind == "allow"


def _once_env(tmp_path, monkeypatch, *, with_skill: bool = True):
    """在隔离 HOME 里放一个用户级 skill，chdir 到干净项目目录。"""
    home = Path.home()                       # conftest 已把 HOME 指到临时目录
    if with_skill:
        _write_skill(home / ".pai" / "skills", "alpha", description="甲技能",
                     body="ALPHA-BODY-TOKEN")
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    monkeypatch.chdir(proj)


def test_once_loads_user_level_skill_in_dontask_mode(tmp_path, monkeypatch):
    """once（无真人，dontAsk）下加载用户级 skill 必须成功——
    否则「skills 跟人走」在最常用的模式里结构性不可用。"""
    from pai.modes.once import run_once
    _once_env(tmp_path, monkeypatch)
    script = [
        {"tool_calls": [("skill", json.dumps({"name": "alpha"}))]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    tool_msgs = [m for m in client.requests[-1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs, "skill 调用必须有回填"
    assert "ALPHA-BODY-TOKEN" in tool_msgs[0]["content"]
    assert "权限被拒绝" not in tool_msgs[0]["content"]


def test_once_loads_project_skill_from_repo_subdir(tmp_path, monkeypatch):
    """25 复核高 2 的回归场景：从仓库子目录启动，项目级 skill 照常进目录，
    工具调用必须拿到正文而非权限拒绝（此前扫描按 git 根、边界按 cwd，
    once/dontAsk 下直接死——正是 R4#10 要避开的权限话术，feature 27 修）。"""
    from pai.modes.once import run_once
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    _write_skill(repo / ".pai" / "skills", "alpha", description="甲技能",
                 body="SUBDIR-BODY-TOKEN")
    sub = repo / "src" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    script = [
        {"tool_calls": [("skill", json.dumps({"name": "alpha"}))]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    assert "<available_skills>" in client.requests[0]["messages"][0]["content"]
    tool_msgs = [m for m in client.requests[-1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs, "skill 调用必须有回填"
    assert "SUBDIR-BODY-TOKEN" in tool_msgs[0]["content"]
    assert "权限被拒绝" not in tool_msgs[0]["content"]


def test_once_system_prompt_carries_catalog(tmp_path, monkeypatch):
    from pai.modes.once import run_once
    _once_env(tmp_path, monkeypatch)
    client = FakeClient([{"content": "done"}])
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    system = client.requests[0]["messages"][0]
    assert system["role"] == "system"
    assert "<available_skills>" in system["content"]
    assert "甲技能" in system["content"]
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "skill" in tool_names


def test_once_without_skills_hides_skill_tool(tmp_path, monkeypatch):
    """没有任何 skill 时不摆 skill 工具——摆一个必然空手而归的工具就是让模型撞空
    （与 INTERACTIVE_ONLY 藏 ask_user_question 同一个道理）。"""
    from pai.modes.once import run_once
    _once_env(tmp_path, monkeypatch, with_skill=False)
    client = FakeClient([{"content": "done"}])
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "skill" not in tool_names
    assert "<available_skills>" not in client.requests[0]["messages"][0]["content"]


def test_once_all_disabled_also_hides_skill_tool(tmp_path, monkeypatch):
    """25 复核低 3：全部 skill 都 disable-model-invocation 时同样收走工具——
    once 连 /skill 通道都没有，这个工具对谁都空手而归。"""
    from pai.modes.once import run_once
    home = Path.home()
    _write_skill(home / ".pai" / "skills", "manual-only", description="只许人调",
                 extra_front="disable-model-invocation: true\n")
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    monkeypatch.chdir(proj)
    client = FakeClient([{"content": "done"}])
    run_once("x", client=client, model="fake", no_session=True, on_event=lambda _: None)
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "skill" not in tool_names
    assert "<available_skills>" not in client.requests[0]["messages"][0]["content"]


# ---------------------------------------------------------------- T5 · 压缩后重挂

import copy  # noqa: E402

from pai.core.skills import (  # noqa: E402
    LoadedSkills,
    make_instructions,
    render_loaded_skills,
)


def _catalog_from(tmp_path, *specs):
    """specs: (name, body) 列表 → 真文件 + 目录表。"""
    home = tmp_path / "home"
    for name, body in specs:
        _write_skill(home / ".pai" / "skills", name, description=f"{name} 描述", body=body)
    skills = scan_skills(cwd=tmp_path / "proj", home=home)
    return {s.name: s for s in skills}


def test_reattach_renders_recent_first_and_rereads_disk(tmp_path):
    catalog = _catalog_from(tmp_path, ("early", "早正文"), ("late", "晚正文"))
    loaded = LoadedSkills()
    loaded.record("early")
    loaded.record("late")
    text = render_loaded_skills(loaded, catalog)
    assert text.index("late") < text.index("early")          # 最近优先
    catalog["late"].path.write_text("---\ndescription: d\n---\n盘上新内容\n",
                                    encoding="utf-8")
    assert "盘上新内容" in render_loaded_skills(loaded, catalog)   # 重挂时现读磁盘


def test_reattach_truncates_head_and_drops_over_total_budget(tmp_path):
    catalog = _catalog_from(tmp_path, ("big", "头部要保住 " + "长" * 300),
                            ("second", "次正文"))
    loaded = LoadedSkills()
    loaded.record("second")
    loaded.record("big")                                     # big 最近
    text = render_loaded_skills(loaded, catalog, per_skill_chars=50, total_chars=52)
    assert "头部要保住" in text                               # 单个超限截头部保留
    assert "已截断" in text
    assert "次正文" not in text                               # 总预算装不下整条丢弃


def test_reattach_skips_deleted_files_and_empty_is_empty(tmp_path):
    catalog = _catalog_from(tmp_path, ("gone", "会消失"))
    loaded = LoadedSkills()
    loaded.record("gone")
    catalog["gone"].path.unlink()
    assert render_loaded_skills(loaded, catalog) == ""
    assert render_loaded_skills(LoadedSkills(), catalog) == ""


def test_loaded_skills_record_is_thread_safe():
    """25 复核低 2：skill 工具声明 concurrency_safe=True 会进调度线程池，
    追踪器 record 在执行期写——`_seq += 1` 是读改写，无锁会丢增量。
    缩小线程切换间隔逼出竞争（无锁时探针 5/5 复现，丢约 35%）。"""
    import sys
    import threading
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        loaded = LoadedSkills()
        n_threads, per_thread = 8, 5000

        def worker(tid: int) -> None:
            for i in range(per_thread):
                loaded.record(f"s{tid}-{i}")

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert loaded._seq == n_threads * per_thread, \
            "并发 record 丢了增量——「最近优先」的排序会退化成运气"
    finally:
        sys.setswitchinterval(old)


def test_make_instructions_composes_base_and_loaded(tmp_path):
    catalog = _catalog_from(tmp_path, ("alpha", "甲正文"))
    loaded = LoadedSkills()
    inst = make_instructions(lambda: "基础指令", loaded, catalog)
    assert inst() == "基础指令"                               # 没加载过：与 base 一字不差
    loaded.record("alpha")
    text = inst()
    assert text.startswith("基础指令")
    assert '<skill_content name="alpha">' in text and "甲正文" in text


def test_compaction_reinjects_loaded_skill_body(tmp_path, monkeypatch):
    """验收标准 4（R4#A4 点名的 CC 坑）：压缩重建后，已加载 skill 的正文仍在上下文里。

    底料用 REAL_TRAJECTORY（真实会话轨迹夹具，AGENTS 规约）。场景是三锚节奏
    （feature 26 修假绿）：skill 轮之后再来两轮 bash，让 find_cut_point 的刀落在
    skill 轮之后、把它的 tool_result 真的摘出上下文——25 复核证明两锚版里正文被
    keep-recent 尾段保住，掐断重挂测试照样绿。双向断言：token 不在任何 tool 消息
    （自证正文真被摘掉了，防场景漂移回假绿）+ token 在指令消息（只可能来自重挂——
    组合 loader 在压缩重建后被 loop 重新调用，届时追踪器里已有加载记录，D#42 的车）。
    """
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools
    from tests.test_compaction import REAL_TRAJECTORY

    catalog = _catalog_from(tmp_path, ("alpha", "ALPHA-REATTACH-TOKEN"))
    loaded = LoadedSkills()
    skill_mod.set_catalog(catalog)
    skill_mod.set_tracker(loaded)
    try:
        script = [
            {"tool_calls": [("skill", json.dumps({"name": "alpha"}))],
             "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}},
            {"tool_calls": [("bash", json.dumps({"command": "true"}))],
             "usage": {"prompt_tokens": 390, "completion_tokens": 10, "total_tokens": 400}},
            {"tool_calls": [("bash", json.dumps({"command": "true"}))],
             "usage": {"prompt_tokens": 840, "completion_tokens": 10, "total_tokens": 850}},
            {"content": "这是摘要"},
            {"content": "done"},
        ]
        client = FakeClient(script)
        messages = copy.deepcopy(REAL_TRAJECTORY)
        answer = run_agent(
            "继续", client=client, model="fake",
            tools=get_tools(["bash", "read_file", "write_file", "edit_file", "skill"]),
            messages=messages, context_window=1000, max_steps=8,
            compaction=CompactionSettings(reserve_tokens=200, keep_recent_tokens=1),
            instructions=make_instructions(lambda: "# 项目指令与记忆（来自 PAI.md 与自动记忆）\n基础",
                                           loaded, catalog),
            on_event=lambda _: None)
        assert answer == "done"
        summary_reqs = [r for r in client.requests if "tools" not in r]
        assert summary_reqs, "场景必须真的触发了压缩，否则本测试在测空气"
        tool_bodies = [m.get("content") or "" for m in messages if m.get("role") == "tool"]
        assert not any("ALPHA-REATTACH-TOKEN" in body for body in tool_bodies), \
            "skill 的 tool_result 必须真的被压缩摘掉——它还在就说明场景漂回了假绿（25 复核）"
        inst_msgs = [m for m in messages
                     if m.get("role") == "user" and "# 项目指令与记忆" in (m.get("content") or "")]
        assert inst_msgs, "压缩重建后必须有指令消息"
        assert "ALPHA-REATTACH-TOKEN" in inst_msgs[0]["content"], \
            "正文被摘掉后，token 只可能经重挂回到指令消息——不在就是重挂没生效"
    finally:
        skill_mod.set_catalog(None)
        skill_mod.set_tracker(None)


# ---------------------------------------------------------------- T6 · /skill 命令与 REPL 装配

from pai.core.permissions import RuleSet as _RuleSet  # noqa: E402
from pai.modes.interactive import HELP, run_interactive  # noqa: E402

_OPEN = _RuleSet.from_lists(default_decision="allow")


def _repl(lines, script, tmp_path, monkeypatch):
    home = Path.home()                       # conftest 已隔离
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    monkeypatch.chdir(proj)
    out: list = []
    client = FakeClient(script)

    def reader(prompt=""):
        if not lines:
            raise EOFError
        return lines.pop(0)

    run_interactive(client=client, model="fake", reader=reader, out=out.append,
                    on_event=lambda _: None, no_session=True, rules=_OPEN)
    return client, "\n".join(out)


def test_help_mentions_skill_command():
    assert "/skill" in HELP


def test_repl_skill_command_expands_and_runs_turn(tmp_path, monkeypatch):
    _write_skill(Path.home() / ".pai" / "skills", "alpha", description="甲技能",
                 body="ALPHA-REPL-TOKEN")
    client, printed = _repl(["/skill alpha 加急处理"], [{"content": "收到"}],
                            tmp_path, monkeypatch)
    assert len(client.requests) == 1
    user_msgs = [m for m in client.requests[0]["messages"] if m["role"] == "user"]
    expanded = user_msgs[-1]["content"]
    assert '<skill name="alpha">' in expanded
    assert "ALPHA-REPL-TOKEN" in expanded
    assert "加急处理" in expanded            # 参数追加在块后（pi 形态）


def test_repl_bare_skill_lists_without_model_call(tmp_path, monkeypatch):
    _write_skill(Path.home() / ".pai" / "skills", "alpha", description="甲技能")
    client, printed = _repl(["/skill"], [], tmp_path, monkeypatch)
    assert client.requests == []
    assert "alpha" in printed and "甲技能" in printed


def test_repl_skill_unknown_name_no_model_call(tmp_path, monkeypatch):
    _write_skill(Path.home() / ".pai" / "skills", "alpha", description="甲技能")
    client, printed = _repl(["/skill nope"], [], tmp_path, monkeypatch)
    assert client.requests == []
    assert "nope" in printed and "alpha" in printed


def test_repl_system_prompt_carries_catalog_and_tool(tmp_path, monkeypatch):
    _write_skill(Path.home() / ".pai" / "skills", "alpha", description="甲技能")
    client, _ = _repl(["随便问一句"], [{"content": "答"}], tmp_path, monkeypatch)
    system = client.requests[0]["messages"][0]
    assert "<available_skills>" in system["content"]
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "skill" in tool_names


def test_repl_without_skills_hides_tool_and_catalog(tmp_path, monkeypatch):
    client, _ = _repl(["问一句"], [{"content": "答"}], tmp_path, monkeypatch)
    system = client.requests[0]["messages"][0]
    assert "<available_skills>" not in system["content"]
    tool_names = {t["function"]["name"] for t in client.requests[0]["tools"]}
    assert "skill" not in tool_names


def test_repl_all_disabled_hides_tool_but_keeps_user_channel(tmp_path, monkeypatch):
    """25 复核低 3：全部 skill 都 disable-model-invocation 时目录为空，模型调
    skill 必然空手而归——照「不摆撞空的工具」原则收走；/skill 用户通道不受影响
    （它走 get_catalog，不走工具集）。"""
    _write_skill(Path.home() / ".pai" / "skills", "manual-only", description="只许人调",
                 extra_front="disable-model-invocation: true\n", body="人调正文")
    client, printed = _repl(["/skill manual-only", "随便问一句"],
                            [{"content": "收到"}, {"content": "答"}],
                            tmp_path, monkeypatch)
    assert len(client.requests) == 2, "/skill 通道必须照常跑轮次"
    assert "人调正文" in client.requests[0]["messages"][-2]["content"] \
        or any("人调正文" in (m.get("content") or "")
               for m in client.requests[0]["messages"])
    tool_names = {t["function"]["name"] for t in client.requests[1]["tools"]}
    assert "skill" not in tool_names
    assert "<available_skills>" not in client.requests[1]["messages"][0]["content"]


def test_repl_skill_can_invoke_disable_model_invocation(tmp_path, monkeypatch):
    """spec 验收 2 后半句（25 复核补的缺口）：disable-model-invocation 只限模型
    自动加载，/skill 用户通道照常可调——用户显式点名不该被自己的配置拦住。"""
    _write_skill(Path.home() / ".pai" / "skills", "manual-only", description="只许人调",
                 extra_front="disable-model-invocation: true\n", body="MANUAL-ONLY-TOKEN")
    client, printed = _repl(["/skill manual-only"], [{"content": "收到"}],
                            tmp_path, monkeypatch)
    assert len(client.requests) == 1, "用户显式 /skill 必须照常跑一轮"
    user_msgs = [m for m in client.requests[0]["messages"] if m["role"] == "user"]
    expanded = user_msgs[-1]["content"]
    assert '<skill name="manual-only">' in expanded
    assert "MANUAL-ONLY-TOKEN" in expanded
    # 对照：同一个 skill 在模型可见目录里必须不存在（它只对模型隐藏，不对人）
    assert "manual-only" not in client.requests[0]["messages"][0]["content"]


def test_repl_skill_command_records_into_tracker_for_reattach(tmp_path, monkeypatch):
    """/skill 通道加载的也要计入重挂——用户显式加载的正文没理由比模型加载的低一等。"""
    _write_skill(Path.home() / ".pai" / "skills", "alpha", description="甲技能",
                 body="TRACK-TOKEN")
    client, _ = _repl(["/skill alpha"], [{"content": "收到"}], tmp_path, monkeypatch)
    from pai.core.tools import skill as sk
    assert sk._TRACKER is not None and "alpha" in sk._TRACKER.names_recent_first()
