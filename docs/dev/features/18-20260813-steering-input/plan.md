# 18 steering-input 实施计划

日期：2026-08-13。前置：[spec.md](spec.md) 七问已拍板（结论表见 spec 末尾）。
每个 task 一律 TDD：先写测试贴红的输出，再实现贴绿的数字；[devlog.md](devlog.md) 一步一条。

## 两处「plan 阶段才看清」的修正（先写在这，免得与 spec 打架）

① `tui/app.py:407` 不用改。 spec 的设计要点里写着「去掉 `and not self.busy` 的一半」，
那是按「另立命令暂存列表」的思路写的。问 7 拍的是跟 CC 一致——命令与消息存同一条队列、
靠 drain 谓词滤掉。而 `app.py:407` 现有的 `and not self.busy` 恰好已经把干活期间的
`/xxx` 送进 SUBMIT → 队列了。所以这一处零改动，风险也少一处。

② `!` 与 `/` 一起排除。 问 5 问的是 `/`，候选 D（只排除 `/`、`!` 另议）用户没选；
问 7 的答复是「跟 CC 一致」，而 CC 两者都排除在中途注入之外——slash 由
`isSlashCommand` 在 `query.ts:1573` 滤掉，bash 模式由 `INLINE_NOTIFICATION_MODES` 在
`getQueuedCommandAttachments` 里滤掉，且 `queueProcessor.ts` 对两者都逐条处理。
pai 的 `!` 与 `/` 在 `app.py:407` 本来就是同一个判断，拆开反而要额外写代码。
这是我按「跟 CC 一致」推的，不是用户逐字拍的——若要只排除 `/`，改 T3 的谓词一行即可。

## Task 拆分（依赖顺序）

### T1 `core/queue.py`：`drain()` 加可选谓词

对应 CC 的 `dequeueAllMatching(predicate)` / `getCommandsByMaxPriority` + `remove`：
取走匹配的，不匹配的按原顺序留在队列里——这是「命令留到本轮结束」的落点。

- 测试 `tests/test_queue.py`（现有 8 处实例化同步改语义）：
  - `all` + 谓词：三条里滤出两条，留下的那条仍在队列且顺序不变；
  - `all` + 谓词全不匹配：返回 `[]`，队列一条不少；
  - `single` + 谓词：取走第一条匹配的（不是第一条），前面不匹配的留着；
  - 不传谓词 = 现有行为逐字不变（回归）；
  - 空队列传谓词返回 `[]` 不抛；
  - 返回值是切片不是引用（现有不变量）。
- 实现：`drain(self, where: Optional[Callable[[dict], bool]] = None) -> List[dict]`。
- 顺带改模块 docstring：「steering 至今没有真实输入源」「followUp 才是通电的那条」
  这两段随本次交付作废，按拍板结果重写（不许留下与现实各说各话的注释——
  这正是 2026-08-12 那次改写的教训）。

### T2 `core/loop.py`：删 followUp 参数，`:283` 改查 steering（前置缺陷）

- 测试 `tests/test_loop.py`：
  - 前置缺陷回归（本次的核心红）：队列非空 + 模型这轮不发 tool_calls →
    消息被注入 `messages` 且 loop 继续跑，不是 `return finish("final", ...)`。
    这条在改代码前必然红——现在的 `:289` 直接返回。
  - 现有 `test_follow_up_keeps_loop_running`（`:613`）改写成 steering 版本：
    语义从「followUp 让 loop 继续」变成「steering 让 loop 继续」，不是改个名字了事，
    队列模式从 `single` 变 `all`，断言要跟着变。
  - 中途注入点（`:352`）行为不变（现有测试保持绿）。
  - 两个出口的顺序：同一次 run 里先撞 `:352` 再撞 `:283`，两处都能注入。
  - `get_follow_up_messages` 参数已删：仍传它要报 `TypeError`（别静默吞掉）。
- 实现：
  ```python
  if not msg.tool_calls:
      steering = get_steering_messages() if get_steering_messages else []
      if steering:
          # 模型本该停下，但用户排了队——继续跑，而不是让他重开一轮。
          # 这是 steering 的**第二个出口**（CC 形状：mid-turn drain + turn 结束后处理）；
          # 少了它，模型某轮不调工具时队列里的话就永久卡死（feature 18 前置缺陷）。
          _extend(messages, steering, session)
          continue
      return finish("final", msg.content or "")
  ```
  并删掉 `:103` 的 `get_follow_up_messages` 参数与 `:284` 的取用。

### T2.5（补 1，2026-08-13 增补）：注入的消息必须在界面上可见 —— 待拍

事实（已复核）：`loop.py:395-399` 的 `_extend` 只 `append` 进 `messages` 与 `session`，
不发任何事件。于是 steering 注入后 TUI 一无所知，用户看不见自己刚插的话进了上下文。

CC 踩过同一个坑并修了（`src/utils/messages.ts:3748-3756`，注释原话）：

*"Only hide from the transcript if the queued command was itself system-generated.
Human input drained mid-turn has no origin and no `QueuedCommand.isMeta` — it should
stay visible. Previously this hardcoded `isMeta:true`, which hid user-typed messages
in brief mode (`filterForBriefTool`) and in normal mode (`shouldShowUserMessage`)."*

即：CC 一度把中途 drain 进来的用户输入当系统消息藏掉了，后来专门改成「有 origin
或自带 isMeta 才藏，人打的字保持可见」。pai 现在的状态比那个 bug 还早一步——根本没有
可见/不可见这个概念，因为压根没发事件。

- 候选 (a)·新增事件（如 `SteeringInjected(count, texts)`），loop 在 `_extend` 之后发。
  代价（已核实）：`core/events.py` 的 `AgentEvent` Union 现有 16 个类
  （feature 17 加了 `ConversationCleared` / `RecallInjected`），加一个要同步
  ① dataclass + Union 成员；② `render_text` 分支；③ `tui/dock.py` 的 `handle` 分支
  （补 2 正好挂这里）；④ `tests/test_events.py` 的成员数与渲染断言。
  `modes/echo` 走 `print_event → render_text`，不需要单独改。
- 候选 (b)·不动 loop，由 `interactive` 在 drain 回调里自己上屏（回调本来就在它手里）。

我的推荐：(a)，理由三条（用户已要求「不要直接选」，这里只给推荐与理由）：

1. (b) 会让 viz 瞎掉。 feature 17 刚把「运行时流转」做成一等公民：`core/trace.py`
   把 14 种事件落 `.events.jsonl`，页面靠它点亮。steering 注入恰恰就是一次运行时流转
   （上下文被改写了）。(b) 只在 TUI 那条路上上屏，viz 与 `.events.jsonl` 里什么都没有——
   等于新功能一交付就在观测页面上留了个洞。
2. (b) 把「注入」与「显示」分家，而它们必须同真同假。 (a) 里事件在 `_extend`
   之后发，「上下文真的改了」是发事件的前提；(b) 里显示发生在 drain 回调（`_extend` 之前，
   甚至可能因为后续中断而根本没注入成）。CC 那条注释修的正是这类不一致的下游版本。
3. 成本其实是「一次性 4 处」，而非持续负担。 Union 到 16 个类不是不能再加的信号——
   `RecallInjected` 才刚加过，形状现成可抄；而 (b) 省下的这 4 处，会在
   「once 模式也要看见」「viz 也要看见」时各补一遍。

未拍板前 T2.5 不动手；T1、T2 与它无关，先走。
若最终选 (b)，T3 的 drain 回调里加两行即可，plan 其余不变。

### T3 `modes/interactive.py`：接线（队列改 steering + 注入谓词）

- 测试 `tests/test_interactive_steering.py`（新文件）：
  - 干活期间 SUBMIT 的文本进 steering 队列（假 driver 喂一条 SUBMIT）；
  - 注入谓词：`/help` 与 `!ls` 不在 `get_steering_messages()` 的返回里，
    且仍留在队列（这是 T4 的输入）；普通文本在返回里；
  - `_run_turn` 传给 `run_agent` 的是 `get_steering_messages`，不再传 `get_follow_up_messages`。
- 实现：
  - `:314` `follow_up = PendingMessageQueue("single")` → `steering = PendingMessageQueue("all")`；
  - `_run_turn` 形参 `follow_up` → `steering`，注入回调
    `get_steering_messages=lambda: steering.drain(where=_for_model)`；
  - `_for_model(msg) -> bool`：`not str(msg.get("content", "")).lstrip().startswith(("/", "!"))`；
  - `:449-451` 那段「steering 在纯 REPL 无输入源」的注释按实况改写；
  - `dock.set_queued` 的 docstring 语义 followUp → steering（`tui/dock.py:128`），
    `tests/test_tui_dock.py:127` 的用例名与断言跟着改。

### T4 本轮结束后的队列处理（CC 的 `useQueueProcessor` 那一档）

`run_agent` 返回后队列里可能还剩两种东西：被谓词滤下的 `/`、`!` 命令；
以及最后一次 drain 之后才敲进来的普通消息（`AgentEnd` 事件也会触发一次 poll，
窗口虽小但真实存在——followUp 删掉之后没人再兜它，必须在这里兜）。

- 测试 `tests/test_interactive_steering.py`：
  - 队列里剩 `/help` → 本轮结束后走 `_dispatch_command`，内容从未进过 `messages`
    （这条正是「不能当文本发给模型」的验收）；
  - 剩两条命令 → 逐条执行（照 CC 的错误隔离/退码/进度 UI 那条理由）；
  - 剩普通消息 → 起新一轮（`_run_turn` 被再调用一次），不静默丢；
  - 命令与消息混排 → 按 FIFO 顺序处理，不重排；
  - 处理完 `dock.set_queued(0)`。
- 补 2（2026-08-13 增补）：dock 待决数在中途 drain 之后不会减。
  已核实：`set_queued` 只在 `interactive.py:766`（干活期间 enqueue 时）与 `:831`
  （本轮结束的 `finally`）被调用，两处都在 TUI 主循环里；`run_agent` 内部 drain 掉
  队列之后没有任何人更新，界面会一直显示 drain 前的旧数字，直到本轮结束才跳回真值。
  这与补 1 是同一件事的两半（「注入了但界面不知道」），一起解决：
  补 1 选 (a) 就挂在 `dock.handle(SteeringInjected)` 上，选 (b) 就在 drain 回调里更新。
  - 测试要钉住的不是「drain 后调了 set_queued」，而是
    drain 之后 dock 的 queued 数等于队列的真实剩余量（例如队列里 2 条消息 + 1 条 `/`
    命令，中途 drain 走 2 条消息后 dock 应显示 1，不是 3、也不是 0）——
    快照式断言才防得住「更新了但更新成旧值」。
- 实现：`_drain_queue_after_turn(...)`，放在 `:814-835` SUBMIT 分支 `_run_turn` 之后：
  `while` 队列非空 → 取队首；是命令则 `single` 模式取一条 dispatch，
  否则 `all` + `_for_model` 批量取走起新一轮。
  上界要有（比如一次最多转 N 轮），否则「命令又往队列里塞消息」能转成死循环。

### T5 e2e：真跑一遍（假 provider）

- 测试 `tests/test_e2e_steering.py`（沿用 feature 15 的假 provider + pty）：
  - 模型第一轮调工具、工具跑着的时候喂一行输入 → 下一次请求体里看得见那句话
    （断言打在假 provider 收到的 messages 上，这是「本轮内注入」唯一硬证据）；
  - 模型第一轮就直接作答（不调工具）+ 队列非空 → 消息仍被注入、又跑了一轮
    （前置缺陷的 e2e 版，与 T2 的单测互为反证）；
  - 干活期间喂 `/help` → 请求体里没有 `/help`，屏幕上有命令的输出。

## 收尾（不算 task，但不做就不算交付）

1. `./test.sh` 全绿，贴真实数字；`STATUS.md` 测试数对账（有机器校验）。
   另有四处 STATUS 正文要改（无机器校验，漏了就是文档与现实各说各话）：
   `:12` 「steering/followUp 双队列」、`:35` 「干活时打的字进 followUp 队列」、
   `:59` `core/queue.py` 那行的「followUp 已通电；steering 有注入点无输入源」、
   `:225` 「steering 无真实输入源」。
2. `features/18/devlog.md` 一步一条，红→绿数字真实。
3. 交付即复盘：`复盘.md` 四问，其中「我现在质疑什么」必答——
   本次最该被质疑的候选：默认改 steering 之后「不要打断你」彻底无法表达（问 2 选的不留），
   真跑几天再看这个取舍站不站得住。
4. 关 TODO 三条：05 拍板问 2 / 12 spec G6 / 本次的前置缺陷。
5. 档案头部状态 → 已交付；`features/README.md` 交付总览那行改写。
6. 够格升格 decisions 的一条（补 3，2026-08-13 改写措辞）：
   原写「pai 只留一条消息队列」——说小了。复核 CC 源码后确认 T2 的第二出口
   比 CC 强，这条 decisions 应写成取长补短，并写明各自被拒绝的那一半：

   | 来源 | pai 抄的 | pai 拒的 |
   |---|---|---|
   | CC | 单队列（用户输入默认中途注入，交互式用户没有第二档手势） | `next` 的退化行为：`query.ts:558` 的 `needsFollowUp` 注释原话 *"Set during streaming whenever a tool_use block arrives — the sole loop-exit signal"*，只在 `:834` 有 tool_use 时置真。模型这轮不调工具 → `:1062` `if (!needsFollowUp)` 直接 `return {reason:'completed'}`（`:1264`/`:1357`），根本走不到 `:1570` 的 mid-turn drain。那条 `next` 只能留在队列里等 turn 结束、由 `useQueueProcessor` 开一个新 query——即 CC 的 `next` 在这种轮次上退化成 `later` |
   | pi | 第二出口：`loop.py:283` 也查一次 steering，在同一个 run 内解决——形状取自 pi 内层 while 的 `\|\| pendingMessages.length > 0`（`agent-loop.ts:174`），「队列非空就不许退出」 | 双队列结构（`steeringQueue`/`followUpQueue` 两个对象把「什么时候发」这个问题推给集成方，pai 的答案是一条队列 + 两个出口） |

   一句话：单队列取自 CC，第二出口取自 pi——两家各拿一半，且拒掉的那一半要写进正文，
   否则读者会以为 pai 只是抄了 CC。交付时定编号。
