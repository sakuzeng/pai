# 18-steering-input —— 给 steering 队列接真实输入源
状态：已交付
分支：`feat/18-steering-input`（立项、七问拍板、实现与交付）
流程：superpowers 全链路（[spec.md](spec.md) → 七问拍板 2026-08-13 → [plan.md](plan.md) → TDD。
      理由：动 core/loop 的注入时机 + modes/tui 的输入分流，
      且含一条已交付代码的前置缺陷要一并修）

改已交付功能 [12-tui](../12-20260811-tui/README.md) 的行为（规矩 7：改变而非完成）——
12 的拍板问 4 选的是「干活时打的字排队，本轮结束后依次发出」，本档案要重新问的正是
这个默认值。12 号档案冻结，本档案链回。

同时关联 [05-repl](../05-20260810-repl/README.md) 的遗留（拍板问 2 的诚实边界：
steering 结构就位但无真实输入源）——那条遗留的另一半在这里关。

## 需求

给 `core/queue.py` 的 steering 队列接上真实输入源，让「用户在 agent 干活期间说的话」
能在本轮内注入模型，而不是只能等本轮结束。设计依据取 CC 而非 pi：
CC 的用户输入默认 `next`（中途注入），系统消息才默认 `later`，即
「人说话默认优先，机器说话默认等着」——这个默认值有真实用户量验证过。
走读见 [knowledge/loop/cc-message-queue.md](../../../../knowledge/loop/cc-message-queue.md)。

### 现状（不用再查，动工前已核实）

| 位置 | 现状 |
|---|---|
| `core/queue.py` | `PendingMessageQueue` 两条具名队列，`drain()` 有 `all`/`single` 两模式 |
| `core/loop.py:102-103` | `get_steering_messages` / `get_follow_up_messages` 两个注入参数 |
| `core/loop.py:283-289` | followUp 注入点（模型不发 tool_calls 时），`return` 在 steering poll 之前 |
| `core/loop.py:352-355` | steering 注入点（本轮工具结果全部回填之后）——有注入点无调用方 |
| `modes/interactive.py:762-768` | 干活期间 `driver.poll` 的 SUBMIT 分支 → `follow_up.enqueue`（唯一输入源） |
| `tui/app.py:407` | `text.startswith(("/", "!")) and not self.busy` 才走 COMMAND——干活期间的 `/xxx` 当普通文本进队列 |
| `tui/dock.py:127` | `set_queued(count)` 只有一个计数，语义写死为 followUp |
| `tests/test_queue.py` | 8 处 `PendingMessageQueue(...)` 实例化 |

### 验收标准（拍板后补全，先记框架）

1. 干活期间的输入按拍板选定的默认档进队，且本轮内能被注入（假 provider e2e 可验）。
2. 前置缺陷（见 spec「前置缺陷」节）修掉：模型某轮不调工具直接作答时，
   队列里的 steering 不会卡死——要么被注入、要么退化处理，二者必居其一且有测试钉死。
3. TODO 的两条 steering 登记（05 拍板问 2 / 12 spec G6）随交付一并关闭。
4. `tool_calls` 与其结果的配对不被注入劈开（现有不变量，回归测试须保持绿）。

## 候选方案与确认

拍板问原文与候选取舍见 [spec.md](spec.md)「拍板问」节。2026-08-13 一次会话拍完七问
（原定五问，另有两问是前几问的选择组合出来的，不先定就写不成 plan）。

过程本身有两处值得留档：用户在问 3 与问 2 上都没有直接选，而是要我先去核实/解释
（「cc是怎样做的呢」「在模型执行工具的时候 next 会将用户的消息注入到对话中吧」）。
两次核实各改写了一条结论——见问 3 与问 2 的记录。

### 问 1（主问）：TUI 干活期间敲回车，默认改成 steering（本轮就注入）吗？

- 候选 A·改（照 CC）：干活期间输入默认进 steering，本轮工具结果回填后立即注入。
  唯一一条有真实用户量验证过的证据；代价是「排队」意图要靠问 2 的显式路径保住，
  且 pai 的普通 user 消息比 CC 的 attachment 更容易被模型读成推翻计划。
- 候选 B·不改（维持 12 的排队）：零回归，风险全压在显式路径设计上。
- 候选 C·按内容分流（短句 steering / 长句 followUp）：不用学手势，但判据是启发式的、
  猜错代价大，且无任何参照实现这么做。

选择：A·改成 steering（照 CC）。

抛问时按用户要求给了反方理由（pai 与 CC 的五条结构性差异：无 attachment 层 /
无 Esc 单独打断路径 / 只有两档而非三档 / 有 `max_steps` / CC 的默认值是连同它的 UI
一起被验证的），用户看过之后仍选 A。

### 问 2：followUp 还留不留？留的话用什么显式路径进？

用户第一次没有选，而是反问机制：「在模型执行工具的时候 next 会将用户的消息注入到
对话中吧，如果是这样的话，可以的」。核实后答复了两条边界（这两条现在写进了 spec）：

1. 不是「工具跑到一半插进去」，是「这一批工具结果回填完、下一次 API 请求发出前」插进去
   （CC 对 `next` 的定义原话 + `query.ts:1570-1590` 把 attachment push 进 `toolResults`；
   pai 的 `loop.py:352-355` 位置一模一样）。所以模型是在决定下一步动作之前看到的。
2. 前提是这一轮模型确实调了工具。这个前提现在不成立——正是前置缺陷那条，
   本次一并修才兑现。

- 候选 A·不留，只剩一条队列：最接近 CC 的交互式实情（它的用户确实只能发 `next`）；
  代价是「不要打断你，干完再看」彻底无法表达，且 followUp 是目前唯一通电的那条。
- 候选 B·留，`/later <文本>` 命令：与问 5 天然契合，实现最省；打字长。
- 候选 C·留，`>` 前缀：与 `!`/`/` 同族，敲起来最快；污染正文。
- 候选 D·留，修饰键：不碰正文；但多数终端 `Shift+Enter` 与 `Enter` 同字节，得先实测。

选择：A·不留，只剩一条队列。

### 问 3：steering 用 `all` 还是 `single`？

用户第一次没有选，而是反问「cc是怎样做的呢」——我抛问时的依据是笔记两节并读的
推断，并已标注「未复核 CC 源码」。于是去读了 v2.1.88 源码，结论如下（改写了推断）：

- `query.ts:1570` mid-turn：`getCommandsByMaxPriority('next')` 拿快照（filter 不是 dequeue）
  → 整批转 attachment → `:1642` `removeFromQueue(consumedCommands)` 整批摘掉。
- `queueProcessor.ts` between-turn：`dequeueAllMatching(同 mode)` 批量出队，
  注释原话 *"each becomes its own user message with its own UUID"*。
- 逐条出队（`dequeue()`）只用在 slash 与 bash 命令上，理由是逐条的错误隔离/退码/进度 UI。

即 CC 两个 drain 点都是批量，且不合并成一条——等于 pai 的 `all` 模式
（`drain()` 返回 list、`_extend` 逐个 append，形状恰好一致）。

- 候选 A·`all`（各自一条消息）· 候选 B·`single` · 候选 C·`all` 但合并成一条
  （核实后确认 CC 不这么做，它特意给每条留独立 UUID）。

选择：A·`all`，照 CC，各自一条消息。

### 问 4：dock 队列区两条队列怎么显示？

作废——问 2 选了「不留」，只剩一条队列，本问自动消解。
`set_queued` 的语义从 followUp 改成 steering 即可（一处注释 + 一处调用）。

### 问 5：要不要照 CC 把 `/` 命令排除在中途注入之外？

背景是一条已核实的现存缺陷：`tui/app.py:407` 是
`startswith(("/", "!")) and not self.busy`——干活期间敲 `/help` 现在就已经
当普通文本发给模型了，正是 CC 明文禁止的那件事（*"not be sent to the model as text"*），
只因 followUp 要等本轮结束所以症状不明显；默认改成 steering 后会立刻变刺眼。

- 候选 A·排除，本轮结束后执行（CC 的 `useQueueProcessor`）· 候选 B·排除，立刻执行
  （与正在跑的 loop 抢 `messages`）· 候选 C·不排除维持现状 · 候选 D·只排除 `/`，`!` 另议。

选择：A·排除，本轮结束后执行。

### 问 6：前置缺陷怎么修——两个出口还是双层循环？

原本这条只在 spec 里摆了代价没拍。问 2 定了「followUp 不留」之后代价变了
（`loop.py:283-289` 那个分支本来就要动），于是重新抛一次。

- 候选 a·两个出口（CC 形状）：把 `:283` 分支的 followUp 检查换成 steering 检查，
  非空就注入 + `continue`。于是 steering 有两个出口（`:283` 结束处 + `:352` 中途处），
  正是 CC 的形状（mid-turn drain + turn 结束后的 queueProcessor）。
  `for` 循环不动，`max_steps` 语义不变。
  spec 里原写的反对理由（「steering 被当 followUp 用、磨损队列命名的契约」）
  随 followUp 被删已经不成立。
- 候选 b·改回双层循环（pi 形状）：「队列非空就不许退出」成为结构性保证；
  代价是必然动 `max_steps` 语义（计内层则外层需自己的上界防无限转，计外层则变成
  「最多几个回合」，两处 finish 文案与所有断言步数的测试都要改），而 pi 没有 `max_steps`，
  这一点上给不出参考答案。

选择：a·两个出口（CC 形状）。

### 问 7：被推迟的 `/` 命令在本轮结束前存在哪里？

问 5（`/` 排除、本轮结束后执行）与问 2（删掉 followUp 队列）组合出来的派生问题。

- 候选 A·另立一个命令暂存列表（modes 层的普通 list，内容永不进模型）
- 候选 B·干活期间直接拒掉（提示「等本轮结束再敲」，什么都不存）
- 候选 C·干活期间立刻执行（推翻问 5）

选择：跟 CC 一致（用户原话）。即：`/` 命令与普通消息存在同一条队列里，
steering 的 drain 带谓词把它们滤掉（CC 的 `dequeueAllMatching(predicate)` /
`getCommandsByMaxPriority` + `remove` 就是这个形状），本轮结束后由 modes 层
逐条取出交给 `_dispatch_command`——逐条也是 CC 的做法（`queueProcessor.ts`
对 slash 与 bash 显式不批量）。
落到 pai：`PendingMessageQueue.drain()` 增加可选谓词参数，`all`/`single` 两模式保留。

## 结果与总结

干活期间打的字，本轮就进模型。 5 个 task（+1 个拍板期间加的 T2.5）严格 TDD，
详细日志见 [devlog.md](devlog.md)，四问复盘见 [复盘.md](复盘.md)。

| task | 做了什么 | 红 → 绿 |
|---|---|---|
| T1 | `queue.drain(where=...)` 谓词：取匹配的、不匹配的按原顺序留下 | `5 failed, 8 passed` → `13 passed` |
| T2 | 删 `get_follow_up_messages`；`loop.py:283` 改查 steering（前置缺陷，两个出口） | `4 failed, 67 passed` → `71 passed` |
| T2.5 | `SteeringInjected` 事件（注入可见性），Union 16 → 17 | `6 failed, 91 passed` → `105 passed` |
| T3 | `interactive` 接线 + `_for_model` 谓词滤掉 `/`、`!` | collection `ImportError` → `90 passed` |
| T4 | 轮末队列处理 + dock 计数跟着 drain 减 | `2 failed`＋collection error → `79 passed` |
| T5 | 6 条 e2e（真进程/真 pty/真 SSE），两轮假绿各记一条 | → `6 passed in 27.49s` |

全量：`1111 passed, 3 deselected in 109.29s`。

注入反证已做（复盘「下次怎么做更好」那条的当场实践）：把 `loop.py` 的出口②
临时拆掉，`tests/test_e2e_steering.py` 是 `2 failed, 4 passed`——
恰好是针对出口②的那两条红，另外四条（中途出口、命令处理）照常绿。
「红得精准」而不是「全红」，说明这几条测试各钉各的地方。

刻意没做的：CC 的 `now` 档（进程级中断粒度对不上，且 CC 自己也不开给交互式用户）、
attachment 形状（pai 走 OpenAI 兼容协议没这层）、`tui/app.py:407` 那行一个字没改
（问 7 选「跟 CC 一致」之后它恰好已经是对的——干活期间的 `/` 本来就走 SUBMIT 进队列）。

## 遗留问题

- [x] ~~前置缺陷·steering 在「模型不调工具」的轮次会卡死~~ 本次修复（问 6 取 (a) 两个出口）。
- 「不要打断你，干完再看」现在无法表达（复盘质疑一，已登记 [TODO](../../TODO.md)）。
- 轮末残余「一条消息一轮」的代价没量过（复盘质疑二，已登记 TODO）。
- 撞上 `MAX_QUEUE_ROUNDS`（8）时用户没有提示（复盘质疑三，已登记 TODO）。
- `test_typing_while_busy_lands_in_the_queue` 是条不会失败的测试（复盘，已登记 TODO）。
- 旁生（不属于本 feature）：`TurnStart` 是死事件 + 术语三套并存，已登记 TODO
  并由用户升格成 feature 19（术语完全对齐 pi/CC + viz-v2 上把步数预算做可见）。

## 用到的知识

- [knowledge/loop/cc-message-queue.md](../../../../knowledge/loop/cc-message-queue.md)
  ——本档案的主要设计依据（第三节：默认值才是真正的设计决定；
  第六节：pai 自己的前置缺陷）。
- [knowledge/loop/pi-agentloop.md](../../../../knowledge/loop/pi-agentloop.md)
  第三节 ——pi 的双队列与「队列非空就不许退出」的内层 while 条件。
- [knowledge/tui/cc-input-ownership-and-modes.md](../../../../knowledge/tui/cc-input-ownership-and-modes.md)
  ——谁拥有输入，与队列是一件事的两半。
