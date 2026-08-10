# 02-20260803-compaction —— 上下文压缩
状态：已交付（2026-08-09 终审通过；触发→切→摘→重建→熔断全链 e2e；已合并 main，待用户逐项验收）
分支：早于本字段的规矩（2026-08-10 立），未回填——分支线性叠，事后用 git 推不出「在哪条上做的」

## 需求

上下文接近窗口上限时自动压缩：`find_cut_point`（在哪下刀）→ `summarize`（调模型摘要）
→ `compact`（接进 loop，带熔断器），闭环在真实会话轨迹上跑通。

## 候选方案与确认

早期裁决（入 decisions）：切点用真实 usage 差值而非字符估算（D#32，推翻 D#19）；
压缩成败只认压缩后首次真实 usage（D#34）。

### 2026-08-09 brainstorm 三问拍板（用户；问答完整存档，规矩 6 回补）

**问 1**（D#12/16 悬案）：摘要时把历史喂给模型的方式——拍平成纯文本（pi 做法）还是
原样发消息数组（CC 做法）？背景：缓存价差 50 倍使原样发在成本上反超拍平约 32 倍，
但 CC 自陈原样发有百分之几的不听话率（模型把「给历史写摘要」误解成「继续干活」），
DeepSeek 上未知。
- 候选 A·先小规模实测再定：真实轨迹两种方式各跑 ≥3 次，比不听话率与含缓存真实成本；
  实测方案写进 spec，数据进 decisions
- 候选 B·先按拍平实现：不花钱、行为确定（纯文本没有不听话问题）；代价是放弃 50 倍
  缓存价差，原样发留作日后对照实验
- 候选 C·直接原样发：吃满价差；赌 DeepSeek 听话，不听话率不实测，压缩失败才发现
**选择**：A。理由：这条悬了两轮就是因为没数据，几毛钱买个定论最便宜。

**问 2**：超长单轮的兜底——pai 选了「只在轮次边界下刀」（比 pi 更强的约束，
D#32 注记），若单轮自身就超过保留预算怎么办？背景：1M 窗口下触发点约 98 万 token，
当前全天用量 3 万，几乎不可能碰到。
- 候选 A·不压+警告，靠预算熔断兜底：YAGNI——检测到即落盘警告不压，现有熔断器兜底
  停机；复杂兜底真碰到再设计（TODO 留记）
- 候选 B·轮内清旧工具结果：microcompact 思想，保留轮结构只替换该轮工具结果内容——
  现在实现，代价是为几乎不触发的路径写代码和测试
- 候选 C·支持劈轮：学 pi 的 isSplitTurn，最完备也最复杂，需重开 D#32 裁决
**选择**：A。理由：为触发不了的路径写复杂逻辑违反精简立意。

**问 3**：拍平 vs 原样发实测会打真实 API（花钱副作用需显式确认），何时执行？
- 候选 A·实现 summarize 时顺带执行：代码即实验脚手架，此刻确认即授权，届时不再问
- 候选 B·spec 定稿后立即单独实测：结论更早，但探针代码用完即弃
- 候选 C·执行前再问一次：最谨慎，多一次打断
**选择**：A。理由：不写一次性探针；本次确认即花钱授权（预算 1 元内，
走 `PAI_RUN_LLM_TESTS=1` 显式通道）。

## 实施

superpowers 全链路：[spec.md](spec.md)（2026-08-09 定稿，用户已批）→
[plan.md](plan.md)（2026-08-09 定稿：6 task 全量代码 TDD）→ SDD（feat/compaction 分支）。
P0 清障已完成（R#3/4/7/8/9 五条，见 docs/dev/archive/devlog-2026-08.md 对应条目）。

## 结果与测试

6 个 task 严格 TDD（红→绿）跑完，[plan.md](plan.md) 全量代码交付，进度台账见
`.superpowers/sdd/plan/progress.md`：

| task | 内容 | 提交后全套 |
|---|---|---|
| 1 | `AnchorBook`（锚点列表，D#32） | 99 passed, 1 deselected |
| 2 | 并行 tool_calls 配对测试（R#11） | 101 passed, 1 deselected |
| 3 | `find_cut_point`（在哪下刀） | 104 passed, 1 deselected |
| 4 | `summarize` 双模式 + 拍平/原样发实测脚手架（2 轮返工，见 progress.md） | 107 passed, 3 deselected |
| 5 | `compact` + 熔断状态机（D#34） | 110 passed, 3 deselected |
| 6 | 接线进 loop + e2e（含超长单轮警告） | 113 passed, 3 deselected |
| 终审 | 最强模型全分支审查 With fixes → 修复波 4/4 addressed 复审 clean（Critical：摘要 usage 漏记预算——计划自带 bug） | **115 passed, 3 deselected** |

Task 6 的 e2e 夹具撞出一条此前只在理论上成立的约束：`find_cut_point` 需要 ≥2 个锚点
才能算真实差值，而 `compact()` 后锚点簿被清空——意味着**压缩后若仍处于超线状态，
下一步必然先撞见「无可压」警告，再等一轮真实 usage 落盘才凑够两锚、算出下一次真实
切点**。`test_breaker_stops_auto_compaction` 把简报原稿设想的「一超线就压」单轮节奏
改写为「warn-turn + build-turn」两步一压，详见 STATUS 缺陷 1 与代码注释（find_cut_point 与 loop 触发块）。

## 遗留问题

均在 TODO：`reserve_tokens=16384` / `keep_recent_tokens=20000` 实测校准（阶段 1 主线跑通
但仍是从 pi 借来的经验值）、microcompact 评估（触发条件已满足）。
P0/P1 清单已全部划掉，出处见对应 TODO 条目。

## 用到的知识

[knowledge/claude-docs/context-management.md](../../../../knowledge/claude-docs/context-management.md)、
[knowledge/source-walks/cc-compaction.md](../../../../knowledge/source-walks/cc-compaction.md)
