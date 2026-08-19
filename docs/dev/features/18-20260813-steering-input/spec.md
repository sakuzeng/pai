# 18-steering-input · spec

状态：七问已于 2026-08-13 拍完，选择与理由完整存档在
[README「候选方案与确认」](README.md#候选方案与确认)，本文件末尾「拍板结论」一节给汇总。
下面的「拍板问」节保留抛问时的原文与候选（规矩 6：问答原样落盘，不因结果回头改问题）。

## 背景与问题

`core/queue.py` 的 steering 队列从 feature 05 起就是「有结构、有注入点、无调用方」：
`loop.py:352-355` 每轮工具结果回填后会 poll 一次，但没有任何代码往这条队列里 enqueue。
TUI 交付（12/13/16）之后用户确实能在 agent 干活时打字了，可那条路
（`modes/interactive.py:762-768`）只接 followUp——12 的拍板问 4 选的是「排队，本轮结束后发」。

于是 TODO 里躺着两条登记：05 拍板问 2（诚实边界：REPL 阶段物理上做不到）、
12 spec G6（TUI 之后仍不通电）。本次要一并关掉。

本次的设计依据是 CC 而不是 pi。 pi 的答案是两条具名队列，把「用户怎么表达
『现在就转向』和『等你干完再说』」这个问题推给了集成方（两条队列的模式都可配，
默认都是 `one-at-a-time`）。CC 给了一个更完整、且有真实用户量验证过的答案：
一条队列 + 三档优先级，用户输入默认 `next`（中途注入），系统消息才默认 `later`。
走读全文见 [cc-message-queue.md](../../../../knowledge/loop/cc-message-queue.md)。

## 目标（做什么）

1. 给 steering 队列接上真实输入源（TUI 干活期间的键盘输入）。
2. 定下 pai 的默认档（拍板问 1）与显式路径（拍板问 2）。
3. 修掉下面「前置缺陷」一节那条——它比接输入源更靠前，不修就是接了个会卡死的队列。
4. 关闭 TODO 的两条 steering 登记。

## 非目标（明确不做什么）

- 不做 CC 的 `now` 档（abort 在跑的工具）：pai 的中断是进程级标志（D#40），
  粒度对不上「只 abort 这一个工具调用」；且 CC 自己也没把 `now` 开给交互式用户
  （全仓只有 SDK schema 能设，REPL/print 只是订阅它然后 abort）。
- 不改队列结构：保留 pi 的两条具名队列，不换成「一条队列 + priority 字段」。
  pai 只需要两档，名字承载调用时机的契约；换成字段反而把这条约束藏起来。
  将来真要第三档再议。
- 不做 attachment 形状：pai 走 OpenAI 兼容协议，没有 attachment 这层，
  注入仍是 `messages.push({"role": "user", ...})`。
- 不动子 agent 分流（`agentId`）——pai 没有子 agent。

## 前置缺陷：steering 在「模型不调工具」的轮次会永久卡死

<!-- 这一节是拍板问之外的事实陈述，不是选择题；选择题只在末尾的 (a)/(b) 代价对比 -->

这是 pai 自己的缺陷，不是 CC 差异，读 cc-message-queue.md 第六节时撞出来的。

### 成因

pai 把 pi 的两层 while 压成了单层 `for` + `continue`（`loop.py:167` 的
`for step in range(1, max_steps + 1)` + `:284-288` 的 followUp `continue`）。
于是执行顺序是：

```
loop.py:283   if not msg.tool_calls:            ← 模型这轮直接作答
loop.py:284       follow_ups = get_follow_up_messages()
loop.py:285-288   if follow_ups: _extend(...); continue
loop.py:289       return finish("final", ...)   ← **在这里就返回了**
      ⋮
loop.py:352   if get_steering_messages:         ← 永远走不到
loop.py:355       _extend(messages, get_steering_messages(), session)
```

后果：模型某一轮不调工具、直接作答时，队列里的 steering 消息永远不会被注入，
也不会退化成 followUp——它就卡在队列里。 用户看着 dock 上的计数，
而那条话再也不会发出去。

这不是理论风险：「用户在模型打最后一段总结时打字」正是最常见的场景之一
（模型收尾那轮通常就不调工具）。

### 两家为什么没有这个问题

- pi：内层 while 的条件是 `hasMoreToolCalls || pendingMessages.length > 0`
  （`agent-loop.ts:174`）——队列非空就不许退出。
- CC：drain 挂在 `query.ts` 的工具结果处理链上，而 `later` 档本来就是
  end-of-turn 处理，两档各有各的出口，不共用一个 return。

### 方案代价对比（这一条要一起拍）

(a) 在 `loop.py:283` 分支里加一次 steering 检查。
即「模型不调工具时，先看 steering 队列，非空就同 followUp 一样 `_extend` + `continue`」。

- 代价小：改动局限在一个分支内，`for` 循环结构不动，现有 `max_steps` 语义不变。
- 代价在语义上：steering 的定义是「中途转向」，而这里它被当成 followUp 用了
  ——同一条消息走两条不同注入点，「哪个注入点负责哪种时机」这条契约被稀释。
  队列命名承载语义（非目标里刚说「名字承载调用时机的契约」），(a) 正好在磨损它。
- 还要决定：两条队列都非空时谁先注入（steering 先，还是按 CC 的 `next > later`？
  ——CC 的档序天然回答了这个问题，pai 的双队列结构没有内建答案）。

(b) 改回双层循环（外层「还有话要说就继续」，内层「还有工具要跑就继续」）。

- 结构上与 pi/CC 对齐，「队列非空就不许退出」成为结构性保证，
  而不是散在某个 `if` 分支里的一次检查。
- 代价：会动到 `max_steps` 语义，这是必须先想清的一条：
  - 现状 `step` 是 `for` 的循环变量，一步 = 一次模型请求；followUp 走 `continue`
    也扣步数预算。
  - 改双层后，「步」计在内层还是外层？计内层 = 语义不变（仍是一次请求一步），
    但外层循环需要自己的上界，否则「排队 → 注入 → 模型答 → 又排队」可以无限转下去；
    计外层 = `max_steps` 变成「最多几个回合」，所有现存关于步数的测试与
    `finish("max_steps", ...)` 的文案都要改。
  - 另需注意：pi 根本没有 `max_steps`（`agent-loop.ts` / `types.ts` 全文检索零命中），
    所以「pi 怎么做」在这一点上给不出答案，pai 得自己定。
  - 波及面：`loop.py:167` 的 `for`、`:170`/`:176` 两处 `finish` 的步数文案、
    `:357` 的 `max_steps` 出口，以及所有断言步数的测试。

倾向不写在这里——(a)/(b) 的选择留给拍板问答之后的 plan；本节只把两条路的真实代价摆出来。

2026-08-13 已拍：选 (a)（问 6）。补一条：上面给 (a) 记的那个代价
（「steering 被当 followUp 用，磨损队列命名的契约」）随问 2 删掉 followUp 已经不成立——
只剩一条队列时，两个出口就是 CC 的形状（mid-turn drain + turn 结束后的 queueProcessor），
不是权宜之计。「两队列都非空时谁先注入」那个子问题也一并消失。

## 拍板问

<!-- 规矩 6：问题原文、候选与取舍描述原样落盘。选择与理由由用户填进 README 的「确认」节 -->

### 问 1（主问）：TUI 干活期间敲回车，默认改成 steering（本轮就注入）吗？

背景：feature 12 拍板问 4 选的是排队（followUp）。CC 的取舍是默认中途注入——
`messageQueueManager.ts:122-129` 的 `enqueue()` 把用户命令默认成 `next`，
而任务通知走 `enqueuePendingNotification()` 默认 `later`，注释写明动机：
*so user input is never starved by system messages*。用户不需要任何修饰键或前缀来
表达「我要现在插话」，那就是默认行为。

- 候选 A·改（照 CC）：干活期间的输入默认进 steering，本轮工具结果回填后立即注入。
  收益：这是本次唯一一条「有真实用户量验证过」的证据；符合直觉——人打断机器，
  机器就该马上听见。代价：见下面的反方理由。
- 候选 B·不改（维持 12 的排队）：默认仍进 followUp，steering 只走显式路径。
  收益：现状零回归，「排队」这个用户已经习惯的行为不变；风险都压在显式路径的设计上。
- 候选 C·按内容分流：例如短句（疑似催促/纠偏）走 steering、长句走 followUp。
  取舍：不用用户学任何手势，但判据是启发式的，猜错的那次代价很大，
  且没有任何参照实现这么做——列在这里是为了让 A/B 的边界清楚，不是推荐。

反方理由（pai 与 CC 的差异，以及哪些差异会让这个默认值不成立）：

1. pai 没有 attachment 这层。 CC 把队列消息转成 attachment 跟在 `toolResults`
   后面（笔记第四节），形状上自带「补充材料」的语气；pai 只能 push 一条普通
   `role:"user"` 消息，夹在工具结果与下一轮请求之间。同样的默认值，两家的「注入强度」
   不同——一条突如其来的 user 消息更可能被模型读成「推翻前面的全新指令」，
   而不是「顺手补一句」。「顺手补一句就把整个计划带偏」这个失败模式，pai 比 CC 更容易撞上。
2. pai 没有 Esc 单独打断的路径。 CC 的用户有三条独立的路：Esc（abort 当前工具）、
   队列 `next`、队列 `later`。pai 的 `Ctrl+C` 是进程级 `InterruptFlag`（D#40），
   一按就是整轮结束（`loop.py:347-350` 直接 `finish("interrupted", ...)`）。
   所以在 pai 里，「我要现在转向但别把这轮杀掉」与「我说完，你干完再说」
   只能靠这两条队列来表达——队列是唯一的表达渠道。
   若默认改成 steering 而问 2 不给显式路径，用户就直接失去了「排队」这个选项。
3. CC 的 `next` 是「三档里的中间档」，pai 的默认是「两选一」。 CC 上有 `now`
   兜底极端情况、下有 `later` 承接系统消息，`next` 落在中间是安全的；pai 只有两档，
   这个默认值决定的是全部，没有第三档可以兜。
4. pai 有 `max_steps`，CC/pi 没有。 steering 注入会让模型多跑若干轮，
   更容易撞上步数上限并以 `finish("max_steps", ...)` 收场；followUp 的 `continue`
   同样扣预算，但它至少发生在「模型本来就要停」的时刻。
5. CC 的默认值是被它的 UI 一起验证的，不是孤立成立的：CC 会显示排队状态、
   有 Esc 提示、有 attachment 的视觉呈现。把默认值单独摘出来抄，
   等于假设「用户量验证」验的是默认值本身而不是「默认值 + 那套 UI」。
   pai 的 dock 目前只有一个 `set_queued` 计数（见问 4）。

### 问 2：如果改默认，followUp 还留不留？留的话用什么显式路径进？

背景：接问 1 候选 A。CC 那边「显式降级到 `later`」是给系统消息用的
（`enqueuePendingNotification`），交互式用户其实没有降级手势——因为 CC 的用户
本来就有 Esc 和别的出口。pai 没有，所以这问必须单独答。

- 候选 A·不留，只剩一条队列：删掉 followUp 路径，所有输入都是 steering。
  收益：概念最少，dock 也不用改（问 4 自动消解）。代价：「等你干完再说」这个意图
  在 pai 里彻底没有表达方式了；且 followUp 是目前唯一通电的那条，删它是拿
  已交付能力换新能力。
- 候选 B·留，用前缀触发（如 `>` 或 `later:` 开头）。收益：零新键位，
  与 pai 已有的 `!`（bash）/ `/`（命令）同族——用户已经在学前缀了。
  代价：污染消息正文（要转义、要处理「我真的想以 `>` 开头」）；多一个前缀就多一条要记的规矩。
- 候选 C·留，用修饰键（如 `Alt+Enter` / `Shift+Enter` 提交进 followUp）。
  收益：完全不碰正文。代价：终端对 `Shift+Enter` 的转义序列支持不一，
  很多终端把它和 `Enter` 发成同一串字节——pai 自己解析键盘（`tui/keys.py`），
  这条得先实测再定，否则做出来在用户的终端上是死键。
- 候选 D·留，用 `/` 命令（如 `/queue <文本>` 或 `/later <文本>`）。
  收益：命令体系与 `_dispatch_command` 现成，实现最省。
  代价：打字最长，「顺手补一句」的场景下几乎没人会用；且与问 5 冲突——
  干活期间的 `/` 目前根本没走命令通道（见问 5 背景）。

### 问 3：steering 用 `all` 还是 `single` 模式？

背景：`queue.py` 的文档注释主张 `all`——*「用户连打三句通常是同一个转向意图，
拆开逐轮注入反而错乱」*。这句是 feature 05 写下的推断，从未被真实使用验证过
（因为它一直没有输入源）。

关于 CC 到底是哪种，笔记两节要并读（这一点值得当场校正）：

- 笔记第二节讲 `dequeue()`：线性扫一遍找最高档，同档按数组顺序即 FIFO（一次一条）。
- 笔记第四节讲 mid-turn drain 那处，用的不是 `dequeue()` 而是
  `getCommandsByMaxPriority(...)` 拿快照，随后 `for await` 把整批转成 attachment。

即「同档 FIFO 逐条出队」是 `dequeue()` 的语义，而 mid-turn 注入那一处实际是批量灌的
——这与 `queue.py` 主张的 `all` 反而一致。依据是笔记第二/四节的并读，不是我直接读的
CC 源码；拍板前建议复核 `query.ts` 那段。

- 候选 A·`all`（一次全灌）：三句话一次进模型，转向意图完整。
  代价：若三句是「改主意又改回来」，模型会同时看到矛盾指令（但 `single` 也只是把矛盾
  分散到不同轮，未必更好）。
- 候选 B·`single`（一条一轮）：每条各触发一轮，中间可被中断、可被权限拦。
  收益：每注入一条模型都有机会响应完再看下一条，节奏可控。
  代价：用户敲的三句被拆成三轮，且队列里剩下的要等下一轮工具结果才走得掉——
  若模型下一轮就不调工具了，剩下的直接撞上「前置缺陷」那条。
- 候选 C·`all` 且合并成一条 user 消息：多条内容拼成一条注入。
  收益：形状最省、边界最清楚。代价：丢掉逐条边界（session 回放时看不出用户敲了几次）。

注：followUp 现在用的是 `single`，两条队列可以各选各的模式，不必统一。

拍板时复核（2026-08-13，改写了上面那段推断）：用户没有直接选，而是问「cc是怎样做的呢」。
读了 v2.1.88 源码，上面标着「未复核」的推断方向对但说法不准，准确版本是：
- `query.ts:1570` mid-turn：`getCommandsByMaxPriority('next')` 拿快照（`filter`，不删）
  → 整批转 attachment → `:1642` `removeFromQueue(consumedCommands)` 整批摘掉。
- `queueProcessor.ts` between-turn：`dequeueAllMatching(同 mode)` 批量出队，
  注释原话 *"each becomes its own user message with its own UUID"*。
- 逐条出队（`dequeue()`）只用在 slash 与 bash 命令上——注释给了理由：
  逐条的错误隔离、退码、进度 UI。

即两个 drain 点都是批量，且都不合并成一条。「同档 FIFO 逐条」只是 `dequeue()`
这个函数的语义，不是 CC 注入路径的实际行为。候选 C（合并成一条）由此被排除：
CC 特意给每条留独立 UUID。

### 问 4：dock 队列区现在只有一个 `set_queued`，两条队列怎么显示？

背景：`tui/dock.py:127` 的 `set_queued(count)` 只有一个计数，注释写死了语义
（*「followUp 队列里排了多少条」*），调用点在 `interactive.py:766` 与 `:831`。
问 1 若选 A，屏幕上就同时可能有两种待发消息，而它们发出的时机差一整轮。

- 候选 A·合计一个数字（现状最小改动）：`set_queued(steering + followUp)`。
  收益：不动 dock 布局。代价：用户看不出「我刚说的这句是马上发还是等着」——
  而这正好是本次新增的唯一区别，藏起来等于白做。
- 候选 B·分列两个计数（如 `⏭2 ⏸1`）：dock 加一个字段与一段渲染。
  收益：时机一眼可见。代价：dock 横向空间要重新排（已有模型名/上下文/cwd/模式）。
- 候选 C·只显示「本轮就会发的」（steering 数），followUp 不在 dock 上显示或另处提示。
  收益：不加宽 dock，突出「马上要发生的事」。代价：排队中的 followUp 变成隐形状态。
- 候选 D·一个数字 + 一个记号（如 `3↑` 表示队首是 steering）。
  取舍：省空间但要用户学记号。

### 问 5：要不要照 CC 把 `/` 命令排除在中途注入之外？

CC 的理由（笔记第四节②，注释原话）：slash 命令
*"must go through `processSlashCommand` after the turn ends, not be sent to the model as text"*
——`/xxx` 是给客户端执行的，不是给模型读的。

pai 现在是什么样（已核实，这不是假设）：`tui/app.py:407` 是

```python
if text.startswith(("/", "!")) and not self.busy:
    return [(COMMAND, text)]
return [(SUBMIT, text)]
```

`and not self.busy` 意味着：agent 干活期间敲 `/help`，它不会被当命令，
而是当普通文本走 SUBMIT 进队列，最后原样发给模型。 这正是 CC 明文禁止的那件事，
pai 目前每天都在做（只是因为 followUp 要等本轮结束，症状不明显）。
问 1 若选 A，这条会立刻变得刺眼：敲 `/help` 会中途打断模型去读一句 `/help`。

- 候选 A·抄这条规则：队列注入前过滤掉 `/` 开头的命令，让它们走命令通道。
  子问题：干活期间的命令立刻执行（有些命令会改 `messages`，与正在跑的 loop 抢状态），
  还是排到本轮结束后执行（CC 是后者，`useQueueProcessor`）？——建议后者，
  但这是个要一起拍的子选择。
- 候选 B·不抄，维持现状：`/` 在干活期间仍当文本。
  收益：不动 `app.py:407` 那行，零回归。代价：上面那个失败模式保留，且它会随问 1 变严重。
- 候选 C·抄，但只排除 `/`，`!` 另说：`!` 是 shell 命令，同样是给客户端执行的，
  但它的副作用（跑一条 shell）在干活期间执行是否安全要单独想——CC 那边
  bash 模式命令由 `INLINE_NOTIFICATION_MODES` 在更下游滤掉，是另一条路径。

## 拍板结论（2026-08-13）

| # | 问题 | 选择 |
|---|---|---|
| 1 | 干活期间的默认档 | 改成 steering（照 CC：人说话默认优先） |
| 2 | followUp 留不留 | 不留，只剩一条消息队列 |
| 3 | drain 模式 | `all`，各自一条消息（照 CC，不合并） |
| 4 | dock 两条队列怎么显示 | 作废（问 2 消解了它）；`set_queued` 语义改成 steering |
| 5 | `/` 命令排不排除中途注入 | 排除，本轮结束后执行 |
| 6 | 前置缺陷修法 | (a) 两个出口（CC 形状），`for` 循环与 `max_steps` 语义不动 |
| 7 | 被推迟的 `/` 存哪里 | 跟 CC 一致：同一条队列 + drain 带谓词滤掉，结束后逐条执行 |

由此定下的设计（细化进 [plan.md](plan.md)）：

- `core/queue.py`：`drain()` 增加可选谓词参数（对应 CC 的 `dequeueAllMatching(predicate)`），
  `all`/`single` 两模式保留；`steering` 用 `all`，命令逐条取用 `single`。
- `core/loop.py`：`get_follow_up_messages` 参数删除；`:283` 分支改查 steering
  （注入 + `continue`），`:352` 中途注入点不动 → steering 两个出口。
- `modes/interactive.py`：`follow_up` 改 `steering = PendingMessageQueue("all")`，
  SUBMIT 分支照旧 enqueue；本轮结束后先把队列里的 `/` 命令逐条交给 `_dispatch_command`。
- `tui/app.py:407`：去掉 `and not self.busy` 的一半——`/` 干活期间也标成命令而非文本
  （具体形状由 plan 定，约束是「不能立刻执行」）。

## 验收标准

1. 前置缺陷有回归测试：构造「队列非空 + 模型这轮不发 tool_calls」，
   断言消息被注入并继续跑（问 6 选的 (a)），而非静默丢失。
2. 干活期间的输入进 steering，假 provider e2e 能验到本轮内注入
   （模型下一次请求里看得见那句话）。
3. `tool_calls` 与其结果的配对不被注入劈开（现有不变量保持绿）。
4. 干活期间敲 `/xxx` 不会被当文本发给模型，本轮结束后作为命令执行。
5. `tests/test_queue.py` 现有 8 处实例化随谓词参数与模式变更同步改语义，不留假绿。
6. TODO 两条 steering 登记（05 拍板问 2 / 12 spec G6）+ 前置缺陷那条一并关闭。
