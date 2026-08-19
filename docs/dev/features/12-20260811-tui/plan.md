# plan：12-tui —— 8 个 task，严格 TDD

档案：[README.md](README.md) ／ 需求与验收：[spec.md](spec.md) ／ 分支：`feat/12-tui`

规矩（AGENTS.md）：每个 task 先写测试跑红（贴红的输出），再写实现跑绿（贴绿的数字）。
不允许「先写实现，再补测试」。测试条数一律写下限——feature 09 复盘的教训：
把计划的估算当成「应该达到的事实」，会制造一场必然失败的对账。

---

## 动工前先解决的一个结构问题

读代码时撞见的，它决定了 task 顺序：

权限模式今天是「装配期常量」，运行时改不动。
`run_interactive` 里 `mode` 被直接烤进闭包：

```python
gate = make_before_tool_call(rules, hooks=hooks, tools=tools,
                             asker=human_asker, warn=out, mode=mode)   # ← mode 是值不是引用
```

`/mode` 与 shift+tab 要能切，gate 就必须读一个可变持有者而不是捕获的常量。
所以 T5 必须排在 T7 接线之前，且它动的是 `core/gate.py` 的签名——
属「只加不改语义」（阶段 2 的 D#38 已经把 core 的约束放宽到这一条）。

## 目录布局

一个阶段一个模块（AGENTS.md 架构约束），新建 `src/pai/tui/` 包：

```
src/pai/tui/component.py   Component 契约 / Container / CURSOR_MARKER
src/pai/tui/keys.py        原始字节 → 按键事件（纯函数）
src/pai/tui/editor.py      行编辑器组件
src/pai/tui/arbiter.py     输入归属仲裁 + 抑制语义
src/pai/tui/dialog.py      对话框组件（权限 ask / AskUserQuestion 合流）
src/pai/tui/dock.py        dock 的组件组合（活动区/队列区/输入行/状态行）
src/pai/tui/renderer.py    唯一碰终端的地方：raw mode、重绘、resize、复原
src/pai/modes/interactive.py  改成接线（主循环）
```

分层判据：`component/keys/editor/arbiter/dialog/dock` 全是纯函数或纯状态机，
离线可测且不碰终端；只有 `renderer.py` 写终端。这条边界是本轮可测性的全部来源。

---

## T1 · TUI 内核：Component 契约 + Container + dock 渲染器

目标：把「组件树 → 行数组 → 终端」这条路打通，dock 能画出来、能重画、能收缩。

红（≥8 条）
- `render(width)` 返回行数组；`Container` 按顺序拼接子组件的行。
- `invalidate()` 递归下发到所有子组件。
- 渲染器把 N 行 dock 画出来后，光标停在 dock 的最后一行（下一帧的相对移动基准）。
- 重画同样高度的 dock：只发相对移动 + `CSI 2K` + 内容，不发清屏、不发 `3J`。
- dock 变矮（5 行 → 2 行）：多出来的 3 行被清空后才收缩，屏幕上不留残影。
- dock 变高：新增行追加，dock 之上的内容（scrollback）字节不变。
- 每次写入整体包在 `\x1b[?2026h` / `\x1b[?2026l` 里。
- `commit(lines)`：把内容从 dock 上交到 scrollback——先清掉 dock，把 lines
  当普通输出打出去（于是它归终端拥有、永久留下），再在下面重画 dock。
  用户提交的那行输入、每条 assistant 消息、每次工具结果都走这个操作。
  测试要钉死：commit 之后再重画 dock 不会覆盖刚上交的内容。
- 注入反证：把「变矮时先清空」这一步删掉，`test_dock_shrink_leaves_no_residue` 必须变红。
- 注入反证：把 commit 里「先清 dock」删掉，上交的内容会与 dock 残影叠在一起，
  `test_commit_does_not_interleave_with_dock` 必须变红。

绿：`component.py` + `renderer.py` 的绘制部分。渲染器收一个 `write` 回调与
`width()/height()` 两个取尺寸的回调（依赖注入，测试传假的即可，AGENTS.md 架构约束）。
差量重绘不做（原则 4）：dock 每帧整体重画。

风险：dock 变矮是本方案最容易出错的地方——多出来的行一旦滚出 dock 就属于
scrollback，清不掉。测试要钉死「先清空再收缩」的顺序。

---

## T2 · 按键解析 + 行编辑器

目标：raw mode 下的字节流变成可测的按键事件，再变成编辑器状态。

红（≥14 条）
- 解析：可见字符（含中文多字节）、退格（`\x7f` 与 `\x08`）、方向键（`\x1b[A/B/C/D`）、
  Home/End（两组常见序列）、shift+tab = `\x1b[Z`、Ctrl+A/E/U/K/W、
  回车、Ctrl+C、Ctrl+D、Esc。
- 未识别的转义序列被丢弃，不得塞进输入框（否则用户按个 F5 就往输入里灌 `\x1b[15~`）。
- bracketed paste：`\x1b[200~…\x1b[201~` 之间的内容整体插入，其中的回车不提交。
- 多字节 UTF-8 被拆成两个 chunk 送达时能拼回一个字（真实终端会这样）。
- 编辑器：插入/退格/Delete、左右移动、Home/End、词跳、Ctrl+U/K/W 的边界情形。
- 光标列按 `display_width` 算：光标在「中文中文|abc」处时列号是 8 不是 4。
- `render(width)` 在光标处吐 `CURSOR_MARKER`，且该标记不占可见宽度。
- 历史 ↑/↓：读 05 已交付的历史文件，语义不变（按 cwd 分文件、连续重复只记一条）。
- 续行：行尾 `\` + 回车不提交，进入续行态。

绿：`keys.py` + `editor.py`。编辑器是纯状态机：`(state, key) -> state`，不做 IO。

风险：按键序列是长尾。只支持一组主流序列，其余丢弃并留一个调试开关
（`PAI_TUI_DEBUG_KEYS=1` 时把未识别序列打到 stderr），别装作全支持。

---

## T3 · 输入归属仲裁 + 抑制语义

目标：替掉「asker 与主循环共用一个 reader，谁先 `read()` 谁拿到」。

红（≥8 条）
- 仲裁函数：给定（输入框内容、最后按键时刻、待决对话框队列、用户是否主动唤出），
  返回谁拥有输入。
- 输入框非空 → 返回「编辑器」，待决对话框不弹。
- 输入框非空但距最后按键 ≥1500ms → 返回队首对话框。
- 输入框清空 → 立即放行（不等 1500ms）。
- 用户主动唤出的对话框不受抑制。
- 被抑制期间状态行显示「N 个请求在等」，且 N 正确（不许静默）。
- 时间由注入的 `now()` 提供，测试不 sleep。
- 注入反证：把「输入框非空即压住」这条删掉，抑制相关的测试必须变红。

绿：`arbiter.py`，纯函数 + 一个小状态对象。
1500ms 常量旁必须写明「从 CC `PROMPT_SUPPRESSION_MS` 抄来、依赖 CC 的使用节奏假设」
（TODO「给照抄来的常数建一条检查习惯」，与 `max_tokens=256` 那次同一种病）。

---

## T4 · 对话框：权限 ask 与 AskUserQuestion 合流

目标：兑现 spec G4 的铁证——提问期间敲命令必须当命令执行。

红（≥6 条）
- 对话框组件渲染问题 + 候选项 + 提示行；↑/↓ 选择、回车确认、数字键直选。
- Esc 取消：权限框 = 拒绝本次调用；提问框 = 取消回答（返回给模型的字符串要区分得开）。
- 铁证反例：提问期间输入 `!echo 我是命令`，执行 shell，不进答案。
- 铁证反例：提问期间输入 `/status`，执行命令，不进答案。
- 用户自己的话（既非命令也非序号）仍能作为答案交给模型——别把真人锁进选项里。
- 并发批里两个工具同时要问真人：排队逐个问，不允许两个框同时抢输入
  （`ask.py` 的注释已经点名这是同款根因）。

绿：`dialog.py`；`_make_asker` 从「读下一行 stdin」改为「往对话框队列塞一项并等它被回答」。

---

## T5 · 权限模式运行时可变 + `/mode` + shift+tab

目标：解决开头那个结构问题，并关掉 STATUS「两条待用户拍板」的第 2 条。

红（≥7 条）
- `make_before_tool_call` 接受可变模式持有者；改持有者后，下一次判定就用新模式
  （这条是整个 task 的要害，用一个先 `default` 后 `acceptEdits` 的双次判定钉死）。
- 轮转表：`default → acceptEdits → bypassPermissions（可用时）→ default`。
- `bypassPermissions` 不可用时被跳过，不是报错。
- `dontAsk` 不在轮转环里（D#53：它与「无真人」合流，不该出现在给真人按的键上）。
- 轮转表是数据不是 if 链，给 `plan` 留位（本档案问 2 的改判要求）。
- `/mode` 无参列出四态与当前态；带参切换；非法值给出可选清单。
- `/status` 与 `/permissions` 显示当前模式（顺带关掉 TODO 那条小修）。

绿：`core/gate.py` 签名从 `mode: str` 改为可变持有者（只加不改语义：
旧的传值调用要继续可用，once 不受影响）；轮转表放 `core/permissions.py`。

---

## T6 · 事件 → dock：活动区、并发可见、队列区、状态行

目标：让 dock 反映 loop 的真实状态，并关掉「并发在界面上完全不可见」。

参照实物（2026-08-11 用户给的 CC 截图，`evidence/` 已存档）：

```
● 写 plan 前先把要动的代码看清楚。          ← 已上交 scrollback
Reading 1 file, running 1 shell command…    ← 活动区：并发被压成一行「按动作计数」
  └ src/pai/modes/interactive.py            ← 明细行
✳ Hullaballooing… (16s · ↓ 536 tokens)      ← 状态行：转圈 + 已用时 + 本轮 token
› ▌                                          ← 输入行
```

turn 结束后这块塌缩成永久的一行 `✳ Cooked for 6m 48s` 留在 scrollback 里。

红（≥9 条）
- `ToolStart` 进活动区、`ToolEnd` 出活动区。
- 同一批并发工具同时在列（不是按顺序一个个冒出来）——这条直接对着 11 复盘质疑二。
  呈现形态照 CC：一行按动作聚合计数（「读 1 个文件，跑 1 条命令…」）+ 明细行。
  纯 pai 味的「一工具一行」也满足这条，但聚合形态在工具多时不会把 dock 撑高，选它。
- 状态行带转圈 + 已用时 + 本轮 token（`(16s · ↓ 536 tokens)`）。
  pai 已经有 usage 与预算数据，这是零新增数据源的一处白捡收益。
  时钟由注入的 `now()` 提供，测试不 sleep。
- `AgentEnd` 时把一行摘要 `commit` 进 scrollback（形如 `✳ 用时 6m48s · 12.3k token`），
  而不是清空了事——否则一轮跑完屏幕上什么痕迹都不留。
- followUp 队列非空时显示「已排队 N 条」，本轮结束后清零。
- 状态行显示当前权限模式 + 待决请求数。
- 拿真实会话轨迹当输入跑一遍事件序列（AGENTS.md：编的字符串测不出中文与
  `tool_calls.arguments` 这类真实坑），断言 dock 的行内容。
- 所有 dock 组件的输出宽度 ≤ 终端宽度（沿用 T1 的宽度守卫）。
- `AgentEnd` 后活动区清空。

绿：`dock.py`。若「`ToolEnd` 按原顺序交付」不足以呈现「谁先跑完」，
最小改动是给事件加时间戳（11 复盘质疑二本来就给了这个提示）——
不改线程模型（spec 非目标）。

---

## T7 · 接线：主循环换成 TUI

目标：`run_interactive` 从「阻塞 `input()`」换成「读按键 → 更新组件 → 重画 dock」。

红（≥7 条）
- 空闲态：输入回车提交，走原来的 `/命令` / `!shell` / 模型三条分支，语义不变。
- 提交的那行输入本身要 `commit` 进 scrollback（`› 继续`），不能只活在 dock 里——
  否则用户翻历史看不到自己问过什么。
- 干活期间按键进 dock 输入框（不是被吞掉）。
- 干活期间回车 → 进 followUp 队列，本轮结束后发出（拍板问 4）。
- 两级 Ctrl+C 语义保持（干活时置标志，空闲时两次退出）。
- 历史仍按 cwd 分文件、连续重复只记一条（05 语义不回退）。
- 跨轮状态（messages / 锚点簿 / 熔断 / 召回）仍由这一层持有，不回退。

绿：改写 `modes/interactive.py` 的主循环；`_read_line` / `_make_asker` 退役。

风险：这是回归面最大的一个 task。05 的 8 个 task 与后续五个补漏的成果都在这个文件里，
每一条既有语义都要有测试兜着才动。

---

## T8 · 终端生命周期与守卫

目标：spec G9 全部——退化、复原、resize、兜底、断言、fail-loud。

红（≥6 条）
- 非 tty 闸门：`stdout` 不是 tty 就整个不进 TUI，退回今天的行为（判 stdout 不判 stdin，与 CC 同口径）；顺带处理管道下的欢迎语与提示符噪音。
- resize：`SIGWINCH` 同步处理、同尺寸事件丢弃、只重画 dock、不清 scrollback。
- 异常兜底：主循环任何逃逸异常都回到提示符，`EOFError` 除外（Ctrl+D 正常退出）。
- 终端复原：正常/异常/信号三条退出路径都写回 disable 序列并显示光标
  （无条件发，不支持的终端上是 no-op——CC 的理由是终端能力检测不可靠）。
- 主线程断言：不在主线程时明确告警，而不是像今天这样静默退化为不可中断
  （05 遗留 `_install_sigint`）。
- 超宽 fail-loud：渲染行宽超终端宽即报错并指认是哪个组件。

绿：`renderer.py` 的生命周期部分 + `interactive.py` 的兜底层。

---

## 验收（对齐 [spec 的验收标准](spec.md)）

- `./test.sh` 全绿，新增测试不少于 40 条（本 plan 各 task 下限相加 = 67，
  下限就是下限，多出来不算超额，少了才要解释）。
- 至少一条测试拿真实会话轨迹当输入（T6）。
- 手工验收一条：中文 IME 候选框贴着输入光标——离线测不出，交付前请用户看一眼
  （基准线见 [evidence 手工清单](evidence/20260811-终端反向对照/手工清单.md)）。
- 交付前写 `复盘.md`（features/README 规矩 8），四问，其中「我现在质疑什么」必答。

## 刻意不做（与 spec 非目标一致，写在这里防止实现时手滑）

alt-screen / 主题 / 鼠标 · transcript 滚动与搜索 · plan 模式语义 · `Ctrl+R` ·
多行编辑器 · 差量重绘 · 改线程模型 · `/resume`。
其中 `Ctrl+R` 与 steering 不通电是拍板时就知道的功能回退，已登记 TODO。
