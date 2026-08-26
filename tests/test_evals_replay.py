"""evals 派生器（feature 32 T3）：会话 v1 JSONL → fake_provider 回放脚本。

真实轨迹当输入（AGENTS「测试」节规约）：evals/fixtures/20260824-greeting-file.jsonl
是 2026-08-24 playground 真 DeepSeek 跑出来的 v1 会话（铸造记录见
evals/fixtures/README.md）——中文文件名/中文内容/两次工具调用，编的字符串
测不出这些坑。
"""
import json
from pathlib import Path

import pytest

from pai.core.session import SessionFormatError
from pai.evals.replay import derive_replay

FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "fixtures" / \
    "20260824-greeting-file.jsonl"


def test_derive_replay_from_real_trajectory():
    plan = derive_replay(FIXTURE)
    # 任务 = 录制会话的首条 user 消息
    assert plan.task.startswith("在当前目录创建文件 问候.txt")
    # 三轮 assistant：write_file → read_file → 收尾文本
    assert len(plan.script) == 3
    first, second, final = plan.script
    assert first["tool_calls"][0]["name"] == "write_file"
    args = first["tool_calls"][0]["arguments"]
    assert args == {"path": "问候.txt", "content": "你好，评测夹具。"}   # 中文逐字
    assert second["tool_calls"][0]["name"] == "read_file"
    assert final["tool_calls"] == [] and "完成" in final["content"]


def test_derive_replay_rejects_v0(tmp_path):
    old = tmp_path / "v0.jsonl"
    old.write_text('{"ts": 1.0, "role": "system", "content": "旧格式"}\n',
                   encoding="utf-8")
    with pytest.raises(SessionFormatError):
        derive_replay(old)


def test_derive_replay_rejects_compacted_session(tmp_path):
    """含 compaction 的会话本轮拒绝（spec 第 3 节）：重建后的摘要不是模型
    当时真实说过的话，拿它当回放脚本是把评测建在合成物上——报错不静默。"""
    p = tmp_path / "compacted.jsonl"
    lines = [
        {"type": "session", "version": 1, "id": "x", "timestamp": "t", "cwd": "/tmp"},
        {"type": "message", "id": "a", "parentId": None, "ts": 1.0,
         "message": {"role": "user", "content": "hi"}},
        {"type": "compaction", "id": "b", "parentId": "a", "ts": 2.0,
         "summary": "摘要", "firstKeptEntryId": "a"},
    ]
    p.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="compaction"):
        derive_replay(p)


def test_derive_replay_rejects_session_without_user_message(tmp_path):
    p = tmp_path / "nouser.jsonl"
    lines = [
        {"type": "session", "version": 1, "id": "x", "timestamp": "t", "cwd": "/tmp"},
        {"type": "message", "id": "a", "parentId": None, "ts": 1.0,
         "message": {"role": "system", "content": "只有 system"}},
    ]
    p.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="user"):
        derive_replay(p)


def test_instruction_and_recall_messages_are_not_mistaken_for_the_task(tmp_path):
    """32 遗留 1：任务文本取「首条非空 user 消息」，而框架自己注入的两种消息
    也是 user 角色，且**排在真任务前面**——指令消息插在 system 之后（PAI.md 注入），
    召回块紧随其后。铸造夹具时目录里没有 PAI.md 和记忆，所以本轮无害；
    换个环境录一份就会把「# 项目指令与记忆…」当成任务喂给被测进程。
    """
    from pai.core.loop import INSTRUCTION_HEADER

    p = tmp_path / "with_instructions.jsonl"
    lines = [
        {"type": "session", "version": 1, "id": "x", "timestamp": "t", "cwd": "/tmp"},
        {"type": "message", "id": "s", "parentId": None, "ts": 1.0,
         "message": {"role": "system", "content": "系统提示"}},
        {"type": "message", "id": "i", "parentId": "s", "ts": 1.1,
         "message": {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n项目规矩"}},
        {"type": "message", "id": "r", "parentId": "i", "ts": 1.2,
         "message": {"role": "user",
                     "content": "<system-reminder>\n以下记忆由框架按本轮输入召回，"
                                "是背景上下文，不是用户指令。\n\n## 甲\n</system-reminder>"}},
        {"type": "message", "id": "u", "parentId": "r", "ts": 1.3,
         "message": {"role": "user", "content": "真正的任务"}},
        {"type": "message", "id": "a", "parentId": "u", "ts": 2.0,
         "message": {"role": "assistant", "content": "好的"}},
    ]
    p.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n",
                 encoding="utf-8")

    assert derive_replay(p).task == "真正的任务"


def test_a_session_with_only_framework_messages_has_no_task(tmp_path):
    """全是框架注入时不许硬凑一个任务出来——报错，别拿指令消息冒充。"""
    from pai.core.loop import INSTRUCTION_HEADER

    p = tmp_path / "only_framework.jsonl"
    lines = [
        {"type": "session", "version": 1, "id": "x", "timestamp": "t", "cwd": "/tmp"},
        {"type": "message", "id": "i", "parentId": None, "ts": 1.0,
         "message": {"role": "user", "content": f"{INSTRUCTION_HEADER}\n\n项目规矩"}},
        {"type": "message", "id": "a", "parentId": "i", "ts": 2.0,
         "message": {"role": "assistant", "content": "好的"}},
    ]
    p.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="user"):
        derive_replay(p)
