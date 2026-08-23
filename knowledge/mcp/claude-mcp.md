# Claude Code 官方 MCP 文档精读

- 来源：https://code.claude.com/docs/zh-CN/mcp（官方文档，抓取于 2026-08-23；行为条目大量标注引入版本 v2.1.1xx~2.1.2xx，引用带版本）
- 精读日期：2026-08-23
- pai 锚点：features/29（MCP client 子阶段）、src/pai/core/tools/__init__.py（REGISTRY 与 schema 同源约束——MCP 是第一个「schema 来自外部」的工具源，E4 ToolSource seam 的兑现时刻）、src/pai/core/permissions.py（mcp 工具名进规则的形态）、docs/dev/roadmap.md 阶段 6
- 相关：[pi-mcp.md](pi-mcp.md)、[cc-mcp.md](cc-mcp.md)、[dsh-mcp.md](dsh-mcp.md)

## 传输层四种

- stdio：本地进程，`claude mcp add <name> -- <command> [args...]`（`--` 分隔自家选项与 server 命令）。server 环境里注入 `CLAUDE_PROJECT_DIR`（稳定项目根，中途 add-dir 不变）。
- HTTP：远程推荐形态；JSON `type` 收 `http`，`streamable-http` 是别名（MCP 规范用后者，抄来的配置免改）。有 `url` 没 `type` 的条目按配置错误跳过并报错（v2.1.202 前报的是误导性的 `command: expected string`——文档自己记版本漂移）。
- SSE：已弃用（deprecated），仍支持。
- WebSocket：双向推送场景；不支持 OAuth 与 `--transport` 标志，只能 headers 认证。

## 配置与 scope 三层

`.mcp.json` 结构：`{"mcpServers": {"<name>": {type, command/args/env | url/headers, timeout, alwaysLoad, oauth…}}}`。env 扩展 `${VAR}` / `${VAR:-default}`；缺变量无默认值 → 字面 `${VAR}` 保留 + 警告，配置照加载。

| scope | 位置 | 共享 | 备注 |
|---|---|---|---|
| local（默认） | `~/.claude.json` 按项目路径分桶 | 否 | 旧版本叫 project |
| project | 项目根 `.mcp.json` | 检入版本控制 | 使用前逐个批准（安全） |
| user | `~/.claude.json` | 否 | 旧版本叫 global |

同名优先级 local > project > user > 插件 > claude.ai connectors；整条覆盖，字段不跨层合并。

项目级信任链（对 pai 的 skills 信任门禁 D#28 是同族问题）：`.mcp.json` 的 server 使用前提示批准（`claude mcp reset-project-choices` 重置）；v2.1.196 起批准记录只从「未检入仓库的设置文件」读，且要先过工作区信任对话框——克隆下来的仓库不能自己批准自己的 server（检入的 `enableAllProjectMcpServers` 在不受信任目录被忽略）。

## 工具接入与命名

- 工具名 `mcp__<server>__<tool>`；插件捆绑的是 `mcp__plugin_<plugin>_<server>__<tool>`。权限规则 / hooks / allowed-tools 都用全名。
- 保留 server 名单：`workspace`、`claude-in-chrome`、`computer-use` 等，撞名跳过并警告。
- 根级 `anyOf/oneOf/allOf` 的输入 schema API 不收：v2.1.195 起拍平成单对象 + 描述里注明参数分组（server 端要自己再校验组合）；更早版本直接跳过该工具。
- 动态更新：支持 `list_changed` 通知（tools/prompts/resources 都会刷新）。

## 超时与预算（数字全在这，pai 立案的对照物）

- 启动超时：`MCP_TIMEOUT`（毫秒，如 10000）。
- 工具执行超时：`MCP_TOOL_TIMEOUT`，默认约 28 小时（！）；每 server `timeout` 字段（毫秒，<1000 忽略）覆盖之。HTTP/SSE/connector 另有每请求首字节计时器 60s。
- 空闲超时（v2.1.187+）：无响应且无进度通知即中止——HTTP 系默认 5 分钟、stdio 默认 30 分钟；`CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` 可调、0 关闭。
- 输出预算：单次工具输出 >10,000 token 警告（阈值固定）；默认上限 25,000 token（`MAX_MCP_OUTPUT_TOKENS` 可调）；server 可按工具声明 `_meta["anthropic/maxResultSizeChars"]`（≤500,000 字符硬顶）；超阈值的结果落盘、对话里换成文件引用。

## 重连与失败面

- HTTP/SSE 断连自动重连：指数退避 1s 起步翻倍、最多 5 次，失败标记后 `/mcp` 手动重试；stdio 是本地进程不自动重连。
- 初连瞬时错误（5xx/拒连/超时）重试 3 次（v2.1.121+）；认证/404 不重试。连接成功后的发现请求（tools/list 等）也重试 3 次（v2.1.191+）。
- 失败可见性（v2.1.205 前的坑）：老版本不把连接失败告诉模型，模型表现得像那个 server 从未配置过——现在经 ToolSearch 结果报告失败。pai 视角：这就是「工具错误回填给模型」（AGENTS 架构约束）在连接层的对应物。

## 工具搜索（上下文成本的官方解法）

默认启用：MCP 工具全部延迟加载，会话启动只带工具名 + server instructions，模型经 ToolSearch 按需发现；`ENABLE_TOOL_SEARCH=auto[:N]` 改为阈值模式（工具集占上下文 <10% 就全量预载）；`false` 全量预载。每 server `alwaysLoad: true` 豁免（代价：阻塞启动等它连上，上限 5s）。工具描述与 server instructions 各截 2KB。依赖 `tool_reference` 块的模型支持（Sonnet 4.5+）。

## 权限与审批

- 组织可对 connector 工具设 ask/blocked：ask 每次提示且任何 allow 规则/模式都跳不过、dontAsk 模式下直接拒绝；blocked 直接从工具列表滤掉。
- server 可按工具声明 `_meta["anthropic/requiresUserInteraction"]: true`（v2.1.199+）：每次调用必须真人批准，acceptEdits/bypassPermissions 都不豁免，dontAsk 下拒绝——与 pai 的 dontAsk「ask 降级为 deny」（D#48）同构。

## resources / prompts / elicitation / roots

- resources：`@server:protocol://path` 引用，取回作为附件注入；有 list/read 工具配套。
- prompts：`/mcp__server__promptname [args]` 展开注入对话（与 pai /skill 的展开注入同形）。
- elicitation：server 中途要结构化输入，表单或 URL 两种模式弹给用户。
- roots/list：用「启动目录 + additionalDirectories」回答（v2.1.203+，之前只回启动目录），变更发 `notifications/roots/list_changed`——CC 把自己的工作目录边界喂给 server 自律，不是强制。

## OAuth（远程 server，pai v1 大概率不做，记形态）

401/403 标记待认证 → `/mcp` 或 `claude mcp login <name>` 走浏览器流程；令牌刷新失败重试一次（v2.1.206 语义修正）；`oauth.scopes` 固定请求范围；动态头 `headersHelper`（任意 shell 命令，10s 超时，项目/local 级须过工作区信任才跑）。

## 对 pai 的直接输入

1. 三层数字（启动/执行/空闲超时 + 输出 token 预算）是 pai 立案时的现成对照物；28 小时的默认执行超时说明真正干活的是空闲超时与首字节计时器。
2. 项目级 server 的信任链与 pai feature 28 的 skills 信任门禁同族——pai 的 MCP 若做项目级配置，信任标记可复用同一套（`skills_trusted` 的模式推广）。
3. 工具搜索是「工具多了才需要」的官方印证（roadmap 顺带工具 ToolSearch 的定位没错）；pai v1 工具个位数，全量注入即可，但输出 token 上限（25k 档）应当从第一天就有——它防的是单次回填炸上下文，与工具数量无关。
4. schema 拍平与「server 端自己再校验」提醒：外部 schema 不可信，pai 接入时要有 schema 清洗层（@tool 装饰器同源约束的边界在 MCP 处失效，须记 decisions）。
