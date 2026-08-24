"""装配收敛（feature 31）。

先钉验收 3：MCP 关闭从 atexit 改单出口 finally——REPL 无论正常退出（EOF）
还是异常上抛，`close_all_mcp` 都必须在 run_interactive 返回前确定性执行。
修前红：atexit 注册的关闭在函数返回时不触发，断言先于解释器退出跑到。

打桩走 `pai.core.mcp` 的模块属性（与 test_mcp.py 的 `mcp_mod.…` 用法同口径）：
装配方在调用点解析属性，测试才替换得掉。
"""
from pathlib import Path

import pytest
from fake_llm import FakeClient

from pai.core import mcp
from pai.core.permissions import RuleSet
from pai.modes.interactive import run_interactive

# 同 test_interactive：测的是接线不是权限，边界兜底别来捣乱
_OPEN = RuleSet.from_lists(default_decision="allow")


def _patch_mcp(monkeypatch, closed):
    marker = object()
    monkeypatch.setattr(mcp, "connect_configured_servers",
                        lambda **_kw: ([marker], [], []))
    monkeypatch.setattr(mcp, "close_all_mcp", closed.extend)
    return marker


def test_repl_closes_mcp_sessions_before_returning(monkeypatch):
    closed: list = []
    marker = _patch_mcp(monkeypatch, closed)

    def reader(prompt=""):
        raise EOFError

    run_interactive(client=FakeClient([]), model="fake", reader=reader,
                    out=lambda _s="": None, on_event=lambda _e: None,
                    no_session=True, rules=_OPEN)
    assert closed == [marker], "run_interactive 返回前必须已关闭 MCP sessions"


def test_repl_closes_mcp_sessions_when_loop_raises(monkeypatch):
    """finally 与 atexit 的另一半差别：异常路径也得关（try/finally 天然覆盖）。"""
    closed: list = []
    marker = _patch_mcp(monkeypatch, closed)

    class Boom(RuntimeError):
        pass

    def reader(prompt=""):
        raise Boom("reader 炸了")

    with pytest.raises(Boom):
        run_interactive(client=FakeClient([]), model="fake", reader=reader,
                        out=lambda _s="": None, on_event=lambda _e: None,
                        no_session=True, rules=_OPEN)
    assert closed == [marker]


def test_assemble_applies_bash_timeout_from_settings(monkeypatch, tmp_path):
    """settings 的 bash.timeoutSeconds 经装配层落到 shell 默认超时；
    没配置时显式清空（上一个装配的残留不许漂给下一个）。"""
    import json

    from pai.core import mcp as mcp_mod
    from pai.core.tools import get_tools, shell
    from pai.modes.assembly import assemble

    monkeypatch.setattr(mcp_mod, "connect_configured_servers",
                        lambda **_kw: ([], [], []))
    home = Path.home()                      # conftest 已隔离
    p = home / ".pai" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bash": {"timeoutSeconds": 240}}), encoding="utf-8")

    assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
             on_event=lambda _e: None, session=None, recall_model="fake",
             mode="dontAsk", rules=_OPEN)
    assert shell.default_timeout_seconds() == 240

    p.write_text("{}", encoding="utf-8")
    assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
             on_event=lambda _e: None, session=None, recall_model="fake",
             mode="dontAsk", rules=_OPEN)
    assert shell.default_timeout_seconds() == shell.TIMEOUT_SECONDS


def test_assemble_wires_additional_directories_into_boundary(monkeypatch, tmp_path):
    """feature 33（H9）：settings 的 permissions.additionalDirectories 落到
    WorkingDirs——此前只存在于文档里，配了静默不生效。"""
    import json

    from pai.core import mcp as mcp_mod
    from pai.core.tools import get_tools
    from pai.modes.assembly import assemble

    monkeypatch.setattr(mcp_mod, "connect_configured_servers",
                        lambda **_kw: ([], [], []))
    extra = tmp_path / "extra-root"
    extra.mkdir()
    p = Path.home() / ".pai" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"permissions": {"additionalDirectories": [str(extra)]}}),
        encoding="utf-8")

    asm = assemble(client=FakeClient([]), tools=get_tools(), warn=lambda _m: None,
                   on_event=lambda _e: None, session=None, recall_model="fake",
                   mode="dontAsk", rules=_OPEN)
    assert str(extra) in asm.working_dirs.additional
