# CC 的流式工具执行走读：工具在模型还没说完的时候就开跑

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `src/services/tools/StreamingToolExecutor.ts`(530) / `toolOrchestration.ts`(188)、
  `src/Tool.ts`(792) 的能力标志与 `buildTool` 默认值、`src/query.ts` 的驱动点、
  `src/utils/tokens.ts` 的 `getAssistantMessageId`
  （符号名检索，反编译行号会漂；`toolExecution.ts` 1745 行本篇不覆盖）
- 精读日期：2026-08-11
- pai 锚点：`src/pai/core/loop.py`、`src/pai/core/tools/__init__.py`（`@tool` 装饰器）、
  docs/dev/features/11-20260811-streaming（阶段 5）

为什么读这篇：roadmap 阶段 5 的「参照」栏点名了这两个文件，而阶段 5 的范围里有一条
「工具能力标志进 `@tool`，调度靠标志不靠 if-else 判工具名」——这句话是从哪来的、
标志到底被谁消费、默认值该怎么定，不走一遍源码就只能照抄名字。

## 一、`isReadOnly` / `isConcurrencySafe` 是函数不是布尔字段

`Tool` 接口上两者的签名都收 `input`：

```
isConcurrencySafe(input): boolean
isReadOnly(input): boolean
```

收 input 是关键。`Bash` 是不是只读，取决于这次跑的是 `ls` 还是 `rm -rf`——
静态布尔表达不了。这与 pai 在 feature 09 定的
「匹配语义下放给工具」（[D#52](../../docs/dev/decisions.md)、`get_path`/`access`）是同一个模式：
框架问问题，工具用自己的领域知识回答。

`buildTool` 集中填默认值，注释自称 fail-closed where it matters：

| 方法 | 默认 | 读出来的意思 |
|---|---|---|
| `isEnabled` | `true` | 装了就能用 |
| `isConcurrencySafe` | `false` | 假定不安全 |
| `isReadOnly` | `false` | 假定会写 |
| `isDestructive` | `false` | 只有不可逆操作（删/覆盖/发送）才置 true |
| `checkPermissions` | allow | 让位给通用权限系统（不是「放行」，是「本工具没有额外意见」） |

默认全 false，忘了声明就退化成串行 + 当写操作看待——代价是慢，不是错。
`FileEditTool` / `FileWriteTool` 干脆一个都不声明，靠的就是这个默认。

### 两个标志不是独立的

`BashTool` 的实现直接把并发安全定义成只读：

```
isConcurrencySafe(input) { return this.isReadOnly?.(input) ?? false }
isReadOnly(input)        { /* 拆复合命令 → 只读约束检查 → allow 才算只读 */ }
```

`AgentTool` 反着来且理由写在注释里：`isReadOnly` 返回 true，注释说
「权限检查委托给它底下的工具」——即这里的「只读」是对本层而言，不是对世界而言。
`FileReadTool` / `GlobTool` / `GrepTool` 两者都 true；`AskUserQuestionTool`、
`ExitPlanMode`、`McpAuth` 这类会改会话状态的都 false。

### 消费者只有两处，而且分得很干净

- `isConcurrencySafe` → 只被两个执行器读（`StreamingToolExecutor` 与 `toolOrchestration`），
  纯粹是调度输入；
- `isReadOnly` → 被 UI（权限对话框怎么显示）、`--print` 的工具清单、
  以及记忆抽取（只读工具的调用才拿来抽记忆）读。

同一个事实两个用途、互不耦合——这是「下放给工具」能成立的原因：
工具只需回答一个关于自己的问题，不需要知道谁在问。

两个调用点都套了同一层防御：先 `inputSchema.safeParse`，解析失败 → 不安全；
调用抛异常 → `catch` 掉当不安全。注释点名了真实来源：shell 词法解析可能失败。

## 二、`toolOrchestration.ts`：非流式路径的分批

`partitionToolCalls` 把一轮里的多个 tool_use 折成批：连续的并发安全工具合成一批并行跑，
其余每个自成一批串行跑。注意是「连续」——顺序被保留，一个非安全工具会把前后切开。
并发上限 `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY`，默认 10。

这是保序的贪心分组，不是重排。想清楚一点：模型发出的工具顺序被当作有意义的，
调度只在不改变可观察顺序的前提下偷并行。

## 三、`StreamingToolExecutor.ts`：把「等模型说完」这一步删掉

驱动点在 `query.ts`：流式解析出的每条 assistant 消息，其中的 `tool_use` block 一到手就
`addTool(block, message)`，同一轮里后面的 block 还在流。所以工具执行与模型输出是重叠的。
类注释写明三条契约：并发安全的工具彼此可并行、非并发安全的工具独占执行、
结果按工具到达顺序缓冲后再吐（并行执行但不并行交付，顺序对模型可见）。

状态机 `queued → executing → completed → yielded`，几处值得抄的判断：

- `canExecuteTool`：当前没有在跑的工具，或者（本工具安全 且 在跑的全都安全）；
- `processQueue` 遍历队列时，遇到跑不了的非安全工具就 `break`——不能跳过它去跑后面的，
  否则顺序就破了。安全工具跑不了则只是 `continue`；
- `getCompletedResults` 吐结果时同理：碰上正在执行的非安全工具就停，保证交付顺序。

### 出错了杀谁：只有 Bash 会牵连兄弟

`siblingAbortController` 是 `toolUseContext.abortController` 的子控制器，注释把语义写死了：
abort 子控制器不会 abort 父控制器——即杀掉兄弟任务，但不把「取消」向上传播、
不结束这一轮（roadmap 阶段 5 写的「子 AbortController 思路」就是这个）。

而且只有 Bash 的错误会触发，注释给了理由：bash 命令之间常有隐含依赖链
（`mkdir` 失败 → 后续命令没意义），而 Read/WebFetch 这类彼此独立，
一个失败不该把其余的全毁掉。被牵连的工具收到的是合成的 tool_result
（`Cancelled: parallel tool call X errored`，`is_error: true`）——
注意它仍然是一条格式合法的 tool_result，tool_call_id 配对不会因取消而破。

合成错误分三种来源：`sibling_error` / `user_interrupted` / `streaming_fallback`，
措辞各不相同（用户主动拒绝时用 REJECT_MESSAGE，UI 才能显示「用户拒绝了编辑」
而不是「编辑文件出错」）。

### 中断的粒度：工具自己说要不要被打断

`interruptBehavior(): 'cancel' | 'block'`，默认 `block`（不实现就是不许打断，
新消息排队等着）。只有声明 `cancel` 的工具会在用户中途发消息时被取消。
`getAbortReason` 里有个细节：abort 的 `reason === 'interrupt'`（用户干活时打字）
只取消 `cancel` 类工具，其余返回 `null` 继续跑。

### 流式回退时要丢掉半成品

`discard()` + 重建执行器。注释说的问题很具体：回退后新响应带来的是新的 tool_use_id，
旧执行器里在跑的工具吐出来的 tool_result 会变成孤儿（配不上任何 tool_call）。
配对不变量在流式下多了这条失效路径。

## 四、`getAssistantMessageId`：这条不适用于 pai，但值得知道为什么

pai 的 TODO 里有条「接流式前必修：并行工具调用会让 usage 重复累加」，出处就是这里。
读了源码 + 真跑一次 DeepSeek 之后，结论要改写：

CC 的成因是 Anthropic 协议的形状——流式并行工具调用时，每个 content block 会成为
一条独立的 assistant 记录，但它们共享同一个 `message.id`。于是从后往前找
「最后一次真实 usage」当锚点时，会锚在同一个响应的最后一个分片上，
而该分片的 usage 其实覆盖了前面几个分片的内容 → 前面那些分片被估算重复计入。
`getAssistantMessageId` 的用法是：找到锚之后继续往前走，只要 id 相同就把锚往前挪，
挪到同一响应的第一个分片为止；遇到 id 不同的响应才停；中间夹着的 user/tool_result 不算断点。

pai 走 OpenAI 兼容协议，一次流式响应只产生一份 usage（实测见
[features/11 的探针证据](../../docs/dev/features/11-20260811-streaming/evidence/20260811-流式探针/说明.md)
B 与 C：2 个并行 tool_calls、1 份 usage，流式与非流式一致）。
所以那条 TODO 的前提不成立——它描述的不是「流式的固有问题」，
而是「CC 选择了 block 级消息记录」的后果。pai 只要保持「一次响应组装成一条 assistant 消息」，
这个问题就不存在；反过来说，如果 pai 将来为了边流边显示而拆成多条记录，就会自己造出这个 bug。

## 五、抄什么、不抄什么（pai 视角）

| CC 的做法 | pai 打算怎么办 |
|---|---|
| 能力标志是收 input 的函数，默认全 false | 抄。与 feature 09 的 `get_path`/`access` 同一个模式，形状已有先例 |
| 并发安全 = 只读（Bash） | 抄这个推导方向，但 pai 的 `bash` 目前没有只读判定器（feature 07 明确不做只读免提示集合，见 TODO） |
| 保序贪心分批 | 抄。顺序是模型的意图，调度不该重排 |
| 只有 Bash 错误牵连兄弟 | 抄，且抄它的理由（隐含依赖链），不要写成「出错就全杀」 |
| 子 AbortController 不向上传播 | 抄语义；pai 的中断是进程级标志（[D#40](../../docs/dev/decisions.md)），需要设计一层「本轮取消」 |
| `interruptBehavior` 默认 block | 待评估。pai 现在的中断是「查标志」轮询，粒度不同 |
| `getAssistantMessageId` 去重 | 不抄（见第四节，协议不同，抄了是给自己加不存在的补丁） |
| 流式回退 `discard()` | 待评估。pai 没有模型降级回退路径，暂时没有这条失效路径 |
