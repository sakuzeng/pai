# 官方文档覆盖图

- 来源：https://code.claude.com/docs/llms.txt （2026-08-09 查询，非全量枚举——新章节按需补行）
- 精读日期：2026-08-09（本表只登记归属，内容仍按需精读，禁止囤积式通读）
- pai 锚点：docs/dev/roadmap.md（各阶段「前置精读」是唯一权威触发点，本表是反向全景）

回答一个问题：官方文档讲的能力里，pai 要实践什么、放在哪个阶段、明确不做什么。

| 官方章节（/docs/zh-CN/…） | pai 归属 | 笔记 |
|---|---|---|
| context-window、costs | 阶段 1 压缩 | [context-management.md](context-management.md) ✓ |
| prompt-caching | 阶段 1（D#12/16 拍平 vs 原样发实测时读） | 未读 |
| interactive-mode | 阶段 2 REPL/TUI | [interactive-mode.md](interactive-mode.md) ✓ |
| memory | 阶段 3 记忆 | [memory.md](memory.md) ✓ |
| permissions、permission-modes | 阶段 4 权限 | 未读 |
| hooks、hooks-guide | 阶段 4 权限 | 未读 |
| skills | 阶段 6 | 未读 |
| mcp、mcp-quickstart | 阶段 6 | 未读 |
| sub-agents、agent-teams | **不做**——超精简边界；大输出隔离问题用 read_file 截断提示兜（TODO R#17） | — |
| checkpointing | **暂不做**——回滚/重演依赖会话树，等阶段 2 后按需评估 | — |
| settings、cli-reference、statusline 等产品配置类 | **不做**——产品面功能，非 harness 学习目标 | — |
| agent-sdk/* | **不做**——pai 本身就是在造这一层 | — |
