# CC 的 skills 机制走读（反编译源码）

- 来源：claude-code-source-code（反编译，版本 2.1.88）：`src/tools/SkillTool/`（SkillTool.ts 1108 行 + prompt.ts + constants.ts）、`src/skills/loadSkillsDir.ts`（1086 行）、`src/utils/attachments.ts`（skill_listing 注入）、`src/services/compact/compact.ts`（压缩重挂）。⚠️ 行号会漂，检索符号名
- 精读日期：2026-08-22
- pai 锚点：features/25（验收标准「压缩后已加载 skill 仍有效」的机制出处）、src/pai/core/compaction.py
- 相关：[claude-skills.md](claude-skills.md)（官方文档描述的是 2.1.196+ 行为，与本篇 2.1.88 有系统性版本差——两篇对不上时先怀疑版本，再怀疑文档）

## 形态：skill 就是 command，加载是一次工具调用

CC 里 skill 与 slash command 是同一张表（`getCommands`），SkillTool（模型可见名 `Skill`）是模型侧的调用入口：`{skill: "name", args?: "…"}`。调用后两条执行路径：

- inline（默认）：command 展开成完整 prompt 注入当前对话，输出仅 `{success, commandName, allowedTools?, model?, status:"inline"}`——真正的「结果」是展开的 prompt 本身，模型接着处理它。
- forked（`context: fork`）：`prepareForkedCommandContext` 把正文变成子 agent 的 promptMessages，`runAgent` 跑完取结果文本回填，输出 `{status:"forked", agentId, result}`。skill 的 `effort` 合进 agent 定义、`model` 传给 runAgent。

工具 prompt 里的硬话值得抄：skill 匹配用户请求时是 BLOCKING REQUIREMENT（先调 Skill 再答）；见到 command 标签说明已加载、不要再调一遍（防重复加载的提示词层防线）。

## 目录注入：不在 system prompt，在 system-reminder attachment

与 pi 最大的结构差异。`attachments.ts` 的 skill_listing 路径：

- 每个 agent 维护 `sentSkillNames` 集合，只发增量——首次发全量（isInitial），会话中途新加载的（/reload-plugins 等）只发新增条目。
- resume 路径有抑制标志：上个进程已注入过的名单在 transcript 里，恢复后把当前全部标为已发、只播 resume 之后的增量——不重复烧 token。
- 预算：`SKILL_BUDGET_CONTEXT_PERCENT = 0.01`（上下文窗口的 1%，按 4 字符/token 折算，兜底 8,000 字符）；`SLASH_COMMAND_TOOL_CHAR_BUDGET` 环境变量可覆盖。
- 每条上限 `MAX_LISTING_DESC_CHARS = 250`（description + when_to_use 合并后截断）。⚠️ 官方文档说这个上限是 1,536（`skillListingMaxDescChars` 可配）——2.1.88 → 2.1.196+ 之间放宽了 6 倍并做成了设置项，版本漂移实据。
- 超预算的降级阶梯：先全文试 → 装不下则 bundled 永不截、其余按剩余预算均分每条描述长度 → 均分后不足 20 字符则非 bundled 只留名字。

## 压缩后重挂（pai 验收标准的机制出处）

`addInvokedSkill` 把每次调用的 skill（名字/路径/正文）记进进程态，按 agent 隔离；`conversationRecovery` 在 resume 时重登记。压缩时 `createSkillAttachmentIfNeeded`：

- 只取当前 agent 的已调用 skills，按 invokedAt 最近优先排序；
- 每个正文截 `POST_COMPACT_MAX_TOKENS_PER_SKILL = 5_000` token（保头部——setup/usage 通常在头部，注释原话）；
- 总预算 `POST_COMPACT_SKILLS_TOKEN_BUDGET = 25_000`，装不下的整条丢弃（不是再截短）；
- 打包成 `invoked_skills` attachment 附在压缩产物后。

两个常量与官方文档数字完全一致——文档与源码在这条上交叉验证通过。旁边还有同构的 plan 文件重挂与 plan-mode 重挂：「压缩会吞掉非消息态的常设指令、需要显式重挂」在 CC 里是一类问题的通用解法，pai 的 D#42 指令重注入是同一味药。

## 其他值得记的

- `loadSkillsDir.ts` 按目录发现 skill（`getSkillDirCommands` memoize + `clearSkillCaches` 失效 + `onDynamicSkillsLoaded` 回调 + `addSkillDirectories` 动态追加）——发现层与 command 表解耦，`skillChangeDetector.ts` 管实时变更。
- MCP prompt 与 MCP skill 有边界修补：只有 `loadedFrom === 'mcp'` 的进 SkillTool 可调集合，防模型猜名字调到不可发现的 MCP prompt。
- `maxResultSizeChars = 100_000`；Skill 工具一次只跑一个（展开的 prompt 要先被处理完）。
- 遥测里 skill 名按「内置/bundled/官方市场才记真名，第三方一律 custom」脱敏——名单是用户数据这个意识 pai 用不上，但值得知道。

## pai 视角

- pai 不抄 Skill 工具形态（R4#A4 定了 pi 最小形态），本篇要抄走的是两个数字性机制：列表预算（1% 窗口 + 每条上限 + 降级阶梯）与压缩重挂（5k/25k、最近优先、整条丢弃）。pai 的版本可以简化，但「没有预算」和「压缩后不管」都是被两家（CC 实装、官方文档背书）证过的坑。
- 增量注入（sentSkillNames + resume 抑制）依赖「消息一旦入 transcript 就还在」——pai 的压缩会改写历史，抄这条前要先回答「压缩后目录还在不在」；dsh 的 digest 方案（见 [dsh-skills.md](dsh-skills.md)）在这点上更自洽。
