# knowledge —— 学习沉淀

与 `docs/dev/`（开发证据）正交：那边记「pai 做了什么、为什么」，
这边记「外面的世界怎么做、我学到了什么」。

## 结构：按「这是哪个知识点」分

分类标准是知识点（主题），不是来源。 目录 = 一个知识点，同一个知识点下
官方文档、pi 源码、CC 源码、dsh 源码与其第一方文档、自己的沉淀并排放——
因为读的时候本来就要并排读。

```
loop/            agent loop 的结构与运行时、消息注入与队列
context/         上下文窗口、压缩、token 计量
memory/          记忆分层与召回
permissions/     权限求值、工作目录边界、hooks 与门禁
tui/             终端 UI：绘制、备用屏、鼠标、输入归属、终端物理特性
streaming/       流式输出与工具调度
skills/          按需加载的能力扩展：发现、索引注入、渐进式披露
mcp/             MCP client：传输、工具桥接、命名、超时预算、信任
model-api/       打模型 API 时要知道的事（key 取法、max_tokens 语义）
engineering/     换个项目仍成立的通用工程方法（测试、观测、接缝、进程）
overview/        跨主题的覆盖图与索引
anna/            anna 工作区方法论（本地不入库，R2#1 裁决——这不是知识点分类，
                 是入库边界，别按主题拆散它）
inbox.md         还写不出锚点的：新工具/想法一行一项待消化
```

来源信息不丢，靠文件名前缀承载（这是原「按来源分」规约留下的、仍然有效的一半）：

| 前缀 | 来源 | 例 |
|---|---|---|
| `cc-` | Claude Code 反编译源码 | `loop/cc-loop.md` |
| `pi-` | pi-mono 源码 | `loop/pi-loop.md` |
| `dsh-` | deepseek-harness 源码或其仓内第一方文档（`docs/*.zh.md`） | `loop/dsh-loop.md` |
| `pi-cc-` / `cc-dsh-` 等 | 对照多家的走读（前缀按字母序拼，最多两家；三家以上用无前缀 + 标题写清） | `permissions/cc-pi-permission-boundaries.md` |
| `claude-` | Claude Code 官方文档（不是源码） | `memory/claude-memory.md` |
| 无前缀 | 没有单一外部原文的沉淀（横切概念 / 方法论回流 / 开发中撞出的通用知识） | `tui/terminal-width.md` |

`dsh-` 为什么不拆成「源码」与「官方文档」两个前缀（D#69）：CC 那边拆是因为
两者出处根本不同——官方文档在 anthropic.com，源码是反编译来的，且两者常互相打脸。
dsh 的文档与源码在同一个仓库、同一个 commit 里，拆开只会制造一个每次都要问
「这算哪个」的边界。但证据等级仍要在正文里标：写「dsh 文档说」还是「dsh 源码是」，
一句话的事，别省。

目录随第一篇笔记创建，禁止空目录占位；不嵌套二级目录。

2026-08-13 改版记录（用户指定）：原规约是「按来源分」（`claude-docs/` / `source-walks/` /
`concepts/`），理由是「主题会重叠，来源不会」。
改的原因是它把该并排读的东西拆散了——想搞清 agent loop，得同时翻 `source-walks/pi-agentloop.md`、
`source-walks/cc-message-queue.md` 和一堆 `concepts/`，而目录结构一点忙都帮不上。
代价照旧存在且必须承认：主题确实会重叠（`cc-message-queue` 既属 loop 也沾 tui 的输入归属，
`reasoning-models-max-tokens` 是做召回时撞出来的却归 model-api）。
重叠时的裁决规则：按「这条知识本身在讲什么」放，不按「当时为什么去读它」放，
另一头用 `相关：` 行互链。28 篇一次性迁完，历史链接已全仓改写。

## 开发中用到的知识，能不能落这里？

能，但要先分两种——判据是「换个项目还成不成立」：

| 这条知识 | 落哪 | 例子 |
|---|---|---|
| 只关于 pai 自己：为什么这么设计、踩了什么坑、当时怎么选的 | 不进 knowledge。进 `docs/dev/`：过程写 features 档案的 devlog、取舍写 decisions、教训写复盘 | 「compact 后指令消息会被摘掉，所以要重注入」 |
| 可迁移的通用工程知识：换个语言/项目依然成立的事实与机制 | 对应知识点目录，用无前缀文件名 | POSIX 进程组与 `killpg` → `engineering/`；东亚宽字符占两列 → `tui/` |

判断卡壳时问一句：这段话如果出现在别人的项目里，还有用吗？
有用 → knowledge 的知识点目录；只有 pai 的人看得懂 → `docs/dev/`。

两边可以互链，但不要互抄：knowledge 写机制本身，档案里写「pai 在哪儿用到它、
当时撞出什么」，中间用一行链接连起来（指针优先，规约 4）。

## 使用规约

1. 按需精读，动工前补笔记，禁止囤积式通读。只读 roadmap 当前阶段
   「前置精读」列出的章节（见 [../docs/dev/roadmap.md](../docs/dev/roadmap.md)）。
2. 准入一问：这篇笔记能否锚到已存在的东西（某个源文件、已写下的 decisions
   条目、或已动工/即将动工的 roadmap 阶段的前置精读清单）？只能锚到遥远未来阶段的，
   先在该阶段「前置精读」记一行待读，动工那天再落笔记——否则就是囤积。
   面经、考点、通识囤积去面试准备仓库。
   唯一豁免：[inbox.md](inbox.md)——还写不出锚点的新工具/想法在那里一行一项地待着，
   升格成正式笔记时才须过准入一问；升格或裁决不做后从 inbox 划掉。
3. 指针笔记是一等公民：面试准备仓库已有的深度文档只写一页指针
   （链接原文 + 摘 pai 视角结论），不搬运正文。

## 笔记模板

```markdown
# <标题>
- 来源：<官方文档 URL / 仓库内相对路径。本机绝对路径不进笔记正文——
  收进本页「外部参照」一节，正文以「外部参照 N」引用>
- 精读日期：YYYY-MM-DD
- pai 锚点：<src/pai/... | docs/dev/decisions.md #N | roadmap 阶段 N>

<正文>
```

## 登记表

状态取值：指针 = 只链接原文 + 摘 pai 视角结论；精读 = 对照来源逐点写的完整笔记；
沉淀 = 无单一原文可链的原创整理（如方法论回流）。指针升精读的时机：动工时发现
指针的结论粒度不够用。

| 笔记 | 一句话 | 状态 | pai 锚点 |
|---|---|---|---|
| `loop/` | | | |
| [loop/cc-loop.md](loop/cc-loop.md) | CC 的 loop 结构与运行时：`query()` 是异步生成器（外壳只负责「正常返回才补发 completed」，started-without-completed 是刻意保留的失败信号）；run↔query 术语对照；CC 的 loop 内部只有一个队列出口（另一个 `useQueueProcessor` 在循环之外，起的是新 query）→ 循环条件不看队列，故 `next` 在纯答话轮次退化成 `later`（⚠️ 「退化」指投递时机，`priority` 字段入队即定终身不改，出队排序上 next 仍优先于 later），而 pi 不退化。另含：Ⓐ 的门槛由调用方传（全仓仅两个调用点）+ 门槛切片 vs 取最高的双语义、Ⓐ 的空转路径（空数组一路流过 + `snapshot` 引用稳定性是 `useSyncExternalStore` 的命门）、路 B 是自驱动 effect（两个订阅源 / 三道守卫 / 靠同步执行顺序防重入）、标签怎么打（选函数而非判内容；`LocalShellTask` 用 feature flag 调档）、术语出处（mid-turn drain 是 CC 行话不是标识符）、四条具体走位 + 一次完整时间线。⚠️ CC 没有 followUpQueue；`attachment` 是 58 个分支的注入物中间层，它做的三件事里 pai 只需补两件（可见性靠事件流、语气外壳靠字符串包装，都与协议无关） | 精读 | src/pai/core/loop.py、src/pai/core/recall.py、features/18 |
| [loop/cc-prompt-and-transcript.md](loop/cc-prompt-and-transcript.md) | CC 的两个「唯一入口」：`getSystemPrompt(tools,…)` 是装配层函数——指导语按「有没有这个工具」条件化（enabledTools 集合）而非干列名字，`SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 把会话相关段压到静态前缀之后护缓存（动态位在前会把前缀哈希裂成 2^N）；`recordTranscript(messages)` 是全 QueryEngine 唯一落盘口且幂等——按消息 uuid 对已落盘集合去重、只写增量、顺手串 parentUuid 链。可迁移拆解：「唯一收口」不需要消息身份（pai `_record` 已对齐），「按身份幂等」依赖 uuid（归 R4#A1）——这也解释了 pai 的 `replay_messages` 为何必须拒绝含 compaction 的会话而不是硬拼 | 精读 | src/pai/core/loop.py、src/pai/core/session.py、features/22、features/23 |
| [loop/session-format-three-way.md](loop/session-format-three-way.md) | 会话格式三家对照（pi session-manager / CC sessionStorage+conversationRecovery / dsh persistence.zh.md）：四件事完全收敛——首行 header（带 version，拒绝语义分「太新请升级 / 太旧无升级路径」两个方向）、统一信封 {type,id,parentId,ts} + 消息嵌套在 payload、id 链（pi uuidv7 / CC uuid4）、压缩是带 firstKeptEntryId 的**条目**而非改写（重建 = 摘要 + 保留段 + 其后全部，历史一字不删）。恢复侧：CC 三道卫生过滤（半截回合整块删；反教材——过滤时造新 uuid 会让转录每次 resume 指数增长）、删除后 relink 断链、dsh「内存配平中断轮次、物理尾部保持撕裂原样」+ 词汇表外事件拒绝而非静默跳过 | 精读 | src/pai/core/session.py、features/24 |
| [loop/cc-message-queue.md](loop/cc-message-queue.md) | 不是两条队列，是一条队列 + 三档优先级（`now`/`next`/`later`）；用户输入默认 `next` 即中途注入、系统消息默认 `later`（「人说话默认优先，机器说话默认等着」）；`now` 会 abort 在跑的工具但交互式用户产生不了，只有 SDK 能设；注入形状是 attachment 跟在 toolResults 后不是 user 消息；slash 命令排除在 mid-turn drain 外。附一条 pai 自己的前置缺陷：单层 `for` 压平了 pi 的双层 while，不调工具的回合会把 steering 卡死在队列里 | 精读 | src/pai/core/queue.py、src/pai/core/loop.py、features/18 |
| [loop/dsh-loop.md](loop/dsh-loop.md) | dsh 的 loop：一个 inbox（两个列表 next-turn / next-step）+ 两层循环，`kick()` 的 `while (await this.turn())` 外套 `turn()` 的 step 循环。三个出口全在 loop 内：`:266` 每个 step 边界都 claim、`:299` 循环条件本身带「队列非空」（= pi 的形状）、`:324` turn/end 后 `hasPending` 直接开新 turn（= CC 的「重开」但位置在 agent 自己手里，dsh 没有「loop 之外」这个位置）。⚠️ 本篇更正 pi-loop.md：「在 loop 内部问队列是 pi 独有的」加进 dsh 后不成立，真正独有的是 CC。另含：术语上 dsh 与 pai 同边、与 pi/CC 相反（step = 一次请求+工具，turn = 一条用户消息到下一条）；`claim` 两个列表取法不对称（next-step 全量抽干 / next-turn 每 turn 只取 1 条）；inbox 持久化（`agent/inbox/spliced` 落会话日志，重启还在）；三个动词 = 两个正交轴（followup/steer/inject = 列表 × 唤不唤醒，`inject()` 的「注入不唤醒」pai/CC 都没有）；`agent/turn-stopping` 把pai 当 bug 修掉的那条前置缺陷做成了公开插件接缝（`/loop` 模式住在这里）。★ 默认值与 CC/pai 相反：忙碌时回车默认 `queue`（等你干完），Cmd/Ctrl+Enter 才插话，且默认值用户可配 —— 直接推翻 D#68「没有参照实现」这条论据 | 精读 | src/pai/core/loop.py、src/pai/core/queue.py、decisions #68 #69、features/18 |
| [loop/pi-agentloop.md](loop/pi-agentloop.md) | pi 四层分层 + 十种事件 + 双队列注入时机 + AgentLoopConfig 全部钩子 | 精读 | roadmap 阶段 2 |
| [loop/pi-loop.md](loop/pi-loop.md) | pi 的 loop 结构与运行时：四者不是四层栈（`AgentHarness` 是 `Agent` 的兄弟，两者各自直接调 `runAgentLoop`，且 pi 自己的 coding-agent 里 `AgentHarness` 零命中）；两层 while 就是双队列语义的物理形态——内层条件 `hasMoreToolCalls \|\| pendingMessages.length > 0` 保证「模型不调工具也能同 run 内注入」；agent/run/turn 三个术语的边界；首个 turn 不发 `turn_start`；`stopReason === "length"` 时该轮 tool_call 全部判失败；无步数上限；「在 loop 内部问队列」是 pi 独有的形状（与 CC/pai 的结构性分歧表）。⚠️ 本篇更正了 `loop/pi-agentloop.md` 的四层分层错误 | 精读 | src/pai/core/loop.py、src/pai/core/queue.py、features/18 |
| `context/` | | | |
| [context/cc-compaction.md](context/cc-compaction.md) | CC 四级递进压缩策略要点 | 指针 | roadmap 阶段 1 |
| [context/claude-context-management.md](context/claude-context-management.md) | 官方上下文窗口与 compact 机制，对照 pai 压缩现状 | 精读 | src/pai/core/compaction.py |
| [context/context-management.md](context/context-management.md) | 上下文管理全梯度 + 「窗口用不满≠不用管」的实测认知 | 沉淀 | src/pai/core/compaction.py |
| `memory/` | | | |
| [memory/cc-memdir.md](memory/cc-memdir.md) | 记忆召回是框架主动做的：便宜模型按 header manifest 选 ≤5 篇；外加 memoryAge 的陈旧警告 | 精读 | src/pai/core/memory.py |
| [memory/claude-memory.md](memory/claude-memory.md) | 官方两套记忆（人写的分层指令 / 模型自写的自动记忆）、加载算法，及压缩重注入这条 pai 尚不存在的 bug | 精读 | roadmap 阶段 3 |
| `permissions/` | | | |
| [permissions/cc-pi-permission-boundaries.md](permissions/cc-pi-permission-boundaries.md) | CC 的默认不是常量是函数（`in_working_dir ? allow : ask`）；pi 零内置权限 + 明写免责；钩子失败语义两家都 fail-closed 而 pai 反着来 | 精读 | src/pai/core/permissions.py、features/09 |
| [permissions/claude-permissions-hooks.md](permissions/claude-permissions-hooks.md) | 权限三态求值顺序、Bash 匹配四个坑、「语义下放给工具」的官方原文、hooks 决策协议 | 精读 | roadmap 阶段 4 |
| [permissions/hooks-gates.md](permissions/hooks-gates.md) | hooks 事件与工具调用门禁模式（阶段 4 设计输入）；fail-open vs fail-closed 按失败代价分场景 | 沉淀 | roadmap 阶段 4、decisions #54 |
| [permissions/path-boundary-checks.md](permissions/path-boundary-checks.md) | 路径边界判定四条坑：前缀≠包含、两个 cwd 锚点（合并即 cd 逃逸）、符号链接双路径且 allow/deny 反向、判不出来≠没问题 | 沉淀 | src/pai/core/boundary.py、decisions #51 #52 |
| `tui/` | | | |
| [tui/alt-screen-and-mouse.md](tui/alt-screen-and-mouse.md) | `?1049h` 不幂等（已在备用屏时重发=清屏+回原点，两个 macOS 终端实测一致，有源码把它写反）；1000/1002/1003 是互斥单选、1006 只是编码；DECRQM 在 Terminal.app 完全不可用且不被识别的查询会漏成可见字符污染测量；备用屏里 resize 终端不替你重排；OSC 52 会被静默拒绝（本机 iTerm2 实测写不进剪贴板）故自写选区不能只靠它 | 沉淀 | src/pai/tui/terminal.py、features/13 |
| [tui/cc-alt-screen.md](tui/cc-alt-screen.md) | CC 的 alt-screen 对外部用户默认关（`USER_TYPE==='ant'` 才开）+ 三个逃生口 + tmux -CC 同步探测；命中测试只要 130 行便宜，选区要 917 行昂贵（拿走鼠标=拿走终端原生选中复制）；「进 alt」必须早于「第一帧」否则退出后才暴露；alt 屏是个需要自愈的状态 | 精读 | src/pai/tui/terminal.py、features/13 |
| [tui/cc-input-ownership-and-modes.md](tui/cc-input-ownership-and-modes.md) | 对话框不抢焦点，它等你停手（输入框非空即压住权限/提问框，停手 1500ms 才弹，且显式提示「Waiting for permission…」）——与 pai TODO 里凭文档推出的「问题框接管输入焦点」方向相反；模式轮转 `plan` 在环里而 `dontAsk` 不在；resize 刻意不去抖 | 精读 | src/pai/modes/interactive.py、src/pai/core/tools/ask.py、roadmap 阶段 2 |
| [tui/claude-interactive-mode.md](tui/claude-interactive-mode.md) | 官方交互契约（中断两级 / 干活时输入 / `!` shell 模式 / 历史），及 pai REPL 取舍 | 精读 | roadmap 阶段 2 |
| [tui/pi-alt-screen.md](tui/pi-alt-screen.md) | alt-screen 是另一个渲染器不是补丁：VStack/ScrollView/每帧重建的布局树；follow-end 状态机是「流式时用户在往回翻」的唯一解；退出时要重渲染完整文档打回主屏（拿最后一帧顶替就是裁剪过的视口）；原则 2 的原文是「别在 main-screen 里假装」不是「别做 alt-screen」 | 精读 | src/pai/tui/、roadmap 阶段 2 原则 2、features/13 |
| [tui/pi-tui-main-screen.md](tui/pi-tui-main-screen.md) | main-screen 的差量重绘 diff 的是整份文档的行数组，宽度一变就全量重绘并 `\x1b[3J` 清掉 scrollback（只有持有整份文档才敢清）；`CURSOR_MARKER` 的位置永远要摆、`showHardwareCursor` 只管可不可见；超宽行 fail-loud。另纠一条范围错误：`tui-plan.md` 讲的是 alt-screen（当时不做，feature 13 已做，见 pi-alt-screen.md） | 精读 | src/pai/modes/interactive.py、roadmap 阶段 2 |
| [tui/terminal-raw-mode.md](tui/terminal-raw-mode.md) | raw mode 的三条静默陷阱：`input()` 永远等不到行尾（Enter 发 `\r`）且 Ctrl+C/D 同时失效 = 程序必死；终端替你折行而你的光标算术不知道；emoji 不能做界面字形（字体缺字 + 宽度不确定）。外加退出时无条件复原 | 沉淀 | src/pai/tui/、features/12 |
| [tui/terminal-width.md](tui/terminal-width.md) | 中文占两列、ANSI 不占列；必须先按可见文本截断再上色 | 沉淀 | src/pai/modes/statusline.py |
| `streaming/` | | | |
| [streaming/cc-streaming-tools.md](streaming/cc-streaming-tools.md) | 工具在模型还没说完就开跑：能力标志是收 input 的函数（默认全 false）、保序贪心分批、只有 Bash 出错才杀兄弟、子 AbortController 不向上传播；`getAssistantMessageId` 那条不适用于 pai（协议不同） | 精读 | src/pai/core/loop.py、roadmap 阶段 5 |
| [streaming/streaming-tool-calls.md](streaming/streaming-tool-calls.md) | 流式下 tool_calls 按 `index` 归并且 `arguments` 逐字符分片；usage 实测永远在末块（`include_usage` 是空操作，惯用的「choices 为空即 usage 块」分支永不触发 → 用量静默丢失）；中断的流没有 usage | 沉淀 | src/pai/core/loop.py、roadmap 阶段 5 |
| `mcp/` | | | |
| [mcp/claude-mcp.md](mcp/claude-mcp.md) | 官方 MCP 全景（抓取 2026-08-23，行为条目带 v2.1.1xx~2.2xx 版本）：四种传输与 `mcpServers` 配置形状、scope 三层与项目级审批+工作区信任链、`mcp__s__t` 命名、超时三件套（连接 `MCP_TIMEOUT`/执行默认约 28h/空闲 5min-30min）、输出预算（警告 10k 固定、上限 25k token 可调、超限落盘换文件引用）、重连退避 1s×2 封顶 5 次、工具搜索默认延迟加载（阈值 10% 窗口）、根级组合器 schema 拍平 | 精读 | features/29、roadmap 阶段 6 |
| [mcp/pi-mcp.md](mcp/pi-mcp.md) | pi 显式不做 MCP（写进 philosophy 的产品决策，git 全历史零 MCP 文件）：「225-token README beats a 13,000-token MCP server description」；替代形态三层（CLI+README+Skills / Extensions 进程内注册 / resources_discover）。可抄的骨架：工具注册表与来源解耦（MCP 是灌表 adapter）、prepareToolCall 固定流水线让权限层结构性覆盖、错误转 isError 回填、fail-closed、session_start 起 shutdown 收的进程契约 | 精读 | features/29、src/pai/core/tools/__init__.py |
| [mcp/cc-mcp.md](mcp/cc-mcp.md) | CC 2.1.88 反编译：tools/list 后五道工序（capability 门禁→Unicode 清洗防 HackerOne #3086545→description 截 2048→schema 原样透传→annotations 映射能力位）；权限默认 ask、specifier 三形态禁括号；memoize 连接池+onclose 惰性重连（作者自留 TODO 怀疑）、SDK 只发 onerror 不发 onclose 的缝隙补丁、stdio 关闭 SIGINT→SIGTERM 升级；输出 25k token 超限落盘+类型签名；MCP 工具默认全延迟加载 | 精读 | features/29、src/pai/core/permissions.py |
| [mcp/dsh-mcp.md](mcp/dsh-mcp.md) | dsh（pin 47f9438）918 行源码/2393 行测试/0 行子系统文档：Tools only（Resources/Prompts 延后判据原文）、`serverName` 用户配置不信远端、命名 hash 兜底 `\0` 分隔、代隔离重连（uptime 重置预算/等关闭再退避否则彻底停/故障期不注销工具）、裸 request 绕 SDK 缓存副作用。两个缺口=pai 超车点：MCP 工具不过任何权限门（`mcp__*` 通配是记录成已具备的空头期权）、上下文全量平铺无预算。⚠️ 文档 vs 源码八处不符（D1-D8），Agent Note 是不更新的决策快照 | 精读 | features/29、src/pai/core/permissions.py、knowledge/skills/dsh-skills.md |
| `skills/` | | | |
| [skills/claude-skills.md](skills/claude-skills.md) | 官方 skills 全景：SKILL.md（frontmatter+正文）、四级存放与冲突规则、渐进式披露（description 常驻/正文调用时载）、列表预算（窗口 1% + 每条 1536 字符）、压缩后重挂（单个 5k/共享 25k token）；含 2.1.239 真实探针两条出入（frontmatter name 也能调起、坏 YAML 时正文首段顶 description） | 精读 | roadmap 阶段 6、features/25 |
| [skills/pi-skills.md](skills/pi-skills.md) | pi 最小形态（R4#A4 原型）：扫描（SKILL.md 目录不再递归/根下 .md/ignore 文件/realpath 去重/先到先得）+ `<available_skills>` XML 进 system prompt + 模型用 read 加载正文（零新增工具，pi 自认不总灵）+ `/skill:name` 展开成 `<skill>` 块。⚠️ 无列表预算（三家唯一）、压缩后正文不重挂；文档说 name 必填而源码回退目录名 | 精读 | features/25、src/pai/core/memory.py |
| [skills/cc-skills.md](skills/cc-skills.md) | CC 2.1.88 反编译：skill=command，Skill 工具调用（inline 展开 prompt / fork 子 agent 两路）；目录经 system-reminder attachment 增量注入（sentSkillNames + resume 抑制），预算窗口 1%、每条 250 字符（官方文档已放宽到 1536——版本漂移实据）；压缩重挂 `createSkillAttachmentIfNeeded`（最近优先、单个截 5k、总预算 25k、装不下整条丢）与官方数字交叉验证一致 | 精读 | features/25、src/pai/core/compaction.py |
| [skills/dsh-skills.md](skills/dsh-skills.md) | dsh（pin 47f9438）四件套切分：registry/provider/consumer 三层 + 三层数据结构（Summary→Candidate→Definition，目录轻/正文重分离）；rank 优先级（项目赢用户）；目录注入是持久 user-role system-reminder + digest 比对替换 + 压缩隐藏后自愈重发；`skill({name})` 专用工具每次重读盘。⚠️「零新增工具」是 pi 形态，dsh 有工具——加载动作三家三分 | 精读 | features/25、roadmap 阶段 6 |
| `model-api/` | | | |
| [model-api/pi-cc-api-keys.md](model-api/pi-cc-api-keys.md) | pi 的映射表+注入钩子 vs CC 的带来源+apiKeyHelper；结论：key 留 .env 不进 settings.json | 精读 | src/pai/config.py |
| [model-api/reasoning-models-max-tokens.md](model-api/reasoning-models-max-tokens.md) | 推理模型的 reasoning 计进 `max_tokens`：上限设小不省钱，只会让 content 静默变空串（实测同 query 思考量差 17 倍） | 沉淀 | src/pai/core/recall.py |
| `engineering/` | | | |
| [engineering/injection-seams.md](engineering/injection-seams.md) | 装配期捕获：依赖会变时闭包存的还是当时那个值，症状是「我改了但没反应」；判据、兼容写法、「改完立刻生效」的测试前后结果必须不同（否则假绿）、同一个坑会连撞两次；外加「接缝上的 bug 离线测试结构上看不见」 | 沉淀 | src/pai/core/gate.py、features/12 |
| [engineering/instruments-lie.md](engineering/instruments-lie.md) | 观测工具骗人的四种方式：污染被测对象／全量记录器漏掉第二个写入出口／读取工具给的是复合视图／能力探测探的是另一个能力。前三种都长得像「被测代码有 bug」，第四种让你以为自己做过了一次根本没发生的观测 | 沉淀 | src/pai/tui/record.py、features/13 复盘、features/16 |
| [engineering/mutation-testing-pitfalls.md](engineering/mutation-testing-pitfalls.md) | 注入反证的坑：注错了和没测住现象一样（全绿）；「没被执行到」分控制流被屏蔽与测试场景压根不走那条路两种；正交防线要分别注；红阶段就绿的测试不具本次鉴别力 | 沉淀 | features/07、features/09、features/13 的 devlog |
| [engineering/process-groups-and-interrupts.md](engineering/process-groups-and-interrupts.md) | 独立进程组 + killpg 才杀得干净；杀不净的第一个症状是输出丢失不是资源泄漏 | 沉淀 | src/pai/core/tools/shell.py |
| `overview/` | | | |
| [overview/claude-docs-map.md](overview/claude-docs-map.md) | 官方文档章节 → pai 归属/不做 的覆盖图 | 沉淀 | docs/dev/roadmap.md |
| `anna/` | | | |
| [anna/gates.md](anna/gates.md) | anna 确定性门禁方法论（含短板教训）。本地不入库（R2#1 裁决，.gitignore 排除）——克隆本仓库的读者看不到此文件 | 沉淀 | roadmap 阶段 4 |
| [inbox.md](inbox.md) | 待消化收件箱（准入豁免区，一行一项） | 常驻 | 升格前豁免 |
