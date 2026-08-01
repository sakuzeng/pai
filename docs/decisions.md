# 设计决策记录

每个阶段完成后追加一节：pi/Claude Code 怎么做的 → pai 怎么做的 → 为什么。这是面试话术的直接来源。

## 种子版（2026-08-02）

1. 工具异常在 Tool.run() 内转成字符串结果，loop 不感知。
   pi 在 loop 层 catch 后 createErrorToolResult；CC 在 executor 层。pai 收进 Tool 自身，理由：Python 里装饰器 + 方法边界最自然，且保证"任何调用路径"都不会漏（未来子 agent 直接调工具也安全）。
2. tool_call_id 配对由 loop 唯一负责，任何分支（未知工具、参数非法 JSON、执行异常）都必须回填一条 tool 消息。
   来源：CC query.ts 的孤儿 tool_result 防护——API 层面 tool_use 与 tool_result 必须严格成对，这是三个实现共同的硬约束。
3. max_steps 用 for 而不是 while True + 计数。
   mini-pi 没有步数上限；pi 用 maxIterations、CC 也有兜底。防的是模型永不收敛时烧钱。
4. 会话 JSONL 从第一天就有。
   pi 的 session 是 harness 核心；先落地最小版（append-only 每消息一行），阶段 1 compaction 时"原始数据不删只改视图"的架构才接得上。
5. 参数非法 JSON 不 crash，回填错误让模型重试。
   真实 provider 偶发输出坏 JSON；mini-pi 会直接 json.loads 崩掉。
