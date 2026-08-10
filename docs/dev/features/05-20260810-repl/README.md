# 05-20260810-repl —— 交互模式（纯 REPL 先行）

状态：已交付（2026-08-10，8 task 全部 TDD 跑完，193 passed；待合并 main 后转已验收）

## 需求

roadmap 阶段 2 前半程：`modes/interactive.py` 纯 REPL。做三件事——
**事件流定型**（`on_event` 从字符串升级为结构化事件，参照 pi 三层生命周期但砍掉流式才有意义的
`message_update`）、**steering/followUp 双队列**（结构与注入点先立）、**REPL 本体**
（历史 / 多行 / `!` shell 模式 / `/` 命令 / Ctrl+C 两级中断）。顺带 AskUserQuestion 工具。
TUI 是阶段 2 后半程，另立档案。

## 候选方案与确认

### 2026-08-10 brainstorm 四问拍板（用户；问答完整存档，规矩 6）

**问 1**：事件流怎么定型？现在 loop 只有 `on_event(str)`（拼好的中文字符串），
REPL 要按事件类型分别渲染就必须结构化。
- 候选 A·**事件对象，破坏性替换 `on_event`**：新建 `core/events.py`，dataclass 扁平联合
  （agent_start / turn_start / turn_end / tool_start / tool_end / compaction / warning /
  agent_end），`on_event` 签名一次性从 `str` 改成事件对象，loop 里 5 处调用点 + 现有测试
  同步改，渲染成中文字符串的活下放给 modes 层。
  代价：一次性破坏改动，测试要跟着动；收益：只有一套事实。
- 候选 B·并行双通道：保留 `on_event(str)` 原样（once 与全部现有测试零改动），另加
  keyword-only `on_agent_event=None` 发结构化事件。代价：同一件事两处发射两处维护，
  字符串渲染永远留在 loop 里（正是要搬走的东西）；收益：改动面最小。
- 候选 C·dict 事件（TypedDict）：与 session JSONL 落盘格式同构，可直接 append。
  代价：类型注解弱，与 AGENTS.md「类型注解必写」擦边；收益：事件流与审计流合一。

**选择：A**。理由：只留一套事实，渲染下放到 modes 层。

**问 2**：steering/followUp 双队列在纯 REPL 里做到哪一层？纯 REPL 的 `input()` 是阻塞的，
agent 干活时用户根本没法打字——这是「REPL 先行」的结构性限制。
- 候选 A·**结构与挂点先立，REPL 只喂 followUp**：实现 `PendingMessageQueue`
  （enqueue/drain/clear/has_items + `all|single` 两种 drain 模式，抄 pi 语义不抄代码）
  与两个注入点——steering 在每轮工具执行完之后、followUp 在 agent 本该停下时。
  REPL 阶段真实输入源只有 followUp；steering 用注入的假回调写测试钉死注入位置。
- 候选 B·后台线程读 stdin，纯 REPL 也做真 steering。代价：线程与 readline 抢终端、
  回显与提示符错乱、Ctrl+C 语义复杂化，且这些坑 TUI 阶段要重做一遍。
- 候选 C·只做 followUp，steering 整体推到 TUI。代价：注入点这个真正值钱的设计点被推迟，
  TUI 阶段要回头改 loop 一次。

**选择：A**。诚实标注：REPL 阶段 steering **无真实输入源**，等 TUI/流式才通电。

**问 3**：中断（Ctrl+C）做到哪一步？官方对 `Esc` 的承诺是「停止当前响应或工具调用中途，
且保留迄今完成的工作」（K claude-docs/interactive-mode.md）。
- 候选 A·只做步边界中断：`KeyboardInterrupt` 捕获后设标志，loop 在下一次 `create()`
  之前干净退出。跑飞的 bash 停不了（阻塞在 subprocess）。
- 候选 B·**连工具执行中途也能中断**：bash 工具改用可杀的子进程组 + 轮询等待，
  Ctrl+C 真能打断跑飞的命令。代价：要动 `core/tools/shell.py`，即 roadmap 阶段 2 写的
  「core 不动」作废；收益：更接近官方语义。
- 候选 C·阶段 2 不做中断，随阶段 5 流式一起做。

**选择：B**。连带后果两条，已写进 spec 与 decisions：① 「core 不动」边界正式作废；
② 中断必须**回填工具结果**而不是抛异常——否则 `tool_call_id` 配对断裂，下一轮请求 400。

**问 4**：AskUserQuestion（roadmap 记在阶段 2「顺带工具」）怎么做？
- 候选 A·**做成真工具，asker 依赖注入**：`ask_user_question` 走现有 `@tool` 生成 schema，
  REPL 装配期注入真人问答通道，测试注入假 asker，once 模式**干脆不注册**这个工具
  （无真人可问，注册了就是让模型撞空）。
- 候选 B·loop 里开特例分支（认工具名）。代价：违反「调度靠能力标志不靠工具名 if-else」。
- 候选 C·阶段 2 不做，与阶段 4 权限的 ask 三态合并设计。

**选择：A**。

### 2026-08-10 追加：工具调用状态行（用户拿 CC 截图问「这里有哪些可以实现」）

来源是 CC 的工具调用状态行两张截图：全完成态 `✓ Bash ×14 | ✓ WebSearch ×3 | ✓ WebFetch ×2
| ✓ ToolSearch ×1`；混合态 `◐ Bash: echo "=== improve... | ◐ Bash: Applications Top ...
| ✓ Bash ×16 | ✓ AskUserQuestion ×1`（进行中的单独展开带参数预览且排在前，已完成的按工具名折叠计数）。

拆成 6 个能力后逐条判定，**前四条收进 Task 8，后两条明确不做**：

| 能力 | 判定 | 理由 |
|---|---|---|
| 同名工具折叠计数 | 做 | `ToolStart`/`ToolEnd` 已带 `name`，聚合是纯函数 |
| 三态图标 + 颜色 | 做（有折扣） | `is_error` 只覆盖 loop 自造的错，工具内部异常标不出红叉（spec 已声明的边界） |
| 进行中单独展开 + 参数预览 | 做 | 但必须按**终端列宽**截断（中文占两列，`unicodedata.east_asian_width`） |
| 单行原地刷新 | 做 | `\r` + 清行，不需要 alt-screen；工具执行本在主线程发事件，无需并发 |
| 多个进行中并列 | 不做 | pai 一次只跑一个工具，并发属阶段 5 |
| 多行常驻状态区 / 鼠标 / 点击展开 | 不做 | 要 alt-screen 与行数管理，属 TUI 阶段 |

落点：`modes/statusline.py` 的 `render_tool_line(events, width) -> str` 纯函数 + 一个 `\r` 打印器。
选纯函数契约不是审美——它与 roadmap 已拍板的 TUI 设计原则 1（`Component.render(width) -> list[str]`
纯函数、组件不持终端句柄）同构，TUI 阶段可直接复用。

### 提问时的一处口误更正

问 1 的选项描述里写「loop 里 8 处调用点」，**实际是 5 处**
（`loop.py:103 / 105 / 114 / 130 / 182`）。不影响选择，如实记在这里。

## 实施

superpowers 全链路：[spec.md](spec.md) → [plan.md](plan.md) → SDD。
分支 `feat/repl`（自 `feat/compaction` 开出，基线 115 passed）。

## 结果与测试

8 个 task 严格 TDD（红→绿），每步真实数字见 [devlog.md](devlog.md)：

| task | 内容 | 提交后全套 |
|---|---|---|
| 1 | `core/events.py` 事件流定型（10 事件 + `render_text`） | 120 passed |
| 2 | `core/queue.py` PendingMessageQueue（all/single 两模式） | 127 passed |
| 3 | `core/interrupt.py` 中断标志 | 131 passed |
| 4 | bash 可中断到**进程组**（含注入反证） | 136 passed |
| 5 | loop 接线：事件 + 双队列 + 中断（唯一破坏性改动） | 149 passed |
| 6 | `core/tools/ask.py` AskUserQuestion | 154 passed |
| 7 | `modes/interactive.py` REPL + cli 分发 | 178 passed |
| 8 | `modes/statusline.py` 工具状态行（用户截图追加） | **193 passed, 3 deselected** |

**TDD 抓出的两个真 bug**（都不在计划里，是写测试时撞出来的）：
1. `verify_compaction` 返回**新对象**，loop 原来换绑局部变量——注入方看不到失败计数，
   **熔断器在 REPL 里等于每轮清零、连续失败永远数不到 3**。修法 `_adopt` 写回同一对象。
2. 冒烟真跑时一次 401 让整个 REPL **带栈退出**——REPL 崩了等于丢掉整段对话，
   而这一层的全部价值就是「对话留着」。修法：catch 后回提示符。

另有两处自查修正：`once.py` 默认 `on_event=print` 会打印 dataclass repr（测试注入假
handler 照不出来，补 `capsys` 断言）；状态行彩色路径原本跳过截断，而真 tty 走的正是彩色路径。

## 遗留问题

全部登记在 TODO「feature 05（REPL）遗留」小节，共 6 条：`Tool.run` 返回契约分不出错误、
steering 无真实输入源（诚实边界）、`AgentStart.task` 多轮语义歧义、`_preview` 只取首个参数、
REPL 无会话恢复、`_install_sigint` 非主线程静默失效。

## 用到的知识

[knowledge/claude-docs/interactive-mode.md](../../../../knowledge/claude-docs/interactive-mode.md)（官方交互契约）、
[knowledge/source-walks/pi-agentloop.md](../../../../knowledge/source-walks/pi-agentloop.md)（事件三层 + 双队列 + 钩子）
