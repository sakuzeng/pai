# 05-20260810-repl · 开发日志

一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。
基线：`115 passed, 3 deselected`（feat/repl 分支自 feat/compaction 开出）。

本文件的收录范围：8 个 task 之外，还收了交付当天的五个补漏。
其中「write/edit 原子写」严格说属于 feature 00 的 `fs.py`、「测试污染 ~/.pai」属于测试基建
——放这里是因为它们都是同一轮交付之后被用户追问连锁挖出来的，
拆散到三个档案里反而看不出那条因果链。归档位置的这点勉强，如实标注。

## 2026-08-10 · Task 1：事件流定型（core/events.py）

目标：把 loop 里拼好的中文字符串换成结构化事件，渲染下放给上层；
硬约束是 `once` 模式输出一字不变。

改动：新建 `src/pai/core/events.py`（10 个 frozen dataclass + `AgentEvent` 联合 +
`render_text`）、`tests/test_events.py`。loop 本体这一步不动（Task 5 才接线）。

测试：红 `ModuleNotFoundError: No module named 'pai.core.events'`（collection error）
→ 绿 `120 passed, 3 deselected`（115 → 120，+5）。

设计要点（挑三条会被问到的）：
- `LEGACY_*` 常量把改造前 loop.py 五处 `on_event` 的原文抄进测试当唯一事实源——
  这是「行为一字不变」唯一可机器校验的形式。
- `render_text` 返回 `Optional[str]`，`None` = 默认不打印。不用空串：
  `print("")` 会吐空行，「不打印」与「打印空行」是两回事。
- 3.9 运行期不认 `X | Y` 做类型别名（PEP 604 是 3.10），`AgentEvent` 必须写 `Union[...]`；
  `from __future__ import annotations` 只救注解，救不了别名（AGENTS.md 那条注记的实例）。

遗留：`ToolEnd.is_error` 只覆盖 loop 自造的错（参数非法/未知工具），
工具内部异常被 `Tool.run` 吸收成字符串无从分辨——要真区分得改 `Tool.run` 返回契约，
不在本轮范围，登记 TODO。

## 2026-08-10 · Task 2：PendingMessageQueue（core/queue.py）

目标：steering/followUp 两条队列的结构与 drain 语义。

改动：新建 `src/pai/core/queue.py`、`tests/test_queue.py`。

测试：红 `ModuleNotFoundError: No module named 'pai.core.queue'` → 绿
`127 passed, 3 deselected`（120 → 127，+7；计划估 +5，实际多写了两条边界测试）。

设计要点：两种 drain 模式不是凑 pi 的形状——steering 用 `all`（用户连打三句通常是
同一个转向意图，拆开逐轮注入反而错乱），followUp 用 `single`（每条各触发一轮，
中间还可能被中断）。`drain` 返回切片不返回内部列表引用（同 FakeClient 存引用那个坑）；
未知 mode 构造期就报错，不静默降级。

遗留：无。

## 2026-08-10 · Task 3：中断标志（core/interrupt.py）

目标：一个能被 Ctrl+C 置位、被工具与 loop 同时看见的标志。

改动：新建 `src/pai/core/interrupt.py`、`tests/test_interrupt.py`。

测试：红 `ImportError: cannot import name 'interrupt' from 'pai.core'` → 绿
`131 passed, 3 deselected`（+4）。

设计要点：进程级单例而非依赖注入——`@tool` 从函数签名生成 schema，给 bash 加个
flag 参数会把它发给模型看。这是「schema 与代码同源」的直接代价，取舍要进 decisions。
`current()` 永不返回 None（否则每个调用点都要判空）；包 `threading.Event` 而非裸 bool，
因为 TUI/流式阶段一定会有读输入的线程来置位。

遗留：全局状态的老问题——测试必须能干净复位，靠 `set_current(None)` 与
`tests/test_tools.py` 的 `_injected_flag()` contextmanager 兜住。

## 2026-08-10 · Task 4：bash 可中断到进程组（core/tools/shell.py）

目标：Ctrl+C 真能打断跑飞的命令（拍板问 3 选 B 的落地）。

改动：`shell.py` 从 `subprocess.run` 改为 `Popen(start_new_session=True)` + 轮询等待
（`POLL_SECONDS=0.1`）+ `os.killpg(SIGKILL)`；`tests/test_tools.py` 加 5 条。

测试：红 `4 failed, 10 passed in 91.17s`（91 秒是因为 `sleep 30` 全白等到 60s 超时，
正是要修的东西）→ 绿 `tests/test_tools.py` `14 passed in 6.60s`，全套
`136 passed, 3 deselected in 9.25s`（131 → 136，+5）。

注入反证（计划要求）：把 `os.killpg(...)` 换成 `proc.kill()`，
`test_bash_kills_whole_process_group_not_just_the_child` 确实变红，
但红的位置比预期更靠前——不是「孙进程还活着」这条断言，而是更前面的
`assert m`（没拿到 PID）：杀不掉整组时，后台 `sleep` 仍握着 stdout 管道，
`communicate` 收不到 EOF，连已产出的输出都一起丢了。同一个根因的两个症状，
反而更说明只杀子进程是错的。已还原实现。

顺带修正的一处不实话：超时提示原文是「若含后台进程，它可能仍在运行」——
现在整组被杀，这话不再成立，改为「命令与其整个进程组已被终止」。

遗留：`_Killed` 是内部控制流异常（把已组织好的话带出轮询循环），不是错误路径；
若将来 `_wait` 长出第三种终止原因要留意别把它当成异常处理。

## 2026-08-10 · Task 5：loop 接线（事件 + 双队列 + 中断）

目标：本轮唯一的破坏性改动——`on_event` 从收字符串改为收事件对象，
同时把 steering/followUp 两个注入点与中断接进 loop。

改动：`src/pai/core/loop.py`（大改）、`src/pai/modes/once.py`（默认处理器）、
`tests/test_loop.py`（2 条改写 + 11 条新增）、`tests/test_modes.py`（+2）。

测试：红 `12 failed, 23 passed`（2 条原断字符串的测试 + 10 条新增；
`TypeError: run_agent() got an unexpected keyword argument ...` 与事件断言失败）
→ 绿全套 `148 passed, 3 deselected`（136 → 148，+12），
补完下面那条回归测试后 `149 passed, 3 deselected`。

设计要点：
- 两条原本断字符串的压缩测试改成断事件类型与字段（`CompactionSkipped.reason`），
  比断中文文案更强：文案可以改，语义不能改。
- 中断不是「跳过剩下的工具」而是「剩下的各回一条『已取消』」——
  `test_interrupt_backfills_remaining_tool_calls` 钉死三个 `tool_call_id` 一一配对。
  这条要是漏了，下一轮请求就是 400（R#11 有真实复现路径）。
- steering 注入点必须在本轮所有工具结果回填之后：插在中间会劈开 tool_calls
  与它的结果，配对当场断裂。`test_steering_not_called_when_model_gives_final_answer`
  钉住语义边界（没有工具调用就不该问 steering）。
- `messages` 传入即续用，且 `compact` 的结果用 `messages[:]` 原地替换——
  调用方（REPL）持有的是同一个列表对象，换绑变量会让它拿到压缩前的旧历史。
- 工具执行分派抽成 `_run_tool` 返回 `(args, result, is_error)`，loop 主体只管发事件。

回归修正：`once.py` 的默认 `on_event=print` 改为 `print_event`——
不改的话用户屏幕上会是一串 `ToolEnd(...)` dataclass repr。测试注入了假 handler
所以第一轮全绿也照不出来，补 `test_once_default_event_handler_prints_rendered_text`
用 `capsys` 断言实际打印内容（含那个「一字不变」的基准串）。

遗留：`AgentStart` 事件在 `messages` 续用时仍带 `task` 字段，语义上是「本轮的任务」
而非「整个会话的任务」——REPL 多轮时字段名会有点歧义，暂不改，记档。

## 2026-08-10 · Task 6：AskUserQuestion（core/tools/ask.py）

目标：模型拿不准时问真人，而不是猜着往下做。

改动：新建 `src/pai/core/tools/ask.py`；`tools/__init__.py` 加 `INTERACTIVE_ONLY`
让默认工具集排除它；`tests/test_tools.py` +5。

测试：红 `5 failed, 14 passed`（`ImportError` + `KeyError: 'ask_user_question'`）
→ 绿全套 `154 passed, 3 deselected`（149 → 154，+5）。

设计要点：候选项只能是 JSON 数组字符串——`@tool` 只认标量参数，这是
「schema 与代码同源」的直接后果，所以 `Annotated` 描述里必须把格式讲给模型听
（`test_ask_schema_is_generated_from_signature` 断言描述里有 "JSON"）。
「注册了但不进默认集合」比「不注册」好：`once` 看不见它，交互模式显式点名要回来，
一个注册表两种视图。少于两个选项直接报错——只有一个选项的「提问」是通知，不该打断真人。

遗留：无。

## 2026-08-10 · Task 7：REPL 本体（modes/interactive.py）

目标：把前六个 task 组装成能用的交互模式。

改动：新建 `src/pai/modes/interactive.py`、`tests/test_interactive.py`（21 条）；
`cli.py` 分发（带 task 走 once，不带 task 进 REPL）；`loop.py` 加
`anchors` / `compaction_state` 两个可注入参数 + `_adopt` 写回。

测试：红 `ModuleNotFoundError: No module named 'pai.modes.interactive'`
→ 绿全套 `178 passed, 3 deselected`（154 → 178，+24）。

中途 TDD 出来的一个真 bug（不是计划里的 task）：`verify_compaction` 返回新对象，
loop 原来是 `state = verify_compaction(...)` 换绑局部变量——注入方（REPL 跨轮持有）
永远看不到失败计数，熔断器在 REPL 里等于每轮清零、连续失败永远数不到 3。
`test_compaction_state_updates_propagate_to_caller` 先红（`failures=0, awaiting_verify=True`）
后绿，修法是 `_adopt` 写回同一个对象。同理锚点簿也必须跨轮持有，否则每轮第一次请求
退回纯字符估算（已知 -33% 误差）——`test_anchor_book_can_be_shared_across_runs` 钉死。

冒烟撞出的第二个真问题：真跑 `printf ... | pai` 时，一次 401 让整个 REPL
带栈退出。once 崩了无所谓（本来就跑完即退），REPL 崩了等于把整段对话丢掉——
而这一层的全部价值就是「对话留着」。补 `test_model_error_does_not_kill_the_repl`
（断言两轮都报错、都没退出），实现里 catch `Exception` 后回提示符。

冒烟实录（`DEEPSEEK_API_KEY=dummy`，只跑不打模型的路径）：
`/help`、`!echo`、`\` 续行、`/status`（`📊 消息 3 条 | 估算 614 token / 窗口 1000000
| 锚点 0 个 | 压缩：正常（失败 0 次）`）、401 报错后继续、`/exit` 全部按预期。

设计要点：
- 干活期间 SIGINT 只置标志不抛异常——抛 KeyboardInterrupt 会把已完成的工作
  连同栈一起丢掉，而官方对中断的承诺恰恰是「保留迄今完成的工作」；空闲期间恢复默认
  处理器，于是 `input()` 照常抛 KeyboardInterrupt，走两级 Ctrl+C。
- `/clear` 用 `del messages[1:]` 保留 system，而不是整段清空让下一轮重建（等价但更难解释）。
- `!命令` 不自动接话：官方 v2.1.186 起会自动接话且给了开关，pai 默认关——
  每次 `!` 自动接话就是每次都花一次请求钱。
- steering 传 `None`：纯 REPL 的阻塞 `input()` 拿不到「干活时打字」，如实标注等 TUI 通电。

遗留：① `_install_sigint` 在非主线程装不上（退化为不可中断），已 try/ValueError 兜住；
② REPL 无 `/resume`，会话只活在进程内（spec 非目标已声明）。

## 2026-08-10 · Task 8：工具调用状态行（modes/statusline.py）

目标：把用户截图里的 CC 状态行做成 pai 能做的那部分（取舍表见档案）。

改动：新建 `src/pai/modes/statusline.py`（`display_width` / `render_tool_line` 纯函数
+ `StatusLinePrinter` 原地刷新）、`tests/test_statusline.py`（15 条）；
`interactive.py` 加 `make_event_handler`——真 tty 走状态行，非 tty 退回滚动行。

测试：红 `ModuleNotFoundError: No module named 'pai.modes.statusline'`
→ 绿全套 `193 passed, 3 deselected`（178 → 193，+15）。

自己给自己挖了又填的坑：第一版 `color=True` 时直接跳过截断（因为 ANSI 转义符会让
列宽算错）——而真 tty 上走的正是彩色路径，等于彩色输出根本没有宽度限制。
补 `test_colored_line_is_also_width_limited`（剥掉转义符后量可见宽度）先红后绿，
改法是把 `(可见文本, 颜色)` 分开存，按可见文本算宽度、装不下的整段丢弃，最后才上色。
两个经典坑在同一个函数里撞齐了：中文宽度与转义符不占列。

目视验证（三种终端宽度，形状与截图一致，列宽严格不超）：

```
w= 80 列宽= 79 | ◐ bash: echo "=== improve 目录概览 ===" && ls -la | ✓ bash ×14 | ✓ read_file ×3
w= 40 列宽= 40 | ◐ bash: echo "=== improve 目录概览 ==="…
w= 24 列宽= 24 | ◐ bash: echo "=== impro…
```

遗留：`_preview` 取参数字典的第一个值当预览——`bash` 只有 command 所以正好，
多参数工具（`edit_file`）的预览会只显示 path，够用但不精确，记 TODO。

## 2026-08-10 · 补漏：历史文件写了但没读回 readline（05 交付后发现）

怎么发现的：用户问「本机现在能测什么」，我准备写「↑/↓ 翻历史」时先去核实，
`grep readline src/pai/modes/interactive.py` → 一行都没有。

漏在哪：spec 写的是「`readline` 提供 ↑/↓ 与 `Ctrl+R`；历史按 cwd 分文件存」，
实现只做了后半句（写文件、按 cwd 分、连续重复只记一条），从没把文件读回 readline，
所以 ↑ 是死的。Task 7 的两条历史测试只断言了「文件内容对不对」，
全绿也照不出来——测试覆盖了产物，没覆盖用途。

改动：`interactive.py` 加 `_is_real_terminal_input`（谓词，可测）与
`_read_history_into_readline`；`tests/test_interactive.py` +3。
`.active` 走 `!小修` 显式放行通道（理由留档：`!小修:补 05 漏项——历史文件写了但没读回 readline`）。

测试：红 2 条（`AttributeError: module 'pai.modes.interactive' has no attribute
'_read_history_into_readline'`）→ 绿 **`239 passed, 3 deselected`（235 → 239，+4）。

中途踩的一个坑：第一版测试写
`monkeypatch.setattr(interactive.sys, "stdin", SimpleNamespace(isatty=...))`——
`interactive.sys` 就是真的 `sys` 模块对象，这一改把 `input()` 一起弄坏了
（`AttributeError: 'SimpleNamespace' object has no attribute 'readline'`）。
改成把条件抽成 `_is_real_terminal_input(reader)` 谓词单独测，不再动进程级 stdin。

诚实边界：macOS 系统 Python 的 readline 是 libedit 后端，历史文件格式与 GNU readline
略有差异；读失败按「没有历史」处理。这条只能在真终端上验证，我在这个环境里验不了——
需要用户本机确认 ↑ 真的能翻出上一轮的输入。

## 2026-08-10 · 补漏二：Ctrl+C 打断 `!命令` 会掀掉整个 REPL

怎么发现的：给用户写手工测试清单时，我正要写「用 `!sleep 300` 省钱测中断」，
顺手核了一下那条路径有没有被中断保护覆盖——`grep` 出来 `_install_sigint` 只在
`_run_turn` 里装（249 行），而 `!` 分支在 233 行在它外面。

症状：`!` 分支跑 bash 时没有 SIGINT 处理器，Ctrl+C 直接抛 `KeyboardInterrupt`，
而 `except KeyboardInterrupt` 只包了 `_read_line`——异常一路逃出 `run_interactive`。
写成测试时它的破坏力一目了然：KeyboardInterrupt 把整个 pytest 进程都中止了
（`31 deselected` 之后直接崩），这就是它在真终端里的样子。

改动：抽出 `_interruptible(flag)` 上下文管理器（clear 标志 → 装处理器 → finally 还原），
模型轮次与 `!` 分支共用；`!` 分支另加一层 `except KeyboardInterrupt` 兜底
（信号可能落在装处理器前后的缝隙里）。顺带把 `_run_turn` 里那段 try/except/finally
拆成 `_guarded_run(out, ...)`，读起来不再是三层嵌套。

测试：红——`KeyboardInterrupt` 中止 pytest 全程 → 绿 `247 passed, 3 deselected`
（245 → 247，+2）。两条新测试：中断后 REPL 能继续正常对话；
`!` 期间 `signal.getsignal(SIGINT)` 不是 `default_int_handler`
（还是默认处理器就等于没修）。

同一类第三次了：401 炸会话（Task 7）、这次的 Ctrl+C 炸会话，根因都是
「REPL 这一层的价值是对话留着，任何逃逸的异常都是在毁掉这个价值」。
前两次都是「补一处 catch」，这次改成了共用作用域——但仍然是发现一处补一处。
真正的做法应该是在 REPL 主循环上兜一层「任何异常都回提示符」，
把「哪条路径漏了」变成不需要逐条排查的问题。已登记 TODO。

诚实边界：这条修的是「不崩」。至于 Ctrl+C 之后 bash 的进程组是否真被杀干净，
测试里是用假的 `_run_shell` 验的调用契约，真信号 + 真 sleep 的组合仍然只能在真终端验
（用户手工清单第 2 条）。

## 2026-08-10 · 补漏三：pai 退出不收割 bash 起的后台进程组

怎么发现的：用户问「关掉 pai 是不是就不会再调 API 了」，我答「是」并顺带如实交代了
一个副作用——`!sleep 300 &` 起的后台进程不会跟着死。用户当场反问：
「照理来说所有命令都基于 pai 这个会话进程，关闭之后应该都停掉」。他是对的，
而且官方也是这么做的——`interactive-mode` 那篇笔记里就记着「当 Claude Code 退出时，
后台任务会自动清理」，我写笔记时抄下了这句，做的时候没联想到。

根因：`start_new_session=True` 是能整组 `killpg` 的前提（补漏一那条），
代价就是子进程脱离 pai 的进程组，pai 死了它不跟着死。解法不是放弃独立进程组
（那样又杀不干净了），而是登记 + 退出时收割。

改动：`shell.py` 加模块级 `_SPAWNED_GROUPS` 登记表与 `reap_spawned()`；
`cli.py` 在 `try/finally` 里调用它——放 cli 出口而不是各 mode 里，
因为两种模式共用一条出路，异常路径也覆盖得到。`tests/test_tools.py` +3、
`tests/test_interactive.py` +1。

测试：红 `AttributeError: module 'pai.core.tools.shell' has no attribute 'reap_spawned'`
→ 绿全套 `251 passed, 3 deselected`（247 → 251，+4）。

测试前提写错了一次（值得记）：初版用 `sleep 30 & echo PID=$!`，红在
「命令返回时后台进程已经死了」——因为后台进程握着 stdout 管道，`communicate`
收不到 EOF，`bash()` 一直等到它自然结束（30 秒）才返回。要复现「命令已返回、
后台进程仍存活」，后台那条必须重定向掉输出（`>/dev/null 2>&1 &`）。
这和补漏一里「杀不净时连输出都丢」是同一条管道语义的两面。

端到端实测（真跑，非测试）：`printf '!sleep 300 >/dev/null 2>&1 & echo PID=$!\n/exit\n' | pai`
→ 拿到 PID=56407 → pai 退出后 `kill -0` 查不到 → ✅ 已随 pai 一起清掉。

诚实边界（两条，都写进了代码注释）：
① `kill -9 pai` 时这段代码没机会跑——任何进程内方案都救不了，这是原理性的；
② 登记的是 pgid，理论上存在「组早已结束、pgid 被系统重用」后误杀无关进程的窗口。
真实风险低（macOS pid 空间大、回绕慢）但不为零，已记 TODO 而不是假装没有。

## 2026-08-10 · 补漏四：write/edit 先截断后写，进程中途死掉会丢内容

怎么发现的：用户追问「read / write / edit 这些工具应该也会停止吧」。
答案本身很简单（进程内同步调用，进程死了就没了），但顺着这个问题看实现，
撞见一个比「会不会继续跑」严重得多的东西。

根因：`open(path, "w")` 的语义是先截断、后写入。进程若死在这两步之间
（`kill -9` / OOM / 断电），文件就是空的或半截的。`edit_file` 尤其险——
它把原内容读进内存后同样要截断重写，那一瞬间原文只存在于内存里，进程一死彻底没了。
窗口很短（小文件微秒级），但这正是「关掉 pai」这个场景要问的。

改动：`fs.py` 加 `_atomic_write`（同目录 `mkstemp` → 写 → `os.replace`），
`write_file` / `edit_file` 都改走它；`tests/test_tools.py` +4。

三个实现细节（都写进了注释）：
- 临时文件必须与目标同目录——跨文件系统的 `rename` 不是原子的，会退化成拷贝；
- 改名前把原文件的权限位复制到临时文件，否则可执行位会丢（`chmod 755` 的脚本被
  改一次就不能执行了）；
- 失败路径 `unlink` 临时文件——半截的 `.pai-tmp-xxx` 比没有更让人困惑。

测试：红 3 条 → 绿全套 `255 passed, 3 deselected`（251 → 255，+4）。

测试写错了一层（值得记）：初版直接调 `fs.write_file(...)` 并断言返回值含「错误」，
红在 `OSError` 直接抛出来。「工具错误不 throw」的契约在 `Tool.run` 边界上（D#1），
不在函数内部——裸调当然会抛，那测的不是系统的真实行为。改成走
`get_tools()["write_file"].run(...)` 后即绿。这条错误我今天犯过同款：
补漏三里也是先写了个「探针式」的假断言。

端到端实测：`chmod 755` 的文件 edit 一次 → 内容替换正确、权限仍是 0o755、
目录里只有目标文件没有临时文件残留。

这条修的边界：原子写保证「不会读到半截文件」，不保证「改动一定成功」——
`kill -9` 落在 replace 之前，结果就是「旧的完好、这次编辑没发生」。
这是正确的取舍：对 agent 改用户源码这件事，丢一次编辑 远好过 丢一个文件。

## 2026-08-10 · 真终端手工验收：三项全过（用户执行）

四个补漏里有三条我在这个环境里验不了，标注为「只能真终端验」。用户实测反馈全部正常：

| 项 | 验的是什么 | 结果 |
|---|---|---|
| ↑ 翻历史 / Ctrl+R | 补漏一：历史文件读回 readline（macOS libedit 后端我无法验证） | ✅ 正常 |
| `!sleep 300` + Ctrl+C | 补漏二（不炸 REPL）+ 阶段 2 task 4（整组 killpg 真杀干净） | ✅ 正常 |
| 工具状态行 | task 8：真 tty 才启用的原地刷新、中文列宽 | ✅ 正常 |

至此四个补漏（readline / Ctrl+C 炸 REPL / 后台进程不收割 / write-edit 非原子）
全部既有测试覆盖、又有真人实测。`255 passed, 3 deselected`。

## 2026-08-10 · 补漏五（最严重）：测试把数据写进了用户真实的 ~/.pai

怎么发现的：用户自己去翻 `~/.pai/history/e4887ef95b86e3ee`，问「这里面只有最后
可能是我自己测试时加的，别的这些是什么」。这类污染不会让任何测试变红——
靠的是用户起了疑心。

规模：687 行里只有 3 行是用户自己的，其余是测试数据累积了约 40 轮
（每跑一次 `./test.sh` 追加一批）。`~/.pai/history/` 下另有几十个垃圾文件——
pytest 每个 `monkeypatch.chdir(tmp_path)` 都是一个新 cwd，于是一个哈希一个文件。
`~/.pai/projects/<hash>/memory/` 也有我冒烟测试写进去的 `MEMORY.md` 与 `构建.md`。

根因：`tests/test_interactive.py` 里 20 处 `_run(...)` 没传 `history_path`，
于是 `history_path_for()` 落到真实 `$HOME`。这不是「某个测试写错了」——
20 个调用点意味着第 21 个还会忘。

修法（结构上做不到，而不是靠记性）：在 `tests/conftest.py` 里加 autouse fixture
把每个测试的 `$HOME` 指向临时目录。另加一条防护的防护
（`test_tests_can_never_touch_the_real_home`）——否则哪天 conftest 被改坏了没人知道。

这一路又炸出三个连锁问题，每个都值得记：

1. 假 home 不能建在 `tmp_path` 里——好几个测试在断言「`tmp_path` 下只有我写的那个
   文件」，塞个 `fake-home` 进去当场误伤 3 条。改用 `tmp_path_factory` 另开目录。
2. `history_path_for(*, base=HISTORY_BASE)` 的默认参数在函数定义时就求值了，
   改模块常量追不回来。防护测试第一次跑就抓到了它——这正是「导入期 vs 运行期」
   的同款陷阱（`HISTORY_BASE` 本身也是导入期常量，所以两处都要打）。
3. 换 `$HOME` 会让子进程连第三方包都 import 不到——用户 site 目录由 `$HOME` 推导，
   于是 viz 的 `python -m pai.viz.collect` 既找不到 `pai` 也找不到 `dotenv`。
   修在测试环境（把 `src` 与真实的 user-site 一起给 `PYTHONPATH`），不动生产代码。

测试：`256 passed, 3 deselected`（255 → 256，+1 防护测试；conftest 不计）。

数据清理：全量备份到 `~/.pai.bak-213818`，保留用户真实的 3 行输入，
删掉其余历史文件与冒烟测试写出的 `projects/`。

修的时候我又犯了一个更糟的错（合并 main 后才发现）：我以为 `tests/conftest.py`
不存在，用 Write 整个覆盖了它——而原文件里有一个防止花钱的守卫
（`pytest_collection_modifyitems`：llm 测试必须「有 key 且 `PAI_RUN_LLM_TESTS=1`」
才跑，D#21-23，注释里写着「外部评审时评审者本人就中招了」）。
`./test.sh` 自带 `-m "not llm"` 所以一直是绿的，掩盖了裸跑 `pytest` 会直接花钱这个回归。
是合并后看 diff 里「`conftest.py | 64 +--` 是修改不是新建」才发现的。已恢复并与隔离 fixture 合并，
实测裸跑 `pytest` → `3 skipped`，不花钱。
教训：写一个「我以为不存在」的文件之前必须先确认它真的不存在——
尤其是 conftest 这种「存在与否会改变整套测试行为」的文件。

顺带修了我自己新加的守卫的一处误报：`test_status_reports_the_current_test_count`
在裸跑 `pytest` 时会红——因为那时 llm 测试是 skipped（算进 collected=260），
而 `./test.sh` 带 marker 时是 deselected（不算，=257）。收紧成只在标准入口口径下对账。

教训（够格进复盘）：今天四个补漏都是「功能没做对」，这一个是「测试本身伤害了用户」——
性质更严重。而且它绕开了所有防线：测试全绿、评审看代码看不出来、
唯一的发现途径是用户去翻自己的文件。凡是会写 `$HOME` 的代码，测试必须在结构上隔离，
这条应该在写第一个写盘功能时就立，而不是等被抓。
