# 02-compaction · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-09 · task 1 AnchorBook（锚点列表，D#32）

**目标**：把「锚只留最新一个」升级为锚点列表，为 find_cut_point 的真实差值反推打地基。

**改动**：`src/pai/core/compaction.py` 新增 `AnchorBook`（`entries`/`record`/`latest`/`reset`）。

**测试**：3 test_records_and_latest / test_turn_cost_is_adjacent_difference /
test_reset_clears_everything，RED（`ImportError`）→ GREEN；全套 **99 passed, 1 deselected**。

**遗留**：无。

## 2026-08-09 · task 2 并行 tool_calls 配对测试（R#11 补覆盖）

**目标**：给已有的并行 tool_calls 处理逻辑补测试——之前逻辑上处理了但无测试覆盖。

**改动**：`tests/test_loop.py` 新增 2 条（同序配对、合法+未知工具混发）。

**测试**：RED → GREEN；全套 **101 passed, 1 deselected**。

**遗留**：无。

## 2026-08-09 · task 3 find_cut_point（在哪下刀）

**目标**：按锚点真实差值反推切点，绝不切在孤儿 tool_result 上，锚不足两个时如实返回 1。

**改动**：`src/pai/core/compaction.py` 新增 `find_cut_point`。

**测试**：3 test（切点计算 / tool 边界前移 / 无可压返回 1），RED → GREEN；
全套 **104 passed, 1 deselected**。

**遗留**：`test_returns_1_when_nothing_can_be_cut` 钉死单锚恒返回 1——这条约束在 task 6
写 e2e 夹具时才暴露出对触发节奏的实际影响（见该 task 记录）。

## 2026-08-09 · task 4 summarize 双模式 + 实测脚手架

**目标**：调模型生成摘要，flat（拍平）/raw（原样发）两种模式；跑真实 API 实测哪种更可靠。

**改动**：`src/pai/core/compaction.py` 新增 `summarize`；`tests/test_llm_summarize_experiment.py`
打真实 API（`PAI_RUN_LLM_TESTS=1` 显式开）；evidence 落盘 6 份 JSON。

**测试**：3 test RED → GREEN；**2 轮返工**（round 1 critical：`test_compaction.py` 被整体
重写丢了 22 条既有测试，`git checkout` 恢复原文件后补加新测试；round 2：raw 模式该不该带
system 消息的仲裁，代码不动，补覆盖测试）；最终全套 **107 passed, 3 deselected**。

**遗留**：实测裁决 style 默认值留给 D#37（task 6 前定稿：`flat`）。

## 2026-08-09 · task 5 compact + 熔断状态机（D#34）

**目标**：切 + 摘 + 重建三合一；熔断成败只认压缩后首次真实 usage，不看估算值。

**改动**：`src/pai/core/compaction.py` 新增 `compact`、`CompactionState`、
`verify_compaction`、`MAX_COMPACT_FAILURES=3`。

**测试**：3 test（重建结构 / 真实 usage 判成败 / 连续 3 次熔断），RED → GREEN；
全套 **110 passed, 3 deselected**。

**遗留**：`tripped` 单向性（置位后降线不回落）无测试覆盖，已手验正确，标记 deferred。

## 2026-08-09 · task 6 接线进 loop + e2e（阶段 1 主线收尾）

**目标**：把触发/切/摘/重建/熔断整条链路接进 `run_agent`；超长单轮不压+警告的非目标路径
一并验证；`config.py`/`once.py` 透传默认配置。

**改动**：`src/pai/core/loop.py`（`run_agent` 加 `context_window`/`compaction` 两个
keyword-only 参数，触发块 + verify 块）；`src/pai/config.py`（`context_window()`）；
`src/pai/modes/once.py`（透传）；`tests/test_loop.py` 新增 3 条 e2e。

**测试**：Step 2 确认 RED（`TypeError: unexpected keyword argument 'context_window'`）→
按简报实现后跑 3 条新测试，2/3 红（`test_loop_compacts_when_over_threshold` /
`test_breaker_stops_auto_compaction` 断言失败，非 TypeError）——排查发现简报给的两处
夹具数字本身对不上已经钉死的生产语义：
1. `test_loop_compacts_when_over_threshold` 里 `usage(700)` 差 82 token 才够触发阈值
   （`anchor(710) + 尾部估算(8) = 718 < 800`）——调至 `usage(850)`，其余结构/断言不动。
2. `test_breaker_stops_auto_compaction` 的「1 超线轮 + 1 摘要轮」单轮节奏踩中
   task 3 钉死的约束（`find_cut_point` 单锚恒返回 1）：压缩后锚点簿被清空，
   下一步必然先撞「无可压」警告，要再等一轮真实 usage 才凑够两锚算出下一次切点。
   脚本改写为「warn-turn + build-turn」两步一压，断言（3 次真实压缩 + 熔断 + 最终
   `"done"`）不变，用真实 `FakeClient` 跑通后回填。
两处修正均在**新增测试范围内落笔**，未碰任何既有测试一行；`git diff` 自查确认
`test_compaction.py`/`test_loop.py` 只有 `--- a/` 头行、无 `-` 删除行。
GREEN 后全量：**113 passed, 3 deselected**（符合预期 110+3）。

**遗留**：`reserve_tokens=16384` / `keep_recent_tokens=20000` 仍无真实生产数据校准；
microcompact 评估触发条件已满足，登记 TODO。
