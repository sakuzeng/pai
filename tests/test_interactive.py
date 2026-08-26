"""REPL（feature 05 task 7）。

全套离线：client 用 FakeClient，输入源用注入的 reader（默认才是 input）——
「输入源可注入」是这一层能被测的唯一原因，也是 modes/ 层依赖注入约束的延续。
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_llm import FakeClient

from pai.core.compaction import CompactionSettings
from pai.core.permissions import RuleSet
from pai.modes.interactive import run_interactive

# 同 test_modes：这些测的是 REPL 接线不是权限，feature 09 的边界兜底会拦住它们
_OPEN = RuleSet.from_lists(default_decision="allow")


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
    kwargs.setdefault("rules", _OPEN)
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


def test_conversation_persists_across_turns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)      # 别捡到仓库自己的 AGENTS.md（D#43 复议后它算指令文件）
    client, _ = _run(["第一问", "第二问"], [{"content": "一"}, {"content": "二"}])
    second = client.requests[1]["messages"]
    assert [m["content"] for m in second][1:] == ["第一问", "一", "第二问"]


def test_slash_clear_keeps_system_and_drops_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)      # 同上：仓库根的 AGENTS.md 会变成一条指令消息
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
        {"tool_calls": [("remember", json.dumps({"name": "构建", "description": "怎么跑测试",
                                                 "fact": "测试用 ./test.sh"}))]},
        {"content": "好"},
    ]
    events: list = []
    client = FakeClient(script)
    run_interactive(client=client, model="fake", rules=_OPEN, reader=_reader(["记一下"]),
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


# ---- asker 抢走 REPL 输入（2026-08-10 演示 08 时意外照出）----


def test_asker_offers_a_way_to_skip(tmp_path, monkeypatch):
    """模型提问时 asker 和 REPL 共用同一个 reader——用户被问住就出不来。
    空行必须是明确的逃生口，而不是被当成一个空答案交回去。"""
    monkeypatch.chdir(tmp_path)
    script = [
        {"tool_calls": [("ask_user_question",
                         json.dumps({"question": "用哪个？", "options": '["A", "B"]'}))]},
        {"content": "好"},
    ]
    client, printed = _run(["帮我选", ""], script)
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "跳过" in tool_msg["content"]
    assert "跳过" in printed or "回车" in printed          # 提示语要写出来，别让人猜


def test_asker_does_not_swallow_slash_commands(tmp_path, monkeypatch):
    """`/status` 这类命令在提问期间被静默当成答案交给模型，是最坏的一种吞。"""
    monkeypatch.chdir(tmp_path)
    script = [
        {"tool_calls": [("ask_user_question",
                         json.dumps({"question": "用哪个？", "options": '["A", "B"]'}))]},
        {"content": "好"},
    ]
    client, printed = _run(["帮我选", "/status", "2"], script)
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["content"] == "B", "命令不该被当成答案；应重新读一次"
    assert "不支持" in printed


def test_asker_lets_the_user_exit(tmp_path, monkeypatch):
    """被提问时用户必须能退出——否则 /exit 变成答案，人被困在问题里。"""
    monkeypatch.chdir(tmp_path)
    script = [
        {"tool_calls": [("ask_user_question",
                         json.dumps({"question": "用哪个？", "options": '["A", "B"]'}))]},
        {"content": "好"},
    ]
    client, printed = _run(["帮我选", "/exit", "不该读到这一行"], script)
    assert "再见" in printed


# ---- feature 07 Task 7：/permissions ----


def test_slash_permissions_lists_rules_with_source(tmp_path, monkeypatch):
    """拒绝要说得出「哪条规则、从哪来」，否则用户无从修。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pai").mkdir()
    (tmp_path / ".pai" / "settings.json").write_text(
        json.dumps({"permissions": {"deny": ["Bash(rm *)"], "allow": ["Bash(ls *)"]}}),
        encoding="utf-8")

    _, printed = _run(["/permissions"], [], rules=None)   # 本条要的就是从磁盘读

    assert "bash(rm *)" in printed
    assert "bash(ls *)" in printed
    assert "project" in printed


def test_slash_permissions_says_so_when_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, printed = _run(["/permissions"], [], rules=None)
    assert "没有" in printed or "默认" in printed


def test_repl_holds_recall_state_across_turns(tmp_path, monkeypatch):
    """RecallState 跨轮持有：第一轮注入过的记忆，第二轮不再重复选，
    于是第二轮**连侧查询都不发**（状态每轮清零的话，脚本会被多消耗一条而报错）。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.memory import memory_dir

    from tests.test_memory_scan import write_memory
    from tests.test_recall import reply

    write_memory(memory_dir(), "甲", description="怎么跑测试", body="记忆正文")
    client = FakeClient([reply(["甲.md"]), {"content": "第一轮"}, {"content": "第二轮"}])

    run_interactive(client=client, model="fake", rules=_OPEN,
                    reader=_reader(["问题一", "问题二"]), out=lambda _: None,
                    on_event=lambda _: None, no_session=True)

    assert len(client.requests) == 3          # 召回 1 次 + 两轮各 1 次


# ---- R4#11：/compact 是唯一碰网络的命令路径，不许掀掉会话（2026-08-19 评审）----


def test_manual_compact_survives_a_network_error():
    """`/compact` 撞上一次网络抖动不该掀掉整个会话。

    已登记的「两条主循环都兜了」只包住 `_run_turn`；`_handle_command`
    是一路裸抛的——REPL 下整个 while 循环带栈掀掉、TUI 下大 try 只有 finally
    （终端复原了但对话没了）。而这恰恰是最不该丢上下文的时刻：
    用户按 `/compact` 正是因为上下文已经攒得很长了。
    """
    from pai.core.compaction import AnchorBook, CompactionSettings, CompactionState
    from pai.modes.interactive import _manual_compact

    class Exploding:
        def __init__(self):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._boom))

        def _boom(self, **kwargs):
            raise RuntimeError("429 Too Many Requests")

    messages = [{"role": "system", "content": "s"}]
    messages += [{"role": "user", "content": f"第 {i} 句"} for i in range(6)]
    before = list(messages)

    anchors = AnchorBook()
    anchors.record(2, 100)
    anchors.record(4, 900)

    said: list = []
    _manual_compact(messages=messages, anchors=anchors, state=CompactionState(),
                    client=Exploding(), model="fake",
                    compaction=CompactionSettings(keep_recent_tokens=1),
                    out=said.append)

    assert messages == before, "失败了就不该动历史"
    assert any("压缩失败" in line for line in said), f"要告诉用户为什么，实际：{said}"


def test_slash_permissions_tells_the_whole_truth():
    """feature 33（09 遗留 1 提示半边 + 遗留 3）：/permissions 必须说出
    两件此前不可见的事——bash 不参与目录边界（配 allow 白名单即可越界，
    本功能的主要失效模式 D#52）、危险写清单（硬编码不可配，用户此前撞上才知道）。"""
    _, printed = _run(["/permissions"], [])
    assert "bash" in printed and "边界" in printed
    assert ".git/hooks" in printed
    assert ".ssh" in printed
    assert "settings.json" in printed


def test_repl_wires_keep_recent_tokens_from_the_env(monkeypatch):
    """REPL 侧同款接线（once 那条在 test_modes）。两处都要：装配序列虽已收敛进
    assembly，`CompactionSettings` 仍是各自构造的。"""
    captured: dict = {}

    def fake_run_agent(*args, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("pai.modes.interactive.run_agent", fake_run_agent)
    monkeypatch.setenv("PAI_KEEP_RECENT_TOKENS", "888")
    _run(["问一句"], [{"content": "ok"}])
    assert captured["compaction"].keep_recent_tokens == 888


# ---- /compact 的「无可压」要可操作（TODO「压缩链路的可验证性」第二条）----


def test_manual_compact_says_how_far_short_the_history_is():
    """「无可压」三个字分不清「坏了」与「还没到量」。用户按 `/compact` 时
    唯一想知道的是「那我还要聊多久」——差额是算得出来的，就该说出来。"""
    from pai.core.compaction import AnchorBook, CompactionState
    from pai.modes.interactive import _manual_compact

    anchors = AnchorBook()
    anchors.record(2, 1000)
    anchors.record(4, 1800)          # 可用差值只有 800，门槛 20000

    said: list = []
    _manual_compact(messages=[{"role": "system", "content": "s"}],
                    anchors=anchors, state=CompactionState(),
                    client=None, model="fake",
                    compaction=CompactionSettings(keep_recent_tokens=20000),
                    out=said.append)
    text = "\n".join(said)
    assert "19200" in text, f"要说清还差多少 token，实际：{said}"
    assert "PAI_KEEP_RECENT_TOKENS" in text, "还要给出第二条出路：把门槛调小"


def test_manual_compact_without_anchors_does_not_pretend_to_know_the_gap():
    """锚不足两个时一个差值都算不出来，不许拿门槛冒充「还差这么多」。"""
    from pai.core.compaction import AnchorBook, CompactionState
    from pai.modes.interactive import _manual_compact

    said: list = []
    _manual_compact(messages=[{"role": "system", "content": "s"}],
                    anchors=AnchorBook(), state=CompactionState(),
                    client=None, model="fake",
                    compaction=CompactionSettings(keep_recent_tokens=20000),
                    out=said.append)
    text = "\n".join(said)
    assert "锚点不足" in text
    assert "还差" not in text, f"算不出来就别说，实际：{said}"


# ---- /clear 与 /compact 同样改写上下文（10 遗留 6 的第二半边 / feature 37）----


def _rewriting(events):
    from pai.core.events import CONTEXT_REWRITING

    return [type(e) for e in events if isinstance(e, CONTEXT_REWRITING)]


def _command_kwargs(**overrides):
    from pai.core.compaction import AnchorBook, CompactionState

    kwargs = dict(out=lambda _s="": None,
                  messages=[{"role": "system", "content": "s"},
                            {"role": "user", "content": "一"}],
                  anchors=AnchorBook(), state=CompactionState(), tools={},
                  client=None, model="fake", compaction=CompactionSettings(),
                  context_window=1000)
    kwargs.update(overrides)
    return kwargs


def test_clear_emits_a_context_rewriting_event():
    """`/clear` 把整段对话删了——比压缩更彻底。召回去重表与规则注入表若不跟着清，
    那几篇记忆此后再也不会被选中，而且完全静默。

    feature 37 起这件事是 `ConversationCleared` 事件的性质
    （`events.CONTEXT_REWRITING`），不再是一个单独穿下来的回调。"""
    from pai.core.events import ConversationCleared
    from pai.modes.interactive import _handle_command

    seen: list = []
    _handle_command("/clear", **_command_kwargs(on_event=seen.append))
    assert _rewriting(seen) == [ConversationCleared]


def test_other_commands_rewrite_nothing():
    """反向守卫：`/status` 不动上下文，不许顺手发一条改写事件。"""
    from pai.modes.interactive import _handle_command

    seen: list = []
    _handle_command("/status", **_command_kwargs(on_event=seen.append))
    assert _rewriting(seen) == []


def test_manual_compact_emits_a_context_rewriting_event():
    from pai.core.compaction import AnchorBook, CompactionState
    from pai.core.events import Compacted
    from pai.modes.interactive import _manual_compact

    anchors = AnchorBook()
    anchors.record(2, 100)
    anchors.record(4, 900)
    seen: list = []
    messages = [{"role": "system", "content": "s"}]
    messages += [{"role": "user", "content": f"第 {i} 句"} for i in range(6)]
    _manual_compact(messages=messages, anchors=anchors, state=CompactionState(),
                    client=FakeClient([{"content": "摘要"}]), model="fake",
                    compaction=CompactionSettings(keep_recent_tokens=1),
                    out=lambda _s="": None, on_event=seen.append)
    assert _rewriting(seen) == [Compacted]


def test_a_failed_manual_compact_rewrites_nothing():
    """失败的压缩没有改写任何东西（历史原样留着），不该发改写事件。"""
    from pai.core.compaction import AnchorBook, CompactionState
    from pai.modes.interactive import _manual_compact

    class Exploding:
        def __init__(self):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._boom))

        def _boom(self, **kwargs):
            raise RuntimeError("429 Too Many Requests")

    anchors = AnchorBook()
    anchors.record(2, 100)
    anchors.record(4, 900)
    seen: list = []
    messages = [{"role": "system", "content": "s"}]
    messages += [{"role": "user", "content": f"第 {i} 句"} for i in range(6)]
    _manual_compact(messages=messages, anchors=anchors, state=CompactionState(),
                    client=Exploding(), model="fake",
                    compaction=CompactionSettings(keep_recent_tokens=1),
                    out=lambda _s="": None, on_event=seen.append)
    assert _rewriting(seen) == []


# ---- /memory reload：REPL 中途改 PAI.md 要能生效（06 task 4）----


def test_memory_reload_makes_a_changed_instruction_file_take_effect(tmp_path, monkeypatch):
    """症状（06 task 4 登记）：`_inject_instructions` 认出已有指令消息就直接返回，
    连 loader 都不调——于是多轮 REPL 只在第一轮读盘，改了 PAI.md 得等一次压缩或重启。
    这条测试跑的是真实症状：第一轮之后改文件，`/memory reload`，第三轮该看见新内容。
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "PAI.md").write_text("旧指令甲", encoding="utf-8")

    lines = ["一", "/memory reload", "二"]

    def reader(prompt=""):
        if not lines:
            raise EOFError
        line = lines.pop(0)
        if line == "/memory reload":         # 第一轮已经跑完了，此刻才改盘上的文件
            (tmp_path / "PAI.md").write_text("新指令乙", encoding="utf-8")
        return line

    client = FakeClient([{"content": "答一"}, {"content": "答二"}])
    printed: list = []
    run_interactive(client=client, model="fake", reader=reader, rules=_OPEN,
                    out=printed.append, on_event=lambda _: None, no_session=True)

    first = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    second = json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert "旧指令甲" in first
    assert "新指令乙" in second, "reload 之后必须重新读盘"
    assert "旧指令甲" not in second, "旧的那条要被丢掉，不能两份并存"


def test_memory_reload_says_what_it_did():
    from pai.core.loop import INSTRUCTION_HEADER
    from pai.modes.interactive import _handle_command

    messages = [{"role": "system", "content": "s"},
                {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n旧"}]
    said: list = []
    _handle_command("/memory reload", **_command_kwargs(
        out=said.append, messages=messages, ledger=[None, None]))
    assert len(messages) == 1, "指令消息要被丢掉"
    assert any("下一轮" in line for line in said), f"要说清什么时候生效，实际：{said}"


def test_plain_memory_still_lists_files():
    """反向守卫：不带 reload 的 `/memory` 一个字都不该动上下文。"""
    from pai.core.loop import INSTRUCTION_HEADER
    from pai.modes.interactive import _handle_command

    messages = [{"role": "system", "content": "s"},
                {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n旧"}]
    said: list = []
    _handle_command("/memory", **_command_kwargs(out=said.append, messages=messages,
                                                 ledger=[None, None]))
    assert len(messages) == 2
    assert any("记忆目录" in line for line in said)


# ---- resume 只恢复对话不恢复设置，得说出来（24 遗留）----


def _write_session(tmp_path, cwd="/somewhere/else"):
    import json as _json
    from pai.core.session import SessionLog

    directory = tmp_path / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "20260826-120000-abcdef12.jsonl"
    lines = [
        {"type": "session", "version": 1, "id": "abcdef1234", "timestamp": "t",
         "cwd": cwd},
        {"type": "message", "id": "u", "parentId": None, "ts": 1.0,
         "message": {"role": "user", "content": "上次的问题"}},
        {"type": "message", "id": "a", "parentId": "u", "ts": 2.0,
         "message": {"role": "assistant", "content": "上次的回答"}},
    ]
    path.write_text("\n".join(_json.dumps(l, ensure_ascii=False) for l in lines) + "\n",
                    encoding="utf-8")
    assert SessionLog                                  # 只为说明格式出处
    return path


def test_resume_says_that_settings_are_not_restored(tmp_path, monkeypatch):
    """dsh 明确警告「恢复到不同构图的组合是错误」，pai 连警告都没有（24 遗留）。
    权限模式 / 模型 / system prompt 全取当前环境，而对话是旧的——
    最容易咬人的是权限模式（上次在 bypass 里跑的活，这次未必）。"""
    monkeypatch.chdir(tmp_path)
    path = _write_session(tmp_path)

    printed: list = []
    run_interactive(client=FakeClient([]), model="fake",
                    reader=_reader([EOFError]), rules=_OPEN,
                    out=printed.append, on_event=lambda _: None,
                    no_session=True, resume=str(path))
    text = "\n".join(printed)
    assert "已恢复会话" in text
    assert "设置" in text and "权限模式" in text, f"要说清恢复的只是对话，实际：{printed}"


def test_resume_points_out_a_different_working_directory(tmp_path, monkeypatch):
    """header 里存着录制时的 cwd（feature 24 的格式给了这个事实）。
    换了目录才是真正会咬人的那一档：工作目录边界与项目指令都跟着 cwd 走。"""
    monkeypatch.chdir(tmp_path)
    path = _write_session(tmp_path, cwd="/一个/别的/目录")

    printed: list = []
    run_interactive(client=FakeClient([]), model="fake",
                    reader=_reader([EOFError]), rules=_OPEN,
                    out=printed.append, on_event=lambda _: None,
                    no_session=True, resume=str(path))
    assert any("/一个/别的/目录" in line for line in printed), printed


def test_resume_in_the_same_directory_says_nothing_about_cwd(tmp_path, monkeypatch):
    """反向守卫：目录没变就别提——每次都喊等于没喊。"""
    monkeypatch.chdir(tmp_path)
    path = _write_session(tmp_path, cwd=str(Path(tmp_path).absolute()))

    printed: list = []
    run_interactive(client=FakeClient([]), model="fake",
                    reader=_reader([EOFError]), rules=_OPEN,
                    out=printed.append, on_event=lambda _: None,
                    no_session=True, resume=str(path))
    assert not any("录制于" in line for line in printed), printed


# ---- /memory 要看得见规则（feature 36 Task 6）----


def test_memory_lists_path_scoped_rules(tmp_path, monkeypatch):
    """这层机制的失效方式天然是沉默的：规则没进上下文，模型照样给一个像样的回答。
    所以规则文件必须能在 `/memory` 里被看见——它首先是个调试工具。"""
    from pai.modes.interactive import _handle_command

    monkeypatch.chdir(tmp_path)
    directory = tmp_path / ".pai" / "rules"
    directory.mkdir(parents=True)
    (directory / "前端.md").write_text("---\npaths: web/**\n---\n\n正文",
                                       encoding="utf-8")

    said: list = []
    _handle_command("/memory", **_command_kwargs(out=said.append))
    text = "\n".join(said)
    assert "前端" in text and "web/**" in text


def test_memory_marks_which_rules_are_already_injected(tmp_path, monkeypatch):
    from pai.core.rules import RuleState, scan_rules, select_and_render
    from pai.modes.interactive import _handle_command

    monkeypatch.chdir(tmp_path)
    directory = tmp_path / ".pai" / "rules"
    directory.mkdir(parents=True)
    (directory / "前端.md").write_text("---\npaths: web/**\n---\n\n正文",
                                       encoding="utf-8")
    state = RuleState()
    select_and_render(["web/a.css"], scan_rules(warn=lambda _s: None), state,
                      root=tmp_path)

    said: list = []
    _handle_command("/memory", **_command_kwargs(out=said.append, rule_state=state))
    assert any("已注入" in line for line in said), said


def test_memory_without_rules_says_nothing_about_them(tmp_path, monkeypatch):
    """反向守卫：没有规则目录时不许多打一节（`/memory` 已经够长了）。"""
    from pai.modes.interactive import _handle_command

    monkeypatch.chdir(tmp_path)
    said: list = []
    _handle_command("/memory", **_command_kwargs(out=said.append))
    assert not any("规则" in line for line in said), said
