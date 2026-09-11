"""feature 49：resume 追加同一文件 + 会话内 `/resume`，照 CC 2.1.88。

CC：`switchSession(sid)` 沿用被恢复会话的 id、落盘指针指回原转录，`useLogMessages(messages,
ignore = 恢复后一条新消息都没有)` 什么都不写；只有 `--fork-session` 才造新 id 走新文件。
`/resume` 命令无参弹 `LogSelector`、带参先当 id 匹配；选中后在进程内换 messages 状态并切 session。
pai 对应：`SessionLog.open_existing` / `switch_to`、`EventTrace` 跟着 session 的路径走、
`modes/resume.py::switch_conversation`（发 `ConversationResumed`，进 `CONTEXT_REWRITING`）、
`--fork-session` 保留 24 的新文件路径。
"""

import json
import sys

import pytest

from fake_llm import FakeClient
from helpers import OPEN_RULES, scripted_reader

from pai.core.events import CONTEXT_REWRITING, AgentStart, ConversationResumed
from pai.core.loop import INSTRUCTION_HEADER
from pai.core.paths import sessions_dir
from pai.core.session import SessionFormatError, SessionLog, load_session
from pai.core.trace import EventTrace
from pai.modes.interactive import run_interactive


def _record(*msgs):
    """用真 SessionLog 在本项目的 sessions 目录里写一份会话，返回路径。"""
    log = SessionLog(sessions_dir())
    for m in msgs:
        log.append(m)
    return log.path


def _session_files():
    return sorted(p for p in sessions_dir().glob("*.jsonl")
                  if not p.name.endswith(".events.jsonl"))


def _messages(path):
    _, entries = load_session(path)
    return [e["message"] for e in entries if e["type"] == "message"]


def _run(lines, script, out=None, on_event=None, **kw):
    client = FakeClient(script)
    run_interactive(client=client, model="fake", reader=scripted_reader(lines), rules=OPEN_RULES,
                    out=out or (lambda _s: None), on_event=on_event or (lambda _e: None), **kw)
    return client


SMALL = ({"role": "system", "content": "s"},
         {"role": "user", "content": "记住我叫小明"},
         {"role": "assistant", "content": "好的小明"})


# ---- SessionLog 接管既有文件 ---------------------------------------------------

def test_open_existing_adopts_the_id_and_continues_the_physical_tail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _record(*SMALL)
    header, entries = load_session(path)

    log = SessionLog.open_existing(path)
    assert log.path == path and log.session_id == header["id"]
    log.append({"role": "user", "content": "再问"})

    header2, entries2 = load_session(path)
    assert header2 == header, "接管不重写 header"
    assert [e["id"] for e in entries2[:-1]] == [e["id"] for e in entries], "原条目一条不动"
    assert entries2[-1]["parentId"] == entries[-1]["id"], "parentId 接在物理尾部上（dsh 形）"
    assert path.read_text(encoding="utf-8").count('"type": "session"') == 1


def test_open_existing_rejects_a_v0_file(tmp_path):
    p = tmp_path / "old.jsonl"
    p.write_text('{"role": "user", "content": "x"}\n', encoding="utf-8")
    with pytest.raises(SessionFormatError):
        SessionLog.open_existing(p)


def test_event_trace_follows_the_session_when_it_switches(tmp_path, monkeypatch):
    """观测流按会话同名配对（viz 靠它）。session 切了文件，trace 不能还写旧的那份。"""
    monkeypatch.chdir(tmp_path)
    a = _record({"role": "user", "content": "a"})
    b = _record({"role": "user", "content": "b"})
    log = SessionLog.open_existing(a)
    trace = EventTrace(log)
    trace(AgentStart(task="第一段"))
    log.switch_to(b)
    trace(AgentStart(task="第二段"))
    assert "第一段" in a.with_suffix(".events.jsonl").read_text(encoding="utf-8")
    assert "第二段" in b.with_suffix(".events.jsonl").read_text(encoding="utf-8")
    assert "第二段" not in a.with_suffix(".events.jsonl").read_text(encoding="utf-8")


# ---- --resume 追加同一文件 -----------------------------------------------------

def test_cli_resume_appends_to_the_same_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _record(*SMALL)
    header, before = load_session(path)

    client = _run(["我叫什么", "/exit"], [{"content": "小明"}], resume="", history_path=tmp_path / "h")

    assert "记住我叫小明" in json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert _session_files() == [path], "照 CC：沿用原会话，不新建文件"
    header2, after = load_session(path)
    assert header2["id"] == header["id"] and "parentSession" not in header2
    assert [e["id"] for e in after[:len(before)]] == [e["id"] for e in before], "原条目原样、不重录"
    new_msgs = [e["message"]["content"] for e in after[len(before):] if e["type"] == "message"]
    assert new_msgs == ["我叫什么", "小明"], new_msgs


def test_resume_without_typing_leaves_the_file_byte_for_byte(tmp_path, monkeypatch):
    """CC `useLogMessages` 的 ignore：恢复后一条新消息都没有就什么都不写。
    也是用户 2026-09-10 13:39 那次的真实场景（恢复、看一眼、退出）。"""
    monkeypatch.chdir(tmp_path)
    path = _record(*SMALL)
    raw = path.read_bytes()
    _run([EOFError], [], resume="", history_path=tmp_path / "h")
    assert path.read_bytes() == raw and _session_files() == [path]


def test_refreshed_system_stays_in_memory_and_unchanged_instructions_are_not_rerecorded(
        tmp_path, monkeypatch):
    """CC 的转录里不存 system prompt——pai 重装配出的 system 只在内存；
    指令消息与磁盘现有的那条内容一样就沿用原条目，不再追加一份。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "PAI.md").write_text("规矩 SAME\n", encoding="utf-8")
    from pai.core.loop import _instruction_message
    from pai.core.memory import build_context
    same = _instruction_message(build_context())
    path = _record({"role": "system", "content": "旧 system STALE"}, same,
                   {"role": "user", "content": "问"}, {"role": "assistant", "content": "答"})
    _, before = load_session(path)

    client = _run(["再问", "/exit"], [{"content": "好"}], resume="", history_path=tmp_path / "h")

    sent = client.requests[0]["messages"]
    assert sent[0]["role"] == "system" and "STALE" not in sent[0]["content"]
    after_msgs = _messages(path)
    assert [m["role"] for m in after_msgs].count("system") == 1, "重装配的 system 不落盘"
    _, after = load_session(path)
    instrs = [e for e in after if e["type"] == "message"
              and str(e["message"].get("content", "")).startswith(INSTRUCTION_HEADER)]
    assert len(instrs) == 1 and instrs[0]["id"] == before[1]["id"], "指令没变就不重录"


def test_changed_instructions_are_rerecorded_after_resume(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "PAI.md").write_text("规矩 OLD\n", encoding="utf-8")
    from pai.core.loop import _instruction_message
    from pai.core.memory import build_context
    old = _instruction_message(build_context())
    path = _record({"role": "system", "content": "s"}, old,
                   {"role": "user", "content": "问"}, {"role": "assistant", "content": "答"})
    (tmp_path / "PAI.md").write_text("规矩 NEW\n", encoding="utf-8")

    client = _run(["再问", "/exit"], [{"content": "好"}], resume="", history_path=tmp_path / "h")

    sent_instr = [m for m in client.requests[0]["messages"]
                  if str(m.get("content", "")).startswith(INSTRUCTION_HEADER)]
    assert len(sent_instr) == 1 and "NEW" in sent_instr[0]["content"] \
        and "OLD" not in sent_instr[0]["content"]
    on_disk = [m for m in _messages(path) if str(m.get("content", "")).startswith(INSTRUCTION_HEADER)]
    assert len(on_disk) == 2 and "NEW" in on_disk[-1]["content"], "变了才追加一条，旧的留在盘上"


def test_fork_session_writes_a_new_file_with_parent_session(tmp_path, monkeypatch):
    """`--fork-session`（CC 同名 flag）：24 的现行为——新文件、header 的 parentSession 指旧会话、
    对话消息按原 id 重录；原文件一个字节不动。"""
    monkeypatch.chdir(tmp_path)
    path = _record(*SMALL)
    raw = path.read_bytes()
    h1, e1 = load_session(path)

    _run(["再问", "/exit"], [{"content": "好"}], resume="", fork_session=True,
         history_path=tmp_path / "h")

    files = _session_files()
    assert len(files) == 2 and path.read_bytes() == raw
    other = [f for f in files if f != path][0]
    h2, e2 = load_session(other)
    assert h2["parentSession"] == h1["id"] and h2["id"] != h1["id"]
    conv1 = {e["id"] for e in e1 if e["type"] == "message" and e["message"]["role"] != "system"}
    conv2 = {e["id"] for e in e2 if e["type"] == "message"}
    assert conv1 <= conv2, "fork 时对话消息按原 id 重录"


def test_cli_fork_session_flag_requires_resume(monkeypatch):
    import pai.cli as cli

    seen = {}
    monkeypatch.setattr(cli, "run_interactive", lambda **kw: seen.update(kw))
    monkeypatch.setattr(sys, "argv", ["pai", "--resume", "--fork-session"])
    cli.main()
    assert seen["fork_session"] is True and seen["resume"] == ""
    monkeypatch.setattr(sys, "argv", ["pai", "--fork-session"])
    with pytest.raises(SystemExit):
        cli.main()


# ---- 会话内 /resume ------------------------------------------------------------

def test_slash_resume_switches_to_the_target_conversation(tmp_path, monkeypatch):
    """CC 的 `/resume <id>`：换 messages、切 session、发上下文改写事件。
    切换前的对话留在它自己的文件里，切换后的消息追加进目标文件。"""
    monkeypatch.chdir(tmp_path)
    path = _record(*SMALL)
    header, _ = load_session(path)
    events = []

    client = _run(["你好", f"/resume {header['id'][:8]}", "我叫什么", "/exit"],
                  [{"content": "你好呀"}, {"content": "小明"}],
                  on_event=events.append, history_path=tmp_path / "h")

    texts = [str(m.get("content")) for m in client.requests[1]["messages"]]
    assert any("记住我叫小明" in t for t in texts), "切换后的请求带目标会话的历史"
    assert not any("你好呀" in t for t in texts), "切换前的对话不带过去"
    assert any(isinstance(e, ConversationResumed) for e in events)
    assert ConversationResumed in CONTEXT_REWRITING, "resume 重建是第三种上下文改写（events.py 那条注释）"
    files = _session_files()
    assert len(files) == 2, "自己的那段在自己的文件里，目标文件被接管"
    assert [m["content"] for m in _messages(path)][-2:] == ["我叫什么", "小明"]


def test_slash_resume_lets_recall_come_back(tmp_path, monkeypatch):
    """纵切（同 feature 37 的 /clear 那条）：切换前召回过的记忆，切换后必须能再次被选中——
    走完整事件链：`switch_conversation` 发 `ConversationResumed` → 装配层监听器 → `surfaced` 清空。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.memory import memory_dir
    from helpers import recall_reply as reply, write_memory

    write_memory(memory_dir(), "甲", description="怎么跑测试", body="记忆正文在此")
    path = _record(*SMALL)
    header, _ = load_session(path)
    client = FakeClient([reply(["甲.md"]), {"content": "一"},
                         reply(["甲.md"]), {"content": "二"}])
    run_interactive(client=client, model="fake", rules=OPEN_RULES,
                    reader=scripted_reader(["第一问", f"/resume {header['id'][:8]}", "第二问"]),
                    out=lambda _s="": None, on_event=lambda _e: None, no_session=True)
    turns = [r for r in client.requests if "tools" in r]
    assert len(turns) == 2
    assert "记忆正文在此" in json.dumps(turns[1]["messages"], ensure_ascii=False)


def test_slash_resume_without_argument_offers_recent_sessions(tmp_path, monkeypatch):
    """CC 无参 `/resume` 弹选择器：最近的排第一，每行带首句；选中即切换。"""
    monkeypatch.chdir(tmp_path)
    _record({"role": "system", "content": "s"}, {"role": "user", "content": "甲会话的第一句"},
            {"role": "assistant", "content": "答甲"})
    _record({"role": "system", "content": "s"}, {"role": "user", "content": "乙会话的第一句"},
            {"role": "assistant", "content": "答乙"})
    printed = []
    client = _run(["/resume", "1", "接着", "/exit"], [{"content": "好"}],
                  out=printed.append, history_path=tmp_path / "h")
    text = "\n".join(printed)
    assert "甲会话的第一句" in text and "乙会话的第一句" in text, text
    sent = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert "乙会话的第一句" in sent and "甲会话的第一句" not in sent, "1 = 最近的那个（乙）"


def test_cancelling_the_picker_keeps_the_current_conversation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _record(*SMALL)
    events = []
    client = _run(["你好", "/resume", "", "再说", "/exit"],
                  [{"content": "你好呀"}, {"content": "好"}],
                  on_event=events.append, history_path=tmp_path / "h")
    texts = [str(m.get("content")) for m in client.requests[1]["messages"]]
    assert any("你好呀" in t for t in texts), "取消后仍是原来的对话"
    assert not any(isinstance(e, ConversationResumed) for e in events)


def test_slash_resume_with_an_unknown_id_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _record(*SMALL)
    printed = []
    _run(["/resume zzzzzzzz", "/exit"], [], out=printed.append, history_path=tmp_path / "h")
    assert any("zzzzzzzz" in line and "没有" in line for line in printed), printed


def test_slash_resume_with_nothing_to_resume_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    printed = []
    _run(["/resume", "/exit"], [], out=printed.append, history_path=tmp_path / "h")
    assert any("没有" in line for line in printed), printed


# ---- 只认当前目录录制的会话（用户 2026-09-11 截图：pai_playground 子目录的会话被列进来了）----
# CC：项目目录按启动 cwd 归档，/resume 选择框与 --continue 只看当前目录；跨目录只能给明确的 id。

def _record_elsewhere(directory, other_cwd, *msgs):
    """在 `directory` 里录一份 header.cwd = other_cwd 的会话——像是在别的目录启动过 pai。
    同一个 git 仓库的子目录正是这种情况：slug 按 git 根算，文件落在同一个 sessions 目录。"""
    import os
    other_cwd.mkdir(parents=True, exist_ok=True)
    before = os.getcwd()
    os.chdir(other_cwd)
    try:
        log = SessionLog(directory)
        for m in msgs:
            log.append(m)
    finally:
        os.chdir(before)
    return log.path


def _two_places(tmp_path):
    here = _record({"role": "system", "content": "s"}, {"role": "user", "content": "这里的会话"},
                   {"role": "assistant", "content": "答"})
    elsewhere = _record_elsewhere(sessions_dir(), tmp_path / "other",
                                  {"role": "system", "content": "s"},
                                  {"role": "user", "content": "别处的会话"},
                                  {"role": "assistant", "content": "答"})
    return here, elsewhere


def test_picker_only_lists_sessions_recorded_in_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pai.modes.resume import recent_sessions
    here, elsewhere = _two_places(tmp_path)          # elsewhere 更新，不过滤的话它排第一
    labels = [label for _, label in recent_sessions()]
    assert any("这里的会话" in l for l in labels) and not any("别处的会话" in l for l in labels), labels

    printed = []
    _run(["/resume", "", "/exit"], [], out=printed.append, history_path=tmp_path / "h")
    text = "\n".join(printed)
    assert "这里的会话" in text and "别处的会话" not in text, text


def test_resume_latest_skips_sessions_recorded_elsewhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pai.core.session import resolve_resume_target
    here, elsewhere = _two_places(tmp_path)
    assert resolve_resume_target(None) == here, "无参 = 当前目录最近一次，不是目录里最近一次"

    only_elsewhere = tmp_path / "only"
    only_elsewhere.mkdir()
    _record_elsewhere(only_elsewhere, tmp_path / "other2", {"role": "user", "content": "x"})
    with pytest.raises(FileNotFoundError) as e:
        resolve_resume_target(None, directory=only_elsewhere)
    assert "当前目录" in str(e.value) and "id" in str(e.value), str(e.value)


def test_explicit_id_still_reaches_a_session_recorded_elsewhere(tmp_path, monkeypatch):
    """跨目录只能明确指定（CC 的 --resume <uuid> 同款）；恢复提示会说明录制目录不同（feature 35）。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.session import resolve_resume_target
    _, elsewhere = _two_places(tmp_path)
    sid = load_session(elsewhere)[0]["id"]
    assert resolve_resume_target(sid[:8]) == elsewhere
    printed = []
    _run([f"/resume {sid[:8]}", "/exit"], [], out=printed.append, history_path=tmp_path / "h")
    assert any("录制于" in line for line in printed), printed
