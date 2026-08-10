# 11-streaming —— 流式输出 + 工具执行调度

状态：已交付（2026-08-11，方案 B，6 task TDD，509 passed；复盘见 [复盘.md](复盘.md)）
分支：`feat/11-streaming`（自 `main` 开出，承担立档案 → 前置精读 → brainstorm → 实现全程）

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

**用户原话**（2026-08-11，开工指令节选）：

> 开始 pai 项目的阶段 5（流式）。
>
> 三件事按顺序做，**每一步做完停下来等我**：
> 1. 立档案 …… 状态「讨论中」，`.active` 切过去。
> 2. 补前置精读——roadmap 阶段 5 的清单只有一条且没打勾（官方 streaming 章节）。
>    本地有 CC 源码 `~/improve/coding/agent/projects/claude-code-source-code`，
>    重点看 `src/services/tools/StreamingToolExecutor.ts` 与 `src/Tool.ts` 的
>    `isConcurrencySafe` / `isReadOnly`（符号名检索，行号会漂）。
>    笔记进 `knowledge/` 并登记 README，roadmap 清单打勾。
>    feature 09 的教训：那次精读覆盖了文档每一节却漏掉整整一层机制，
>    所以精读之后要做一次「反向对照」——拿几个真实场景跑一遍看行为对不对。
> 3. brainstorm：候选方案 ≥2 个讲给我，我拍板后你再写 spec。
>    已知必须进范围的两条：
>    - TODO 里标着「接流式前必修」的并行工具调用 usage 重复累加（影响预算熔断正确性）
>    - 工具能力标志 `is_read_only` / `is_concurrency_safe` 进 `@tool`
>      （照 feature 09 的 `get_path`/`access` 那个「下放给工具」的模式）
>    feature 05 REPL 留的两条遗留也与流式直接相关，评估是否一并解决：
>    steering 有注入点无输入源、`Tool.run` 返回契约分不出工具内部错误

对应 [roadmap 阶段 5 · 流式](../../roadmap.md)。

### 已知必须进范围（用户指定）

| 条目 | 出处 | 为什么与流式绑死 |
|---|---|---|
| 并行工具调用的 usage 重复累加 | TODO P3「接流式前必修」（2026-08-03，CC `utils/tokens.ts:28`） | 流式下每个 content block 成为独立 assistant 记录但共享 `message.id`，天真累加＝重复计费，**直接影响预算熔断的正确性** |
| 工具能力标志 `is_read_only` / `is_concurrency_safe` 进 `@tool` | roadmap 阶段 5 范围；CC `src/Tool.ts` | 调度靠标志不靠 if-else 判工具名；模式照 feature 09 的 `get_path`/`access`「下放给工具」（[D#52](../../decisions.md)） |

### 待评估是否一并解决（用户点名，brainstorm 时给结论）

| 条目 | 出处 | 与流式的关系 |
|---|---|---|
| steering 队列有注入点无真实输入源 | TODO「feature 05 遗留」（05 拍板问 2） | 阻塞 `input()` 拿不到「agent 干活时打字」，当时明确记着「等 TUI/流式阶段接真实输入源时才通电」 |
| `Tool.run` 返回契约分不出工具内部错误 | TODO「feature 05 遗留」（05 task 1） | 工具内部异常被吸收成「错误：…」字符串，状态行标不出红叉；流式下工具调度要按成败决定要不要杀兄弟任务 |

### 验收标准

拍板后的完整清单见 [spec.md「验收标准」](spec.md#验收标准)（9 条）。要点：
`./test.sh` 全绿（基线 458）、装配器对**真实 chunk 夹具**跑通、**usage 两种协议形状都取得到**、
中断无 usage 有显式留痕、能力标志默认 False、保序、`tool_call_id` 配对在并发+中断下不破、
并发是**可观测的**真并发。

> 立项时写的第 2 条「并行工具调用下 usage 不重复累加」**已作废**——前提被实测推翻，
> 见下文「反向对照撞出来的三条」。原文留档，不删。

## 候选方案与确认

### 讨论的起点：三个事实改变了阶段 5 的形状

brainstorm 前先做了[前置精读](#用到的知识)与真实探针，结果推翻了立项时对本阶段的三条认知：

1. **「并行工具调用 usage 重复累加」不是流式问题**，是 Anthropic 协议的形状带来的
   （详见上文「反向对照撞出来的三条」）。它被**替换**成两条真的：
   末块取法（`include_usage` 空操作 → OpenAI 惯用写法拿不到 usage）、中断的流没有 usage。
   这两条**任何方案都必须做**，不再是「选项」。
2. **roadmap 阶段 5 的目标写着「流式输出 + 工具执行中断」，而工具执行中断在
   [feature 05](../05-20260810-repl/README.md) 就交付了**（进程组 + 轮询标志 + bash 中途可杀）。
   阶段 5 真正剩下的是**流式输出**与**并发调度**。
3. **「边流边派发」对 pai 的收益远小于对 CC**。探针 B 的实测位置：76 个 chunk 里前 54 块
   全是 reasoning + content，第一个 tool_call 分片在 **#55**，index=0 拼完在 **#64**，
   最后一个在 **#74**。即「不等模型说完就开跑」最多抢到 **12/76 ≈ 16%** 的流时间——
   而 CC 那套复杂度（半成品丢弃、孤儿 tool_result、兄弟取消）全是为它付的。
   （按 chunk 位置估算，**没测真实墙钟**，是比例不是秒数。）

### 方案 A · 薄流式（只做输出）

新增 `core/streaming.py` 纯函数装配器（按 `index` 归并 tool_calls、`arguments` 拼接后解析、
每块都看 `usage`），loop 的 `create()` 换成流式，events 补上当初被砍掉的增量事件
（`events.py` 第 5-8 行原话：「等阶段 5 真有『一轮内多次增量』再补」）。**工具执行一字不动。**

代价：**与「能力标志」互斥**——标志挂上去没有消费者就是死代码；阶段 5 只做一半，并发另开一轮。

### 方案 B · 流式 + 能力标志 + 保序并发

A 全部，加上照 CC 的能力标志（**收 `input` 的函数**、默认全 `False`、挂载方式对齐 feature 09 的
`path_access_for`）+ 保序贪心分批调度（连续的并发安全工具合成一批并行，其余串行，**不重排**）。

一处**故意偏离 CC**：**权限判定按批前置**，只把已 allow 的派发给调度器。CC 是在
`runToolUse` 里判的——那样同批的两个并行工具会同时要求问真人，正好撞上 TODO 里
「asker 与 REPL 抢同一个输入流」那条。按批前置让这个问题在结构上不存在，
且因为并发批内**全是只读工具**，它们不会改变彼此的权限判定前提（见 spec 的取舍论证）。

代价：引入线程池；`SessionLog.append` 要加锁；状态行要支持多个 `◐` 并列
（`statusline.py` 的 docstring 正好写着「那是并发（阶段 5）的事」）。

**一个被高估的风险已排除**：TODO 说三个进程级全局（`set_memory_dir` / `set_notifier` /
`set_origin_session`）「一旦有并发就要重新考虑」——查过了，它们是**装配期写、执行期只读**，
线程并发下不构成竞争。真正要加锁的只有 `SessionLog`。

### 方案 C · 全套照 CC

B 全部，加边流边派发、`discard()` 半成品丢弃、只有 bash 出错才杀兄弟。
学习价值最高（CC 那套执行器完整走一遍），但为上面那 16% 付全部复杂度；
且**必须**先改 `Tool.run` 返回契约（不知道工具是否出错就没法决定杀不杀兄弟），
而 `discard()` 那条失效路径 pai 目前根本不存在（没有模型降级回退）。

### 确认

**问 1**：阶段 5 的范围选哪个？

- 候选 A·**薄流式（只做输出）**：只换 `create(stream=True)` + 装配器 + 增量事件 + usage 修正，
  工具执行一字不动。最小风险、最快看到效果。代价：能力标志只能同时放弃
  （挂了没人消费就是死代码），阶段 5 只做一半，并发另开一轮。
- 候选 B·**流式 + 能力标志 + 保序并发**：输出逐字上屏 + usage 两条修正 + 中断可掐在流中途；
  能力标志照 CC 做成收 input 的函数、默认全 False；保序贪心分批，只读工具并行。
  权限判定前置串行（偏离 CC，绕开抢输入流）。不做边流边派发与兄弟取消。
- 候选 C·**全套照 CC**：B 全部，加边流边派发（实测最多抢 16% 流时间）+ 半成品丢弃 +
  只有 bash 出错才杀兄弟。必须连带改 `Tool.run` 契约，且 `discard()` 那条失效路径 pai 目前不存在。

**选择：B**。（我给的推荐理由，用户采纳：收益排序上，并行两个 1 秒的读文件省下的时间
比抢那 16% 的流时间多；而 C 独有的那部分复杂度，pai 现在连触发条件都没有。）

**问 2**：流式默认开还是需显式开启？（这是 05 复盘质疑二「不该默认改变已交付功能的输出形态」的直接回声）

- 候选甲·**默认开，不加开关**：once 与 REPL 一律流式。YAGNI，且流式是严格更好的体验
  （早看到字、早能中断）。代价：确实改变了 once 已交付的输出形态，重定向到管道时也会逐字写。
- 候选乙·**默认开，但非 tty 自动退回一次性输出**：与状态行现有做法一致
  （`_is_real_terminal_input`）。代价：两条输出路径都要测，且「为什么管道里不流」没有强理由。
- 候选丙·**默认关，显式开启**：保住已交付行为一字不变。代价：默认路径上没人用得到它，
  且开关落在哪（env 还是 settings.json）又是一个得拍的板。

**选择：甲**（默认开，不加开关）。

**问 3**：两条 feature 05 遗留，哪些进本轮范围？（可多选）

- 候选甲·**都不进**：steering 等 TUI（它要的是输入线程，不是流式）；
  `Tool.run` 契约单独开 `fix/` 小立项。本轮交付面最窄、最好复盘。
- 候选乙·**只进 `Tool.run` 错误契约**：改成 `(text, is_error)` 或受控异常，影响 4 个工具 + loop + 测试；
  顺带让状态行真能标红叉（现在 `is_error` 在撒谎）。选 C 的话这条是强制的。
- 候选丙·**只进 steering 输入源**：起一个 stdin 读取线程让「干活时打字」真通电。
  会与 `_make_asker` 抢同一个输入流（TODO 已记的老问题），换个姿势踩同一个坑。
- 候选丁·**两条都进**：交付面最宽，但本轮会同时动 loop、工具层、输入层三处，出问题难定位是哪一层。

**选择：甲**（都不进）。

我给出的评估（用户采纳）：steering 需要的是**独立输入线程或非阻塞 stdin**，
流式既非必要也非充分——读 chunk 的循环照样占着主线程；真解法是 TUI 的模态输入，
与「asker 抢输入流」同根，TODO 里已写明「不该在 REPL 阶段继续打补丁」。
`Tool.run` 契约按 [08 复盘定的判据](../08-20260810-storage-layout/README.md)
（「顺手」只在『不做它本轮交付就是有缺陷的』时成立）不该搭车：B 不做它也不算有缺陷。

### 选 B 附带的一个好处（论证时才发现，记在这）

**流式文本与状态行不会抢同一行终端**——因为 B **不做边流边派发**，模型输出与工具执行
在时间上不重叠：模型说话时没有工具在跑（状态行不显示），工具跑时模型已经说完了。
选 C 的话这两者天然重叠，得额外设计一层终端行管理。

## 结果与总结

6 task 严格 TDD 交付（Task 6 例外，如实记在 [devlog](devlog.md)），
`./test.sh` → **509 passed, 3 deselected**（基线 458，净增 51 条）。

| 交付项 | 落点 |
|---|---|
| 流式装配（index 归并 / arguments 拼接 / usage 两种形状 / 中断） | `core/streaming.py`（新模块） |
| loop 走流式 + 增量事件 + 中断到流中途 + `unmetered` 留痕 | `core/loop.py`、`core/events.py::MessageDelta` |
| 工具能力标志（收 input 的函数，默认 False） | `core/tools/__init__.py::capabilities_for` + 各工具模块 |
| 保序贪心分批调度 | `core/scheduler.py`（新模块） |
| 权限**按批前置** + 结果按原顺序回填 + SessionLog 加锁 | `core/loop.py`、`core/session.py` |
| 增量上屏 + 最终答案不打两遍 | `modes/echo.py`（新模块）、`cli.py`、`modes/interactive.py` |

**真跑冒烟**（`pai_playground/`）：答案逐字上屏、两个 `read_file` 同批执行、结尾无重复 🤖。

**刻意没做的**：边流边派发、兄弟取消、`discard()` 半成品丢弃（拍板选 B，实测边流边派发
最多抢 16% 流时间）；`Tool.run` 错误契约、steering 输入源（拍板问 3 选甲）；
bash 的只读判定器（feature 07 已明确不做）；流式开关（拍板问 2 选甲）。

## 遗留问题

每条已同步登记 [TODO](../../TODO.md)。

1. **中断丢弃半条 assistant 消息，与屏幕上看到的不一致**（复盘质疑四）：
   打出来的半截答案不进上下文，下一轮问「你刚说的那个」它不知道。
2. **并发在界面上完全不可见**（复盘质疑二）：事件全在主线程发、`ToolEnd` 按原顺序交付，
   于是看不出谁先跑完、甚至看不出并发有没有真的发生。
3. **`MAX_TOOL_WORKERS = 8` 是个不会生效的常量**（复盘质疑一）：唯一的并发安全工具是
   `read_file`，模型一轮最多发过 3 个。连带质疑「给照抄常数写来源注释」这条习惯的形式化风险。
4. **`once` 的输出形态变了**（复盘质疑三）：多了 `🤖 ` 前缀与空行，stdout 被多次写入。
   `pai "..." > out.txt` 这类脚本用法迟早要回来处理。
5. **能力判定的三条退化路径不可分辨**（Task 3）：「判定器写错了」与「工具确实不安全」
   在外部完全一样，且不留痕；工具多了会变成静默的性能损失。
6. **`assemble` 不认 `finish_reason` 提前收尾**（Task 1）：读到迭代器结束为止。
   真实 SDK 在 `[DONE]` 后就停，暂不影响。
7. **中断粒度是「块与块之间」**（Task 1）：巨大 chunk 传输中按 Ctrl+C 要等它收完。
8. **核实并核销一条旧担忧**：TODO 里「三个进程级全局一旦有并发就要重新考虑」——
   查证**不成立**（`set_memory_dir` / `set_notifier` / `set_origin_session` 都是
   装配期写、执行期只读）。真正需要加锁的只有 `SessionLog.append`，本轮已加。

## 用到的知识

第 2 步「前置精读」的产物（roadmap 阶段 5 清单已同步打勾）：

- [K source-walks/cc-streaming-tools.md](../../../../knowledge/source-walks/cc-streaming-tools.md)
  ——CC `StreamingToolExecutor` / `Tool.ts` 能力标志 / `toolOrchestration` 保序分批 /
  兄弟取消 / `getAssistantMessageId`。末节是「抄什么、不抄什么」的 pai 视角对照表。
- [K concepts/streaming-tool-calls.md](../../../../knowledge/concepts/streaming-tool-calls.md)
  ——OpenAI 兼容协议流式的通用工程知识：`index` 归并、`arguments` 逐字符分片、
  usage 位置、中断无 usage、并行调用**不会**重复计 usage。
- **反向对照的原始证据**：[evidence/20260811-流式探针/](evidence/20260811-流式探针/说明.md)
  （6 个探针，5 次真实请求，原始 chunk 全量 JSONL + 脚本）。

### 「官方 streaming 章节」这条清单项为什么改了

roadmap 原文写的是「官方 streaming 相关章节 → 届时落 `knowledge/claude-docs/`」。
落笔时发现**官方 Claude Code 文档没有 streaming 章节**
（[K claude-docs/map.md](../../../../knowledge/claude-docs/map.md) 的覆盖图里也没有），
而真正约束 pai 的是它实际说的协议——**OpenAI 兼容协议打 DeepSeek**。
所以这条改落 `concepts/`（无单一外部原文可链），理由已在 roadmap 就地留档，原条目划掉保留。

### 反向对照撞出来的三条（feature 09 教训的落点）

1. **`stream_options.include_usage` 在 DeepSeek 上是空操作**，且**没有**文档所说的
   「choices 为空数组的额外块」——usage 一律在带 `finish_reason` 的**末块**上。
   照文档写惯用法（`if not chunk.choices: usage = ...`）会让 usage **静默丢失**，
   预算熔断与锚点一起哑掉。**这是文档读得再全也读不出来的一层。**
2. **必修范围那条要重写**：「并行工具调用 usage 重复累加」是 Anthropic 协议的形状带来的，
   pai 这边不成立（实测 2 个并行 tool_calls → 1 份 usage，流式非流式一致）。
   TODO 原条目已划掉并写明错在哪；**但若 pai 为了边流边显示把一次响应拆成多条 assistant 记录，
   就会亲手造出这个 bug** —— 从「必修前置」变成了「设计时别踩」。
3. **中断掉的流拿不到 usage**（末块没读到），被中断请求的消耗**恒定少算**。
   原本不在任何清单上。
