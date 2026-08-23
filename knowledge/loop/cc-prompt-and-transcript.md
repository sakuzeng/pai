# CC 的 system prompt 装配与落盘收口：两个「唯一入口」

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `src/constants/prompts.ts`（914，`getSystemPrompt` / `getSessionSpecificGuidanceSection` /
  `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`）、`src/utils/sessionStorage.ts`（5105，
  `recordTranscript` / `insertMessageChain` / `shouldSkipPersistence`）、
  `src/QueryEngine.ts`（`recordTranscript` 的 8 处调用点）（符号名检索，反编译行号会漂）
- 精读日期：2026-08-22
- pai 锚点：`src/pai/core/loop.py`（`build_system_prompt` / `_record`）、
  `src/pai/core/session.py`（`replay_messages`）、
  `docs/dev/features/22-20260822-system-prompt-assembly`、
  `docs/dev/features/23-20260822-model-visible-is-recorded`
- 相关：[cc-loop.md](cc-loop.md)（循环结构，本篇不重复）

两个机制一句话：prompt 是装配层按实际工具算出来的，落盘是全 QueryEngine
只有一个入口的。features/22、23 各按其中一半对齐。

---

## 一、getSystemPrompt：装配层函数，不是常量

`getSystemPrompt(tools, model, additionalWorkingDirectories, mcpClients)` 是
async 装配函数，返回分段数组（Anthropic 的 system 收块数组）。三个可迁移点：

1. 指导语按「有没有这个工具」条件化，不是干列名字。
   `enabledTools = new Set(tools.map(_ => _.name))`，然后
   `hasAskUserQuestionTool ? 「不理解拒绝原因就去问」 : null`、
   `hasAgentTool ? 子代理指导 : null`。工具的 schema 与描述走 API 的 tools
   参数，prompt 里只放「怎么用它们协作」的指导。
2. 静态/动态分界护缓存前缀。`SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 之前是全局
   可缓存的静态段；会话相关的条件段全部压到边界之后——注释明说每个放前面的
   运行时开关会把前缀哈希裂成 2^N 个变体（PR #24490/#24171 同类 bug）。
   对 pai 的对应约束：生成结果在会话内必须逐字稳定（84~91% 缓存命中率就
   押在这上面）。
3. 环境信息（cwd/日期/模型）是 prompt 的一段（`computeSimpleEnvInfo`），
   不是散在别处。pai 未做（R4#E2 只开了缝），skills 阶段随装配层加段。

pai 的取形（features/22 拍板）：`build_system_prompt(tools)` 纯函数 +
`run_agent(system_prompt=None)` 兼容缝；OpenAI 兼容协议 system 是单字符串，
分段数组不抄，join 即可。

## 二、recordTranscript：落盘只有一个入口，且幂等

`recordTranscript(messages)` 是 QueryEngine 全部约 8 处落盘的唯一入口，
每次传当前完整 messages。函数内部：

1. 按消息 uuid 对已落盘集合（`getSessionMessages`）去重，只追加增量——
   调用方不需要知道「哪些是新的」，随时全量调用都收敛。
2. 顺手串 `parentUuid` 链（`--resume` / 分支重开的地基）。
3. 压缩后 messagesToKeep 出现在新 summary 之后，有专门的前缀跳过逻辑
   （靠 uuid 才能识别「旧消息换了位置」）。
4. 持久化开关收口在 `shouldSkipPersistence()`（test 环境 /
   `--no-session-persistence` / 保留期为 0），append 与 materialize 共用同一个
   守卫——绕过守卫的写入路径被注释点名过（`appendEntryToFile` 不走
   per-entry 检查）。

可迁移的拆解：「唯一收口」与「按身份幂等」是两件事。前者不需要消息有身份
（pai 的 `_record` 已对齐）；后者依赖 uuid（pai 消息还没有身份字段，
归 R4#A1 会话格式改造——CC 处理压缩后重放全靠它，这也解释了 pai 的
`replay_messages` 为什么必须拒绝含 compaction 记录的会话而不是硬拼）。
