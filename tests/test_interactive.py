"""REPL（feature 05 task 7）。

全套离线：client 用 FakeClient，输入源用注入的 reader（默认才是 input）——
「输入源可注入」是这一层能被测的唯一原因，也是 modes/ 层依赖注入约束的延续。
"""
import json

import pytest
from fake_llm import FakeClient

from pai.core.compaction import CompactionSettings
from pai.modes.interactive import run_interactive


def _reader(lines):
    """脚本化输入：元素是字符串就当用户输入，是异常类就抛（模拟 Ctrl+C / Ctrl+D）。"""
    queue = list(lines)

    def read(prompt=""):
        if not queue:
            raise EOFError
        item = queue.pop(0)
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item
        return item

    return read


def _run(lines, script, **kwargs):
    out: list = []
    client = FakeClient(script)
    run_interactive(client=client, model="fake", reader=_reader(lines),
                    out=out.append, on_event=lambda _: None, no_session=True, **kwargs)
    return client, "\n".join(out)


def test_slash_exit_ends_loop_without_calling_model():
    client, printed = _run(["/exit", "不该读到这一行"], [])
    assert client.requests == []
    assert "再见" in printed


def test_ctrl_d_ends_loop():
    client, printed = _run([], [])
    assert client.requests == []
    assert "再见" in printed


def test_conversation_persists_across_turns():
    client, _ = _run(["第一问", "第二问"], [{"content": "一"}, {"content": "二"}])
    second = client.requests[1]["messages"]
    assert [m["content"] for m in second][1:] == ["第一问", "一", "第二问"]


def test_slash_clear_keeps_system_and_drops_history():
    client, printed = _run(["第一问", "/clear", "第二问"],
                           [{"content": "一"}, {"content": "二"}])
    second = client.requests[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user"]
    assert second[1]["content"] == "第二问"
    assert "已清空" in printed


def test_slash_status_reports_context_and_breaker():
    _, printed = _run(["第一问", "/status"], [{"content": "一"}])
    assert "token" in printed and "锚点" in printed and "压缩" in printed


def test_slash_help_lists_commands():
    _, printed = _run(["/help"], [])
    for command in ("/exit", "/clear", "/compact", "/status"):
        assert command in printed


def test_unknown_slash_command_does_not_call_model():
    client, printed = _run(["/nope"], [])
    assert client.requests == []
    assert "未知命令" in printed


def test_bang_runs_shell_without_calling_model():
    client, printed = _run(["!echo 从 shell 来的", "问一句"], [{"content": "好"}])
    assert len(client.requests) == 1                     # `!` 那轮没打模型
    assert "从 shell 来的" in printed
    # 命令与输出都进了上下文（官方 shell 模式的语义），但不自动接话
    flat = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert "echo 从 shell 来的" in flat and "从 shell 来的" in flat


def test_backslash_continues_multiline_input():
    client, _ = _run(["第一行 \\", "第二行"], [{"content": "好"}])
    assert client.requests[0]["messages"][-1]["content"] == "第一行 \n第二行"


def test_first_ctrl_c_hints_second_exits():
    client, printed = _run([KeyboardInterrupt, KeyboardInterrupt], [])
    assert client.requests == []
    assert "再按一次" in printed


def test_input_between_two_ctrl_c_resets_the_counter():
    """两次 Ctrl+C 之间输过东西就不算「连按」——否则用户会莫名其妙被退出。"""
    client, printed = _run([KeyboardInterrupt, "问一句", KeyboardInterrupt],
                           [{"content": "好"}])
    assert len(client.requests) == 1
    assert printed.count("再按一次") == 2                 # 两次都只是提示，没退出


def test_slash_compact_compacts_and_resets_anchors():
    script = [
        {"content": "一", "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                                    "total_tokens": 110}},
        {"content": "二", "usage": {"prompt_tokens": 300, "completion_tokens": 10,
                                    "total_tokens": 310}},
        {"content": "这是摘要"},                          # ← /compact 触发的摘要请求
    ]
    client, printed = _run(["第一问", "第二问", "/compact"], script,
                           compaction=CompactionSettings(keep_recent_tokens=1))
    assert "tools" not in client.requests[2]              # 摘要请求不带 tools
    assert "已压缩" in printed


def test_slash_compact_without_anchors_explains_why():
    client, printed = _run(["/compact"], [])
    assert client.requests == []
    assert "锚点不足" in printed


def test_ask_user_question_is_wired_to_the_reader():
    """REPL 才有真人可问：工具要在工具集里，且答案来自 reader。"""
    script = [
        {"tool_calls": [("ask_user_question",
                         json.dumps({"question": "用哪个？",
                                     "options": '["方案A", "方案B"]'}))]},
        {"content": "好"},
    ]
    client, printed = _run(["帮我选", "2"], script)
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["content"] == "方案B"
    assert "用哪个？" in printed


def test_history_dedupes_consecutive_duplicates(tmp_path):
    history = tmp_path / "h"
    _run(["问一句", "问一句", "换一句"], [{"content": "1"}, {"content": "2"},
                                          {"content": "3"}], history_path=history)
    assert history.read_text(encoding="utf-8").splitlines() == ["问一句", "换一句"]


def test_history_path_is_per_working_directory(tmp_path, monkeypatch):
    from pai.modes.interactive import history_path_for

    monkeypatch.chdir(tmp_path)
    a = history_path_for(base=tmp_path / "hist")
    monkeypatch.chdir(tmp_path.parent)
    b = history_path_for(base=tmp_path / "hist")
    assert a != b, "历史按工作目录分文件（官方 interactive-mode 的语义）"


def test_slash_commands_do_not_enter_history(tmp_path):
    history = tmp_path / "h"
    _run(["/status", "问一句"], [{"content": "1"}], history_path=history)
    assert history.read_text(encoding="utf-8").splitlines() == ["问一句"]


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_input_is_ignored(blank):
    client, _ = _run([blank, "问一句"], [{"content": "好"}])
    assert len(client.requests) == 1


def test_cli_dispatches_to_repl_without_task_and_to_once_with_task(monkeypatch):
    """cli 只做分发：带 task 走 once，不带 task 进 REPL。"""
    import sys

    from pai import cli

    calls: list = []
    monkeypatch.setattr(cli, "run_interactive", lambda **kw: calls.append(("repl", kw)))
    monkeypatch.setattr(cli, "run_once", lambda task, **kw: calls.append(("once", task)) or "ok")

    monkeypatch.setattr(sys, "argv", ["pai"])
    cli.main()
    monkeypatch.setattr(sys, "argv", ["pai", "写个脚本"])
    cli.main()

    assert [kind for kind, _ in calls] == ["repl", "once"]
    assert calls[1][1] == "写个脚本"


def test_model_error_does_not_kill_the_repl():
    """冒烟实测撞出来的：一次 401 让整个 REPL 带栈退出。

    单次模式崩了无所谓（本来就跑完即退），REPL 崩了等于把整段对话连同上下文一起丢掉——
    而这一层的全部价值就是「对话留着」。
    """
    from types import SimpleNamespace

    def boom(**_):
        raise RuntimeError("401 Unauthorized")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    out: list = []
    run_interactive(client=client, model="fake", reader=_reader(["问一句", "再问一句"]),
                    out=out.append, on_event=lambda _: None, no_session=True)
    printed = "\n".join(out)
    assert printed.count("401 Unauthorized") == 2      # 两轮都报错，都没退出
    assert "再见" in printed                            # 最后是被 Ctrl+D（EOF）正常结束的
