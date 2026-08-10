# 05-20260810-repl · spec

2026-08-10 brainstorm 定稿（四问拍板记录见 [README](README.md)「候选方案与确认」）。

## 背景与问题

pai 现在只有 `modes/once.py`（单次任务，跑完即退）。交互模式缺三样东西：

1. **事件流**：`run_agent(on_event=print)` 发的是拼好的中文字符串
   （`"🔧 bash({...}) → ..."`）。REPL 要按事件类型分别渲染（工具调用折叠、压缩提示单独一行、
   用量进状态栏），拿字符串没法分流——loop 里 5 处调用点全是「渲染已经在 loop 里做完了」。
2. **消息队列**：用户在 agent 干活期间/结束时想追加的话，现在无处可放。
3. **REPL 本体**：多轮对话共享一份 `messages`、历史、多行输入、中断。

## 目标（做什么）

### 1. `core/events.py` —— 事件流定型

dataclass 扁平联合（参照 pi 的 `AgentEvent`，砍掉不流式就没意义的 `message_update`）：

| 事件 | 字段 | 发射时机 |
|---|---|---|
| `AgentStart` | `task` | 进入 loop |
| `TurnStart` | `step` | 每步开头 |
| `AssistantMessage` | `content`、`tool_call_names` | 收到模型回复后 |
| `ToolStart` | `tool_call_id`、`name`、`args` | 每个 tool_call 执行前 |
| `ToolEnd` | `tool_call_id`、`name`、`args`、`result`、`is_error` | 执行后 |
| `Compacted` | `cut`、`before`、`after` | 压缩成功 |
| `CompactionSkipped` | `reason`（`anchors_pending` \| `nothing_to_cut`）、`estimated` | 触发但没压 |
| `BreakerTripped` | `failures` | 熔断 |
| `Interrupted` | `where`（`tool` \| `step`） | 中断落地 |
| `AgentEnd` | `reason`（`final` \| `max_steps` \| `budget` \| `interrupted`）、`text` | 退出 loop |

- `TurnEnd` **不设**：非流式下它与 `AssistantMessage` 同一时刻同一信息，设了是给 pi 的
  形状凑数。等阶段 5 流式真有「一轮内多次 message_update」时再补。
- `is_error` 的**诚实边界**：只能标出 loop 自己造的错（参数不是合法 JSON / 参数不是对象 /
  未知工具）。工具内部异常被 `Tool.run` 吸收成 `"错误：..."` 字符串，loop 无从分辨——
  要真分辨得改 `Tool.run` 的返回契约，那是另一件事（登记 TODO，不在本轮）。
- `render_text(event) -> str | None` 默认渲染器：把现在 loop 里那 5 条中文字符串**原样**搬来，
  `once` 模式接 `on_event=lambda e: print(render_text(e))`，**对外行为一字不变**（测试钉死）。
  返回 `None` 表示「这个事件默认不打印」（如 `TurnStart`）。

### 2. `core/queue.py` —— PendingMessageQueue 与两个注入点

- 队列：`enqueue` / `has_items` / `drain` / `clear`；`mode` 取 `"all"`（一次全取）或
  `"single"`（一次一条），语义抄 pi（`agent.ts:123`），代码独立写。
- `run_agent` 新增两个 keyword-only 参数，**默认 `None` 时行为与接线前完全一致**
  （沿用压缩接线的先例）：
  - `get_steering_messages: Callable[[], list[dict]] | None` —— 每轮**所有 tool 结果
    回填完之后**、进入下一步之前调用，非空则把消息追加进 `messages`。
  - `get_follow_up_messages: Callable[[], list[dict]] | None` —— 模型**没有 tool_calls
    即将返回**时调用，非空则把消息追加进 `messages` 并**继续循环**而不是返回。
- REPL 只把真实输入接到 followUp；steering 在 REPL 阶段无输入源（诚实边界，见 README 问 2），
  但注入位置由测试（假回调）钉死。

### 3. 中断（问 3 选 B）

- `core/interrupt.py`：`InterruptFlag`（`set` / `is_set` / `clear`）+ 进程级
  `current()` / `set_current()`。选进程级单例而非构造注入，是因为 `@tool` 注册的是模块级函数，
  多加参数会污染发给模型的 schema——取舍记 decisions。
- `bash` 工具：`start_new_session=True` 起独立进程组；用 `poll` + 短超时轮询等待，
  每次轮询检查中断标志；命中则 `os.killpg(SIGKILL)` 收掉**整组**（跑飞命令派生的孙进程一并收，
  这是起独立会话的理由），返回 `"(已中断，命令被终止)"` + 已产出的部分输出
  ——沿用超时分支已经确立的做法：**抹掉部分输出会让模型误判重试**（R3#3）。
- loop：中断标志置位后
  1. 当前轮**剩余的 tool_calls 一律不执行，但每个都回填一条 `"(已取消)"` 的 tool 消息**
     ——`tool_call_id` 配对是硬约束，缺一条下轮就是 400（R#11 有真实复现）；
  2. 发 `Interrupted` 事件，在**下一次 `create()` 之前**返回，`messages` 原样保留；
  3. `AgentEnd(reason="interrupted")`。
- REPL：`SIGINT` 处理器只置标志不抛；空闲时按一次清输入、连按第二次退出（抄 CC 两级语义）。

### 4. `core/tools/ask.py` —— AskUserQuestion

- `ask_user_question(question: str, options: str) -> str`，`options` 是 **JSON 数组字符串**
  ——`@tool` 只支持 str/int/float/bool（`tools/__init__.py` 的显式报错已经这么指路）。
- asker 通过模块级 `set_asker()` 注入（与中断标志同一模式）：REPL 注入真人问答，
  测试注入假 asker；**`once` 模式不注册此工具**（无真人可问）。
- 未注入 asker 时返回错误字符串而不是抛（工具错误不 throw）。

### 5. `modes/interactive.py` —— REPL

- 多轮共享一份 `messages`：`run_agent` 目前每次调用自己造 `messages`。**新增
  keyword-only `messages: list[dict] | None`**（传入即续用，不传维持原状），REPL 持有对话。
- 输入层（能力全部取自 K claude-docs/interactive-mode.md）：
  - `readline` 提供 ↑/↓ 与 `Ctrl+R`；历史**按 cwd 分文件**存 `~/.pai/history/<hash>`，
    **连续重复只记一条**（官方两条语义）。
  - 多行：`\` + Enter（唯一全终端可用的那条）。
  - `!cmd` shell 模式：直接跑 bash 工具，命令与输出进 `messages`，**不自动接话**
    （CC v2.1.186 起会自动接话且提供开关；pai 默认关——每次 `!` 都花一次请求钱）。
  - `/` 命令最小集：`/exit`、`/clear`、`/compact`、`/status`、`/help`。
- 事件渲染：默认用 `render_text`，工具结果按现有 200 字符截断规则。

## 非目标（明确不做）

- **TUI**（alt-screen、主题、鼠标、Component 契约、CURSOR_MARKER）——阶段 2 后半程另立档案。
- 真并发 steering 输入源（要线程或流式）；`@` 文件补全、`/` 菜单交互筛选、vim 模式、
  提示建议、`/btw`、语音、后台任务、转录查看器——理由逐条见 K interactive-mode.md 第三节。
- 流式（阶段 5）、权限钩子（阶段 4）、`Tool.run` 返回契约改造（`is_error` 只覆盖 loop 自造错）。
- 会话恢复 / `--resume`：REPL 的 `messages` 只活在进程内，落盘仍是现有 append-only JSONL。

## 边界变更（要记 decisions）

roadmap 阶段 2 原文「纯 REPL 先行（**core 不动**）」**作废**。事件流定型必然改
`loop.on_event` 签名，问 3 选 B 又必然改 `tools/shell.py`。改为：**core 可动，但只加不改语义**
——新参数一律 keyword-only 且默认值维持旧行为；唯一的破坏性改动是 `on_event` 的参数类型
（用户已知情选择）。

## 验收标准

- `./test.sh` 全绿全离线；`once` 模式的事件输出**逐字不变**有测试钉死。
- 每条注入点/中断路径有测试：steering 注入在工具结果之后、followUp 让 loop 继续、
  中断后剩余 tool_calls 全部回填「已取消」（配对不变量）、bash 中断杀的是**进程组**。
- REPL 的 `/` 命令与 `!` shell 模式可离线测（注入假 client + 假输入序列）。
- 每步红→绿真实数字进本目录 devlog.md；边界变更进 decisions；遗留逐条进全局 TODO。
