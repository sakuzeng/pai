# Claude Code 官方 skills 章节精读

- 来源：https://code.claude.com/docs/zh-CN/skills（精读时文档描述的行为基线是 v2.1.196~2.1.205，本机实测用 2.1.239）
- 精读日期：2026-08-22
- pai 锚点：roadmap 阶段 6（skills 子阶段）、features/25、src/pai/core/loop.py（`build_system_prompt` 装配缝）
- 相关：[cc-skills.md](cc-skills.md)（反编译源码侧，版本 2.1.88，与本篇有系统性版本差）

## 一句话模型

skill = 一个目录 + 一个 `SKILL.md`（YAML frontmatter + markdown 正文）。description 常驻上下文供匹配，正文只在调用时加载——这就是渐进式披露（progressive disclosure）。你能 `/skill-name` 显式调，Claude 能按 description 自动调，两个开关（`disable-model-invocation` / `user-invocable`）各关一边。

## 存放位置与优先级

| 级别 | 路径 | 生效范围 |
|---|---|---|
| 企业 | 托管设置 | 组织所有用户 |
| 个人 | `~/.claude/skills/<name>/SKILL.md` | 该用户所有项目 |
| 项目 | `.claude/skills/<name>/SKILL.md` | 本项目 |
| 插件 | `<plugin>/skills/<name>/SKILL.md` | 启用插件处 |

同名冲突：企业 > 个人 > 项目；任何级别覆盖同名捆绑 skill；插件走 `plugin:skill` 命名空间不参与冲突。skill 与同名 `.claude/commands/` 文件并存时 skill 赢（自定义命令已并入 skills，旧 commands 文件继续工作）。

三个 pai 视角要点：

- 项目 skills 从起始目录一路向上收集到仓库根（子目录里启动也拿得到根上定义的）；反向的嵌套发现（`packages/frontend/.claude/skills/`）按需触发，冲突时嵌套者以 `apps/web:deploy` 目录限定名共存。
- `--add-dir` 目录的 `.claude/skills/` 会加载（是「additionalDirectories 只授文件权限」原则的显式例外），`settings.json` 里配的 additionalDirectories 不加载。
- 实时变更检测：会话中增删改 SKILL.md 即刻生效，不用重启；但会话启动时不存在的顶级 skills 目录要重启才被监视。

## frontmatter 字段（全部可选）

核心三件：`name`（只是显示名——命令名来自目录名，唯一例外是插件根 SKILL.md）、`description`（匹配依据；省略时用正文第一段顶上）、`disable-model-invocation`（true = 只许人调，且 description 不进上下文）。

其余：`user-invocable: false`（只许模型调，从 `/` 菜单隐藏）、`allowed-tools`（skill 激活期免批准的工具，是授权不是限池）、`disallowed-tools`（激活期从池中移除，下条消息即清）、`model` / `effort`（当轮覆盖）、`context: fork` + `agent`（丢进 subagent 跑，正文变成 prompt）、`hooks`（限 skill 生命周期）、`paths`（glob 匹配才自动激活）、`argument-hint` / `arguments`（命名参数）、`when_to_use`（追加进列表，与 description 合并后受同一截断上限）。

字符串替换：`$ARGUMENTS` / `$N` / `$name`、`${CLAUDE_SESSION_ID}`、`${CLAUDE_SKILL_DIR}`（引用随包脚本的关键）、`${CLAUDE_PROJECT_DIR}`。skill 不含 `$ARGUMENTS` 时参数以 `ARGUMENTS: <value>` 追加在尾部。

动态上下文注入：`` !`cmd` ``（行首或空白后才认）与 ```` ```! ```` 围栏块在发给模型之前先执行，输出替换占位符——是预处理，模型只见结果；替换只跑一遍，输出不会被二次扫描。`disableSkillShellExecution` 可整体禁用。

## 列表预算与截断（pai 必抄的部分）

- skill 名单（name + description）注入上下文，预算是模型上下文窗口的 1%（`skillListingBudgetFraction` 可调，`SLASH_COMMAND_TOOL_CHAR_BUDGET` 环境变量给定值）。
- 超预算时先砍「调用最少的」skill 的 description（名字永远保留），常用的保全文。
- 每条 description + when_to_use 合并截 1,536 字符（`skillListingMaxDescChars` 可调）。⚠️ 反编译源码 2.1.88 里这个每条上限是 250——版本漂移的实据，见 [cc-skills.md](cc-skills.md)。

## 内容生命周期与压缩（feature 25 验收标准的出处）

- 调用时正文作为一条消息进入对话，之后不重读文件——「常设说明」要写成常设语气。
- 重复调用且渲染结果相同时只加一行「已加载」提示，不再贴第二份（v2.1.202 起；之前每次全量追加）。
- 自动压缩后重挂：每个被调用过的 skill 的最近一次调用重新附加，单个截前 5,000 token，全部共享 25,000 token 预算，从最近调用的开始填——调得早的可能被整个挤掉。这两个数字与反编译源码常量一致（`POST_COMPACT_MAX_TOKENS_PER_SKILL` / `POST_COMPACT_SKILLS_TOKEN_BUDGET`），交叉验证通过。
- 官方排障口径：skill「失效」时内容通常还在，是模型不再偏好它——先改 description，硬约束上 hooks。

## 实测与文档的出入（claude 2.1.239 真实探针，详见 features/25 evidence）

- 目录名是命令名、frontmatter `name` 只是显示名——列表实测符合（`probe-dirname` 按目录名列出）。但用 frontmatter name 调用（`/totally-different-name`）也真的调起来了——机制未查明（可能是模型经 Skill 工具解析），与「不会改变你输入的内容」的文档措辞不符，如实记录不编解释。
- frontmatter YAML 写坏时，排障节说「元数据为空、没有 description 可匹配」；实测正文首段顶上了 description 的位置（description 省略回退首段的规则吞掉了这个场景），列表里看起来与正常 skill 无异。

## pai 视角

- pai 走 pi 的最小形态（R4#A4 拍板方向），本篇的价值是知道「完整形态有什么、砍掉的是哪些」：fork 执行、allowed-tools、hooks、动态注入、参数替换第一版都可以不做，但列表预算与压缩后重挂不是可选项——前者管上下文成本，后者是 CC 踩过的坑（验收标准点名）。
- 「description 省略回退正文首段」看似贴心，实测证明它会掩盖 frontmatter 写坏的事故。pai 的 memory.py 对 frontmatter 的态度是「窗口内没收尾就当没有」——skills 加载器沿用这个诚实边界时，要决定坏 frontmatter 是跳过（fail loud 进 diagnostics）还是回退，别无意识地抄回退。
