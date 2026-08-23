# 29-mcp-client（阶段 6 子阶段二：MCP client）
状态：已交付
分支：feat/29-mcp-client（前置精读四篇笔记、动工前反向对照与立档随本分支入库）
流程：superpowers 全链路（roadmap 阶段 6 既定），spec/plan 拍板后产出

## 需求

给 pai 一个 MCP client：用户把外部 MCP server 写进配置，pai 启动时连接、把
server 的工具桥接进自己的工具注册表，模型像调内置工具一样调它们——阶段 6
「按需加载的能力扩展」的后半程（skills 是自带说明书的指令扩展，MCP 是带协议的
工具扩展）。出处：roadmap 阶段 6。

前置精读四篇已落 knowledge/mcp/（[官方](../../../../knowledge/mcp/claude-mcp.md) /
[pi](../../../../knowledge/mcp/pi-mcp.md) / [cc](../../../../knowledge/mcp/cc-mcp.md) /
[dsh](../../../../knowledge/mcp/dsh-mcp.md)）；动工前反向对照
（[evidence](evidence/20260823-mcp动工前反向对照/说明.md)）三条真实探针 +
源码级对照。三家格局：pi 显式不做（反例+骨架）、CC 全家桶（七层 scope/OAuth/
延迟加载）、dsh 最小桥（Tools only，918 行源码，但权限与上下文预算两个缺口）。

验收标准（怎么算做完，spec 阶段细化）：

- 配置一个 stdio MCP server 后，其工具出现在模型工具集（`mcp__<server>__<tool>`
  命名），模型调用可拿到结果（真实轨迹夹具 + 交付前反向对照真跑）；
- server 起不来 / 中途死 / 返回 isError / 超时，各自的失败面可见且不崩 loop
  （工具错误回填的架构约束延伸到连接层）；
- MCP 工具过权限层（decide 链），项目级 server 配置过信任门禁（feature 28 推广）；
- 上下文与输出有预算（description 截断 + 单次输出字符上限——dsh 裸奔的两处，
  CC 的数字做初值）；
- `./test.sh` 全绿，不打真实网络/API 的离线测试（假 MCP server 走 tests/ 内实现）。

## 候选方案与确认

四个正交决策点，每问候选如下（推荐项基于三家对照与反向对照证据）：

### 问 1 · v1 范围：协议面砍到哪

- 候选 A·Tools only + 仅 stdio（推荐）：initialize / tools/list / tools/call /
  isError / 每调用超时；resources、prompts、sampling、roots、elicitation、
  notifications（含 list_changed）、HTTP 传输全部显式延后并记遗留。dsh 同款
  裁剪判据：「协议能力在自家架构里没有归属者时就不到动工时候」——pai 的
  prompts 归属者（/命令表）和 resources 归属者（@引用）都还没有对应机制。
- 候选 B·Tools + list_changed + HTTP：多两块——动态刷新与远程 server。代价：
  list_changed 要求会话中途改模型工具集（pai 装配期定死工具集的既有形态要动）；
  HTTP 引入长连接与重连语义（dsh 都把 http 排除在监督器重启之外）。

### 问 2 · 协议实现：手写 JSON-RPC vs 官方 python SDK

- 候选 A·手写（推荐）：stdio 的 newline-delimited JSON-RPC，client 侧就是
  initialize/tools/list/tools/call 四个请求 + id 配对 + 超时。反向对照的探针
  server 70 行已验证 server 侧同协议可行；dsh 的 D4 教训（SDK 高层 API 的隐式
  校验缓存咬人、被迫降级裸 request）说明包 SDK 也躲不开读协议。学习驱动项目
  的核心收益就在亲手写这层。代价：协议演进要自己跟（钉住协商到的
  protocolVersion，超出的能力一律不声明——capabilities 空对象，dsh 同款）。
- 候选 B·依赖官方 `mcp` SDK：协议细节托管，代价是引第一个重量级运行时依赖
  （pai 至今零第三方运行时依赖）、且 D4 类隐式行为要自己验证。

### 问 3 · 权限与信任：默认档位

- 候选 A·默认 ask + server 级规则 + 项目级配置过 28 门禁（推荐）：MCP 工具
  不声明路径语义，落 pai 既有兜底「未声明路径语义 → ask」——与 CC 的默认 ask
  同构，pai 结构上免费。规则 specifier 支持 `mcp__<server>`（server 级放行，
  matcher 下放实现）。项目级 server 配置复用 feature 28 的信任标记模式
  （`skills_trusted` 推广或并列 `mcp_trusted`）。连带后果如实声明：once/dontAsk
  下 MCP 工具默认被拒，须 allow 规则放行——与 CC 非交互要 `--allowedTools`
  同构（反向对照 P1 实证）。
- 候选 B·默认放行（dsh 现状）：接入即用零摩擦；代价是外部进程的工具无门槛
  进模型手里，dsh 敢这么做的前提（不默认挂载任何 server + 部署方自组 guard）
  pai 只有一半。

### 问 4 · 配置位置与形状

- 候选 A·pai settings.json 加 `mcpServers` 字段（推荐）：两层 settings
  （用户级/项目级）与合并、告警、信任链全部复用既有机制；形状抄事实标准
  `{"mcpServers": {name: {command,args,env}}}`（字段名与 CC/生态一致，
  `.mcp.json` 兼容挂载记遗留）。
- 候选 B·独立 `.pai/mcp.json`：与 CC 的 `.mcp.json` 更像，但 pai 要新开一条
  配置读取与分层合并路径，两套配置文件两套规矩。

### 确认

2026-08-23 用户一轮拍板四问（AskUserQuestion，问题与候选原文见上四节；
四问均选 A 即推荐项；理由栏用户未附文字，只记选择本身）：

问 1（v1 范围）：A·Tools only + 仅 stdio。resources/prompts/sampling/roots/
elicitation/list_changed/HTTP 显式延后记遗留。
问 2（协议实现）：A·手写 JSON-RPC（stdio newline-delimited；capabilities 空对象；
不引官方 SDK——D4 教训与学习价值双重理由）。
问 3（权限默认）：A·默认 ask + server 级规则。落既有兜底「未声明路径语义→ask」，
`mcp__<server>__*` 靠 Rule.matches_tool 的 fnmatch 语义零改动即得（比 CC 省、
补掉 dsh 缺口）；项目级配置过 feature 28 式信任门禁。once/dontAsk 下默认被拒、
须 allow 规则，与 CC 非交互 --allowedTools 同构（evidence P1 实证）。
问 4（配置位置）：A·settings.json 加 `mcpServers` 字段（用户/项目两层，
读法循 hooks.py 自读两层的先例——项目层要单独过信任门禁，不能用
load_settings 的预合并结果）。

设计细则见 [spec.md](spec.md)，任务切分见 [plan.md](plan.md)。

## 结果与总结

6 个 task 全部交付（详细红→绿见 [devlog.md](devlog.md)）：

- `core/mcp.py`（新模块，约 470 行）：`MCPSession` 显式状态机（手写 newline
  JSON-RPC、id 配对、脏 stdout 容忍、超时/进程死/isError 全收敛 MCPError、
  close 幂等）+ 桥接（`mcp__<server>__<tool>` 小写归一 + 超长 hash 兜底、
  (server, raw) 存闭包不反解、Unicode 清洗 + 2048 描述截断 + 100k 输出预算、
  MCPError → `错误：` 字符串——「工具错误不 throw」延伸到连接层）+ 配置
  （settings.json `mcpServers` 两层自读、项目赢、坏条目告警跳过）+ 信任门禁
  （feature 28 模式推广，`mcp_trusted` 标记）+ 装配辅助（失败隔离连接、
  幂等关闭）。
- once/interactive 接线：并表后重过 visible_tools（deny 裸名生效）；once
  try/finally 关闭、interactive atexit（多出口取舍记注释与遗留 7）。
- 权限零引擎改动：默认 ask 落既有兜底、`mcp__<server>__*` 靠 fnmatch 白拿
  ——dsh 的「空头期权」缺口在 pai 不存在。
- 测试 31 条（协议 11 / 桥接 8 / 配置信任 5 / 装配权限 6 / loop 级 1）+
  pty e2e 1 条（真 pai + 真 MCP 子进程全链）；注入反证两处各红各的（掐断
  桥接 / 门禁旁路）。全量 `./test.sh` → 1339 passed, 3 deselected
  （交付前 1307）。
- 升格 [D#74](../../decisions.md)（schema 同源约束的显式破例：清洗 + 截断后
  透传，破例范围只 bridge_tools 一处）。
- 交付前反向对照（真实回合）见 [evidence/20260823-mcp交付前反向对照/](evidence/20260823-mcp交付前反向对照/说明.md)。

## 遗留问题

八条，逐条已登记 [TODO](../../TODO.md)「feature 29（MCP client）遗留」：
HTTP/OAuth（1）、协议面其余能力（2）、重连（3）、大输出落盘与非文本（4）、
env 展开与生态兼容（5）、连接失败不告知模型（6）、atexit 关闭取舍（7，记录性）、
dirty-stdout 丢弃不可见（8）。

## 用到的知识

- [knowledge/mcp/claude-mcp.md](../../../../knowledge/mcp/claude-mcp.md)（官方全景与全部数字）
- [knowledge/mcp/pi-mcp.md](../../../../knowledge/mcp/pi-mcp.md)（不做的理由与可抄骨架）
- [knowledge/mcp/cc-mcp.md](../../../../knowledge/mcp/cc-mcp.md)（五道清洗工序、默认 ask、重连）
- [knowledge/mcp/dsh-mcp.md](../../../../knowledge/mcp/dsh-mcp.md)（Tools only 判据、命名不变式、两缺口）
- [evidence/20260823-mcp动工前反向对照/](evidence/20260823-mcp动工前反向对照/说明.md)（三探针 + 不符清单）
