# 07-20260810-permissions · 实施计划

7 个 task，严格 TDD（先红后绿，贴真实 pytest 输出）。
**基线：`276 passed, 3 deselected`**（2026-08-10 刷新——本计划初稿写于 235 那会儿，
其后交付了 feature 08 与五个补漏；下面每个 task 的累计数字已按新基线重算）。
分支 **`feat/07-permissions`**（自 `main` 开出）——初稿写的 `feat/permissions` 不合
2026-08-10 立的命名规约（`<类型>/<NN>-<描述>`），已更正。
每个 task 一条 devlog，逐条写不攒最后补。

顺序：规则求值 → 匹配下放 → bash 匹配器 → fs 匹配器 → 配置加载 → hooks → 接线。
Task 3 是「权限系统是不是纸糊的」的分水岭，不许简化。

---

## Task 1：规则解析与三态求值（`core/permissions.py`）

**测试先行**（`tests/test_permissions.py`，新建）：

1. `test_parses_bare_tool_and_specifier` —— `"Bash"` → `Rule("bash", None)`；
   `"Bash(git push *)"` → `Rule("bash", "git push *")`；大小写与空格容错。
2. `test_deny_beats_more_specific_allow` —— **本 task 的核心**：
   `deny=["Bash(aws *)"]` + `allow=["Bash(aws s3 ls)"]` → `deny`。
3. `test_ask_beats_allow`
4. `test_first_match_in_order_wins_not_most_specific`
5. `test_no_match_falls_back_to_default_decision` —— 默认 `allow`，可配成 `ask`/`deny`。
6. `test_tool_name_glob_matches_whole_name` —— `"*"` 匹配全部，`"read_*"` 匹配前缀，
   但不做未锚定的 allow glob（官方跳过并告警，pai 直接拒绝解析）。
7. `test_decision_carries_reason_and_rule` —— 拒绝要说得出「被哪条规则挡的、从哪来的」。

**实现**：`Rule` / `RuleSet` / `Decision` 三个 dataclass + `decide()`。

**验收**：235 → 283 passed（+7）。

## Task 2：匹配下放给工具（`matcher_for` + 默认实现）

**测试先行**（`tests/test_permissions.py` + `tests/test_tools.py`）：

1. `test_default_matcher_globs_first_argument` —— 没挂 matcher 的工具用默认实现。
2. `test_matcher_for_attaches_to_registered_tool` —— 装饰器把函数挂到 `Tool.matcher`。
3. `test_permission_layer_never_branches_on_tool_name` —— 白盒：给一个**假工具**挂
   自定义 matcher，断言权限层调的就是它（证明没有工具名 if-else）。
4. `test_require_all_flag_is_passed_through` —— allow 判定传 `require_all=True`，
   deny/ask 传 `False`。

**实现**：`Tool` 加 `matcher` 字段（默认 `None`）；`matcher_for(func)` 装饰器；
`permissions` 里调用 `tool.matches(specifier, args, require_all=...)`。

**验收**：+4 → 287 passed。

## Task 3：bash 匹配器（**分水岭**）

**测试先行**（`tests/test_permissions.py`）：

1. `test_compound_command_requires_every_subcommand_to_match` ——
   `allow=["Bash(ls *)"]` 时 `ls && rm -rf /` **不放行**。这条漏了权限系统等于零。
2. `test_any_subcommand_matching_deny_blocks` —— `deny=["Bash(rm *)"]` 挡下
   `echo hi && rm -rf /`。
3. `test_all_separators_split` —— `&&`、`||`、`;`、`|`、`|&`、`&`、换行 逐个覆盖。
4. `test_process_wrappers_are_stripped` —— `Bash(npm test *)` 匹配 `timeout 30 npm test`、
   `nice npm test`、`xargs npm test`；**但** `xargs -n1 npm test` 不匹配（带标志不剥）。
5. `test_env_runners_are_not_stripped_and_this_is_a_known_hole` ——
   `allow=["Bash(devbox run *)"]` **确实**放行 `devbox run rm -rf .`。
   把官方承认的洞写成测试固定下来，而不是假装没有。
6. `test_word_boundary_before_star` —— `Bash(ls *)` 匹配 `ls -la` 不匹配 `lsof`；
   `Bash(ls*)` 两者都匹配。
7. `test_colon_star_suffix_equals_trailing_space_star`

**实现**：`shell.py` 里 `@matcher_for(bash)`；拆分与剥离都是纯函数，单独可测。

**验收**：+7 → 294 passed。

## Task 4：fs 匹配器（路径锚点）

**测试先行**：

1. `test_double_slash_is_filesystem_absolute`
2. `test_tilde_is_home_relative`
3. `test_single_slash_anchors_to_the_settings_source` —— 用户设置里的 `/secrets/**`
   指向 `~/.pai/secrets/**` 而**不是**项目里的 `secrets/`（官方最大的坑）。
4. `test_bare_filename_matches_at_any_depth` —— `Read(.env)` ≡ `Read(**/.env)`。
5. `test_relative_pattern_anchors_to_cwd`
6. `test_symlink_double_check_is_not_implemented` —— **如实记录已知洞**：
   断言当前行为（只看给定路径），并在 docstring 里写清这是 TODO 而非设计。

**实现**：`fs.py` 里给 `read_file`/`write_file`/`edit_file` 挂同一个路径匹配器；
`Rule` 带 `anchor` 目录（由 source 决定）。

**验收**：+6 → 300 passed。

## Task 5：配置加载与裸名 deny 摘工具

**测试先行**：

1. `test_loads_user_then_project_settings` —— 两层都读到，`source` 标对。
2. `test_deny_in_either_layer_beats_allow_in_the_other` —— 跨层的 deny 优先，双向各测一次。
3. `test_malformed_settings_does_not_crash` —— 坏 JSON 留告警、当作空规则集，不弄挂 agent。
4. `test_bare_name_deny_removes_tool_from_schema` —— 被 `deny=["Bash"]` 挡的工具
   **不出现在发给模型的 tool schema 里**（查 `FakeClient.requests[0]["tools"]`）。
5. `test_scoped_deny_keeps_tool_visible` —— `deny=["Bash(rm *)"]` 时 bash 仍在 schema 里。

**实现**：`load_rules(cwd, home)`；`get_tools` 侧或 loop 侧做摘除（实现时定，取舍写 devlog）。

**验收**：+5 → 305 passed。

## Task 6：外部命令 hook（`core/hooks.py`）

**测试先行**（`tests/test_hooks.py`，新建；hook 用 tmp_path 里的真脚本，不 mock 子进程）：

1. `test_exit_zero_json_decision_is_honored` —— stdout 的 `permissionDecision` 生效。
2. `test_exit_two_blocks_with_stderr_as_reason`
3. `test_other_exit_codes_are_non_blocking`
4. `test_multiple_hooks_deny_beats_ask_beats_allow`
5. `test_hook_allow_cannot_override_deny_rule` —— **边界一**。
6. `test_hook_block_beats_allow_rule` —— **边界二**。
7. `test_hook_timeout_does_not_block_work` —— 超时按非阻断处理（anna 铁律）。
8. `test_hook_crash_does_not_block_work` —— 脚本本身抛异常同上。
9. `test_matcher_filters_by_tool_name`

**实现**：`run_pre_tool_use(hooks, tool, args, timeout)`；子进程用 `subprocess.run` 带超时。

**验收**：+9 → 314 passed。

## Task 7：接进 loop / ask 降级 / `/permissions` / **注入验证**

**测试先行**（`tests/test_loop.py`、`tests/test_interactive.py`、`tests/test_modes.py`）：

1. `test_denied_tool_is_not_executed_but_result_is_backfilled` —— 工具没跑，
   但 `tool_call_id` 配对完好（D#41 同款不变量）。
2. `test_deny_reason_reaches_the_model` —— 理由在 tool 消息里，模型能据此换做法。
3. `test_ask_without_a_human_degrades_to_deny` —— once 模式（拍板问 1）。
4. `test_ask_in_repl_prompts_the_human` —— REPL 走 `ask_user_question` 通道，
   人选「允许」就真的执行。
5. `test_permission_decided_event_is_emitted`
6. `test_no_before_tool_call_preserves_old_behavior` —— 默认 None = 逐字不变。
7. `test_slash_permissions_lists_rules_with_source`
8. **注入验证（roadmap 硬要求）**：把 `decide()` 的求值顺序改成「allow 优先」，
   断言 Task 1 与 Task 3 的关键测试**确实变红**；还原后再绿。整段过程贴进 devlog。

**实现**：`run_agent(..., before_tool_call=None)`；`modes/` 两处装配；REPL 的 `/permissions`。

**验收**：+7 → **321 passed** 左右，`./test.sh` 全绿。

---

## 每 task 完成后必做

devlog 一条（目标 / 改动文件 / 红→绿真实数字 / 遗留）。
**交付前必须先写 `复盘.md`**（2026-08-10 立的规矩 8，含「我现在质疑什么」必答节，
`tests/test_docs_consistency.py` 强制）。全部完成后：全局 devlog 里程碑一行、
decisions 记四问取舍 + 「默认决策 allow」的安全代价 + 「前缀匹配防不住对抗」的官方原话，
STATUS 更新（数字有机器对账，忘改会红），遗留（符号链接双路径、环境运行器的洞、只读命令集未做）逐条进 TODO。
