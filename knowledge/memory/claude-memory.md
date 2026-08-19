# 官方记忆（memory）精读

- 来源：https://code.claude.com/docs/zh-CN/memory （2026-08-10 抓取）
- 精读日期：2026-08-10
- pai 锚点：roadmap 阶段 3（记忆）、`src/pai/core/loop.py` 的 `SYSTEM_PROMPT`（现在硬编码）、
  `src/pai/core/compaction.py`（压缩后指令的重注入问题，见第五节）

## 一、最重要的一条：两套机制，不是一套

官方明确把它拆成两个互补系统，两者都在每次对话开始时加载：

| | CLAUDE.md 文件 | 自动记忆 |
|---|---|---|
| 谁写 | 你 | Claude 自己 |
| 内容 | 指令与规则 | 学到的东西与模式 |
| 范围 | 项目 / 用户 / 组织 | 每个 worktree（同仓库的 worktrees 共享一份） |
| 加载 | 每会话全量 | 每会话，但只加载 `MEMORY.md` 的前 200 行或 25KB |
| 用于 | 编码标准、工作流、项目架构 | 构建命令、调试见解、Claude 发现的偏好 |

pai 阶段 3 的目标句「分层记忆文件加载 + 会话学得的东西写回」正好是这两套的各一半——
读的是第一套（分层指令），写的是第二套（自动记忆）。设计时别把它们混成一个东西：
第一套是「拼接进上下文」，第二套是「索引 + 按需读」，加载策略根本不同。

## 二、分层加载的确切规则（pai 要抄的核心）

位置与优先级（从最宽到最具体，后加载的更靠近对话）：

| 范围 | 位置 | 谁能看到 |
|---|---|---|
| 托管策略 | `/Library/Application Support/ClaudeCode/CLAUDE.md`（macOS）等 | 组织全体，不可被个人设置排除 |
| 用户 | `~/.claude/CLAUDE.md` | 仅本人，所有项目 |
| 项目 | `./CLAUDE.md` 或 `./.claude/CLAUDE.md` | 团队（进版本控制） |
| 本地 | `./CLAUDE.local.md` | 仅本人当前项目（gitignore） |

查找算法（三条，缺一条行为就不对）：

1. 从 cwd 向上遍历目录树，沿途每个目录都查 `CLAUDE.md` 与 `CLAUDE.local.md`。
2. 全部拼接，不是互相覆盖。顺序从文件系统根向下到 cwd——即越靠近你启动的位置，
   越晚被读到。同一目录内 `CLAUDE.local.md` 排在 `CLAUDE.md` 之后。
3. cwd 之下的子目录里的文件不在启动时加载，等 Claude 真去读那个子目录的文件时才带进来。

`@path` 导入：相对路径相对含导入的那个文件解析（不是 cwd）；可递归，最大深度 4 跳；
跳过代码块与行内代码（写 `` `@README` `` 是字面文本，`@README` 才是导入）。
导入的文件在启动时展开——所以拆文件不省上下文，只是好组织。

`.claude/rules/`：递归发现所有 `.md`；无 `paths` frontmatter 的在启动时加载，
有 `paths`（glob）的只在 Claude 读到匹配文件时才进上下文。用户级 `~/.claude/rules/`
先于项目规则加载（项目优先级更高）。

## 三、自动记忆的机制（pai「写回」要抄的）

- 存储：`~/.claude/projects/<project>/memory/`，`<project>` 由 git 仓库决定——
  同仓库的所有 worktrees 与子目录共享一份；不在 git 仓库里才退回项目根。
- 结构：`MEMORY.md`（简洁索引，每会话加载）+ 任意主题文件（`debugging.md` 等，
  启动时不加载，Claude 要用时用普通文件工具按需读）。
- 200 行 / 25KB 上限只管 `MEMORY.md`，超出部分会话开始时根本不加载。
  CLAUDE.md 无论多长都全量加载（但官方建议每个 <200 行，长了「降低遵守度」）。
- Claude 自己决定什么值得记（判据是「对未来对话有没有用」），不是每会话都写。
- 纯 markdown，用户可随时读改删（`/memory` 浏览）。

## 四、「记忆是上下文，不是强制配置」——这句话对 pai 阶段 4 更重要

官方原话：两套记忆 Claude 都当作上下文而不是强制配置；要真正阻止某个动作，
改用 PreToolUse hook。还补了一刀：CLAUDE.md 的内容是作为 system prompt 之后的
user message 传进去的，不是 system prompt 本身，所以没有严格遵守的保证。

这正是 pai 已经实践过的结论的官方版本：`guards/design_gate.py`（PreToolUse）就是为了把
AGENTS.md 里的软约束降到确定性层——见 [permissions/hooks-gates.md](../permissions/hooks-gates.md)
与 features/03-20260809-design-gate。阶段 4 做权限时这条要再引一次：
能写进提示词的都不叫防线。

## 五、与 pai 阶段 1（压缩）直接冲突的一条，必须现在记下

项目根 CLAUDE.md 在压缩中存活：`/compact` 之后 Claude 从磁盘重新读取并重新注入。
子目录里的嵌套 CLAUDE.md 不会自动重注入，等下次读到那个目录的文件才回来。

pai 的 `compact()` 现在重建的是 `[system] + [摘要] + [保留尾部]`——system 是硬编码的
`SYSTEM_PROMPT`，没有任何指令文件需要重注入，所以现在不冲突。但阶段 3 一旦把
分层记忆拼进上下文，压缩就会把它们连同历史一起摘掉：阶段 3 的验收必须包含
「压缩后指令文件重新注入」这一条，否则记忆功能在长会话里会静默失效——
这是本次精读最有价值的一条，它是从别人的文档里读出来的、pai 尚不存在的 bug。

## 六、明确记下但 pai 不做的

| 官方能力 | 不做的理由 |
|---|---|
| 托管策略层（MDM 分发、`managed-settings.json` 的 `claudeMd`） | 组织部署功能，非 harness 学习目标 |
| `claudeMdExcludes`（monorepo 里跳别的团队的文件） | 要先有 monorepo 痛点，现在是过度设计 |
| `.claude/rules/` 的 `paths` 条件加载 | 值得做但排后面：它本质是「按需加载」，与阶段 6 skills 是同一个机制，届时一起做更划算 |
| `/init`、`/doctor` 的修剪建议、`InstructionsLoaded` hook | 产品面工具 |
| subagent 的独立记忆 | sub-agents 在 map.md 已裁定不做 |
| HTML 注释在注入前被剥离 | 细节，pai 可原样保留（注释也没多少 token） |

## 七、pai 阶段 3 的落地结论（本笔记的产出）

1. 读：从 cwd 向上遍历，拼接 `PAI.md` / `PAI.local.md`（名字待拍板）+ `~/.pai/PAI.md`，
   顺序为根→cwd、同目录内 local 在后；`@path` 导入带深度上限与环检测。
2. 写：`MEMORY.md` 索引 + 主题文件，索引有行数/字节上限，主题文件按需读。
3. 注入点：现在的 `SYSTEM_PROMPT` 是 loop 里的常量，指令拼接后要么进 system、
   要么按官方做法进第一条 user 消息——这是阶段 3 要拍板的第一个取舍
   （官方选了 user 消息，且自陈因此「没有严格遵守保证」）。
4. 压缩重注入：见第五节，验收必须覆盖。
