# pi 与 MCP：显式不做（反例 + 可抄的骨架）

- 来源：pi-mono `4c01c709`（2026-08-02）全树检索 + git 全历史；`packages/coding-agent/README.md`、`docs/usage.md`、`docs/extensions.md`、`packages/agent/src/agent-loop.ts`、`docs/rpc.md`。证据等级：可读源码（最高档）。
- 精读日期：2026-08-23（本篇由源码走读 agent 检索、本人复核整理）
- pai 锚点：features/29（MCP client 立案的候选形态之一就是「pi 式不做/延后」）、src/pai/core/tools/__init__.py（Tool 注册表——pi 证明了 MCP 该是灌注册表的 adapter）、src/pai/core/gate.py（统一 preflight——MCP 工具必过权限层的结构保证）
- 相关：[claude-mcp.md](claude-mcp.md)、[cc-mcp.md](cc-mcp.md)、[dsh-mcp.md](dsh-mcp.md)

## 结论：pi 没有 MCP client，也没有 MCP server——产品决策不是没做完

README 原文：*"No MCP. Build CLI tools with READMEs (see Skills), or build an extension
that adds MCP support."*（README.md:495，附作者博文链接）。git 全历史零 MCP 文件；
立场 2025-11-12 一次性钉死（commit `60e4fcf0` "State upfront: pi does not support MCP"）。
被删掉但留在历史里的理由三条：*"A 225-token README beats a 13,000-token MCP server
description"*（token 效率）、bash 管道可组合、*"No server processes, no protocol
complexity, just executables"*。

易误判点：`packages/protocol/` 的 `PROTOCOL_VERSION = 2` + CBOR framing 是
「远程 pi session」协议——方向相反（别人连 pi），与 MCP 无关。

## pi 的替代形态三层

1. 形态 A（官方首推）：CLI 工具 + README + Skills。零协议零进程管理，「schema」是
   一份 SKILL.md，「调用」是内置 bash。渐进披露（只有 name+description 常驻，
   正文按需 read）正是对「tools/list 全量塞上下文」的反制。
2. 形态 B：Extensions 进程内 `pi.registerTool()`——MCP 若要做就做在这层的 adapter。
   关键性质：运行时动态注册立即生效（等价 `tools/list_changed`）、
   `executionMode: "sequential"|"parallel"` 逐工具并发开关（server 不支持并发时用）、
   扩展可自带依赖（可以 depend on 官方 MCP SDK）。
3. 形态 C：`resources_discover` 钩子——扩展贡献本地 skill/prompt/theme 文件路径。
   粒度是本地文件不是 URI，与 MCP resources 只是形似。

## pi 已验证的骨架（MCP client 最容易做烂的那半边）

- 工具注册表与来源解耦：agent loop 只认一个 Tool 抽象，MCP 是灌表的 adapter——
  「有没有 MCP」对主循环透明。
- `prepareToolCall` 固定流水线（agent-loop.ts:599 附近）：查表 → 参数 shim →
  schema 校验 → `beforeToolCall` 统一 preflight（可 block 可改参）→ 查取消。
  权限层挂在注册表下游而非 adapter 内部，于是「MCP 工具过不过权限层」结构上
  必然过——pai 的 gate.py 同构，这条白拿。
- 错误一律转 `isError: true` 的 tool result 回喂模型，循环不断（与 pai
  「工具错误不 throw」的 AGENTS 架构约束逐字同款）。
- fail-closed：permission-gate 示例「无 UI 一律 block」——与 pai D#48
  （dontAsk 下 ask 降级 deny）同构。
- 进程生命周期契约（extensions.md:220）：*"Do not start background resources…
  from the factory. Defer… until session_start. Register an idempotent
  session_shutdown."*——直接可搬成 pai 的 MCP server 管理规则。
- 项目信任门禁：项目级 `.pi/` 资源未 trust 不加载，决策存 `~/.pi/agent/trust.json`，
  非交互模式走 `defaultProjectTrust`（默认忽略项目资源）——pai feature 28 的
  skills 信任门禁同族，MCP 项目级配置照搬。

## pi 的明确缺口（照 pi 形态做 MCP 必须自己补）

- 传输层全部（stdio spawn + JSON-RPC framing）。唯一相关经验是 docs/rpc.md 的
  血泪一句：*"strict LF-delimited JSONL... Do not use generic line readers like
  Node readline"*，以及 `output-guard.ts` 防 stdout 污染的思路。
- initialize 握手与版本协商——pi 自家协议是「精确匹配、不协商只拒绝」的极简，
  可作 pai v0 的省事选择。
- 通用工具超时：pi 没有（只有 bash 可选 timeout），跨进程的 MCP 必须补。
- 崩溃重连：pi 无此概念。走读 agent 的建议与 pi 气质一致：v0 不重连，server
  死了摘工具、后续调用回 isError 说明下线。
- resources/prompts/sampling/roots：v0 全不做并把「不做什么」写进立案文档——
  pi 把 No-MCP 写进 README Philosophy 段这个工程习惯本身值得抄。

## 对 pai 的启示

pi 在本子阶段是「反例 + 骨架」：传输层参考须另找（CC / dsh / 官方 python-sdk），
但它把两条最值钱的结构性结论先给了——MCP 是注册表 adapter 不是 loop 公民；
权限/错误/取消挂在注册表下游让 MCP 工具免费获得全部治理。渐进披露的账
（225 vs 13,000 token）是 pai 上下文预算设计的定量依据。
