# feature 29 · plan（TDD 任务切分）

每个 task 先红后绿，红绿数字进 devlog。测试全离线：假 MCP server 是 tests/
内的零依赖 stdio 脚本（反向对照探针的血统），假 LLM 走 tests/fake_llm.py。

- T1 协议层：`tests/fake_mcp_server.py`（可参数化：正常/慢/死/isError/脏 stdout）
  + `core/mcp.py` 的 `MCPSession`——握手、发现（含 nextCursor 分页）、调用、
  超时、进程死、非 JSON 行容忍。红：模块不存在。
- T2 桥接：公开名归一化/超长 hash/撞名跳过、description Unicode 清洗 + 2048
  截断、结果映射（join/占位符/空）、输出 100k 字符预算、MCPError → 错误字符串。
- T3 配置与信任：`load_mcp_servers`（两层、项目赢、坏 JSON 告警、name 校验）
  + `mcp_trusted` 门禁三态（复用 28 的 apply 模式）。
- T4 装配：once/interactive 接线（连接、并表、退出关闭）；权限三条（dontAsk
  默认拒、`mcp__<server>__*` allow 放行、deny 优先）。
- T5 loop 级 + e2e：REAL_TRAJECTORY 底 + mcp 调用进上下文；pty e2e（真 pai +
  fake provider + 真假 MCP server 子进程）。
- T6 交付收尾：注入反证（掐断桥接/门禁各一）、全量回归、decisions 升格
  （schema 同源破例 + 拍板要点）、留痕四件套、交付前反向对照真跑。
