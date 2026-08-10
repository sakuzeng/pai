"""索引投影与新鲜度（feature 10 Task 2）。

本文件里最重要的一条是 test_index_is_derived_from_files_not_from_the_disk_index：
它是「投影 vs 账本」的判据——账本实现（往 MEMORY.md 打补丁）在这条上必红。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pai.core.memory import (
    MAX_INDEX_LINES,
    MEMORY_INDEX,
    freshness_note,
    load_memory_index,
    memory_age,
    render_index,
    scan_memories,
)

from tests.test_memory_scan import write_memory


def ts(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def test_memory_age_says_today(tmp_path: Path):
    assert memory_age(ts("2026-08-11 09:00"), ts("2026-08-11 23:00")) == "今天"


def test_memory_age_uses_calendar_days_not_elapsed_seconds():
    # 相差只有两小时，但跨了日历日——按 86400 秒整除会错答「今天」
    assert memory_age(ts("2026-08-10 23:00"), ts("2026-08-11 01:00")) == "昨天"


def test_memory_age_counts_days():
    assert memory_age(ts("2026-06-25 10:00"), ts("2026-08-11 10:00")) == "47 天前"


def test_freshness_note_is_empty_within_one_day():
    # 新鲜时警告是噪音（CC 同款阈值：>1 天才提示）
    assert freshness_note(ts("2026-08-11 09:00"), ts("2026-08-11 10:00")) == ""
    assert freshness_note(ts("2026-08-10 09:00"), ts("2026-08-11 10:00")) == ""


def test_freshness_note_warns_that_file_line_refs_may_be_stale():
    note = freshness_note(ts("2026-06-25 10:00"), ts("2026-08-11 10:00"))
    assert "47 天前" in note
    assert "时间点观察" in note        # 记忆不是实时状态
    assert "file:line" in note         # 带行号的引用会让过期声明显得更权威


def test_render_index_without_now_has_no_relative_time(tmp_path: Path):
    write_memory(tmp_path, "甲", description="用 ./test.sh 跑测试")
    text = render_index(scan_memories(tmp_path))
    assert "- [甲](甲.md) — 用 ./test.sh 跑测试" in text
    # 相对时间是**渲染时刻**的函数，写进持久文件就会腐坏——正是新鲜度要防的东西
    assert "今天" not in text


def test_render_index_with_now_includes_relative_time(tmp_path: Path):
    write_memory(tmp_path, "甲", description="用 ./test.sh 跑测试", mtime=ts("2026-06-25 10:00"))
    text = render_index(scan_memories(tmp_path), now=ts("2026-08-11 10:00"))
    assert "47 天前" in text


def test_index_header_declares_it_is_generated(tmp_path: Path):
    write_memory(tmp_path, "甲")
    text = render_index(scan_memories(tmp_path))
    assert "自动生成" in text and "手改会被覆盖" in text


def test_render_index_of_empty_directory_is_empty(tmp_path: Path):
    # 空串让 build_context 据此不插「自动记忆」那一节
    assert render_index(scan_memories(tmp_path)) == ""


def test_index_is_derived_from_files_not_from_the_disk_index(tmp_path: Path):
    """判据测试：盘上的 MEMORY.md 与实际文件不一致时，进上下文的必须是**文件**那套。"""
    write_memory(tmp_path, "真实的", description="这条才存在")
    (tmp_path / MEMORY_INDEX).write_text(
        "# 记忆索引\n\n- [陈旧的](陈旧的.md) — 这个文件早就被删了\n", encoding="utf-8")
    text = load_memory_index(tmp_path)
    assert "真实的" in text
    assert "陈旧的" not in text


def test_truncation_notice_points_at_recall_not_read_file(tmp_path: Path):
    for i in range(MAX_INDEX_LINES + 10):
        write_memory(tmp_path, f"m{i:03d}", mtime=1_700_000_000 + i)
    text = load_memory_index(tmp_path)
    # 读侧已经不读 MEMORY.md 了，旧提示语「用 read_file 直接读该文件」指错了地方；
    # 而且有召回层之后，被截断 ≠ 那条记忆不存在
    assert "read_file" not in text
    assert "召回" in text
