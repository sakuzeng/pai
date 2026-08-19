# pi agent 分层、事件与钩子（精读）

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `packages/agent/src/types.ts`（437 行，全部契约在此）、`packages/agent/src/agent.ts`；
  深度对照见外部参照 2（本文不重复）
- 精读日期：2026-08-09 立（指针）→ 2026-08-10 升精读（阶段 2 交付后回流实际读到的东西）
- pai 锚点：`src/pai/core/loop.py`、`src/pai/core/events.py`、`src/pai/core/queue.py`、
  `src/pai/modes/`（roadmap 阶段 2）

为什么升级：这篇原本是指针，只写了「有四层、有双队列」。阶段 2 实现时我实际读了
`agent.ts:123` 的队列实现与 `types.ts:422` 的事件联合，那些结论当时只落进了 features/05
的档案，没回流笔记——登记规约说的「指针升精读的时机：动工时发现指针的结论粒度不够用」
正是这个情形。

## 一、~~四层分层~~ 四个组件（🔴 2026-08-13 更正：原文的分层关系是错的）

🔴 本节原先写的是「四层分层：1 → 2 → 3 → 4」，与源码不符。
`AgentHarness` 不是 `Agent` 的上层，它是 `Agent` 的兄弟——两者各自直接调 `runAgentLoop`。
完整结构与逐个组件的职责见 [pi-loop.md](pi-loop.md) 第一节，本节只留更正与索引。

三条证据：
1. `harness/agent-harness.ts:11` 是 `import { runAgentLoop } from "../agent-loop.ts"`，全文件无 `new Agent`
2. `coding-agent/src/core/agent-session.ts:304` 是 `readonly agent: Agent`——跳过了 `AgentHarness`
3. `grep -rn "AgentHarness" packages/coding-agent/src/` 零命中——它不在 pi 自己的生产链路上，
   使用者是 `packages/agent/test/` 与 `packages/evals/`

错误成因（这条方法论比错误本身值钱）：本节是 2026-08-09 立的指针内容，
08-10 升精读时只回流了第二、三节（事件与队列），第一节没回去核，
而整篇的状态标记已经改成了「精读」。
教训：笔记的状态标记应该到节，不到篇。 升级时没核的部分要显式留标记，
否则「精读」这个标签会替没读过的内容背书。

真实形状（详见 [pi-loop.md](pi-loop.md)）：

```
        agentLoop()  ← 唯一的循环，792 行，零业务
         ↑        ↑
    Agent 类      AgentHarness（自带电池的 SDK 门面，pi 自己不用）
         ↑
   AgentSession → modes/{interactive, print, rpc}
```

- `agentLoop()` —— 无状态纯循环函数（792 行，不含任何业务）
- `Agent` 类 —— 有状态 + 事件订阅 + 两条队列；`createLoopConfig()` 是它与纯循环之间唯一的桥
- `AgentHarness` —— 会话/技能/提示模板/压缩/工具/生命周期，与 `Agent` 平级的另一条组装线
- `AgentSession` —— 应用层编排（interactive / print / rpc 三种模式共用它，
  在 `packages/coding-agent/src/core/agent-session.ts`，不在 packages/agent 下），坐在 `Agent` 上

pai 现状 = `agentLoop` 那一层（`run_agent`）+ 半个 `AgentSession`（`modes/`）；
`Agent` 那一层被 REPL 兼任，`AgentHarness` 那条线整条没有。

## 二、事件：扁平 discriminated union，三层生命周期（`types.ts:422`）

```ts
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages }
  | { type: "turn_start" }
  | { type: "turn_end"; message; toolResults }
  | { type: "message_start"; message }
  | { type: "message_update"; message; assistantMessageEvent }
  | { type: "message_end"; message }
  | { type: "tool_execution_start"; toolCallId; toolName; args }
  | { type: "tool_execution_update"; toolCallId; toolName; args; partialResult }
  | { type: "tool_execution_end"; toolCallId; toolName; result; isError }
```

pai 的取舍与差异（D#39）：pai 取了 8 种、砍掉 `turn_end` 与 `message_update`。
理由是不流式时 `turn_end` 与 `AssistantMessage` 同一时刻同一信息、
`message_update` 更是纯流式产物。代价是阶段 5 补回来时渲染层要改一次。

值得注意的三处形状：

- `tool_execution_*` 三段式（start / update / end），`update` 带 `partialResult`——
  长耗时工具的流式输出靠它。pai 只有 start/end，没有 update。
- `isError` 在事件里是一等字段。pi 能给，因为它的工具结果本身带错误标志；
  pai 的 `Tool.run` 把异常吸收成字符串，所以 `ToolEnd.is_error` 只标得出 loop 自造的错
  ——这条边界的根因就在这里（TODO 已记：改 `Tool.run` 返回契约）。
- `agent_end` 带完整 `messages`，即事件流自身足以重建会话。

## 三、双队列：语义差别在「什么时候问」，不在「队列本身」（`agent.ts:123`）

`PendingMessageQueue` 本体只有 30 行——`enqueue` / `hasItems` / `drain` / `clear`，
构造时定 `mode`。唯一有意思的是 `drain` 的两种模式：

```ts
drain(): AgentMessage[] {
  if (this.mode === "all") { const d = this.messages.slice(); this.messages = []; return d }
  const first = this.messages[0]; if (!first) return []
  this.messages = this.messages.slice(1); return [first]   // "single"
}
```

真正的设计在 `types.ts` 的两个钩子上，注释写死了调用时机：

| 钩子 | 何时被调用（原文要点） |
|---|---|
| `getSteeringMessages()` | 当前 assistant 轮执行完它的 tool calls 之后（除非 `shouldStopAfterTurn` 先退出）。返回的消息在下一次 LLM 调用之前加进上下文。当前 assistant 消息的 tool calls 不会被跳过 |
| `getFollowUpMessages()` | agent 没有更多 tool calls、也没有 steering 消息时。返回非空则加进上下文并继续下一轮 |

两个钩子的契约都写着同一句：must not throw or reject；没有就返回 `[]`。
`getApiKey` 与 `shouldStopAfterTurn` 也各有一句同样的契约。
「钩子不许抛」是 pi 贯穿全套配置的硬约定——pai 的「工具错误不 throw」是同一种思路
在另一个位置的体现。

pai 的实现（feature 05 task 2/5）与之一致：steering 注入点在本轮所有工具结果回填之后
（插在中间会劈开 tool_calls 与结果，配对当场断裂），followUp 在「本该返回」处。
差异：pai 的两个回调是同步函数、默认 `None`；pi 是 async 且必返回数组。

## 四、`AgentLoopConfig` 的全部钩子（pai 只用了一半，另一半是路线图）

| 钩子 | 用途 | pai |
|---|---|---|
| `convertToLlm` | UI-only 消息过滤（发给模型前剔除只给人看的消息） | ❌ 未做 |
| `transformContext` | 压缩挂点 | ⚠️ pai 把压缩直接写进 loop，没抽成钩子 |
| `beforeToolCall` | 权限挂点，返回 block + reason 即拦截 | 🔜 阶段 4 |
| `afterToolCall` | 结果后处理 | ❌ 未做 |
| `getSteeringMessages` / `getFollowUpMessages` | 双队列 | ✅ 阶段 2 已做 |
| `getApiKey` | 每次 LLM 调用动态取 key（为短时 OAuth token 而设，工具执行期间可能过期） | ❌ 见 K model-api/pi-cc-api-keys.md |
| `shouldStopAfterTurn` | 每轮结束后问一次「要不要优雅停机」，返回 true 则发 `agent_end` 并在轮询两个队列之前退出。注释举的例子正是「上下文快满之前」 | ❌ 未做 |
| `prepareNextTurn` | 在 `turn_end` 之后、决定是否发下一次请求之前，返回替换的上下文/模型/thinking 状态 | ❌ 未做 |
| 工具执行模式 | `"sequential"` / `"parallel"`（并行时先顺序预检、再并发执行；`tool_execution_end` 按完成序发，工具结果消息按 assistant 源序发） | 🔜 阶段 5 |

`shouldStopAfterTurn` 与 `prepareNextTurn` 是这次重读的新收获：pai 现在把
「该不该压缩」「压缩后怎么办」都硬写在 loop 的循环体里；pi 把这两个时机做成了钩子，
于是压缩、换模型、优雅停机都是同一个挂点上的不同实现。
pai 若将来要做「切换模型」或「上下文满了优雅收尾」，这是现成的形状。

## 五、TUI 侧的 pi 事实（原指针内容，保留）

- `Component.render(width) -> list[str]` 是唯一必须实现的契约；不用 React/Ink，
  pi-tui 运行时依赖只有 marked + get-east-asian-width
  （宽度计算为什么要单独引一个包，见 K tui/terminal-width.md）。
- CURSOR_MARKER 技巧：焦点组件在光标位置吐零宽 APC 序列，TUI 扫描剥离后把硬件光标
  定位过去——IME（中文输入）候选框位置正确的关键。
- main-screen（渲染进主屏 + scrollback）与 alt-screen 两种模式；
  `tui-plan.md`（仓库根，36KB）明写「不要给 main-screen 假装有 sticky/nested-scroll 语义」。
