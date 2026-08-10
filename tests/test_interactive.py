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


def test_repl_assembles_layered_instructions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "PAI.md").write_text("这个项目用 pytest", encoding="utf-8")

    client, _ = _run(["问一句"], [{"content": "好"}])
    sent = client.requests[0]["messages"]
    assert any("这个项目用 pytest" in str(m["content"]) for m in sent)


def test_repl_shows_memory_writes(tmp_path, monkeypatch):
    """用户有权知道 agent 往自己硬盘上写了什么（问 4 选 A：自动写但要看得见）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    from pai.core.events import MemoryWritten, render_text

    script = [
        {"tool_calls": [("remember", json.dumps({"topic": "构建",
                                                 "fact": "测试用 ./test.sh"}))]},
        {"content": "好"},
    ]
    events: list = []
    client = FakeClient(script)
    run_interactive(client=client, model="fake", reader=_reader(["记一下"]),
                    out=lambda _: None, on_event=events.append, no_session=True)

    written = [e for e in events if isinstance(e, MemoryWritten)]
    assert [e.topic for e in written] == ["构建"]
    assert "已记住" in render_text(written[0])


# ---- feature 06 task 7：/memory ----


def test_slash_memory_lists_loaded_files(tmp_path, monkeypatch):
    """「指令没生效」的第一诊断步骤就是看文件到底加载没有——所以要列路径与行数。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "PAI.md").write_text("规矩一\n规矩二\n规矩三", encoding="utf-8")

    client, printed = _run(["/memory"], [])
    assert client.requests == []
    assert "PAI.md" in printed
    assert "3 行" in printed


def test_slash_memory_shows_memory_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _, printed = _run(["/memory"], [])
    assert "自动记忆" in printed and ".pai" in printed


def test_slash_memory_says_so_when_nothing_loaded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _, printed = _run(["/memory"], [])
    assert "没有加载任何指令文件" in printed        # 打印空白等于让人猜


def test_slash_memory_is_listed_in_help():
    _, printed = _run(["/help"], [])
    assert "/memory" in printed


def test_history_is_not_bound_to_readline_for_injected_readers(tmp_path, monkeypatch):
    """注入 reader 的测试路径绝不该碰进程级的 readline 状态——否则测试之间互相串。"""
    from pai.modes import interactive

    calls: list = []
    monkeypatch.setattr(interactive, "_read_history_into_readline", lambda p: calls.append(p))
    _run(["/exit"], [], history_path=tmp_path / "h")
    assert calls == []


def test_history_is_loaded_when_input_is_a_real_terminal(tmp_path, monkeypatch):
    """↑/↓ 与 Ctrl+R 靠 readline，而 readline 的历史要从我们自己写的文件里读回来。

    （05 交付时漏了这一半：历史文件一直在写，但从没读回去，↑ 是死的。
    测试只覆盖了「文件写对没有」，所以全绿也照不出来。）
    """
    from pai.modes import interactive

    history = tmp_path / "h"
    loaded: list = []
    monkeypatch.setattr(interactive, "_is_real_terminal_input", lambda _: True)
    monkeypatch.setattr(interactive, "_read_history_into_readline", lambda p: loaded.append(p))

    _run(["/exit"], [], history_path=history)
    assert loaded == [history]


def test_real_terminal_input_requires_both_real_input_and_tty(monkeypatch):
    from pai.modes import interactive

    monkeypatch.setattr(interactive.sys.stdin, "isatty", lambda: True, raising=False)
    assert interactive._is_real_terminal_input(input) is True
    assert interactive._is_real_terminal_input(lambda _: "x") is False

    monkeypatch.setattr(interactive.sys.stdin, "isatty", lambda: False, raising=False)
    assert interactive._is_real_terminal_input(input) is False


def test_read_history_into_readline_survives_a_missing_file(tmp_path):
    from pai.modes import interactive

    interactive._read_history_into_readline(tmp_path / "从来没有过的文件")   # 不抛


def test_ctrl_c_during_shell_mode_does_not_kill_the_repl(monkeypatch):
    """`!命令` 走的分支在 _run_turn 之外，没装 SIGINT 处理器——
    于是 Ctrl+C 打断 `!sleep 300` 会抛 KeyboardInterrupt 把整个 REPL 带栈掀掉。
    与 401 炸会话是同一类：REPL 这一层的全部价值就是「对话留着」。
    """
    from pai.modes import interactive

    def boom(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(interactive, "_run_shell", boom)
    client, printed = _run(["!sleep 300", "问一句"], [{"content": "好"}])

    assert "中断" in printed
    assert len(client.requests) == 1, "被中断之后还应该能继续正常对话"
    assert "再见" in printed


def test_shell_mode_runs_under_the_interrupt_flag(monkeypatch):
    """正确的中断姿势不是捕获异常，而是让 bash 看见标志、自己杀掉进程组再回填结果
    （D#41：中断是数据路径不是异常路径）。所以 `!` 分支必须也在标志作用域内跑。
    """
    import signal

    from pai.modes import interactive

    seen = {}

    def spy(command, **kwargs):
        seen["handler"] = signal.getsignal(signal.SIGINT)

    monkeypatch.setattr(interactive, "_run_shell", spy)
    _run(["!echo hi"], [])

    handler = seen.get("handler")
    assert callable(handler), "跑 `!命令` 期间必须装着自定义 SIGINT 处理器"
    assert handler is not signal.default_int_handler, \
        "还是默认处理器 = Ctrl+C 仍会抛 KeyboardInterrupt 掀掉 REPL"


def test_cli_reaps_background_process_groups_on_exit(monkeypatch):
    """收割必须挂在 cli 的出口上：REPL 与单次模式共用一个 finally，
    正常退出、Ctrl+D、甚至抛异常都会走到。`kill -9` 救不了——任何进程内方案都不行。
    """
    import sys

    from pai import cli

    calls: list = []
    monkeypatch.setattr(cli, "run_interactive", lambda **kw: None)
    monkeypatch.setattr(cli.shell, "reap_spawned", lambda: calls.append("reaped"))
    monkeypatch.setattr(sys, "argv", ["pai"])
    cli.main()
    assert calls == ["reaped"]

    monkeypatch.setattr(cli, "run_once", lambda task, **kw: (_ for _ in ()).throw(RuntimeError("炸")))
    monkeypatch.setattr(sys, "argv", ["pai", "任务"])
    try:
        cli.main()
    except RuntimeError:
        pass
    assert calls == ["reaped", "reaped"], "即使跑挂了也要收割"


def test_tests_can_never_touch_the_real_home(isolate_home):
    """防护本身要有测试，否则哪天 conftest 被改坏了没人知道。

    2026-08-10：测试把 `!sleep 300` 这类数据写进了用户真实的输入历史
    （~/.pai/history/<cwd 哈希>），是靠用户翻文件才发现的——这种污染不会让任何测试变红。
    """
    from pathlib import Path

    from pai.modes.interactive import HISTORY_BASE, history_path_for

    assert isolate_home in Path(HISTORY_BASE).parents, "历史根目录必须在临时 home 下"
    assert isolate_home in history_path_for().parents
    assert Path.home() == isolate_home


def test_slash_memory_shows_both_memory_and_session_dirs(tmp_path, monkeypatch):
    """这次问题的起点就是用户不知道那些文件是什么、在哪——所以两个目录都要列出来。"""
    monkeypatch.chdir(tmp_path)
    _, printed = _run(["/memory"], [])
    assert "自动记忆" in printed and "会话" in printed
    assert "projects" in printed


def test_slash_memory_shows_the_readable_slug(tmp_path, monkeypatch):
    """显示的必须是可读 slug 而不是 16 位哈希（feature 08 的诉求）。"""
    monkeypatch.chdir(tmp_path)
    _, printed = _run(["/memory"], [])
    assert str(tmp_path.absolute()).replace("/", "-") in printed
