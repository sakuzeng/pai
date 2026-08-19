# 08-20260810-storage-layout · 实施计划

4 个 task，严格 TDD（先红后绿，贴真实 pytest 输出）。基线：258 passed, 3 deselected。
分支 `feat/storage-layout`（自 `main` 开出）。每个 task 一条 devlog（逐条写，不攒最后补）。

---

## Task 1：`core/paths.py` —— 路径的唯一事实源

测试先行（`tests/test_paths.py`，新建）：

1. `test_slug_is_the_dashed_absolute_path` —— `/Users/x/proj` → `-Users-x-proj`（与 CC 同形）。
2. `test_slug_uses_the_git_root` —— 临时 `git init` 的仓库，两个子目录得到同一个 slug。
3. `test_slug_falls_back_to_cwd_outside_git`
4. `test_slug_keeps_chinese_path_as_is` —— 中文原样保留，不转义。
5. `test_known_slug_collision_is_documented` —— 把已知缺陷钉成测试：
   断言 `/a-b/c` 与 `/a/b-c` 确实撞成同一个 slug，docstring 写明这是与 CC 一致的
   已知取舍、TODO 已登记。这样将来有人「顺手修好」时会看见这条测试并读到理由。
6. `test_project_dir_layout` —— `~/.pai/projects/<slug>/`，其下 `memory/` 与 `sessions/`。

实现：`user_dir` / `project_slug` / `project_dir` / `memory_dir` / `sessions_dir`，
`_git_root` 从 `memory.py` 搬过来（自己往上找 `.git`，不起子进程）。

验收：258 → 264 passed（+6）。

## Task 2：`memory.py` 转调 paths（对外 API 不变）

测试先行：

1. `test_memory_dir_now_lives_under_the_readable_slug` —— 路径里含 slug、不含 16 位哈希。
2. `test_memory_module_keeps_its_public_api` —— `memory.memory_dir(cwd=, home=)` 签名与
   返回类型不变（`build_context` / `memory_tool` 的调用点不用改）。
3. 回归：`tests/test_memory.py` 里既有的「git 根归并」「非 git 回退」仍绿。

实现：`memory.memory_dir` 转调 `paths.memory_dir`；删掉 `memory.py` 里重复的 `_git_root`。

验收：+2 → 266 passed。

## Task 3：`SessionLog` 默认落用户目录（本轮最要紧的一条）

测试先行：

1. `test_session_defaults_to_the_project_sessions_dir` —— 不传 `directory` 时落
   `~/.pai/projects/<slug>/sessions/`。
2. `test_session_directory_param_still_works` —— 保留注入口（测试与将来的 `--session-dir`）。
3. `test_running_pai_does_not_create_sessions_in_cwd` —— e2e：在临时目录里跑一轮
   （fake client），断言该目录下没有 `sessions/`。这条是整个需求的初衷。
4. `test_memory_and_sessions_share_one_project_dir` —— 两者同居。
5. `test_every_record_carries_session_id_and_cwd` —— 每条记录都带 `sessionId` 与 `cwd`
   （08 之后不记 cwd 就是净信息丢失：同仓库不同子目录写进同一个目录）。
6. `test_same_second_sessions_do_not_collide` —— 同一秒建两个 SessionLog 得到两个文件，
   `sessionId` 各不相同（关掉 R#15 旧账）。
7. `test_filename_keeps_the_timestamp_prefix` —— `%Y%m%d-%H%M%S-<短 id>.jsonl`，
   于是 `ls` 仍按时间排序（与 CC 不同：CC 用纯 `<sessionId>.jsonl`）。

实现：`SessionLog.__init__` 默认参数从 `"sessions"` 改为 `None` 再在函数体里取
`sessions_dir()`——不能写成默认值直接调用（默认参数在函数定义时求值，
补漏五刚在 `history_path_for` 上栽过同款）。

验收：+7 → 273 passed。

## Task 4：装配层与可见性

测试先行：

1. `test_once_and_repl_use_the_new_session_location`
2. `test_slash_memory_shows_both_memory_and_session_dirs` —— `/memory` 要把会话目录
   也列出来：这次问题的起点就是用户不知道那些文件是什么、在哪。
3. `test_slash_memory_shows_the_readable_slug` —— 显示的是可读 slug 不是哈希。

实现：`once.py` / `interactive.py` 走 `paths`；`_show_memory` 增加会话目录一行。

验收：+3 → 276 passed 左右，`./test.sh` 全绿。

---

## 每 task 完成后必做

devlog 一条（目标 / 改动文件 / 红→绿真实数字 / 遗留）。全部完成后：
先写复盘再宣告交付（规矩 8，含「我现在质疑什么」必答节）；
STATUS 更新（数字有机器对账，忘了会红）；decisions 记两条：「slug 用全路径连字符、接受与 CC 同款的碰撞」、
「会话文件名保留时间戳前缀而非 CC 的纯 uuid」；遗留（slug 碰撞、history 仍用哈希）逐条进 TODO；
全局 devlog 里程碑一行。
