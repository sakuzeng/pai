# 49-resume-same-file-and-slash-resume 开发日志

## 立档与拍板（2026-09-11）

用户在 48 交付回复后提「我想追加同一文件呢。并且在命令/resume 下能够恢复对话呢」→ 需求池 →
立档案、三组候选四个问题 → 用户「照cc的吧，先合48」。先把 `feat/48` 以 no-ff 合回 `main`
（merge cfed4e0）并推送 main 与 48 分支，再从 main 切出本分支。

## TDD（2026-09-11）

红：

```
E   ImportError: cannot import name 'ConversationResumed' from 'pai.core.events'
1 error in 0.09s
E       AssertionError: 照 CC：追加同一文件，不新建
E       assert 2 == 1                      (test_modes::test_resume_continues_the_previous_conversation)
```

改动：

- `core/session.py`：`SessionLog.switch_to(path)`（就地接管：id / cwd / `_last_id` 取物理尾部 /
  不再写 header）与 `open_existing(path)`。
- `core/trace.py`：`EventTrace.path` 改成按 session 当前路径算的 property。
- `core/events.py`：`ConversationResumed(session_id, kept)`，进 `AgentEvent` 与 `CONTEXT_REWRITING`。
- `modes/resume.py`：`load_conversation` / `refresh_assembly`（从 interactive 搬来并加「指令没变不重录」）/
  `resume_note` / `recent_sessions` / `switch_conversation` / `resume_command`。
- `modes/commands.py`：`/resume` 分支（延迟 import 避免与 resume 模块互相 import）、HELP、
  `_handle_command` 多收 `skills_catalog` / `instructions` / `asker` / `on_switched`。
- `modes/interactive.py`：启动 resume 默认 `SessionLog.open_existing`，`--fork-session` 走原路径；
  REPL 与 TUI 三处 `_dispatch_command` 补 asker / instructions / on_switched；TUI 的 `on_switched`
  = `app.clear_transcript()` + `app.replay(...)` + `refresh_context()`。
- `tui/app.py`：`clear_transcript()`。`cli.py`：`--fork-session`（无 `--resume` 报错）。
- `viz/collect.py` / `viz/flow.py`：新事件的源码位置与时间线分隔。`README.md`：两处文档。
- 测试：`tests/test_resume_switch.py` 15 条；`test_modes` 接力测试改成同一文件语义；
  `test_trace` 样本表加新事件；e2e 现有接力测试补「只有一个文件」，新增
  `test_slash_resume_switches_the_screen_to_the_other_conversation`。

第一轮绿后两条红：

1. `test_trace::test_every_event_type_is_covered_by_samples`——加了事件没加样本，这条测试就是为此立的。
2. e2e `/resume`：选择框里发了 "1" 没发回车。对话框提示语写「数字直选」，实现是输入序号后回车；
   用 pty 复现打出原始输出才看见 `   1` 挂在输入区。测试改成 `"1\\r"`；提示语与行为不符登记 TODO。

绿：

```
tests/test_e2e_tui.py -k resume:  2 passed, 18 deselected in 13.97s
相关单测 8 个文件:                  182 passed, 1 skipped in 1.08s
全量（STATUS 更新前）:              1 failed, 1719 passed, 8 deselected in 190.00s
```

注入反证（都红、都恢复）：

```
拿掉 on_switched 里的 clear_transcript：E  AssertionError: 切换前的对话不该还在屏上   1 failed
拿掉 switch_conversation 发 ConversationResumed：
    test_slash_resume_switches…       E  assert False（events 里没有该事件）
    test_slash_resume_lets_recall_come_back  E  assert '记忆正文在此' in …   （召回没回来）
接管时把 _header_written 置回 False：   5 failed, 10 passed（header 被重写、字节不变那条等全红）
```

已知缺陷 / 遗留：见 README「遗留问题」，每条已登记 TODO。
