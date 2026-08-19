# 06-20260810-memory · 实施计划

7 个 task，严格 TDD（先红后绿，贴真实 pytest 输出）。基线：193 passed, 3 deselected。
分支 `feat/memory`（自 `feat/repl` 开出）。每个 task 一条 devlog。

顺序按依赖排：发现 → 导入 → 自动记忆读 → 接线 → 压缩重注入 → 写回 → `/memory`。
Task 5 是本功能唯一「不做就是 bug」的一环，不许挪到最后。

---

## Task 1：分层发现（`core/memory.py`）

测试先行（`tests/test_memory.py`，新建；全部用 `tmp_path` 造目录树）：

1. `test_discovers_up_the_tree_root_first` —— `a/b/c` 三级各放 `PAI.md`，
   cwd=`a/b/c` 时顺序是 `a → a/b → a/b/c`（根在前，越近越晚）。
2. `test_local_comes_after_plain_in_same_dir` —— 同目录 `PAI.md` 在前、`PAI.local.md` 在后。
3. `test_user_level_comes_first` —— `~/.pai/PAI.md`（注入 home）排在所有项目文件之前。
4. `test_subdirectory_files_are_not_loaded` —— cwd 之下子目录里的 `PAI.md` 不进结果。
5. `test_missing_files_are_skipped_silently` —— 没有任何文件时返回 `[]`，不抛。
6. `test_agents_md_is_not_read` —— 放一个 `AGENTS.md` 断言不被读（问 2 的裁决要被钉死，
   否则以后有人「顺手加上」）。

实现：`discover(cwd, home) -> list[Path]`，两个参数都可注入（否则测试要 chdir + 改 HOME）。

验收：193 → 199 passed（+6）。

## Task 2：`@path` 导入展开

测试先行（同文件）：

1. `test_import_is_relative_to_the_importing_file` —— `a/PAI.md` 里写 `@sub/x.md`
   解析成 `a/sub/x.md`，不是 cwd/sub/x.md。
2. `test_import_recurses_up_to_four_hops` —— 链式导入 5 层，第 5 层不展开且留提示行。
3. `test_import_cycle_terminates` —— A↔B 互导入，不死循环、不爆栈。
4. `test_inline_code_and_fenced_blocks_are_not_imports` —— `` `@README` `` 与
   ```` ```\n@README\n``` ```` 都保持字面。
5. `test_missing_import_leaves_a_note_not_an_exception`
6. `test_absolute_and_home_paths_work` —— `@~/.pai/x.md` 与绝对路径。

实现：`expand_imports(text, base, depth=0, seen=frozenset()) -> str`。
先剥代码块（记录区间）再扫 `@path`，避免正则误伤。

验收：+6 → 205 passed。

## Task 3：自动记忆的读取（项目 key + 上限）

测试先行：

1. `test_project_key_comes_from_git_root` —— 仓库内两个子目录得到同一个 key
   （用 `git init` 造临时仓库；worktree 共享是同一条语义）。
2. `test_project_key_falls_back_to_project_root_outside_git`
3. `test_memory_index_is_truncated_at_200_lines`
4. `test_memory_index_is_truncated_at_25kb`
5. `test_truncation_leaves_an_explicit_note` —— 官方静默截断，pai 必须留提示。
6. `test_topic_files_are_not_loaded_at_startup` —— 目录里有 `debugging.md` 也不进结果。

实现：`memory_dir(cwd, home)` / `load_memory_index(dir)`；
`MAX_INDEX_LINES = 200`、`MAX_INDEX_BYTES = 25 * 1024`（官方数字，注释写明出处）。

验收：+6 → 211 passed。

## Task 4：接线进 loop 与两个模式

测试先行（`tests/test_loop.py` / `test_modes.py` / `test_interactive.py`）：

1. `test_instructions_become_the_first_user_message` —— 断言请求里
   `[system, user(指令), user(任务)]` 的确切顺序。
2. `test_no_instructions_preserves_old_message_shape` —— 不传 `instructions` 时
   与现在逐字相同（again：默认 None = 行为不变）。
3. `test_instructions_are_loaded_lazily_once_per_run` —— 传的是可调用对象，
   loop 在开头调一次（不是每步调）。
4. `test_once_and_repl_both_assemble_instructions` —— 两条装配路径都真的接上了。

实现：`run_agent(..., instructions: Callable[[], str] | None = None)`；
`modes/once.py` 与 `modes/interactive.py` 各自装配 `memory.build_context()`。

验收：+4 → 215 passed。

## Task 5：压缩后重注入（必做，不是加分项）

测试先行（`tests/test_loop.py`，e2e，fake provider 扮演摘要模型）：

1. `test_instructions_survive_compaction` —— 触发压缩后，下一次请求的 messages 里
   仍有指令消息，且位置在 system 之后。
2. `test_reinjected_instructions_are_re-read_from_disk` —— 中途改文件内容，
   断言压缩后拿到的是新内容（这条区分「重读」与「缓存字符串」，是本 task 的核心）。
3. `test_no_reinjection_when_instructions_not_provided` —— 老行为不变。

实现：loop 的压缩块里，`compact()` 之后 `messages.insert(1, instruction_message)`，
内容来自重新调用 `instructions()`。注意与 `messages[:]` 原地替换的配合顺序。

验收：+3 → 218 passed。

## Task 6：`remember` 工具 + 审计

测试先行（`tests/test_tools.py` + `tests/test_loop.py`）：

1. `test_remember_writes_topic_file_and_indexes_it` —— 主题文件有内容，
   `MEMORY.md` 里有指向它的一行。
2. `test_remember_appends_without_clobbering` —— 第二次写不覆盖第一次。
3. `test_remember_rejects_path_traversal` —— `../../etc/x`、绝对路径、
   带 `/` 的 topic 全部被挡（模型生成的参数是唯一能指定写盘路径的地方）。
4. `test_remember_returns_error_string_on_failure` —— 不抛（工具错误不 throw）。
5. `test_memory_written_event_is_emitted_and_logged` —— 事件发出且落进会话 JSONL。
6. `test_remember_is_available_in_once_mode` —— 与 `ask_user_question` 不同，
   写回不是交互模式独有的。

实现：`core/tools/memory_tool.py`（名字避开 `core/memory.py`）；
`core/events.py` 加 `MemoryWritten`；loop 落盘。

验收：+6 → 224 passed。

## Task 7：`/memory` 命令（REPL）

测试先行（`tests/test_interactive.py`）：

1. `test_slash_memory_lists_loaded_files` —— 列出实际加载的文件路径与行数。
2. `test_slash_memory_shows_memory_dir` —— 显示自动记忆目录位置。
3. `test_slash_memory_says_so_when_nothing_loaded` —— 没有任何指令文件时明确说「没有」，
   而不是打印空白（「指令没生效」的第一诊断步骤）。

实现：`interactive._handle_command` 加分支；`HELP` 加一行。

验收：+3 → 227 passed 左右，`./test.sh` 全绿。

---

## 每 task 完成后必做

devlog 一条（目标 / 改动文件 / 红→绿真实数字 / 遗留）。全部完成后：全局 devlog 里程碑一行、
decisions 记问 1 的取舍（进 user 消息 + 重注入的代价）与问 2（不读 AGENTS.md 的理由）、
STATUS 模块表与测试数字更新、遗留逐条进 TODO。
