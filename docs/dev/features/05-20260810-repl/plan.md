# 05-20260810-repl · 实施计划

7 个 task，严格 TDD（先写红测试、贴红输出，再实现、贴绿输出）。基线：`115 passed, 3 deselected`。
分支 `feat/repl`。每个 task 一条 devlog。

任务顺序按依赖排：事件 → 队列 → 中断内核 → bash 可杀 → loop 接线 → ask 工具 → REPL。
前 6 个 task 完成时 `once` 模式行为必须逐字不变；REPL 是最后一层组装。

---

## Task 1：`core/events.py` 事件流定型

测试先行（`tests/test_events.py`，新建）：

1. `test_render_text_matches_legacy_strings` —— 对每个事件构造实例，断言
   `render_text` 的输出逐字等于 loop 现在拼的字符串。基准串直接从
   `loop.py:103/105/114/130/182` 抄进测试当常量（这是「行为一字不变」的锚）。
2. `test_render_text_returns_none_for_silent_events` —— `AgentStart` / `TurnStart` /
   `AssistantMessage` 默认不打印，返回 `None`。
3. `test_tool_end_truncates_long_result` —— 结果 >200 字符时带 `…`，≤200 不带
   （现有行为：`result[:200]` + 条件省略号）。
4. `test_events_are_frozen_dataclasses` —— 事件是值对象，`dataclasses.FrozenInstanceError`。

实现：`@dataclass(frozen=True)` 定义 spec 表里 10 个事件 +
`AgentEvent = Union[...]`（3.9 运行期不认 `X | Y`，用 `Union`；文件顶 `from __future__ import annotations`
只解决注解不解决别名，这里必须写 `Union`）+ `render_text(event) -> Optional[str]`
用 `isinstance` 分派（3.9 无 `match`）。

验收：`115 passed` → `119 passed`（+4）。

## Task 2：`core/queue.py` PendingMessageQueue

测试先行（`tests/test_queue.py`，新建）：

1. `test_drain_all_takes_everything_and_empties`
2. `test_drain_single_takes_one_in_fifo_order` —— 入队 3 条，drain 三次分别拿到 1/2/3 条序。
3. `test_drain_empty_returns_empty_list` —— 不抛。
4. `test_clear_discards_pending`
5. `test_has_items_reflects_state`

实现：`QueueMode = Literal["all", "single"]`；`PendingMessageQueue` 持 `list[dict]`。
语义抄 pi（`agent.ts:123` 的 `drain` 两模式），代码独立写。

验收：`124 passed`（+5）。

## Task 3：`core/interrupt.py` 中断标志

测试先行（`tests/test_interrupt.py`，新建）：

1. `test_flag_set_is_set_clear_roundtrip`
2. `test_current_is_process_singleton` —— `set_current(f)` 后 `current() is f`。
3. `test_current_defaults_to_unset_flag` —— 从没注入时 `current().is_set()` 为 False
   （不能返回 None：调用方就得到处判空，工具里写不出干净代码）。

实现：`InterruptFlag` 包 `threading.Event`（未来 TUI/流式一定有线程，现在就选可跨线程的）。
模块级 `_CURRENT`，`set_current` / `current`。

验收：`127 passed`（+3）。

## Task 4：bash 工具可中断（改 `core/tools/shell.py`）

测试先行（追加进 `tests/test_tools.py`）：

1. `test_bash_normal_path_unchanged` —— 回归：普通命令输出、退出码提示、截断三条行为不变
   （现有测试已覆盖大半，补一条起独立会话后仍能拿到 stdout）。
2. `test_bash_returns_cancelled_when_flag_set` —— 预置已 set 的标志，跑
   `sleep 5`，断言秒回（`time.monotonic()` 差值 < 2s）且结果含「已中断」。
3. `test_bash_kills_process_group_not_just_child` —— monkeypatch `os.killpg` 记录调用，
   断言收的是 `os.getpgid(proc.pid)` 而不是 `proc.pid`；并注入反证：把实现改回
   `proc.kill()` 时本测试必须红（注入验证写进 devlog，抄 design_gate 的做法）。
4. `test_bash_keeps_partial_output_on_interrupt` —— 中断时已产出的输出不被抹掉
   （与超时分支 R3#3 同一条教训）。

实现：`subprocess.Popen(..., start_new_session=True)`；`while proc.poll() is None` 轮询
（`proc.communicate(timeout=0.1)` 拿部分输出会丢管道，改用非阻塞读或超时 `communicate` 后重试——
实现时以「拿得到部分输出」为准，取舍写 devlog）；命中中断 → `os.killpg(os.getpgid(pid), SIGKILL)`。
超时分支保持现状语义不动。

验收：`131 passed`（+4）。

## Task 5：loop 接线（事件 + 双队列 + 中断）—— 本轮唯一的破坏性改动

测试先行（改 `tests/test_loop.py` + 新建断言）：

1. 先把现有测试改红：现有对 `on_event` 的断言收到的将是事件对象而非字符串。
   改法是断言事件类型与字段（更强的断言），不是把事件 `str()` 回去凑合。
2. `test_once_output_is_byte_identical` —— 在 `tests/test_modes.py`：`run_once` 的
   `on_event` 收到的打印文本与改造前逐字一致（用 Task 1 的基准常量）。
3. `test_steering_injected_after_all_tool_results` —— 假 `get_steering_messages` 返回一条，
   断言它在 `messages` 里的位置在该轮所有 tool 消息之后、下一次请求之前
   （查 `FakeClient.requests[1]["messages"]` 的尾部顺序）。
4. `test_steering_not_called_when_no_tool_calls` —— 语义边界：steering 是「工具执行后」的挂点。
5. `test_follow_up_keeps_loop_running` —— 模型第一轮就给 `content`（本该返回），
   followUp 返回一条 → loop 继续跑第二轮；队列空后正常返回。
6. `test_follow_up_none_preserves_old_behavior` —— 不传两个参数时请求序列与改造前一致。
7. `test_interrupt_backfills_remaining_tool_calls` —— 配对不变量：一轮 3 个 tool_calls，
   在第 1 个执行后置中断标志，断言 `messages` 里仍有 3 条 `role="tool"`，
   后两条内容为「已取消」，且 `tool_call_id` 与 3 个 tc 一一对应。
8. `test_interrupt_returns_before_next_create` —— `FakeClient` 脚本只给 1 轮；
   若 loop 多调一次会 `AssertionError`（脚本耗尽），以此钉死「不再发请求」。
9. `test_interrupt_emits_interrupted_and_agent_end_reason`
10. `test_messages_param_continues_existing_conversation` —— 传入已有 `messages`
    不再重建 system/user 两条。

实现：`run_agent` 新增 keyword-only `get_steering_messages` / `get_follow_up_messages` /
`interrupt` / `messages`（全部默认 `None`）；5 处 `on_event` 改发事件；工具循环里每个 tc
之前查中断标志；`AgentEnd` 在四条返回路径（final / max_steps / budget / interrupted）各发一次。

验收：先跑出红（现有 loop/modes 测试失败数会明确贴进 devlog），再到 `141 passed`（+10）。

## Task 6：`core/tools/ask.py` AskUserQuestion

测试先行（`tests/test_tools.py` 追加）：

1. `test_ask_returns_asker_answer` —— 注入假 asker，断言返回其答案。
2. `test_ask_without_asker_returns_error_string` —— 不抛（工具错误不 throw）。
3. `test_ask_rejects_malformed_options_json` —— `options` 不是 JSON 数组时返回错误串。
4. `test_ask_schema_has_two_string_params` —— schema 由 `@tool` 生成，两个 string 参数。
5. `test_get_tools_excludes_ask_by_default` —— `once` 拿到的工具集不含它
   （无真人可问；REPL 显式加）。

实现：`ask_user_question(question, options)`；模块级 `set_asker`；
`get_tools()` 的默认集合排除它——实现时注意 `@tool` 是 import 即注册，
排除要在 `get_tools` 侧做（这条取舍写 devlog）。

验收：`146 passed`（+5）。

## Task 7：`modes/interactive.py` REPL

测试先行（`tests/test_interactive.py`，新建；输入源与 client 全注入，纯离线）：

1. `test_slash_exit_ends_loop`
2. `test_slash_clear_resets_messages_but_keeps_system`
3. `test_slash_status_reports_tokens_steps_breaker` —— 断言含估算 token 与压缩状态。
4. `test_slash_compact_triggers_manual_compaction` —— 假 client 扮演摘要模型。
5. `test_bang_runs_shell_without_calling_model` —— `!ls` 后 `FakeClient.requests` 为空，
   且命令与输出都进了 `messages`。
6. `test_backslash_continues_multiline_input`
7. `test_second_ctrl_c_on_empty_prompt_exits` —— 两级语义。
8. `test_history_dedupes_consecutive_duplicates` + `test_history_file_is_per_cwd`
9. `test_conversation_persists_across_turns` —— 第二轮请求的 messages 含第一轮内容。

实现：`run_interactive(*, client, model, reader, on_event, ...)`——`reader` 可注入
（默认 `input`），这是全套离线可测的关键；`readline` 只在真实交互路径挂载。
followUp 队列接真实输入；steering 传 `None`（REPL 无输入源，注释写明）。
`cli.py` 加分发：无 task 参数 → REPL。

验收：`155 passed` 左右（+9），`./test.sh` 全绿。

## Task 8：`modes/statusline.py` 工具调用状态行

2026-08-10 追加（来源与取舍表见 [README](README.md)「工具调用状态行」）。依赖 Task 1 的事件，
可在 Task 5 之后任意时点插入。

测试先行（`tests/test_statusline.py`，新建）：

1. `test_completed_tools_fold_by_name_with_count` —— 14 次 bash + 3 次 read_file 的事件序列
   → `✓ bash ×14 | ✓ read_file ×3`；只出现一次的不带 `×1`。
2. `test_running_tool_shown_first_with_arg_preview` —— 有未配对的 `ToolStart` 时它排在最前，
   带参数预览。
3. `test_truncates_by_terminal_columns_not_characters` —— 本 task 的核心断言：
   含中文的参数按列宽截断，`width=20` 时输出的显示宽度 ≤20（用
   `unicodedata.east_asian_width` 算 W/F 为 2 列）；用纯字符数截断的实现必然红。
4. `test_error_tool_gets_cross_mark` —— `is_error=True` 出 `✗`。
5. `test_no_color_when_not_a_tty` —— 非 tty 或 `NO_COLOR` 时不吐 ANSI 转义符
   （否则管道与测试输出全是乱码）。
6. `test_empty_events_render_empty_string` —— 不抛。

实现：`render_tool_line(events, width, *, color=False) -> str` 纯函数（不碰终端句柄）；
另有 `StatusLinePrinter` 用 `\r` + `\x1b[K` 原地刷新，只在真实 tty 上启用。
明确不做：并发多个进行中（pai 一次一个工具）、多行常驻区、鼠标。

验收：`161 passed` 左右（+6）。

---

## 每 task 完成后必做

devlog 一条（目标 / 改动文件 / 红→绿真实数字 / 遗留）。全部完成后：全局 devlog 里程碑一行、
decisions 记边界变更（core 不动作废）与两处取舍（进程级注入点、`TurnEnd` 不设）、
STATUS 模块表与测试数字更新、遗留逐条进 TODO。
