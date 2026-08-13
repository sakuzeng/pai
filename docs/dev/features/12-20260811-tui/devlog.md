# <NN>-<名称> · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## YYYY-MM-DD · <这一步做了什么>

**目标**：

**改动**：动了哪些文件。

**测试**：红→绿的真实 pytest 数字（贴实际输出，如 `3 failed` → `78 passed`），不写「都过了」。

**遗留**：已知缺陷/待办（同步登记全局 TODO）。

## 2026-08-11 前置精读 + 反向对照

**目标**：roadmap 阶段 2 的两个勾都是 REPL 半程的，TUI 半程一篇笔记都没有。补齐并做反向对照。

**动了哪些文件**：
- 新增 `knowledge/tui/pi-tui-main-screen.md`（绘制侧）
- 新增 `knowledge/tui/cc-input-ownership-and-modes.md`（输入侧）
- `knowledge/README.md` 登记表 +2 行
- `docs/dev/roadmap.md`：阶段 2 前置精读补两条 + 反向对照勾选项；新增头部「固定末项」一节；阶段 5 补勾；阶段 6/7 各补一行未勾
- 新增 `evidence/20260811-终端反向对照/`（6 个探针脚本 + 说明.md + 手工清单.md）
- `docs/dev/TODO.md`：反向作固定项那条划掉；steering 那条改写定性；新增「feature 12 前置发现」5 条

**读了什么**：pi-mono `tui-plan.md`(1001 行)、`tui.ts`(1223)、`tui-main-screen.ts`(552)、
`settings-manager.ts`/`interactive-mode.ts` 相关段；CC `REPL.tsx` 的 `getFocusedInputDialog`、
`getNextPermissionMode.ts`、`defaultBindings.ts`、`ink.tsx` 的 `handleResize`、
`use-input.ts`、`main.tsx` 的非交互判定、`utils/staticRender.tsx`。

**反向对照**（真 pty，`pty.fork()` + `TIOCSWINSZ`，不提交 prompt）：6 条见 evidence 说明。
最重的两条：① pai 对 resize 一个字节都不发；② 「干活时打的字」没丢、在内核 tty 缓冲区里，
**改写了 steering 那条遗留的定性**。

**测试**：`pytest tests/test_docs_consistency.py -q` → **10 passed, 1 skipped**。
（本步不动 src，无红绿；档案未拍板，design_gate 也不允许动。）

**已知缺陷 / 待办**：
- 三项纯视觉的项目我观测不到（本机无 tmux/pyte），留了手工清单待用户回填。
- 探针初版误让 `!sleep 3` 后的输入带回车、被当作新一行提交给了模型，产生了一次真实请求；
  发现后立即 kill 并改成不带回车。**如实留档**。

## 2026-08-11 brainstorm → spec 定稿

**目标**：候选方案 ≥2 个交用户拍板，拍完写 spec。

**开场做的一次前提校正**：用户定调「以 CC 为主」，但 CC 的渲染层（React reconciler +
Yoga + 虚拟滚动 + 行宽缓存）pai 复刻不了也不该复刻。值钱的是**行为层**——
输入仲裁/抑制语义/模式轮转/resize 策略/非交互闸门，这些在所有候选里都按 CC 定死，
不作为选项；要选的是架构轴。顺带发现 **CC 的主形态本身就是「底部活动区」**
（`staticRender.tsx` 注释：渲染成字符串再 print，已提交消息不再重渲染），
于是「以 CC 为主」与「方案 A」同向。

**三个候选**：A 底部活动区 / B 全帧持有 / C 双态（空闲 readline、干活期接管）。

**拍板**：四问一次拍完，用户四条全选推荐项——
A 方案、plan 不进本轮（对 09 拍板的改判）、对话框照抄 CC 抑制语义、干活时输入走 followUp。
完整问答（问题原文 + 每个候选的取舍 + 选择 + 理由）已原样存档进档案「确认」节。

**动了哪些文件**：档案 README（状态转「已拍板」+ 候选与确认全存档）、
新增 `spec.md`（9 个目标 / 8 条非目标 / 11 条验收 / 4 条已知风险）、
TODO（plan 那条就地记改判；新增「拍板后已知的功能回退」两条）。

**测试**：`pytest tests/test_docs_consistency.py -q` → **10 passed, 1 skipped**（本步不动 src；
skip 的是 STATUS 数字对账，只在 `./test.sh` 完整口径下跑）。

**刻意没做**：plan 模式语义、transcript 滚动/搜索、`Ctrl+R`、差量重绘、改线程模型。
其中 `Ctrl+R` 与 steering 不通电是**拍板时就知道的功能回退**，已登记 TODO 而非留到复盘。

## 2026-08-11 plan 定稿（8 task）

**目标**：把 spec 拆成带红→绿的 TDD task。

**动工前撞见的结构问题**（决定了 task 顺序）：权限模式今天是**装配期常量**——
`make_before_tool_call(..., mode=mode)` 把值烤进闭包，`/mode` 与 shift+tab 运行时改不动。
所以 T5（模式可变）必须排在 T7（接线）之前，且要动 `core/gate.py` 签名（只加不改语义）。

**目录布局**：新建 `src/pai/tui/` 包，分层判据是
**只有 `renderer.py` 碰终端，其余（component/keys/editor/arbiter/dialog/dock）全是纯函数或纯状态机**——
这条边界是本轮可测性的全部来源。

**8 个 task**：内核+dock 渲染器 / 按键+行编辑器 / 输入仲裁 / 对话框 / 模式可变+切换 /
事件→dock / 主循环接线 / 终端生命周期与守卫。各 task 测试条数写**下限**，相加 67，
验收线定 40。

**中途按用户给的 CC 实物截图改了 plan**（原图是对话里贴的、落不了盘，
evidence 存的是**转录**并已声明这一点）：补了四处 plan 原先没写的——
① `commit(lines)`：把内容从 dock **上交**到 scrollback 的操作（提交的输入、消息、
工具结果都走它），并配两条注入反证；② 并发的呈现形态改**照 CC 聚合计数**（工具多时
不撑高 dock），而非原写的「一工具一行」；③ 状态行带**转圈 + 已用时 + 本轮 token**
（pai 已有 usage，零新增数据源）；④ `AgentEnd` 时 **commit 一行摘要**进 scrollback，
而不是清空了事。

**测试**：`pytest tests/test_docs_consistency.py -q` → **10 passed, 1 skipped**（本步仍不动 src）。

## 2026-08-11 T1 · TUI 内核：Component 契约 + Container + dock 渲染器

**目标**：打通「组件树 → 行数组 → 终端」，dock 画得出、重画得对、收缩不留残影，
并做出 dock 与 scrollback 之间唯一的通道 `commit()`。

**先建了一个测试基建**：`tests/tui_screen.py`（最小终端模拟器）。
理由是前置反向对照卡住的那件事——本机无 tmux/pyte，**看得见字节看不见屏幕**。
而「变矮不留残影」「commit 不叠影」这类断言**在原始字节上没法验**：同一效果有多种字节
写法，断言字节等于把实现钉死。所以断言屏幕内容。模拟器自己也有 9 条测试
（它错了会让被测代码假绿，同 engineering/mutation-testing-pitfalls.md 那条）。
**它遇到不认识的转义序列直接 raise**——静默忽略会让测试对着「模拟器没看懂」的假象变绿。

**改动**：
- 新增 `src/pai/tui/__init__.py`、`component.py`（Component/Container/Text/CURSOR_MARKER）、
  `renderer.py`（DockRenderer：draw / commit / clear）
- 新增 `tests/tui_screen.py`、`tests/test_tui_screen.py`、`tests/test_tui_component.py`、
  `tests/test_tui_renderer.py`
- 改 `src/pai/modes/statusline.py` 的 `display_width`（见下）
- `docs/dev/STATUS.md` 测试数字 509 → 541

**红→绿**：
- 红：`2 errors during collection` — `ModuleNotFoundError: No module named 'pai.tui'`
- 绿：`541 passed, 3 deselected`（T1 新增 32 条：9 模拟器 + 6 组件 + 15 渲染器 + 2 宽度）

**撞出的一条真问题**：`display_width` **不剥转义序列**。今天状态行没暴露，是因为它
**先按可见文本截断再上色**，`display_width` 从来只拿到纯文本；而 `CURSOR_MARKER` 是
**嵌在组件文本里**的 APC 序列，不剥就把 8 个字符算成 8 列，硬件光标直接摆错列、
中文 IME 候选框跟着漂。pi 撞过同一件事（`utils.ts` 的注释就写着
"and APC sequences like CURSOR_MARKER"）。已改为剥 CSI/OSC/APC 三类，
并加了一条**回归护栏**钉死「既有调用方全传纯文本，剥转义不改变它们的结果」。

**三条注入反证**（各自打红了不同的测试，不是同一组）：
1. `total = max(len(lines), old)` → `total = len(lines)`（不清多余行）：
   `test_shrinking_dock_leaves_no_residue` + `..._cursor_on_new_last_line` **2 failed**
2. commit 里去掉 `self._erase()`（不先清 dock）：
   `test_commit_does_not_interleave_with_dock` + `..._scrolls_old_content_into_scrollback` **2 failed**
3. 光标不退回 dock 最后一行（`back = 0`）：
   `test_shrinking_dock_leaves_cursor_on_new_last_line` **1 failed**

**遗留**：
- `display_width` 现在住在 `modes/statusline.py`，而 tui 要用它，形成 tui → modes 的依赖
  （无环，statusline 不反向依赖 tui）。**T6 把状态行搬进 dock 时应把这个宽度原语一并
  挪进 tui 包**。已登记 TODO。
- 渲染器的前置条件「首次调用前光标在空行行首」判不了，只写进 docstring。

## 2026-08-11 T2-T8 · 一路做完

按用户「把能做的都做了」一次推完，每个 task 仍走红→绿。

**T2 按键 + 行编辑器**（17 + 28 条）：解码器**带状态**——真终端会把多字节字符与转义
序列拆成两次 read 送达（反向对照实测）。未识别序列**丢弃不塞进输入框**但留 `unknown`
事件供调试。编辑器是纯状态机 `(state, key) -> state`。
红：`ModuleNotFoundError: No module named 'pai.tui.editor'` → 绿：45 passed。

**T3 输入仲裁**（12 条）：本次要治的病的落点。照 CC——输入框非空即压住对话框，
停手 1500ms 放行，被压期间 `is_suppressing()` 可被问出来（**静默是最不能接受的**）。
1500ms 常量旁写明了它从 CC 抄来、带着 CC 的使用节奏假设。

**T4 对话框**（13 条）：**08 遗留那条铁证的反例进了测试**——提问期间敲
`!echo 我是命令` / `/status` 必须执行命令而非当成答案，靠 `handoff()` 交回主循环。

**T5 模式可变**（10 条 + test_modes 4 条）：解决动工前撞见的结构问题。
`PermissionModeState` 可调用，gate **每次判定现取**。
`MODE_CYCLE` 是数据不是 if 链，给 plan 留位；`dontAsk` 不在环里。
**第一版那条要害测试是假绿**（两次都断言 deny，换回捕获常量照样过），
改成 default→deny / acceptEdits→allow / 改回→deny 才真能鉴别；注入反证确认打红。

**T6 dock**（14 条）：形态照用户给的 CC 实物截图。并发**按动作聚合计数**。
状态行带转圈 + 已用时 + token。`AgentEnd` 吐一行摘要给 commit。
真实轨迹夹具从 `pai_playground/sessions/20260803-000946.jsonl` 抄进
`tests/fixtures/real_turn.jsonl`（剥 `ts`），顺带**修好了 STATUS 缺陷 6 那条断掉的溯源链**。

**T7 接线 + T8 生命周期**（19 + 12 + 6 条）：新增 `tui/terminal.py`（raw mode /
SIGWINCH 同步不去抖 / 无条件复原 / 非主线程告警）、`tui/app.py`、`tui/driver.py`；
`run_interactive` 加非 tty 闸门（判 **stdout**，与 CC 同口径）与主循环异常兜底。

**T1 漏了半条，T7 顶出来的**：渲染器当时**没实现 CURSOR_MARKER 的提取与硬件光标定位**，
标记被原样写进终端。补上「找标记 → 按 `display_width` 算可见列 → 剥掉 → 摆硬件光标」，
并把 `_to_top()` 的基准从 `height-1` 改成 `_cursor_offset`（光标停在输入行而非最后一行，
按最后一行算会让整块 dock 每帧上移一行）。补 4 条测试。

**真跑冒烟撞出一条离线测不出的**（`pai_playground/tui-probe/p5_tui_smoke.py`，真 pty
真 raw mode，不提交 prompt 不花钱）：**空闲时每 100ms 白刷一帧**——驱动醒来后无条件
重画。离线测试永远看不出，它们从不走超时那条路。加 `needs_tick()`：只有转圈与
「抑制到期」是随时间变的。启动帧数 25 → 2。

冒烟同时证实：中文光标列 `\x1b[7G` 正确、shift+tab 切模式、`/mode` 可用、
`!echo hi` 上交 scrollback、Ctrl+D 复原终端（`\x1b[?2004l\x1b[?25h`）。

**测试**：`./test.sh` → **680 passed, 3 deselected**（feature 12 新增 171 条，plan 下限 67）。

**遗留**：见档案「遗留问题」与 TODO。

## 2026-08-11 交付后修复波（用户真跑打回）

**背景**：宣告交付时 680 passed 全绿。用户在 `/tmp/paitest` 真跑，**当场打回三条**，
另提了四轮视觉要求。这一节记全过程——**它比前面八个 task 更值得回看**。

### 三条 bug，全在组件之间的接缝上

| bug | 接缝在哪 | 为什么 171 条测试没抓到 |
|---|---|---|
| **模型的回答完全不上屏** | `render_text(AssistantMessage)` 返回 `None`（契约是「流式已逐字打过，别重打」）↔ TUI 的 `on_event` 跳过 `MessageDelta`——**两边都以为对方会打** | 没有一条测试走完 delta→AssistantMessage 全链路 |
| **权限框卡死，退都退不出去** | `gate` 装配期捕获了 REPL 的 asker，TUI 只换了 `ask.set_asker`。老 asker 调 `input()`，而 raw mode 下 Enter 发 `\r` 不是 `\n` → 永远等不到行尾；`ISIG` 关了所以 Ctrl+C/D 只是普通字节 | 没有一条测试走「TUI 起来之后触发权限 ask」 |
| **排版满屏阶梯** | `render_text` 产出**多行字符串** ↔ `app.commit()` 假设**单行**，既不拆 `\n` 也不折行 → 终端自己折了，而 dock 按「我写了几行」记账 | 测试里 commit 的都是单行短字符串 |

**第二条尤其该记**：它与 T5 那条「模式是装配期常量」**是同一个病**，我刚修完一个，
转头就没想到 asker 也是。→ 已升格 [D#62](../../decisions.md) 与
[K engineering/injection-seams.md](../../../../knowledge/engineering/injection-seams.md)。

### 四轮视觉修正（每一轮都是用户看了截图才发现）

1. **「没有 TUI 的样子」**——我把 TUI 实现成了「底部两行光秃秃的 dock」。
   补分隔线 + footer（cwd / 模式 / 模型 / 上下文占用），取自 CC 与 pi 的共同视觉语汇。
   **根因是我 spec 只写了功能没写视觉层**，转录 CC 截图时只盯机制没看 chrome。
2. **`🤖` 渲染成方块**——emoji 字体缺字。全面换成文本呈现符号并加测试卡死
   （[D#63](../../decisions.md)）。顺带做了 logo 与流光动画。
3. **「一眼扫过去看不清用户的输入」**——第一版只换 glyph（看不出），
   第二版做成灰色（**方向错了**：工具行也是灰的，用户输入反而成了最不显眼的东西），
   第三版照 CC 做**整行背景色带**。层级定为 **用户 > agent > 工具**。
4. **bash 命令显示成 Python repr**（引号转义成 `\'`）——`gate` 用 `repr()` 拼参数。
   改成命令原样独占一行带 `$` 前缀，长参数截断。

### 用户拍板的一次分叉

用户提出三条需求（工具结果能点 / transcript 能滚 / 像新开一个窗口），
追下去发现**底下是同一个约束：谁拥有屏幕**，而方案 A 结构上做不到。
给了三条路（甲=键盘展开 / 乙=转 alt-screen / 丙=先甲再单独立项），
**用户选丙**：甲已交付（`^O` 展开被折叠的工具输出，连按往回走，历史有界 32 条），
乙另立 [features/13-alt-screen](../13-20260811-alt-screen/README.md)。

### 改动与数字

- 新增 `tui/theme.py`（配色与字形）、`tui/logo.py`（wordmark + 流光）
- 改 `tui/app.py`（答案上屏 / commit 拆行折行 / 工具结果折叠 / `^O` / 色带）、
  `tui/dock.py`（活动区照 CC 重做：圆点 + 单工具耗时 + 多行展开 + `$` 前缀）、
  `tui/dialog.py`（多行问题 / 权限与提问不同记号）、`tui/keys.py`（`^O`）、
  `core/gate.py`（asker 可变 + 问题可读化）、`modes/interactive.py`（接线）
- **680 passed → 747 passed**（新增 67 条）

**遗留**：见档案「遗留问题」与 TODO「用户真跑打回来的」一节。
