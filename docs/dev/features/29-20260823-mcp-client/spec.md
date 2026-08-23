# feature 29 · MCP client — spec

拍板依据：README「候选方案与确认」四问全 A（Tools only + 仅 stdio / 手写
JSON-RPC / 默认 ask + server 级规则 / settings.json `mcpServers` 字段）。
参照笔记 knowledge/mcp/ 四篇；动工前反向对照 evidence 三探针。

## 1. 协议层（`core/mcp.py`，新模块）

新模块只依赖标准库（subprocess/json/threading）+ `core/paths`/`core/skills` 的
信任标记模式；不 import loop 内部（AGENTS 架构约束）。

- `MCPServerConfig`（frozen dataclass）：`name`、`command`、`args`、`env`、
  `timeout_ms`（每调用，默认 60_000，取 dsh 默认；<1000 忽略回默认，照 CC 语义）、
  `source`（`"user" | "project"`）。name 合法性 `^[a-z0-9_-]{1,32}$`
  （dsh 模式收紧到小写——公开名要与权限规则的小写化约定对齐），不合法
  warn + 跳过该 server（fail loud 不拒载别家）。
- `MCPSession`：显式状态机（`connecting/connected/failed/closed`），不抄 CC 的
  memoize 隐式控制流（其作者自留 TODO 的那处）。
  - `start()`：spawn 子进程（`stderr=PIPE` 单独排走不进 UI；env = 进程 env +
    config.env 覆盖）；发 `initialize`（`clientInfo: pai`、
    `capabilities: {}`——空对象，dsh 同款：协议层杜绝 server 反向发起）；
    收 result 后发 `notifications/initialized`；再 `tools/list`（不处理分页
    cursor 之外的情况：有 `nextCursor` 就继续拉，drain 完为止）。
    连接/发现整体超时 `MCP_CONNECT_TIMEOUT_MS = 10_000`（自定，CC 是 30s——
    pai 本地 stdio 场景 10s 足够，常量旁注明未校准）。
  - 传输：newline-delimited JSON-RPC。写：`json.dumps + "\n"` 后 flush；读：
    后台线程逐行 `readline`，按 `id` 配对挂起的请求（dict + Event）；
    非 JSON 行丢弃计数（server 往 stdout 打日志是常见事故，不能炸）。
  - `call_tool(raw_name, args, timeout_ms)`：`tools/call`，超时或进程死 →
    抛 `MCPError`（带原因）；`isError: true` → 同样抛 `MCPError`（错误细节 =
    content 的 text 拼接）——**在协议层是异常，到工具层转字符串**（见 §2）。
  - `close()`：先 `terminate()`（SIGTERM），0.5s 不退 `kill()`（SIGKILL）。
    CC 的 SIGINT→SIGTERM 升级是 Docker 场景，pai v1 本地脚本 SIGTERM 起步够，
    理由记注释。幂等（pi 的 shutdown 契约）。
  - 不重连（拍板问 1 的范围内）：进程死后 session 置 `failed`，后续 `call_tool`
    立刻抛「server 已退出」——工具层回填给模型（pi 式「摘除胜过半吊子重连」）。

## 2. 工具桥接（`core/mcp.py` 内，产出 pai 的 `Tool`）

- 公开名：`mcp__{server}__{raw}` 全小写化后 `[^a-z0-9_-]` → `_`；超 64 字符
  截断 + `sha256(f"{server}\0{raw}")[:12]` 兜底（dsh 命名五不变式，`\0` 防拼接
  歧义）。(server, raw) 存在 Tool 闭包里，调用走 raw name——绝不从公开名反解
  字符串（CC 的 `split('__')` 缺陷引以为戒）。公开名撞名（归一化后）：后者
  跳过 + warn。
- description：Unicode 清洗（NFKC + 剥 Cf/Co/Cn 类别——CC 防 HackerOne
  #3086545 的 20 行，外部 description 是不可信输入）后截 2048 字符
  （`MAX_MCP_DESC_CHARS`，CC 同值）。
- schema：`inputSchema` 清洗（同 Unicode 处理）后原样作 `Tool.parameters`——
  这是 @tool 装饰器「schema 与代码同源」约束的显式破例，升格 decisions。
- execute：包一层把 `MCPError` 转 `"错误：..."` 字符串返回（pai「工具错误不
  throw」架构约束——协议层异常收敛在桥接层，loop 永远看到字符串）。
- 结果映射：content 数组里 text 块 `"\n"` join（dsh 教训：join('') 丢块间界）；
  image/audio/resource 等非 text 块 → 占位符一行（`[image: <mime>，已丢弃]`，
  不落盘——落盘记遗留）；全空 → `（<tool> 无文本输出）`。
- 输出预算：`MAX_MCP_OUTPUT_CHARS = 100_000`（CC 25k token × 4 字符换算，
  未实测校准，注明来源）；超限截断 + 一行提示（不做 CC 的落盘+类型签名，记遗留）。
- 能力声明：不声明 read_only/concurrency_safe（未声明 = False = 串行执行，
  外部工具当不安全处理正确）；无 get_path 无豁免 → 兜底 ask（拍板问 3 正解）。

## 3. 配置与信任（拍板问 4 + 28 门禁推广）

- `settings.json` 的 `mcpServers` 段：`{"mcpServers": {"<name>": {"command":
  "...", "args": [...], "env": {...}, "timeout": 60000}}}`（字段名与 CC/生态
  一致；`type` 字段可省或 `"stdio"`，其它值 warn 跳过）。
- 读两层（循 hooks.py 自读两层的先例，不用 load_settings 的预合并——项目层
  要单独过门禁）：用户级 `~/.pai/settings.json` 直接可用；项目级
  `<cwd>/.pai/settings.json` 的 mcpServers 过信任门禁（28 模式）：标记文件
  `~/.pai/projects/<slug>/mcp_trusted`；interactive 首遇未信任时用装配期 asker
  问一次（精确选中「信任」才持久化），once 无人可问 → 跳过 + warn 指路。
  同名项目级赢（与 settings 合并语义、skills D#72 一致）。
- 坏 JSON/坏字段：warn + 该层/该条跳过，pai 照常起（启动路径不崩，同 skills）。

## 4. 装配（once + interactive，loop 零改动）

- 装配期：读配置 → 过信任门禁 → 逐 server `MCPSession.start()`（串行，v1 不做
  并发连接；单 server 失败 warn + 跳过，不影响别家——CC 的失败隔离）→ 桥接出
  Tool 列表 → 并入 `tools` dict（在 `visible_tools` 过滤之后并入、之后再算
  system prompt——deny 裸名规则对 MCP 工具照常生效需注意求值处：并入后统一再
  过一次 `visible_tools`）。
- 退出：once 在 `run_agent` 返回后 finally 关闭全部 session；interactive 在
  REPL/TUI 退出路径关闭。中途死进程不重连（§1）。
- 连接失败告知模型：v1 不注入失败说明（反向对照 P3 证明 CC 文档的该行为
  实测未复现，无可抄的已验证形态）；失败只 warn 给用户。记遗留。

## 5. 权限（拍板问 3，零引擎改动）

- MCP 工具无 get_path 无豁免 → `_boundary_fallback`「未声明路径语义 → ask」
  ——默认 ask 即 CC 语义；once/dontAsk 下降级 deny，须 allow 规则（与 CC
  非交互 `--allowedTools` 同构，evidence P1 实证）。
- server 级放行写法：`allow: ["mcp__<server>__*"]`（`Rule.matches_tool` 的
  fnmatch 已支持 glob，零改动）；单工具 `mcp__<server>__<tool>`。文档与测试
  钉住这两形态。deny/ask 同理。

## 6. 验收标准（对 README 的细化）

1. 协议：假 server（tests 内零依赖 stdio 脚本，反向对照探针的血统）握手/
   发现/调用/超时/isError/进程死各有单测；
2. 桥接：命名（归一化/超长 hash/撞名跳过）、description 清洗截断、结果映射
   （join/占位符/预算截断）、错误转字符串——单测钉死；
3. 配置与信任：两层合并项目赢、坏 JSON 告警跳过、项目级门禁三态
   （once 跳过+warn / interactive 信任持久化 / 拒绝不持久化）；
4. 装配：once 全链（fake LLM 调 mcp 工具拿到结果）、默认 ask 在 dontAsk 下
   拒绝、allow 规则 `mcp__<server>__*` 放行——装配级测试钉死；
5. loop 级：REAL_TRAJECTORY 真实轨迹做底 + mcp 工具调用进上下文（AGENTS
   「至少一条真实轨迹输入」规约）；
6. e2e：真 pai 进程（pty + fake provider）+ 真 stdio MCP server 子进程全链；
7. `./test.sh` 全绿；交付前反向对照真跑一个完整回合（真 DeepSeek 自主调
   MCP 工具）。

## 7. 非目标（v1 明确不做，逐条记遗留）

- HTTP/SSE/ws 传输、OAuth、headersHelper；
- resources / prompts / sampling / roots / elicitation / progress /
  list_changed（会话中途工具集变更与「REPL 中途改 skill 不生效」同族）；
- 重连与健康检查（pi 式「死了摘除」；dsh 的 uptime 预算重连设计已记笔记，
  真需要时抄）；
- 大输出落盘 + 类型签名（CC 形态）；非 text 内容落盘；
- `${VAR}` 环境变量展开；`.mcp.json` 生态文件兼容挂载；
- 工具搜索/延迟加载（ToolSearch——工具总数过一页才需要，roadmap 既定）。
