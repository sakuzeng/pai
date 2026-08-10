# 05-20260810-repl · 开发日志

一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。
基线：`115 passed, 3 deselected`（feat/repl 分支自 feat/compaction 开出）。

## 2026-08-10 · Task 1：事件流定型（core/events.py）

**目标**：把 loop 里拼好的中文字符串换成结构化事件，渲染下放给上层；
硬约束是 `once` 模式**输出一字不变**。

**改动**：新建 `src/pai/core/events.py`（10 个 frozen dataclass + `AgentEvent` 联合 +
`render_text`）、`tests/test_events.py`。loop 本体这一步不动（Task 5 才接线）。

**测试**：红 `ModuleNotFoundError: No module named 'pai.core.events'`（collection error）
→ 绿 **`120 passed, 3 deselected`**（115 → 120，+5）。

**设计要点**（挑三条会被问到的）：
- `LEGACY_*` 常量把改造前 loop.py 五处 `on_event` 的原文抄进测试当唯一事实源——
  这是「行为一字不变」唯一可机器校验的形式。
- `render_text` 返回 `Optional[str]`，`None` = 默认不打印。**不用空串**：
  `print("")` 会吐空行，「不打印」与「打印空行」是两回事。
- 3.9 运行期不认 `X | Y` 做类型别名（PEP 604 是 3.10），`AgentEvent` 必须写 `Union[...]`；
  `from __future__ import annotations` 只救注解，救不了别名（AGENTS.md 那条注记的实例）。

**遗留**：`ToolEnd.is_error` 只覆盖 loop 自造的错（参数非法/未知工具），
工具内部异常被 `Tool.run` 吸收成字符串无从分辨——要真区分得改 `Tool.run` 返回契约，
不在本轮范围，登记 TODO。

## 2026-08-10 · Task 2：PendingMessageQueue（core/queue.py）

**目标**：steering/followUp 两条队列的结构与 drain 语义。

**改动**：新建 `src/pai/core/queue.py`、`tests/test_queue.py`。

**测试**：红 `ModuleNotFoundError: No module named 'pai.core.queue'` → 绿
**`127 passed, 3 deselected`**（120 → 127，+7；计划估 +5，实际多写了两条边界测试）。

**设计要点**：两种 drain 模式不是凑 pi 的形状——steering 用 `all`（用户连打三句通常是
同一个转向意图，拆开逐轮注入反而错乱），followUp 用 `single`（每条各触发一轮，
中间还可能被中断）。`drain` 返回切片不返回内部列表引用（同 FakeClient 存引用那个坑）；
未知 mode 构造期就报错，不静默降级。

**遗留**：无。

## 2026-08-10 · Task 3：中断标志（core/interrupt.py）

**目标**：一个能被 Ctrl+C 置位、被工具与 loop 同时看见的标志。

**改动**：新建 `src/pai/core/interrupt.py`、`tests/test_interrupt.py`。

**测试**：红 `ImportError: cannot import name 'interrupt' from 'pai.core'` → 绿
**`131 passed, 3 deselected`**（+4）。

**设计要点**：进程级单例而非依赖注入——`@tool` 从函数签名生成 schema，给 bash 加个
flag 参数会把它发给模型看。这是「schema 与代码同源」的直接代价，取舍要进 decisions。
`current()` 永不返回 None（否则每个调用点都要判空）；包 `threading.Event` 而非裸 bool，
因为 TUI/流式阶段一定会有读输入的线程来置位。

**遗留**：全局状态的老问题——测试必须能干净复位，靠 `set_current(None)` 与
`tests/test_tools.py` 的 `_injected_flag()` contextmanager 兜住。

## 2026-08-10 · Task 4：bash 可中断到进程组（core/tools/shell.py）

**目标**：Ctrl+C 真能打断跑飞的命令（拍板问 3 选 B 的落地）。

**改动**：`shell.py` 从 `subprocess.run` 改为 `Popen(start_new_session=True)` + 轮询等待
（`POLL_SECONDS=0.1`）+ `os.killpg(SIGKILL)`；`tests/test_tools.py` 加 5 条。

**测试**：红 **`4 failed, 10 passed in 91.17s`**（91 秒是因为 `sleep 30` 全白等到 60s 超时，
正是要修的东西）→ 绿 `tests/test_tools.py` **`14 passed in 6.60s`**，全套
**`136 passed, 3 deselected in 9.25s`**（131 → 136，+5）。

**注入反证**（计划要求）：把 `os.killpg(...)` 换成 `proc.kill()`，
`test_bash_kills_whole_process_group_not_just_the_child` **确实变红**，
但红的位置比预期更靠前——不是「孙进程还活着」这条断言，而是更前面的
`assert m`（没拿到 PID）：**杀不掉整组时，后台 `sleep` 仍握着 stdout 管道，
`communicate` 收不到 EOF，连已产出的输出都一起丢了**。同一个根因的两个症状，
反而更说明只杀子进程是错的。已还原实现。

**顺带修正的一处不实话**：超时提示原文是「若含后台进程，它可能仍在运行」——
现在整组被杀，这话不再成立，改为「命令与其整个进程组已被终止」。

**遗留**：`_Killed` 是内部控制流异常（把已组织好的话带出轮询循环），不是错误路径；
若将来 `_wait` 长出第三种终止原因要留意别把它当成异常处理。

## 2026-08-10 · Task 5：loop 接线（事件 + 双队列 + 中断）

**目标**：本轮唯一的破坏性改动——`on_event` 从收字符串改为收事件对象，
同时把 steering/followUp 两个注入点与中断接进 loop。

**改动**：`src/pai/core/loop.py`（大改）、`src/pai/modes/once.py`（默认处理器）、
`tests/test_loop.py`（2 条改写 + 11 条新增）、`tests/test_modes.py`（+2）。

**测试**：红 **`12 failed, 23 passed`**（2 条原断字符串的测试 + 10 条新增；
`TypeError: run_agent() got an unexpected keyword argument ...` 与事件断言失败）
→ 绿全套 **`148 passed, 3 deselected`**（136 → 148，+12），
补完下面那条回归测试后 **`149 passed, 3 deselected`**。

**设计要点**：
- 两条原本断字符串的压缩测试改成**断事件类型与字段**（`CompactionSkipped.reason`），
  比断中文文案更强：文案可以改，语义不能改。
- 中断不是「跳过剩下的工具」而是「剩下的各回一条『已取消』」——
  `test_interrupt_backfills_remaining_tool_calls` 钉死三个 `tool_call_id` 一一配对。
  这条要是漏了，下一轮请求就是 400（R#11 有真实复现路径）。
- steering 注入点必须在**本轮所有工具结果回填之后**：插在中间会劈开 tool_calls
  与它的结果，配对当场断裂。`test_steering_not_called_when_model_gives_final_answer`
  钉住语义边界（没有工具调用就不该问 steering）。
- `messages` 传入即续用，且 `compact` 的结果用 `messages[:]` **原地替换**——
  调用方（REPL）持有的是同一个列表对象，换绑变量会让它拿到压缩前的旧历史。
- 工具执行分派抽成 `_run_tool` 返回 `(args, result, is_error)`，loop 主体只管发事件。

**回归修正**：`once.py` 的默认 `on_event=print` 改为 `print_event`——
不改的话用户屏幕上会是一串 `ToolEnd(...)` dataclass repr。测试注入了假 handler
所以第一轮全绿也照不出来，补 `test_once_default_event_handler_prints_rendered_text`
用 `capsys` 断言实际打印内容（含那个「一字不变」的基准串）。

**遗留**：`AgentStart` 事件在 `messages` 续用时仍带 `task` 字段，语义上是「本轮的任务」
而非「整个会话的任务」——REPL 多轮时字段名会有点歧义，暂不改，记档。

## 2026-08-10 · Task 6：AskUserQuestion（core/tools/ask.py）

**目标**：模型拿不准时问真人，而不是猜着往下做。

**改动**：新建 `src/pai/core/tools/ask.py`；`tools/__init__.py` 加 `INTERACTIVE_ONLY`
让默认工具集排除它；`tests/test_tools.py` +5。

**测试**：红 `5 failed, 14 passed`（`ImportError` + `KeyError: 'ask_user_question'`）
→ 绿全套 **`154 passed, 3 deselected`**（149 → 154，+5）。

**设计要点**：候选项只能是 **JSON 数组字符串**——`@tool` 只认标量参数，这是
「schema 与代码同源」的直接后果，所以 `Annotated` 描述里必须把格式讲给模型听
（`test_ask_schema_is_generated_from_signature` 断言描述里有 "JSON"）。
「注册了但不进默认集合」比「不注册」好：`once` 看不见它，交互模式显式点名要回来，
一个注册表两种视图。少于两个选项直接报错——只有一个选项的「提问」是通知，不该打断真人。

**遗留**：无。

## 2026-08-10 · Task 7：REPL 本体（modes/interactive.py）

**目标**：把前六个 task 组装成能用的交互模式。

**改动**：新建 `src/pai/modes/interactive.py`、`tests/test_interactive.py`（21 条）；
`cli.py` 分发（带 task 走 once，不带 task 进 REPL）；`loop.py` 加
`anchors` / `compaction_state` 两个可注入参数 + `_adopt` 写回。

**测试**：红 `ModuleNotFoundError: No module named 'pai.modes.interactive'`
→ 绿全套 **`178 passed, 3 deselected`**（154 → 178，+24）。

**中途 TDD 出来的一个真 bug**（不是计划里的 task）：`verify_compaction` 返回**新对象**，
loop 原来是 `state = verify_compaction(...)` 换绑局部变量——注入方（REPL 跨轮持有）
永远看不到失败计数，**熔断器在 REPL 里等于每轮清零、连续失败永远数不到 3**。
`test_compaction_state_updates_propagate_to_caller` 先红（`failures=0, awaiting_verify=True`）
后绿，修法是 `_adopt` 写回同一个对象。同理锚点簿也必须跨轮持有，否则每轮第一次请求
退回纯字符估算（已知 -33% 误差）——`test_anchor_book_can_be_shared_across_runs` 钉死。

**冒烟撞出的第二个真问题**：真跑 `printf ... | pai` 时，一次 401 让整个 REPL
**带栈退出**。once 崩了无所谓（本来就跑完即退），REPL 崩了等于把整段对话丢掉——
而这一层的全部价值就是「对话留着」。补 `test_model_error_does_not_kill_the_repl`
（断言两轮都报错、都没退出），实现里 catch `Exception` 后回提示符。

**冒烟实录**（`DEEPSEEK_API_KEY=dummy`，只跑不打模型的路径）：
`/help`、`!echo`、`\` 续行、`/status`（`📊 消息 3 条 | 估算 614 token / 窗口 1000000
| 锚点 0 个 | 压缩：正常（失败 0 次）`）、401 报错后继续、`/exit` 全部按预期。

**设计要点**：
- 干活期间 SIGINT **只置标志不抛异常**——抛 KeyboardInterrupt 会把已完成的工作
  连同栈一起丢掉，而官方对中断的承诺恰恰是「保留迄今完成的工作」；空闲期间恢复默认
  处理器，于是 `input()` 照常抛 KeyboardInterrupt，走两级 Ctrl+C。
- `/clear` 用 `del messages[1:]` 保留 system，而不是整段清空让下一轮重建（等价但更难解释）。
- `!命令` 不自动接话：官方 v2.1.186 起会自动接话且给了开关，pai 默认关——
  每次 `!` 自动接话就是每次都花一次请求钱。
- steering 传 `None`：纯 REPL 的阻塞 `input()` 拿不到「干活时打字」，如实标注等 TUI 通电。

**遗留**：① `_install_sigint` 在非主线程装不上（退化为不可中断），已 try/ValueError 兜住；
② REPL 无 `/resume`，会话只活在进程内（spec 非目标已声明）。

## 2026-08-10 · Task 8：工具调用状态行（modes/statusline.py）

**目标**：把用户截图里的 CC 状态行做成 pai 能做的那部分（取舍表见档案）。

**改动**：新建 `src/pai/modes/statusline.py`（`display_width` / `render_tool_line` 纯函数
+ `StatusLinePrinter` 原地刷新）、`tests/test_statusline.py`（15 条）；
`interactive.py` 加 `make_event_handler`——真 tty 走状态行，非 tty 退回滚动行。

**测试**：红 `ModuleNotFoundError: No module named 'pai.modes.statusline'`
→ 绿全套 **`193 passed, 3 deselected`**（178 → 193，+15）。

**自己给自己挖了又填的坑**：第一版 `color=True` 时直接跳过截断（因为 ANSI 转义符会让
列宽算错）——而真 tty 上走的**正是**彩色路径，等于彩色输出根本没有宽度限制。
补 `test_colored_line_is_also_width_limited`（剥掉转义符后量可见宽度）先红后绿，
改法是把 `(可见文本, 颜色)` 分开存，按可见文本算宽度、装不下的整段丢弃，最后才上色。
两个经典坑在同一个函数里撞齐了：**中文宽度**与**转义符不占列**。

**目视验证**（三种终端宽度，形状与截图一致，列宽严格不超）：

```
w= 80 列宽= 79 | ◐ bash: echo "=== improve 目录概览 ===" && ls -la | ✓ bash ×14 | ✓ read_file ×3
w= 40 列宽= 40 | ◐ bash: echo "=== improve 目录概览 ==="…
w= 24 列宽= 24 | ◐ bash: echo "=== impro…
```

**遗留**：`_preview` 取参数字典的第一个值当预览——`bash` 只有 command 所以正好，
多参数工具（`edit_file`）的预览会只显示 path，够用但不精确，记 TODO。

## 2026-08-10 · 补漏：历史文件写了但没读回 readline（05 交付后发现）

**怎么发现的**：用户问「本机现在能测什么」，我准备写「↑/↓ 翻历史」时先去核实，
`grep readline src/pai/modes/interactive.py` → **一行都没有**。

**漏在哪**：spec 写的是「`readline` 提供 ↑/↓ 与 `Ctrl+R`；历史按 cwd 分文件存」，
实现只做了后半句（写文件、按 cwd 分、连续重复只记一条），**从没把文件读回 readline**，
所以 ↑ 是死的。Task 7 的两条历史测试只断言了「文件内容对不对」，
全绿也照不出来——**测试覆盖了产物，没覆盖用途**。

**改动**：`interactive.py` 加 `_is_real_terminal_input`（谓词，可测）与
`_read_history_into_readline`；`tests/test_interactive.py` +3。
`.active` 走 `!小修` 显式放行通道（理由留档：`!小修:补 05 漏项——历史文件写了但没读回 readline`）。

**测试**：红 2 条（`AttributeError: module 'pai.modes.interactive' has no attribute
'_read_history_into_readline'`）→ 绿 **`239 passed, 3 deselected`**（235 → 239，+4）。

**中途踩的一个坑**：第一版测试写
`monkeypatch.setattr(interactive.sys, "stdin", SimpleNamespace(isatty=...))`——
`interactive.sys` **就是真的 `sys` 模块对象**，这一改把 `input()` 一起弄坏了
（`AttributeError: 'SimpleNamespace' object has no attribute 'readline'`）。
改成把条件抽成 `_is_real_terminal_input(reader)` 谓词单独测，不再动进程级 stdin。

**诚实边界**：macOS 系统 Python 的 readline 是 libedit 后端，历史文件格式与 GNU readline
略有差异；读失败按「没有历史」处理。**这条只能在真终端上验证，我在这个环境里验不了**——
需要用户本机确认 ↑ 真的能翻出上一轮的输入。
