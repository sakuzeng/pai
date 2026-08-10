"""记忆扫描侧：frontmatter 解析 + 目录扫描（feature 10 Task 1）。

召回与索引投影共用这一个扫描结果，所以它的边界（只读前 30 行、排除索引文件、
坏文件不炸）必须先钉死——上层两个消费者都建在它上面。
"""

from __future__ import annotations

import os
from pathlib import Path

from pai.core.memory import (
    FRONTMATTER_MAX_LINES,
    MAX_SCANNED,
    MEMORY_INDEX,
    parse_frontmatter,
    scan_memories,
)


def write_memory(directory: Path, name: str, *, description: str = "一句话描述",
                 type_: str = "project", body: str = "正文", mtime: float | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "metadata:\n"
        f"  type: {type_}\n"
        "  originSessionId: abc123\n"
        "  modified: 2026-08-11T10:00:00Z\n"
        "---\n"
        "\n"
        f"{body}\n",
        encoding="utf-8",
    )
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_parses_our_own_frontmatter(tmp_path: Path):
    path = write_memory(tmp_path, "构建约定", description="用 ./test.sh 跑测试", type_="feedback")
    fields = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert fields["name"] == "构建约定"
    assert fields["description"] == "用 ./test.sh 跑测试"
    assert fields["type"] == "feedback"                      # metadata 块被拍平
    assert fields["originSessionId"] == "abc123"


def test_strips_quotes_from_values(tmp_path: Path):
    # CC 写出来的 description 是带引号的（本机实测样本），解析必须去引号
    (tmp_path / "a.md").write_text(
        '---\nname: a\ndescription: "带逗号,所以加了引号"\n---\n正文\n', encoding="utf-8")
    fields = parse_frontmatter((tmp_path / "a.md").read_text(encoding="utf-8"))
    assert fields["description"] == "带逗号,所以加了引号"


def test_ignores_unknown_keys_instead_of_failing(tmp_path: Path):
    (tmp_path / "a.md").write_text(
        "---\nname: a\nnode_type: memory\nmetadata:\n  weird: 1\n---\n正文\n", encoding="utf-8")
    fields = parse_frontmatter((tmp_path / "a.md").read_text(encoding="utf-8"))
    assert fields["name"] == "a"
    assert fields["node_type"] == "memory"       # 不认识也原样收着，不报错


def test_no_frontmatter_parses_to_empty(tmp_path: Path):
    assert parse_frontmatter("- 2026-08-10 这是 06 时代的裸 bullet\n") == {}


def test_scan_excludes_the_index_file(tmp_path: Path):
    write_memory(tmp_path, "甲")
    (tmp_path / MEMORY_INDEX).write_text("# 记忆索引\n\n- [甲](甲.md)\n", encoding="utf-8")
    names = [h.name for h in scan_memories(tmp_path)]
    assert names == ["甲"]                        # MEMORY.md 已常驻上下文，不该再进 manifest


def test_scan_sorts_by_mtime_newest_first(tmp_path: Path):
    write_memory(tmp_path, "旧", mtime=1_700_000_000)
    write_memory(tmp_path, "新", mtime=1_800_000_000)
    write_memory(tmp_path, "中", mtime=1_750_000_000)
    assert [h.name for h in scan_memories(tmp_path)] == ["新", "中", "旧"]


def test_scan_caps_at_max_scanned_keeping_the_newest(tmp_path: Path):
    for i in range(MAX_SCANNED + 5):
        write_memory(tmp_path, f"m{i:03d}", mtime=1_700_000_000 + i)
    headers = scan_memories(tmp_path)
    assert len(headers) == MAX_SCANNED
    assert headers[0].name == f"m{MAX_SCANNED + 4:03d}"      # 留下的是最新的那批


def test_scan_reads_only_the_first_lines(tmp_path: Path):
    padding = "".join(f"pad{i}: x\n" for i in range(FRONTMATTER_MAX_LINES + 2))
    (tmp_path / "长.md").write_text(
        f"---\nname: 长\n{padding}description: 藏在三十行之后\n---\n正文\n", encoding="utf-8")
    header = scan_memories(tmp_path)[0]
    assert header.description != "藏在三十行之后"     # 读不到就是读不到，manifest 成本才恒定


def test_legacy_file_without_frontmatter_degrades(tmp_path: Path):
    # 06 时代写下的裸 bullet 文件：能用、不报错、不需要迁移脚本
    (tmp_path / "约定.md").write_text("\n- 2026-08-10 用户偏好中文回复\n- 2026-08-10 另一条\n",
                                      encoding="utf-8")
    header = scan_memories(tmp_path)[0]
    assert header.name == "约定"
    assert header.type == "legacy"
    assert "用户偏好中文回复" in header.description


def test_unreadable_file_is_skipped_not_fatal(tmp_path: Path):
    write_memory(tmp_path, "好的")
    (tmp_path / "坏的.md").write_bytes(b"---\nname: \xff\xfe\n---\n")
    assert [h.name for h in scan_memories(tmp_path)] == ["好的"]


def test_missing_directory_scans_to_empty(tmp_path: Path):
    assert scan_memories(tmp_path / "还不存在") == []
