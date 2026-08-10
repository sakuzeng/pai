# 10-memory-recall · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-11 · 立项与拍板

**目标**：把 06 交付时留下的三条空缺（frontmatter / 新鲜度 / 召回层）合成一次交付。

**改动**：新建档案 `10-20260811-memory-recall/`（README 含两问拍板全文存档、spec、plan），
`docs/dev/需求池.md` 记用户原话并标「升格」，`.active` 指向本档案，开分支 `feat/10-memory-recall`。

**分析里最值钱的一步**：发现三条不是并列的，**粒度 × 索引是否全量 × 召回是否存在**互相锁死
——「一事一文件」只有在有召回层时才成立，否则索引行数 = 记忆条数，200 行上限提前撞。
所以拍板顺序与 TODO 记的**相反**：先拍召回层，粒度才有唯一解。

**新查出的第四条空缺（TODO 未登记）**：`MEMORY.md` 索引行只有主题名与链接
（`- [约定](约定.md)`，`memory_tool.py:84`），连一句描述都没有——模型在上下文里
看到的全部信息是「有个文件叫 `约定.md`」。三条 TODO 里最便宜、收益最大的一条反而没被记下。

**一手证据**：走读笔记 [K cc-memdir](../../../../knowledge/source-walks/cc-memdir.md) 只覆盖读侧
（`findRelevantMemories` / `memoryScan` / `memoryAge`）。本次在**本机 `~/.claude/projects/<slug>/memory/`
读到了活的 CC 记忆文件**，补上了写侧格式的四条（详见 spec 附录一）：`description` 与索引钩子是
两个不同字符串、`modified` 是写进 frontmatter 的 ISO 戳、`originSessionId` 能回指会话、
`node_type: memory` 那层套娃不抄。

**测试**：本步无代码改动。基线 `385 passed`（feature 09 交付时）。

**遗留**：无（拍板阶段）。

## 2026-08-11 · Task 1：frontmatter 解析与目录扫描

**目标**：把召回与索引投影共用的那层扫描先钉死——两个消费者都建在它上面。

**改动**：`src/pai/core/memory.py` 加 `MemoryHeader` / `parse_frontmatter` / `scan_memories`
与三个常量（`FRONTMATTER_MAX_LINES=30`、`MAX_SCANNED=200`、`LEGACY_TYPE`）；
新增 `tests/test_memory_scan.py`（11 条）。

**决定不引 PyYAML**：frontmatter 是我们自己的工具写出来的，只需认「`---` 围栏 +
`key: value` + 缩进的 `metadata:` 块」这个子集。为解析自己产生的 6 行文本引一个新依赖
不划算。不认识的键原样收着而不是报错——CC 那边多出来的 `node_type` 不会把扫描弄红。

**解析器的一条硬边界**：`parse_frontmatter` 自己也只看前 30 行，
**窗口内没见到收尾围栏就一律当没有 frontmatter**。否则「每文件只读前 30 行」
这条成本约束会被解析器悄悄破坏（manifest 的输入成本与记忆总量无关，全靠这个）。

**测试**：红 `ImportError: cannot import name 'FRONTMATTER_MAX_LINES'` → 绿 `11 passed`。

**遗留**：无。

## 2026-08-11 · Task 2：索引改投影 + 新鲜度

**目标**：`MEMORY.md` 从「账本」变「投影」，并把相对时间接上。

**改动**：`memory.py` 加 `memory_age` / `freshness_note` / `render_index` / `INDEX_HEADER`，
`load_memory_index` 重写为 `scan → render → 截断`；新增 `tests/test_memory_index.py`（11 条）；
改写 `tests/test_memory.py` 里 4 条 06 时代的索引测试（旧语义是「原样读 MEMORY.md」）。

**判据测试**：`test_index_is_derived_from_files_not_from_the_disk_index`——盘上 MEMORY.md
写着一行陈旧内容、目录里是另一套文件，断言拿到的是**文件**那套。账本实现在这条上必红。
（06 复盘第二节的教训：三条测试里只有一条能分辨真假实现，那条才是核心。）

**实现中新想到的一条**：`render_index(headers, now=None)` —— `now` 为 None 就不渲染相对时间。
理由是**相对时间是渲染时刻的函数，写进持久文件就会腐坏**，而「一条三个月前的记忆在文件里
写着『今天』」正是新鲜度这条特性要防的东西。所以盘上那份不带时间，进上下文的那份才带。
拍板讨论时没想到这一层，是写测试时被 `render_index` 的两个消费者逼出来的。

**截断提示改词**：旧提示写「需要时用 `read_file` 直接读该文件」——读侧已经不读那个文件了，
指错了地方；且有召回层之后，放不进常驻区不再等于「那条记忆不存在」。

**测试**：红 `ImportError: cannot import name 'freshness_note'` → 本文件绿 `11 passed`；
全量先红 `4 failed, 402 passed`（4 条旧语义测试），改写后全量绿 `406 passed, 4 skipped`。

**遗留**：无。

## 2026-08-11 · Task 3：remember 改「一事一文件 + 更新语义 + 索引重建」

**目标**：写侧改成 CC 的形状，并把「先找已有的、更新而不是新建重复的」这条**写入纪律**
从提示词降到工具里（CC 靠系统提示词让模型自觉，pai 靠 `remember` 结构上保证）。

**改动**：
- `src/pai/core/tools/memory_tool.py` 重写：`remember(name, description, fact, type="project")`，
  frontmatter 渲染、同名更新（正文追加 / `description` 与 `modified` 覆写）、
  写完 `_rebuild_index`（投影 + 原子写）、新增 `set_origin_session` 注入点；
- `src/pai/core/tools/fs.py`：`_atomic_write` 提为公开 `atomic_write`（两个调用点跟改）——
  记忆索引也要原子写，跨模块 import 一个下划线开头的私有函数是坏味道；
- `tests/test_tools.py`：06 段 6 条随签名改写 + 新增 8 条；
- `tests/test_interactive.py`：REPL 那条脚本里的 `remember` 参数跟改。

**两个实现期才想清楚的点**：
1. **`originSessionId` 更新时不覆写**——它记的是**产生**这篇记忆的那次会话，
   不是最后一次动它的会话；后者由 `modified` 表达。两个字段各管各的。
2. **旧文件就地补 frontmatter**：`_split_existing` 对没有 frontmatter 的文件把整篇当正文，
   于是下次写到它头上时自动补齐、旧内容原样留着。这就是 spec 里「不写迁移脚本」的兑现方式，
   比写迁移脚本更好——迁移脚本要求人记得跑一次。

**测试**：红 `7 failed, 2 passed`（`TypeError: remember() got an unexpected keyword argument 'name'`）
→ `tests/test_tools.py` 绿 `41 passed`；全量绿 `414 passed, 4 skipped`。

**遗留**：`set_origin_session` 是第三个进程级全局注入点（`set_memory_dir` / `set_notifier`
之后），与 TODO 里「06 task 6：注入点是进程级全局，有并发就要重新考虑」是同一条账，
不新增 TODO，在既有那条上补一笔。

## 2026-08-11 · Task 4/5：召回选择器与注入块

**目标**：把 06 复盘留的悬案「pai 少了一整层机制」补上。

**改动**：新增 `src/pai/core/recall.py`（`RecallState` / `build_manifest` /
`_parse_selection` / `select_memories` / `recall_block`）与 `tests/test_recall.py`（19 条）。

**照 CC 的**：header 拼 manifest（成本与记忆总量无关）、上限 5 写进 prompt 而不只在代码里
截断、`alreadySurfaced` 在**调模型之前**过滤、返回文件名过白名单、失败返回空不阻断。

**比 CC 多的三处**（都是预算文化逼出来的，已升格 D#56）：空目录/全已注入不发请求、
usage 回传给熔断账、连续 3 次失败本会话停用。**不押在 provider 上的一处**：
只用 `json_object` 不用严格 `json_schema`，正确性靠防御式解析（抓第一个 `{...}`）+ 白名单。

**测试**：红 `ModuleNotFoundError: No module named 'pai.core.recall'` → 绿 `19 passed`。

**遗留**：`recentTools` 去噪没做（CC 会区分「正在用的工具，用法文档不选、但坑与警告要选」）
——需要给 loop 加一条「最近用了哪些工具」的管线，记忆量还没到需要它的规模。已登记 TODO。

## 2026-08-11 · Task 6：接进 loop

**目标**：让 loop 用上召回，但**不认识**记忆。

**改动**：`run_agent` 加 `recall: Optional[Callable[[str], tuple]]`，在 task 消息之后调用一次；
空文本不插消息、usage 计进 `spent_tokens`、异常降级成「没召回」。
`tests/test_loop.py` 新增 5 条。

**接口形状是抄自己的**：与既有的 `instructions: Callable[[], str]` 同构——
装配层把 client/模型/目录/状态关进闭包，loop 只看见一个回调。
这样 loop 的测试可以注入假 callable，召回的测试可以注入假 client，两边都不用碰对方。

**测试**：红 `5 failed, 51 passed`（`TypeError: run_agent() got an unexpected keyword
argument 'recall'`）→ 绿 `56 passed`。

**遗留**：无。

## 2026-08-11 · Task 7：装配层、配置与真实轨迹

**目标**：两个模式接线，把 `RecallState` 交给该持有它的那一层。

**改动**：`config.recall_model()`（`PAI_RECALL_MODEL`，回落主模型）；
`modes/once.py` 与 `modes/interactive.py` 构建 `make_recall(...)` 闭包 +
`set_origin_session(session.session_id)`；`_run_turn` 透传 `recall`；
`tests/test_config.py` +2、`tests/test_modes.py` +2、`tests/test_interactive.py` +1、
`tests/test_recall.py` +3（含真实轨迹）。

**一个只有写测试才会撞见的顺序坑**：`run_interactive` 里 `model = model or model_name()`
在前，如果召回模型也写成 `model or recall_model()` 放在它后面，**注入的 model 永远非空**，
`PAI_RECALL_MODEL` 就成了一条永远走不到的分支。必须在兜底**之前**算。

**真实轨迹测试**（AGENTS.md 规约）：`test_real_trajectory_query_flows_through_recall_and_compaction`
——拿 `REAL_USAGE_TRAJECTORY`（源自 `pai_playground/sessions/20260802-235657.jsonl`）里的
真实中文 query 走一遍召回，断言它原样进了 manifest 请求；再把注入块接进压缩的体积计算，
断言 `context_tokens` 确实变大、`find_cut_point` 不炸。

**测试**：各文件先红（`ImportError` / 断言失败）→ `./test.sh` 全绿
`447 passed, 3 deselected`（基线 385，本需求净增 62 条）。顺带更新 STATUS 的模块表与测试数。

**遗留**：见档案「遗留问题」。

## 2026-08-11 · 收尾：离线冒烟抓到一个静默降级

**目标**：真写一遍记忆看产物长什么样（`pai_playground` 之外的纯离线冒烟，不打 API）。

**抓到的问题**：第二次 `remember` 不传 `type`，把第一次写的 `feedback` **静默降回了
`project`**。根因是 `@tool` 的默认值让「没传」与「传了默认值」不可区分，
而我把默认值写成了 `"project"`。

**改法**：默认值改成空串，实现里回落 `已有 type > DEFAULT_TYPE`；补两条测试
（`test_update_keeps_the_existing_type_when_not_specified` /
`test_new_memory_without_type_defaults_to_project`）。

**这条值得记的地方**：`test_same_name_updates_instead_of_creating_a_second_file` 断言了
description 会覆写、正文会追加，唯独没断言 type——**测试覆盖了「该变的变了」，
漏掉了「不该变的没变」**。冒烟只花了一分钟就把它露出来，因为人眼看产物时
「咦这里怎么是 project」是本能反应，而写断言时想不到要断言它。

**测试**：红 `1 failed`（`assert 'project' == 'feedback'`）→ `./test.sh` 全绿
`449 passed, 3 deselected`。

**遗留**：无。

## 2026-08-11 · 真跑冒烟（用户授权花钱）：抓到两个离线测不出的 bug

**目标**：兑现 spec 风险项与遗留 1——真实 provider 到底接不接受 `json_object`。

**结论比预期糟**：`response_format={"type":"json_object"}` **被接受**（没有 400），
但**召回在真实环境下 100% 失效**，而且离线测试全绿、没有任何告警。两个独立原因：

**bug 1 · `max_tokens=256` 把预算喂给了思考。** `deepseek-v4-flash` 是推理模型，
`reasoning_tokens` 计进 `max_tokens`。实测同一 query 三次，思考分别烧掉
**218 / 112 / 1941** token（差 17 倍）——256 会概率性地让 `content` 变成空串。
那个 256 是照抄 CC 的，而 CC 那一档用的是**不推理的 Sonnet**。
**常数是跟着模型类别走的，不是跟着任务走的**（同 06 复盘质疑四「照抄官方数字」那类债）。
→ 改 4096，常量旁写明不许调小：计费按真实用量走，调高不花钱，调低只会静默丢结果。

**bug 2 · 模型把 manifest 的装饰一起抄了回来。** 清单行是
`- [feedback] 构建约定.md (今天): 描述`，提示要求只输出文件名，它回的是
`"[feedback] 构建约定.md"`。白名单原本要求**逐字相等**，于是**全部选择结果被静默丢弃**——
这是「离线全绿、线上全废」的教科书案例。
→ 白名单仍然说了算，但匹配放宽：在模型回的串里**找**已知文件名，**取最长匹配**
（否则 `a.md` 会抢走 `xa.md` 的票）；同时在 prompt 里加一句「只写文件名，别抄 `[类型]`」。

**顺带修的第三处（bug 1 之所以静默的根因）**：`_parse_selection` 原本把
「解析不出来」和「明确选了空列表」都返回 `[]`，于是**故障永远触发不了熔断、也发不出事件**。
改成返回 `Optional`：`None` = 故障（计数 + 回调），`[]` = 正常判断。

**新增 `RecallFailed` 事件**（用户同意的那条建议）：`core/events.py` 加事件与渲染，
`core/recall.py` 用 `RecallFailure` 回调（核心模块不认识事件系统，同 `memory_tool` 的做法），
两个模式在装配层把回调转成事件。

**改动**：`core/recall.py`、`core/events.py`、`modes/{once,interactive}.py`；
`tests/test_recall.py` +8、`tests/test_events.py` +1；
沉淀 [K concepts/reasoning-models-max-tokens.md](../../../../knowledge/concepts/reasoning-models-max-tokens.md)；
量测脚本 `pai_playground/smoke/recall_{json_object,max_tokens}.py`。

**测试**：红 `6 failed, 24 passed` → `./test.sh` 全绿 `458 passed, 3 deselected`。

**修复后重跑真冒烟**（端到端确认）：
```
query='测试怎么跑？'                → 选中 ['构建约定']   total_tokens=454
query='帮我看看 loop.py 有没有 bug' → 选中 []            total_tokens=584
query='压缩什么时候触发'            → 选中 ['压缩阈值']   total_tokens=513
```
第二条是空的，符合预期——那三篇确实都不相关，「不确定就别选、宁可返回空」这条去噪规则生效了。
单次召回成本约 500 token。

**遗留**：无新增；遗留 1 已核销。

## 2026-08-11 · 量测原件归档（规矩 9）

**目标**：D#56 与 knowledge 笔记引用的数字，脚本却在 gitignore 的 `pai_playground/` 里——
溯源链会断（TODO 里已经有一条同样的旧账：测试夹具的出处在 playground）。

**改动**：按 features/README 规矩 9 建
`evidence/20260811-召回真跑冒烟/`（两个脚本 + 两份输出 + 说明）。

**归档时重跑一次，拿到了比第一次更有力的证据**：同一 prompt 同一 query，
第二次跑里 **`max_tokens=512` 全部 512 个 token 烧在思考上、content 为空，
而 256 反而成功了**。两次合看，reasoning 在 38 ~ 1941 之间抽签，**且不单调**。

这把结论从「256 太小」推进到了**「没有哪个小上限是安全的」**——
「调到刚好够用」这个思路本身不成立。笔记与 evidence 说明都按这个改写了。

**测试**：`./test.sh` 全绿 `458 passed, 3 deselected`（本步只动文档与 evidence）。

**遗留**：无。
