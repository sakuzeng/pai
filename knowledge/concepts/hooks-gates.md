# hooks 与工具调用门禁

- 来源：CC 反编译源码（外部参照 6）`src/utils/hooks/`；官方 hooks 章节未精读（归属见 [../claude-docs/map.md](../claude-docs/map.md)，阶段 4 前置）；anna 实践见 anna/gates.md（本地不入库）
- 精读日期：2026-08-09（概念整理，非逐行走读；同日门禁落地后更新锚点）
- pai 锚点：**已落地** `guards/design_gate.py` + `.claude/settings.json`（工作区自身的方案门禁，档案见 docs/dev/features/03-20260809-design-gate/）；pai 产品侧的权限层在 roadmap 阶段 4，挂点对应 pi 的 `beforeToolCall` / `afterToolCall`

## 概念

hook = 在 agent 生命周期的固定点执行外部命令/检查的挂点。CC 有 26 个事件，
对 pai 有意义的核心是四个：

- **PreToolUse**（工具调用前）——可返回 allow / deny / ask，**门禁的落点**
- **PostToolUse**（调用后）——记录与审计的落点（如 anna 的 read_log）
- **UserPromptSubmit** / **Stop**——输入预处理与收尾校验

## 门禁模式（为什么它重要）

把「先讨论再动手」这类提示词约束降级到**确定性层**的机制载体就是 PreToolUse：
命中受保护路径 → 用代码判定过程产物是否齐备 → deny（缺什么告诉模型，让它自己补）
或 ask（必须真人拍板的那一个节点）。三条铁律来自 anna 实战（详见 anna/gates.md）：

1. deny 模型可自救绕过，ask 不可伪造——ask 只用在刀刃上；
2. 记录与判定职责分离，记录器永不打断会话；
3. 门禁自己必须带测试 + 退出码三态（通过/不通过/**没检查**）。

**deny 之后的问答回路**（硬约束与软引导的接力）：deny 只硬拦「改代码」这一步，
拒绝理由（reason 文本）作为工具结果回到模型上下文，**引导**它走合法路径——
调 AskUserQuestion（选项式弹窗，用户选择作为工具结果返回）或纯对话把候选讲给用户。
拿到拍板后模型写确认块、改状态字段（档案在 docs/ 下不受门禁管，刻意的：
文档路通、代码路锁），再重试原操作即放行。边界：「去问」本身仍是提示词层，
模型可伪造确认块（留 diff 痕）；要让「问」也不可伪造，用 PreToolUse 的第三种
返回值 `ask`（宿主弹权限框，必须真人点）——anna 只在「方案齐备、只差拍板」
一个节点用它，pai 门禁 v1 未用，留作升级。另一已知旁路（R3#9）：hook 只匹配
Edit 类工具，Bash 重定向写文件可绕过——不拦（误伤太大），如实声明靠审查兜底。

## pai 已落地的实例（2026-08-09，工作区层）

`guards/design_gate.py`：PreToolUse 拦 Edit/Write 于 `src/`/`tests/`，读
`features/.active` → 档案「状态：」行，未到「已拍板」即 deny。判定链路：
**改代码的钥匙（状态字段）只能从讨论流程长出来**——deny 理由给出的唯一合法路径是
「≥2 候选 → 用户拍板 → 写确认块 → 改状态」。落地时修正 anna 三短板：
decide() 纯函数 + 10 条 pytest（注入已知错误验证真会拦）、`.active` 指针不硬编码
任务路径、`!` 前缀显式放行留痕。注意分层：这是**开发 pai 的工作区**的门禁
（harness 的 harness）；pai 产品自身的权限层是下节的阶段 4，二者机制同构、层次不同。

## pai 怎么用（阶段 4 的设计输入）

- 挂点：loop 的 `before_tool_call`（对应 pi 的 `beforeToolCall`，返回 block+reason 即拦截）——
  权限不进 loop 本体，长在钩子上。
- 先做 allow / ask / deny 三态规则 + 规则语义下放给工具解释（CC 的做法）；
  hooks 作为用户可配置的扩展（跑外部命令）是其后的增量，不是第一步。
- 对照：pi 无 hooks 系统，只留钩子扩展点——「库把权限留给扩展点，产品内置多层权限」。
