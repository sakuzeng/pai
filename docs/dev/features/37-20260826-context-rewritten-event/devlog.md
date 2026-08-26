# 37-context-rewritten-event · 开发日志

一步一条。全局 devlog 只记里程碑一行 + 指到这里。

## 2026-08-26 · 立项与拍板

目标：把 `on_context_rewritten` 从注入回调改成事件（用户指示）。

先数了一下账：src 里 28 处引用，大半是把它从 `run_agent` 一路穿到 `_run_turn` /
`_handle_command` / `_manual_compact` 与 REPL、TUI 两条路的八个调用点。

形状有三个候选（事件集合常量 / 新增 `ContextRewritten` 事件 / 就地 isinstance），
问了用户，选 A·事件集合常量。问答原样存进 [README](README.md)。

选 A 的实质是：不给同一件事造第二个名字。压缩发 `Compacted`、`/clear` 发
`ConversationCleared` 本来就是两条事件，再加一条 `ContextRewritten` 会让同一个
位置发两条、viz 时间线还要处理冗余。缺的从来不是事件，是「哪些事件意味着上下文
被改写」这个判据没有家——那就给判据一个家。

改动：新建档案、`.active` 指过来、开分支 `refactor/37-context-rewritten-event`。

测试：无（尚未动代码）。

## 2026-08-26 · `events.CONTEXT_REWRITING`

目标：判据落地。

`CONTEXT_REWRITING = (Compacted, ConversationCleared)`，常量旁写清加新成员的
判据只有一条：这个事件发生之后，「某条消息还在上下文里」这句话会不会变成假的。
压缩（换掉）与清空（丢弃）都会；暂缓压缩、熔断、注入召回都不会。

三条测试：两条钉正反成员、一条防漂移（集合里每个都必须是 `AgentEvent` 的成员，
写错名字或留下被删掉的类就红——同 EVENT_SRC 那条守卫的理由，只是那边校验键集合、
这边校验子集关系）。

改动：`src/pai/core/events.py`、`tests/test_events.py`。
红：三条 `ImportError: cannot import name 'CONTEXT_REWRITING'`。
绿：`tests/test_events.py` `15 passed`。

## 2026-08-26 · 装配层改成事件监听器

目标：`Assembly.on_context_rewritten`（回调）→ `Assembly.state_listener`（监听器）。

监听器只做一件事：`isinstance(event, CONTEXT_REWRITING)` 就清两张表。
判据不写成就地 isinstance——那正是候选 C，会让第三种改写方式出现时静默漏。

诚实边界写进 docstring：失效因此挂在观测通道上，`on_event` 为 None 的路径不会
触发作废。生产的三条路（once / REPL / TUI）都恒有 on_event。

改动：`src/pai/modes/assembly.py`、`tests/test_assembly.py`（三条改写 + 一条新的
反向守卫：一个普通的 `ToolEnd` 不许把去重表清掉）。
红：三条 `AttributeError: 'Assembly' object has no attribute 'state_listener'`。

## 2026-08-26 · 拆参数：28 处引用归零

目标：把回调从 `run_agent` 与八个调用点上拆掉，换成三处并联。

三处并联，与既有的 `trace` 是同一处安排、同一个理由：

- `once.py`：`assemble` 之后 `on_event = compose(on_event, asm.state_listener)`；
- `interactive.py` REPL：同上一句；
- `_run_tui` 自建的 `on_event`：TUI 这条路不经过外层 compose，所以监听器要在
  那里单独喂一次（trace 早就是这么处理的，注释里写着原因）。

顺带在两个事件发射点旁写明它们现在兼一职（不只是给观测流看的）。

改动：`src/pai/core/loop.py`（删参数与调用块）、`src/pai/modes/once.py`、
`src/pai/modes/interactive.py`（13 处）、`tests/test_loop.py`、
`tests/test_interactive.py`。

feature 35/36 写的六条测试跟着机制搬家（意思没变，断言从「回调被调用」改成
「发了一条 CONTEXT_REWRITING 事件」）。搬的时候自己犯了个错并当场发现：
替换区间取反了（新节的头在旧节之后），结果把中间一段测试复制了一份——
`grep -c "def _command_kwargs"` 数出 4 个才看见。删掉重复块后 `61 passed`。

绿：`test_assembly + test_interactive + test_modes + test_loop` `219 passed`。

## 2026-08-26 · 把「没测到」补上

写完发现新加的那条 TUI 测试后半段是假的：它在 `term.start()` 上引爆之后就结束了，
而 `state_listener` 的调用点在 `on_event` 内部——引爆时那一行根本没跑到，
断言等于没有。

补法借了上一条测试的力：`_run_tui` 在 `term.start()` 之前会把自建的 `on_event`
塞进 `event_sink`（那是给装配期闭包用的可换持有者）。于是引爆之后，sink 里装的
就是那个自建 handler——喂它一条 `ConversationCleared`，监听器就该听见。

三处接线各做一次注入反证：

```
TUI 不喂状态监听器              → 1 failed, 85 passed
REPL 不 compose 监听器          → 1 failed, 85 passed
/clear 不发事件                 → 4 failed, 82 passed
```

改动：`tests/test_trace_wiring.py`。

## 2026-08-26 · 交付

`./test.sh`（venv `~/.virtualenvs/pai`，Python 3.9.6）：

```
1487 passed, 3 deselected in 163.21s (0:02:43)
```

`on_context_rewritten` 在 src 与 tests 里的引用：28 → 0（只剩三处历史叙述，
在 events.py 的常量注释与两条 TODO 追记里，那是留痕不是引用）。
