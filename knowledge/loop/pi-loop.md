# pi 的 agent loop：一个纯循环 + 两条并行组装线

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `packages/agent/src/agent-loop.ts`(792) / `agent.ts`(577) / `types.ts`(437) /
  `harness/agent-harness.ts`(1185) / `packages/coding-agent/src/core/agent-session.ts`(3332) /
  `modes/interactive/interactive-mode.ts`
- 精读日期：2026-08-13
- pai 锚点：`src/pai/core/loop.py`、`src/pai/core/queue.py`、`src/pai/modes/interactive.py`、
  `docs/dev/features/18-20260813-steering-input`
- 相关：[cc-loop.md](cc-loop.md)（同一件事的 CC 版）、
  [pi-agentloop.md](pi-agentloop.md)（事件与钩子的清单，本篇不重复）、
  [cc-message-queue.md](cc-message-queue.md)（队列细节）

本篇与 `loop/pi-agentloop.md` 的分工：那篇是清单（十种事件、八个钩子逐条列），
本篇是结构与运行时（谁调谁、循环怎么转、一次运行的边界在哪）。

🔴 本篇更正了 `pi-agentloop.md:15-23` 的一处结构错误。那里把四者写成
「1→2→3→4 四层分层」，源码不支持。详见第一节。
错误成因：那句是 2026-08-09 立的指针，08-10 升精读时只回流了事件与队列两节，
第一节的分层图没回去核，而整篇的状态已经标成「精读」。
教训：笔记的状态标记应该到节，不到篇。

---

## 一、结构：不是四层栈，是一个纯循环带两条并行组装线

```
                    agentLoop() / runAgentLoop()        ← 唯一的循环，792 行，零业务
                          agent-loop.ts
                           ↑         ↑
             agent.ts 调 ──┘         └── agent-harness.ts:11 调
                  │                            │
              Agent 类                    AgentHarness
           (agent.ts, 577)              (harness/, 3013)
                  │                     「自带电池」的 SDK 门面
   agent-session.ts:304                        │
   `readonly agent: Agent`                使用者：packages/agent/test/
                  │                            + packages/evals/
            AgentSession                  ← pi 自己的 coding-agent 里
      (coding-agent/core/, 3332)            grep 零命中，不在生产链路
                  │
    modes/{interactive, print-mode.ts, rpc}
```

证据三条：
1. `harness/agent-harness.ts:11` 是 `import { runAgentLoop } from "../agent-loop.ts"`，全文件无 `new Agent`
2. `coding-agent/src/core/agent-session.ts:304` 是 `readonly agent: Agent`——跳过了 AgentHarness
3. `grep -rn "AgentHarness" packages/coding-agent/src/` 零命中

### 四者各自干什么

| | 持有什么 | 对外是什么 |
|---|---|---|
| `agentLoop()` | 什么都不持有。状态从参数进，事件从 `EventStream` 出 | 一个函数：`(prompts, context, config, signal, streamFn) → EventStream<AgentEvent, AgentMessage[]>` |
| `Agent` | 状态 `_state`、两条队列、订阅者集合、一排钩子字段 | 有状态的外壳：`prompt()` / `steer()` / `followUp()` / `abort()` / `subscribe()` |
| `AgentHarness` | `session`（持久化）、`models`、tools、`resources`（skills/模板）、三条队列、`phase` 状态机、retry、shutdown | 任务级 API：`prompt()` / `skill()` / `compact()` / `navigateTree()` / `requestShutdown()` |
| `AgentSession` | `readonly agent: Agent` + coding-agent 特有的一切 | 应用层，三种运行模式共用 |

`Agent` 这一层的全部意义就两个方法：

- `createLoopConfig()`（`agent.ts:434`） —— 把自己的字段打包成纯循环要的 `config`。
  这是「有状态外壳」与「无状态循环」之间唯一的桥。
- `processEvents()`（`agent.ts:529-576`） —— 事件流经这里时顺手改状态再转发给订阅者：
  `message_start/update` 更新 `streamingMessage`、`message_end` 推进 `messages`、
  `tool_execution_start/end` 增删 `pendingToolCalls` 集合、`turn_end` 捞 `errorMessage`、
  `agent_end` 清场。

`AgentSession` 的文件头 docstring 把第四层的定位写全了（`:1-14`）：

*"Core abstraction for agent lifecycle and session management. This class is shared between
all run modes (interactive, print, rpc). … Modes use this class and add their own I/O
layer on top."*

一份编排、三种 I/O —— 这正是 pai 的 `modes/once.py`（对应 print-mode）与 `modes/interactive.py` 的出处。

## 二、三个术语：agent / run / turn

| 层 | 边界 | 判据 |
|---|---|---|
| agent | `Agent` 实例的一生（一个进程一个） | 常驻对象，不是模型也不是某轮对话 |
| run | 一次 `prompt()` → `agent_end` | `activeRun` 存在 / `_state.isStreaming` 为真（`agent.ts:471-520`） |
| turn | 一次 LLM 请求 + 它引发的全部工具执行 + 结果回填 | `turn_start` → `turn_end`（`turn_end` 带 `{ message, toolResults }`） |

- 一次 run 里通常有多个 turn（模型调一次工具就多一个 turn）
- 一个 turn 里可以有多个工具调用——它们全属于同一个 turn
- 对话历史 `_state.messages` 跨 run 保留：`finishRun()`（`:514-520`）只清
  `isStreaming` / `streamingMessage` / `pendingToolCalls`，没碰 messages。
  所以「新 run」≠「新对话」。

⚠️ 一个容易看漏的坑（`agent-loop.ts:176-181`）：第一个 turn 不发 `turn_start`——
```ts
if (!firstTurn) { await emit({ type: "turn_start" }) } else { firstTurn = false }
```
因为 `agent_start` 已经覆盖了它。订阅事件流做 UI 时，turn 数不能靠数 `turn_start`，会少一个。

## 三、循环骨架：两层 while，双队列语义的物理形态

`agent-loop.ts:155-275` 的 `runLoop`：

```
pendingMessages = await getSteeringMessages()          :167  ← 开跑前先问一次
                                                             注释：user may have typed while waiting

while (true) {                                          :170 ← 外层：followUp
  hasMoreToolCalls = true                               :171
  while (hasMoreToolCalls || pendingMessages.length) {  :174 ← 内层：turn
      emit turn_start（首轮跳过）                        :176-181
      注入 pendingMessages 进 context                    :183-192
      message = await streamAssistantResponse(...)      :195  ← 一次 LLM 请求
      if (stopReason 是 error/aborted) → agent_end 返回  :198-202
      toolCalls = message 里的 toolCall                  :205
      hasMoreToolCalls = false                          :207
      if (toolCalls.length > 0) {
          stopReason === "length"
              ? failToolCallsFromTruncatedMessage(...)  :213 ← 见下「值得偷的一条」
              : executeToolCalls(...)                   :214
          结果全部 push 进 currentContext                :217-220
      }
      emit turn_end { message, toolResults }            :220
      config.prepareNextTurn?.()  → 可换 context/model/thinking  :222-243
      if (await config.shouldStopAfterTurn?.()) → agent_end 返回  :245-255
      pendingMessages = await getSteeringMessages()     :257  ← 每轮末问 steering
  }
  followUpMessages = await getFollowUpMessages()        :261  ← 只在这问一次
  if (followUpMessages.length) {
      pendingMessages = followUpMessages                :264
      continue                                          :265  ← 外层再转一圈
  }
  break
}
emit agent_end
```

### 🔑 两层 while 就是双队列的语义

内层条件 `hasMoreToolCalls || pendingMessages.length > 0` 是整个设计的支点：

- 模型还在发工具调用 → `hasMoreToolCalls` 真 → 内层继续（agent 正在干活）
- `:257` poll 到 steering → `pendingMessages` 非空 → 内层条件照样为真，退不出去
- 两个都空 → 内层退出（agent 干完了）→ 外层这才问 followUp

推论（这条对 pai 至关重要）：即使模型某一轮不调任何工具、直接给出最终答案，
只要 steering 队列非空，内层就不会退出——你的话一定在同一个 run 内被用上。

🔴 pai 缺的正是这一条：pai 把两层 while 压成单层 `for` + `continue`，
于是「不发 tool_calls 就 `return`」（`loop.py:283-289`）发生在 steering poll（`:352`）之前。
模型某轮直接作答时，队列里的 steering 消息永久卡死。
这是 feature 18 的前置缺陷，修法就是把上面这个 `||` 条件补回来。

### 🔑 与 CC 的结构性分歧：两个队列出口都在 loop 内部

⚠️ 2026-08-13 更正（[dsh-loop.md](dsh-loop.md)）：本节原标题与末尾结论都写着
「是 pi 独有的」。加进第三参照源 dsh 之后这个量词不成立 —— dsh 的 `:299`
`if (turnEnds && this.inbox.nextStep.length === 0) break` 同样是「循环条件带队列非空」。
下面这张三家对照表本身没有错，错的只是「独有」。 真正独有的是 CC：
四家里只有它把出口放在了循环之外。

上面那个 `||` 条件不只是「少了一个判断」，它标定了 pi 与 CC 的分界：

| | 队列出口在哪 | 循环条件看队列吗 | 后果 |
|---|---|---|---|
| pi | 两个都在 loop 内部：`:257` 问 steering、`:261` 问 followUp | ✅ `hasMoreToolCalls \|\| pendingMessages.length > 0` | 不退化——模型不调工具那轮也在同一个 run 内注入 |
| CC | 只有 mid-turn 那个在 loop 内；另一个（`useQueueProcessor`）在 loop 之外 | ❌ 没有 tool_calls 就直接 `return`，队列压根不问 | `next` 退化成 `later`，只能开一个新 query |
| pai（feature 18 后） | 出口一在 loop 内、出口二（T2）也在 loop 内、T4 兜底在 loop 外 | ✅ 取 pi 的做法 | 不退化 |

所以「在 loop 内部问队列拿到就重开一轮」是 pi 与 dsh 共有、CC 没有的形状
（原文写「pi 独有」，见本节开头的更正）。
CC 与 pai 都把「agent 已经停了之后怎么办」挪到了 loop 外面——
那已经不是同一次运行了（CC 的 `turnCount` 归零；pai 是 `run_agent` 重新调一次）。

⚠️ 不要说「CC 有 followUpQueue」——CC 只有一条 `commandQueue`，`later` 是它的一个
priority 值，且那个出口在循环之外。详见 [cc-loop.md](cc-loop.md) 第三节。
（2026-08-13 画三家对照图时，正是在这里把 pi 的语义误套给了 CC，返工两次才对。）

### 两个钩子的调用时机（`types.ts:228-252`，doc comment 即契约）

| 钩子 | 原文要点 |
|---|---|
| `getSteeringMessages()` | 当前 assistant 轮执行完它的 tool calls 之后调用（除非 `shouldStopAfterTurn` 先退出）；返回的消息在下一次 LLM 调用之前加进上下文；当前消息的 tool calls 不会被跳过。*"Use this for 'steering' the agent while it's working."* |
| `getFollowUpMessages()` | agent 没有更多 tool calls、也没有 steering 消息时调用；返回非空则加进上下文并继续下一轮。*"…messages that should wait until the agent finishes."* |

两者契约都写着 `must not throw or reject`，没有就返回 `[]`。
「钩子不许抛」是 pi 贯穿全套配置的硬约定——pai 的「工具错误不 throw，转成字符串结果」
（`tools/__init__.py:133-140`）是同一种思路在另一个位置的体现。

### 谁决定进哪条队列：调用方，不是循环

`Agent` 上是两个独立的公开方法（`agent.ts:274-282`）：

```ts
/** Queue a message to be injected after the current assistant turn finishes. */
steer(message: AgentMessage): void   { this.steeringQueue.enqueue(message); }
/** Queue a message to run only after the agent would otherwise stop. */
followUp(message: AgentMessage): void { this.followUpQueue.enqueue(message); }
```

没有任何逻辑根据「agent 现在在干什么」替你选。
`AgentSession.prompt()` 甚至在 agent 忙时强制你表态（`agent-session.ts:1159-1163`）：

`"Agent is already processing. Specify streamingBehavior ('steer' or 'followUp') to queue the message."`

但 pi 自己的交互模式做了跟 CC 一样的默认选择（`interactive-mode.ts`）：

| 键 | 代码 | 进哪条 |
|---|---|---|
| Enter（默认） | `:2892-2895` `prompt(text, { streamingBehavior: "steer" })` | steering |
| Alt+Enter | `:3820-3823` `prompt(text, { streamingBehavior: "followUp" })` | followUp |

消息结构上带 `mode: "steer" \| "followUp"` 字段（`:201`），`:4129-4132` 的 if/else 照它分派。
`Alt+Enter` 在空闲时退化成普通 Enter（`:3827`：*"If not streaming, Alt+Enter acts like regular Enter"*）——
不忙的时候两个键没区别，避免用户记错。

所以「pi 把选择推给集成方」只对框架层成立；pi 的 UI 层与 CC 同款：
忙时人说话，默认就是中途插进去。这是两家一致的默认值，比单看 CC 更有说服力。

## 四、`AgentLoopConfig` 的钩子全表（pai 只用了一半）

| 钩子 | 用途 | pai |
|---|---|---|
| `getSteeringMessages` / `getFollowUpMessages` | 双队列 | ✅ 有注入点（steering 待 feature 18 通电） |
| `beforeToolCall` | 权限挂点，返回 block + reason 即拦截 | ✅ `loop.py:108` |
| `afterToolCall` | 结果后处理 | ❌ |
| `transformContext` | 压缩挂点 | ⚠️ pai 把压缩硬写进 loop 循环体，没抽成钩子 |
| `shouldStopAfterTurn` | 每轮末问一次「要不要优雅停机」，注释举的例子正是「上下文快满之前」 | ❌ |
| `prepareNextTurn` | 在 `turn_end` 之后、决定是否发下一次请求之前，返回替换的 context / model / thinking 档 | ❌ |
| `convertToLlm` | UI-only 消息过滤（发给模型前剔除只给人看的消息） | ❌ |
| `getApiKey` | 每次 LLM 调用动态取 key（为短时 OAuth token 而设） | ❌ |

最值得讲的一条自我批评：pi 把「该不该压缩」「压缩后怎么办」做成了
`shouldStopAfterTurn` / `prepareNextTurn` 两个钩子，于是压缩、换模型、优雅停机
都是同一个挂点上的不同实现。pai 是硬写在循环体里的。
将来要做「切换模型」或「上下文满了优雅收尾」，pi 那个形状是现成的。

## 五、两条 pai 该知道的细节

① 截断的 tool_call 全部判失败（`agent-loop.ts:207-216`）

```ts
// A "length" stop means the output was cut off by the token limit, so
// every tool call in the message may carry truncated arguments. Fail
// them all instead of executing potentially borked calls.
message.stopReason === "length"
    ? await failToolCallsFromTruncatedMessage(toolCalls, emit)
    : await executeToolCalls(...)
```

🔴 pai 没有这条：`streaming.assemble` 拼完 `arguments` 就解析，解析失败才报错——
一个恰好截在合法 JSON 边界上的残参数会被照常执行。已登记 TODO。

② 没有步数上限。 `agent-loop.ts` 与 `types.ts` 全文检索 `maxSteps` / `maxTurns` / `maxIterations` 零命中。
pi 靠 `shouldStopAfterTurn` 让调用方自己决定何时停。
pai 硬编码 `max_steps=20`；CC 有可选的 `maxTurns`（交互模式默认不设）。三家三个答案。

## 六、pai 站在哪

pai = 第 ① 层（`run_agent`）+ 一部分第 ④ 层（`modes/`），第 ② 层被 REPL 兼任，
第 ③ 层那条并行线整条没有（skills / session 管理正是 `AgentHarness` 的内容）。

第 ② 层被兼任的代价已经咬过一次：`messages` 必须原地替换 `messages[:]` 而不是换绑
（`loop.py:199, :435-438`）——REPL 跨轮持有的是同一个列表对象，换绑的话续轮拿到的还是压缩前的历史。
「谁持有这个对象」这类问题，在 pi 里由 `Agent` 那一层统一回答；pai 没有那一层，就得每处自己小心。
