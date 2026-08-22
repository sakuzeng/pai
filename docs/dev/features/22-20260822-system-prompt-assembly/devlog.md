# 22-system-prompt-assembly · 开发日志

## 2026-08-22 · 用户指定「参照 CC」→ 走读 → 拍板 A → TDD 交付

目标：system prompt 从常量变装配（R4#E2），修掉「prompt 谎报工具集」。

改动：`core/loop.py`（`build_system_prompt` + `system_prompt` 参数）、
`modes/once.py`、`modes/interactive.py`（`_run_turn` / `_run_shell` 两处 +
`_dispatch_command` 里的 shell 调用点）；`tests/test_loop.py` 4 条、
`tests/test_modes.py` 2 条。

测试：红 `3 failed`（build 不存在 / 参数不存在）+ 装配判别一条红
（once 的三条内容断言对旧常量恰好全真，补「system != SYSTEM_PROMPT」判别
才红）→ 全绿 `117 passed`（loop+modes 两文件）。

遗留：CC env 段未抄（见 README 遗留）。
