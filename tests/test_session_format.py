"""feature 24（R4#A1）：会话格式 v1——首行 header + 统一信封 + 压缩即条目。

形状是三家收敛形（K loop/session-format-three-way.md）：pi/CC/dsh 在
「header 首行、{type,id,parentId,ts} 信封、消息嵌套 payload、压缩记成带
firstKeptEntryId 的条目」上完全一致。拍板 A/B/A 见 features/24 README。
"""

import json

import pytest

from pai.core.session import (
    SESSION_VERSION,
    SessionFormatError,
    SessionLog,
    build_messages,
    load_session,
    replay_messages,
)
from test_compaction import REAL_TRAJECTORY


def _lines(log):
    return [json.loads(l) for l in
            log.path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---- T1 写侧 -------------------------------------------------------------


def test_first_line_is_a_header_with_version_and_identity(tmp_path):
    log = SessionLog(tmp_path)
    log.append({"role": "user", "content": "你好"})
    head = _lines(log)[0]
    assert head["type"] == "session"
    assert head["version"] == SESSION_VERSION
    assert head["id"] == log.session_id
    assert head["cwd"] == log.cwd
    assert "timestamp" in head


def test_messages_are_wrapped_in_an_envelope_with_nested_payload(tmp_path):
    """消息嵌 `message` 字段（pi/CC 同款）：顶层判别字段只有 type——
    「消息用 role、旁账用 type」的双轨病就是本 feature 要治的。"""
    log = SessionLog(tmp_path)
    log.append({"role": "user", "content": "你好"})
    entry = _lines(log)[1]
    assert entry["type"] == "message"
    assert entry["message"] == {"role": "user", "content": "你好"}
    assert "role" not in entry, "role 不许再出现在顶层"
    assert entry["id"] and entry["parentId"] is None
    assert isinstance(entry["ts"], float)


def test_type_records_keep_their_fields_beside_the_envelope(tmp_path):
    """非消息记录（usage/compaction）字段与信封并排（pi 的 typed entry 同款）。"""
    log = SessionLog(tmp_path)
    log.append({"type": "usage", "step": 2, "total_tokens": 7})
    entry = _lines(log)[1]
    assert entry["type"] == "usage"
    assert entry["step"] == 2 and entry["total_tokens"] == 7
    assert entry["id"]


def test_parent_id_chains_entries_in_file_order(tmp_path):
    log = SessionLog(tmp_path)
    id1 = log.append({"role": "user", "content": "一"})
    id2 = log.append({"role": "assistant", "content": "二"})
    entries = _lines(log)[1:]
    assert [e["id"] for e in entries] == [id1, id2]
    assert entries[0]["parentId"] is None
    assert entries[1]["parentId"] == id1


def test_append_can_preserve_an_explicit_id_for_resume(tmp_path):
    """CC 反教材（K session-format-three-way 第二节）：resume 路径造新身份会让
    转录每次恢复指数增长。重录必须能按原 id 写。"""
    log = SessionLog(tmp_path)
    got = log.append({"role": "user", "content": "x"}, record_id="fixed-id-01")
    assert got == "fixed-id-01"
    assert _lines(log)[1]["id"] == "fixed-id-01"


# ---- T2 读侧 -------------------------------------------------------------


def test_v0_files_are_refused_with_an_honest_message(tmp_path):
    """拍板问 2 = B：旧格式不做读兼容，如实提示。旧文件不动不删。"""
    p = tmp_path / "old.jsonl"
    p.write_text(json.dumps({"role": "user", "content": "旧格式"}) + "\n",
                 encoding="utf-8")
    with pytest.raises(SessionFormatError) as e:
        load_session(p)
    assert "旧格式" in str(e.value)


def test_newer_versions_are_refused_with_the_upgrade_direction(tmp_path):
    """dsh 语义：版本不认识要说明方向——「太新请升级」与「损坏」是两种错误。"""
    p = tmp_path / "future.jsonl"
    p.write_text(json.dumps({"type": "session", "version": SESSION_VERSION + 1,
                             "id": "x", "timestamp": "t", "cwd": "/"}) + "\n",
                 encoding="utf-8")
    with pytest.raises(SessionFormatError) as e:
        load_session(p)
    assert "升级" in str(e.value)


def test_unknown_entry_types_are_refused_unless_ignorable(tmp_path):
    """dsh 教训：静默跳过一个不认识的必需事件可能改变日志其余部分的解读方式。"""
    log = SessionLog(tmp_path)
    log.append({"role": "user", "content": "x"})
    with open(log.path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "从未见过", "id": "z", "parentId": None,
                            "ts": 0.0}) + "\n")
    with pytest.raises(SessionFormatError):
        load_session(log.path)

    with open(log.path, "a", encoding="utf-8") as f:
        pass
    # ignorable 的未知类型放行（改写最后一行）
    lines = log.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    rec["ignorable"] = True
    lines[-1] = json.dumps(rec, ensure_ascii=False)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    header, entries = load_session(log.path)
    assert header["version"] == SESSION_VERSION


# ---- T3 重建 -------------------------------------------------------------


def test_build_messages_rebuilds_a_real_trajectory(tmp_path):
    log = SessionLog(tmp_path)
    for m in REAL_TRAJECTORY:
        log.append(m)
    log.append({"type": "usage", "step": 1, "total_tokens": 5})
    _, entries = load_session(log.path)
    messages, ledger = build_messages(entries)
    assert messages == REAL_TRAJECTORY
    assert len(ledger) == len(messages)
    assert all(ledger), "每条消息都要有对应的 entry id"


def test_build_messages_reconstructs_a_compacted_session(tmp_path):
    """压缩即条目（pi buildContextEntries 同款）：历史一字不删，重建 =
    [system, 摘要 user, 自 firstKeptEntryId 起的保留段, 压缩条目之后的全部]。
    feature 23 的「拒收压缩会话」历史使命就此结束。"""
    log = SessionLog(tmp_path)
    ids = [log.append(m) for m in [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "旧问题"},
        {"role": "assistant", "content": "旧回答"},
        {"role": "user", "content": "新问题"},
        {"role": "assistant", "content": "新回答"},
    ]]
    log.append({"type": "compaction", "step": 3, "cut": 3,
                "firstKeptEntryId": ids[3], "summary": "早前聊了旧问题"})
    log.append({"role": "user", "content": "压缩后的追问"})
    _, entries = load_session(log.path)
    messages, ledger = build_messages(entries)
    assert messages == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "[早前对话的摘要，供延续任务用]\n早前聊了旧问题"},
        {"role": "user", "content": "新问题"},
        {"role": "assistant", "content": "新回答"},
        {"role": "user", "content": "压缩后的追问"},
    ]
    assert ledger[2] == ids[3], "保留段的 id 必须是原 id"


def test_build_messages_relocates_the_instruction_after_system(tmp_path):
    """压缩后重注入的指令消息在文件尾部，但内存里它永远在 system 之后
    （_inject_instructions 的 insert 位置）；重建要放回同一位置，且只留最新一条。"""
    from pai.core.loop import INSTRUCTION_HEADER

    log = SessionLog(tmp_path)
    ids = [log.append(m) for m in [
        {"role": "system", "content": "s"},
        {"role": "user", "content": f"{INSTRUCTION_HEADER}\n旧指令"},
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
    ]]
    log.append({"type": "compaction", "step": 2, "cut": 2,
                "firstKeptEntryId": ids[2], "summary": "摘要"})
    log.append({"role": "user", "content": f"{INSTRUCTION_HEADER}\n新指令"})
    _, entries = load_session(log.path)
    messages, ledger = build_messages(entries)
    assert messages[0]["role"] == "system"
    assert messages[1]["content"].startswith(INSTRUCTION_HEADER)
    assert "新指令" in messages[1]["content"]
    assert sum(1 for m in messages
               if str(m.get("content", "")).startswith(INSTRUCTION_HEADER)) == 1


def test_replay_messages_now_goes_through_the_v1_loader(tmp_path):
    log = SessionLog(tmp_path)
    for m in REAL_TRAJECTORY:
        log.append(m)
    assert replay_messages(log.path) == REAL_TRAJECTORY


# ---- T5 resume：配平、目标解析 -------------------------------------------


def test_trim_unfinished_drops_the_torn_tail():
    """CC 三道过滤的 pai 版（K session-format-three-way 第二节）：assistant 声明的
    tool_calls 没有对应结果就整块删——半截回合发回去就是 400。
    dsh 的说法是「内存配平中断轮次，物理尾部保持撕裂原样」——修复只在读取侧。"""
    from pai.core.session import trim_unfinished

    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "bash", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "结果"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c2", "type": "function",
                         "function": {"name": "bash", "arguments": "{}"}}]},
        # c2 的结果没落盘——进程死在这里
    ]
    ledger = ["i0", "i1", "i2", "i3", "i4"]
    trimmed, trimmed_ledger = trim_unfinished(messages, ledger)
    assert trimmed == messages[:4]
    assert trimmed_ledger == ledger[:4]


def test_trim_unfinished_drops_orphan_tool_results():
    from pai.core.session import trim_unfinished

    messages = [{"role": "user", "content": "问"},
                {"role": "tool", "tool_call_id": "ghost", "content": "孤儿结果"}]
    trimmed, _ = trim_unfinished(messages, [None, None])
    assert trimmed == [{"role": "user", "content": "问"}]


def test_resolve_resume_target_picks_the_latest_session(tmp_path):
    from pai.core.session import SessionLog, resolve_resume_target

    a = SessionLog(tmp_path)
    a.append({"role": "user", "content": "旧"})
    import time as _t
    _t.sleep(0.02)
    b = SessionLog(tmp_path)
    b.append({"role": "user", "content": "新"})
    (tmp_path / "x.events.jsonl").write_text("{}\n", encoding="utf-8")

    assert resolve_resume_target(None, directory=tmp_path) == b.path


def test_resolve_resume_target_by_id_prefix_and_by_path(tmp_path):
    from pai.core.session import SessionLog, resolve_resume_target

    log = SessionLog(tmp_path)
    log.append({"role": "user", "content": "x"})
    assert resolve_resume_target(log.session_id[:8], directory=tmp_path) == log.path
    assert resolve_resume_target(str(log.path), directory=tmp_path) == log.path


def test_resolve_resume_target_errors_honestly_when_nothing_matches(tmp_path):
    from pai.core.session import resolve_resume_target

    with pytest.raises(FileNotFoundError):
        resolve_resume_target(None, directory=tmp_path)      # 目录里一个会话都没有
    with pytest.raises(FileNotFoundError):
        resolve_resume_target("deadbeef", directory=tmp_path)


def test_second_compaction_can_keep_the_first_summary(tmp_path):
    """交付后自查撞出的边界：第二次压缩的切点落在**第一次的摘要消息**上时，
    firstKeptEntryId 指向的是 compaction 条目而不是 message 条目。
    pi 的 buildContextEntries 扫**全部条目**、保留段里的 compaction 条目化身为
    摘要消息；只扫 message 条目的实现会把保留段静默丢光。"""
    log = SessionLog(tmp_path)
    ids = [log.append(m) for m in [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "很旧的问题"},
        {"role": "assistant", "content": "很旧的回答"},
    ]]
    comp1 = log.append({"type": "compaction", "step": 1, "cut": 1,
                        "firstKeptEntryId": ids[1], "summary": "第一次摘要"})
    ids2 = [log.append(m) for m in [
        {"role": "user", "content": "后来的问题"},
        {"role": "assistant", "content": "后来的回答"},
    ]]
    # 第二次压缩：切点恰好落在第一次的摘要消息上（保留段从它开始）
    log.append({"type": "compaction", "step": 5, "cut": 2,
                "firstKeptEntryId": comp1, "summary": "第二次摘要"})
    log.append({"role": "user", "content": "最新的问题"})
    _, entries = load_session(log.path)
    messages, ledger = build_messages(entries)
    contents = [str(m.get("content", "")) for m in messages]
    assert any("第二次摘要" in c for c in contents)
    assert any("第一次摘要" in c for c in contents), \
        "保留段以旧摘要开头：它必须以摘要消息的身份活下来，不能被静默丢掉"
    assert any("后来的问题" in c for c in contents), "旧摘要之后的保留消息也得在"
    assert any("最新的问题" in c for c in contents)
