# dsh 的 MCP client 精读（mcp-client 插件）

- 来源：deepseek-harness pin `47f943859b`（2026-08-13）。源码 `packages/mcp/mcp-client/`（918 行源码 / 2393 行测试）；文档面：`.agents/notes/implemented/feature/2026-07-07-mcp-client-plugin.zh.md`（主 Agent Note）、`2026-08-06-mcp-client-auto-reconnect.zh.md`、包 README.zh.md。证据等级：第一方源码 + 第一方设计文档——但本次走读实证「文档说≠源码是」共八处（见末节），dsh 的官方文档档位不免检。
- 精读日期：2026-08-23（由源码走读 agent 检索、本人复核整理）
- pai 锚点：features/29、src/pai/core/tools/__init__.py（命名注册表）、src/pai/core/permissions.py（`mcp__*` 通配的教训）、knowledge/skills/dsh-skills.md（skills 有两级披露而 MCP 没有——同仓对照）
- 相关：[claude-mcp.md](claude-mcp.md)、[pi-mcp.md](pi-mcp.md)、[cc-mcp.md](cc-mcp.md)

前置警告：`docs/subsystems/` 60 个子系统里没有 mcp.md，roadmap 里「dsh docs/api-gateway.zh.md」这条线索是空的——真正的设计意图在 `.agents/notes/` 与包 README。918 行源码 / 2393 行测试 / 0 行子系统文档，这个比例本身就是 dsh 对 MCP 的定位声明：外围适配器，不是核心能力。

## 机制要点

- 传输只有 stdio 与 streamable-http 两种（无 SSE/ws/OAuth；http 只有静态 header）。两者在监督器眼里不对等：http transport 自带 SSE 恢复、不在重启范围内。stdio 的 env 过 `scrubbedParentEnv()`（剥 KEY/PASSWORD/SECRET/TOKEN 与 DSH_*）。
- 配置无 mcp.json 无分层：一个 server = cordis.yml 一行插件实例。`serverName` 是用户配置不是远端 `serverInfo.name`——*"远端名称是不可信输入、跨部署不唯一…不得静默重命名模型可见工具"*。名冲突加载期抛错（fail loud），不静默覆盖。默认不挂任何 server：stdio 由 SDK 直接 spawn、不经 `ctx.shell`，在沙箱策略之外——这是拒绝默认挂载的明确理由。
- 命名：`mcp__<serverName>__<rawName>`，64 字符 `[A-Za-z0-9_-]` 上限，超限/非法退化为截断 + `sha256("<server>\0<raw>")[:12]`（`\0` 防 `(a,b_c)/(a_b,c)` 撞哈希）。杀手论证：微软调查 1470 个 server 有 775 个工具名冲突、`search` 出现在 32 个 server；且裸名方案会「添加不相关 server 时静默重命名既有工具，对话中途让会话历史与权限规则失效」。
- 代（generation）隔离重连：每次重连全新 transport+Client（SDK 的 Protocol 终身绑一个 transport）；`isCurrent` 栅栏让过时代回调全部惰性。退避 500ms×2^n 封顶 30s、最多 10 次、无抖动；预算按 uptime 重置（≥maxDelayMs 在线才清零）——按「连接成功」重置会让崩溃循环的 server 每周期洗白预算变成重启风暴。失败代必须等 transport 确认关闭才进退避，5s 等不到就彻底停——宁可停也不许两个子进程重叠。故障期间不注销工具（防 schema 前缀双重失效抖动），预算耗尽才注销。
- 调用：不用 SDK 高层 `callTool/listTools`，走裸 `request()`——SDK 的 per-page output-validator 缓存会预校验桥接层不支持的契约（工程情报，见不符 D4）。参数非对象兜底成 `{}`（让 server 报「缺参数」这种模型能学的错）。每调用超时 60s 默认；没传 onprogress → 无 resetTimeoutOnProgress，流式长任务照样 60s 被砍；initialize/tools/list 无自定超时落 SDK 默认 60s（README 自认限制）。
- 结果：text 块 `\n` join（DeepSeek 序列化器 `join('')` 会丢块间边界——正确性缺陷）；image/audio/resource 降级为占位符文本；`isError` → throw 交注册表错误路径（content 压扁成 message，structuredContent 丢弃）；outputSchema 声明了却不回 structuredContent → INVALID_TOOL_OUTPUT（测试钉死）。
- MCP Tasks（2025-11-25 规范）显式拒绝（throw），但两份文档都没记——用户只会撞到运行时英文错误。

## 权限与上下文成本（dsh 的两个缺口，pai 的超车点）

- 权限：MCP 工具不过任何审批/policy——`ToolDefinition` 没有权限字段，mcp-client 只依赖 `ctx.tools` 一个服务，默认无条件放行。Agent Note 三次拿「`mcp__*` 策略匹配模式」论证前缀选择，但 `ToolRestriction` 是精确名 Set、全仓库无权限通配实现——用「未来能力」论证当下决策、记录成「已具备」（不符 D6）。skills 有 isModelInvocable 双重检查，MCP 侧零对应——MCP 是绕过 skills 门禁的旁路。
- 上下文：全量平铺——schema 与 description 原样透传（*"垃圾进垃圾出；这是服务器作者的责任，不是桥接的"*），inputSchema 连子集校验都不过，无目录预算、无按需展开。skills 侧的两级披露（500 字目录 + 按需加载）没有移植过来。成本被显式接受（「描述与 JSON Schema 在 token 中占主导，限定符换稳定标识」）。README 的「模型体验 / Token 影响 / KV Cache 影响」三段式写作纪律值得抄。

## 砍掉的规范面（全集差）

Resources/Prompts：延后，判据原文——*"Resources 需要 harness 侧的机制来决定何时注入内容（系统提示词？按需？模型触发？）。Prompts 需要 harness 尚不具备的「提示词模板」概念。Tools 是高价值、低风险的起点。"* Sampling/Roots/Elicitation/Completions/Logging/Progress：零提及零实现（握手 `capabilities: {}` 一行决定——服务器协议层就知道不能反向发起）。Server 角色：ACP 已覆盖，不重复。ping：无（靠 onclose 探活，对 http 即无探活）。

## 文档 vs 源码八处不符（pai 反向对照素材，编号沿走读报告）

D1 image 块：Note 说「丢弃 + logger.warn」，源码是占位符文本且不碰 logger（README 对）。D2 isError：Note 说映射成 `{content, isError:true}`，源码是 throw 压扁（README 对）——错误结果保不保结构是真实设计选择点。D3 取消方法名：Note 写 `$/cancelRequest`（那是 LSP），MCP 是 `notifications/cancelled`——文档单方面事实错误。D4 高层 API：两份文档都说用 `client.callTool/listTools`，源码走裸 request（文档双错，修复后没跟）。D5 Note 的 Config 代码块漏 `failOnStartupError`/`reconnect`（正文提了、代码块没回填——代码块比正文更易腐坏）。D6 `mcp__*` 通配（见上）。D7 MCP Tasks 显式拒绝无文档出口。D8 outputSchema/structuredContent 整块 Note 缺失（后加功能，Note 是决策时点快照不更新）。另有一条无法证伪：Note 称 MCP 工具名可 128 字符含 `.`——仓库内无佐证，存疑待查规范。

元结论：Agent Note 是决策快照刻意不更新、README 是活文档——分层本身值得抄，但三个病要防：代码块腐坏、未来能力记成已具备、显式拒绝不出口到用户文档。

## 对 pai 的启示

1. 最小交付面 = Tools only，且把「不做什么」连判据一起写进立案（「协议能力在自家架构里没有归属者时就不到动工时候」）；sampling 这类连「延后」都值得显式写一句——dsh 零提及是反面教材。
2. 命名空间第一天强制、无 opt-out；注册表存 (server, raw) 二元组 + 确定性 hash 兜底，`\0` 分隔别省。
3. 权限门立案时就定：pai 已有 per-tool matcher 下放机制（feature 07），MCP 工具进 decide 链结构上免费——不要复制 dsh「前缀买了空头期权」的状态；与 skills 的 model_invocable 统一成一个「可调用性」谓词值得考虑。
4. 上下文预算超车：把 skills 的两级披露移植到 MCP（目录 name+截断 description，schema 按需），加 CC 的 2048/25k 两个数字。
5. 重连三件套直接抄：uptime 重置预算、等关闭再退避否则彻底停、故障期不注销工具；pai 多 server 场景补 jitter（dsh 没做）。
6. 包 SDK 前先验证高层 API 的缓存/校验副作用，预留裸 RPC 降级口（D4 的教训对 python mcp SDK 同样成立——pai 若手写 JSON-RPC 则天然免疫）。
