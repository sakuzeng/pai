# pi 的 skills 实现走读

- 来源：pi-mono `packages/coding-agent/src/core/skills.ts`（487 行）、`packages/agent/src/harness/skills.ts`（375 行）、`packages/coding-agent/src/core/agent-session.ts`（`_expandSkillCommand`）、`packages/coding-agent/docs/skills.md`；commit `4c01c709`（2026-08-02）
- 精读日期：2026-08-22
- pai 锚点：features/25（R4#A4 点名的最小形态原型）、src/pai/core/memory.py（`scan_memories` 即 pai 侧骨架）、src/pai/core/loop.py（`build_system_prompt`）
- 相关：[claude-skills.md](claude-skills.md)、[dsh-skills.md](dsh-skills.md)

## 全机制四步（pi 文档自己的总结，源码证实）

1. 启动时扫描各位置，只取 name + description；
2. system prompt 里注入 `<available_skills>` XML 索引（`formatSkillsForPrompt`，在 `system-prompt.ts` 两处拼接）；
3. 任务匹配时模型自己用 `read` 工具加载完整 SKILL.md——零新增工具；
4. 模型照正文办事，相对路径按 skill 目录解析（索引头部的指导语明说了这条解析规则）。

这就是 R4#A4 说的最小形态。pi 文档原文承认第 3 步不可靠：*models don't always do this; use prompting or `/skill:name` to force it*。

## 扫描（`loadSkillsFromDir`，pai 直接可抄的部分）

- 发现规则：目录含 `SKILL.md` 即是 skill 根、不再往下递归；否则加载根下直属 `.md` 文件、并递归子目录找 `SKILL.md`。跳过 `.` 开头与 `node_modules`。
- 位置：`~/.pi/agent/skills/` 与 `.pi/skills/`（默认），`--skill <path>` 与 settings `skills` 数组追加——所以「把 `~/.claude/skills` 挂进来」只是一行配置，跨 harness 复用是设计目标。
- 尊重 `.gitignore` / `.ignore` / `.fdignore`（模式带相对前缀逐层累加）。
- 符号链接跟随；用 realpath 去重（同一文件经两条路径挂进来只载一次）。
- 名字冲突：先到先得，输家进 `collision` 诊断；诊断（`ResourceDiagnostic`）是一等公民，warning 不阻断加载。

## 校验（agentskills.io 规范，宽松执行）

name ≤64、`^[a-z0-9-]+$`、无首尾/连续连字符；description ≤1024。全部只出 warning 照样加载——唯一的硬门槛是 description 缺失即不加载（`skill: null`）。

⚠️ 文档与源码不符：`docs/skills.md` 的 frontmatter 表写 `name` Required=Yes，源码实际是 `name = frontmatter.name || parentDirName`（回退目录名，只警告）。pi 还明写了它故意偏离标准：不要求 name 与父目录一致，理由是共享 skill 目录会被多个 harness 用。而 harness 包那份实现（`packages/agent/src/harness/skills.ts`）却多一条「name 必须与父目录一致」的警告校验——同仓两份实现在这条上互相打架，引用时要说清是哪份。

## 注入（`formatSkillsForPrompt`）

`disable-model-invocation: true` 的 skill 被过滤掉才轮到渲染；空列表返回空串（不留空标签）。格式：

```
The following skills provide specialized instructions for specific tasks.
Use the read tool to load a skill's file when the task matches its description.
When a skill file references a relative path, resolve it against the skill directory …

<available_skills>
  <skill>
    <name>…</name>
    <description>…</description>
    <location>…（SKILL.md 绝对路径）</location>
  </skill>
</available_skills>
```

name/description/location 全部 XML 转义。注意 pi 没有任何列表预算/截断——描述有 1024 上限但条数无上限，几十个 skill 就是几十条全文进 system prompt（CC 与 dsh 都对此设了预算，pi 是三家里唯一裸奔的）。

## 显式调用（`/skill:name`，`_expandSkillCommand`）

- 前缀匹配 `/skill:`，查内存里的 skill 表，命中则当场重读文件（`readFileSync`）、剥 frontmatter，包成 `<skill name="…" location="…">正文</skill>` 块替换用户输入；参数直接追加块后。
- 未知名字原样透传（当普通输入交给模型）；读文件失败发扩展错误事件、原样透传。
- steering 路径同样过展开（排队的 `/skill:` 消息注入前也会展开）。
- `enableSkillCommands` 设置可关（默认开）。

也就是说 pi 的「加载」有两条对称路径：模型自己 `read`（进 tool_result）与用户 `/skill:` 展开（进 user 消息），后者不经过模型判断、必然全文进上下文。

## 压缩后的行为（pai 验收标准视角）

pi 对「已加载的 skill 正文在压缩后是否幸存」没有任何特殊处理——正文以 tool_result 或 user 消息的身份参与普通压缩，摘要吞掉就吞掉了。索引部分倒是天然安全：`<available_skills>` 住在 system prompt 里，压缩不碰 system。CC 踩过的坑（压缩后重挂正文）pi 尚未踩或尚未修——pai 的验收标准点名要处理，这是 pai 相对 pi 最小形态唯一必须加的东西。

## pai 视角

- `scan_memories`（frontmatter 窗口解析、mtime 排序、截断）与 `loadSkillsFromDir` 的职责几乎重合，差异只在：skills 认目录结构（`<name>/SKILL.md`）、要 XML 索引而非 markdown 索引、name 来自目录名。复用骨架时别抄 pi 的 ignore 文件支持——pai 的记忆扫描没做，v1 的 skills 也不必做（登记遗留即可）。
- pi 的「零新增工具」依赖模型愿意 `read`；pi 自己承认不总是灵。pai 用 DeepSeek，模型服从性更没有保证——拍板时要把「工具形态 vs read 形态」当真实取舍问，不是照抄 pi 就完事。
