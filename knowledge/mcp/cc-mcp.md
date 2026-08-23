# CC 的 MCP client 实现走读

- 来源：Claude Code 反编译源码 2.1.88（`src/services/mcp/{client,config,types,envExpansion,mcpStringUtils,normalization,useManageMCPConnections}.ts`、`src/tools/MCPTool/`、`src/utils/{permissions,mcpValidation,toolSearch,sanitization}.ts`）。证据等级：反编译源码——检索符号名不引行号，引用带版本 2.1.88；官方文档基线已到 2.1.2xx，行为条目会漂（见 [claude-mcp.md](claude-mcp.md) 的版本注记）。
- 精读日期：2026-08-23（由源码走读 agent 检索、本人复核整理）
- pai 锚点：features/29、src/pai/core/tools/__init__.py（Tool 注册表与 schema 同源约束的破例点）、src/pai/core/permissions.py（mcp 规则 specifier）、src/pai/core/boundary.py（项目级 server 审批与 feature 28 信任门禁同族）
- 相关：[claude-mcp.md](claude-mcp.md)、[pi-mcp.md](pi-mcp.md)、[dsh-mcp.md](dsh-mcp.md)

## 配置与 scope

- schema（types.ts）：stdio 的 `type` 可省略（向后兼容）、`command` 非空 + `args`/`env`；http/sse 是 `type` 字面量 + `url` + `headers`/`headersHelper`/`oauth`。文件形状 `{"mcpServers": {name: config}}`。
- scope 七种（local/user/project/dynamic/enterprise/claudeai/managed）；合并 `Object.assign({}, plugin, user, project(approved), local)`——后写覆盖、整条不合并字段；enterprise 存在则排他接管。project 层从 cwd 向上逐层收 `.mcp.json`（近者优先）。
- env 展开 `${VAR}` / `${VAR:-default}`，缺失记 warning 不阻断（envExpansion.ts）。
- 项目级审批（utils.ts `getProjectMcpServerStatus`）：pending/approved/rejected 三态，未批准的根本不进连接集合。安全注释原文：*"a repo should not be able to accept the bypass dialog on behalf of users"*——仓库自己不能替用户点头，与 pai feature 28 信任标记「不进仓库」同一直觉。

## 工具接入（tools/list 之后的五道工序）

1. capability 门禁：`if (!client.capabilities?.tools) return []`；
2. Unicode 清洗 `recursivelySanitizeUnicode`（NFKC + 剥 `\p{Cf}\p{Co}\p{Cn}`）——动机是真实攻击（HackerOne #3086545：Unicode Tag 字符往 description 里藏指令）；
3. description 截 `MAX_MCP_DESCRIPTION_LENGTH = 2048`（注释：OpenAPI 生成的 server 见过 15-60KB 的 description）；server instructions 同限；
4. schema 原样透传（不做清洗规整——根级组合器的拍平是 2.1.195 才加的，2.1.88 没有）；
5. annotations 映射能力位：`readOnlyHint → isReadOnly/isConcurrencySafe`、`destructiveHint`、`openWorldHint`——与 pai 的 `capabilities_for` 逐位对上。
单 server 失败隔离：整个 fetch try/catch 兜底返回空列表。

## 命名与权限

- `mcp__<server>__<tool>`，归一化 `[^a-zA-Z0-9_-] → _`；反解用 `split('__')`，自认缺陷：server 名含 `__` 会解析错——pai 该在注册表存 (server, tool) 二元组，前缀名只做展示。
- 权限：MCPTool.checkPermissions 回 passthrough → 流水线末步转 ask。默认档位就是 ask。规则 specifier 三形态：`mcp__server`（server 级）、`mcp__server__*`（等价通配）、`mcp__server__tool`；明确禁止括号内容（不像 `Bash(git:*)`）。deny/ask/bypass 的免疫顺序与内置工具同一条链。

## 生命周期与健壮性

- 启动即批量连（本地并发 3、远程并发 20），不阻塞 UI；`connectToServer` 用 memoize 当连接池、`onclose` 删缓存实现惰性重连——作者自留 TODO 怀疑这个 memoize 复杂度不值。pai 结论：用显式 `MCPSession` 状态机（disconnected/connecting/connected/needs_auth/failed），不抄隐式控制流。
- 握手：capabilities 声明 `{roots: {}, elicitation: {}}`（空对象声明——发 `{form:{},url:{}}` 会弄崩 Java SDK server 的零字段类）；协议版本交给官方 SDK，不自行钉版本。roots 回 `file://<getOriginalCwd()>`。
- 超时四件套（2.1.88 数值）：`MCP_TIMEOUT` 连接 30s；`MCP_TOOL_TIMEOUT` 默认 100_000_000ms（≈27.8h，注释 effectively infinite）；`MCP_REQUEST_TIMEOUT_MS = 60000` 仅 HTTP POST（GET 是长连 SSE 豁免）；工具调用同时下发 SDK timeout 和自己的 `Promise.race`（SDK 内部超时在 SSE 中断时不可靠）。
- 重连：远程指数退避 1s×2^n 封顶 30s、最多 5 次；stdio/sdk 不自动重连（onclose 清缓存 → 下次调用重 spawn）。SDK 只发 onerror 不发 onclose 的缝隙：连续 3 次终端错误后手动 close 掉 transport 并拒掉挂起的 promise——否则 callTool 永久挂起。
- stdio 关闭：close() 只发 abort 信号，Docker 类 server 要显式 SIGINT → 100ms → SIGTERM，50ms 探活、600ms failsafe。
- notifications：tools/prompts/resources 的 listChanged 都处理（删 memo 缓存重取）。

## 结果回填与输出预算

- content 分派：text 原样；image 缩放后 base64 块；audio/blob 一律落盘回文件路径文本（*"Replaces the old behavior of dumping raw base64 into the context"*）；resource 文本带 `[Resource from <server> at <uri>]` 前缀。
- `isError: true` → 抛 McpToolCallError（不混进正常 tool_result）；401 → McpAuthError；session 过期（404+-32001）清缓存重试 1 次；用户 Esc → 静默返回。
- 输出预算：默认 25k token（env 可调），超限落盘 + 返回文件路径与 `inferCompactSchema` 类型签名 + 分页提示语；含图片时退回截断。粗估（0.5 系数、图片 1600 token）过半才调 counting API。
- 没有工具数量硬上限——控制全靠 token 预算 + 延迟加载（MCP 工具默认全 deferred，`ENABLE_TOOL_SEARCH` 四档，auto 阈值 10% 窗口）。

## 对 pai 的启示（走读结论 + 本人复核）

抄的（最小形态，估几百行 Python）：配置形状 `mcpServers` + env 展开；`mcp__s__t` 命名但注册表存二元组；capability 门禁 + 单 server 失败隔离；2048 描述截断 + 25k 输出预算（生产校准过的初值）；isError/协议错/超时统一收敛成工具失败经既有「错误回填」路径给模型；blob 落盘不进上下文；权限 specifier 三形态默认 ask；项目级 server 显式批准（feature 28 信任门禁直接推广）；stdio 关闭信号升级；连接 30s + 工具超时给有限默认值（27.8h 的「无限」对 pai 是挂死源）。

不碰的（CC 规模产物）：OAuth 全家桶（auth.ts 2465 行）、七层 scope 与企业排他、ToolSearch 的 beta 依赖（思想可用朴素等价物：延迟到用时注入）、ws/ide/proxy 五种额外传输、elicitation/channels、遥测包装。Unicode 清洗 20 行属例外——外部 description 是不可信输入这一课性价比极高，建议抄。
