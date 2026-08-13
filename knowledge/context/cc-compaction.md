# CC 压缩策略要点（指针）

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）`src/services/compact/`、`src/query.ts`；pi 侧深度走读见外部参照 3（本文不重复）
- 精读日期：2026-08-09
- pai 锚点：`src/pai/core/compaction.py`（roadmap 阶段 1）；关联决策 D#32/D#34

## pai 阶段 1 直接要用的结论

**CC 不是「满了就摘要」一招，是四级递进，从轻到重：**

1. **工具结果预算**（query.ts 内 `applyToolResultBudget`）：单条消息内工具结果总量超预算
   则内容替换成引用，状态可持久化以便 resume。
2. **microcompact**（`microCompact.ts`）：只清**白名单工具**（Read/Shell/Grep/Glob/
   WebSearch/WebFetch/Edit/Write 八个）的旧结果，替换为 `[Old tool result content cleared]`。
   按工具名选目标、按 tool_use_id 替换，不解析结果语义（清多少由 token 估算决定），
   因此与第 1 级正交。**性价比最高的一级**：这些工具可重放（文件还在磁盘上，
   命令可以再跑），清掉旧结果损失最小。
3. **autocompact**：接近 token 上限触发的完整摘要压缩。
4. **手动 /compact**：fork 一个 agent 生成摘要，写 compact 边界消息，然后
   postCompactCleanup + 重新注入附件（文件状态、agent 列表等）。

**对 pai 的含义**：

- pai 阶段 1 做的是第 3 级（autocompact）。第 2 级 microcompact 值得在阶段 1 之后
  评估——pai 的 4 个工具（bash/read_file/write_file/edit_file）恰好全部可重放，
  实现只需按 tool_call_id 替换内容，不用调模型，零成本。
- 切点约束两家一致的部分只有一条：**保留段不以孤儿 tool_result 开头**（否则 400）。
  pi 的 `findValidCutPoints` 只把 toolResult 排除在切点之外，**允许劈开一个 turn**
  （`isSplitTurn: true`，用 `findTurnStartIndex` 回记轮次起点）——单轮超过保留预算时
  仍能在轮内下刀。pai 选的是**更强**的约束：切点只落轮次边界（D#32，真实 usage 差值
  只能按轮次反推，粒度天然对齐）。代价：超长单轮无法压缩，届时需要兜底（已注记 D#32）。
- 压缩后的「读数空窗」是 pai 特有问题（锚定法假设 append-only）：压缩成功与否
  只认压缩后第一次真实 usage 回传（D#34），CC 无此问题因为它不用锚定法。
- CC 摘要保留清单（官方模拟器原文）：用户请求与意图、关键技术概念、检查/修改过的
  文件及重要代码片段、错误及修法、待办、当前工作。丢弃：完整工具输出、中间推理。
  这份清单可直接当 pai `summarize` 的 prompt 骨架。
