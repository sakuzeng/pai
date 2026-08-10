# 09-20260810-working-dir-boundary · 实施计划

6 个 task，严格 TDD（先红后绿，贴真实 pytest 输出）。
**基线：`329 passed, 3 deselected`**（feature 07 交付后）。
分支 `feat/09-working-dir-boundary`（自 `feat/07-permissions`——09 依赖 07 的
`permissions.py` / `hooks.py` / `gate.py`，07 合并进 main 之前只能从它开出）。
每个 task 一条 devlog，**STATUS 的测试数字每 task 同步**（07 的教训：
`test_status_reports_the_current_test_count` 拿实时 `testscollected` 对账，
攒到最后改会让中间几个 task 全程带一条红）。

顺序：工具自我声明 → 边界判定 → 兜底接线 → 符号链接 → 危险路径 → hook 复议 + 注入验证。
**Task 3 是行为变化的分水岭**（once 从「什么都能干」变成「cwd 内只读」），不许简化。

---

## Task 1：工具自我声明 `get_path` 与 `access`

**测试先行**（`tests/test_permissions.py`）：

1. `test_fs_tools_declare_path_and_access` —— `read_file` 是 `("read", path)`；
   `write_file` / `edit_file` 是 `("write", path)`。
2. `test_bash_declares_neither` —— **拍板问 2 的结构性落点**：bash 两个字段都是 None，
   所以它结构上就进不了边界判定，不是靠 if 判掉的。
3. `test_boundary_ignores_tools_without_declaration` —— 没声明的工具兜底走 allow。
4. `test_get_path_reads_the_declared_argument` —— 不是「第一个参数」而是**声明的那个**。

**实现**：`Tool` 加 `get_path` / `access` 两字段；`path_access_for(tool, access)` 装饰器
（与 `matcher_for` 同款，挂到已注册工具上，挂到没注册的工具当场抛）。

**验收**：329 → 333 passed（+4）。

## Task 2：边界判定核心（纯函数，先不接线）

**测试先行**（`tests/test_boundary.py`，新建）：

1. `test_path_inside_cwd_is_in_boundary`
2. `test_parent_directory_is_outside` —— **用户那句话的直接落点**。
3. `test_sibling_directory_is_outside`
4. `test_additional_directories_extend_the_boundary`
5. `test_boundary_uses_startup_cwd_not_current_cwd` —— 中途 `os.chdir` 不改变边界
   （照 CC 的 `getOriginalCwd()`）。
6. `test_all_paths_must_be_inside`（`.every` 语义，为 Task 4 的双路径铺路）
7. `test_prefix_is_not_enough` —— `/tmp/proj-evil` **不算**在 `/tmp/proj` 内
   （只比较字符串前缀会放行它，这是个真实的经典洞）。

**实现**：`core/boundary.py` —— `WorkingDirs`（启动 cwd + additional）、
`path_in_working_path()`、`paths_all_inside()`。纯函数，不碰 permissions。

**验收**：+7 → 340 passed。

## Task 3：兜底接线（**分水岭：行为在此改变**）

**测试先行**（`tests/test_permissions.py`）：

1. `test_default_is_now_workingdir` —— `RuleSet()` 的 `default_decision` 默认值变了。
2. `test_read_inside_cwd_allows`
3. `test_read_outside_cwd_asks` —— **验收标准第一条**。
4. `test_write_always_asks_even_inside` —— 照 CC，写没有目录放行那一步。
5. `test_bash_still_allows_and_this_is_the_known_hole` —— 把拍板问 2 承认的洞
   **写成测试固定下来**（07 的 `test_env_runners_...` 同款做法）。
6. `test_explicit_allow_preserves_feature_07_behavior` —— 向后兼容：
   显式 `default_decision="allow"` 时与 07 逐字相同。
7. `test_deny_and_ask_rules_still_win` —— D#46 求值顺序不受影响。
8. `test_once_degrades_boundary_ask_to_deny` —— 与 D#48 的交互，走 `gate.py`。

**实现**：`decide()` 的兜底分支；`RuleSet.default_decision` 默认值改 `"workingdir"`；
`decide()` 需要 `WorkingDirs`（新注入点，默认从启动 cwd 建）。

**验收**：+8 → 348 passed。**本 task 之后 once 的行为已变，devlog 要写明。**

## Task 4：符号链接双路径（关掉 feature 07 TODO#3）

**测试先行**（`tests/test_boundary.py` + 改 `tests/test_permissions.py`）：

1. **改写** `test_symlink_double_check_is_not_implemented` → `test_symlink_cannot_bypass_deny`。
   07 那条钉的是有洞行为，本 task 让它变红是**预期内的**，devlog 要贴出来。
2. `test_symlink_out_of_boundary_is_outside` —— 界内的软链指向界外 → 越界。
3. `test_working_dirs_are_resolved_the_same_way` —— CC 注释标的坑：
   不对称解析会造成**误拒**（macOS `/System/Volumes/Data/...`）。
4. `test_paths_to_check_computed_once` —— 白盒：断言 realpath 只算一次
   （CC 注释说不这么做是 30 次 syscall）。
5. `test_broken_symlink_does_not_crash`

**实现**：`get_paths_for_permission_check(path)`；deny/ask 规则对两条分别查；
边界判定要求两条都在界内。

**验收**：+4（1 条是改写）→ 352 passed。

## Task 5：危险路径清单（bypass 免疫）

**测试先行**（`tests/test_boundary.py`）：

1. `test_dangerous_files_are_blocked_even_with_allow_rule` —— **bypass 免疫的核心**：
   `default_decision="allow"` + `allow=["write_file(*)"]` 时写 `~/.bashrc` 仍被拦。
2. `test_git_hooks_are_protected` —— `.git/hooks/**` 是持久化位点。
3. `test_pai_settings_is_protected` —— 防 agent 改自己的权限规则
   （CC 的 `isClaudeSettingsPath` 同款）。
4. `test_reading_dangerous_files_is_not_blocked` —— 只挡**写**，读不挡
   （挡读会让 agent 连自己的配置都看不了）。
5. `test_deny_rule_still_takes_precedence` —— 内置检查排在 deny 桶**之后**、
   ask 桶之前，不能把 deny 降级成 ask。

**实现**：`boundary.py` 里 `DANGEROUS_WRITE_PATHS`；接进 `decide()` 的求值链。

**验收**：+5 → 357 passed。

## Task 6：hook 改 fail-closed（复议 D#50）+ 注入验证

**测试先行**（`tests/test_hooks.py`）：

1. **改写** `test_hook_timeout_does_not_block_work` → `test_hook_timeout_blocks`。
   07 那条钉的是 fail-open，本 task 让它变红是**预期内的**。
2. **改写** `test_hook_crash_does_not_block_work` → `test_hook_crash_blocks`。
3. `test_hook_cannot_be_started_blocks` —— 命令不存在同样 deny。
4. `test_non_blocking_exit_codes_are_still_non_blocking` —— **边界**：
   退出码非 0 非 2 是脚本明确表达的「没意见」，不是失败，语义不变。
5. `test_design_gate_stays_fail_open` —— `guards/design_gate.py` 的 fail-open
   **有测试钉住**，免得日后被「统一一下」误改（`tests/test_design_gate.py`）。

**注入验证**（roadmap 硬要求，至少两条）：

- 把 `path_in_working_path` 改成恒 `True` → 断言 Task 2/3 的关键测试变红；
- 把「写一律 ask」改成「写也走 `in_working_dir`」→ 断言
  `test_write_always_asks_even_inside` 变红；
- 把危险路径检查挪到 allow 规则**之后** → 断言 bypass 免疫那条变红。

三条注入的红字输出整段贴进 devlog（07 的做法）。

**验收**：+3（2 条是改写）→ **360 passed** 左右，`./test.sh` 全绿。

---

## 每 task 完成后必做

devlog 一条（目标 / 改动文件 / 红→绿真实数字 / 遗留）+ **STATUS 数字同步**。
**交付前必须先写 `复盘.md`**（规矩 8，含「我现在质疑什么」必答节，一致性测试强制）。
全部完成后：全局 devlog 里程碑一行、decisions 记
（默认姿态改 workingdir、bash 不参与边界与 CC 的差异、D#50 复议结论）、
STATUS 更新（模块表 + **已知缺陷第 0 条要改写**：不再是「不配置等于不存在」，
而是「bash 绕过边界」）、遗留逐条进 TODO。

**另需回头修的**：feature 07 的 TODO 第 1 条（首启无规则时告知全放行）
在本需求落地后**语义已变**——默认不再是全放行，该条应改写或关闭。
