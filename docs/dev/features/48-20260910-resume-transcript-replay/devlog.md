# 48-resume-transcript-replay 开发日志

## 排查（2026-09-10）

用户原话「我使用resume并不能恢复对话状态」。只查不改，结论进需求池当日条目：
读盘重建链路正常、模型侧通（e2e 只断言 provider 收到历史）；屏幕侧 `_run_tui` 的
`Transcript()` 空建、无人遍历 `messages`；恢复提示走 print 在进备用屏（`2J`）前打出即被盖掉。
用户机器上 13:37 / 13:39 两个带 parentSession 的文件是证据，13:39 那次恢复后一个字没敲就退了。
顺带发现提示语「system prompt 都按当前环境重新装配」不属实（`run_agent` 只在 messages 为空时
造 system，`_inject_instructions` 见旧指令消息就跳过）。

## 立档与拍板（2026-09-10 → 09-11）

档案立于 09-10，三个候选四个问题。09-11 用户问「cc是怎么做的呢，按cc的来吧」→ 读 CC 2.1.88
反编译源码八处（清单见 README「确认」节与 knowledge/tui/cc-resume-rendering.md），四问全对应
候选 A，其中问 2 的 `!命令` 细节按 CC 修订为「命令行 + 输出折叠」。

## TDD（2026-09-11）

红：

```
E   ModuleNotFoundError: No module named 'pai.modes.resume'
1 error in 0.51s
```

```
>           assert "已恢复会话" in screen, f"恢复提示要在屏幕上：\n{screen}"
E           AssertionError: 恢复提示要在屏幕上：
1 failed in 6.13s
```

改动：

- 新增 `src/pai/tui/history.py`（回放项类型 + `user_entry` / `compacted_entry`）、
  `src/pai/modes/resume.py`（`history_items`：消息 → 回放项，纯函数）。
- `src/pai/tui/app.py`：`TuiApp.replay(items)`；`_submitted` 改用 `user_entry`；
  `_remember_collapsed` 从 `on_event(ToolEnd)` 抽出供两处用。
- `src/pai/modes/interactive.py`：恢复的消息改在装配之后入 messages，先经 `_refresh_assembly`
  换 system、丢旧指令；`_run_tui` 收 `resumed` / `resume_note`，logo 与提示行之后回放、再 commit
  恢复提示；REPL 路径仍 print。
- `src/pai/modes/commands.py`：`shell_echo` / `split_shell_echo`（`!` 回显格式正反一处）；
  `src/pai/core/session.py`：`SUMMARY_HEADER` 常量；`src/pai/tui/theme.py`：`COMPACTED = "✻"`。
- 测试：`tests/test_resume_replay.py`（9 条）、`tests/fixtures/resume_session.jsonl`（真实轨迹）、
  e2e `test_resume_carries_the_conversation_into_a_new_process` 改查 `screen_text()`、
  `test_modes.py::test_resume_continues_the_previous_conversation` 的「保留原 id」改为
  对话消息保留原 id（system 是新内容新 id）、`test_tui_theme.py` 的字形表加 `COMPACTED`。

第一轮绿后剩三条红，两条是我的假设错：

1. 真实会话里一条最终回答都没有——我以为 37 条里至少有一条答案。查 events 流：整段是一次
   run（`AgentStart` 一条），第二问「现在在做什么呢」是干活时插进去的（`SteeringInjected`），
   run 在第 12 步被用量预算掐断（唯一的 `AgentEnd`，reason=budget）。断言改为「零答案」，
   答案条目的渲染改由合成测试盯。我在注释里第一版写成「两条 AgentEnd 都是 budget」，
   复核 events 后改成实情。
2. `test_resume_continues_the_previous_conversation` 断言重录保留全部原 id，与拍板问 3·A
   （system 换成当前装配的、按新 id 录）冲突。改为对话消息（user/assistant/tool）保留原 id、
   新文件里恰有一条 system。

绿：

```
tests/test_resume_replay.py tests/test_modes.py: 48 passed in 0.69s
tests/test_e2e_tui.py::test_resume_carries_the_conversation_into_a_new_process: 1 passed in 6.58s
```

全量（STATUS 更新前）：`1 failed, 1703 passed, 8 deselected in 184.52s`——唯一红的是
`test_status_reports_the_current_test_count`（STATUS 还写着 1694）。更新 STATUS 后复跑数字见 README。

注入反证（都红、都恢复）：

```
拿掉 app.replay：      E  AssertionError: 旧对话要回放上屏（照 CC）：   1 failed in 6.28s
拿掉 _refresh_assembly：E  assert ('STALE' not in '旧的 system prompt STALE'
```

已知缺陷 / 遗留：见 README「遗留问题」，每条已登记 TODO。
