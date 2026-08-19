# 17 viz-flow 开发日志

## T1 `core/trace.py`：EventTrace + compose（2026-08-13）

目标：把 loop 发的结构化事件落成观测流 JSONL，供 viz 回放与实时点亮。

动的文件：新增 `src/pai/core/trace.py`、`tests/test_trace.py`。

红 → 绿：红 `ModuleNotFoundError: No module named 'pai.core.trace'`（collection error）
→ 绿 `8 passed`。

设计要点（写下来是因为代码本身说不出）：
- 事件文件名由 session 文件名推导（`X.jsonl` → `X.events.jsonl`），两个文件同名配对；
- `MessageDelta` 不落盘——增量正文最终会作为完整消息进 session 文件，
  在观测流里再落一份等于写第二份正文（waku 对 `text` 增量同款处理）；
- 写失败吞掉 OSError 且只告警一次：观测流挂了不能连累正事，但每步刷一行会淹掉真输出。
  测试用「父目录是个文件」制造确定性的 OSError，不用 chmod（root 下 chmod 不生效，会假绿）；
- `compose` 不吞异常：渲染器炸了就该炸，吞掉会让「界面不动」变成无声的谜。
  与 EventTrace 自己吞写失败不矛盾——那是观测流对自己的约束，不是通用扇出的职责。

教训（自己撞的）：spec 里写「其余 11 种全落」，实际数一遍是 13 种。
`test_every_event_type_is_covered_by_samples` 用反射比对 events.py 的 dataclass 集合，
把这个数字从「作者数的」变成「机器数的」——T2 加事件时它立刻红了（见下），守卫兑现。

## T2 `RecallInjected`：成功召回也发事件（2026-08-13）

目标：此前只有失败发事件（`RecallFailed`），成功召回是哑的——
观测流里说得出「召回过」，说不出「召回了什么」。

动的文件：`src/pai/core/events.py`（新 dataclass + union + render_text）、
`src/pai/core/recall.py`（`make_recall` 加 `on_selected` 回调）、
`tests/test_recall.py` +3、`tests/test_events.py` +2、`tests/test_trace.py`（样本清单 +1）。

红 → 绿：红 `TypeError: make_recall() got an unexpected keyword argument 'on_selected'`
（3 failed）→ 绿 `49 passed`（trace + recall + events 三个文件合跑）。

中途 T1 的守卫按设计报红：加完 `RecallInjected` 后
`test_every_event_type_is_covered_by_samples` 立刻失败（`declared - covered` 多出新类型），
补进样本清单才绿。这正是那条测试存在的理由——新增事件不许静默缺席观测流。

设计要点：
- 回调收的是文件名元组而不是事件对象——recall 与 memory/permissions 一样不认识 events，
  装配层负责翻译（core 之间不互相认对方的词汇表，沿用 `RecallFailure → RecallFailed` 的既有形状）；
- 明确不选（`selected: []`）不发事件：那是正常结果，不是「注入了 0 篇」，
  发空事件只会在页面上刷噪音；失败路径归 `on_failure`，两个回调不许同时响（有测试钉住）。

## T3 装配：once ×1 + interactive ×1（2026-08-13）

目标：把 EventTrace 接进两个模式，让真跑就产生观测流。

动的文件：`src/pai/modes/once.py`、`src/pai/modes/interactive.py`（各 +1 处 compose、
+1 处 `on_selected`、import）、新增 `tests/test_trace_wiring.py`。

红 → 绿：红「没有事件文件」`assert 0 == 1`（2 failed）→ 绿 `5 passed`；
全套 `1016 passed, 3 deselected`（约 71s）。

plan 认账的最大返工风险没有兑现，且方向相反：plan 写「interactive 三处装配点的
session 生命周期可能不同，最可能返工」。动工前核对实况——`session` 在 `run_interactive`
里只建一次（`SessionLog()` 一处），经 `common` 字典传给 TUI 与纯 REPL 两条路，
下游三处 `run_agent` 共用同一个 `on_event`；`/clear` 只截断 `messages` 不换会话。
于是装配点是 2 处不是 4 处，且不存在「换了会话还写旧文件」的问题。
有测试钉住这个事实（`test_interactive_writes_one_event_file_for_the_whole_repl`：
两轮对话 + 中间 `/clear`，断言恰好一个事件文件、两个 `AgentStart`）。

利用 Python 闭包的一处刻意安排：`compose` 的重绑定放在 `memory_tool.set_notifier` 与
`make_recall` 之后也照样生效——那些 lambda 按名字查 `on_event`，查的是重绑之后的值。
所以 `MemoryWritten` / `RecallFailed` / `RecallInjected` 全都进事件流，不需要调整语句顺序。
（反过来说，`compose(on_event, ...)` 捕获的是旧值，不会自我递归。）

顺带：`--no-session` 时不落观测流（「这次别写盘」也包括观测流），有测试。

已知缺陷 / 待办：
- 事件文件无上限增长、无清理策略（长会话会一直长）——本轮不做，交付时登记 TODO；
- scheduler 并发批、queue 进出仍无事件源，故页面上看不到并发分批与队列——本轮范围外。

下一步：T3.5（用户提问引出的插入任务），然后 T4。

## T3.5 会话内的「分段」必须留痕（2026-08-13）

起因：用户问「如何区分新的 pai 对话呢，有这个吗」。查证后分三种情况：
① 新起进程 → 新会话文件（时间戳 + 短 id + 每条记录带 `sessionId`），分得出；
② 自动压缩 → loop 发 `Compacted`，分得出；
③ REPL 里 `/clear` → 两个流里都不留痕，分不出。

查证中发现回答本身也错了一半：`_manual_compact` 只 `out()` 打印，不发事件——
所以 ② 只对自动压缩成立，手动 `/compact` 和 `/clear` 一样隐形。两个一起补。

动的文件：`core/events.py`（新增 `ConversationCleared`）、
`modes/interactive.py`（`/clear` 发事件、`_manual_compact` 发 `Compacted`、
`_handle_command` 与 `_dispatch_command` 接 `on_event`、`_run_tui` 接 `trace`）、
`tests/test_trace_wiring.py` +4、`tests/test_trace.py`（样本 +1）。

红 → 绿：红「两条都缺」（2 failed）→ 修 → 中途 e2e 抓到回归（见下）→ 全套
`1020 passed, 3 deselected`（约 72s）。

为什么不用「`/clear` 时换新会话文件」：那会改动 08 已交付的落盘语义，
还会影响将来的 `--resume`（续哪个文件？），且 T3 刚钉的测试要推翻。
发一个事件、让 viz 画分隔线，代价小得多。

### 撞出来的两个真 bug（都是我自己 T3 埋的 / 早就在的）

bug 1：T3 的接线在 TUI 模式下根本不生效。
`_run_tui` 不接收 `on_event`——它自建一个走 `app.on_event` 的本地版本，
于是 `run_interactive` 里 compose 出来的（渲染器 + 落盘）只有纯 REPL 那条路在用。
后果：真 tty 下跑 pai（日常用法）完全不落观测流，而 T3 的测试全都注入了 reader，
走的是 REPL 路径，照不到。修法：把 `EventTrace` 实例单独递给 `_run_tui`
（`trace=` 参数），TUI 的本地 `on_event` 里调它。
不能把外层 compose 直接递进去——外层默认渲染器往 stdout 打字，会弄花 dock。

bug 2（自己刚埋的）：`kw["on_event"]` 取了个没人传的键，KeyError 把整个 TUI 打崩。
`_dispatch_command(..., **kw)` 的两处调用点都没传 `on_event`，
真跑时屏幕全空。只有 pty e2e 照得到（`test_multiline_content_does_not_stair_step`
等 8s 没等到 `/permissions` 才失败）——feature 15 那套假 provider + 真 pty 值回票价。
修法：`on_event` 改成 `_dispatch_command` 的显式必填参数（漏传当场 TypeError），
不给默认值——默认 None 的话漏传就是「静默不落盘」，正是本 task 在修的那类 bug。
另补一条 0.1s 的快测直接调 `_dispatch_command`，让同类漏传不必等 e2e。

### 顺带发现、本轮不修（已登记 TODO）

TUI 模式下 `memory_tool.set_notifier` 与 recall 的 `on_failure` 用的是外层 `on_event`，
即默认渲染器 → 直接往 stdout 打字，可能弄花 dock（`MemoryWritten` / `RecallFailed` 两类）。
这是 feature 12/13 就存在的老问题，不是本轮引入；修它要动 TUI 的事件路由，
超出 17 的范围。

## T4 `viz/flow.py`：turn 分组与配对（2026-08-13）

目标：把审计流 + 观测流两个 JSONL 合并成「回合时间线」。唯一一处分组逻辑——
前端不重复实现（两份必然漂移），所以这里是时间线正确性的全部地基。

动的文件：新增 `src/pai/viz/flow.py`、`tests/test_viz_flow.py`、
`tests/fixtures/real_session.jsonl`（新夹具）、`tests/fixtures/README.md`。

红 → 绿：红 `ModuleNotFoundError: No module named 'pai.viz.flow'` → 绿 `12 passed`
→ 真实数据跑出两个问题（见下）→ 绿 `14 passed`；全套 `1034 passed, 3 deselected`。

新夹具 `real_session.jsonl`（真跑 2026-08-11，抄进版本库，出处写进 fixtures/README）。
它是唯一一份保留 `ts` 的夹具，与「抄进来要剥 ts」的规约不冲突：那条规约的理由是
「时间是噪音」，而这里 `ts` 正是被测对象（排序、两流归并、耗时全靠它）。
三处编不出来的真实形状：一条 assistant 里两个并发 `read_file`（feature 11 的分批跑出来的）、
真实 `call_00_eYpVDzjffTKaD6HqyCUX7545` id 格式、`usage` 里
`prompt_cache_hit_tokens` 与 `prompt_tokens_details.cached_tokens` 两套缓存字段并存。

### 拿 8 个真实会话跑一遍，跑出两个测试没覆盖的问题

问题 1（假阳性，已修）：`!命令` 的记录被全判成「未完成」。
`_run_shell` 往 session 落的是 `{"role": "user", "content": "我执行了命令 `…`，输出：…"}`
——形状上与真人提问一模一样，但它不经模型，永远等不到 assistant。
原判据「没有收尾的 assistant 就算未完成」把 8 个会话里的 3 个判成 ⚠，
「未完成」这个信号当场从证据退化成噪音。
改判据：真的开了工（有 llm 步骤）却没收尾才算未完成。
刻意不靠匹配「我执行了命令」那句话——用户自己就能原样打出这几个字。
修完再跑：3 条 shell 记录归位，唯一剩下的 ⚠ 是真的被中断的那条
（20260811-134308，工具结果是 `(已取消，用户中断)`）。

问题 2（判断分歧，改了测试）：`starts_conversation` 首轮算不算真。
我先写的断言是「首轮为 False」，实现给的是 True。想清楚之后实现是对的：
第一轮确实开启了第一段对话，语义一致；前端画分隔线的条件是
`starts_conversation and 不是第一张卡`，由渲染层跳过 index 0，
比在数据里给首轮开特例干净。测试改成三轮（`[True, False, True]`）把两个方向都钉住，
顺带断言清空标记不会同时留在上一轮的步骤里（否则分隔线画重）。

设计要点：
- 判别字段在 `_kind_of` 一处收口：审计流混用 `role`（消息）与 `type`（其余），
  是需求池 2026-08-10 记的形状债；不收口的话每个消费者都要写一遍
  `r.get('type', r.get('role'))`；
- `usage` 先落、`assistant` 后落，所以一个 llm 步骤由两条记录合成
  （`pending_llm` 等着）。没有配套 usage 时（中断/provider 没回）仍造一个步骤——
  消息不能因为缺 usage 就从页面上消失；
- `tool_calls[].arguments` 是字符串，解析失败保留 `raw`：真实轨迹里出现过畸形 JSON，
  吞掉会让页面显示空参数表却说不出为什么；
- 工具结果没回来 → 不造 tool 步骤，只把该调用标 `pending`（凭空造一行等于伪造证据）；
- 坏行跳过并计数（`skipped`），绝不因半行拒绝整个文件。

下一步：T5 server 新端点（`/api/sessions`、`/api/flow`、`/api/events` 游标、`/api/reveal`）。

## T5 server 观测端点（2026-08-13）

目标：四个新端点——会话列表、时间线全量、增量游标、跳编辑器。

动的文件：`src/pai/viz/server.py`（+4 路由 + 6 个纯函数）、`tests/test_viz_server.py` +14。

红 → 绿：红「端点与 `sessions_dir`/`_editor_cmd` 都不存在」（3 failed + 9 errors）
→ 绿 `18 passed` → 真跑发现一处缺口（见下）→ `20 passed`；
全套 `1048 passed, 3 deselected`（约 79s）。

`/api/structure` 的子进程模式原样不动——那是为 `@tool` 的 import 缓存设计的（01 的核心体验）。
新端点全是读 JSONL，没有缓存问题，进程内直读。

### 真跑一次 server 打真实数据，发现一个测试没覆盖的缺口

起 server 打 `~/.pai` 里的 8 个真实会话，全部正常；越界两条（`?session=../../../etc/passwd`、
`/api/reveal?path=../../../etc/passwd`）都被挡住。然后在旁边真跑了一回合 pai：
游标从 `7:0` 跳到 `5:7`，返回 0 条记录。

原因：新起一次 pai 会换一个会话文件，而页面盯的是 `latest`。旧游标对新文件不合法
（`a=7 > rows=5`），走「重新对齐、不回历史」分支——语义是对的，但页面会显示
「什么都没发生」，而实际上一个全新回合正在产出事件。

修法：响应带回 `session`（解析到的会话名），前端一比对就知道该重载时间线。
`/api/flow` 同样带（下拉框要显示解析结果）。两条测试钉住。
这个缺口纯测试照不出来——测试里会话文件是固定的，只有真跑才会换文件。

### 安全边界（页面上唯一会执行本机命令的地方）

`/api/reveal` 三道闸门，缺一不可，各有测试：
1. 路径 `resolve()` 后必须在仓库根内（`REPO_ROOT not in target.parents` 即拒）；
2. 只认 PATH 上的 `cursor`/`code`（或 `$PAI_EDITOR`），argv 列表直接 exec 不过 shell；
3. 找不到编辑器不是错误——把完整路径给用户，他自己开（不做 Finder fallback）。

`?session=` 同样是路径注入面：只认「会话目录下的一个文件名」，含分隔符直接拒
（`Path(name).name != name`），再 `resolve()` 后校验父目录。三种越界写法都有测试。

游标容错：`""`/`abc`/`1`/`9:9`/`-3:-3`/`1:2:3` 六种畸形值逐个测过，
一律退化成「从现在开始」而不是 500——游标来自客户端，任何形状都不能让 server 崩。

下一步：T6 `collect.py` 代码位置自省 + 顺手修 `_stage_key` 的反引号 bug。

## T6 代码位置自省 + 顺手修 `_stage_key`（2026-08-13）

目标：每个工具/节点/事件类型都标出「发生在哪个代码文件」——把观测页面同时当 harness 教材。

动的文件：`src/pai/viz/collect.py`（`_source_of` 自省 + `NODE_SRC`/`EVENT_SRC` 两份映射
+ `_stage_key` 修复）、`tests/test_viz_collect.py` +4。

红 → 绿：红 4 条（自省字段、节点 src、EVENT_SRC、干净 key）→ 绿 `12 passed`
→ 全套里又红一条（见下）→ 全套 `1052 passed, 3 deselected`。

plan 认账的假设当场验证：plan 写「`inspect.getsourcefile` 对装饰器包裹的函数可能拿到 wrapper，
不成立就取 `__wrapped__`」。实测 `Tool.func` 存的就是原函数（`hasattr(fn, "__wrapped__")` 为 False），
`@tool` 没有包一层 wrapper，直接取即可。

自省结果（真跑 `python -m pai.viz.collect`）：

    bash        src/pai/core/tools/shell.py:87
    edit_file   src/pai/core/tools/fs.py:72
    read_file   src/pai/core/tools/fs.py:50
    remember    src/pai/core/tools/memory_tool.py:114
    write_file  src/pai/core/tools/fs.py:62

两份手写映射的边界：`NODE_SRC` / `EVENT_SRC` 是设计知识，程序推不出来
（与 01 的 pipeline 手写数据同一取舍）。防漂移交给测试：`EVENT_SRC` 的键集合必须
恰好等于 events.py 的事件类名集合（减 `MessageDelta`），且每个文件必须存在。
`EVENT_SRC` 刻意不指 events.py——那里只有 dataclass 定义，14 个事件全指同一个文件
等于什么都没说；指的是机制住在哪（`PermissionDecided → core/gate.py`、
`Compacted → core/compaction.py`）。未开工的环节（skills / mcp_client）指向 `roadmap.md`——
「还没写」也是一种诚实的位置，点进去看得到设计。

### 顺手修：`_stage_key` 的反引号 bug（2026-08-12 分析 waku 时发现）

`strip("`")` 只剥两端，碰不到中间的。STATUS.md 里 `` `core/tools/` 的 matcher ``
解析出 `key = "` 的 matcher"`（带反引号和空格）直接显示在页面上。
修法：先剥掉全部反引号再拆路径；散文式单元格取最后一个标识符样的词当 key
（`matcher`），整句留给 label。新增反向断言 `test_stage_keys_are_clean_identifiers`
（既有一致性测试只查 pipeline→stages 方向，照不到这个）。TODO 对应条目已关闭。

### 全套里多红一条：`@tool` 注册表是全局的

`test_every_tool_reports_where_its_code_lives` 单跑绿、全跑红：
`tests/test_tools.py` 注册的探针工具 `_cap_bool_probe` 漏进了 `get_tools()`，
它的 src 是 `tests/test_tools.py:616`，不以 `src/pai/` 开头。

实现没错，断言错了——自省把测试里的工具也正确解析成了仓库相对路径。
契约本来就是「指向真实存在的文件、带行号」，`src/pai/` 前缀是我附加的臆断。
改成：全部工具断言「文件真实存在 + 有行号」，`src/pai/` 前缀只对四个内置工具断言。
注册表全局泄漏是既有的测试卫生问题，已登记 TODO，不在 17 范围内根治。

下一步：T7 前端（时间线 + 结构图通电 + 会话下拉 + 代码位置角标）。

## T7 前端：回合时间线 + 结构图通电 + 代码位置（2026-08-13）

目标：把前六个 task 的数据变成页面上看得见的流转。

动的文件：`src/pai/viz/index.html`（+CSS 段、+时间线 section、+约 200 行 JS）、
`src/pai/viz/flow.py`（两处修，见下）、`tests/test_viz_server.py` +5 结构断言、
`tests/test_viz_flow.py` +4、`evidence/20260813-页面验收/`。

红 → 绿：结构断言 5 条一次过；两条 bug 各自先红后绿；
全套 `1060 passed, 3 deselected`（约 80s）。

### 端到端真验收（起 server + 真跑 pai + 浏览器看）

`evidence/20260813-页面验收/` 两张截图：
1. `01-时间线展开.jpg`——回合卡片展开后每步齐全（LLM 步的模型/in-out/缓存率、
   工具的参数与结果、harness 事件行、代码位置角标）；
2. `02-实时切会话与字段修复.jpg`——页面开着不动，终端另跑一回合，页面 2s 内
   自己切到新会话并长出新卡片（T5 那个「换会话要说出来」的修复在真实场景生效）。

浏览器控制台零错误（唯一一条来自用户的沉浸式翻译插件，与 pai 无关）。

### 浏览器里看出来的两个 bug（纯后端测试都照不到）

bug 1：观测流与审计流重影。首次端到端跑出来 10 步，其中 3 步是重影——
`AssistantMessage` 与 assistant 记录逐字相同，`ToolStart`/`ToolEnd` 与 tool 记录说同一件事。
但后两者带着审计流没有的东西：精确耗时（start→end）与 `is_error`。
所以不是丢弃而是合并进 tool 步骤；没有观测流的老会话退回近似值
（「模型发出调用 → 结果落盘」）并标 `ms_approx`，页面显示成 `~1500ms`——
并发批里这个近似是偏大的（第二个工具的区间含第一个），标出来才不骗人。
10 步 → 6 步，且工具耗时从近似变精确。

bug 2：字段撞名。页面上显示 `PermissionDecided bash → event`，应是 `→ allow`。
`PermissionDecided` 自己有一个 `kind` 字段（allow/deny），而步骤判别字段也叫 `kind`
（llm/tool/event），平铺时后者覆盖前者。修法不是给这一个事件开特例（下一个撞名字段
又会中招），而是把事件载荷整体放进 `data`——结构上不可能再撞。

### 一处操作上的坑（值得记住）

改完 `flow.py` 后页面没变化：常驻 server 不会重新 import Python 模块。
新端点是进程内直读，所以改后端要重启；而 `/api/structure` 因为走子进程反倒不用重启——
01 当年为 `@tool` 缓存做的那个设计，顺带让结构图免疫了这个坑。waku 的
`static/README.md` 也专门写了这条（"A running server does not pick up Python changes"）。

### 前端的三条结构性决定（plan T7 定的，实施后确认都对）

1. turn 分组只在 Python 一处：有新事件就整体重拉 `/api/flow` 重渲，不在 JS 里再实现一遍；
2. 灯与卡解耦：`/api/events` 只驱动点亮队列，时间线只认 `/api/flow`，动画丢帧不影响正确性；
3. `innerHTML` 只搭骨架、数据一律 `esc()`：工具结果是任意字符串，含 `<script>` 是正常输入。

另外两处沿用既有教训：点亮走 CSS 类不走 SVG 属性（01 的 D#29-31）、
展开态用 Set 记住（否则 2s 一刷新卡片自己合上）。

没有 JS 测试运行器（waku 同境况），机器可判的钉在 `test_viz_server.py`：
页面锚点存在、前端调的每个 `/api/` 都真有路由、`STAGE` 引用的节点 id 都在
`_PIPELINE_NODES` 里、`STAGE` 的事件键都是真事件类型。诚实边界：JS 的行为逻辑
（队列播放顺序、展开态保持）没有自动化测试兜着，靠人眼 + 截图归档。

下一步：T8 收尾（STATUS/TODO/档案 README/复盘）。
