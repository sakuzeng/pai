# 10-memory-recall · spec

<!-- superpowers brainstorming 的产物：一次一问澄清后的共识落盘。拍板问答全文在 README。 -->

## 背景与问题

feature 06 交付的自动记忆只有**一层**：`MEMORY.md` 索引常驻上下文，主题文件「靠模型自己
想起来 `read_file`」。[K cc-memdir](../../../../knowledge/source-walks/cc-memdir.md) 走读
裁决了 06 复盘留下的悬案：**CC 的第二层是框架主动召回**，pai 缺的不是实现质量，是一整层机制。

现状四处具体缺口：

| 缺口 | 现状代码 |
|---|---|
| 索引行没有描述 | `memory_tool.py:84` 写的是 `- [约定](约定.md)`，模型无从判断该不该读 |
| 记忆文件没有 frontmatter | `memory_tool.py:72` 写的是裸 bullet `- 2026-08-10 <fact>` |
| 没有任何新鲜度提示 | 日期只在 bullet 里，且是 ISO 戳（**模型不擅长日期算术**） |
| 没有召回 | 索引是唯一入口，撞 200 行上限 = 记忆等于不存在 |

## 目标（做什么）

1. **写侧改格式**：`remember` 从「追加到主题文件」改成「创建或更新一篇记忆」，
   落盘带 frontmatter，格式与本机 CC 记忆文件对得上（附录一）。
2. **索引改投影**：`MEMORY.md` 由 frontmatter 扫描结果重新渲染，不再打补丁。
3. **新鲜度**：相对时间（「47 天前」）进索引与召回块；≥2 天的记忆附陈旧警告。
4. **召回层**：每轮用户输入前跑一次侧查询，≤5 篇注入 `<system-reminder>`，
   usage 计进预算熔断，失败静默降级、连续 3 次停用。

## 非目标（明确不做什么）

- **`recentTools` 去噪**（CC 有：正在用的工具，其用法文档不选、但坑与警告要选）。
  pai 的记忆量还没到需要这层去噪，且要给 loop 加一条「最近用了哪些工具」的管线。→ TODO。
- **召回的开关配置**。本次唯一的「关」是记忆目录为空（短路，不发请求）。
  真要开关应落在 `.pai/settings.json`（feature 07 的两层配置）而不是又一个 env。→ TODO。
- **`MEMORY.md` 自动剪枝 / 遗忘机制**（06 遗留）。触发条件仍是「它真长起来」，
  但本次一事一文件让它长得更快——**这一点必须写进遗留问题**，别让它悄悄恶化。
- **200 行 / 25KB 上限按中文校准**（06 复盘质疑四）。没有数据，本次不动。
- **`/memory reload`**（06 遗留，几行的事，走小修通道）。
- **删除记忆的工具**。`remember` 只负责创建与更新；记忆是纯 markdown，
  要删要重写用现有 `edit_file` / `write_file`（06 复盘第六节的论证仍成立）。
- **旧记忆文件的迁移脚本**。本机实测现存 3 个文件共 186 字节（冒烟留下的），
  降级读取即可，写迁移代码不划算。

## 设计要点

### 一、记忆文件格式（pi 无此概念 → CC 见附录一 → pai）

```markdown
---
name: <slug，等于文件名去掉 .md>
description: <一句话；召回器与索引行**共用**这一份文案>
metadata:
  type: user | feedback | project | reference
  originSessionId: <写下它的那次会话>
  modified: <ISO 8601>
---

<正文，追加式；每次 remember 追加一段>
```

**与 CC 的差异（README「刻意不同」第 2 条）**：CC 让模型写两份文案——frontmatter 的
`description` 给召回器读，`MEMORY.md` 行尾的钩子给主模型读。pai 只写一次、两处共用。

**frontmatter 解析自己写，不引 PyYAML**：格式是我们自己的工具产生的，只需认
「`---` 围栏 + `key: value` + 两空格缩进的 `metadata:` 块 + 可选引号」这个子集。
引一个新依赖去解析自己写的 6 行文本不划算。解析不认识的字段忽略，不报错。

### 二、扫描（照 CC `memoryScan.ts`）

`scan_memories(directory) -> list[MemoryHeader]`：

- 遍历 `*.md`，**排除 `MEMORY.md`**（它已经常驻上下文，CC 的 `findRelevantMemories` 也显式排除）；
- **每文件只读前 30 行**（`FRONTMATTER_MAX_LINES = 30`）——manifest 的输入成本与记忆总量几乎无关；
- 按 **mtime 新→旧**排序，截断 **200** 个（`MAX_SCANNED`）；
- 读失败的文件跳过，不炸（记忆扫描在启动路径上）。

**降级**：没有 frontmatter 的旧文件 → `description` 取首个非空行（截断 80 字），
`type = "legacy"`，`name` 取文件名。不报错、不回填。

### 三、索引是投影（本需求的核心取舍，拍板问 2）

一个渲染函数喂两个出口，结构上不可能漂：

```
scan_memories(dir) ──> render_index() ──┬──> build_context()  进上下文
                    └─> build_manifest() ──> 召回器
                                            └──> remember() 写盘 MEMORY.md（原子写）
```

**读侧纯读**：`build_context` 只 `scan + render`，**不写盘**——feature 09 刚把工作目录
边界立起来，读路径偷偷产生写副作用不符合这个姿态。
**写侧重建**：`remember` 成功后重建并原子写（复用 `fs._atomic_write` 的做法：
同目录 tmp + `os.replace`），避免两个 pai 进程同时写把索引写坏。

**已知行为**：手删记忆文件后、下次 `remember` 之前，盘上那份 `MEMORY.md` 滞后。
此时**上下文里那份是对的**（每次都重新扫），错的只是给人看的那份，下次写记忆自动修好。

**相对时间只进上下文，不进盘**：`render_index(headers, now=None)` —— `now` 为 None 就
不渲染时间。理由：相对时间是**渲染时刻的函数**，写进持久文件就会腐坏，
而「一条三个月前的记忆在文件里写着『今天』」正是新鲜度这条特性要防的东西。

索引文件头写明它是生成物：

```
# 记忆索引（本文件由 pai 自动生成，手改会被覆盖；要改请改对应记忆文件的 frontmatter）
```

**截断的性质变了**：有召回层之后，撞上 200 行/25KB 不再是「那条记忆等于不存在」，
而是「常驻区放不下，仍可被召回选中」。所以 `memory.py:164` 那句提示要改词——
它现在指向 `read_file MEMORY.md`，而读侧已经不读那个文件了。

### 四、新鲜度（照 CC `memoryAge.ts`）

- `memory_age(mtime, now)` → `今天` / `昨天` / `N 天前`。**按日历日差算**，
  不用 86400 秒整除——否则昨晚 23:00 与今早 01:00 会算成「今天」。
- `freshness_note(days)`：**≤1 天返回空**（新鲜时警告是噪音，CC 同款阈值）。
  ≥2 天返回：「这条记忆写于 N 天前。记忆是**时间点观察，不是实时状态**——
  其中关于代码行为的断言或 `file:line` 引用可能已经过期，当成事实之前先核对当前代码。」

动机是 CC 注释里写明的真实事故：**带 `file:line` 的引用会让一条过期声明听起来更权威，
而不是更不权威**。pai 迟早会踩，CC 已经替我们踩过。

### 五、召回（照 CC `findRelevantMemories.ts`）

```
manifest 行： - [type] <文件名> (<相对时间>): <description>
```

`select_memories(query, headers, *, client, model, already_surfaced, max_files=5)`：

1. **空目录短路**：0 篇 → 直接返回 `([], {})`，不发请求；
2. `already_surfaced` **在调模型之前**滤掉（否则 5 个名额浪费在已经在上下文里的东西上）；
3. 侧查询：`client.chat.completions.create(model=recall_model, max_tokens=256,
   response_format={"type": "json_object"})`，系统提示含 CC 那两条去噪规则——
   **不确定就别选、宁可返回空**；**最多 5 篇**（写进 prompt，不只在代码里截断）；
4. **防御解析**：正则抓第一个 `{...}` 再 `json.loads`，拿 `selected` 里的字符串；
5. **白名单校验**：只保留真实存在的文件名（模型会编不存在的），再截到 ≤5；
6. 任何异常/解析失败 → `([], {})`，不阻断主流程。

**风险项（实现期必须真验一次）**：DeepSeek 的 OpenAI 兼容层支持 `json_object`，
但 `json_schema` 严格模式未必支持——所以第 3 步用 `json_object`，正确性靠第 4、5 步兜底，
而不是靠 provider 的 schema 强制。真跑冒烟确认后把结果记进 devlog。

### 六、注入与接线

**loop 不认识记忆**。照 `instructions: Callable[[], str]` 的同款做法，新增
`recall: Optional[Callable[[str], tuple[str, dict]]]` —— 给一句 query，返回
（要注入的文本, usage）。目录、client、模型、状态全在装配层的闭包里。

- 注入位置：**该轮 task 消息之后**追加一条 user 消息。append-only，与 `SessionLog`
  的顺序一致；`<system-reminder>` 块自身声明了「这是背景上下文，不是用户指令」。
- 空串不插（同 `_inject_instructions` 的规矩，塞空消息是白烧 token）。
- **usage 计进 `spent_tokens`**，与压缩那次同款（`loop.py:191`）。
- `RecallState`（`surfaced` / `failures` / `disabled`）由装配层持有跨轮——
  与 `AnchorBook` / `CompactionState` 同构，REPL 每轮调一次 `run_agent` 也不会清零。
- 连续失败 3 次 → `disabled`，本会话不再发请求（CC 没有这层；pai 的预算文化要求它）。

### 七、配置

`config.recall_model()` → `PAI_RECALL_MODEL`，未设置回落 `model_name()`。
CC 有便宜档（Sonnet）可切，pai 只有一个模型档——这个 env 就是那个口子。

## 验收标准

1. 新增测试全部先红后绿，`./test.sh` 全绿（当前基线 385 passed）；
2. `remember` 落盘文件能被 `scan_memories` 读回，字段齐；同名再写 = 更新（正文追加、
   `description`/`modified` 覆写），不产生第二个文件；
3. 删掉一个记忆文件后再 `remember`，`MEMORY.md` 里那行**消失**（投影方案的判据测试——
   账本实现过不了这条）；
4. 无 frontmatter 的旧文件出现在索引里，`type` 为 `legacy`，不报错；
5. `render_index(..., now=None)` 不含相对时间，给了 `now` 才含（防止时间戳腐坏）；
6. 召回：白名单能挡住模型编的文件名；`already_surfaced` 的不再选；空目录不发请求；
   client 抛异常返回空且不阻断；连续 3 次失败后不再发请求；
7. loop：召回文本插在 task 之后、usage 计进 `spent_tokens`、返回空串不插消息；
8. 至少一条测试拿**真实会话轨迹**当输入（AGENTS.md 测试规约）。

## 附录一 · 本机 CC 记忆文件实测（2026-08-11）

`~/.claude/projects/-Users-sakuzeng-improve-coding-agent-projects-pai/memory/`：

```markdown
---
name: pai-module-workflow
description: "pai 项目每个新模块的标准开发流程(superpowers 全链路),用户确认采用"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 6cb0e83b-dd25-4235-ae32-bd6396336072
  modified: 2026-08-09T07:26:56.497Z
---

<正文，feedback/project 类型带 **Why:** 与 **How to apply:** 两行>
相关:[[pai-project-context]]        ← wikilink 可指向尚不存在的记忆
```

`MEMORY.md`：`- [pai 模块开发标准流程](pai-module-workflow.md) — superpowers 全链路:brainstorm→...`

走读笔记未覆盖、由这份样本补上的四条：`description` 与索引钩子是**两个不同字符串**；
`modified` 是写进 frontmatter 的 ISO 戳（与文件 mtime 并存，不会被 `touch`/拷贝破坏）；
`originSessionId` 让记忆能回指产生它的那次会话；`node_type: memory` 这层套娃 pai 不抄。
