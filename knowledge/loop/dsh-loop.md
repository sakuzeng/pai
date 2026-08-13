# dsh 的 agent loop：一个 inbox + 两个列表 + 两层循环

- 来源：deepseek-harness（github.com/deepseek-ai/deepseek-harness，MIT），**commit `47f9438`**
  —— 该项目自称开发者预览、破坏性变更在即，本篇所有结论只对这个 commit 负责。
  `packages/core/agent-loop/src/agent.ts`(496) / `packages/core/agent/src/inbox.ts` /
  `packages/core/agent/src/types.ts` / `packages/client/ui-conversation/src/client/input/submission-policy.ts` /
  `packages/client/ui-conversation/src/submission-settings.ts` / `packages/host/apiproxy/src/api-proxy.ts` /
  `docs/architecture.zh.md`「轮次流程」一节（**第一方文档**）
- 精读日期：2026-08-13
- pai 锚点：`src/pai/core/loop.py`、`src/pai/core/queue.py`、
  `docs/dev/decisions.md` #68（本篇给它加了第三家参照）、#69（三档证据等级）、
  `docs/dev/features/18-20260813-steering-input`
- 相关：[pi-loop.md](pi-loop.md) 与 [cc-loop.md](cc-loop.md)（同一件事的另两家）、
  [cc-message-queue.md](cc-message-queue.md)（CC 的三档优先级）

> **证据等级声明**（D#69）：dsh 是三家里唯一**源码与设计文档同 commit** 的。
> 本篇凡写「文档说」的都指 `docs/architecture.zh.md`，凡写「源码是」的都带文件:行号。
> 两者本篇未发现打架 —— 但这是**本 commit 的观察，不是保证**。

---

## 0. 一句话

**pi 把队列问在 loop 内、CC 把队列问在 loop 外，dsh 三个出口全在 loop 内**
—— 连 CC 交给 React effect 的那一圈「重开」，dsh 也收进了 agent 自己的 `while`。

⚠️ **本篇更正了 [pi-loop.md](pi-loop.md) 的一句话**：那里写「『在 loop 内部问队列』是 pi
独有的形状」。加进 dsh 之后**「独有」不成立**了。pi-loop.md 关于 pi/CC/pai 三家的对照表本身
没有错，错的只是那个量词 —— 真正独有的是 **CC**：只有它把出口放在了循环之外。

## 1. 术语：dsh 与 pai 同边，与 pi/CC 相反

文档原文（`architecture.zh.md`）：

> 一个**步骤**是一次模型请求加上它调用的工具。一个**轮次**包含零个或多个步骤：
> 它在领取首条输入之前打开，并在不再欠下任何工作时关闭。

对到四家：

| 概念 | dsh | pai | pi | CC |
|---|---|---|---|---|
| 一次模型请求 + 它调的工具 | **step** | **step**（`loop.py`） | turn | turn |
| 消费一条排队消息、做到没活干为止 | **turn** | **turn**（`viz/flow.py`） | **（无名）** 外层 while 的一次迭代 | query |
| 从被唤醒到重新空闲的一整趟 | **（无名）** `kick()` 的一趟 | 无（`run_agent` 一次调用≈一条消息） | **run**（`prompt()` → `agent_end`） | 无 |

**所以 pai 现在的用词与 dsh 完全一致，与 pi/CC 相反。** 需求池里那条「`step` 可以理解为
`turn` 吗、pai 能不能对齐」因此有了新答案：**pai 不需要改**；要改反而是倒向 pi/CC 那套，
而那会同时改掉 `max_steps` 这个公共参数的名字。

> ⚠️ **2026-08-13 修正（用户追问「dsh 的 turn 是不是 pi 的 run」逼出来的）**：
> 本表原来只有两行，把 pi 的 `run` 直接摆在 dsh 的 `turn` 那一格 —— **错了，差一层**。
> **pi 的一个 run 可以装下多个 dsh 意义上的 turn**：`agent-loop.ts:261-265` 拿到 followUp
> 之后是 `continue` 回外层，**仍是同一个 run**，`agent_end` 只在两个队列都空时发一次；
> 而 dsh 每消费一条 `next-turn` 就是一对新的 `turn/start`/`turn/end`（`:319`+`:324-329`）。
>
> **两家各缺一个名字，且缺的正好互补**：
> pi 给「一整趟」起了名（run / `agent_end`）却没给「一条消息」的边界起名 ——
> **那个边界在 pi 的事件流里完全看不见**；dsh 反过来，`turn/*` 精确标着这个边界
> **且是持久会话事件**（可落盘可重放），但「一整趟」只有实时的 `agent/status`
> （`running` ↔ `idle`，`:109`），不进日志。
> CC 的 `query` 对得上 dsh 的 turn（`later` 起的是新 query），这一格原来是对的。

## 2. 两层循环的物理形态

```
kick()   agent.ts:212    while (await this.turn()) {}          ← 外层：turn 循环
turn()   agent.ts:263    while (true) { …一个 step… }          ← 内层：step 循环
```

内层单次迭代（`agent.ts:263-301`，删去中断检查后的骨架）：

```ts
let turnEnds: TurnEndReason | null = null
let target: InboxTarget = 'next-turn'          // :261 首次领取才碰 next-turn
while (true) {
  const decision = await this.preStep(target, { turn, step })   // :266 → inbox.claim()
  if (decision.kind === 'reject') { turnEnds = { kind: 'blocked' }; return false }   // :267
  if (turnEnds && decision.messages.length === 0) break                              // :271
  if (phase.step === 0 && decision.messages.length === 0) { … return false }         // :274
  session.append('step/start', …)                                                    // :279
  for (const m of decision.messages) session.append('user/message', m)               // :282
  const stepEnd = await this.step(decision.assembly)                                 // :287
  if (turnEnds === null || turnEnds.kind !== 'max-tokens') turnEnds = stepEnd        // :290
  session.append('step/end', …)                                                      // :292
  if (turnEnds && this.inbox.nextStep.length === 0)
    await this.dispatch.serial('agent/turn-stopping', { turn, signal })              // :295
  if (turnEnds && this.inbox.nextStep.length === 0) break                            // :299
  target = 'next-step'                                                               // :300
}
```

`step()` 返回 **`null` = 工具还欠一次请求**、非 null = 这个 turn 可以收了
（`:399` `return concluded ? { kind: 'completed' } : null`；`:394` 没有 tool-call 直接
`completed`）。所以 `turnEnds === null` 是「继续」的第一条理由，`nextStep` 非空是第二条。

## 3. 三个出口，全在 loop 内

| 出口 | 位置 | 语义 |
|---|---|---|
| **①** | `:266` `preStep` → `inbox.claim(target, turn)` | **每个 step 边界都领一次**，不是只在工具结果之后 |
| **②** | `:299` `if (turnEnds && this.inbox.nextStep.length === 0) break` | **循环条件本身带「队列非空」** —— 队列有货就不许 break |
| **③** | `:324` `if (!this.inbox.hasPending) return false` → `kick()` 的 `while` | turn/end 之后还有货 → **直接开新 turn**，仍在 agent 自己手里 |

**② 就是 pi 内层 while 的 `|| pendingMessages.length > 0`**（见 [pi-loop.md](pi-loop.md)），
**③ 对应 CC 的「开一个新 query」但位置不同** —— CC 那圈在 `useQueueProcessor`
这个 React effect 里，属于 loop 之外；dsh 的这圈是 `kick()` 的 `while`，属于 loop 之内。
**dsh 没有「loop 之外」这个位置。**

三家的「重开一轮」于是落在三个不同的地方，这是本篇最值得记的一张表：

| | 「重开」发生在哪 | 谁驱动 |
|---|---|---|
| pi | loop 内的回边（同一个 run） | 循环条件 |
| CC | **loop 之外**，起的是新 query | React effect（`useQueueProcessor`） |
| dsh | loop 之外层，但仍在 agent 内 | `kick()` 的 `while (await this.turn())` |
| pai | 两个在 loop 内 + 一个在 loop 外兜底（T4） | 循环条件 + `_drain_queue_after_turn` |

### 3.1 两条不走 `:324` 的短路（容易漏）

`:267`（pre-step 被拒）与 `:274`（首个 step 领到空）走的是 **`return false`**，
不是 `break` —— 于是**跳过 `:324` 的 `hasPending` 检查，inbox 里还有货也不开新 turn**。
兜底在 `kick()` 的 finally：`:220` `if (wakeRequested && this.inbox.hasPending) this.wakeDriver()`。
即「不在这一圈开新 turn，但会重新唤醒 driver」。

`:271` 是第二道守卫：`turnEnds` 已定且这次 claim 领到空 —— 对应「`:299` 时队列非空，
但轮到 claim 时消息被 `remove()` 掉了」。

## 4. inbox：一个对象、两个列表、且**持久化**

`packages/core/agent/src/inbox.ts`：

```ts
type InboxState = Record<InboxTarget, UserMessage[]>   // 'next-turn' | 'next-step'

claim(target, turn) {
  const claimed = this.mutate('next-step', 0, this.nextStep.length, [], false)  // :72 全量抽干
  if (target === 'next-turn') claimed.push(...this.mutate('next-turn', 0, 1, [], false))  // :74 只取 1 条
  …
}
```

**两个列表的取法不对称，这是设计不是巧合**：
- `next-step` —— **全量抽干**（一个 step 边界一次吃掉所有插话）；
- `next-turn` —— **每个 turn 只取 1 条**（一条排队消息 = 一个 turn，turn 的定义就是这么来的）。

**持久化**：构造函数 `:32-39` 从会话事件里重放 `agent/inbox/spliced`，每次 `splice` 都落一条
持久事件。**排队消息重启还在** —— pai 的 `PendingMessageQueue` 是纯内存态，进程一死就没了。

## 5. 三个动词 = 两个正交轴

`agent.ts:113-132`：

```ts
send(message, target: InboxTarget, wakeup: boolean) {
  const wakingAfterAbort = wakeup && this.phase.kind !== 'idle' && this.phase.abort.signal.aborted
  const resolvedTarget = wakingAfterAbort ? 'next-turn' : target      // :117 撞上已 abort 的活动就降级
  this.inbox.splice(resolvedTarget, Infinity, 0, [message])
  if (wakeup) this.wakeDriver(wakingAfterAbort)
}
followup(input) { this.send(input, 'next-turn', true) }    // :123
steer(input)    { this.send(input, 'next-step', true) }    // :127
inject(input)   { this.send(input, 'next-step', false) }   // :131
```

| 动词 | 列表 | 唤醒 | 对到 CC | 对到 pai |
|---|---|---|---|---|
| `followup()` | next-turn | ✔ | `later` | **无**（feature 18 把 followUp 删了，D#68） |
| `steer()` | next-step | ✔ | `next` | `PendingMessageQueue` 入队 |
| `inject()` | next-step | ✘ | **无对应** | **无对应** |

**`inject()` 是 pai/CC 都没有的第四档**：注入上下文但**不惊动 agent**，躺在 inbox 里等下一条
唤醒消息搭车。文档原话：「注入的上下文会留在 inbox 中，直到另一条消息将其唤醒。」
工具执行往队列塞上下文走的就是它（`agent.ts:397` 把 `context => inbox.splice('next-step', …)`
传给 `executeToolCalls`）。

**CC 的三档 vs dsh 的两轴**：CC 的 `now`/`next`/`later` 把「落哪个边界」和「要不要唤醒 / 要不要
打断」揉进**一个枚举**；dsh 拆成**两个布尔轴**，2×2 里实现了 3 格（缺 next-turn + 不唤醒）。
`now` 那档 dsh 不做成优先级，而是单独的 `cancel(cause, { keepInbox })`（`:134`）。

## 6. `agent/turn-stopping`：把 pai 那条前置缺陷做成了公开扩展点

`:295` 在 break 之前发一个 **serial 事件**（无 `next()`，不是 waterfall），监听器可以在这里
`steer()` 一条进去，`:299` 再查一次 `nextStep` 就不会 break —— **同一个 turn 续上一个 step**。

dsh 自己的测试把这条钉死了，且测试名直接写明用途：

- `loop.spec.ts:766` `agent/turn-stopping can steer another step (/loop pattern)`
- `contract-regressions.spec.ts:318` `steer() from an agent/turn-stopping listener continues the same turn`
  ——注释：*the default decision was false (no tools), but steering forced step 2*

**这正是 pai feature 18 修掉的那条前置缺陷的场景**（模型纯答话那轮把队列卡死）。
pai 把它当 bug 修了；dsh 把同一个位置**开成了插件接缝**，`/loop` 这类「自动续跑」的行为
就住在这里。⚠️ 但注意代价：serial 事件里能改循环是否继续 —— 这等于把**停机条件**交给了插件。

## 7. ★ 默认值：dsh 与 CC / pai 相反

这是本篇对 pai 最有直接后果的一条。

| 层 | 事实 | 出处 |
|---|---|---|
| 协议层 | `mode: 'queue' \| 'steer'` 是**必填**，zod 没有 `.default()` —— **harness 不替调用方选** | `api-proxy.ts` 的 `api/sessions.schema.ts:290` |
| 分发层 | `if (mode === 'steer') agent.steer(message) else agent.followup(message)` | `api-proxy.ts:2498-2499` |
| UI 层 | 忙碌时敲**回车 → 默认 `queue`**（= followup = 等你干完），**Cmd/Ctrl+Enter 才是 steer**；不忙 或 传输不支持 steer 时一律 `queue` | `submission-policy.ts:48-57` |
| 默认值 | `DEFAULT_BUSY_ENTER_BEHAVIOR = 'queue'`，且是**用户可配的设置项**（`busyEnter`） | `submission-settings.ts:18` |

对照 [cc-message-queue.md](cc-message-queue.md)：**CC 用户输入默认 `next`（中途注入）**，
理由写在源码注释里 —— *so user input is never starved by system messages*。
pai 的 D#68 抄的正是 CC 这一半。

**两家给了相反的默认值，而且各自都有道理**：
- CC 的「人说话默认优先」成立的前提是**它还有 Esc 这条独立打断路径**，插话不是唯一手势；
- dsh 的「默认排队」成立的前提是**它把两种意图都做成了手势**（Enter / Cmd+Enter）
  并且**允许用户改默认**，于是不必替用户猜。

**对 pai 的直接后果**：D#68 的代价一栏如实记过一句——
「『不要打断你、干完再看』这个意图在 pai 里现在**无法表达**」，复盘已就此立疑，理由是
「没有参照实现，也没有证据说用户需要它」。**这条理由现在被证伪了：dsh 就是参照实现，
而且那是它的默认。** 该不该改 pai 的默认是另一回事（pai 只有两档、没有 Esc 独立路径），
但「没有参照实现」这个论据不能再用。

## 8. 与 pai 的差异清单（可直接当 TODO 读）

| dsh 有 | pai 现状 | 值不值得 |
|---|---|---|
| inbox 持久化（`agent/inbox/spliced` 落会话日志） | 纯内存，进程死即丢 | 与 `--resume` 是同一件事，等 resume 立项时一起算 |
| `inject()`：注入不唤醒 | 无这一档 | pai 目前没有「后台注入」的产出方，先记着 |
| 「等你干完」是**默认**且**可配** | 无法表达（D#68 代价栏） | ★ 直接推翻了 D#68「没有参照实现」这条论据 |
| `agent/turn-stopping` 插件接缝 | 同一位置 pai 是硬编码的出口二 | pai 没有插件系统，暂不适用；但**「停机条件可被扩展」是个值得记的形状** |
| `next-turn` 每 turn 只取 1 条 | `drain()` 一律批量 | pai 只有一条队列，不存在这个区分 |

## 9. 我没验的部分（诚实边界）

- **本篇全部结论来自读源码 + 读第一方文档，没有真跑过 dsh**（未 `pnpm install`）。
  按 roadmap「反向对照」那条固定项，这只算到「读」为止。
- Cordis 的插件装配、`agent/pre-step` 这类 waterfall 的实际监听器分布没查
  —— 本篇只关心 loop 与队列，装配层是 dsh 与 pai **架构不可对拿**的那部分（D#69）。
- `packages/subagent/`、`workflow/` 里是否还有第二条 loop 没查。
