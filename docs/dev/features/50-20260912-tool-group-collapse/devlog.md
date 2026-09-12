# 50-tool-group-collapse 开发日志

## 立档与拍板（2026-09-12）

用户截图 + 原话「优化一下这个界面，感觉当前的展开，收起有点不明显，不像claudecode这样的加深背景
（同时在执行结束之后会收起，显示执行了几条命令）」。读 CC 四处源码（清单见 README「需求」节与
K tui/cc-tool-group-collapse.md），三候选四问，用户「都可以照cc的来呢」→ 全按 CC：连续读搜看跑折组、
答案或写改文件断组；折叠 dim 无底色、展开块暗底（对应 CC 选中行）；展开一级铺全部；活轮次也只画
一行现在时 + `⎿` 提示。

## TDD（2026-09-12 → 09-13）

红：

```
E   ModuleNotFoundError: No module named 'pai.tui.groups'
1 error in 0.09s
```

改动：

- 新增 `src/pai/tui/groups.py`：`ACTIONS` 词表（顺序固定，照 CC）、`BREAKERS`、`is_collapsible`、
  `ToolGroup`（start / end / close / summary，`hint` 用 `statusline._preview`）、`group_entry`。
- `src/pai/tui/transcript.py`：`TranscriptEntry.invalidate()`。`src/pai/tui/theme.py`：`TOOL_BG`。
- `src/pai/tui/app.py`：`_group` / `_group_entry` 状态与 `_open_group` / `_close_group` / `_touch_group`；
  `on_event` 在 AssistantMessage 非空、AgentStart、AgentEnd、ToolStart（断组工具）处定格，
  ToolStart / ToolEnd（可折叠）进组；`ToolEnd` 断组工具走 `_tool_entry(expanded=name in EDIT_TOOLS)`；
  `_tool_entry` 展开块铺 `TOOL_BG`；`expand_last` 备用屏下切最近可展开条目；`replay` 走同一状态机
  （`!命令` 计成一条命令）；`clear_transcript` 清组；`_submitted` 空闲时定格挂着的组。
- 测试：`tests/test_tui_groups.py` 10 条；e2e 新增 1 条；`test_resume_replay` 3 处、
  `test_tui_alt_wiring` 1 处、`test_tui_mouse_realuse` 4 条改到组的契约（其中「单行结果不可展开」
  反转为「总是可展开且展开显示命令与输出」，理由写在测试里）。

第一轮绿后剩两类红：

1. `test_tui_mouse_realuse` 五条：都按「一条 ToolEnd = 一条可展开行」写，现在 ToolEnd 进组且组在
   AgentEnd 前是活跃态——第一版活跃组不接受展开，点了没反应。改成活跃组也可展开
   （CC 的 ctrl+o 对进行中的组同样生效，`(ctrl+o to expand)` 两态都带），再改测试契约。
2. e2e `until="(^O 收起)"`：两个 4000 字符的文件铺开一百多行，视口跟随末尾，摘要行被顶出屏幕。
   改等 AGENTS.md 截断尾部还看得见的一句。这暴露了一条真缺陷（展开长组后不知道怎么收），登记 TODO。

绿：

```
相关 10 个测试文件: 208 passed in 1.03s
e2e -k "collapse or resume": 3 passed, 18 deselected in 17.94s
全量（STATUS 更新前）: 1 failed, 1733 passed, 8 deselected in 195.76s（红的是测试数校验）
```

注入反证（都红、都恢复）：

```
拿掉 AssistantMessage 处的断组：E  AssertionError:   读了 3 个文件 (^O 展开) …（答案前后并成一组）
拿掉 AgentEnd 处的定格：        E  AssertionError: …（最后一组停在现在时，计数对不上）
```

已知缺陷 / 遗留：见 README「遗留问题」，每条已登记 TODO。
