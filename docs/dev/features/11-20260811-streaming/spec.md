# 11-streaming · spec

拍板结果见 [README 的「候选方案与确认」](README.md#候选方案与确认)：
**方案 B（流式 + 能力标志 + 保序并发）、默认开不加开关、两条 05 遗留都不进。**

## 背景与问题

pai 的 loop 每步一次阻塞的 `client.chat.completions.create()`，拿到完整响应才做任何事。
三个后果：

1. **等待期完全没有反馈**。模型思考 + 输出几十秒，终端一片空白。
2. **中断的粒度是「一次请求」**。Ctrl+C 只能停在请求边界，正在生成的那次必须等它跑完。
3. **多个 tool_calls 只能一个个来**。模型一轮发 3 个 `read_file` 是实测发生过的场景
   （TODO R#11 有真实 400 复现路径），串行执行是纯粹的浪费。

前置精读与真实探针另外撞出两条**不修就静默失效**的账（详见
[README 反向对照](README.md#反向对照撞出来的三条)）：DeepSeek 的 usage 只在末块且
`choices` 非空（OpenAI 惯用写法取不到 → 预算熔断与锚点一起哑掉）、
中断掉的流拿不到 usage（消耗恒定少算）。

## 目标（做什么）

1. **流式输出**：`stream=True`，模型文本逐字上屏；中断可掐在流中途。
2. **usage 正确性**：按实测规则取 usage；中断无 usage 的情形显式留痕，不静默。
3. **工具能力标志**：`is_read_only` / `is_concurrency_safe` 进 `@tool` 体系，
   **收 `input` 的函数、默认全 `False`**，挂载方式对齐 feature 09 的 `path_access_for`。
4. **保序并发调度**：连续的并发安全工具合成一批并行执行，其余串行；**结果顺序 = 模型发出的顺序**。
5. **不破任何既有不变量**：`tool_call_id` 严格配对（含中断与权限拒绝路径）、
   工具错误不 throw、离线可测。

## 非目标（明确不做什么）

| 不做 | 理由 |
|---|---|
| 边流边派发（tool_call 一凑齐就开跑） | 拍板选 B。实测最多抢 16% 流时间，而 CC 那套复杂度全为它付 |
| 兄弟取消（一个工具错了杀掉并行的其他工具） | 同上。且它依赖 `Tool.run` 错误契约，本轮不改 |
| `discard()` 半成品丢弃 | pai 没有模型降级回退路径，这条失效路径不存在 |
| `Tool.run` 返回契约（分不出工具内部错误） | 拍板问 3 选甲。单独开 `fix/` 立项 |
| steering 真实输入源 | 拍板问 3 选甲。它要的是输入线程不是流式，真解法在 TUI |
| bash 的只读判定器 | feature 07 已明确不做只读免提示集合（TODO 有记）。所以 bash 的两个标志都是 `False` |
| 流式开关（env / settings.json） | 拍板问 2 选甲：默认开，不加开关 |
| 状态行与流式文本的终端行争用 | 选 B 后两者时间上不重叠，问题不存在（见 README 末节） |
| 跨会话/多线程共享 provider client | 只在一轮内并发工具，不并发调模型 |

## 设计要点

### 1. `core/streaming.py`：装配层

**pi 怎么做**：`packages/agent` 在 provider 层做 SSE 解析，事件化后往上抛。
**CC 怎么做**：走 Anthropic SDK 的事件流（`message_start` / `content_block_delta` / …），
**每个 content block 变成一条独立的 assistant 记录**，共享 `message.id`。
**pai 怎么做**：装配成**一条** assistant 消息，形状与非流式的 `response.choices[0].message` 兼容。

**理由**：这不是省事，是躲开一个 bug。CC 的 `getAssistantMessageId` 存在的唯一原因就是
「一次响应变成了多条记录」——那是它自己的建模选择带来的
（[K concepts/streaming-tool-calls.md](../../../../knowledge/concepts/streaming-tool-calls.md) 第四节）。
pai 保持「一次响应 = 一条 assistant 消息」，这个补丁就永远不需要。
**这条要写进代码注释**：将来谁想为了边流边显示把它拆成多条，得先读到这句话。

装配规则（全部来自[实测](evidence/20260811-流式探针/说明.md)，不是从文档推的）：

- **usage：每块都看 `chunk.usage`，最后一个非空的赢**。
  *不许*写成 `if not chunk.choices: usage = chunk.usage`——DeepSeek 上末块 `choices` 非空，
  这个分支永不触发；也*不许*写成「只看末块」——标准 OpenAI 会给独立块。
  「每块都看」是唯一同时正确的写法。
- **tool_calls 按 `index` 归并**，不按 `id`（`id` 与 `name` 只在该 index 的首块出现）。
- **`arguments` 字符串累积，中途绝不解析**（实测 16 个字符分了 9 块发）。
- 交错到达要能吃下：实测 DeepSeek 是串行分片（index=0 发完才发 index=1），
  但按 index 归并天然兼容交错，**不依赖这个观察**。
- `finish_reason` 出现即收尾。

对外接口：

```python
@dataclass
class StreamedResponse:
    content: str | None
    tool_calls: list[StreamedToolCall]      # .id / .function.name / .function.arguments
    finish_reason: str | None
    usage: dict                              # 空 dict = 这次没拿到（中断）
    interrupted: bool
```

`usage` 用 dict 即可：`compaction.usage_fields()` 已经覆盖 dict 分支，loop 那一侧不用改。

装配器接受 `on_delta: Callable[[str], None]` 与中断标志，逐块调用；
中断置位即停止消费并返回 `interrupted=True`、`usage={}`。

### 2. loop 的改动

- `create(..., stream=True)` → `assemble(...)`，返回上面那个对象；
  下游（`msg.content` / `msg.tool_calls` / 锚点 / session 落盘）**形状不变**。
- **新事件 `MessageDelta(text)`**——`events.py` 开头承诺的那个
  （「砍掉 message_update…等阶段 5 真有『一轮内多次增量』再补」）。
  `render_text` 对它返回 `None`（默认渲染器不管流式上屏，交给 modes 层），
  与「渲染下放 modes 层」（D#39）一致。
- **中断新增一个检查点：每块之间**。中断后仍然要走完既有的收尾路径
  （已完成的工作保留在 messages 里）。
- **中断无 usage 的处理**：`spent_tokens` 不增、锚点不记（现有代码
  `if usage and usage.get("prompt_tokens") is not None` 天然安全），
  但**必须留痕**——往 session 落一条 `{"type": "usage", "step": N, "unmetered": True}`，
  并让 `Interrupted` 事件带上这个事实。
  **理由**：偏差方向是恒定的（总是少算），静默的恒定偏差比随机误差危险得多。

### 3. 能力标志

**CC 怎么做**：`Tool` 接口上 `isReadOnly(input)` / `isConcurrencySafe(input)` 都是**收 input 的函数**
（Bash 是不是只读取决于这次跑 `ls` 还是 `rm`），`buildTool` 统一填默认 `false`。
**pai 怎么做**：照抄这个形状。

```python
@dataclass
class Tool:
    ...
    is_read_only: Optional[Callable[[dict], bool]] = None
    is_concurrency_safe: Optional[Callable[[dict], bool]] = None
```

挂载用 `capabilities_for(read_file, read_only=True, concurrency_safe=True)`，
参数接受 `bool | Callable[[dict], bool]`，内部统一包成 callable。

**为什么不做成装饰器**（feature 09 的 `path_access_for` 是装饰器）：那里装饰的是一个真的
getter 函数；这里绝大多数取值是常量，装饰一个 `lambda args: True` 只是噪音。
**为什么仍保留 callable 形态**：`bash` 将来若有只读判定器，签名不用改。

求值一律防御（照 CC 的 try/catch）：**未声明 → False；调用抛异常 → False；参数不是 dict → False**。
**默认 fail-closed 的代价是慢，不是错**——新加工具忘了声明，最坏结果是它被串行执行。

pai 六个工具的取值：

| 工具 | read_only | concurrency_safe | 理由 |
|---|---|---|---|
| `read_file` | ✅ | ✅ | 纯读 |
| `write_file` / `edit_file` | ❌ | ❌ | 写 |
| `bash` | ❌ | ❌ | **不声明**。CC 是 `isConcurrencySafe = isReadOnly(input)`，而 pai 没有只读命令判定器（feature 07 明确不做），前件不存在就老老实实 False |
| `ask_user_question` | ❌ | ❌ | 要真人；并发问两个问题就是抢输入流 |
| `remember` | ❌ | ❌ | 写文件 + 重建索引 |

### 4. `core/scheduler.py`：保序贪心分批

**CC 怎么做**（`toolOrchestration.ts` 的 `partitionToolCalls`）：折成批——
连续的并发安全工具合成一批并行跑，其余每个自成一批串行跑。**是保序贪心分组，不是重排。**
**pai 怎么做**：一样。

```python
def partition(tool_calls, tools) -> list[Batch]     # 纯函数，可单测
def execute(batches, run_one, max_workers) -> list  # 结果按原顺序回填
```

**为什么保序是硬约束**：模型发出的工具顺序是有意义的（先 `read_file` 再 `edit_file`），
调度只在不改变可观察顺序的前提下偷并行。**并发的是执行，不是交付。**

并发上限 `MAX_TOOL_WORKERS = 8`。**这个数从哪来、依赖什么前提**（TODO 那条
「给照抄来的常数建一条检查习惯」的落实）：CC 默认 10 且可用环境变量调；pai 目前唯一的
并发安全工具是 `read_file`（纯 IO，不吃 CPU），8 是**未实测的经验值**，
实际并发度受限于模型一轮发几个工具（实测见过 3 个）。**改它之前先拿数字。**

### 5. 权限判定**按批前置**（本轮与 CC 的主要偏离）

**CC 怎么做**：权限在 `runToolUse` 内部判，与执行交织。
**pai 怎么做**：**每批开始前，串行判完该批所有工具的权限**，只把 allow 的交给并发执行。

**理由（两条）**：
1. CC 的做法下，同批两个并行工具可能同时要求问真人 —— 正好撞上 TODO 里
   「asker 与 REPL 抢同一个输入流」那条已知缺陷。按批前置让它结构上不存在。
2. **语义变化被限制在批内**：并发批里全是**并发安全的只读工具**，
   它们不改变彼此的权限判定前提。批与批之间仍然保持「先执行前一批、再判定后一批」的顺序，
   所以「工具 A 建了目录，工具 B 才能写进去」这类依赖不受影响。

**诚实边界**：如果将来有工具声明了 `concurrency_safe=True` 却**不是**只读的，
这条论证就不成立了。所以调度器**只把「两个标志都为真」的工具放进并发批**，
而不是只看 `concurrency_safe`——把论证的前提钉死在代码里。

### 6. `SessionLog.append` 加锁

多线程同时往同一个 JSONL 追加。`threading.Lock` 一层，几行。
（三个进程级全局 `set_memory_dir` / `set_notifier` / `set_origin_session` **不需要动**：
装配期写、执行期只读，线程并发下不构成竞争。TODO 里那条担忧核实后不成立，届时去登记。）

### 7. 状态行支持多个 `◐` 并列

`statusline.py` 的 docstring 写着「pai 一次只跑一个工具，所以多个 ◐ 并列不做——那是并发
（阶段 5）的事」。本轮兑现：`render_tool_line` 仍是纯函数
（`(events, width) -> str`，与 TUI 设计原则 1 同构），只是「进行中」不再假定只有一个。

### 8. 测试基建

- `tests/fake_llm.py` 加流式假 provider：`create(stream=True)` 返回 chunk 迭代器。
- **真实轨迹夹具**：从 [evidence 的 `B_parallel_tool_calls.jsonl`](evidence/20260811-流式探针/说明.md)
  剪裁出 tool_calls 分片段 + 末块 usage，内联进测试并注明剪裁规则与出处。
  编的字符串测不出「`arguments` 逐字符分片」「usage 在非空 choices 的末块上」这类真实坑
  —— 这正是 AGENTS.md 要求「至少一条测试拿真实轨迹当输入」的原因。
  evidence 已在版本库内，**溯源链不断在 gitignored 目录里**（STATUS 缺陷 6 那种账不再欠）。

## 验收标准

1. `./test.sh` 全绿（基线 **458 passed, 3 deselected**）。
2. 装配器对**真实 chunk 夹具**跑通：`arguments` 拼接后才解析、按 `index` 归并出 2 个调用。
3. **usage 取法有反向测试钉死**：喂「DeepSeek 形状」（usage 在 choices 非空的末块）与
   「标准 OpenAI 形状」（usage 在 choices 为空的独立块）两种 chunk 序列，**两种都取得到**。
4. 中断掐在流中途：返回 `interrupted=True`、`usage` 为空、`spent_tokens` 不增、
   session 里有 `unmetered` 留痕。
5. 能力标志**默认 False**有测试钉死：新注册一个不声明标志的工具 → 被判为不可并发（串行）。
6. **保序**有测试钉死：`[read, write, read, read]` 分成 4 批还是 3 批、
   结果顺序与 `tool_calls` 顺序逐一对齐。
7. **`tool_call_id` 配对不变量**在「并发 + 中途中断」「并发 + 部分被权限拒绝」两条路径上都不破。
8. **并发是真并发**：用可观测手段证明（如 barrier / 计时），不是「看起来像并行」。
9. 不传新参数时行为与接线前逐字相同（沿用 loop 既有的 keyword-only + 默认 None 约定）。
