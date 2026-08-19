# CC 的 agent loop：一个生成器 + 两条 drain 路径

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `src/query.ts`(1729，`query` / `queryLoop`)、`src/QueryEngine.ts`、
  `src/utils/messageQueueManager.ts`(547)、`src/utils/queueProcessor.ts`(95)、
  `src/hooks/useQueueProcessor.ts`(68)、`src/utils/attachments.ts`、`src/utils/messages.ts`、
  `src/types/textInputTypes.ts`（符号名检索，反编译行号会漂）
- 精读日期：2026-08-13
- pai 锚点：`src/pai/core/loop.py`、`src/pai/core/queue.py`、`src/pai/modes/interactive.py`、
  `docs/dev/features/18-20260813-steering-input`
- 相关：[pi-loop.md](pi-loop.md)（同一件事的 pi 版）、
  [cc-message-queue.md](cc-message-queue.md)（队列的三档与默认值，本篇不重复）、
  [../streaming/cc-streaming-tools.md](../streaming/cc-streaming-tools.md)（工具调度）

本篇与 `loop/cc-message-queue.md` 的分工：那篇讲队列（一条队列、三档优先级、
默认值取舍），本篇讲循环（query 的边界、turn 怎么数、两条 drain 路径挂在循环的哪里）。

---

## 一、结构：`query()` 是个异步生成器

```ts
export async function* query(params: QueryParams):
    AsyncGenerator<StreamEvent | RequestStartEvent | Message | ..., Terminal>
{
  const consumedCommandUuids: string[] = []
  const terminal = yield* queryLoop(params, consumedCommandUuids)   // ← 真正的循环
  for (const uuid of consumedCommandUuids) {
    notifyCommandLifecycle(uuid, 'completed')   // 只在正常返回时跑
  }
  return terminal
}
```

外壳 `query()` 只做一件事：在循环正常返回后补发生命周期通知。注释写明了为什么在外面：

*"Only reached if queryLoop returned normally. Skipped on throw (error propagates through
`yield*`) and on `.return()`. This gives the same asymmetric started-without-completed signal
as print.ts's drainCommandQueue when the turn fails."*

「started 发了但 completed 没发」被刻意保留成一个可观测的失败信号——不是漏了，是设计。

`queryLoop` 内部是 `while (true)`，每轮末尾重建一个 `State` 对象继续（`query.ts:1714-1728`，
检查点就叫 `query_recursive_call`）：

```ts
queryCheckpoint('query_recursive_call')
const next: State = {
  messages: [...messagesForQuery, ...assistantMessages, ...toolResults],
  toolUseContext: toolUseContextWithQueryTracking,
  turnCount: nextTurnCount,
  transition: { reason: 'next_turn' },
  ...
}
state = next
```

`State` 里有个字段专门给测试用（`query.ts:213-215`）：

```ts
// Why the previous iteration continued. Undefined on first iteration.
// Lets tests assert recovery paths fired without inspecting message contents.
transition: Continue | undefined
```

「让测试能断言走了哪条恢复路径，而不必去翻消息内容」——这是把可测试性写进数据结构的一例，
pai 的 `CompactionSkipped(reason=...)` 分 `anchors_pending` / `nothing_to_cut` 是同一个思路。

## 二、术语对照：query ↔ run

| | pi | CC | pai |
|---|---|---|---|
| 一次完整运行 | `run`（`runAgentLoop`，`activeRun`） | `query`（`query()` / `queryLoop()`） | 一次 `run_agent()` 调用 |
| 内部一步 | `turn`（`turn_start`/`turn_end` 事件） | `turn`（`turnCount`） | `step`（`for step in range(1, max_steps+1)`） |
| 「正在跑」标志 | `isStreaming` / `activeRun` | `isQueryActive`（`QueryGuard`，`useSyncExternalStore` 订阅） | 无显式标志（TUI 用 `app.busy`） |
| 步数上限 | ❌ 无 | `maxTurns?: number`，可选（`query.ts:191`，`if (maxTurns && ...)` 才生效；交互模式不设） | ✅ 硬编码 `max_steps=20` |

run 与 query 是两家对同一个概念的不同命名：一次用户输入引发的完整 agentic 循环，内含 N 个 turn。
代码结构也同形——pi 是嵌套 while，CC 是单层 while + state 重建。

## 三、两条 drain 路径：中途消息落在循环的哪里

CC 处理「用户在 agent 干活时打的字」只有两条路，走哪条取决于这一轮有没有工具接缝。

📌 术语出处：`mid-turn drain` / `end-of-turn drain` 是 CC 自己的行话，不是我起的名——
出处在 `types/textInputTypes.ts:276-292` 定义 `QueuePriority` 的 doc comment 里
（`next` — *Mid-turn drain…*；`later` — *End-of-turn drain…*），全仓另有 40+ 处注释在用 `mid-turn`。
但它不是标识符：`grep "midTurnDrain"` 零命中，真正干活的代码内联在 `queryLoop` 里，没有独立函数。

⚠️ 读反编译源码时，行话与标识符要分开记：行话告诉你「设计者怎么想的」，
标识符告诉你「去哪改」。只记行话将来 grep 不到，只记标识符讲不出设计意图。
本篇引「原话」的地方一律附 `file:line`。

中文：`drain` 译抽取，不译「排空」（它不是全取，有门槛与过滤）、不译「出队」
（`dequeue` 在 CC 里是另一个真实函数）。笔记里保留英文原词 + 中文时机：轮内 drain / 轮末 drain。

### 路 A · mid-turn drain（`query.ts:1547-1642`）

发生在执行完工具、准备发下一次请求之前：

```
① 取快照（不删）    getCommandsByMaxPriority(sleepRan ? 'later' : 'next')
       ↓ 四道过滤：slash 排除 / 主线程只要 agentId===undefined
                   / 子 agent 只要发给自己的 task-notification
② 整批转 attachment  getQueuedCommandAttachments()
       ↓
③ 塞进本轮 toolResults   for await (...) { yield attachment; toolResults.push(attachment) }
       ↓
④ 摘掉真被消费的     removeFromQueue(consumedCommands)          :1642
   并打生命周期      notifyCommandLifecycle(uuid, 'started')
       ↓
⑤ 发下一次请求 —— 你的话与工具结果在同一次 API 往返里到达模型
```

注释原话：*"Get queued commands snapshot before processing attachments.
These will be sent as attachments so Claude can respond to them in the current turn."*

四条讲究：

1. 快照与删除分两步。先 `filter` 拿快照（不动队列），转完 attachment 再整批删——中途抛异常命令还在队列里，不会丢。
2. 只摘真被消费的（`:1630-1634`）：仅 `mode === 'prompt' | 'task-notification'` 的会被移除；
   slash 与 bash 留在队列里，因为它们压根没被转成 attachment。
3. slash 命令被排除在 mid-turn drain 之外：*"they must go through `processSlashCommand`
   after the turn ends, not be sent to the model as text"*。
4. `sleepRan` 会临时把门槛从 `next` 放宽到 `later`——SleepTool 跑过就把 later 那批也捎上，
   否则它们卡在队列里会让 `hasPendingNotifications()` 恒真、Sleep 以 0ms 无限唤醒。

#### Ⓐ 的门槛：谁传、谁检查

门槛不是某个模块自己定的，是调用方传进去的参数——`getCommandsByMaxPriority` 是纯过滤函数：

```ts
// messageQueueManager.ts:525-532
const PRIORITY_ORDER = { now: 0, next: 1, later: 2 }
export function getCommandsByMaxPriority(maxPriority: QueuePriority) {   // ← 门槛从参数来
  const threshold = PRIORITY_ORDER[maxPriority]
  return commandQueue.filter(cmd => PRIORITY_ORDER[cmd.priority ?? 'next'] <= threshold)
}
```

所以「谁检查门槛」= 「谁调用它」，全仓只有两处：

| 调用点 | 传的门槛 | 干什么 |
|---|---|---|
| `query.ts:1570` | `sleepRan ? 'later' : 'next'` | ✅ 就是 Ⓐ 本身 |
| `print.ts:1860` | `'now'` | 只为探测「有没有 now」→ 有就 `abort()`，不取内容 |

🔑 loop 外那条路根本没有门槛概念。 `useQueueProcessor` 用的是另外三个函数，
它们也读同一张 `PRIORITY_ORDER`，但语义相反：

| 用法 | 函数 | 语义 | 谁用 |
|---|---|---|---|
| 门槛切片 | `getCommandsByMaxPriority(max)` | 取所有 ≤ max 的，不删 | Ⓐ（loop 内） |
| 取最高档 | `peek` / `dequeue` / `dequeueAllMatching` | 取优先级最高的那个/那批，删 | 路 B（loop 外） |

同一张表，两种用法。 于是 `later` 的命运这样成立：

```
Ⓐ（门槛 'next'=1）：filter(p <= 1) → now✓ next✓ later✗   ← later 够不着，留在队列
        ↓ query 结束
路 B（无门槛，只取最高）：队列里现在只剩 later，它就是最高的 → 被取走 → 开新 query
```

`later` 不是「被安排到轮末」，而是「在 Ⓐ 那里够不着，只能等唯一一个不设门槛的出口」。
「轮末」是结果，不是它被打的标签。

这也解释了 `sleepRan` 的唯一真实用例：这次把门槛多抬一档，一次性清空队列，
免得 `hasPendingNotifications()` 恒真。两条具名队列做不到「这次多带一档」——
门槛是可比较的数值，「两个对象」之间没有"中间值"可言。

#### Ⓐ 的空转路径：没有用户输入时它长什么样

Ⓐ 每个「有工具调用的 turn」都会执行一次，跟队列空不空无关——空不空只决定它取到几条。
没有用户输入时：

| 变量 | 值 | 说明 |
|---|---|---|
| `commandQueue` | `[]` | 模块级单例，从没被 push 过 |
| `sleepRan` | `false` | SleepTool 只在 proactive 模式存在 |
| `getCommandsByMaxPriority('next')` | `[]` | 空数组上 `filter` 返回新的空数组 |
| `queuedCommandsSnapshot` | `[]` | 再 `.filter()` 一次，还是 `[]` |
| `getQueuedCommandAttachments([])` | `[]` | `filtered = []` → `Promise.all([])` → `[]` |
| `consumedCommands` | `[]` | |
| `if (consumedCommands.length > 0)` | false | → `removeFromQueue` 不调、生命周期通知不发 |
| `consumedCommandUuids` | `[]` | `query()` 外壳末尾那个 `for` 零次迭代 |
| `snapshot`（模块级） | 仍是最初那个 `Object.freeze([])` | 见下，关键 |

三条容易想当然的：

① 全程没有 `null`/`undefined`，一路都是空数组。
`getQueuedCommandAttachments` 开头那句 `if (!queuedCommands) return []` 防的是没传参，
不是空数组——传 `[]` 时它走正常路径，只是 map 了零次。

② `toolResults` 仍可能变长。 `getAttachmentMessages` 是整条 attachment 流水线，
`queued_commands` 只是其中一个 `maybe(...)` 分支；同一次调用还会跑 `edited_text_file` /
`todo_reminder` / `relevant_memories` / `date_change` 等。「队列空」≠「这一步什么都没加」。

③ 🔑 `snapshot` 的引用不变——这是订阅机制能成立的原因。

```ts
let snapshot = Object.freeze([])                    // 初始值
function notifySubscribers() {
  snapshot = Object.freeze([...commandQueue])       // 只在入队/出队时才重建
  queueChanged.emit()
}
export function getCommandQueueSnapshot() { return snapshot }   // 返回同一个引用
```

没有用户输入 → `notifySubscribers()` 从不被调用 → `getCommandQueueSnapshot()` 每次返回同一个对象
→ `useSyncExternalStore` 判定「没变」→ 不触发 re-render。
注释原话：*"Returns a frozen array that only changes reference on mutation."*

要是写成 `return [...commandQueue]`（每次新建数组），`useSyncExternalStore` 会认为每次都变了 →
无限重渲染。 这是 React 外部 store 的经典陷阱，CC 用一个模块级缓存变量解决。

空集合走正常路径，比到处加空判断更不容易漏。 唯一必须显式判空的是有副作用的那一步
（`removeFromQueue` + 生命周期通知）——那两件事在空集上不是无害的 no-op，
`notifySubscribers()` 会白白重建 snapshot、触发一轮无意义的 re-render。

### 路 B · between-query drain（`useQueueProcessor.ts` + `queueProcessor.ts`）

如果模型这一轮直接吐最终答案，路 A 那段代码根本走不到。消息一直躺着，直到：

```
query 结束 → isQueryActive = false
      ↓ useQueueProcessor 的 effect 触发（:48-51 三个 return 守卫）
processQueueIfReady()
      ↓ peek(isMainThread) 看队首是什么
  ┌───────────────┴───────────────┐
slash 或 bash 模式             其他（普通 prompt）
  dequeue() 逐条出队            dequeueAllMatching(同 mode) 批量出队
      ↓                              ↓
  executeInput([cmd])           executeInput(commands)
      ↓
        开一个新 query
```

`queueProcessor.ts:36-44` 说明了为什么批量是常规、逐条是例外：

*"Bash commands need individual processing to preserve per-command error isolation,
exit codes, and progress UI. Other non-slash commands are batched: all items with the
same mode as the highest-priority item are drained at once and passed as a single array —
each becomes its own user message with its own UUID. Different modes are never mixed
because they are treated differently downstream."*

批量出队 ≠ 合并成一条：连打的三句一次性取出，但各自成一条 user 消息、各带 UUID。

`:55-60` 还有一段防死锁的注释：`peek` 必须带 `isMainThread` 过滤，否则队首是子 agent 通知时
`targetMode` 会被设错，`dequeueAllMatching` 找不到匹配 → `processed: false` 且队列没变 →
React effect 再也不会重新触发，排队的用户消息永久卡死。

#### 路 B 的四个要点（它是个 effect，不是 loop 的一步）

① 它跟 `query()` 没有调用关系。 `useQueueProcessor` 是挂在 REPL 组件树上的 hook。
两者靠一个模块级全局队列间接通信：

```
query()  ──写──→  commandQueue（模块级单例）  ←──读──  useQueueProcessor
   （loop 内）                                        （React 渲染周期）
```

② 两个订阅源都能叫醒它（`useQueueProcessor.ts:35-46`）：

| 触发源 | 什么时候 |
|---|---|
| `isQueryActive`（`queryGuard`） | query 开始 / 结束 |
| `queueSnapshot` 引用变了 | 有人 `enqueue` 或 `removeFromQueue` |

所以你在 agent 干活时打字，effect 当场就被叫醒了——只是被守卫挡回去。

③ 三道守卫（`:48-51`）：

```ts
if (isQueryActive) return          // ← agent 还在跑，什么都别做
if (hasActiveLocalJsxUI) return    // ← 有对话框占着输入，别抢
if (queueSnapshot.length === 0) return
```

④ 🔑 它是自驱动的循环，不是一次性的。 契约写在 `queueProcessor.ts:46-48`：

*"The caller is responsible for ensuring no query is currently running and for calling this
function again after each command completes until the queue is empty."*

```
query #1 结束 → isQueryActive=false → effect 醒 → 取一批 → 开 query #2
                                                              ↓
                          isQueryActive=true → effect 醒但被守卫① 挡回
                                                              ↓
query #2 结束 → isQueryActive=false → effect 醒 → 队列还有？ → 再取一批 → query #3
                                                  └─ 空 → 守卫③ 挡回，停
```

⑤ 一处靠执行顺序（不靠锁）解决的重入（`useQueueProcessor.ts:53-59`）：

*"The sync chain `executeQueuedInput → handlePromptSubmit → executeUserInput → queryGuard.reserve()`
runs before the first real await, so by the time React re-runs this effect (due to the
dequeue-triggered snapshot change), `isQueryActive` is already true and the guard above returns early."*

即：出队会改 snapshot → 触发 re-render → effect 又跑一次；但 `queryGuard.reserve()` 是同步
执行的（在第一个 `await` 之前），所以第二次跑时 `isQueryActive` 已是 true，被守卫① 挡住。

#### 一次完整走位（每步带全局变量状态）

场景：你问「什么是 agent loop」，模型纯文字回答不调工具，你中途打了两句话。

```
t0  你按回车 → queryGuard.reserve() → isQueryActive: false→true，query #1 开始
    commandQueue = []                       isQueryActive = true

t2  👉 你打「再讲讲 turn」回车
    handlePromptSubmit 见 queryGuard.isActive === true → enqueue({mode:'prompt'}) → 默认 'next'
    commandQueue = [A:next]                 isQueryActive = true
    ⚡ effect 醒（snapshot 变）→ 守卫① 挡回

t3  👉 你又打「和 run 什么区别」回车
    commandQueue = [A:next, B:next]         isQueryActive = true
    ⚡ effect 醒 → 守卫① 挡回

t4  模型吐完，这条 assistant 消息没有 tool_calls → queryLoop return
    ★ 这一轮没有工具接缝，query.ts 里 Ⓐ 那段代码从头到尾没执行
    commandQueue = [A, B]  ← 一条没少      isQueryActive = true

t5  query #1 收尾，queryGuard 释放 → isQueryActive: true→false
    ⚡ effect 醒 → 守卫①✅ ②✅ ③(length=2)✅ → processQueueIfReady()
         peek(isMainThread) → A（只看不取；A、B 同为 next+prompt，FIFO 取 A）
         A 不是 slash、mode 不是 bash → 批量分支
         targetMode = 'prompt'
         dequeueAllMatching(同 mode) → 取走 [A, B]     ← ★ 两条一起
         executeInput([A, B])
    commandQueue = []                       isQueryActive = true（见 t6）

t6  executeUserInput 同步调 queryGuard.reserve() → isQueryActive 立刻 true
    ⚡ 出队改了 snapshot → effect 第三次醒 → 守卫① 挡回（这就是要点⑤）

t7  query #2 开始，messages 追加两条 user 消息（各自一条、各带 UUID，不合并）

t8  query #2 结束 → effect 醒 → 守卫③(length=0) 挡回。停。
```

能读出四件事：effect 被叫醒 4 次只有 1 次真干活；你的话在队列里躺了整段时间、对模型完全不可见；
两条一起取走但各成一条消息；只开了一个新 query（两条 mode 相同，一批取完）。

变体一 · 如果 t4 模型调了工具：Ⓐ 触发 → 取走 [A, B] → 转 attachment 塞进本轮 `toolResults` →
`removeFromQueue`。全程 `isQueryActive` 没变过，路 B 一次都没工作，没有新 query。
同样两句话、同样按回车，就因为模型这轮调没调工具，走了完全不同的两条路。

变体二 · 如果 mode 不同：`[A(prompt,next), N(task-notification,later), B(prompt,next)]` →
`peek` 取 A（next=1 < later=2）→ `targetMode='prompt'` → 取走 [A, B]，N 留下 → query #2；
query #2 结束后 effect 再醒 → 取 N → query #3。三条消息 → 两个新 query，mode 不同不混批。

### 🔑 由此得出的结论：CC 的 loop 内部只有一个队列出口

这是本篇最该记住的一句，也是与 pi 的结构性分歧（不是参数差异）：

| | 队列出口在哪 | 循环条件看队列吗 |
|---|---|---|
| pi | 两个都在 loop 内部：`:257` 问 steering、`:261` 问 followUp | ✅ 内层 while 是 `hasMoreToolCalls \|\| pendingMessages.length > 0` |
| CC | 只有 mid-turn 那个在 loop 内；另一个（`useQueueProcessor`）在 loop 之外 | ❌ 没有 tool_calls 就直接 `return`，队列压根不问 |

由此推出那条反直觉的现象：

CC 的 `next` 在「模型这轮不调工具」的场景下事实上退化成 `later`。
`next` 是字面意思——「下一次 API 往返之前」；没有下一次往返，它就只能等到轮末，由路 B 开一个新 query。

⚠️ 「退化」是比喻，别读成「标签被改了」（2026-08-13 讲这条时被问住，措辞补正）：

| | 这条消息 |
|---|---|
| 标签（`priority` 字段） | 一直是 `'next'`，入队即定，终身不改（全仓 `grep "\.priority = "` 零命中） |
| 实际待遇 | 没赶上 Ⓐ，投递时机与 `later` 相同 |

证明标签没变：让 `later` 先入队——

```
t1  系统通知 → enqueuePendingNotification()  → 'later'    commandQueue = [N:later]
t2  你打字   → enqueue()                     → 'next'     commandQueue = [N:later, A:next]
                                                            ↑先来        ↑后来
路 B 的 peek()：PRIORITY_ORDER[later]=2，PRIORITY_ORDER[next]=1 → 取 A，不取 N
```

若 A 真的「变成了 later」，两条都是 2，先进先出该取 N；实际先取 A，
说明标签还是 `next`，而且它在 loop 外依然在起作用——只是作用从「门槛」换成了「排序」：

| | loop 内（Ⓐ） | loop 外（路 B） |
|---|---|---|
| `priority` 的作用 | 门槛：`next` 能过、`later` 过不去 | 排序：`next` 排在 `later` 前面 |
| `next` 丢掉的 | ← 这一格没吃到（「不用等」） | → 这一格特权还在（「排在系统消息前面」） |

严格说法：*`next` 的「中途注入」特权在无工具接缝的轮次落空，投递时机退化成与 `later` 相同；
但 `priority` 字段本身不变，出队排序上仍优先于 `later`。*

⚠️ 两个容易写错的说法（2026-08-13 画对照图时正是在这里翻的车）：

- ❌「CC 有 followUpQueue」——没有。CC 只有一条 `commandQueue`，`later` 是它的一个 priority 值。
- ❌「CC 的 `later` 让这一轮重开」——不是。query 已经 `return` 了，`useQueueProcessor` 起的是
  一个新 query（`turnCount` 归零）。那已经不是同一次运行了。

pi 没有这个退化：内层 while 的 `|| pendingMessages.length > 0`（`agent-loop.ts:174`）
保证队列非空就再起一个 turn，哪怕这轮没调任何工具，且仍在同一个 run 内。

🔑 对 pai 的意义：feature 18 的 T2 让 `loop.py` 在「不发 tool_calls」那条分支上也查一次
steering，拿到的是 pi 的行为（同一个 run 内解决）；T4 的 `_process_queue_after_turn`
才对应 CC 的 `useQueueProcessor`。这是取长补短，不是照抄 CC——decisions 该这么写。

### 标签是怎么打上去的：入队即定，终身不改

`priority` 是 `QueuedCommand` 上的可选字段（`textInputTypes.ts:302-303`）：

```ts
/** Defaults to the priority implied by `mode` when enqueued. */
priority?: QueuePriority
```

打标签只有三种方式，且全部发生在入队那一刻：

方式一 · 不传，由「调用哪个函数」决定默认值（主要路径）

```ts
// messageQueueManager.ts:129
export function enqueue(command) {
  commandQueue.push({ ...command, priority: command.priority ?? 'next' })     // ← 用户
}
// messageQueueManager.ts:143
export function enqueuePendingNotification(command) {
  commandQueue.push({ ...command, priority: command.priority ?? 'later' })    // ← 系统
}
```

你按回车走的就是这条（`handlePromptSubmit.ts:336`）：

```ts
enqueue({ value: finalInput.trim(), mode, pastedContents, skipSlashCommands, uuid })
//        ↑ 通篇没有 priority 字段 → 吃默认值 'next'
```

🔑 「给用户消息打标签」这件事，代码里没有任何一行 if 在判断内容。
它是函数选择的副产品：调 `enqueue` 就是 `next`，调 `enqueuePendingNotification` 就是 `later`。

方式二 · 调用方显式传（少数几处）

| 位置 | 值 | 什么东西 |
|---|---|---|
| `processSlashCommand.tsx:129` | `'later'` | slash 命令产生的后续 |
| `print.ts:1850` / `:2716` | `'later'` | 非交互模式的系统消息 |
| `print.ts:4752` / `:4828` | `'next'` | bridge/channel 来的消息 |
| `useScheduledTasks.ts:75` | `'later'` | 定时任务 |
| `useManageMCPConnections.ts:526` | `'next'` | MCP 连接事件 |
| `LocalShellTask.tsx:169` | `feature('MONITOR_TOOL') ? 'next' : 'later'` | ★ 见下 |

`LocalShellTask` 那条最有意思：同一种消息（后台 shell 任务完成），档位由 feature flag 决定——
开了 `MONITOR_TOOL` 就 `next`（中途插进去让模型立刻知道），没开就 `later`。
这是「一条队列 + 字段」相对「两条具名队列」的实际好处：调档位只改一个值，不用换队列对象。

方式三 · SDK 显式传 —— `entrypoints/sdk/coreSchemas.ts` 的 schema 允许
`priority: z.enum(['now','next','later']).optional()`。`'now'` 只有这条路能产生。

#### 🔑 标签不可变，可变的是「尺子」

看起来像"动态调整优先级"的那句：

```ts
getCommandsByMaxPriority(sleepRan ? 'later' : 'next')   // query.ts:1570
```

它没有修改任何一条命令的 `priority`，改的是读取时的门槛：

| | 谁的属性 | 什么时候定 | 会变吗 |
|---|---|---|---|
| 命令的 `priority` | 每条消息自己 | 入队那一刻 | ❌ 永不改 |
| drain 的门槛 | 读取方（Ⓐ） | 每次读取时 | ✅ `sleepRan` 一变就变 |

如果标签可变，你就得担心「谁在什么时候把我的 next 降成了 later」；
现在不用担心——一条消息的命运只取决于它入队时调了哪个函数。

⚠️ 排噪音：全仓另有大量 `priority: 'low' | 'medium' | 'high' | 'immediate'`，
那是通知栏的另一套系统，与队列无关，grep 时别混。

### 四条具体走位（同一个任务，看队列怎么流动）

任务：「把 src 下的 py 文件加上类型注解」。
提交路径只有一条（`handlePromptSubmit.ts:312-343`），分岔点不是「你按哪个键」，是「agent 当时在干什么」：

```ts
if (queryGuard.isActive || isExternalLoading) {          // agent 在跑
    if (mode !== 'prompt' && mode !== 'bash') return     // 只有这两种能排队
    if (params.hasInterruptibleToolInProgress) {         // ← 例 4
        params.abortController?.abort('interrupt')
    }
    enqueue({ value, mode, uuid, ... })                  // 没传 priority → 默认 'next'
    return
}
```

例 1 · `next` + 有工具接缝 → 路 A，同一个 query 内注入

| 时刻 | 发生什么 |
|---|---|
| turn 2 | 模型发 `Read(a.py)`，工具正在执行 |
| | 👉 你打「只改 core/ 下的就行」+ Enter → `enqueue` → 默认 `'next'` |
| | 工具跑完、结果回填（没被打断） |
| | Ⓐ mid-turn drain：取快照 → 转 attachment → `toolResults.push()` → `removeFromQueue()` |
| turn 3 | 请求里，你的话和 `Read` 的结果并排送达 |

模型收到的形状：

```
tool_result: <a.py 的内容>
user(attachment): wrapCommandText("只改 core/ 下的就行")
```

`origin` 与 `isMeta` 都为空 → 在 transcript 里可见（就是那个修过的 bug，见第四节）。

例 2 · `next` + 没有工具接缝 → 路 B，退化

| 时刻 | 发生什么 |
|---|---|
| turn 4 | 模型「都改完了，共 3 个文件」，没有 tool_calls |
| | 👉 你打「顺便跑一下测试」+ Enter → 同样默认 `'next'` |
| | ③否 → `query.ts` 的 drain 那段根本走不到（它挂在工具结果处理链上）→ 消息躺着 |
| | query 返回 → `isQueryActive` 变假 → `useQueueProcessor` 触发 |
| | `dequeueAllMatching(同 mode)` 批量出队 → `executeInput()` → 开一个新 query |

同一个 `'next'`，两种结局。 这就是退化的具体形态。

例 3 · `later` —— 给系统消息用的

后台任务完成走的是另一个函数（`messageQueueManager.ts:139-143`）：

```ts
/** …defaults priority to 'later' so user input is never starved by system messages. */
enqueuePendingNotification({ value: "Task X 完成", mode: 'task-notification' })
```

于是即使你的 `'next'` 比它晚入队，`dequeue()` 按 `PRIORITY_ORDER`（`now:0 / next:1 / later:2`）
也先给你。——人说话默认优先，机器说话默认等着。

例 4 · 可中断工具 —— 交互式用户唯一能碰到的「打断」

`'now'` 你设不了（全仓只有 SDK schema 能设）。但提交路径上有一条相邻的路
（`handlePromptSubmit.ts:321-332`）：

*"Interrupt the current turn when all executing tools have `interruptBehavior` 'cancel'
(e.g. SleepTool)."*

即：当前在跑的工具全都声明了 `interruptBehavior: 'cancel'` 时，你按回车会先 abort 掉这一轮，
再把话入队。 工具默认是 `'block'`（不许打断），所以绝大多数时候这条不触发。

## 四、`attachment`：注入物的统一中间层

`attachments.ts:440` 的 `Attachment` 是个判别联合，58 个 `type` 分支，与 `user` / `assistant`
在 CC 内部消息联合体里平级（`message.type === 'attachment'`）。

```
Attachment（带类型标签的数据）
      ↓  messages.ts 的 switch(attachment.type)（:3700+）
createUserMessage({ content, isMeta })
      ↓  多数分支再套 wrapMessagesInSystemReminder([...])
真正发给模型的 user 消息
```

最终形态还是 user 消息——Anthropic API 不认识 attachment，它纯粹是中间层。

### 这个中间层解决三件事

① 让「谁来的」活到渲染时。 `queued_command` 分支带 `origin` / `isMeta` / `commandMode`，
`messages.ts` 里靠它区分人打的字与系统通知：

*"Only hide from the transcript if the queued command was itself system-generated.
Human input drained mid-turn has no origin and no `QueuedCommand.isMeta` — it should stay
visible. Previously this hardcoded `isMeta:true`, which hid user-typed messages in brief
mode (`filterForBriefTool`) and in normal mode (`shouldShowUserMessage`)."*

这是个修过的真 bug：中途注入的话一度被当系统消息藏了，用户看不见自己刚说的。
要是入队时就直接转成 user 消息，这个信息早就丢了。

🔴 pai 有同款风险：`loop.py:395-399` 的 `_extend` 只 append 进 messages 与 session，
不发任何事件，TUI 一无所知。已登记为 feature 18 的补充项。

② 渲染时机可以推迟，字节可以稳定。 `relevant_memories` 的 `header` 字段注释：

*"Pre-computed header string (age + path prefix). Computed once at attachment-creation time
so the rendered bytes are stable across turns — recomputing `memoryAge(mtimeMs)` at render
time calls `Date.now()`, so "saved 3 days ago" becomes "saved 4 days ago" across turns →
different bytes → prompt cache bust."*

⚠️ pai 的 `core/recall.py` 已有 `memory_age` / `freshness_note`——若是每轮重算，
就是一个现成的、可实测的缓存缺陷（pai 全天缓存命中率 84.7%）。待核。

③ 一个分支可以产出 0 条、1 条或多条消息。
`dynamic_skill` → 返回 `[]`（*"informational for the UI only"*，只给界面不进上下文）；
`relevant_memories` → 每篇各一条；`queued_command` → 1 条。
「注入物可以完全不进模型上下文」——这是 user 消息这个形状表达不了的。

### 对 pai 的取舍

不抄 attachment 这层（OpenAI 协议下没有对应概念，push 一条 user 消息等价且更简单），
但要把它做的第一、三件事补上：

| CC 用 attachment 做的 | pai 怎么办 |
|---|---|
| 承载 origin/isMeta 决定可见性 | 靠事件流：注入时发事件，让 TUI 显示（feature 18 补充项） |
| 渲染推迟以稳住缓存字节 | 与 steering 无关；但 `recall.py` 的相对时间要核 |
| 给注入内容套语气外壳 `wrapCommandText(text, origin)` | 几行字符串拼接就能拿到。这是「补充材料的语气」的物理来源，不是 attachment 类型带来的 |

🔑 第三条最容易漏：feature 18 的 spec 已识别风险（*"一条突如其来的 user 消息更可能被模型
读成推翻前面计划的全新指令"*），但 plan 的 T1-T5 没有应对措施。
修法与协议无关：注入前套一层 `<user-interjection>…</user-interjection>` 即可。
⚠️ 不要套 pai 现有的 `<system-reminder>`（`recall.py` 的召回块用的是它）——
那是系统提示的语气，而这是用户说的话，语气反了。
CC 那边这两件事也是分开的：`relevant_memories` 走 `wrapMessagesInSystemReminder`，
`queued_command` 走 `wrapCommandText`。

## 五、三家一句话对照

| | pi | CC | pai |
|---|---|---|---|
| 循环形状 | 嵌套 while（外层 followUp / 内层 turn） | 单层 while + state 重建 | 单层 `for` + `continue`（把 pi 的两层压平了） |
| 队列结构 | 两条具名队列（约束在结构里） | 一条队列 + priority 三档（约束在数据里） | 抄 pi 的结构，feature 18 起只留一条 |
| 中途注入 | 内层 while 条件保证同 run 内生效 | 有工具接缝才生效，否则退化成轮末新 query | feature 18 补第二出口，取 pi 的行为 |
| 注入形状 | `messages.push({role:"user"})` | attachment → user 消息（带语气外壳） | push user 消息（语气外壳待补） |
| 步数上限 | 无 | `maxTurns?` 可选，交互模式不设 | `max_steps=20` 硬编码 |
| 打断在跑的工具 | ❌ | `now` 档（仅 SDK 可设，交互式用户走 Esc） | ❌（`InterruptFlag` 是进程级，一按整轮结束） |
