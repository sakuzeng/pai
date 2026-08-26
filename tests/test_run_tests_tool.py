"""`run_tests` 工具（feature 42 Task 2）。

为什么不是「给 bash 配条 allow 规则」：动工前核实的三条结构性事实，
配规则一条也解决不了——
① bash 默认超时 120s，本仓库全量跑 183s，放行了也会在第 120 秒被整组杀掉；
② bash 是头部截断，而 pytest 的判决在尾部，4000 字符正好把 `N passed` 扔掉；
③ bash 结构上不参与目录边界（D#52），配了白名单就等于把边界让出去（D#76）。
"""
import json
import os

import pytest

from pai.core import permissions
from pai.core.permissions import RuleSet
from pai.core.tools import EXEC, all_tools, get_tools


@pytest.fixture(autouse=True)
def _clean_config():
    """每条测试都从「没配置」开始——装配期注入的东西不许漏给下一条。"""
    from pai.core.tools import tests_tool

    tests_tool.set_command(None)
    tests_tool.set_timeout(None)
    yield
    tests_tool.set_command(None)
    tests_tool.set_timeout(None)


# ---- 跑什么：配置优先，其次探测 ----


def test_the_configured_command_wins(tmp_path, monkeypatch):
    from pai.core.tools import tests_tool

    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.sh").write_text("#!/bin/sh\necho 不该跑到我\n", encoding="utf-8")
    os.chmod(tmp_path / "test.sh", 0o755)
    tests_tool.set_command("echo 配置的命令")

    out = tests_tool.run_tests()
    assert "配置的命令" in out
    assert "不该跑到我" not in out


def test_autodetect_prefers_the_projects_own_test_script(tmp_path, monkeypatch):
    """有 `./test.sh` 就用它——项目自己的入口比我们猜的跑法更权威。"""
    from pai.core.tools.tests_tool import resolve_command

    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(tmp_path / "test.sh", 0o755)

    command, source = resolve_command(str(tmp_path))
    assert command == "./test.sh"
    assert "test.sh" in source


def test_autodetect_falls_back_to_pytest_for_a_python_project(tmp_path):
    from pai.core.tools.tests_tool import resolve_command

    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    command, _ = resolve_command(str(tmp_path))
    assert "pytest" in command


def test_autodetect_knows_a_few_other_ecosystems(tmp_path):
    """探测表不是只为 Python 写的——但也别假装它认全世界（见错误路径那条）。"""
    from pai.core.tools.tests_tool import resolve_command

    (tmp_path / "node").mkdir()
    (tmp_path / "node" / "package.json").write_text("{}", encoding="utf-8")
    assert "npm" in resolve_command(str(tmp_path / "node"))[0]

    (tmp_path / "rust").mkdir()
    (tmp_path / "rust" / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    assert "cargo" in resolve_command(str(tmp_path / "rust"))[0]


# ---- 怎么跑：过滤与路径 ----


def test_filter_and_path_are_passed_through(tmp_path, monkeypatch):
    """`filter` 按 pytest 的 `-k` 传、`path` 当位置参数——模型能决定的只有这两样。"""
    from pai.core.tools import tests_tool

    monkeypatch.chdir(tmp_path)
    (tmp_path / "some_test.py").write_text("", encoding="utf-8")
    tests_tool.set_command("echo 收到")

    out = tests_tool.run_tests(filter="loop and not slow", path="some_test.py")
    assert "-k" in out
    assert "loop and not slow" in out
    assert "some_test.py" in out


def test_the_running_command_is_reported(tmp_path, monkeypatch):
    """跑的是什么必须说出来。模型看到 `0 passed` 时，第一个该问的是「跑的是哪条命令」。"""
    from pai.core.tools import tests_tool

    monkeypatch.chdir(tmp_path)
    tests_tool.set_command("echo hi")
    out = tests_tool.run_tests()
    assert "echo hi" in out
    assert "tests.command" in out, "没说清这条命令是谁定的（决定了该改 settings 还是改测试）"

    tests_tool.set_command(None)
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert "自动探测" in tests_tool.run_tests()


def test_a_failing_run_reports_the_exit_code(tmp_path, monkeypatch):
    """测试没过与「工具没跑起来」必须分得开——只回输出的话两者一模一样。"""
    from pai.core.tools import tests_tool

    monkeypatch.chdir(tmp_path)
    tests_tool.set_command("echo 有失败; exit 1")
    out = tests_tool.run_tests()
    assert "有失败" in out
    assert "1" in out and "退出码" in out


# ---- 输出：判决在尾部 ----


def test_long_output_keeps_the_verdict_at_the_end(tmp_path, monkeypatch):
    """本轮最要紧的一条：pytest 的判决在最后一行，头部截断恰好把它扔掉。

    bash 现在就是头部截断（`output[:MAX_OUTPUT_CHARS]`），所以这不是假想的
    失效模式，是今天走 bash 跑测试就会撞上的那一个。
    """
    from pai.core.tools import tests_tool
    from pai.core.tools.output import MAX_OUTPUT_CHARS

    monkeypatch.chdir(tmp_path)
    tests_tool.set_command("seq 1 3000; echo '=== 1534 passed ==='")
    out = tests_tool.run_tests()

    assert "1534 passed" in out, "判决行被截掉了"
    assert "1\n2\n3\n" in out, "开头也该留着（要能看出跑的是什么）"
    assert "截掉" in out, "截断了必须说"
    assert len(out) < MAX_OUTPUT_CHARS * 2


# ---- 错误路径 ----


def test_an_undetectable_project_says_which_setting_to_configure(tmp_path, monkeypatch):
    """错误路径一：探测不到时要指路，不能只说「不知道怎么跑」。"""
    from pai.core.tools import tests_tool

    monkeypatch.chdir(tmp_path)
    out = tests_tool.run_tests()
    assert "错误" in out
    assert "tests.command" in out, "没告诉用户去配哪个键"


def test_a_missing_path_is_reported(tmp_path, monkeypatch):
    """错误路径二：path 指向不存在的地方。"""
    from pai.core.tools import tests_tool

    monkeypatch.chdir(tmp_path)
    tests_tool.set_command("echo hi")
    out = tests_tool.run_tests(path="不存在的目录/x.py")
    assert "错误" in out


def test_a_bogus_configured_timeout_falls_back_loudly(tmp_path, monkeypatch):
    """错误路径三：配置层给的超时非法时不许静默——与 bash.timeoutSeconds 同一条约定。"""
    from pai.core.settings import tests_timeout_seconds

    warned = []
    assert tests_timeout_seconds({"tests": {"timeoutSeconds": 0}}, warn=warned.append) is None
    assert warned, "非法值静默回默认了"


# ---- 接线 ----


def test_the_tool_is_registered_and_its_schema_is_generated():
    fn = get_tools()["run_tests"].schema()["function"]
    props = fn["parameters"]["properties"]
    assert set(props) == {"filter", "path"}
    assert fn["parameters"]["required"] == []
    assert all(props[k]["description"] for k in props)


def test_it_declares_exec_so_the_boundary_can_see_it():
    t = all_tools()["run_tests"]
    assert t.participates_in_boundary()
    assert t.access == EXEC, "写成 READ 就是撒谎：它跑任意项目代码"


def test_the_declared_path_resolves_the_default_root(tmp_path, monkeypatch):
    """不传 path 时回落到 cwd。回空串的话边界拿不到路径 → 兜底 ask，
    于是最常见的调用形态每次都弹窗，而没有任何别的测试会红。"""
    monkeypatch.chdir(tmp_path)
    t = all_tools()["run_tests"]
    assert os.path.abspath(t.get_path({})) == os.path.realpath(str(tmp_path))


def test_it_is_declared_not_concurrency_safe_on_purpose():
    """两个 pytest 同时跑会红得像回归（用户 2026-08-26 原话）——所以这是
    「想过了，结论是不行」，不是「忘了声明」。两者在行为上一样，意图不同，
    所以断言的是**声明存在**且取值为假，不只是取值为假。"""
    t = all_tools()["run_tests"]
    assert t.is_read_only is not None and t.is_concurrency_safe is not None, "根本没声明"
    assert t.read_only({}) is False
    assert t.concurrency_safe({}) is False


def test_two_test_runs_never_batch_in_parallel():
    from pai.core.scheduler import partition

    class _Fn:
        def __init__(self, name, args):
            self.name, self.arguments = name, json.dumps(args)

    class _TC:
        def __init__(self, name, args):
            self.function = _Fn(name, args)

    batches = partition([_TC("run_tests", {}), _TC("run_tests", {})], all_tools())
    assert len(batches) == 2 and not any(b.parallel for b in batches)


def test_running_tests_inside_the_working_dir_is_allowed_without_asking(tmp_path, monkeypatch):
    """本轮的核心验收之一。"""
    monkeypatch.chdir(tmp_path)
    d = permissions.decide("run_tests", {}, RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "allow", d.reason


def test_running_tests_outside_the_working_dir_still_asks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    d = permissions.decide("run_tests", {"path": str(outside)},
                           RuleSet.from_lists(), cwd=str(tmp_path))
    assert d.kind == "ask", d.reason


def test_a_deny_rule_can_target_the_test_root(tmp_path, monkeypatch):
    """挂了 matcher 才有这条。没挂的话吃 `default_matcher`——它比对第一个参数值，
    而这个工具的第一个参数是 filter，规则会拿过滤表达式去比对路径 pattern。"""
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    rules = RuleSet.from_lists(deny=["run_tests(//%s/**)" % str(sub).lstrip("/")])
    d = permissions.decide("run_tests", {"path": str(sub / "x")},
                           rules, cwd=str(tmp_path))
    assert d.kind == "deny", d.reason
