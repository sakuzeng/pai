# 当前状态快照

最后更新：2026-08-11（**阶段 2 后半程 TUI**交付）。
**数字由机器对账**：`test_status_reports_the_current_test_count` 会在完整跑时校验本页的 passed 数——漂了三次之后不再靠人肉。
给接手者（人或 AI）一页看清现状。
「做了什么」的时间线见 [devlog.md](devlog.md)，「为什么这么选」见 [decisions.md](decisions.md)，
功能级故事线见 [features/](features/README.md)，阶段地图见 [roadmap.md](roadmap.md)。

## 一句话

agent loop + 工具系统 + 会话落盘 + 阶段 1 压缩闭环已跑通；阶段 2 前半程**交互模式（纯 REPL）
已交付**——结构化事件流、steering/followUp 双队列、中断到进程组、`/` 命令与 `!` shell 模式、
AskUserQuestion、工具状态行。`pai` 不带参数即进 REPL。
阶段 3 **记忆已交付**——`PAI.md` 三层加载 + `@` 导入 + 自动记忆索引 + `remember` 写回，
且**压缩后从磁盘重读重注入**（不做就是长会话里指令静默失效）。
随后 feature 10 补上**召回层**（06 复盘悬案的落点）：记忆改一事一文件带 frontmatter、
`MEMORY.md` 由扫描结果**重建**（投影而非账本）、相对时间与陈旧警告、
每轮一次侧查询选 ≤5 篇注入 `<system-reminder>`（usage 计进预算熔断，连续失败即停用）。
阶段 4 **权限已交付**——allow/ask/deny 三态（求值顺序 deny → ask → allow）、
匹配语义下放给工具（bash 拆复合命令、fs 认路径锚点）、两层 `settings.json`、
外部命令 hook（三种退出码），**pai 已能跑自己的 `guards/design_gate.py`**。
随后 feature 09 补上**策略层**：默认兜底不再是常量 `allow` 而是**工作目录边界函数**
（读界内放行/界外问、写一律问）、符号链接双路径、危险路径 bypass 免疫、
**权限模式四态**（`default`/`acceptEdits`/`dontAsk`/`bypassPermissions`）。
在当前目录跑 pai，**上级目录与系统文件已需确认**。
阶段 5 **流式已交付**——答案逐字上屏、中断可掐在模型输出中途、工具能力标志
（`is_read_only` / `is_concurrency_safe`，收 input 的函数、默认全 False）进 `@tool`、
**保序贪心分批调度**（连续的并发安全工具并行，其余串行，不重排），
权限**按批前置**判定（偏离 CC，绕开「两个并行工具同时问真人」）。
usage 的取法按实测重写（D#58）：`include_usage` 在 DeepSeek 上是空操作，**每块都看**才取得到。
阶段 2 **后半程 TUI 已交付**——真 tty 下 `pai` 进 TUI：上面是终端 scrollback、
下面是 pai 接管的 dock（活动区 / 队列区 / 输入行或对话框 / 状态行）。
**输入归属由一个仲裁函数算出来**（不再是「谁先 read 谁拿到」），
于是提问期间敲 `!命令` 就是执行命令——08 那条真实事故关掉了；
`/mode` 与 shift+tab 可切权限模式；干活时打的字进 followUp 队列；
并发按动作聚合计数**看得见**。非 tty（管道/CI/注入 reader）整个不进 TUI，行为不变。
功能全貌见 [features/02](features/02-20260803-compaction/README.md)、
[features/05](features/05-20260810-repl/README.md)、
[features/07](features/07-20260810-permissions/README.md)。

## 模块现状

| 模块 | 状态 | 说明 |
|---|---|---|
| `core/loop.py` | 可用 | agent loop：依赖注入、max_steps 兜底、每条消息落盘、usage 落盘、用量预算熔断、自动压缩触发/熔断；**主循环走流式**（侧查询刻意不走）、工具按批调度、权限按批前置（D#59） |
| `core/tools/` | 可用 | `@tool` 从签名生成 schema；bash / read_file / write_file / edit_file |
| `core/compaction.py` | 可用 | 见下——阶段 1 主线（触发→切→摘→重建→熔断）全部接进 loop |
| `modes/once.py` | 可用 | 单次任务，跑完即退出（对应 pi 的 print-mode）。client/model 可注入故可离线测；`context_window()` + `CompactionSettings()` 默认透传 |
| `viz/` | 可用 | `pai-viz` 本地架构可视化：工具自省自动上图，阶段状态解析本表 |
| `cli.py` / `config.py` | 可用 | cli 只做参数解析与分发；OpenAI 兼容协议打 DeepSeek；`context_window()` 读 `PAI_CONTEXT_WINDOW`，默认 1_000_000（v4-flash） |
| `modes/interactive.py` | 可用 | REPL：跨轮持有 messages/锚点簿/熔断状态；历史（按 cwd 分文件、连续重复只记一条）、`\` 续行、`!` shell 模式、`/help /status /compact /clear /exit`、两级 Ctrl+C；API 出错不炸会话 |
| `core/events.py` | 可用 | 12 个 frozen dataclass 扁平联合 + `render_text` 默认渲染器（D#39）。`on_event` 现在收事件对象，渲染下放 modes 层；`MessageDelta`（流式增量）与 `Interrupted(where="stream")` 于阶段 5 补上 |
| `core/queue.py` | 可用 | `PendingMessageQueue`（all/single 两种 drain）。followUp 已通电；**steering 有注入点无输入源**（阻塞 input 拿不到「干活时打字」，等 TUI/流式） |
| `core/interrupt.py` | 可用 | 进程级中断标志（D#40）。loop 在步边界与每个 tool_call 前查，bash 在轮询里查 |
| `modes/statusline.py` | 可用 | `render_tool_line(events, width)` 纯函数（按终端列宽算中文宽度）+ `\r` 原地刷新；真 tty 才启用，非 tty 退回滚动行 |
| `core/tools/ask.py` | 可用 | AskUserQuestion，asker 装配期注入；**默认工具集不含它**（once 无真人可问） |
| `core/paths.py` | 可用 | pai 用户级路径唯一事实源：`~/.pai/projects/<可读 slug>/{memory,sessions}/`，slug 用全路径连字符（D#44，对齐 CC） |
| `core/session.py` | 可用 | append-only JSONL，落**用户目录**不再写当前工作目录；每条带 `sessionId`/`cwd`；文件名带短 id（D#45，关掉 R#15）；`append` 加锁（并发批同时回填会把 JSONL 写成半行） |
| `core/memory.py` | 可用 | 分层指令发现（用户级→根→cwd，local 在后，**不读 AGENTS.md** D#43）、`@path` 导入（相对基准/4 跳/环检测/代码块内不算）、记忆扫描（每文件前 30 行取 frontmatter、mtime 新→旧、截 200）、索引**投影**（`render_index`，200 行 + 25KB 双上限，截断留提示）、相对时间与陈旧警告（`memory_age` / `freshness_note`） |
| `core/recall.py` | 可用 | 按查询召回：manifest → 侧查询（`max_tokens=4096`——**推理模型的 reasoning 计进该上限**，实测 256 会静默截断）→ 防御式 JSON 解析（分得清「没说话」与「明确不选」）→ 白名单（容忍 `[type]` 装饰、取最长匹配）→ ≤5 篇 → `<system-reminder>` 注入块；空目录短路、`alreadySurfaced` 去重、连续 3 次失败停用并发 `RecallFailed` |
| `core/tools/memory_tool.py` | 可用 | `remember(name, description, fact, type)` 一事一文件带 frontmatter，同名即更新；写完重建 `MEMORY.md`（原子写）；name 白名单校验挡路径穿越；目录/通知/会话 id 走注入点 |
| `core/permissions.py` | 可用 | 规则解析 + **七步求值链**（deny → 危险路径 → 显式 ask → bypass → acceptEdits → allow → 兜底；顺序不许改 D#46）；兜底是**工作目录边界函数**不是常量（D#51）；权限模式四态（D#53）；两层 `settings.json` |
| `core/boundary.py` | 可用 | 工作目录边界：启动 cwd 锚点 + `additionalDirectories`；**前缀比到分隔符**（`/tmp/proj-evil` 不算界内）；符号链接双路径；危险路径清单（shell 配置 / `.git/hooks` / `~/.ssh` / pai 自己的 settings） |
| `core/hooks.py` | 可用 | 外部命令 hook：退出码 0/2/其他 三态、多 hook 取最严；**超时/起不来 → deny（fail-closed，D#54）**，其他退出码维持非阻断；`load_hooks` 读两层配置 |
| `core/gate.py` | 可用 | 装配 `before_tool_call`：规则 + hook + **ask 解析**（有真人问真人；无真人 = `dontAsk` 模式，两者合流 D#48/D#53）。loop 因此不认识 ask |
| `core/tools/` 的 matcher | 可用 | `Tool.matcher` + `matcher_for`；bash 拆分隔符/剥包装器/词边界，fs 三件套认 `//`、`~/`、`/`（锚到规则来源）、裸名任意深度。另有 `get_path`/`access` 声明供边界判定用（**bash 两个都不声明**，故结构上不参与边界 D#52） |
| `core/streaming.py` | 可用 | 流式装配：按 `index` 归并 tool_calls（`id`/`name` 只在首块）、`arguments` 拼完才解析（实测逐字符分片）、**usage 每块都看**（两种协议形状都取得到 D#58）、中断即停并如实回空 usage。**一次响应装配成一条 assistant 消息**（D#57，拒绝 CC 的 block 级记录） |
| `core/scheduler.py` | 可用 | 保序贪心分批（照 CC `partitionToolCalls`）：连续的并发安全工具合批并行、其余串行、**结果按输入顺序回填**；单调用批不起线程池（于是 bash 永远在主线程）。`MAX_TOOL_WORKERS=8` 是未实测经验值 |
| `modes/echo.py` | 可用 | 增量上屏：`MessageDelta` 不换行逐字写、每条消息只戴一次 `🤖`；**最终答案不打两遍**——按 `AgentEnd.reason` 分流（`final` 已流过不重打，`budget`/`max_steps`/`interrupted` 是 loop 合成的必须打） |
| `tui/component.py` | 可用 | `Component.render(width) -> list[str]` 纯函数契约 + `invalidate()`；`Container` 递归；`CURSOR_MARKER`（APC，零宽，`display_width` 已会剥） |
| `tui/renderer.py` | 可用 | **唯一碰终端的地方**：dock 整块重绘（相对光标移动 + `CSI 2K`，包在同步输出里）、**变矮先清再收缩**、`commit()` 把内容上交 scrollback、提取 `CURSOR_MARKER` 摆硬件光标（IME 锚点）。**绝不发 `2J`/`3J`**——pai 不持有整份文档，清掉就画不回来 |
| `tui/keys.py` | 可用 | 字节 → 按键，**带状态**（多字节字符与转义序列会被拆成两次 read 送达）；未识别序列丢弃但留 `unknown`；bracketed paste 整段进 |
| `tui/editor.py` | 可用 | 行编辑器（纯状态机）：插入/删除/词跳/Ctrl-U-K-W/历史↑↓/`\` 续行/中文宽度感知光标。**`Ctrl+R` 是已知回退** |
| `tui/arbiter.py` | 可用 | **输入归属仲裁**：输入框非空即压住对话框，停手 1500ms 放行（常量抄自 CC，来源写在旁边），`is_suppressing()` 可被问出来（不许静默） |
| `tui/dialog.py` | 可用 | 权限 ask 与 AskUserQuestion 共用；`handoff()` 把 `!`/`/` 交回主循环执行（08 铁证的修法）；Esc 取消 |
| `tui/dock.py` | 可用 | 活动区（按动作聚合计数）/ 队列区 / 状态行（转圈 + 已用时 + token + 模式 + 待决数）；`AgentEnd` 吐一行摘要给 commit |
| `tui/app.py` / `tui/driver.py` | 可用 | app 粘合各组件（可测）；driver 读真 stdin（`select` 轮询，空闲时靠 `needs_tick()` 不白刷）。**driver 无单测**，靠 playground 冒烟顶着 |
| `tui/screen.py` | 可用 | 最小终端模拟器（字节 → 屏幕，含 SGR 配色跟踪）。**测试断言与回放出图共用同一份**——分成两份的话「测试全绿」与「图上是对的」会各说各话 |
| `tui/record.py` / `tui/replay.py` | 可用 | `PAI_TUI_RECORD=<路径>` 录下写给终端的字节（含尺寸与 resize）；`pai-replay <文件> -o 图.png` 回放成 PNG，**让 AI 自己看得见界面**（feature 14） |
| `tui/terminal.py` | 可用 | raw mode 进出、`SIGWINCH` **同步不去抖 + 同尺寸丢弃**、退出无条件复原、非 tty 闸门（判 stdout）、非主线程明确告警 |
| skills / mcp_client / evals | 未开始 | 路线图后续阶段，见 [roadmap.md](roadmap.md) |

## compaction.py 里有什么

| 函数 | 干什么 | 接进 loop 了吗 |
|---|---|---|
| `estimate_tokens` | 单条消息 token 估算，中英文分别按官方系数（0.6 / 0.3） | 间接 |
| `estimate_conversation_tokens` | 整段消息求和 | 间接 |
| `estimate_request_tokens` | 加上工具 schema，对齐 provider 的 prompt_tokens 口径 | 间接 |
| `context_tokens` | **以真实 usage 为锚 + 增量估算**，误差 1.3% | ✅ 每步算，落盘，且是压缩触发判断的输入 |
| `should_compact` | 阈值判断（`tokens > window - reserve_tokens`） | ✅ 每步触发检查 |
| `find_cut_point` | 在哪下刀，按锚点真实差值反推，绝不切在孤儿 tool_result 上 | ✅ 触发时调用；单锚（刚压完只有 1 个真实点）时如实返回「无可压」，走警告分支——这条约束在 e2e 写夹具时被撞出来，见下方遗留 |
| `serialize_conversation` | 拍平成文本喂摘要模型 | ✅ 经 `summarize` 调用 |
| `summarize` | 调模型生成摘要，`style` 默认 `flat`（D#37 实测裁决） | ✅ 经 `compact` 调用 |
| `compact` | 切 + 摘 + 重建，调用方随后 reset 锚并置 `awaiting_verify` | ✅ 触发且有可压时调用 |
| `CompactionState` / `verify_compaction` / `MAX_COMPACT_FAILURES` | 熔断状态机，成败只认压缩后首次真实 usage（D#34） | ✅ 每步 verify，熔断后触发块整体跳过 |
| `CompactionSettings` | `reserve_tokens=16384`、`enabled=True`、`keep_recent_tokens=20000` | ✅ `once.run_once` 默认值透传 |

## 实测数据（真实跑出来的，非推测）

- 上下文估算误差：无锚 **-33%** → 锚定后 **-1.3%**
- 缓存命中率：单次会话 **91.6%**，全天统计 **84.7%**
- `deepseek-v4-flash`：上下文 **1M**、输出上限 **384K**；缓存命中 0.02 元/M vs 未命中 1 元/M（**50 倍**）
- 按 `reserve_tokens=16384`，压缩触发点是 **983,616** token——以当前用量（全天 3 万）几乎不会触发

## 测试

共收集 **772 项**（阶段 2 REPL 8 task + 阶段 3 记忆 7 task + 交付后五个补漏 + 文档一致性
+ **阶段 4 权限 task 1-7** + **feature 10 记忆召回 7 task** + **feature 11 流式 task 1-6**
+ **feature 12 TUI task 1-9** + **feature 14 录制与回放** + **feature 15 假 provider + e2e**）：

- `./test.sh` → **769 passed, 3 deselected**，全部离线，约 34s。**这是默认路径。**
  两套假 provider 分工是硬的：`tests/fake_llm.py` **注入**的假客户端测装配与逻辑；
  `tests/fake_provider.py` **起一个真 HTTP 服务**，让真 pai 进程经 `PAI_BASE_URL` 打进来——
  于是 `tests/test_e2e_tui.py` 能在真 pty 里跑完整回合（真 SSE、真 gate、真 TUI），
  录制回放后**断言屏幕上有什么**。feature 12 被用户打回的三条 bug 各钉了一条。
- `./test.sh --llm` → 额外跑打真实 API 的冒烟测试，**会产生费用**。
  需同时满足有 `DEEPSEEK_API_KEY` 且 `PAI_RUN_LLM_TESTS=1`——花钱的副作用不能是默认行为。

两份真实轨迹夹具内联在 `tests/test_compaction.py`：
`REAL_TRAJECTORY`（含一条真实的 sed 失败）、`REAL_USAGE_TRAJECTORY` + `REAL_USAGE_STEPS`。

## 已知缺陷（详细条目在 [archive/devlog-2026-08.md](archive/devlog-2026-08.md)）

0. **`bash` 不参与工作目录边界，且这是本功能的主要失效模式**（D#52，feature 09 复盘质疑一）。
   洞**不在默认路径上**——bash 默认 ask，已是最保守的一档；洞在**用户为了可用性
   必然要走的那条路上**：once 下 bash 全被 deny，用户只能配 allow 白名单或开
   `--dangerously-skip-permissions`，而一旦配了 `allow=["Bash(cat *)"]`，
   `cat ../../etc/passwd` 就畅通无阻。CC 靠分类器模型解决，pai 明确不做分类器。
   已登记 TODO：`/permissions` 与首启应明确提示这条。
   另两个已知洞：`Bash(devbox run *)` 会放行 `devbox run rm -rf .`；
   命令拆分是正则不是 shell 词法（方向偏保守，非安全洞）。均有测试钉住当前行为。
   ~~权限层不配置就等于不存在~~ / ~~符号链接绕得开 deny~~ 两条**已由 feature 09 关闭**。

1. **锚与压缩天然冲突，重置后有读数盲区——且接进 loop 后暴露出比原评审更具体的一条约束**
   （评审 R#7，D#34 已裁决熔断器只认真实 usage，本条按接线后的实况改写）。
   `compact()` 重置锚点簿之后，**下一次真实 usage 回来前只有 0 或 1 个锚点**；
   `find_cut_point` 严格要求 ≥2 个锚才能算出真实差值（`test_returns_1_when_nothing_can_be_cut`
   已钉死单锚恒返回 1）。后果：压缩后若仍处于超线状态，**下一步的触发检查必然先撞见
   「无可压」警告**，要再等一步真实 usage 落盘才能凑够两个锚点、算出下一次真实切点——
   e2e 测试 `test_breaker_stops_auto_compaction` 把这条约束从「设计推论」变成了「跑出来的
   事实」：每个熔断周期在脚本层面是 warn-turn + build-turn，不是简报原稿设想的
   「一超线就压」单轮节奏。这不是 bug，是锚定法必然的代价，只是此前没人把它摆到台面。
2. `estimate_tokens` 系统性低估约 **1.5 倍**（chat template 框架开销 + 工具 schema）。
   **仍不修**，理由见 decisions 第 19 条（划掉保留）与第 32 条（改用真实 usage 差值定切点）。
   补充实测：偏差**不均匀**——短 tool 结果低估 4-5 倍，长消息只低估约 2%。
3. `reserve_tokens=16384` / `keep_recent_tokens=20000` **仍无真实生产数据校准**，只在
   loop 接线阶段用 e2e 夹具反推确认过阈值公式本身正确（`tokens > window - reserve`，
   `test_should_compact_threshold_is_strictly_greater` 钉死）；真实摘要长度、真实触发频率
   要等 `PAI_RUN_LLM_TESTS=1` 或生产使用后才能校准，登记见 TODO P1。
4. `should_compact` 的退化情形（`window <= reserve_tokens` 时恒为 True）**已有上层熔断器
   兜底**——`MAX_COMPACT_FAILURES=3` 接进 loop 触发块，连续压缩后仍超线会 tripped，
   不再无限重试（`test_breaker_stops_auto_compaction` 覆盖）。此前记的「尚未实现」已过时。
5. 拍平 vs 原样发（decisions 第 12/16 条）：**已实测裁决**，默认 `style="flat"`（D#37），
   loop 调 `compact` 不传 style，用默认值。原样发的不听话率数据留档见
   `evidence/20260809-拍平vs原样发实测/`。
6. `pai_playground/sessions/` 被 .gitignore 排除，而测试夹具的原始出处在那里——溯源链断了。

## 下一步

阶段 2（REPL + **TUI**）、阶段 3（记忆）、阶段 4（权限 + 工作目录边界）、阶段 5（流式）已交付。
下一步按 roadmap 是**阶段 6 skills / MCP client**。
feature 12 的遗留见 TODO「feature 12（TUI）交付遗留」，其中一条值得先知道：
**跑很久且不发事件的工具执行期间，用户打的字在 dock 上完全看不见**（字符没丢，
在内核 tty 缓冲区，但屏幕不动）——在最需要反馈的时候没有反馈，12 复盘质疑二。
阶段 5 的四条遗留见 TODO「feature 11（流式）遗留」，其中两条值得先知道：
**并发在界面上完全不可见**（做了并发却看不见并发）、
**中断丢弃半条 assistant 消息**（屏幕上看得见、上下文里没有）。

**一条待用户拍板**（见 TODO）：
1. matcher 签名从已拍板 spec 的 3 参改成 4 参（D#49，feature 07 起就欠着）——
   spec 第 2 节与第 4 节凑不到一起，路径锚点是「规则的属性」，三参没有出口。
   要么认可并订正 spec，要么换实现。
   ~~2. `/mode` 与 shift+tab~~ **已由 feature 12 交付**。

阶段 1 遗留的两条候选仍在 TODO：
- **reserve_tokens / keep_recent_tokens 实测校准**——目前仍是从 pi 借来的经验值，
  需要真实会话（或 `--llm` 冒烟测试）的真实摘要长度与触发频率数据才能定。
- **microcompact 评估**（K source-walks/cc-compaction.md）——pai 的 4 个工具全部可重放，
  按 tool_call_id 清旧结果不用调模型，可能是性价比最高的第二级压缩，阶段 1 跑通后评估。

阶段 2 REPL 的 6 条遗留见 TODO「feature 05（REPL）遗留」小节，其中两条值得先知道：
**`Tool.run` 的返回契约分不出工具内部错误**（状态行因此标不出红叉）、
**steering 无真实输入源**（结构已就位，等 TUI/流式通电）。
