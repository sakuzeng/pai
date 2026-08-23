# 29 · devlog

## 2026-08-23 · 前置精读 + 动工前反向对照 + 立档

- 前置精读四篇落 knowledge/mcp/（官方 / pi / CC / dsh），登记 knowledge/README；
  roadmap 参照细目改正（「dsh docs/api-gateway.zh.md」线索实测是空的，真正的
  设计意图在 `.agents/notes/` 与包 README）。三家格局：pi 显式不做（git 全历史
  零 MCP 文件）、CC 全家桶、dsh Tools-only 最小桥但权限与预算两缺口。
- 动工前反向对照（evidence/）：手写 70 行零依赖 stdio MCP server 做探针，
  `claude -p --mcp-config --strict-mcp-config`（dynamic scope 零配置污染）真跑
  三场景——P1 全链与命名（tools/call 走 raw name；capabilities 出现
  `roots:{listChanged:true}`，与 2.1.88 源码的空对象对不上=版本漂移实据）、
  P2 isError 细节一字不差到模型、P3 连接失败告知模型的文档行为实测未复现。
  源码级对照收 dsh 八处文档-源码不符（D1-D8）。
- 拍板四问全 A（README「确认」）。

## 2026-08-23 · T1 协议层（红→绿）

- 红：`tests/test_mcp.py` 10 条 + `tests/fake_mcp_server.py`（探针血统，
  env 参数化 normal/die-after-init/die-after-list/slow-call/dirty-stdout/
  paginate 六形态）→ collection 红（`cannot import ... MCPSession`）。
- 绿：`core/mcp.py` 的 `MCPSession`——显式状态机（connecting/connected/
  failed/closed，刻意不抄 CC 的 memoize 隐式重连）、newline JSON-RPC、后台
  reader 线程按 id 配对、脏 stdout 行容忍、超时/进程死/协议错全走 MCPError、
  close 幂等 SIGTERM→SIGKILL。首跑 `1 failed, 9 passed`——die-after-init 死在
  发现期让 start() 直接失败（合理行为，测试场景改 die-after-list 钉「连上后死」，
  另补一条钉「发现期死 = start 失败」）→ `11 passed`。

## 2026-08-23 · T2 桥接层（红→绿）

- 红：8 条（命名/清洗/截断/结果映射/isError 转字符串/输出预算/撞名）→
  collection 红。
- 绿：`public_tool_name`（小写化归一 + 超长 sha256(`\0` 分隔)[:12] 兜底）、
  `_sanitize`（NFKC + 剥 Cf/Co/Cn——CC 防 HackerOne #3086545 同款）、
  `render_result`（text `\n` join、非 text 占位符、100k 字符预算）、
  `bridge_tools`（(server, raw) 存闭包不反解字符串；MCPError → `错误：` 字符串）。
  中途两红：hash 语义与 spec 不符（把 dsh 的「归一化有改动即 hash」也抄了，
  spec 拍的是 hash 只兜超长、撞名走跳过+warn——按 spec 改）；撞名测试夹具
  选的两个名归一化后差一个下划线根本不撞（改夹具）→ `19 passed`。

## 2026-08-23 · T3 配置与信任（红→绿）

- 红：5 条（两层项目赢/坏条目告警/坏 JSON 跳层/once 丢弃/对话框三态）→
  ImportError。
- 绿：`load_mcp_servers`（两层自读循 hooks.py 先例——项目层要单独过门禁，
  不能用 load_settings 预合并；name `^[a-z0-9_-]{1,32}$`、type 只认 stdio、
  timeout<1000 回默认）+ `apply_mcp_trust`（feature 28 模式推广，标记
  `mcp_trusted` 在项目身份目录）→ `24 passed`。

## 2026-08-23 · T4 装配与权限（红→绿）

- 红：6 条中 3 条真红（once 全链 / dontAsk 默认拒 / repl 并表）；3 条绿于到达
  如实标注——decide 两条钉的是既有求值链对无路径工具的行为（本来就 ask、
  fnmatch 本来就支持 `mcp__fake__*`），untrusted 那条在未接线时空洞地绿。
- 绿：`connect_configured_servers`（配置→门禁→连接失败隔离→桥接）+
  `close_all_mcp`；once.py 接线（并表后重过 visible_tools 让 deny 裸名生效、
  try/finally 关 session）；interactive.py 接线（装配期 asker 问信任；关闭挂
  atexit 而非 try/finally——REPL/TUI 多出口，大缩进不值，close 幂等 +
  进程生命周期 = 会话生命周期，取舍记注释）→ `30 passed`。

## 2026-08-23 · T5 loop 级 + e2e

- loop 级：REAL_TRAJECTORY 做底 + MCP 工具调用进上下文（AGENTS「真实轨迹
  输入」规约）——写下即绿（钉验收不钉新行为，如实记）。
- pty e2e `test_mcp_tool_reaches_model_through_real_process`：真 pai 进程 +
  真 fake_mcp_server 子进程 + fake provider——工具进请求工具集、结果回填、
  allow 规则放行不弹框。一次 NameError 假红（测试内漏 import Path）修正后
  `1 passed in 3.72s`。

## 2026-08-23 · T6 注入反证 + 全量

- 注入反证 1（掐断桥接：connect_configured_servers 直接返回空）→
  `2 failed`（once 全链 + repl 并表都红在工具缺席）。复原。
- 注入反证 2（门禁旁路：apply_mcp_trust 直接 return servers）→
  `2 failed`（untrusted 装配测试 + 门禁单测都红）。复原。
- `tests/test_mcp.py` 全绿 `31 passed`。
- 全量：`./test.sh` → `1339 passed, 3 deselected in 171.98s (0:02:51)`
  （交付前 1307）。

## 2026-08-23 · 交付前反向对照（真实回合）

- 真 DeepSeek 一跑即成：不点名工具，模型按 description 自主调
  `mcp__fake__echo_token({})`，暗号原样返回；项目级配置 + 信任标记 + allow
  规则 + finally 关闭全链兑现。会话落盘核验见
  [evidence](evidence/20260823-mcp交付前反向对照/说明.md)。
