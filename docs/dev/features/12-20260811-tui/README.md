# 12-tui
状态：已交付
分支：`feat/12-tui`（立项、前置精读与反向对照、实现）
流程：superpowers 全链路（brainstorm → spec → plan → 8 task SDD → 合并 → tag `tui-v1`）

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

阶段 2 的**后半程**：把 `modes/interactive.py` 的纯 REPL 换成 TUI（终端 UI 层），
让「一个输入流两个消费者」「干活时能打字」「模式看得见也切得动」这几件在纯 REPL 里
结构上做不出来的事有个家。前半程 REPL 见 [features/05](../05-20260810-repl/README.md)（已交付，
tag `repl-v1`），本档案**不改写它**，是在它之上另起一次交付（features/README 规矩 7）。

阶段 2 的四条 TUI 设计原则**已在 roadmap 拍板，本轮不重议**（见
[roadmap 阶段 2](../../roadmap.md)）：
`Component.render(width) -> list[str]` 纯函数契约 / 只做 main-screen 不假装 sticky /
CURSOR_MARKER 零宽标记定位硬件光标 / 差量重绘后置。

### 已知必须进范围（两条，TODO 里明确标着「留 TUI 阶段」）

1. **模态输入**——asker 与 REPL 抢同一个输入流。实际发生过 `!echo 我是命令` 被当成了
   对问题的回答；当时只做了缓解（空行跳过、`/exit`、`/命令` 提示后重读），
   TODO 原文写明「不该在 REPL 阶段继续打补丁」。出处：TODO「feature 08 遗留」第 1 条。
2. **`/mode` 命令与 shift+tab 权限模式切换**——feature 09 拍板留给 TUI。
   现在换模式只能重启 pai 加 `--permission-mode` flag。
   出处：TODO「feature 09 遗留」+ STATUS「两条待用户拍板」第 2 条。

### 待评估是否一并解决（各自给结论，不默认都做）

- **steering 无真实输入源**（05 遗留）：要的是独立输入线程或非阻塞 stdin。
- **plan 模式**（09 遗留，拍板「留 TUI 阶段连交互一起做」）。
- **`_install_sigint` 在非主线程装不上**（05 遗留）：TUI 的线程模型直接决定它踩不踩。
- **REPL 主循环兜一层「任何异常都回提示符」**（06 遗留，同类问题已出现三次）。
- **05 复盘质疑二**：状态行不该默认改变已交付功能的输出形态。
- **并发在界面上完全不可见**（11 遗留）：事件全在主线程发、`ToolEnd` 按原顺序交付。
  TUI 是它唯一的落点。

### 验收标准

待 brainstorm 拍板后写进 spec.md。

## 候选方案与确认

<!-- ≥2 个候选 + 取舍；只有一个方案等于没讨论。
     拍板问答完整存档（规矩 6）：问题原文、每个候选及其取舍描述、选择、理由，
     原样落盘不压缩。多轮拍板就多个「问 N」小节。 -->

**前提校正（brainstorm 开场）**：用户定调「以 CC 为主」。但 CC 的渲染层是
React reconciler + Yoga 布局 + 虚拟滚动 + 行宽缓存，pai 复刻不了也不该复刻。
**CC 真正值钱的部分在行为层**——输入归属仲裁、抑制语义、模式轮转、resize 策略、
非交互闸门。这些在所有候选里都按 CC 定死，不作为选项。要选的是**架构轴**：
前置精读撞出的岔路口「持有整份文档 vs 只管底部活动区」。

顺带一条：**CC 的主形态其实就是「底部活动区」**——`utils/staticRender.tsx` 的注释
写明它把组件渲染成字符串再 print 到 stdout（因为 Ink 不支持一棵树里多个 `<Static>`），
已提交的消息进 scrollback 就不再重渲染；只有可选的 fullscreen/transcript 模式才是全帧。
所以「以 CC 为主」与「方案 A」是同一个方向。

### 方案 A · 底部活动区（CC 主形态的最小复刻）

transcript 继续 print-and-forget 直接进 scrollback；TUI 只接管屏幕**底部若干行**——
输入框、工具状态行、权限/提问对话框、模式指示。全程 raw mode，相对光标移动 +
`\x1b[2K` 重绘 dock，dock 高度之外一律不碰。

- **对**：不持有整份文档，渲染成本与内存恒定；scrollback 归终端，**永远不清**；
  已交付的 transcript 输出形态一个字不变（正面关掉 05 复盘质疑二）；resize 只重画 dock。
- **代价**：**readline 没了**，行编辑要自己写（插入/删除、左右/词跳、Home/End、
  Ctrl+U/W/K、历史上下、中文宽度感知的光标定位、bracketed paste）。
  05 交付的历史机制要重接，`Ctrl+R` 增量搜索自己写不便宜。
- **做不了**：transcript 内滚动/搜索（CC 的 Ctrl+O）。

### 方案 B · 全帧持有（CC fullscreen 形态）

pai 持有整份消息文档，每帧重渲染 + 行数组 diff，宽度变化全量重绘。

- **对**：能做 transcript 滚动、搜索、消息回溯重渲染，是真正的「界面」。
- **代价**：**resize 要清 scrollback 再重画**（pi 的 `\x1b[3J`）——只有持有全文档
  才敢清；渲染成本随会话线性增长，要配虚拟滚动才压得住；把 pai 的输出形态整个换掉，
  once/管道路径全要重新处理。CC 为此付的是 Yoga + reconciler + 虚拟滚动 + 缓存四层。

### 方案 C · 双态（空闲 readline / 干活期接管）

空闲时维持现状（readline 白送历史/行编辑/IME），一提交任务就进 raw mode 画 dock，
任务结束退回 readline。

- **对**：绕开自写行编辑器这个最大成本，改动面最小。
- **代价**：**两套输入路径**。而这正是本次要治的病——「一个输入流两个消费者，
  谁先 `read()` 谁拿到」换个形式活下来了，只是从 asker-vs-REPL 变成 readline-vs-dock。

### 确认

四问一次拍完，用户四条**全部选了推荐项**。原样存档：

**问 1**：TUI 架构走哪条？（这条决定后面所有取舍）
- 候选 A·**底部活动区**（推荐）：transcript 继续直接进 scrollback，TUI 只接管底部 dock。
  全程 raw mode，行编辑器自己写。最贴近 CC 主形态，scrollback 永不被清，
  已交付输出形态不变。代价是 readline 没了、Ctrl+R 要自己实现。
- 候选 B·**全帧持有**：持有整份文档，每帧重渲染 + 行数组 diff，能做 transcript
  滚动与搜索。代价是 resize 要清 scrollback 再重画、渲染成本随会话增长需配虚拟滚动、
  once/管道路径全要重做。
- 候选 C·**双态**：空闲用 readline，提交后进 raw mode 画 dock，任务结束退回。
  改动面最小、绕开自写行编辑器。代价是两套输入路径——正是本次要治的病换个形式活下来。

**选择**：**方案 A**。理由：用户定调「以 CC 为主」，而 A 就是 CC 的主形态；
C 省下的成本是真的，但它保留病根（交接点就是 bug 的家，asker-vs-REPL 变成
readline-vs-dock）；B 的代价（清 scrollback、虚拟滚动）这个阶段付不起，
且它解决的问题（transcript 滚动）不在阶段 2 范围里。

**问 2**：plan 模式进本轮范围吗？（feature 09 拍板「留 TUI 阶段连交互一起做」，我提出反悔）
- 候选 A·**不进，单独立项**（我的建议）：TUI 只提供「模式能切」+「能弹对话框」两个能力，
  给 plan 留出位置。plan 的语义（工具白名单 + ExitPlanMode 确认流）是权限层与工具层的活。
- 候选 B·**进，按 09 原拍板一起做**：模式轮转从第一天就完整，不留半成品；
  代价是本阶段范围明显变大，且要同时动权限层与工具层。

**选择**：**不进，单独立项**。这是对 [feature 09 拍板的一次改判]，
理由与 09 当时的假设不同：读完 CC 源码后确认 plan 的实质不在交互层。
**要求**：模式轮转必须给 plan 留位，且这条改判要在 TODO 原条目上就地留痕。

**问 3**：对话框（权限/AskUserQuestion）与用户输入抢的时候，谁赢？
- 候选 A·**照抄 CC**（推荐）：输入框非空即压住所有对话框，停手 1500ms 才弹，
  被压期间输入框下方显式提示「N 个请求在等」。用户主动打开的选择器不受压制。
- 候选 B·**对话框抢焦点，Esc 取消**：即 TODO 里原先记的做法（那条是从官方文档推的，
  源码里 CC 并非如此）。没有延迟、语义简单，代价是打到一半被打断。
- 候选 C·**压住但不设时限**：去掉 1500ms 这个抄来的常数，直到用户清空输入或主动唤出。
  代价是用户打了半行走开，请求就一直悬着。

**选择**：**照抄 CC**。（注：1500ms 是抄来的常数，按 TODO「给照抄来的常数建一条检查
习惯」那条，常量旁必须写明它从哪来、依赖什么前提。）

**问 4**：agent 干活时打的字回车后怎么处理？（pai 的双队列两者都支持）
- 候选 A·**排队，本轮结束后发**（CC 行为，推荐）：进 followUp 队列，
  dock 显示「已排队 N 条」。语义简单，不打乱正在进行的工具调用。
- 候选 B·**立即插队发给模型**（steering）：在下一个步边界注入当前对话，
  真正的「边跑边指挥」。代价是打断正在进行的推理。
- 候选 C·**两者都要，按前缀区分**：默认排队，某个前缀表示立即插队。
  代价是多一条要记的语法，且前缀会与已有的 `!` shell 模式打架。

**选择**：**排队，本轮结束后发**（followUp）。

（够格全局复用的取舍升格进 ../../decisions.md 并在此互链——待实现阶段产生。）

## 结果与总结

**阶段 2 后半程交付**：`pai` 在真 tty 下进 TUI——上面是终端 scrollback，
下面是 pai 接管的 dock（活动区 / 队列区 / 输入行或对话框 / 状态行）。
非 tty（管道、CI、注入 reader 的测试）**整个不进 TUI**，行为与今天一个字不变。

八个 task 全部走红→绿：内核+dock 渲染器 / 按键+行编辑器 / 输入仲裁 / 对话框 /
模式可变+切换 / 事件→dock / 主循环接线 / 终端生命周期与守卫。
详细日志见 [devlog.md](devlog.md)，方案见 [spec.md](spec.md) 与 [plan.md](plan.md)。

**关掉的欠账**：

| 欠账 | 出处 | 怎么关的 |
|---|---|---|
| asker 与 REPL 抢同一个输入流 | 08 遗留（有真实事故） | `InputArbiter` 算归属；提问期间 `!`/`/` 经 `handoff()` 交回主循环执行，铁证反例进了测试 |
| `/mode` 与 shift+tab 未做 | 09 遗留 + STATUS 待拍板 2 | `PermissionModeState` 可变持有者 + `MODE_CYCLE` 数据表 |
| steering 无真实输入源 | 05 遗留 | **只关一半**：干活时打字通了（进 followUp），立即插队没通（拍板选的是排队） |
| 并发在界面上完全不可见 | 11 遗留 | dock 活动区按动作聚合计数 |
| REPL 主循环没兜异常 | 06 遗留（同类第三次） | 主循环兜底 + TUI 侧同款，`EOFError` 不吞 |
| 状态行改变已交付输出形态 | 05 复盘质疑二 | 方案 A 天然关掉：transcript 形态不变，状态行进 dock |
| `_install_sigint` 非主线程静默失效 | 05 遗留 | 结论是**不挪子线程**；`TerminalSession.start()` 非主线程明确告警 |
| `/permissions` 不显示当前模式 | 09 遗留（小修） | 显示了 |
| pai 对 resize 完全无反应 | 12 前置发现 | `SIGWINCH` 同步处理、同尺寸事件丢弃、只重画 dock |
| 测试夹具溯源链断了 | STATUS 缺陷 6 | 真实轨迹抄进 `tests/fixtures/real_turn.jsonl` 并写明出处 |

**关键数字**：`./test.sh` → **747 passed, 3 deselected**（feature 12 新增 **238 条**：
八个 task 171 条 + 交付后修复波 67 条；plan 各 task 下限相加 67，验收线 40）。

### 交付后的修复波（2026-08-11，用户真跑打回）

宣告交付时 680 passed 全绿，用户真跑**当场打回三条**，另提四轮视觉要求。
详见 [devlog 的「交付后修复波」一节](devlog.md)。三条 bug 的共同点：
**全在组件之间的接缝上**，而离线测试是逐组件测的——每个组件单独看都对。

升格的取舍：[D#60](../../decisions.md)（方案 A 不持有整份文档）、
[D#61](../../decisions.md)（对话框不抢焦点，推翻 pai 凭文档推出的判断）、
[D#62](../../decisions.md)（会变的依赖传持有者，同一个坑连撞两次）、
[D#63](../../decisions.md)（字形不用 emoji，用测试卡死物理约束）。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处，否则等于没记 -->

1. **`Ctrl+R` 增量历史搜索没了**——拍板时就知道的功能回退（方案 A 全程 raw mode）。
2. **steering 仍不通电**——拍板选 followUp，05 那条遗留只关掉一半。
3. **`display_width` 的家不对**——住在 `modes/statusline.py` 而 `tui/` 要用它。
4. **`_queue_size` 读了 `PendingMessageQueue` 的私有表**——不给 05 交付的类加公开面，
   但这是一处刻意的越界，值得记。
5. **`tui/driver.py` 离线测不透**——需要真 tty / 真 raw mode / 真 select，
   靠 `pai_playground/tui-probe/p5_tui_smoke.py` 冒烟顶着。
6. **干活期间的按键只在「有事件到来时」被读取**——两个事件之间按的键留在内核 tty
   缓冲区（反向对照已证明它们不会丢），但如果某个工具跑很久且不发事件，
   dock 的输入行在那段时间里不会更新。
7. **中文 IME 候选框位置仍未经真人验证**——离线测不出，见验收标准第 11 条。
8. **`^O` 是「再打一遍完整的」，不是原地展开，也不能点**——方案 A 下做不到
   （内容已归终端所有）。真正的点击/滚动/新窗口见
   [features/13-alt-screen](../13-20260811-alt-screen/README.md)。
9. **权限询问里 `write_file` 的 content 只截 160 字**——够用但看不清要写什么，
   真要批得明白得有 diff 预览。
10. **`run_interactive` 的两条主循环仍未合并**（复盘质疑四），交互语义改动要改两处。

## 用到的知识

- [K tui/pi-tui-main-screen.md](../../../../knowledge/tui/pi-tui-main-screen.md)（绘制侧）
- [K tui/cc-input-ownership-and-modes.md](../../../../knowledge/tui/cc-input-ownership-and-modes.md)（输入侧）
- [K tui/terminal-width.md](../../../../knowledge/tui/terminal-width.md)（中文宽度）
- [K tui/terminal-raw-mode.md](../../../../knowledge/tui/terminal-raw-mode.md)（本轮沉淀：raw mode 三条静默陷阱）
- [K engineering/injection-seams.md](../../../../knowledge/engineering/injection-seams.md)（本轮沉淀：装配期捕获 + 接缝测试）
- 本档案 [evidence/](evidence/)：终端反向对照（6 条）+ CC 实物截图转录
