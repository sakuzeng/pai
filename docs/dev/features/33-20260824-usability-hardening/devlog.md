# feature 33 开发日志

## 2026-08-24 · 九个修复面 + README 刷新（逐条 TDD）

代码面（每条：修前红 → 绿；序号对档案验收项）：

1. 折行点击定位（21 遗留 1）：`editor._display_rows` 与 render 共用一套
   折行几何（`_room` 抽出双用），新 `point_at_display(row, col, width)` 按
   显示行换算；app 两个调用点换用，且不再预减 prompt 宽——续行前缀不等宽
   是旧换算的第二处病。红 3 条（ASCII 折行 / 中文宽字符 / 续行前缀）。
2. 粘贴自愈提示（19 遗留 2）：解码器自愈时多吐 `Key("paste_recovered")`，
   app 收到 `dock.set_notice(...)`；editor 不认识该名字原样忽略。
   既有自愈测试改判两个键（修前红）+ app 提示测试 1 条。
3+5. `/permissions` 说全真话（09 遗留 1 提示半边 + 遗留 3）：
   `boundary.dangerous_writes_description()`（与 `is_dangerous_write` 同源）
   + `_show_boundary_caveats`（bash 边界洞 D#52 + 危险写清单），有规则/无规则
   两分支都出——新用户恰好走无规则分支。红 1 条。
   「首启」原意的一次性 banner 刻意不做：读过即丢，双通道（/permissions +
   README）随时可查、更可复核。
4. once 的 defaultMode 告警（09 遗留 2）：`RuleSet.mode_source` 记来源文件，
   once 未显式传模式且配置了非 dontAsk 模式时告警一次（含出路）。
   行为刻意不变：配置的 bypass 在 once 仍不生效——旧 settings 静默提权
   比静默降权更糟。红 1 条 + 反向守卫（没配就一个字不提）。
6. MCP 根级非对象 schema（29 复核 R6，「健全」指示提前解除「等真撞到」）：
   桥接层 warn + 跳过该工具；缺 schema 仍走兜底空对象。红 1 条（四形态）。
7. 超高 dock（21 遗留 3）：`DockRenderer` 收 rows 提供者，钳到
   「终端高度 - 1」保尾部（输入行/状态行在底部）；不传不钳。实况确认：
   逐行 `\r\n` 超屏高会让终端滚动、相对上移指进 scrollback，整块漂移。
   红 1 条 + 界内不动守卫。
8. ↑/↓ 显示行移动（21 遗留 2，CC 同款语义）：`_cursor_vertical` 按最近一次
   render 的宽度取显示行结构，目标列取当前视觉列；非末段行尾收在段末前一
   字符（那个位置视觉上属于下一行——render 插标规则决定的，测试注明取舍）；
   首/末显示行才翻历史；没渲染过退回旧行为（纯 REPL 注入路径）。红 4 条。
9. `additionalDirectories` 首次接线（盘点时抓到的「文档声称、实际没接」）：
   boundary docstring 与 STATUS 都说有这个配置键，装配层从没读过——配了
   静默不生效。`settings.additional_directories`（~ 展开、非法 warn 忽略）
   → assembly 并进 `WorkingDirs.additional`。红 4 条（解析 3 + 接线 1）。

文档面：README 全面重写——旧版「已知缺口」还写着没有 skills/MCP/--resume/
alt-screen（全部早已交付）、测试数字停在 1069、结构表列着不存在的
`mcp_client.py`。新版覆盖：CLI 全参数、REPL/TUI 全命令与键位、权限四模式表
与两句真话、settings.json 全键参考（含本 feature 新接的三个键）、skills 与
MCP 配置方法、数据布局、test.sh/eval.sh、真实的已知问题段；README 不再抄
测试数字（抄了必漂，指向 STATUS 的机器对账）。

红→绿数字：新增 18 条测试，全量 `1395 passed, 3 deselected`；
四套功能冒烟（skills/MCP/权限/会话，28 场景）复跑全过。
