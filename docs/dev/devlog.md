# 开发日志

「做了什么」的时间线。为什么这么选见 [decisions.md](decisions.md)，
下一件该做什么见 [TODO.md](TODO.md)。

**2026-08-09 起**：本文件只保留「里程碑」区——一行一条（一致性测试强制），
功能细节住 `features/<NN>/devlog.md`。此前 17 条详细历史条目（2026-08-02 ~ 08-09）
已整体归档至 [archive/devlog-2026-08.md](archive/devlog-2026-08.md)，内容原样未改。

## 里程碑（2026-08-09 起的唯一合法追加区；一行一条，格式由 tests/test_docs_consistency.py 强制）

- 2026-08-02 harness 骨架落地——loop / 4 工具 / JSONL 落盘 / once 模式，`pai "任务"` 可真跑 → [archive](archive/devlog-2026-08.md)
- 2026-08-03 压缩地基与真实 usage 锚定（误差 1.3%）、框架对齐 pi、pai-viz 交付、冷眼评审消化、P0 五条清完 → [archive](archive/devlog-2026-08.md)
- 2026-08-09 模板与对账——features/_template 五件骨架、追认 00 基座档案、TODO 陈账 R#8/R#9 核销、STATUS 测试数对账 → [features/](features/README.md)
- 2026-08-09 R2#1 终裁「不入库」——knowledge/anna 与体系评审文件进 .gitignore，「失去版本控制备份」的代价如实记 → D#35
- 2026-08-09 knowledge 扩容——inbox.md 收件箱（准入唯一豁免区，首批 4 条）+ concepts/ 随 hooks-gates 首篇创建 → [knowledge/](../../knowledge/README.md)
- 2026-08-09 03-design-gate 立项→交付——方案未拍板不许改 src/tests 的 PreToolUse 门禁，注入验证真会拦 → [档案](features/03-20260809-design-gate/README.md)
- 2026-08-09 02-compaction brainstorm→spec 定稿——三问拍板完整存档，待批后进 plan → [档案](features/02-20260803-compaction/README.md)
- 2026-08-09 04-review-fixes 立项→交付——R3 全量代码梳理 15 条修 10，TDD 7 红转绿 92 passed → [档案](features/04-20260809-review-fixes/README.md)
- 2026-08-09 CLAUDE.md 新建——@AGENTS.md 自动加载入口（AGENTS 不进上下文本会话实证）；evals/playground 裁决不动 → CLAUDE.md
- 2026-08-09 借鉴 anna 三项——功能目录名带立项日期、拍板问答完整存档（02/03 回补全文）、evidence/ 按需规矩，94 passed → [features/](features/README.md)
- 2026-08-09 devlog 治理——里程碑区硬格式 + 一致性测试强制；宣布当天即被违反的长条目压缩至此（细节都在对应档案，未提交故不算改史）→ 本节即格式
- 2026-08-09 devlog 历史归档——17 条详细条目原样迁入 archive/devlog-2026-08.md，主文件 828→22 行 → [archive](archive/devlog-2026-08.md)
- 2026-08-09 decisions 加索引——36 条一行标题表+一致性测试钉住，正文一字未删；32-36 条错位节名归正 → [decisions.md](decisions.md)
- 2026-08-09 02-compaction spec 获批→plan 定稿——6 task 带全量代码严格 TDD，待提交现有改动后开 SDD 分支 → [plan](features/02-20260803-compaction/plan.md)
- 2026-08-09 02-compaction 阶段 1 主线交付——触发/切/摘/重建/熔断接进 loop，e2e 钉死单锚不可切的隐藏约束，113 passed → [档案](features/02-20260803-compaction/README.md)
- 2026-08-09 02-compaction SDD 六 task 完成——AnchorBook/find_cut_point/summarize/compact/熔断/接线全链 TDD，2 轮任务级修复（含 Critical：测试文件被重写当场恢复）→ [档案](features/02-20260803-compaction/README.md)
- 2026-08-09 02-compaction 终审通过——最强模型全分支审查 With fixes（Critical：摘要 usage 漏记预算，计划自带 bug）→ 修复波 4/4 复审 clean，115 passed；5 项 Minor 延后入 TODO → [档案](features/02-20260803-compaction/README.md)
- 2026-08-10 05-repl 立项→交付——阶段 2 前半程：事件流定型/双队列/中断到进程组/REPL/AskUser/状态行，8 task TDD，193 passed → [档案](features/05-20260810-repl/README.md)
- 2026-08-10 06-memory 立项→交付——阶段 3：PAI.md 三层加载/@导入/自动记忆索引/remember 写回/压缩后重注入，7 task TDD，235 passed → [档案](features/06-20260810-memory/README.md)
- 2026-08-10 两处小修——REPL 历史没读回 readline（↑ 一直是死的）、.env 按包位置而非 cwd 解析且无用户级兜底，244 passed → [TODO](TODO.md)
- 2026-08-10 05-repl 交付后五个补漏——readline 没读回/Ctrl+C 炸 REPL/后台进程不收割/write-edit 非原子/**测试污染用户 ~/.pai**，257 passed → [devlog](features/05-20260810-repl/devlog.md)
- 2026-08-10 立需求池——用户想法先记原话再定出路（升格立档案/降格进 TODO/划掉不做），playground 定为手工沙盒 → [需求池](需求池.md)
- 2026-08-10 STATUS 数字改由机器对账——同一处漂了三次（R#2 旧账），加 test_status_reports_the_current_test_count → [STATUS](STATUS.md)
- 2026-08-10 08-storage-layout 立项→交付——落盘布局对齐 CC：可读 slug、会话不再写当前工作目录、每条带 sessionId/cwd，顺带关掉 R#15，272 passed → [档案](features/08-20260810-storage-layout/README.md)
- 2026-08-10 07-permissions 立项→交付——阶段 4：三态求值/匹配下放给工具/bash 四坑/路径锚点/两层设置/外部 hook 全链 TDD，三条注入反证 + 自举跑通自己的 design_gate，329 passed → [档案](features/07-20260810-permissions/README.md)
- 2026-08-11 09-working-dir-boundary 立项→交付——补 feature 07 缺的**策略层**：默认兜底从常量 allow 改为工作目录边界函数、符号链接双路径、危险路径 bypass 免疫、权限模式四态、hook 改 fail-closed，7 task TDD + 四条注入验证，385 passed → [档案](features/09-20260810-working-dir-boundary/README.md)
- 2026-08-11 10-memory-recall 立项→交付——补 feature 06 缺的**召回层**：记忆改一事一文件带 frontmatter、MEMORY.md 由扫描结果重建（投影不是账本 D#55）、相对时间与陈旧警告、每轮侧查询选 ≤5 篇注入 system-reminder（usage 计进熔断、连续失败停用 D#56），7 task TDD，458 passed → [档案](features/10-20260811-memory-recall/README.md)
- 2026-08-11 11-streaming 立项——阶段 5 开工：档案建立状态「讨论中」、.active 切过去，待前置精读与 brainstorm 拍板 → [档案](features/11-20260811-streaming/README.md)
- 2026-08-11 11-streaming 前置精读——CC 流式执行器与能力标志走读 + OpenAI 兼容协议流式实测 6 探针，**推翻 TODO「usage 重复累加」的前提**、撞出 include_usage 空操作与中断无 usage 两条 → [档案](features/11-20260811-streaming/README.md)
- 2026-08-11 11-streaming brainstorm→spec 定稿——三问拍板完整存档：方案 B（流式+能力标志+保序并发）、默认开不加开关、两条 05 遗留都不进；待批后进 plan → [spec](features/11-20260811-streaming/spec.md)
- 2026-08-11 11-streaming plan 定稿——6 task 带全量代码严格 TDD（装配器/loop 流式/能力标志/调度器/接线/上屏），测试数字一律写下限，待批后开工 → [plan](features/11-20260811-streaming/plan.md)
- 2026-08-11 11-streaming 交付——阶段 5：主循环走流式（增量上屏/中断掐在流中途/unmetered 留痕）、工具能力标志进 @tool（收 input 的函数，默认全 False）、保序贪心分批并发、权限按批前置（D#57-59）；**反向对照推翻了 TODO 挂了很久的「usage 重复累加」必修前提**，6 task TDD，509 passed → [档案](features/11-20260811-streaming/README.md)
- 2026-08-11 12-tui 立项——阶段 2 后半程开工：档案建立状态「讨论中」、.active 切过去、分支 feat/12-tui，待前置精读（TUI 半程一篇笔记都没有）与 brainstorm 拍板 → [档案](features/12-20260811-tui/README.md)
- 2026-08-11 12-tui brainstorm→spec 定稿——前置精读补 TUI 半程两篇 + 反向对照撞出 6 条（含推翻 TODO「问题框接管输入焦点」的判断）；四问拍板：方案 A 底部活动区 / plan 不进本轮（改判 09）/ 对话框照抄 CC 抑制语义 / 干活时输入走 followUp → [spec](features/12-20260811-tui/spec.md)
- 2026-08-11 12-tui 交付——阶段 2 后半程：scrollback 在上、pai 接管的 dock 在下（方案 A，CC 主形态的最小复刻）；**输入归属由仲裁函数算出来**关掉 08 那条真实事故（提问期间敲 `!命令` 就是执行命令）、`/mode` + shift+tab 模式轮转、干活时打字进 followUp、并发按动作聚合可见、resize/非 tty 闸门/异常兜底/终端复原；8 task TDD + 真 pty 冒烟撞出「空闲每 100ms 白刷一帧」，680 passed → [档案](features/12-20260811-tui/README.md)
- 2026-08-11 12-tui 交付后修复波——用户真跑打回三条**离线全绿却坏掉**的（答案完全不上屏 / 权限框走老 asker 在 raw mode 下整个程序死住 / commit 不拆换行不折行导致满屏阶梯），全在**组件之间的接缝**上；另按用户要求补视觉层（logo 流光、青蓝配色、去 emoji、用户输入整行色带、工具输出默认折叠 + `^O` 展开），747 passed → [档案](features/12-20260811-tui/README.md)
- 2026-08-11 13-alt-screen 立项（未动工）——「工具结果能点 / transcript 能滚 / 像新开一个窗口」三条底下是同一个约束「谁拥有屏幕」，方案 A 结构上做不到；会推翻阶段 2 原则 2，故按规矩 7 另立档案，用户拍板「先键盘展开、alt-screen 单独立项」 → [档案](features/13-20260811-alt-screen/README.md)
- 2026-08-11 14-session-capture 立项→交付——`PAI_TUI_RECORD` 录下写给终端的字节（含尺寸与 resize）+ `pai-replay` 回放成 PNG，**让 AI 自己看得见界面**（feature 12 的四轮视觉修正全靠用户截图往返，我一次都没先发现）；终端模拟器从测试基建升为 `src/pai/tui/screen.py`，回放与测试共用同一份；第一次出图就撞了自己的字体路由假象，改成逐字查覆盖并主动报缺字，随后自己发现 `🔐` 违反 D#63，756 passed → [档案](features/14-20260811-session-capture/README.md)
- 2026-08-11 15-fake-provider 立项→交付——本地假 provider（真 HTTP 说 OpenAI 兼容协议、SSE 形状照实测）补完闭环：真 pai 进程 + 真 pty + 假模型 + 录制回放，**断言屏幕上有什么**；feature 12 被用户打回的三条各钉一条 e2e。三条注入反证第一轮只红了 1 条，另两条假绿——查清后得出「注入不对 / 断言不对 / 路径已不存在」三种情形要分开处理，769 passed → [档案](features/15-20260811-fake-provider/README.md)
- 2026-08-11 13-alt-screen 前置精读 + 反向对照（动工前）——补上 alt-screen 三篇笔记（pi 的 `tui-plan.md` 主体与 `tui-alt-screen.ts`、CC 的 alt-screen 全家、可迁移的终端协议层）；实测 iTerm2 + Terminal.app **推翻了 CC 源码里的一句注释**（重发 `?1049h` 不是 no-op、会清屏），并撞出 **DECRQM 在 Terminal.app 完全不可用且会污染测量**；另纠正 pai 自己对原则 2 原文的转述。鼠标那块因缺授权整块没测到，如实留手工清单，771 passed → [档案](features/13-20260811-alt-screen/README.md)
- 2026-08-11 13-alt-screen brainstorm→spec 定稿——候选被**重排成 2×2**（进 alt 的时机 × 要不要接管鼠标），六问拍板：常驻 alt + 键盘滚动、**不接管鼠标**（保住终端原生拖选复制）、退出不回吐只打一行提示、默认进 + settings 开关、搜索与 resume 各自单独立项；过程中被用户质疑推翻了我一条推荐（**CC 退出时确实不回吐、只打 resume 提示**，我把 pi 的做法当成两家的做法了），并纠正「原则 2 被整条推翻」的说法 → [spec](features/13-20260811-alt-screen/spec.md)
- 2026-08-11 13-alt-screen plan 定稿——7 task 严格 TDD（模拟器认备用屏 / Transcript 按宽度重渲染 / 滚动状态机 / 整屏帧 diff / 进出 alt 与开关 / 接线 / e2e），测试下限合计 ≥51；两个结构决定写进头部：**第一个 task 是扩终端模拟器**（不然录制回放与 5 条 e2e 当场失效、退回让用户截图），以及 `commit()` 两种落点的接缝定在 `renderer.keeps_transcript`（main-screen 路径逐字节不变） → [plan](features/13-20260811-alt-screen/plan.md)
- 2026-08-11 16-mouse-and-selection 立项→spec 定稿——13 交付后用户真跑撞到「滚轮穿透给终端、翻出旧会话残留」，查清 CC 只是多发了一串 `?1000h?1002h?1003h?1006h`（**差别不在谁滚得动，在事件归谁**）；四问拍板：一次做到位（滚轮+自写选区）/1003 照抄 CC/剪贴板 pbcopy 为主 OSC 52 兜底/点击展开进本轮。**拍板后两轮实测抓到三条决定性的**：一次滚动手势上百条（必须合并，142 这个数直接进验收）、**OSC 52 在本机静默写不进剪贴板**（我推荐的「只做 OSC 52」会交付一个静默失效的复制）、1002 与 1003 观测不到差别（1003 买不到 hover）；另发现 pai 能比 CC 简单一块——**选区锚在逻辑行号而非屏幕行号**，CC 的 scrolledOffAbove 那整块不需要 → [spec](features/16-20260811-mouse-and-selection/spec.md)
- 2026-08-11 16-mouse-and-selection plan 定稿——9 task 严格 TDD（SGR 解析/事件合并/滚轮/选区状态机/高亮/复制双路径/点击展开/生命周期/e2e），测试下限合计 ≥53；三个结构问题写进头部：`Key` 带负载而**编辑器无视它只是因为恰好没人写 else**（补测试钉住）、Transcript 缓存 key 要从 `width` 变 `(width, 展开态)`（**与 13「缓存 key 必须含宽度」是同一个坑的第二次**）、选区高亮必须套在截断之后 → [plan](features/16-20260811-mouse-and-selection/plan.md)
- 2026-08-11 16-mouse-and-selection 实现完 9 task 但**停在「实现中」**——滚轮/拖选复制/点击展开/输入框选区都通了（986 passed），交付前真跑打回 10 条修掉 9 条（**没有一条是离线测试能发现的**：生产路径提交的是不可展开条目、`button=35` 无按键移动被当拖动、松开被输入框吞掉、提示落在分隔线下面…）；剩一条**从后往前拖选不复制且卡顿**，离线两个方向都正常，定性为「真终端里事件一条一条到、`merge` 没机会生效 + 释放事件可能没送到」，按用户要求列 TODO 不修。另复议拍板：鼠标从 1003 降到 **1002**（D#67：CC 发 1003 是因为它要 hover，pai 不要） → [档案](features/16-20260811-mouse-and-selection/README.md)
- 2026-08-13 17-viz-flow 交付——pai-viz 从静态结构图升级为**运行时观察者**：新增观测流落盘（`core/trace.py`，14 种 harness 事件并排落 `<会话同名>.events.jsonl`，与不可再生的审计流分文件）、回合时间线（`viz/flow.py` 唯一一处分组配对，2s 游标轮询实时点亮，跨项目会话回放）、每处流转标代码位置可点击跳编辑器（工具 `file:line` 自省，节点/事件映射由测试防漂移）。页面纯观察无对话输入。参照 waku-agent 的**观测侧**机制骨架（游标/分组/点灯/扇出/容错/reveal），不借其交互侧。8 task 严格 TDD，1069 passed。**每个 task 在测试全绿后跑真数据/真浏览器又各抓出问题**：`!命令` 记录被误判「未完成」（3/8 假阳性）、新起 pai 换会话导致页面静默停更、全局工具注册表泄漏致单跑绿全跑红、观测流与审计流重影、字段撞名显示成 `bash → event`；其中 TUI 路径完全不落盘与 `kw["on_event"]` KeyError 打崩 TUI 两条**只有 pty e2e 与肉眼能发现**。用户当场纠正一处口径：各步 `prompt_tokens` 相加当「计费」没有意义（缓存命中便宜 50 倍），改为上下文峰值/未命中之和/输出之和三个「加起来有意义」的数 → [档案](features/17-20260812-viz-flow/README.md)
- 2026-08-13 18-steering-input 立项——给 steering 队列接真实输入源（改**已交付**的 12 拍板问 4「干活时打的字排队」，12 号档案冻结），设计依据取 CC 而非 pi：用户输入默认 `next`（中途注入）、系统消息才默认 `later`。五问已抛**未替用户选**（默认档 / followUp 留不留与显式路径 / all 还是 single / dock 两条队列怎么显示 / `/` 命令排不排除），主问的反方理由列了 5 条 pai 与 CC 的结构性差异（无 attachment 层、无 Esc 单独打断路径、只有两档而非三档、有 max_steps、CC 默认值是连同 UI 一起被验证的）；spec 另立一节记**前置缺陷**——单层 `for` + `continue` 把 `:283` 的 return 摆在 `:352` 的 steering poll 之前，模型某轮不调工具时队列永久卡死，接输入源之前必须先修 → [档案](features/18-20260813-steering-input/README.md)
- 2026-08-13 18-steering-input 立项→交付——排队消息通电：干活时打的字**本轮就注入**（改 feature 12 拍板问 4 的默认值，照 CC「人说话默认优先、机器说话默认等着」），followUp 队列删掉，pai 只剩**一条队列 + 两个注入出口**；`/`、`!` 与普通消息混装同一条队列，靠 `drain(where=...)` 谓词滤出注入之外、轮末逐条交客户端执行（CC 明文：slash 不能当文本发给模型）；注入后发 `SteeringInjected`，TUI transcript / `.events.jsonl` / viz 三处都看得见。**顺带修掉一条前置缺陷**：单层 `for`+`continue` 把 `:283` 的 return 摆在 `:352` 的 steering poll 之前，模型纯答话那轮（收尾轮通常如此）队列永久卡死——取「两个出口」而非改回双层循环，于是 `max_steps` 语义不动。七问拍板全程存档，其中**两问用户拒绝直接选、要求先核实 CC 源码**，各改写一条结论（CC 两个 drain 点都是批量 / CC 的 `next` 在纯答话轮次退化成新 query）。5+1 task 严格 TDD，1111 passed；e2e **两轮假绿**各记一条（假 provider 秒答导致「模型正在答」不存在、两行输入落进同一批 poll），补 `turn(delay=)` 与「等条件不等秒数」；交付前做注入反证——拆掉出口②后恰好 `2 failed, 4 passed`（红得精准）。取舍升格 D#68：**单队列取自 CC、第二出口取自 pi**，两家拒掉的那一半也写明 → [档案](features/18-20260813-steering-input/README.md)
