# 测试夹具

**真跑产生的轨迹一旦被当作测试夹具，须复制进版本库**（AGENTS.md 测试规约）——
否则溯源链断在一个 gitignore 掉的目录里（这正是 STATUS 缺陷 6 记的那件事）。

| 文件 | 出处 | 用在哪 |
|---|---|---|
| `real_turn.jsonl` | `pai_playground/sessions/20260803-000946.jsonl`（真跑，2026-08-03），已剥掉 `SessionLog` 加的 `ts` 字段 | `tests/test_tui_dock.py` 的真实轨迹驱动测试 |
