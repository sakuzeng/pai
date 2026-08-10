# CC 的 memdir 走读：记忆是怎么被「想起来」的

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `src/memdir/`：`findRelevantMemories.ts`(141) / `memoryScan.ts`(94) / `memoryAge.ts`(53)
  （另有 `memdir.ts` 507 行、`memoryTypes.ts` 271 行、团队记忆三件套，本篇不覆盖）
- 精读日期：2026-08-10
- pai 锚点：`src/pai/core/memory.py`、`src/pai/core/tools/memory_tool.py`、
  docs/dev/features/06-20260810-memory（阶段 3）

**为什么读这篇**：roadmap 阶段 3 的「参照」栏写了 `src/memdir/`，我动工时只读了官方文档
没走源码，交付后在复盘里留下一个悬案——`findRelevantMemories` 这个名字暗示可能有
**相关性筛选**，若属实，pai 的「全靠模型自己想起来 `read_file`」就是明显更弱的设计。
**答案：属实。而且比想象的更完整。**

## 一、两层结构：常驻索引 + 按查询召回

官方文档只说了第一层（`MEMORY.md` 每会话加载、主题文件「Claude 用其标准文件工具按需读」）。
源码里的第二层是文档没写的：

```
MEMORY.md        → 进 system prompt，常驻（findRelevantMemories 显式排除它）
主题文件 *.md    → 每次查询，用一个便宜模型选出 ≤5 篇塞进上下文
```

所以「按需读」不是「模型自己想起来去读」，而是**框架主动召回**。
pai 现在只有第一层，第二层完全空缺——悬案的结论就在这里。

## 二、召回怎么做：拿 header 清单去问一个便宜模型

`findRelevantMemories(query, memoryDir, signal, recentTools, alreadySurfaced)`：

1. `scanMemoryFiles` 扫目录，**每个文件只读前 30 行**（`FRONTMATTER_MAX_LINES`）
   解析 frontmatter，取 `description` 与 `type`；按 mtime 新→旧排序，**截断 200 个**。
2. 拼成 manifest，一行一个文件：`- [type] filename (ISO时间): description`。
3. `sideQuery` 打 **Sonnet**（`getDefaultSonnetModel()`，即便宜档），
   `max_tokens: 256`，用 **JSON schema 强制**输出 `{selected_memories: string[]}`。
4. 返回的文件名**再过一遍白名单**（`validFilenames.has(f)`）——模型可能编出不存在的文件名。
5. 任何失败/中止 → 返回 `[]`，不阻断主流程。

**成本控制的两处细节值得单独记**：

- 只读前 30 行而不是全文，所以 manifest 恒定很小——召回的输入成本与记忆总量**几乎无关**；
- `readFileInRange` 内部 stat 并回传 `mtimeMs`，于是是 **read-then-sort** 而不是
  stat-sort-read。注释算过账：N ≤ 200 时省一半 syscall。

## 三、选择器的 prompt 里有三条精细的去噪规则

系统提示原文的要点：

1. **「不确定就别选」**——`Only include memories that you are certain will be helpful`，
   并明说「宁可返回空列表」。默认偏向不召回，而不是宁滥勿缺。
2. **上限 5 篇**，写在 prompt 里而不只是代码里截断。
3. **`recentTools` 去噪，且区分得很细**：正在用的工具，它的**用法/API 文档不要选**
   （对话里已经有真实用法了）；但**关于这些工具的警告、坑、已知问题仍然要选**——
   注释里那句「active use is exactly when those matter」是这条规则的理由。
   代码注释还点出了它防的是什么：关键词重叠导致的误命中
   （query 里有 "spawn" + 某篇记忆描述里有 "spawn" → 假阳性）。

另有 `alreadySurfaced`：**在调用模型之前**先滤掉前几轮已经出现过的文件，
免得选择器把 5 个名额浪费在调用方马上会丢弃的东西上。

## 四、`memoryAge.ts`：本次走读最值得抄的一小块

53 行，但每一段注释都是一条设计判断：

```ts
memoryAge(mtimeMs)  // "today" / "yesterday" / "47 days ago"
```

> 注释原文（转述）：**模型不擅长日期算术——原始 ISO 时间戳不会触发「这条可能过期了」
> 的推理，而「47 days ago」会。**

```ts
memoryFreshnessText(mtimeMs)  // >1 天才返回非空
```

> 这条记忆已经 N 天了。记忆是**时间点观察，不是实时状态**——
> 关于代码行为的断言或 file:line 引用可能已经过期，当成事实之前先核对当前代码。

**动机注释直接写了它在填什么坑**：用户报告过「陈旧的代码状态记忆被当作事实断言」，
而且——**带 file:line 的引用会让一条过期声明听起来更权威，而不是更不权威**。

≤1 天不加警告（新鲜时警告是噪音）。包装成 `<system-reminder>` 注入。

## 五、对 pai 的落差与建议

| 能力 | CC | pai 现状 |
|---|---|---|
| `MEMORY.md` 索引常驻上下文 | ✅ | ✅ 已做（含 200 行/25KB 上限） |
| 主题文件**按查询召回** | ✅ 便宜模型选 ≤5 | ❌ **全靠模型自己想起来 read_file** |
| 记忆文件带 `description` frontmatter | ✅ 召回全靠它 | ❌ `remember` 写的是裸 bullet |
| 新鲜度/陈旧警告 | ✅ 相对时间 + 警告语 | ❌ 只写了日期，无任何提示 |
| 召回失败降级 | ✅ 返回空，不阻断 | — |

**悬案裁决**：pai 的设计确实更弱，且弱在「召回」这一层——不是实现质量问题，是**少了一层机制**。

但要不要照抄，有一个 pai 特有的成本约束：CC 的召回是**每次查询多打一次模型**。
pai 有预算熔断文化（`max_total_tokens` 默认 20 万），多一次 side query 是实打实的钱。

**所以建议分两档**：

1. **零成本、现在就该做的两条**（不需要额外模型调用）：
   - `remember` 写入时带 **`description` frontmatter**——即使暂不做召回，
     这是「将来能召回」的前提，不写就是给未来挖坑（现有记忆文件届时要回填）；
   - **新鲜度**：`memoryAge` 那套完全不用调模型，写入日期 pai 已经有了。
     加一句相对时间与「记忆是时间点观察不是实时状态」的警告，
     直接对治「过期记忆被当事实断言」——而这个坑 pai 迟早会踩，CC 已经替我们踩过了。
2. **要拍板的一条**：召回层做不做、用什么模型、要不要限成「只在 `MEMORY.md` 索引
   放不下时才召回」。这属于阶段 3 的增量，建议单独立档案而不是塞进阶段 4。

三条都已登记 TODO。
