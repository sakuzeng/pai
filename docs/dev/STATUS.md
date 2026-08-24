# 当前状态快照

最后更新：2026-08-24（feature 31 交付——装配收敛：once/interactive 的装配
序列合一进 `modes/assembly.py`，MCP 关闭 atexit→单出口 finally（29 遗留 7）；
同日独立功能测试 28 冒烟场景全过、三条低级发现 !小修 清零——mcp timeout
静默回默认加 warn、纯中文工具名挂 hash 防撞名、07 档案状态行补翻。档案
[features/31](features/31-20260824-assembly-convergence/README.md)。
随后已知错误面批清（修正路线第一层）：截断轮次（`finish_reason=="length"`）
tool_calls 全判失败不执行（DeepSeek 实测确认字段值）、MCP 连接失败经
instructions 告知模型（29 遗留 6）、P0 并行调用条目对账核销——测试 2026-08-09
就在，漏勾 15 天）。
更早（2026-08-23 夜）：feature 29 交付——阶段 6 后半程 MCP client，阶段 6
全部完成：`core/mcp.py` 手写 stdio JSON-RPC（Tools only，四问拍板全 A）→
`mcp__<server>__<tool>` 桥接（清洗/截断/预算，D#74 schema 同源显式破例）→
settings `mcpServers` 两层配置 + 28 式信任门禁 → 权限零引擎改动（默认 ask 落
既有兜底、`mcp__s__*` fnmatch 白拿）。前置精读四篇 knowledge/mcp/、动工前后
两轮反向对照（真探针 + 真 DeepSeek 回合一跑即成）。档案
[features/29](features/29-20260823-mcp-client/README.md)）。
更早（晚）：feature 28 交付——skills 持久化位点与信任门槛三合一：
`.pai/skills` 段进危险写名单（acceptEdits/bypass 都翻不过）、项目级 skills
CC 式信任门禁（interactive 真人确认持久化 / once 未信任不加载+warn）、用户级
软链真身进边界（项目级刻意不解）。25 复核至此全部清零（高 2 中 2 低 3 修毕，
7 条发现两日收口）。档案
[features/28](features/28-20260823-skills-trust-and-write-guard/README.md)）。
更早（同日）：25 独立交付复核 7 条发现分级登记后，两条高级当日修毕：
feature 26 修假绿——压缩重挂锚测试三锚场景 + 双向断言，注入反证掐断重挂必红；
feature 27 skill 工具退出路径边界——`Tool.boundary_exempt` 显式豁免位（D#73，
CC/dsh 同构），子目录启动与软链正文由「权限被拒绝」变为可用。档案
[features/26](features/26-20260823-reattach-test-fix/README.md)、
[features/27](features/27-20260823-skill-boundary-exempt/README.md)）。
更早：feature 25 交付——阶段 6 skills 子阶段（MCP 子阶段未动）：
`<name>/SKILL.md` 两级目录扫描（项目赢用户 D#72）→ `<available_skills>` 目录经
build_system_prompt 装配缝注入（带预算）→ 专用 `skill(name)` 工具加载正文
（D#71，偏离 R4#A4 的 pi 定向）→ 压缩后重挂已加载正文（搭 D#42 指令重注入的车，
零 loop 改动）→ `/skill` 命令显式通道。档案
[features/25](features/25-20260822-skills/README.md)。
更早（晚）：feature 24 交付——会话格式 v1（三家收敛形：header
首行 / 统一信封 / 消息嵌套 / 压缩即条目带 firstKeptEntryId）+ 全量 `pai --resume`
（配平 + 状态从零 + 按原 id 重录，两进程接力 e2e 钉死），13 号「退出即失联」
与 23 号「拒收压缩会话」两笔债一并关掉，档案
[features/24](features/24-20260822-session-format-and-resume/README.md)。
同日早些：R4 清账日：低批 11 条 + 拍板四条（#16/19/25/27，
#27 立 [features/21](features/21-20260822-input-line-overflow/README.md) 交付
输入行折行）——R4#15~28 全清；随后 E 系列前三条交付：E1 扩展点地图
（[docs/dev/扩展点.md](扩展点.md)）、E2 system prompt 装配
（[features/22](features/22-20260822-system-prompt-assembly/README.md)，
prompt 不再谎报工具集）、E3 落盘唯一收口 + 回放不变量
（[features/23](features/23-20260822-model-visible-is-recorded/README.md)，
`replay_messages` 是 evals 地基），E2/E3 按用户指示参照 CC。
当日早些时候 feature 20 交付并推翻 feature 16 的节流结论，卡顿成因重开待诊）。
数字由机器对账：`test_status_reports_the_current_test_count` 会在完整跑时校验本页的 passed 数——漂了三次之后不再靠人肉。
给接手者（人或 AI）一页看清现状。
「做了什么」的时间线见 [devlog.md](devlog.md)，「为什么这么选」见 [decisions.md](decisions.md)，
功能级故事线见 [features/](features/README.md)，阶段地图见 [roadmap.md](roadmap.md)。

## 一句话

agent loop + 工具系统 + 会话落盘 + 阶段 1 压缩闭环已跑通；阶段 2 前半程交互模式（纯 REPL）
已交付——结构化事件流、排队消息队列、中断到进程组、`/` 命令与 `!` shell 模式、
AskUserQuestion、工具状态行。`pai` 不带参数即进 REPL。
阶段 3 记忆已交付——`PAI.md` 三层加载 + `@` 导入 + 自动记忆索引 + `remember` 写回，
且压缩后从磁盘重读重注入（不做就是长会话里指令静默失效）。
随后 feature 10 补上召回层（06 复盘悬案的落点）：记忆改一事一文件带 frontmatter、
`MEMORY.md` 由扫描结果重建（投影而非账本）、相对时间与陈旧警告、
每轮一次侧查询选 ≤5 篇注入 `<system-reminder>`（usage 计进预算熔断，连续失败即停用）。
阶段 4 权限已交付——allow/ask/deny 三态（求值顺序 deny → ask → allow）、
匹配语义下放给工具（bash 拆复合命令、fs 认路径锚点）、两层 `settings.json`、
外部命令 hook（三种退出码），pai 已能跑自己的 `guards/design_gate.py`。
随后 feature 09 补上策略层：默认兜底不再是常量 `allow` 而是工作目录边界函数
（读界内放行/界外问、写一律问）、符号链接双路径、危险路径 bypass 免疫、
权限模式四态（`default`/`acceptEdits`/`dontAsk`/`bypassPermissions`）。
在当前目录跑 pai，上级目录与系统文件已需确认。
阶段 5 流式已交付——答案逐字上屏、中断可掐在模型输出中途、工具能力标志
（`is_read_only` / `is_concurrency_safe`，收 input 的函数、默认全 False）进 `@tool`、
保序贪心分批调度（连续的并发安全工具并行，其余串行，不重排），
权限按批前置判定（偏离 CC，绕开「两个并行工具同时问真人」）。
usage 的取法按实测重写（D#58）：`include_usage` 在 DeepSeek 上是空操作，每块都看才取得到。
阶段 2 后半程 TUI 已交付——真 tty 下 `pai` 进 TUI：上面是终端 scrollback、
下面是 pai 接管的 dock（活动区 / 队列区 / 输入行或对话框 / 状态行）。
输入归属由一个仲裁函数算出来（不再是「谁先 read 谁拿到」），
于是提问期间敲 `!命令` 就是执行命令——08 那条真实事故关掉了；
`/mode` 与 shift+tab 可切权限模式；干活时打的字本轮就注入（feature 18 改了 12 的默认值）；
并发按动作聚合计数看得见。非 tty（管道/CI/注入 reader）整个不进 TUI，行为不变。
随后 feature 14/15 补上自测闭环：`PAI_TUI_RECORD` 录下写给终端的字节、
`pai-replay` 回放成 PNG（让 AI 自己看得见界面，不必每次让用户截图）；
本地假 provider 说 OpenAI 兼容协议，于是真 pai 进程能在真 pty 里跑完整回合
（真 SSE / 真 gate / 真 TUI），「需要模型开口」的功能也能自动测了——
feature 12 被用户打回的三条 bug 各钉了一条 e2e。
阶段 6 全部交付——skills（SKILL.md 两级目录扫描、目录索引进 system prompt
的渐进式披露、`skill(name)` 工具加载、压缩后重挂、`/skill` 显式通道）与
MCP client（手写 stdio JSON-RPC、`mcp__<server>__<tool>` 桥接、settings 两层
配置 + 信任门禁、权限零引擎改动）。
功能全貌见 [features/02](features/02-20260803-compaction/README.md)、
[features/05](features/05-20260810-repl/README.md)、
[features/07](features/07-20260810-permissions/README.md)。

## 模块现状

| 模块 | 状态 | 说明 |
|---|---|---|
| `core/loop.py` | 可用 | agent loop：依赖注入、max_steps 兜底、每条消息落盘、usage 落盘、用量预算熔断、自动压缩触发/熔断；主循环走流式（侧查询刻意不走）、工具按批调度、权限按批前置（D#59）；截断轮次（`finish_reason=="length"`）tool_calls 全判失败回填不执行（2026-08-24，pi 同款判据） |
| `core/tools/` | 可用 | `@tool` 从签名生成 schema；bash / read_file / write_file / edit_file |
| `core/compaction.py` | 可用 | 见下——阶段 1 主线（触发→切→摘→重建→熔断）全部接进 loop |
| `modes/once.py` | 可用 | 单次任务，跑完即退出（对应 pi 的 print-mode）。client/model 可注入故可离线测；`context_window()` + `CompactionSettings()` 默认透传；装配走 `modes/assembly.py` |
| `modes/assembly.py` | 可用 | 共用装配序列（feature 31）：rules/hooks → skills 信任 → MCP 信任与并表 → boundary → gate → memory → recall 一份实现，once/interactive 只注入差异点（asker / 权限模式 / 事件通道）；不 import loop 内部，MCP 关闭归各模式单出口 finally |
| `viz/` | 可用 | `pai-viz` 本地网页：运行时流转可视化（feature 17）——结构图（工具自省上图、阶段状态解析本表、每处标代码位置可点击跳编辑器）+ 回合时间线（读会话 JSONL 与并排的 `.events.jsonl`，分组配对成回合，2s 游标轮询实时点亮）。页面纯观察，无对话输入 |
| `core/trace.py` | 可用 | 观测流落盘：`EventTrace` 当 `on_event` 用，事件（类型数以 `core/events.py` 的 `AgentEvent` Union 为准，勿在文档里抄数）追加进 `<会话同名>.events.jsonl`（`MessageDelta` 刻意不落）；写失败吞掉且只告警一次——观测流挂了不连累正事。`compose()` 扇出渲染器与落盘器 |
| `cli.py` / `config.py` | 可用 | cli 只做参数解析与分发；OpenAI 兼容协议打 DeepSeek；`context_window()` 读 `PAI_CONTEXT_WINDOW`，默认 1_000_000（v4-flash） |
| `modes/interactive.py` | 可用 | REPL：跨轮持有 messages/锚点簿/熔断状态；历史（按 cwd 分文件、连续重复只记一条）、`\` 续行、`!` shell 模式、`/help /status /compact /clear /exit`、两级 Ctrl+C；API 出错不炸会话 |
| `core/events.py` | 可用 | frozen dataclass 扁平联合 + `render_text` 默认渲染器（D#39）。成员数不在文档里抄——已漂过三次（12→14→17），以本文件的 `AgentEvent` Union 为准。`on_event` 现在收事件对象，渲染下放 modes 层；`MessageDelta`（流式增量）与 `Interrupted(where="stream")` 于阶段 5 补上 |
| `core/queue.py` | 可用 | `PendingMessageQueue`（all/single 两种 drain + 可选谓词）。已通电（feature 18）：TUI 干活期间打的字进队列，loop 有两个注入出口（工具结果回填后 / 模型不调工具时）。队列混装消息与 `/`、`!` 命令，谓词把命令滤出注入之外、留到轮末执行。单队列取自 CC、第二出口取自 pi（D#68） |
| `core/interrupt.py` | 可用 | 进程级中断标志（D#40）。loop 在步边界与每个 tool_call 前查，bash 在轮询里查 |
| `modes/statusline.py` | 可用 | `render_tool_line(events, width)` 纯函数（按终端列宽算中文宽度）+ `\r` 原地刷新；真 tty 才启用，非 tty 退回滚动行 |
| `core/tools/ask.py` | 可用 | AskUserQuestion，asker 装配期注入；默认工具集不含它（once 无真人可问） |
| `core/paths.py` | 可用 | pai 用户级路径唯一事实源：`~/.pai/projects/<可读 slug>/{memory,sessions}/`，slug 用全路径连字符（D#44，对齐 CC） |
| `core/session.py` | 可用 | 格式 v1（feature 24，三家收敛形）：首行 header（version/id/cwd/parentSession）、统一信封 `{type,id,parentId,ts}`、消息嵌套 `message`、压缩即条目带 `firstKeptEntryId`；`load_session`（版本拒绝语义分方向、词汇表外类型拒收）、`build_messages`（压缩重建 + 指令归位）、`replay_messages`（压缩会话不再拒收）、`trim_unfinished` 配平、`resolve_resume_target`；`append` 加锁返 id、支持 `record_id`（resume 不造新身份）。旧 v0 文件按拍板不读（如实报错，不动不删） |
| `core/memory.py` | 可用 | 分层指令发现（用户级→根→cwd，local 在后，不读 AGENTS.md D#43）、`@path` 导入（相对基准/4 跳/环检测/代码块内不算）、记忆扫描（每文件前 30 行取 frontmatter、mtime 新→旧、截 200）、索引投影（`render_index`，200 行 + 25KB 双上限，截断留提示）、相对时间与陈旧警告（`memory_age` / `freshness_note`） |
| `core/recall.py` | 可用 | 按查询召回：manifest → 侧查询（`max_tokens=4096`——推理模型的 reasoning 计进该上限，实测 256 会静默截断）→ 防御式 JSON 解析（分得清「没说话」与「明确不选」）→ 白名单（容忍 `[type]` 装饰、取最长匹配）→ ≤5 篇 → `<system-reminder>` 注入块；空目录短路、`alreadySurfaced` 去重、连续 3 次失败停用并发 `RecallFailed` |
| `core/tools/memory_tool.py` | 可用 | `remember(name, description, fact, type)` 一事一文件带 frontmatter，同名即更新；写完重建 `MEMORY.md`（原子写）；name 白名单校验挡路径穿越；目录/通知/会话 id 走注入点 |
| `core/permissions.py` | 可用 | 规则解析 + 七步求值链（deny → 危险路径 → 显式 ask → bypass → acceptEdits → allow → 兜底；顺序不许改 D#46）；兜底是工作目录边界函数不是常量（D#51），且认 `Tool.boundary_exempt` 豁免位（D#73，目前只有 skill）；权限模式四态（D#53）；两层 `settings.json` |
| `core/boundary.py` | 可用 | 工作目录边界：启动 cwd 锚点 + `additionalDirectories`；前缀比到分隔符（`/tmp/proj-evil` 不算界内）；符号链接双路径；危险路径清单（shell 配置 / `.git/hooks` / `~/.ssh` / pai 自己的 settings / `.pai/skills` 段——feature 28 问 1：写 skills 即写后续指挥权） |
| `core/hooks.py` | 可用 | 外部命令 hook：退出码 0/2/其他 三态、多 hook 取最严；超时/起不来 → deny（fail-closed，D#54），其他退出码维持非阻断；`load_hooks` 读两层配置 |
| `core/gate.py` | 可用 | 装配 `before_tool_call`：规则 + hook + ask 解析（有真人问真人；无真人 = `dontAsk` 模式，两者合流 D#48/D#53）。loop 因此不认识 ask |
| `core/tools/` 的 matcher | 可用 | `Tool.matcher` + `matcher_for`；bash 拆分隔符/剥包装器/词边界，fs 三件套认 `//`、`~/`、`/`（锚到规则来源）、裸名任意深度。另有 `get_path`/`access` 声明供边界判定用（bash 两个都不声明，故结构上不参与边界 D#52） |
| `core/streaming.py` | 可用 | 流式装配：按 `index` 归并 tool_calls（`id`/`name` 只在首块）、`arguments` 拼完才解析（实测逐字符分片）、usage 每块都看（两种协议形状都取得到 D#58）、中断即停并如实回空 usage。一次响应装配成一条 assistant 消息（D#57，拒绝 CC 的 block 级记录） |
| `core/scheduler.py` | 可用 | 保序贪心分批（照 CC `partitionToolCalls`）：连续的并发安全工具合批并行、其余串行、结果按输入顺序回填；单调用批不起线程池（于是 bash 永远在主线程）。`MAX_TOOL_WORKERS=8` 是未实测经验值 |
| `modes/echo.py` | 可用 | 增量上屏：`MessageDelta` 不换行逐字写、每条消息只戴一次 `🤖`；最终答案不打两遍——按 `AgentEnd.reason` 分流（`final` 已流过不重打，`budget`/`max_steps`/`interrupted` 是 loop 合成的必须打） |
| `tui/component.py` | 可用 | `Component.render(width) -> list[str]` 纯函数契约 + `invalidate()`；`Container` 递归；`CURSOR_MARKER`（APC，零宽，`display_width` 已会剥） |
| `tui/renderer.py` | 可用 | 唯一碰终端的地方：dock 整块重绘（相对光标移动 + `CSI 2K`，包在同步输出里）、变矮先清再收缩、`commit()` 把内容上交 scrollback、提取 `CURSOR_MARKER` 摆硬件光标（IME 锚点）。绝不发 `2J`/`3J`——pai 不持有整份文档，清掉就画不回来 |
| `tui/keys.py` | 可用 | 字节 → 按键，带状态（多字节字符与转义序列会被拆成两次 read 送达）；未识别序列丢弃但留 `unknown`；bracketed paste 整段进 |
| `tui/editor.py` | 可用 | 行编辑器（纯状态机）：插入/删除/词跳/Ctrl-U-K-W/历史↑↓/`\` 续行/中文宽度感知光标；超宽按显示列折行（feature 21，CURSOR_MARKER 与选区反显跨行存活）。`Ctrl+R` 是已知回退 |
| `tui/arbiter.py` | 可用 | 输入归属仲裁：输入框非空即压住对话框，停手 1500ms 放行（常量抄自 CC，来源写在旁边），`is_suppressing()` 可被问出来（不许静默） |
| `tui/dialog.py` | 可用 | 权限 ask 与 AskUserQuestion 共用；`handoff()` 把 `!`/`/` 交回主循环执行（08 铁证的修法）；Esc 取消 |
| `tui/dock.py` | 可用 | 活动区（按动作聚合计数）/ 队列区 / 状态行（转圈 + 已用时 + token + 模式 + 待决数）；`AgentEnd` 吐一行摘要给 commit |
| `tui/transcript.py` | 可用 | alt 屏下 pai 自己持有的会话文档：存条目不存行（按 `(内容, 宽度)` 缓存），于是 resize 后历史能按新宽度重排 |
| `tui/scroll.py` | 可用 | 滚动状态机（纯状态零 IO）：follow-end、手动上滚就关掉跟随、视口变化保位、翻页留 4 行重叠 |
| `tui/altscreen.py` | 可用 | 备用屏渲染器：整屏帧 + 行 diff + 绝对定位；绝不发 `2J`、绝不重发 `?1049h`（实测两条硬约束）；`SIGWINCH` 重入保护 |
| `core/settings.py` | 可用 | 两层 `settings.json` 通用读取（`tui.altScreen` 开关）。`permissions.py` 自己那份刻意没动 |
| `tui/mouse.py` | 可用 | SGR 1006 事件（`button&3==3` 是「没按键的移动」不是拖动）+ 按批合并（wheel 累加、drag 留最后一条） |
| `tui/selection.py` | 可用 | transcript 选区：锚在逻辑行号不是屏幕行号（于是 CC 那套「滚出视口的行要另存」整块不需要）；按显示列取文本、剥净转义序列 |
| `tui/clipboard.py` | 可用 | 复制双路径：本地 `pbcopy`/`wl-copy`/`xclip`/`xsel`（看退出码）→ ssh 或全失败时 OSC 52。OSC 52 实测会静默失败，故那条路径的提示语只说「已尝试复制」 |
| `tui/app.py` / `tui/driver.py` | 可用 | app 粘合各组件（可测）；driver 读真 stdin（`select` 轮询，空闲时靠 `needs_tick()` 不白刷）。driver 无单测，靠 playground 冒烟顶着 |
| `tui/theme.py` / `tui/logo.py` | 可用 | 配色与字形（不用 emoji，D#63：字体缺字 + 宽度不确定；有测试遍历所有字形卡死「码位 < U+1F000 且非宽字符且宽度为 1」）；启动 logo 与流光动画（同一份字形每帧只改配色，于是动画离线可测） |
| `tui/screen.py` | 可用 | 最小终端模拟器（字节 → 屏幕，含 SGR 配色跟踪）。测试断言与回放出图共用同一份——分成两份的话「测试全绿」与「图上是对的」会各说各话 |
| `tui/record.py` / `tui/replay.py` | 可用 | `PAI_TUI_RECORD=<路径>` 录下写给终端的字节（含尺寸与 resize）；`pai-replay <文件> -o 图.png` 回放成 PNG，让 AI 自己看得见界面（feature 14） |
| `tui/terminal.py` | 可用 | raw mode 进出、进出备用屏（`?1049h` + `?7l`，退出无条件复原且顺序不能反）、`SIGWINCH` 同步不去抖 + 同尺寸丢弃、非 tty 闸门（判 stdout）、非主线程明确告警 |
| `core/mcp.py` | 可用 | MCP client（feature 29，四问拍板全 A）：`MCPSession` 手写 stdio JSON-RPC 显式状态机（newline 分帧、id 配对、脏 stdout 容忍、超时/进程死/isError 收敛 MCPError、close 幂等 SIGTERM→SIGKILL、不重连——死了摘除）；桥接 `mcp__<server>__<tool>`（小写归一+超长 sha256 兜底、(server,raw) 存闭包不反解、Unicode 清洗（NFKC+剥 Cf/Co/Cn）+描述 2048 截断 + 输出 100k 字符预算、MCPError→`错误：`字符串——D#74 schema 同源显式破例）；配置 settings `mcpServers` 两层自读项目赢 + `mcp_trusted` 信任门禁（28 模式）；权限零引擎改动（默认 ask 落兜底、`mcp__s__*` fnmatch 白拿）。v1 刻意不做的八条见 TODO「feature 29 遗留」 |
| `core/skills.py` | 可用 | skills（feature 25）：`scan_skills` 两级目录（`~/.pai/skills` 与 `<git根>/.pai/skills`，项目赢 D#72；缺/坏 frontmatter 跳过并 warn——刻意不抄 CC 的回退首段）、`render_catalog`（name+description 不给路径，每条 500 字符 + 总 8000 字节双上限）、`render_loaded_skills` + `make_instructions`（压缩后重挂：最近优先、单篇 2 万字符截头保留、总 10 万装不下整条丢，预算是 CC 5k/25k token 的换算值未实测校准）；feature 28：`apply_project_trust` 项目级信任门禁（CC 工作区信任对位——interactive 真人确认持久化、once 未信任不加载+warn，标记在项目身份目录）、`user_skill_link_roots` 用户级软链真身进边界（项目级刻意不解） |
| `core/tools/skill.py` | 可用 | `skill(name)` 工具（D#71）：现读磁盘剥 frontmatter 回 `<skill_content>` + 相对路径基准；未知与被隐藏说同一句话（不泄露）；不进路径边界——`boundary_exempt` 显式豁免位（feature 27，D#73：入参无路径语义、路径来自装配层扫描，CC/dsh 同构；deny/用户 ask 规则照常在前），子目录启动与软链正文由此可用；once/interactive 装配把用户级 skills 根加进 WorkingDirs.additional（附属文件的 read_file 仍走既有边界），`/skill` 命令走展开注入（REPL 空闲即跑轮次，TUI 忙碌期进 steering 队列） |
| mcp_client / evals | 未开始 | 路线图后续阶段，见 [roadmap.md](roadmap.md) |

## compaction.py 里有什么

| 函数 | 干什么 | 接进 loop 了吗 |
|---|---|---|
| `estimate_tokens` | 单条消息 token 估算，中英文分别按官方系数（0.6 / 0.3） | 间接 |
| `estimate_conversation_tokens` | 整段消息求和 | 间接 |
| `estimate_request_tokens` | 加上工具 schema，对齐 provider 的 prompt_tokens 口径 | 间接 |
| `context_tokens` | 以真实 usage 为锚 + 增量估算，误差 1.3% | ✅ 每步算，落盘，且是压缩触发判断的输入 |
| `should_compact` | 阈值判断（`tokens > window - reserve_tokens`） | ✅ 每步触发检查 |
| `find_cut_point` | 在哪下刀，按锚点真实差值反推，绝不切在孤儿 tool_result 上 | ✅ 触发时调用；单锚（刚压完只有 1 个真实点）时如实返回「无可压」，走警告分支——这条约束在 e2e 写夹具时被撞出来，见下方遗留 |
| `serialize_conversation` | 拍平成文本喂摘要模型 | ✅ 经 `summarize` 调用 |
| `summarize` | 调模型生成摘要，`style` 默认 `flat`（D#37 实测裁决） | ✅ 经 `compact` 调用 |
| `compact` | 切 + 摘 + 重建，调用方随后 reset 锚并置 `awaiting_verify` | ✅ 触发且有可压时调用 |
| `CompactionState` / `verify_compaction` / `MAX_COMPACT_FAILURES` | 熔断状态机，成败只认压缩后首次真实 usage（D#34） | ✅ 每步 verify，熔断后触发块整体跳过 |
| `CompactionSettings` | `reserve_tokens=16384`、`enabled=True`、`keep_recent_tokens=20000` | ✅ `once.run_once` 默认值透传 |

## 实测数据（真实跑出来的，非推测）

- 上下文估算误差：无锚 -33% → 锚定后 -1.3%
- 缓存命中率：单次会话 91.6%，全天统计 84.7%
- `deepseek-v4-flash`：上下文 1M、输出上限 384K；缓存命中 0.02 元/M vs 未命中 1 元/M（50 倍）
- 按 `reserve_tokens=16384`，压缩触发点是 983,616 token——以当前用量（全天 3 万）几乎不会触发

## 测试

共收集 1072 项（阶段 2 REPL 8 task + 阶段 3 记忆 7 task + 交付后五个补漏 + 文档一致性
+ 阶段 4 权限 task 1-7 + feature 10 记忆召回 7 task + feature 11 流式 task 1-6
+ feature 12 TUI task 1-9 + feature 14 录制与回放 + feature 15 假 provider + e2e
+ feature 13 alt-screen task 1-7 + feature 16 鼠标与选区 task 1-9
+ feature 17 viz-flow task 1-3.5（事件落盘 + RecallInjected/ConversationCleared + 装配））：

- `./test.sh` → 1358 passed, 3 deselected，全部离线，约 2.5 分钟。这是默认路径。
  可选并行 `./test.sh -n auto`（xdist）：实测 2:07 全绿，10 核仅 1.35× 且
  挂死旧账观察期未过，默认仍串行（feature 30 问 3·A，观察期记录见 TODO）。
  R4#26 已修（2026-08-22）：Pillow 进 dev 依赖并已装，此前常驻的那条 skip 归零；
  今后 Pillow 缺席相关测试直接红（带修法提示），不再静默 skip。
  两套假 provider 分工是硬的：`tests/fake_llm.py` 注入的假客户端测装配与逻辑；
  `tests/fake_provider.py` 起一个真 HTTP 服务，让真 pai 进程经 `PAI_BASE_URL` 打进来——
  于是 `tests/test_e2e_tui.py` 能在真 pty 里跑完整回合（真 SSE、真 gate、真 TUI），
  录制回放后断言屏幕上有什么。feature 12 被用户打回的三条 bug 各钉了一条。
- `./test.sh --llm` → 额外跑打真实 API 的冒烟测试，会产生费用。
  需同时满足有 `DEEPSEEK_API_KEY` 且 `PAI_RUN_LLM_TESTS=1`——花钱的副作用不能是默认行为。

两份真实轨迹夹具内联在 `tests/test_compaction.py`：
`REAL_TRAJECTORY`（含一条真实的 sed 失败）、`REAL_USAGE_TRAJECTORY` + `REAL_USAGE_STEPS`。

## 已知缺陷（详细条目在 [archive/devlog-2026-08.md](archive/devlog-2026-08.md)）

0. `bash` 不参与工作目录边界，且这是本功能的主要失效模式（D#52，feature 09 复盘质疑一）。
   洞不在默认路径上——bash 默认 ask，已是最保守的一档；洞在用户为了可用性
   必然要走的那条路上：once 下 bash 全被 deny，用户只能配 allow 白名单或开
   `--dangerously-skip-permissions`，而一旦配了 `allow=["Bash(cat *)"]`，
   `cat ../../etc/passwd` 就畅通无阻。CC 靠分类器模型解决，pai 明确不做分类器。
   已登记 TODO：`/permissions` 与首启应明确提示这条。
   另两个已知洞：`Bash(devbox run *)` 会放行 `devbox run rm -rf .`；
   命令拆分是正则不是 shell 词法（方向偏保守，非安全洞）。均有测试钉住当前行为。
   ~~权限层不配置就等于不存在~~ / ~~符号链接绕得开 deny~~ 两条已由 feature 09 关闭。

1. 锚与压缩天然冲突，重置后有读数盲区——且接进 loop 后暴露出比原评审更具体的一条约束
   （评审 R#7，D#34 已裁决熔断器只认真实 usage，本条按接线后的实况改写）。
   `compact()` 重置锚点簿之后，下一次真实 usage 回来前只有 0 或 1 个锚点；
   `find_cut_point` 严格要求 ≥2 个锚才能算出真实差值（`test_returns_1_when_nothing_can_be_cut`
   已钉死单锚恒返回 1）。后果：压缩后若仍处于超线状态，下一步的触发检查必然先撞见
   「无可压」警告，要再等一步真实 usage 落盘才能凑够两个锚点、算出下一次真实切点——
   e2e 测试 `test_breaker_stops_auto_compaction` 把这条约束从「设计推论」变成了「跑出来的
   事实」：每个熔断周期在脚本层面是 warn-turn + build-turn，不是简报原稿设想的
   「一超线就压」单轮节奏。这不是 bug，是锚定法必然的代价，只是此前没人把它摆到台面。
2. `estimate_tokens` 系统性低估约 1.5 倍（chat template 框架开销 + 工具 schema）。
   仍不修，理由见 decisions 第 19 条（划掉保留）与第 32 条（改用真实 usage 差值定切点）。
   补充实测：偏差不均匀——短 tool 结果低估 4-5 倍，长消息只低估约 2%。
3. `reserve_tokens=16384` / `keep_recent_tokens=20000` 仍无真实生产数据校准，只在
   loop 接线阶段用 e2e 夹具反推确认过阈值公式本身正确（`tokens > window - reserve`，
   `test_should_compact_threshold_is_strictly_greater` 钉死）；真实摘要长度、真实触发频率
   要等 `PAI_RUN_LLM_TESTS=1` 或生产使用后才能校准，登记见 TODO P1。
4. `should_compact` 的退化情形（`window <= reserve_tokens` 时恒为 True）已有上层熔断器
   兜底——`MAX_COMPACT_FAILURES=3` 接进 loop 触发块，连续压缩后仍超线会 tripped，
   不再无限重试（`test_breaker_stops_auto_compaction` 覆盖）。此前记的「尚未实现」已过时。
5. 拍平 vs 原样发（decisions 第 12/16 条）：已实测裁决，默认 `style="flat"`（D#37），
   loop 调 `compact` 不传 style，用默认值。原样发的不听话率数据留档见
   `evidence/20260809-拍平vs原样发实测/`。
6. `pai_playground/sessions/` 被 .gitignore 排除，而测试夹具的原始出处在那里——溯源链断了。

## 下一步

主线：阶段 1-6 全部交付（压缩 / REPL+TUI / 记忆 / 权限与边界 / 流式 /
skills+MCP client）。roadmap 只剩阶段 7 evals（真实会话轨迹回放评测 + 跑批，
参照 pi `packages/evals/`）——动工前照例先核对该阶段「前置精读」清单。

主线之外，接手者值得先知道的旧账（全部在 TODO，这里只挑影响判断的）：

1. ★ 拖选卡顿成因至今未确诊（feature 16 停在「实现中」的原因）：离线复现不了，
   feature 20 已推翻第一版处方——下一步是真机复现定位，不是再猜一个原因。
2. ★ pty e2e 偶发挂死（不报错不超时就是不回来）：复现即中奖，攒线索阶段。
3. ★「干完再看」手势要不要做（D#68 追记衍生）：产品问题，待用户拍板方向。
4. matcher 签名 3 参改 4 参（D#49，feature 07 起欠着）：spec 与实现凑不拢，
   要么订正 spec 要么换实现，待拍板。
5. 校准类欠账一批：压缩的 reserve/keep_recent、skills 四常量（25 遗留 3）、
   MCP 输出字符预算（29 复核质疑：对中文偏大约一倍）——都等真实使用数据。

各 feature 的遗留细目一律见 TODO 对应小节（05/06/07/09/11/12/13/16/24/25/29 等），
不在此复述——本节只保「现在该往哪看」。
