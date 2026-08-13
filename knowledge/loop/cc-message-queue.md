# CC 的排队消息走读：不是两条队列，是一条队列 + 三档优先级

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `src/utils/messageQueueManager.ts`(547) / `src/types/textInputTypes.ts`（`QueuePriority` 与
  `QueuedCommand` 定义）/ `src/query.ts`（mid-turn drain 点）/ `src/utils/attachments.ts`
  （`getQueuedCommandAttachments`）/ `src/screens/REPL.tsx` 与 `src/cli/print.ts`（`now` 的订阅者）/
  `src/entrypoints/sdk/coreSchemas.ts`（唯一能设 `now` 的地方）
  （符号名检索，反编译行号会漂）
- 精读日期：2026-08-13
- pai 锚点：`src/pai/core/queue.py`、`src/pai/core/loop.py`（`:102-103` 两个注入参数、
  `:284-288` followUp、`:352-355` steering）、`docs/dev/TODO.md` 的两条 steering 登记
  （05 拍板问 2 / 12 spec G6）
- 相关：[pi-agentloop.md](pi-agentloop.md) 第三节（pi 的双队列），
  [cc-input-ownership-and-modes.md](cc-input-ownership-and-modes.md)（谁拥有输入，与本篇是一件事的两半）

**为什么读这篇**：pai 的 steering 队列从 feature 05 起就「有注入点无调用方」，
TODO 里躺了两条登记。要给它接输入源，先得回答一个只有用户能拍的板——
**用户怎么表达「现在就转向」和「等你干完再说」**。pi 的答案是两条具名队列，
把这个问题**推给了集成方**（`AgentHarness` 两条队列的模式都可配，默认都是 `one-at-a-time`）。
CC 给了一个不同且更完整的答案，而且它是**有真实用户量验证过的默认值**。

---

## 一、结构：一条队列，靠字段分档

`messageQueueManager.ts:52` 全局只有一条：

```ts
const commandQueue: QueuedCommand[] = []
```

模块头部注释把定位写死了（`:44-50`）：

> *"All commands — **user input, task notifications, orphaned permissions** — go through this
> single queue. React components subscribe via `useSyncExternalStore`. Non-React code
> (print.ts streaming loop) reads directly. **Priority determines dequeue order:
> 'now' > 'next' > 'later'. Within the same priority, commands are processed FIFO.**"*

**与 pi 的根本差别**：pi 用**两个对象**表达两种时机（`steeringQueue` / `followUpQueue`）；
CC 用**一个对象 + 一个枚举字段**。
代价与收益都很直接——CC 能容纳第三档（pi 的结构里塞不进去，因为它是"两个"而不是"N 档"），
但读代码时"这条消息什么时候会被发出去"要多看一个字段。

## 二、三档的语义（`types/textInputTypes.ts:276-294`，doc comment 即权威定义）

```ts
export type QueuePriority = 'now' | 'next' | 'later'
```

| 档 | 原文语义 | 对应 pi | pai 有吗 |
|---|---|---|---|
| **`now`** | *Interrupt and send immediately. **Aborts any in-flight tool call** (equivalent to Esc + send). Consumers (print.ts, REPL.tsx) subscribe to queue changes and abort when they see a 'now' command.* | ❌ **pi 没有这一档** | ❌ |
| **`next`** | ***Mid-turn drain.** Let the current tool call finish, then send this message **between the tool result and the next API round-trip**.* | `getSteeringMessages` | 有注入点无调用方 |
| **`later`** | ***End-of-turn drain.** Wait for the current turn to finish, then process as a new query.* | `getFollowUpMessages` | ✅ 已通电 |

`PRIORITY_ORDER`（`:151-155`）是 `now: 0 / next: 1 / later: 2`，数字小的先出队。
`dequeue()`（`:167-190`）线性扫一遍找最高档，**同档按数组顺序即 FIFO**；
它还收一个可选 `filter`，注释说明了用途：让 between-turn drain 限定只取主线程的命令
（`cmd.agentId === undefined`）而不必重构既有的 while 循环。

> ⚠️ **别把这条读成「CC 逐条注入」**（2026-08-13 补，feature 18 拍板时复核源码撞出来的）。
> `dequeue()` 是**函数**的语义，不是**注入路径**的行为。两个 drain 点实际都是**批量**：
> - mid-turn（`query.ts:1570`）：`getCommandsByMaxPriority()` 拿快照（`filter`，不删），
>   整批转 attachment，`:1642` `removeFromQueue(consumedCommands)` 整批摘掉。
> - between-turn（`utils/queueProcessor.ts`）：`dequeueAllMatching(同 mode)` **批量出队**，
>   注释原话 *"all items with the same mode as the highest-priority item are drained at once
>   and passed as a single array to executeInput — **each becomes its own user message with
>   its own UUID**"*；不同 mode 从不混批（下游处理方式不同）。
>
> **逐条出队只用在 slash 与 bash 命令上**，`queueProcessor.ts` 给了理由：
> *"Bash commands need individual processing to preserve per-command error isolation,
> exit codes, and progress UI."*
> 即「批量 + 每条各自一条消息」是常规路径，逐条是**为副作用隔离开的例外**。

## 三、🔑 默认值才是真正的设计决定

`messageQueueManager.ts:122-129`：

```ts
/** Used for user-initiated commands (prompt, bash, orphaned-permission).
 *  Defaults priority to 'next' (processed before task notifications). */
export function enqueue(command: QueuedCommand): void {
  commandQueue.push({ ...command, priority: command.priority ?? 'next' })
```

对照任务通知（`:139-143`）：

```ts
/** Convenience wrapper that defaults priority to 'later' so user input
 *  is never starved by system messages. */
export function enqueuePendingNotification(command: QueuedCommand): void {
  commandQueue.push({ ...command, priority: command.priority ?? 'later' })
```

**所以：用户在模型干活时打字回车，默认拿到的是 `next`——也就是 steering。**
用户不需要用任何修饰键、前缀或命令来表达「我要现在插话」，**那就是默认行为**；
反过来，需要显式理由才降级到 `later` 的是**系统消息**，注释写明了动机：
*so user input is never starved by system messages*。

> **这条推翻了一个很自然的设计直觉**：「立即插队」听起来像是特权操作、该要个显式手势。
> CC 的取舍相反——**人说话默认优先，机器说话默认等着**。

### `now` 在本地界面产生不了

全仓检索 `'now'`，能**设置**它的只有 SDK schema（`entrypoints/sdk/coreSchemas.ts`
的 `priority: z.enum(['now','next','later']).optional()`）。
REPL 与 print 只是**订阅**队列、看见 `now` 就 abort：

```ts
// REPL.tsx  —— Abort the current operation when a 'now' priority message arrives
if (queuedCommands.some(cmd => cmd.priority === 'now')) { ... }
// print.ts  —— 同款
if (abortController && getCommandsByMaxPriority('now').length > 0) { ... }
```

**即交互式用户永远发不出 `now`**（他要打断就按 Esc，那是另一条路）；
`now` 是留给**程序化调用方**的通道。

## 四、drain 点与注入形状（`query.ts`，mid-turn）

```ts
const sleepRan = toolUseBlocks.some(b => b.name === SLEEP_TOOL_NAME)
const queuedCommandsSnapshot = getCommandsByMaxPriority(sleepRan ? 'later' : 'next')
  .filter(cmd => {
    if (isSlashCommand(cmd)) return false
    if (isMainThread) return cmd.agentId === undefined
    return cmd.mode === 'task-notification' && cmd.agentId === currentAgentId
  })

for await (const attachment of getAttachmentMessages(..., queuedCommandsSnapshot, ...)) {
  yield attachment
  toolResults.push(attachment)          // ← 跟在本轮 toolResults 后面
}
```

四条讲究：

**① 注入形状是 attachment，不是普通 user 消息。**
注释原话：*"Get queued commands snapshot before processing attachments.
**These will be sent as attachments so Claude can respond to them in the current turn.**"*
`getQueuedCommandAttachments`（`attachments.ts`）把每条命令转成 attachment，
`pastedContents` 里的图片在这里才 `buildImageContentBlocks` 拼成 text + image 的 content block 数组
（**图片在执行时才 resize**，见 `QueuedCommand.pastedContents` 的字段注释）。
> **pi/pai 是 `messages.push({role:"user", ...})`。两家形状不同。**

**② slash 命令被排除在 mid-turn drain 之外。**
注释：*"they must go through `processSlashCommand` after the turn ends (via `useQueueProcessor`),
**not be sent to the model as text**"*。`/xxx` 是给客户端执行的，不是给模型读的。
bash 模式命令则由 `INLINE_NOTIFICATION_MODES` 在 `getQueuedCommandAttachments` 里先滤掉。

**③ 队列是进程级单例，主线程与子 agent 共用，靠 `agentId` 分流。**
主线程只 drain `agentId === undefined`；子 agent 只 drain 发给自己的 task-notification，
**永远看不到用户的 prompt**（注释：*"even if someone stamps an agentId on one"*）。

**④ `sleepRan` 会临时把门槛从 `next` 放宽到 `later`。**
SleepTool 跑过就把 `later` 那批也捎上——否则它们卡在队列里会让
`hasPendingNotifications()` 恒真、Sleep 以 0ms 时长无限唤醒。
（`SleepTool` 只在 proactive 模式存在，普通模式下这一支是空操作。）

## 五、pai 抄什么、不抄什么

| CC 的做法 | pai 打算怎么办 | 理由 |
|---|---|---|
| **用户输入默认 `next`（= 中途注入）**，系统消息才默认 `later` | **抄这个默认值** | 这是本篇最值钱的一条：它有真实用户量验证。pai 现在 TUI 干活时打字只能进 followUp（feature 12 拍板问 4），照 CC 该反过来 |
| 一条队列 + priority 字段 | **不抄结构**，保留 pi 的两条具名队列 | pai 只需要两档；名字承载调用时机的契约（见 [pi-agentloop.md](pi-agentloop.md) 第三节），换成字段反而把这条约束藏起来了。**若将来要第三档再议** |
| `now` 档（abort 在跑的工具） | **不做** | pai 的中断是**进程级标志**（D#40），粒度对不上「只 abort 这一个工具调用」；而且 CC 自己也没把它开给交互式用户 |
| 注入成 attachment 跟在 toolResults 后 | **不抄** | pai 走 OpenAI 兼容协议，没有 attachment 这层；push 一条 user 消息是等价且更简单的落法 |
| slash 命令排除在 mid-turn drain 外 | **抄这条规则** | pai 的 `/` 命令同样是给客户端执行的。TUI 里 `!`/`/` 已由 `tui/dialog.py` 的 `handoff()` 交回主循环，方向一致 |
| **批量 drain，每条各自一条消息**（逐条只留给 slash/bash） | **抄这个形状** | feature 18 问 3 拍板：steering 用 `all`，`drain()` 加可选谓词（对应 `dequeueAllMatching(predicate)`）好把 slash 滤出去 |
| `agentId` 分流 | **不适用** | pai 没有子 agent |

## 六、一条 pai 自己的前置缺陷（读这篇时撞出来的）

pai 把 pi 的**两层 while 压成了单层 `for` + `continue`**（`loop.py:284-288`），
于是 `:283-289` 的「模型不发 tool_calls 就 `return`」在 `:352-355` 的 steering poll **之前**。

**后果：模型某一轮直接作答不调工具时，队列里的 steering 消息永远不会被注入，
也不会退化成 followUp——它就卡在那儿。**

pi 没有这个问题：它的内层 while 条件是 `hasMoreToolCalls || pendingMessages.length > 0`，
**队列非空就不许退出**。

CC 也没有：它的 drain 挂在 `query.ts` 的工具结果处理链上，而 `later` 档本来就是
end-of-turn 处理，两档各有各的出口。

> **这条是给 steering 接输入源之前必须先解决的**，已随 feature 18 立项一并登记。
> **2026-08-13 拍板取 (a)「两个出口」**：`:283` 分支改查 steering（注入 + `continue`），
> `:352` 中途注入点不动——`for` 循环与 `max_steps` 语义都不用动。
> 注意这**不是权宜之计而是 CC 的形状**：CC 同样是两个出口（mid-turn drain +
> turn 结束后的 `useQueueProcessor`），双层循环是 pi 的答案。
> 同次拍板还定了 **followUp 队列删掉**（pai 只留一条消息队列，照 CC 的交互式实情），
> 于是 `:283` 那个分支本来就要动，(a) 的边际成本近乎为零。
> 顺带：pai 的 followUp 走 `continue` 会**消耗 `max_steps` 预算**，而 pi 根本没有 `max_steps`
> （`agent-loop.ts` / `types.ts` 全文检索零命中）——同一处压平带来的第二个代价。

## 外部参照

见 [knowledge/README.md 的「外部参照」节](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)。
