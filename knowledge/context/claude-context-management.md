# 官方文档精读：上下文管理与 compact

- 来源：https://code.claude.com/docs/zh-CN/context-window（上下文窗口交互模拟）、https://code.claude.com/docs/zh-CN/costs（减少令牌使用一节）
- 精读日期：2026-08-09
- pai 锚点：`src/pai/core/compaction.py`；关联决策 D#12/D#16（拍平 vs 原样发）、D#32/D#34

## 官方机制（产品视角，与源码走读互补）

上下文窗口的组成（200K 窗口的实测模拟数据）：系统提示 ~4200 token、自动记忆
MEMORY.md（只载前 200 行或 25KB，先到为准）~680、环境信息 ~280、MCP 工具默认延迟
加载只列名字 ~120、skills 只载一行描述 ~450、CLAUDE.md 全文。启动自动加载约占窗口
的一小部分，大头永远是对话消息与工具结果。

compact 行为：

- `/compact` 用一份结构化摘要替换整段对话。摘要保留：用户请求与意图、关键技术
  概念、检查/修改过的文件及重要代码片段、错误及修法、待办、当前工作。丢弃：完整
  工具输出、中间推理。模拟器按摘要 ≈ 被压内容的 12% 演示。
- 压缩后启动期自动加载的内容会重新注入（系统提示、CLAUDE.md、环境等），
  例外是 skills 描述列表——只有实际调用过的 skill 被保留。
  → 对 pai 的启示：`compact()` 后哪些东西要重建（system 消息、工具 schema）
  必须显式列清单，不能想当然「摘要替换对话」就完了。
- 支持自定义压缩指令：`/compact Focus on code samples` 或 CLAUDE.md 里写
  `# Compact instructions` 节。→ pai 的 `summarize` 可以从第一版就把「保留什么」
  做成参数而非硬编码 prompt。
- auto-compact 阈值（model-config 页查证 2026-08-10，关闭 R2 未核实项）：Sonnet 5
  的 1M 窗口「默认约 967K 令牌」时自动压缩，即预留 ~33K，可用
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 调整；200K 预算配置在该边界同样自动压缩。
  → 对照 pai：`reserve_tokens=16384` 约为 CC 预留量的一半，同一数量级
  （校准 TODO 的参照点之一，另一个是实测摘要 completion ≤1671，见 D#37）。

costs 页列出的省 token 手段（页面本身不做优先级排序，还包括模型选择、MCP 开销、
扩展思考等本表未列项）：任务间 `/clear`（陈旧上下文在之后每条消息上重复付费）、
委托 subagent 隔离大输出（context-window 页模拟器：子 agent 读 6100 token 文件，
主上下文只回来 420 token 摘要）、hooks 预处理（grep ERROR 后只回匹配行，万 token
降到百 token）、skills 按需加载替代 CLAUDE.md 常驻（CLAUDE.md 目标 200 行以下）。
按 pai 现状我的优先级（这是我的排序，非官方）：/clear 心智 > hooks 预处理 >
skills 按需——subagent 不做（超精简边界）。

## 与 pai 现状逐点对照

| 官方机制 | pai 现状 | 差距/决定 |
|---|---|---|
| auto-compact 阈值触发 | `should_compact` 已写未接 | 阶段 1 主线 |
| 摘要保留清单（六项） | `summarize` 未写 | 直接当 prompt 骨架用 |
| 压缩后重注入清单 | 无 | `compact()` 设计时显式列：system + 工具 schema 是 pai 仅有的两样 |
| 自定义压缩指令 | 无 | `summarize(instructions=...)` 参数化，低成本 |
| prompt caching 自动优化 | usage 透传已保住 `prompt_cache_hit_tokens` | D#12/16 的拍平 vs 原样发实测时要算缓存账（50 倍价差） |
| subagent 隔离大输出 | 无 subagent | 不做，超出精简边界；同类问题靠 read_file 截断提示（TODO R#17） |
| hooks 预处理省上下文 | 无 hooks | 阶段 4 权限钩子时一并考虑 |
