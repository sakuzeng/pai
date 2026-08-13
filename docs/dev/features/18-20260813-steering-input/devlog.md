# 18-steering-input 开发日志

一步一条，红→绿贴真实数字。全局 devlog 只留里程碑一行。

## 2026-08-13 立项与七问拍板

目标：给 steering 队列接真实输入源，设计依据取 CC 而非 pi。

- 建档案（README/spec），`.active` → 18，需求池记原话，TODO 登记前置缺陷 + 两条旧登记加指针。
- 抛五问，用户在其中两问上**没有直接选而是要求先核实**，各改写一条结论：
  - 问 3「cc是怎样做的呢」→ 读 v2.1.88 源码，确认**两个 drain 点都是批量**
    （`query.ts:1570` 拿快照整批转 attachment + `:1642` 整批 remove；
    `queueProcessor.ts` 用 `dequeueAllMatching`），逐条出队只用于 slash/bash。
    我抛问时标了「未复核」的推断方向对、说法不准，已在 spec 与 knowledge 笔记两处改写。
  - 问 2 反问注入时机 → 答清两条边界（不是工具跑一半插入，是本批结果回填完、
    下次请求前；且前提是这轮模型调了工具——**该前提当前不成立**，正是前置缺陷）。
- 追加两问（前几问的组合造出来的）：前置缺陷修法取 **(a) 两个出口**、
  被推迟的 `/` 命令**跟 CC 一致**存同一条队列。
- 七问结论表见 [spec.md](spec.md) 末尾，完整问答存档见 [README.md](README.md)。
- 写 [plan.md](plan.md) T1–T5；随后按用户增补补 T2.5（注入可见性，待拍）、
  T4 的 dock 计数、收尾第 6 条 decisions 措辞（单队列取自 CC、第二出口取自 pi）。

## 2026-08-13 T1：`core/queue.py` 的 `drain()` 加可选谓词

**目标**：让一条队列能同时装「要发给模型的消息」与「给客户端执行的 `/`、`!` 命令」，
注入时把后者滤掉**且留在队列里**（问 7「跟 CC 一致」的落点）。

**改了哪些文件**
- `tests/test_queue.py`：+6 条谓词用例，模块 docstring 改写（两种模式的理由改成 CC 实测口径）。
- `src/pai/core/queue.py`：`drain(where=None)`；模块 docstring 整段重写
  （原文写着「steering 至今没有真实输入源」「followUp 才是通电的那条」，本次交付作废）。

**红**（写完测试、未改实现）：

```
5 failed, 8 passed in 0.45s
TypeError: drain() got an unexpected keyword argument 'where'
```

**绿**：

```
tests/test_queue.py .............   13 passed in 0.43s
./test.sh                           1075 passed, 3 deselected in 80.32s
```

**两个实现取舍**（测试先钉死的行为，不是随手写的）
1. `all` + 谓词：不匹配的**按原顺序留在队列**（`test_..._leaves_unmatched_in_place`）。
   丢掉就等于命令被静默吞了。
2. `single` + 谓词：队首不匹配时**往后找**，不是返回 `[]`
   （`test_drain_single_with_predicate_takes_first_match_not_first_item`）。
   返回 `[]` 的话，一条 `/help` 能把它后面的所有消息永久堵住——这是单队列混装的必然坑。

**顺带**：`STATUS.md` 测试数 1069 → 1075（机器对账，改完才全绿）。

**已知缺陷 / 待办**：无新增。T2.5（注入可见性 (a)/(b)）待用户拍板，未动手。

## 2026-08-13 T2：`core/loop.py` 删 followUp 参数 + `:283` 改查 steering（前置缺陷）

**目标**：给 steering 开第二个出口，模型这轮不调工具时也能注入（问 6 选的 (a)）。

**一个值得记的发现**：前置缺陷**不是漏写，是被一条测试钉成了「正确行为」**。
原 `test_steering_not_called_when_model_gives_final_answer` 的 docstring 写着
「语义边界：steering 是『工具执行后』的挂点，**没有工具调用就不该问它**」，
断言 `calls == []`。也就是说 feature 05 当时是**有意**这么设计的，
只是没意识到那样队列会永久卡死。本次把这条测试整个反过来
（`test_steering_is_polled_when_model_gives_final_answer`，断言 `calls == [1]`），
docstring 里写清为什么反。**改测试的断言方向要留下理由**，否则下一个人只会看到
「有人把测试改绿了」。

**改了哪些文件**
- `tests/test_loop.py`：+`import pytest`；反转一条、改写一条、新增两条（两个出口同 run 生效、
  `get_follow_up_messages` 已删则报 `TypeError`）。
- `src/pai/core/loop.py`：删 `:103` 的 `get_follow_up_messages` 形参；
  `:283` 分支改查 steering，注释写清形状取自 pi 的内层 while、以及 CC 在这种轮次会退化。

**红**：

```
4 failed, 67 passed in 0.82s
FAILED test_steering_is_polled_when_model_gives_final_answer   （assert [] == [1]）
FAILED test_steering_keeps_loop_running_when_model_stops       （停在第一轮）
FAILED test_steering_has_two_outlets_in_one_run                （结束出口没注入）
FAILED test_follow_up_parameter_is_gone                        （DID NOT RAISE TypeError）
```

**绿（本 task 范围）**：`tests/test_loop.py 71 passed in 1.71s`

**全量仍红，且是预期的中间态**：`33 failed, 1044 passed`——全部集中在
`test_interactive.py` / `test_trace_wiring.py` / e2e 三处，根因同一个：
`modes/interactive.py:452` 还在传已被删除的 `get_follow_up_messages=`，
**而 `_guarded_run` 会把这个 `TypeError` 吞成一行「❌ 请求失败」**，
于是症状不是崩溃而是「整轮没跑」（`test_slash_clear_leaves_a_marker_in_the_event_stream`
的报错是 `AgentStart` 一个都没有）。T3 接线即恢复。
**顺带印证了 `test_follow_up_parameter_is_gone` 那条的必要性**：
调用方签名对不上时，这个系统的默认行为是**静默降级**而不是响亮失败。

**已知缺陷 / 待办**：全量红（T3 前的必然中间态），不得在此状态宣告任何交付。

## 2026-08-13 T2.5：`SteeringInjected` 事件（注入可见性）

**拍板**：用户选 (a) 新增事件（候选与实测成本见 [plan.md](plan.md) T2.5 节）。
拍板前把两条路都到代码里量了一遍，量出两条改变判断的事实：
1. `core/trace.py` 是**泛型**的（`"event": type(event).__name__`，只排除 `MessageDelta`），
   所以发了事件就**自动**落 `.events.jsonl`、自动上 viz 时间线，零额外代码；
2. `viz/collect.py` 的 `EVENT_SRC` 有机器强制
   （`tests/test_viz_collect.py:163` 断言键集合恰等于事件类名集合）。
   即 (a) 的「多改一处」实际是护栏，不是负担。

**改了哪些文件**
- `core/events.py`：`SteeringInjected(texts)` + Union（16 → **17**）+ `render_text` 分支
  + `_clip()` 辅助（按字符数截断，显示宽度的活不在事件层重做）。
- `core/loop.py`：`_extend` 多收一个 `on_event`，**追加完成之后**发事件；两个出口都传。
- `viz/collect.py`：`EVENT_SRC` 登记，指向 `core/queue.py`
  （机制住在队列，loop 只是它的两个注入出口）。
- `tests/`：`test_events.py` +3、`test_loop.py` +3、`test_trace.py` 的 `SAMPLES` +1。

**一个字段设计的取舍**：用户抛问时写的是 `SteeringInjected(count, texts)`，
实现取 **只留 `texts`**——`count` 就是 `len(texts)`，两个字段就是两个事实源
（照 `RecallInjected(names=...)` 的现成先例，它也没有 count）。

**红**：

```
6 failed, 91 passed in 0.88s
ImportError: cannot import name 'SteeringInjected' from 'pai.core.events'
```

**第二道红（实现到一半冒出来的，正好印证 (a) 的价值）**：

```
FAILED tests/test_trace.py::test_every_event_type_is_covered_by_samples
AssertionError: assert {'MessageDelta', 'SteeringInjected'} == {'MessageDelta'}
```

`EVENT_SRC` 与 `SAMPLES` **两道机器护栏都拦住了**：新增事件不登记「机制住哪」、
不给观测流样本，测试当场红。这正是选 (a) 而不是 (b) 买到的东西——
(b) 那条路上没有任何机制会提醒你「viz 看不见这个」。

**绿（本 task 范围）**：`tests/test_events.py + test_loop.py + test_viz_collect.py
+ test_trace.py = 105 passed in 0.77s`

**时序被测试钉死**：`test_steering_event_comes_after_the_messages_are_in`——
发事件时那条消息必须已经在 `messages` 里。这条钉的正是 (b) 的毛病
（显示发生在注入之前，中断/抛错时屏幕与上下文会各说各话）。

**一处刻意的边界**：`_extend` 的 `on_event` 默认 `None`，`:160` 那处召回注入**不传**——
系统注入不是用户插话，不该顶着 steering 的名义上屏。

**已知缺陷 / 待办**：全量仍红（T3 未接线），同 T2。dock 计数（补 2）留在 T4。

## 2026-08-13 T3：`modes/interactive.py` 接线（队列改 steering + 注入谓词）

**目标**：把 TUI 干活期间的输入接到 steering 上，并让 `/`、`!` 留在队列里不进模型。

**改了哪些文件**
- `src/pai/modes/interactive.py`：
  - `follow_up = PendingMessageQueue("single")` → `steering = PendingMessageQueue("all")`；
  - `_run_turn` / `_run_tui` 的形参与 5 处调用点跟着改名；
  - 注入回调 `get_steering_messages=lambda: steering.drain(where=_for_model)`；
  - 新增 `_for_model()` 谓词；
  - **模块 docstring 的诚实边界改写**（原文「只有 followUp 队列有真实输入源」作废）；
  - `:768` SUBMIT 分支的注释从「拍板问 4：排队」改成「问 1：本轮就注入」。
- `src/pai/tui/dock.py`：`set_queued` 的 docstring 语义 followUp → 待注入量。
- `tests/test_interactive_steering.py`（新）：10 条。
- `tests/test_tui_dock.py`：`test_queue_area_shows_follow_ups` 改名 + 写清语义变了。

**红**：

```
ImportError: cannot import name '_for_model' from 'pai.modes.interactive'
1 error during collection
```

**绿（本 task 范围）**：

```
tests/test_interactive_steering.py + test_interactive.py + test_tui_dock.py
+ test_trace_wiring.py = 90 passed in 0.52s
```

**谓词单独钉 6 条**，其中一条是真会漏的：`  /help`（前面有空格）——
用户敲空格再敲 `/` 是常事，按裸 `startswith` 判就把命令当文本发给模型了。
`_for_model` 是「命令不进模型」这条硬约束的**唯一守门人**，所以边界情况全列出来。

**两条测的是「装配」而不是「逻辑」**：`test_the_queue_is_all_mode` 与
`test_no_follow_up_symbol_left_in_the_module` 直接读源码断言——
队列建成 `single` 模式、或者 followUp 删了一半留一半，单元逻辑再对也没用，
而这两种错都不会让别的测试变红。

**已知缺陷 / 待办**：dock 计数（补 2）与轮末命令执行（T4）尚未做——
现在 `/help` 进队列后**会被谓词滤掉然后一直留在那**，直到 T4 才有人取走执行。

## 2026-08-13 T4：轮末队列处理 + dock 计数跟着 drain 减（补 2）

**目标**：补上 T3 那个洞（命令进队列后没人取），并让 dock 的待决数在**本轮内**准确。

**改了哪些文件**
- `src/pai/core/queue.py`：加 `take_first()`（FIFO 取队首，不看模式不看谓词）。
- `src/pai/modes/interactive.py`：`MAX_QUEUE_ROUNDS = 8`、`_steering_source()`、
  `_process_queue_after_turn()`；`_run_turn` 多收 `on_queue_change`；
  TUI 的 SUBMIT 分支改成 `turn()` 闭包 + 轮末处理 + `/exit` 收尾。
- `tests/test_queue.py` +2、`tests/test_interactive_steering.py` +11。

**红**：

```
tests/test_queue.py            2 failed, 13 passed   AttributeError: 'PendingMessageQueue' object has no attribute 'take_first'
tests/test_interactive_steering.py  1 error          ImportError: cannot import name 'MAX_QUEUE_ROUNDS'
```

**绿**：`test_interactive_steering.py + test_queue.py + test_interactive.py = 79 passed in 0.85s`

### 写实现时撞出来的一个真漏洞：排队的 `/exit` 会被无视

`_dispatch_command` 的返回值是 **bool = 该退出 REPL**（主循环里是 `if _dispatch_command(...): return`）。
我第一版的 dispatch 回调把这个返回值丢了，于是干活期间敲的 `/exit` 会：
**执行 → 然后继续处理队列 → 又起一轮新对话**。用户说了退出，pai 却接着聊。

补了 `test_a_command_that_asks_to_exit_stops_the_processing`，红的输出是
`assert 2 == 1`（`/exit` 之后又跑了一轮）；实现改成 `dispatch` 返真即 `break`，
剩下的**留在队列里**由调用方收尾，并在 SUBMIT 分支加 `or exiting["v"]` 走同一条退出路径。

**这条不是测试推出来的，是核对 `_dispatch_command` 契约时读出来的**——
lambda 吞掉返回值这类错，类型注解不写就没人拦（现在 `dispatch` 标了 `Callable[[str], bool]`）。

### 两处设计取舍

**① 补 2 挂在 `_steering_source` 而不是 `SteeringInjected` 事件上。**
两者分工不同：事件负责**上屏可见**（transcript + 观测流 + viz），
`_steering_source` 负责**计数准确**。选它的实际理由是可测性——
事件那条路只在 TUI 的 `on_event` 闭包里够得着，单测碰不到（只能靠 e2e），
而工厂函数能直接断言剩余量。测试写成**快照式**（plan 补 2 要求的那种）：
2 条消息 + 1 条 `/help`，drain 走 2 条后必须报 **1**——报 3 是没更新，报 0 是骗人。

**② 轮末残余是「一条消息一轮」，不是 CC 的「批量塞进一个新 query」。**
因为 `run_agent(task)` 的 `task` 同时喂给 `AgentStart` 与 `recall()`，
把 N 条拼成一个字符串会把这两处一起弄脏。这条路上本来也只剩零星残余
（两个注入出口已经批量取过了）。偏离已记进函数 docstring。

**③ 与 plan 的两处偏离**（2026-08-13 补记，用户画流程图时对出来的——
plan 是提案不是实况，但**两边不一致就得有人说一句**）：
- 函数名：plan 写 `_drain_queue_after_turn`，实现叫 **`_process_queue_after_turn`**。
  `knowledge/loop/cc-loop.md` 当时引的是 plan 里那个名字，已一并改正
  （笔记是长期参照，指着一个不存在的符号最伤）。
- 取法：plan 写「命令逐条 dispatch，普通消息**批量**取走起新一轮」，
  实现是 **`take_first()` 逐条 FIFO，两种东西一视同仁**。
  改的理由就是上面②那条（`run_agent(task)` 收单个字符串），
  顺带换来一个好处：**混排时严格按用户敲的顺序处理，不重排**——
  批量取消息会把「先敲的命令、后敲的消息」重排成「消息先走」。

**上界 `MAX_QUEUE_ROUNDS = 8`**：不是怕代码写错，是怕真跑时用户一直在打字
（每起一轮新的又会 poll 到新输入）。撞上界就把剩下的留在队列里，下一轮结束还会再处理，
**消息不丢，只是晚一点**——测试钉死了「剩下的还在队列里」。

**已知缺陷 / 待办**：T5 的 e2e 未做（「本轮内注入」目前只有单测层面的证据）。

## 2026-08-13 T5：e2e —— 两轮假绿，两轮都是测试写错

**目标**：把「干活期间打的字本轮就进模型」钉在**假 provider 真收到的请求体**上。

**改了哪些文件**
- `tests/test_e2e_steering.py`（新）：6 条。
- `tests/fake_provider.py`：`turn()` 加 `delay`（逐字符停顿）。
- `tests/test_e2e_tui.py`：`test_typing_while_busy_lands_in_the_queue` 的 docstring
  改写（12 的「排队等本轮结束」语义已作废，断言本身两种语义下都成立故不动）。

**绿**：`tests/test_e2e_steering.py 6 passed in 27.49s`；
全量 `1 failed, 1111 passed in 109.29s`（那 1 条是 STATUS 计数，收尾一并改）。

### 假绿一：假 provider 秒答，「模型正在答」这个状态根本不存在

第一版直接抄了 12 那条 e2e 的写法（`wait=0.05` 然后发第二行）。屏幕证据：

```
● 第一轮答完
✳ 用时 0s
● 第二轮答完
✳ 用时 0s        ← 两个「用时」= 两次 AgentEnd = 两轮
```

于是「干活期间打字」在**不调工具的轮次**上没有任何窗口可测。
修法：给 `turn()` 加 `delay`，**逐字符停顿而不是整轮停顿**——
TUI 靠**每个事件**顺手 poll 一次键盘（`interactive.py` 的 `on_event`），
整轮停顿期间一个事件都不发，键还是读不到。

### 假绿二：两行输入落进了同一批 poll

加了 `delay` 仍是两个「用时」。**推理推不动，去读观测流**——
临时探针读 `.events.jsonl`，事件序列是：

```
['AgentStart', 'AssistantMessage', 'AgentEnd', 'AgentStart', 'AssistantMessage', 'AgentEnd']
```

两次 `AgentStart`、零条 `SteeringInjected`。真因：`s.send("第一个问题\r", wait=0.1)`
太快，第一行还没被主循环取走，第二行就写进了 pty，而
**`driver.poll()` 会把已排队的数据一次读干净**（那是给鼠标事件合并用的设计，
`driver.py:59-65` 写着理由），于是两行落进同一批 → 两个 SUBMIT 都走主循环、各起一轮。

修法：`_wait_for_request()`——**等条件（provider 真收到第 1 次请求）而不是等秒数**。
理由与 `Session.send` 的 `until` 一模一样：死等既慢又脆。

> **这两条都写进了测试注释**：下一个人照着 12 那条 e2e 的形状写新的，会踩同样两脚。

### 「本轮注入」在 e2e 层怎么证明

两种语义在**请求体**上大多分不出来（REPL 跨轮共享 `messages`，新起一轮的消息序列
长得一模一样）。最后落在两处硬区别：

- 工具那条：`sent[-2]["role"] == "tool"`——注入的消息紧跟工具结果；
  新起一轮的话中间会隔着这一轮的 assistant 回答。
- 不调工具那条：`screen.count("用时") == 1`——一次 run 只发一条 `AgentEnd`。

**术语脚注**（用户当场问「本轮指的是 turn 还是 loop/query」，答案值得留下）：
本档案所有「本轮」= **一次 run = 一次 `run_agent()` 调用**（pi 叫 run、CC 叫 query）；
pai 内部那一步叫 `step`。见 K [loop/cc-loop.md](../../../../knowledge/loop/cc-loop.md) 第二节对照表。

### 旁生的发现（不属于本 feature，已登记 TODO）

探针的事件序列里**没有 `TurnStart`**——查下来 `src/` 里没有任何一处发它，
而 `viz/collect.py:150` 声称它住在 `core/loop.py`、`viz/index.html:302` 还给它配了节点。
即 viz 时间线上那一格**永远不会亮**。`EVENT_SRC` 的防漂移测试挡不住这类：
它只校验「键集合 == 事件类名集合」，校验不了「这个事件真有人发」。
连带一条术语债：事件名叫 `TurnStart`、字段却是 `step`。两条都进了 TODO，
并由用户升格成 **feature 19**（术语完全对齐 pi/CC + viz-v2 上把步数预算做可见）。
