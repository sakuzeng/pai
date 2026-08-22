# dsh 的 skills 子系统精读

- 来源：deepseek-harness pin `47f9438`（2026-08-13）：`docs/subsystems/skills.zh.md`（第一方文档）、`docs/capability-seams.zh.md`（`ctx.skills` 条目）、`docs/tool-catalog.zh.md`（`skill` 工具 schema）。本篇全部取自第一方文档（含文档内嵌的 type-equiv 类型与生成的 Cordis API 目录），未逐行走源码——按 D#69，dsh 文档更好不代表免于反向对照，pai 侧的反向对照见 features/25 evidence
- 精读日期：2026-08-22
- pai 锚点：features/25、roadmap 阶段 6 参照栏
- 相关：[claude-skills.md](claude-skills.md)、[pi-skills.md](pi-skills.md)、[cc-skills.md](cc-skills.md)

## 四件套切分（capability seam 的教科书案例）

skill 能力族四个包，职责一句话一个：

- `dsh-skill`（Service Definition，`ctx.skills`）：注册表——合并各提供方目录、缓存发现结果、按名加载正文；
- `dsh-skill-filesystem`（Provider）：本地目录扫描；
- `dsh-skill-badge`（可选 Provider）：随包 skill，交付 CLI 默认禁用；
- `dsh-tool-skill`（Consumer）：目录注入 + 面向模型的 `skill` 工具。

pai 不抄插件化，可拿的是这个切分本身：发现（provider）/合并与缓存（registry）/呈现与加载（consumer）三层各自能换。R4#A4 说的「三层数据结构（目录轻/正文重分离）」即：`SkillSummary`（name/description/whenToUse/调用策略/来源）→ `SkillCandidate`（+rank/locator/path/metadata）→ `SkillDefinition`（+content 正文）。摘要与候选不含正文，正文只在 `get()` 时按需读。

## 发现与优先级（skill-filesystem）

rank 顺序扫根目录：100 `<projectRoot>/.dsh/skills` → 200 `<projectRoot>/.agents/skills` → 300 `customSkillDirs` → 400 `<dshHome>/skills` → 500 `<agentsHome>/skills` → 600 bundled（配了才有）。项目根 = 含 `.git` 的最近祖先，找不到用 cwd。项目赢用户、配置的自定义目录插中间——与 CC 的「个人覆盖项目」方向相反，与 pi 的先到先得也不同，三家三种冲突语义。

- 身份：kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）；接受目录包 `<name>/SKILL.md` 与扁平 `<name>.md` 两种；明确不支持递归 `**/SKILL.md`（pi 支持递归，又一处分歧）。
- 调用策略：读 `disable-model-invocation` 与 `user-invocable` 两个 frontmatter 键，规范化成 `{modelInvocable, userInvocable}` 正向布尔对，省略默认 true；四种组合全保留（双 false = 只有受信调用方能拿）。任意其他 frontmatter 进 `metadata` 不进领域模型。
- watcher（Chokidar）盯根目录增删改；模型侧 `write`/`edit` 命中相关路径也同步失效目录。watcher 挂了只把观测标记为不完整，不隐藏可读候选。

## 目录注入与失效（tool-skill，与 CC/pi 的第三种形态）

- 首个观察到非空完整视图的 `agent/pre-step`，注入一条持久 user-role `<system-reminder>` 目录；只含排序后的 name + XML 转义的 description（description 上限 `catalogDescriptionMaxLength` 默认 500），不含正文、路径、来源、路由提示。
- 之后每个模型步骤前，对 `<available_skills>` 标签间的渲染结果算 digest，与最近一条仍可见的目录消息比对；变了就经 `agent.inject()` 追加一条完整替换目录（删光了也追加一条显式空目录）。不完整快照保留上一份可用视图。
- 压缩交互：如果压缩把历史目录消息全部隐藏，下一份完整快照会重新建立目录——目录住在会话历史里但有自愈路径。这是对 pai 验收标准「压缩后仍有效」在目录侧的第三种答案（pi：住 system prompt 天然免疫；CC：增量 attachment + resume 抑制；dsh：digest 比对 + 压缩后重发）。
- 正文侧：`skill({name})` 工具校验 kebab-case → 查目录 → `isModelInvocable` 拒无权 → 按调用方 cwd 重读完整定义 → 返回 `<skill_content name="…">` + `<skill_resources>` + `<skill_instructions>` 的工具结果。注册表不缓存正文，每次 `get()` 重读盘——「仅改正文会改变后续工具调用，而不会生成目录消息或改写先前工具结果」。

## 注册表语义（pai 大多用不上，记三条）

- 分层：宿主 + 按 scope（agent preset 挂载的落自己层），读取合并层链、近层同名直接赢；单层内 rank → 提供方顺序 → 本地顺序。
- 发现缓存以 scope 链为键；不完整观测（provider 被拒/发现期间目录变更）不缓存，消费方留 last-good 重试。
- `skills/change` 是不带 diff 的失效广播，消费方自己重拉——与 pai「事件通知、读方自取」的 viz 轮询哲学同构。

## 工具 schema（tool-catalog 原文）

单参数 `{name: string}`，required。描述原文：加载可用 skill 的完整说明；在执行点名某项 skill 或与其明确匹配的任务前，用会话 skill 目录中的确切名称调用此工具。写入/影响：`tool/call`、`tool/result`、`user/message replacement catalogs via agent.inject()`。

## pai 视角

- ⚠️ R4#A4 的「零新增工具」说的是 pi 形态；dsh 恰恰是有专用工具的一家。三家在「加载动作」上三分：pi 复用 read、CC 的 Skill 工具展开 prompt、dsh 的 skill 工具返回 tool result。pai 拍板时这是真三选一，不是二选一。
- dsh 的目录只给 name + description（不给 location 路径），配合专用工具成立；pi 给 location 是因为要让模型自己 read。选了 read 形态就必须给路径——两个决定是绑定的，拆开抄会抄出「有路径没人读」或「没路径读不了」。
- 「每次 get() 重读盘、注册表不缓存正文」换来的是改盘即生效；pai 若把正文塞进会话历史（两家皆然），改盘不改历史是必然代价，不用追 dsh 这条。
