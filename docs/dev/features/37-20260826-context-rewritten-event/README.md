# 37-context-rewritten-event
状态：已交付
分支：`refactor/37-context-rewritten-event`
流程：中等改动直做（无 spec/plan）。理由：refactor，外部行为一个字不变——
      改的是「上下文被改写之后谁来作废跨轮状态」这件事的传递方式，
      从穿参数改成听事件。没有新能力可 spec。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

用户 2026-08-26 指示：「把 on_context_rewritten 升格成事件」。

出处是我自己连着两轮复盘提的同一条质疑，已登记 TODO
（[35 复盘质疑二](../35-20260826-todo-backlog-batch-2/复盘.md)、
[36 复盘质疑二](../36-20260826-path-scoped-instructions/复盘.md)）：

`on_context_rewritten` 是 feature 35 为「压缩之后召回去重表要作废」加的注入回调，
feature 36 又给它接了第二个消费者（规则注入表）。问题是它与观测流各修各的——
loop 在同一个位置本来就发 `Compacted`，`/clear` 本来就发 `ConversationCleared`，
而这个回调是第二条并行的通知链。代价是穿参数：src 里 28 处引用，
大半是把它从 `run_agent` 一路穿到 `_run_turn` / `_handle_command` / `_manual_compact`
与 REPL、TUI 两条路的八个调用点。第三个消费者出现时还要再穿一遍。

验收标准：

1. `run_agent` 不再有 `on_context_rewritten` 参数；八个调用点上的穿参数全部消失。
2. 行为逐字不变：压缩 / `/compact` / `/clear` 之后，召回去重表与规则注入表照旧作废。
3. 「哪些事件意味着上下文被改写」在 `events.py` 里有唯一的家。
4. `./test.sh` 全绿，STATUS 数字同步。

## 候选方案与确认

问 1：升格成哪种形状？（三个候选都能把参数拆掉，差别在「上下文被改写」这件事
有没有自己的名字、以及观测流里多不多一条）

- 候选 A·事件集合常量：不新增事件，在 `events.py` 立一个具名的
  `CONTEXT_REWRITING = (Compacted, ConversationCleared)`，装配层与任何将来的
  消费者都按它判。「哪些事件意味着上下文被改写」从此有唯一的家；
  零新事件、观测流与 viz 不变。代价：仍是按类型集合判定，不如一条独立事件直白。
- 候选 B·新增 `ContextRewritten` 事件：压缩成功与 `/clear` 两处各发一条
  （与现有的 `Compacted` / `ConversationCleared` 并存），装配层只听它。
  语义最显式、谁都能订阅。代价：同一个位置发两条事件（一件事两个名字），
  viz 时间线要处理冗余，EVENT_SRC 与节点映射跟着加。
- 候选 C·直接听那两条，不立名字：装配层就地
  `isinstance(e, (Compacted, ConversationCleared))`。改动最小。
  代价：将来第三种改写方式（microcompact、resume 重建…）出现时，忘了往这个元组
  里加就是静默漏——而召回衰减这类 bug 本来就不会报错。

选择：A（事件集合常量）。理由：用户选了推荐项。

## 结果与总结

`on_context_rewritten` 这个参数没了：src 与 tests 里 28 处引用归零
（只剩三处历史叙述——常量注释与两条 TODO 追记，那是留痕不是引用）。

换上的是三样东西：

1. `events.CONTEXT_REWRITING = (Compacted, ConversationCleared)`——「哪些事件
   意味着上下文被改写」唯一的家，常量旁写清加新成员的判据（这个事件之后，
   「某条消息还在上下文里」会不会变成假的）。
2. `Assembly.state_listener`——一个事件监听器，收到集合里的事件就清召回去重表
   与规则注入表。
3. 三处并联（once、REPL、`_run_tui` 自建的 handler），与既有的 `trace` 是同一处
   安排、同一个理由：TUI 那条路不经过外层 compose。

行为逐字不变：压缩 / `/compact` / `/clear` 之后两张表照旧作废。纵切钉住
（真跑两轮 REPL，中间 `/clear`，第一轮召回过的记忆必须能重新被选中），
三处接线各做一次注入反证（拆掉任一处都红）。

测试：`1487 passed, 3 deselected in 163.21s`（此前 1481）。feature 35/36 写的
六条测试跟着机制搬家——意思没变，断言从「回调被调用」改成「发了一条
CONTEXT_REWRITING 事件」。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处 -->

实现层无新增遗留：这是一次收口，没有留下半成品。
一条诚实边界写在 `state_listener` 的 docstring 里而不是当遗留登记：跨轮状态的
作废从此挂在观测通道上，`on_event` 为 None 的路径不会触发作废——生产的三条路
（once / REPL / TUI）都恒有 on_event，真正没有的是某些测试。

[复盘](复盘.md)引出的条目已登记 [TODO](../../TODO.md)。

## 用到的知识

无新增精读：改的是自家已交付机制的传递方式。
