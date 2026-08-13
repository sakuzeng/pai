# 10-memory-recall —— 记忆召回层（frontmatter + 新鲜度 + 按查询召回）

状态：已交付（2026-08-11，7 task TDD，458 passed；复盘见 [复盘.md](复盘.md)）
分支：`feat/10-memory-recall`（brainstorm 拍板 + 全部实现）
流程：superpowers 全链路（brainstorm → spec → plan → 7 task SDD → 合并 → tag `memory-v1`）

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

**用户原话**（2026-08-11）：

> 记忆这块交付时就留了三个已知空缺（frontmatter、新鲜度提示、召回层），只是当时都记成了 TODO。
>
> 所以我的建议是：不要零敲碎打补一个字段，而是把这三条合成一个档案一次做掉——它们共用同一套
> 改动（remember 的写入格式 + load_memory_index 的读取），拆开做会改三遍同一个文件。
> 按规矩 7 的判据，它们改变了 06 的交付结果，所以是新档案 feat/10-memory-recall。

本档案**改变**（而非完成）[06-20260810-memory](../06-20260810-memory/README.md) 的交付结果，
按 features/README 规矩 7 新建并链回；06 冻结。

### 空缺从哪来

三条都出自 [K memory/cc-memdir.md](../../../../knowledge/memory/cc-memdir.md)
（06 复盘第五节留的悬案「`findRelevantMemories` 是否有相关性筛选」的裁决走读），
当时全部降格进了 TODO：

| TODO 条目 | 走读结论 |
|---|---|
| `remember` 写入带 `description` frontmatter | CC 的召回全靠它（只读文件前 30 行拼 manifest） |
| 记忆的新鲜度提示 | CC 用「47 days ago」而非 ISO 戳，因为**模型不擅长日期算术** |
| 召回层做不做（要拍板） | CC 是**框架主动召回**，不是「模型自己想起来 read_file」 |

讨论中新查出**第四条空缺，TODO 未登记**：`MEMORY.md` 的索引行只有主题名与链接
（`- [约定](约定.md)`，`memory_tool.py:84`），**连一句描述都没有**——模型在上下文里
看到的全部信息是「有个文件叫 `约定.md`」，凭什么判断该不该读。

### 验收标准

1. `remember` 写出的记忆文件带 frontmatter（`name` / `description` / `metadata.type` /
   `originSessionId` / `modified`），与本机 CC 记忆文件格式对得上；
2. `MEMORY.md` 由 frontmatter **重建**而非追加，删文件/改描述后不会漂；
3. 进上下文的索引行带描述与相对时间（「47 天前」而非 ISO 戳）；
4. 每轮用户输入前跑一次召回：manifest → 侧查询 → 白名单校验 → ≤5 篇 →
   `<system-reminder>` 注入，含 >1 天的陈旧警告；
5. 召回的 usage 计进 `max_total_tokens` 熔断账；任何失败静默降级不阻断，
   连续失败 3 次本会话停用；
6. 旧格式记忆文件（无 frontmatter）降级可用，不报错、不需要迁移脚本；
7. `./test.sh` 全绿。

## 候选方案与确认

### 讨论的起点：三条空缺之间有一条耦合链

分析时发现三条不是并列的，**粒度 × 索引是否全量 × 召回是否存在**互相锁死：

| | 索引的角色 | 召回 | 粒度可选 |
|---|---|---|---|
| pai 现在 | **全量清单**（每主题自动一行），模型唯一入口 | 无 | 必须按主题聚合，否则 200 行上限提前撞 |
| CC | **一事一文件的清单**，可被截断 | 扫目录，不依赖索引 | 一事一文件才准 |

两条推论：**「一事一文件」只有在有召回层时才成立**（否则索引行数 = 记忆条数，
06 复盘质疑二那条「只增不减」立刻恶化）；反过来，**主题追加会让 description 与
新鲜度都变成半真半假**（一个累积 50 条 bullet 跨三个月的 `约定.md`，description 写什么？
mtime 只反映最后一次追加）。

所以拍板顺序与 TODO 记的相反：**先拍召回层，粒度才有唯一解**。

### 确认

**问 1**：召回层做不做？（TODO 里标着「要拍板」的那条）

- 候选甲·**不做**：只把索引做厚（description + 新鲜度进索引行），靠模型自己 `read_file`。
  零成本。代价：06 复盘留的悬案「pai 少了一整层机制」原样留着；且索引必须全量，
  粒度锁死在主题追加。
- 候选乙·**做成工具** `recall_memory(query)`：manifest 构建 / ≤5 上限 / 白名单校验 /
  失败降级全实现，但触发点是模型自己调，不额外打模型（多一轮 tool call，在主循环里）。
  复用 `@tool` + 权限层 + 事件系统，完全可离线测。代价：**它没解决那个真问题**——
  「模型压根没想起来有记忆」时，工具和 `read_file` 一样叫不动。
- 候选丙·**照 CC 做框架侧查询**：每轮用户输入前打一次模型选文件。
  `compaction.summarize()`（`compaction.py:269`）是现成的侧查询先例，注入 client + model
  照抄形状即可。代价实打实：pai 只有一个模型档（`config.py:11`），没有便宜档可切，
  要加 `PAI_RECALL_MODEL`；且**必须计进 `max_total_tokens` 熔断账**（压缩那次就是这么处理的，
  `loop.py:191`），漏了就是预算文化上的破口。

**选择：丙**。用户原话：「**按cc的来，它是怎么做的呢**」。

连带被锁死的两条（不再单独拍板）：
- **粒度 = 一事一文件**（见上面的耦合链）；
- **召回块入 `messages`**——CC 是附在该轮 user 消息上、跨轮留存；正因为留存才需要
  `alreadySurfaced` 在调模型**之前**去重（否则 5 个名额会浪费在已经在上下文里的东西上）。

**问 2**：`MEMORY.md` 索引怎么维护？（用户追问「索引你计划怎么维护呢」）

- 候选 A·**账本**（现状延伸）：`remember` 时往索引 append / patch 一行。
  代价是四类补丁都得写：新增、描述变了要改行、文件被删要去行、去重。
  而「文件被删」只有全量扫描才知道——**账本方案迟早也要扫描**。
  且现有去重是子串匹配（`if f"{name}.md" in existing`，`memory_tool.py:88`），
  文件多起来后 `a.md` 会在 `xa.md` 那行命中，新记忆静默不进索引。
- 候选 B·**投影**：不再打补丁，从各记忆文件的 frontmatter **重新渲染**整个 `MEMORY.md`。
  关键论据：**召回层本来就要写扫描代码**（`scanMemoryFiles`：每文件前 30 行、取 frontmatter、
  带回 mtime），索引重建就是 `render_index(scan(dir))`——同一个扫描结果的第二个消费者，
  零新增机制。上面四类补丁与那个子串 bug 一并消失。
  代价：**手编 `MEMORY.md` 会被覆盖**（CC 的索引是模型手写的，手改能活到模型下次动它为止）。

**选择：B**。用户原话：「**我认为可以**」（对「手编会被覆盖这个代价你认不认」的回答）。
理由（我给出、用户认可）：pai 的 `remember` 是**工具**（06 问 3 拍板），正确性押在框架上
不押在提示词上；既然如此索引就该是可推导的，而不是又一份需要模型维护对齐的手写状态。

### 与 CC 刻意不同的三处（我定的，非用户拍板；升格候选见 ../../decisions.md）

1. **索引由框架写，不由模型写**。CC 靠系统提示词让模型自己往 `MEMORY.md` 加一行；
   pai 由 `remember` 落盘后重建。理由同问 2 的选择理由。
2. **`description` 一个字段兼任 CC 的两份文案**。CC 的 frontmatter `description`
   （给召回器读）与索引行的钩子（给主模型读）是模型写的两个不同字符串
   （本机实测：`"pai 项目每个新模块的标准开发流程(superpowers 全链路),用户确认采用"`
   vs `superpowers 全链路:brainstorm→...`）。pai 只让模型写一次，两处共用——
   少一个字段，代价是索引行不如 CC 那样为人类另行措辞。
3. **召回连续失败 3 次后本会话停用**。CC 是「失败返回 `[]` 不阻断」，在 pai 会变成
   每轮白打一次请求；沿用 `MAX_COMPACT_FAILURES` 的熔断文化（D#14）。

## 结果与总结

7 task 严格 TDD 交付，`./test.sh` → **458 passed, 3 deselected**（基线 385，净增 73 条）。
详细日志见 [devlog.md](devlog.md)，两条升格的取舍见 [D#55](../../decisions.md)（索引是投影）
与 [D#56](../../decisions.md)（召回照 CC + 三处成本约束）。

| 交付项 | 落点 |
|---|---|
| frontmatter 写入 + 同名即更新 | `core/tools/memory_tool.py`（`remember(name, description, fact, type)`） |
| 目录扫描（前 30 行 / mtime 排序 / 截 200） | `core/memory.py::scan_memories` |
| 索引投影（不再打补丁） | `core/memory.py::render_index` + `memory_tool._rebuild_index`（原子写） |
| 新鲜度（相对时间 + 陈旧警告） | `core/memory.py::memory_age` / `freshness_note` |
| 召回层（manifest → 侧查询 → 白名单 → 注入块） | `core/recall.py`（新模块） |
| 接线（loop 只认一个回调） | `core/loop.py::run_agent(recall=...)`、`modes/{once,interactive}.py` |
| 便宜档配置 | `config.recall_model()`（`PAI_RECALL_MODEL`） |

**刻意没做的**（spec 非目标，逐条有理由）：`recentTools` 去噪、召回开关配置、
`MEMORY.md` 自动剪枝、200 行/25KB 按中文校准、`/memory reload`、删除记忆的工具、
旧文件迁移脚本（改为「下次写到它头上时就地补 frontmatter」）。

## 遗留问题

1. ~~**DeepSeek 的 `json_object` 未经真跑验证**~~ **已验证并修复（2026-08-11，用户授权花钱）**。
   `json_object` 被接受（没有 400），但真跑暴露了**两个离线测不出的 bug**，
   当时召回在真实环境下 100% 失效且完全静默：① `max_tokens=256`（照抄 CC）在推理模型上
   被 `reasoning_tokens` 吃光，`content` 概率性变空串（实测思考量 218/112/1941，差 17 倍）；
   ② 模型把 manifest 的 `[type]` 装饰一起抄回来，逐字相等的白名单把结果全丢了。
   连带修了根因：`_parse_selection` 原本分不清「没说话」与「明确选空」，故障永远触发不了熔断。
   已加 `RecallFailed` 事件。详见 [devlog](devlog.md) 最后一条与
   [K model-api/reasoning-models-max-tokens.md](../../../../knowledge/model-api/reasoning-models-max-tokens.md)。
2. **`recentTools` 去噪未做**（CC 有：正在用的工具，用法文档不选、但坑与警告要选）。→ TODO。
3. **召回没有开关**。唯一的「关」是记忆目录为空。真要开关应落在 `.pai/settings.json`。→ TODO。
4. **索引膨胀变快了**：一事一文件让索引行数 = 记忆条数，200 行上限比 06 时代撞得早得多。
   06 复盘质疑二（「只增不减」）因此更急，且**本次没有引入任何收缩机制**——
   CC 靠写入侧提示词让模型查重/删除，pai 的 `remember` 能更新但不能删。→ TODO。
5. **`set_origin_session` 是第三个进程级全局注入点**——并入 TODO 里既有的那条
   （06 task 6：`set_memory_dir` / `set_notifier` 是进程级全局），不新开条目。
6. **召回块参与压缩切点计算**，与 06 遗留的「指令消息作为普通 user 消息参与切点计算」
   同一类问题：它被摘掉后不会重新召回（不像指令有重注入）。→ TODO。

## 用到的知识

- [K memory/cc-memdir.md](../../../../knowledge/memory/cc-memdir.md)
  ——本需求三条空缺的来源（读侧：`findRelevantMemories` / `memoryScan` / `memoryAge`）。
- **本机 CC 记忆目录实测**（2026-08-11，写侧格式的一手样本，走读笔记未覆盖）：
  `~/.claude/projects/<slug>/memory/` 的 frontmatter 字段、`MEMORY.md` 行格式、
  `[[wikilink]]` 交叉引用、`**Why:** / **How to apply:**` 正文约定。见 [spec.md](spec.md) 附录。
- [06-20260810-memory](../06-20260810-memory/README.md) 档案与复盘（本档案改变其交付结果）。
