# 10-memory-recall · 实施计划

<!-- 7 task，严格 TDD：每个 task 先写会红的测试、贴红的数字，再写实现、贴绿的数字。
     本次由主 agent 直接实现（非 SDD 分发），故 task 只写测试意图与实现要点，不转录全量代码。 -->

基线：`385 passed`（feature 09 交付时）。

## Task 1：frontmatter 解析与目录扫描

**测试先行**（`tests/test_memory_scan.py`，全部会红——函数尚不存在）：

- `test_parses_our_own_frontmatter`：`---` 围栏 + `name`/`description` + 缩进 `metadata` 块，
  取到 `type` / `originSessionId` / `modified`；带引号的值去引号。
- `test_ignores_unknown_frontmatter_keys`：多余键不报错。
- `test_scan_excludes_the_index_file`：目录里的 `MEMORY.md` 不出现在扫描结果里。
- `test_scan_sorts_by_mtime_newest_first`：`os.utime` 造三个不同 mtime，断言顺序。
- `test_scan_caps_at_200_files`：造 205 个文件，`len(...) == 200`，且留下的是最新的。
- `test_scan_reads_only_the_first_30_lines`：第 40 行放一个假的 `description:`，断言没被取到。
- `test_legacy_file_without_frontmatter_degrades`：`type == "legacy"`，
  `description` 取首个非空行，不抛。
- `test_unreadable_file_is_skipped_not_fatal`：坏文件（权限/编码）不炸整次扫描。

**实现**：`src/pai/core/memory.py` 加 `MemoryHeader` dataclass、`FRONTMATTER_MAX_LINES = 30`、
`MAX_SCANNED = 200`、`_parse_frontmatter(head)`、`scan_memories(directory)`。

## Task 2：相对时间与索引投影

**测试先行**（`tests/test_memory_index.py`）：

- `test_memory_age_uses_calendar_days`：昨晚 23:00 vs 今早 01:00 → `昨天`（不是 `今天`）；
  47 天 → `47 天前`。
- `test_freshness_note_is_empty_within_one_day`：今天/昨天 → 空串。
- `test_freshness_note_warns_about_stale_file_line_refs`：≥2 天 → 含「时间点观察」与 `file:line`。
- `test_render_index_without_now_has_no_relative_time`：**盘上那份不含相对时间**
  （防止时间戳腐坏，spec 三）。
- `test_render_index_with_now_includes_relative_time`。
- `test_index_header_marks_it_generated`：头部含「自动生成，手改会被覆盖」。
- `test_load_memory_index_is_derived_from_files_not_from_disk_index`：
  **本 task 的判据测试**——盘上 `MEMORY.md` 写着一行陈旧内容，目录里的记忆文件是另一套，
  断言拿到的是**文件那套**。账本实现过不了这条。
- `test_truncation_notice_no_longer_points_at_read_file`：截断提示改词。

**实现**：`memory_age` / `freshness_note` / `render_index(headers, now=None)`；
`load_memory_index` 改为 `scan → render → 截断`（保留 200 行 / 25KB 两条上限）。

## Task 3：remember 改写为「创建或更新一篇记忆」

**测试先行**（改 `tests/test_memory.py` 现有 remember 段 + 新增）：

- `test_writes_frontmatter_that_scan_can_read_back`：写完用 `scan_memories` 读回，字段齐。
- `test_same_name_updates_instead_of_creating_a_second_file`：目录里仍只有 1 个记忆文件；
  正文两段都在；`description` 与 `modified` 是**新的**。
- `test_rebuilds_index_from_files`：写三篇 → 索引三行。
- `test_deleted_memory_disappears_from_the_index_after_next_write`：
  **投影方案的判据测试**（spec 验收 3）。
- `test_rejects_path_traversal_name`：`_safe_topic` 白名单原样保留。
- `test_index_write_is_atomic`：写入过程中不出现半截文件（同目录 tmp + `os.replace`）。
- `test_origin_session_id_is_recorded_when_injected`：`set_origin_session()` 注入后进 frontmatter；
  不注入则该字段缺席而不是空值。

**实现**：`memory_tool.remember(name, description, fact, type="project")`；
`set_origin_session()` 注入点（与 `set_memory_dir` 同一套，D#40）；
落盘后 `_rebuild_index(dir)` = `render_index(scan_memories(dir))` + 原子写。

## Task 4：召回选择器

**测试先行**（`tests/test_recall.py`，用 `tests/fake_llm.FakeClient`）：

- `test_manifest_line_format`：`- [type] 文件名 (相对时间): description`。
- `test_empty_directory_short_circuits_without_a_request`：`len(client.requests) == 0`。
- `test_already_surfaced_files_are_filtered_before_the_request`：manifest 里不含它们。
- `test_whitelist_rejects_hallucinated_filenames`：模型回一个不存在的文件名 → 被丢掉。
- `test_caps_at_five_files`：模型回 8 个 → 只留 5 个。
- `test_defensive_json_parsing`：回复带前后废话（```json 包裹）仍能解析。
- `test_client_exception_degrades_to_empty`：client 抛异常 → `([], {})`，不向上抛。
- `test_disables_after_three_consecutive_failures`：第 4 次不再发请求。
- `test_returns_usage_for_budget_accounting`：usage 原样回传。
- `test_prompt_states_the_five_file_cap_and_prefers_empty`：断言系统提示含这两条去噪规则。

**实现**：`src/pai/core/recall.py` —— `RecallState`、`build_manifest`、`select_memories`。

## Task 5：注入块渲染

**测试先行**（`tests/test_recall.py` 续）：

- `test_block_is_wrapped_in_system_reminder`。
- `test_block_declares_it_is_background_not_instruction`。
- `test_block_includes_freshness_warning_for_old_memories`；≤1 天的不含。
- `test_block_is_empty_when_nothing_selected`：空 → 空串（loop 据此不插消息）。

**实现**：`recall.recall_block(paths, now)`。

## Task 6：loop 接线

**测试先行**（`tests/test_loop.py` 新增，注入假 callable）：

- `test_recall_text_is_appended_after_the_task_message`。
- `test_recall_usage_counts_toward_the_budget`：熔断在预期步数触发。
- `test_empty_recall_text_inserts_no_message`。
- `test_recall_is_called_once_per_run_with_the_task_as_query`。

**实现**：`run_agent(..., recall: Optional[Callable[[str], tuple[str, dict]]])`，
在 append `user_entry` 之后、进 step 循环之前调用；`spent_tokens += usage.total_tokens`。

## Task 7：装配层、配置与真实轨迹

**测试先行**：

- `tests/test_config.py`：`test_recall_model_falls_back_to_main_model`、
  `test_recall_model_env_overrides`。
- `tests/test_modes.py`：`test_repl_holds_recall_state_across_turns`
  （两轮之间 `surfaced` 不清零）。
- **真实轨迹测试**（AGENTS.md 规约）：拿 `pai_playground/sessions/*.jsonl` 的真实轨迹
  剥掉 `ts` 后当输入，跑一次「召回 + 注入 + 压缩」的组合，确认注入的记忆块不会
  把 `find_cut_point` 弄崩。轨迹抄进 `tests/fixtures/`（真跑产物一旦当夹具必须入库）。

**实现**：`config.recall_model()`；`modes/once.py` 与 `modes/interactive.py` 构建
`make_recall(...)` 闭包并注入；REPL 持有 `RecallState`。

**收尾**：`./test.sh` 全绿 → 写 `devlog.md` 各条 → 写 `复盘.md` → 遗留问题同步 TODO →
全局 devlog 一行里程碑 → 档案状态改「已交付」。
