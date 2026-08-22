# 25-skills（阶段 6 子阶段一：按需加载的能力扩展）
状态：已交付
分支：feat/25-skills（全部：前置精读四篇笔记与立档随分支首提交入库，spec/plan/TDD 实现均在此分支）
流程：superpowers 全链路（roadmap 阶段 6 既定），spec/plan 待定——拍板后产出

## 需求

给 pai 一套 skills：用户把「反复要粘贴的程序性指令」写成 `SKILL.md`（frontmatter
description + markdown 正文）放进约定目录，pai 启动时扫描出轻量索引注入上下文，
模型在任务匹配时按需加载完整正文——description 常驻、正文按需，这是渐进式披露，
与阶段 3 记忆（指令常驻全文注入）互补。出处：roadmap 阶段 6 + R4#A4
（评审定向：照 pi 最小形态 + dsh 三层数据结构思想）。MCP client 是另一个子阶段，
本轮不做；E4 ToolSource seam 明确等 MCP 立项，本轮不碰。

用户给定的三条设计约束（2026-08-22 开工指示原话摘记）：

1. feature 22 开好的 system prompt 装配缝（`build_system_prompt`）就是给注入
   skill 目录准备的，装配层加段即可，不要再动 loop；
2. 验收标准必须含「压缩后已加载的 skill 仍有效」（CC 踩过的坑，R4#A4 点名）；
3. pai 的 core/memory.py 扫描逻辑几乎就是 skill loader 的骨架，优先复用。

验收标准（怎么算做完，spec 阶段细化）：

- 约定目录下的 SKILL.md 被扫描进索引，description 进上下文，正文不进；
- 模型能按需加载某个 skill 的完整正文并照办（真实轨迹夹具 + 交付前真实回合验证）;
- 压缩后已加载的 skill 仍有效（离线测试钉死：压缩发生后模型仍持有或能重获正文）;
- disable-model-invocation 的 skill 不进模型可见索引；
- 索引有预算上限（pi 没有，是三家唯一裸奔的——CC/dsh 都证明了要设）；
- `./test.sh` 全绿，至少一条测试拿真实会话轨迹当输入。

## 候选方案与确认

三家参照的完整机制见 knowledge/skills/ 四篇（[claude](../../../../knowledge/skills/claude-skills.md) /
[pi](../../../../knowledge/skills/pi-skills.md) / [cc](../../../../knowledge/skills/cc-skills.md) /
[dsh](../../../../knowledge/skills/dsh-skills.md)）。关键分歧：三家在「模型怎么加载正文」上
三分——pi 复用 read 工具（零新增工具）、CC 的 Skill 工具展开 prompt、dsh 的 skill
工具返回 tool result。动工前反向对照（[evidence](evidence/20260822-skills动工前反向对照/说明.md)）
证实 R4#A4 的「零新增工具」只是 pi 一家的形态。

### 方案 A · pi 最小形态 + 两条已证坑的补丁

扫描（复用 memory.py 骨架：目录发现 + frontmatter 窗口解析）→
`build_system_prompt` 加一段 `<available_skills>`（name/description/location，
XML 转义）→ 模型用现有 read_file 加载正文，零新增工具。补两条 pi 没有而
CC/dsh 都有的：索引预算上限（超了先截 description 再退名字）与压缩后重挂
（记录已加载 skill，压缩后重注入，机制对齐 D#42 指令重注入的既有先例）。

- 好处：最小改动面（装配层 + 一个新模块 + 压缩挂钩），不动 loop，不动工具集；
  索引住 system prompt，压缩天然摘不掉；location 给了路径，read_file 语义自然。
- 代价：加载靠模型自觉（pi 自认 models don't always do this），DeepSeek 服从性
  没有保证——反向对照阶段必须真跑验证；「已加载」的判定要从 tool_result 里
  认 read_file 读了 skill 路径，比专用工具的判定间接。

### 方案 B · 专用 skill 工具（dsh 缩水版）

新增 `skill(name)` 工具：索引仍经装配缝注入（只给 name + description，不给路径），
模型调工具拿正文（tool result 形态）。压缩后重挂同方案 A。

- 好处：加载动作显式可观测（ToolStart/ToolEnd 事件、状态行、viz 全部白拿），
  「已加载哪些 skill」就是工具调用记录，重挂判定直接；对服从性差的模型，
  工具 schema 里的描述比 system prompt 里的一句指导语更有强制力。
- 代价：多一个工具（schema 进每次请求）；工具集从「通用原语」混入「框架私有
  动作」；与「零新增工具」的评审定向偏离，须记 decisions。

### 确认

2026-08-22 用户一轮拍板四问（AskUserQuestion，选项原文与选择如下；理由栏用户未附文字，
只记选择本身，不代拟）：

问 1：skills 的「加载正文」动作用什么形态？三家三分（evidence 已证实 R4#A4 说的
「零新增工具」只是 pi 一家的做法）：pi 让模型用 read 工具自己读；CC 用 Skill 工具把
正文展开进对话；dsh 用专用 skill 工具把正文作为 tool result 返回。pai 的风险点：
pi 文档自认「模型不总会去 read」，而 pai 用 DeepSeek，服从性更无保证。
- 候选 A·read 形态（AI 推荐）：R4#A4 既定方向；索引给出 SKILL.md 路径，模型用现有
  read_file 加载，零新增工具、不动工具集。服从性风险留给交付前反向对照真跑验证。
- 候选 B·专用 skill 工具：dsh 缩水版，新增 skill(name) 工具返回正文。加载动作显式
  可观测（事件/状态行/viz 白拿），「已加载哪些」就是工具调用记录；代价是多一个框架
  私有工具，且偏离 R4#A4 定向须记 decisions。
选择：B·专用 skill 工具。（偏离 R4#A4 定向，升格 [D#71](../../decisions.md)。）

问 2：验收标准「压缩后已加载的 skill 仍有效」怎么实现？CC 的解法是压缩时把已调用过
的 skill 正文重新附加（单个截 5k token、共享 25k 预算、最近优先）；pai 已有同构先例
D#42（压缩后指令从磁盘重读重注入）。
- 候选 A·重挂正文（AI 推荐）：对齐 CC 机制与 D#42 先例，记录已加载 skill，压缩重建时
  从磁盘重读正文重注入（带预算上限）。「仍有效」= 正文真的还在上下文里，离线可测。
- 候选 B·只保证可重获：索引住 system prompt 天然免疫，正文摘掉就摘掉，靠模型自己
  重新加载——「仍有效」退化成「能再加载」，与 CC 踩坑前的状态相同。
选择：A·重挂正文。

问 3：skills 目录布局与同名冲突语义？三家互不相同：dsh 项目赢用户、CC 个人赢项目、
pi 先到先得。
- 候选 A·两层+项目赢（AI 推荐）：扫 `~/.pai/skills/` 与 `<项目>/.pai/skills/`，
  同名项目级赢（dsh 语义，与 pai 记忆分层「cwd 在后、后来居上」直觉一致）。
- 候选 B·两层+用户赢：CC 语义（个人配置用户主动装、更可信）。
- 候选 C·v1 只做项目级：无冲突问题，但「跨项目复用」核心场景缺席。
选择：A·两层+项目赢。

问 4：要不要给用户显式调用通道？pi 有 /skill:name（展开成 `<skill>` 块注入，参数追加），
也是它对「模型不总自觉」的出路。
- 候选 A·带 /skill 命令（AI 推荐）：v1 就做，展开正文注入对话、参数追加；同时是测试
  与真实使用中确定性加载的通道。走现有 `/` 命令 + 队列注入，不动 loop。
- 候选 B·v1 不带：范围更小，但强制加载没有出路，反向对照的风险敞口更大。
选择：A·带 /skill 命令。

## 结果与总结

7 个 task 全部交付（详细红→绿见 [devlog.md](devlog.md)）：

- `core/paths.py` 两级 skills 路径 + `core/skills.py`（扫描/目录渲染/重挂预算）+
  `core/tools/skill.py`（工具 + 注入点）+ once/interactive/TUI 三路装配 +
  `/skill` 命令 + pty e2e 一条（含注入反证：掐断目录注入即红）。
- 压缩后重挂搭 D#42 指令重注入的车，loop 零改动（用户约束 1 兑现）；
  扫描复用 memory 的 frontmatter 解析（约束 3 兑现）；验收标准「压缩后已加载
  skill 仍有效」由拿 REAL_TRAJECTORY 真实轨迹做底的 loop 级测试钉死（约束 2 兑现）。
- 升格两条 decisions：[D#71](../../decisions.md)（工具形态，偏离 R4#A4 的
  「零新增工具」定向——动工前反向对照证实那只是 pi 一家的形态）、
  [D#72](../../decisions.md)（同名冲突项目赢，dsh 语义）。
- 测试：`./test.sh` → 1291 passed, 3 deselected（交付前 1242）。修出的真 bug 两个：
  `LoadedSkills` 用 time.time() 排序在同一毫秒内并列、截断提示语不计入单篇预算
  导致最近一篇永远装不进总预算。
- 交付前反向对照（真实回合）见 [evidence/20260822-skills交付前反向对照/](evidence/20260822-skills交付前反向对照/说明.md)。

## 遗留问题

六条，逐条已登记 [TODO](../../TODO.md)「feature 25（skills）遗留」：
项目级 skill 无信任门槛（1）、会话中途变更不生效（2）、四个预算常量未校准（3）、
frontmatter 扩展字段与参数替换未做（4）、递归发现与外部目录兼容未做（5）、
`~/.pai/skills/` 整目录读免问的刻意代价（6，记录性）。

## 用到的知识

- [knowledge/skills/claude-skills.md](../../../../knowledge/skills/claude-skills.md)（官方文档精读 + 2.1.239 真实探针）
- [knowledge/skills/pi-skills.md](../../../../knowledge/skills/pi-skills.md)（R4#A4 最小形态原型，含文档与源码不符两处）
- [knowledge/skills/cc-skills.md](../../../../knowledge/skills/cc-skills.md)（列表预算 + 压缩重挂 5k/25k 的机制出处）
- [knowledge/skills/dsh-skills.md](../../../../knowledge/skills/dsh-skills.md)（三层数据结构、digest 目录替换、rank 优先级）
- [evidence/20260822-skills动工前反向对照/](evidence/20260822-skills动工前反向对照/说明.md)（三条文档 vs 实测出入）
