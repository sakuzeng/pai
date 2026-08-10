# 09-20260810-working-dir-boundary · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-11 · Task 1：工具自我声明 `get_path` 与 `access`

**目标**：目录边界要知道「这次调用碰哪个路径、是读是写」，而这只有工具自己知道。
延续拍板问 2 的「语义下放给工具」，**权限层不许按工具名分支**。

**改动**：
- `src/pai/core/tools/__init__.py`：`Tool` 加 `get_path` / `access` 两字段；
  新增 `PathGetter` 类型、`READ`/`WRITE` 常量、`participates_in_boundary()`、
  `path_access_for()` 装饰器
- `src/pai/core/tools/fs.py`：三件套各自声明（read 一个、write 两个）
- `tests/test_permissions.py`：+5 条
- `docs/dev/STATUS.md` 测试数字 329 → 334

**测试**：红 `5 failed, 29 passed`（`AttributeError: 'Tool' object has no attribute 'access'`），
绿 `34 passed in 0.38s`。
全量：`329 passed, 3 deselected` → **`334 passed, 3 deselected`**。

**比 plan 多写一条**（plan 说 +4 → 333，实际 +5 → 334）：
补了 `test_path_access_for_rejects_unregistered_tool`——与 `matcher_for` 同款的
「挂到没注册的工具上当场抛」。理由同 feature 07：默默不生效意味着一个工具
静默退出边界保护，而那正是最不该静默的地方。

**中间红了一次、且是该红的**：`test_status_reports_the_current_test_count`。
我按 plan 写的 +4 去改 STATUS（写成 333），实际是 +5（334），当场被机器对账逮住。
**这正是 07 立这条规矩时想防的**——plan 里的预估数字不等于实际数字，
靠人肉记会漂。

**「bash 进不了边界判定」是结构性的，不是 if**：`test_bash_declares_neither` 断言
`bash.access is None and bash.get_path is None and not bash.participates_in_boundary()`。
拍板问 2 的结论落在**工具没有声明**上，而不是权限层里一句
`if tool_name == "bash": skip`——后者会在加第五个工具时被人照抄成新的分支。

**一处 plan 没写但值得记的**：`get_path` 取的是**声明的那个参数**，
不是「第一个参数值」（默认 matcher 那套）。fs 三件套碰巧都是 `path` 打头，
写成「取第一个」现在也能过，但加第四个碰路径的工具时会静默取错参数。
`test_get_path_reads_the_declared_argument` 用 `edit_file(path, old, new)` 钉这条。

**遗留**：无（本 task 只加声明，未接线）。
