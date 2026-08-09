# 02-20260803-compaction · spec

2026-08-09 brainstorm 定稿（三问拍板记录见 README「候选方案与确认」）。

## 背景与问题

loop 目前只测量不决策：`context_tokens` 每步算并落盘（误差 1.3%），但
`should_compact` 未接线，超警戒线也不压。压缩闭环缺三件事：在哪下刀、怎么摘要、
怎么重建并确认压成功了。

## 目标（做什么）

1. `find_cut_point`：用真实 usage 差值定切点（D#32）——loop 维护**锚点列表**
   `[(message_index, real_tokens), ...]`，相邻差值即每轮真实成本；切点只落轮次边界，
   保留段绝不以孤儿 tool_result 开头；未锚定尾部用字符估算。
2. `summarize`：调模型生成摘要。喂料方式（拍平 vs 原样发）**实测定**，见下。
   prompt 骨架 = 官方六项保留清单（用户意图/技术概念/文件与代码片段/错误及修法/
   待办/当前工作），`instructions` 参数化可覆盖；`serialize_conversation` 跳过
   system 消息（R#16，否则 system 同时出现在拍平文本与新上下文里）。
3. `compact`：切 + 摘 + 重建（system + 摘要消息 + 保留尾部）+ **anchor 列表全部
   重置**（D#18/D#32，锚定法假设 append-only）；压缩成败**只认压缩后首次真实
   usage 回传**（D#34）；熔断器：连续失败 3 次停止自动压缩（对齐 CC）。
4. 接线：`should_compact` 进 loop（发请求前判）；`window <= reserve` 退化情形由
   熔断器兜底（D#14，现 STATUS 缺陷 4）。
5. 补齐并行 tool_calls 测试（R#11，P0 遗留，有真实 400 复现路径）。

## 非目标（明确不做）

- microcompact（阶段 1 完成后单独评估，TODO 已记）
- 超长单轮的复杂兜底——**裁决（2026-08-09）：不压 + 落盘警告，靠预算熔断兜底**；
  轮内清结果/劈轮等真碰到再设计（1M 窗口下触发点 98 万 token，当前全天用量 3 万）
- 流式下的 usage 归一化（阶段 5 前置）；跨会话压缩

## 实测设计（拍平 vs 原样发，唯一花钱步骤）

- 时机：实现 `summarize` 的 task 时顺带执行，代码即实验脚手架（**用户已确认**，
  预算 1 元内，走 `PAI_RUN_LLM_TESTS=1` 显式通道）。
- 方法：同一段真实轨迹（会话 JSONL），拍平/原样发各跑 ≥3 次摘要请求。
- 判据：① 不听话率（输出是摘要还是「继续干活」）② 含缓存的真实成本
  （`prompt_cache_hit_tokens` 计入）③ 摘要长度与保留信息质量（对照六项清单）。
- 落盘：数据进 decisions 新条目（裁决拍平还是原样发），摘要长度顺带校准
  `reserve_tokens=16384`（现无实测依据，STATUS 缺陷 3）。

## 验收标准

- 真实轨迹夹具端到端（离线，fake provider 扮演摘要模型）：触发 → 切点 → 摘要 →
  重建 → 锚重置 → 压缩后首次真实 usage 判成败 → 连续失败熔断，每环有测试钉死。
- 并行 tool_calls：一轮 3 个 tool_calls 各回一条的配对不变量有测试（R#11）。
- `./test.sh` 全绿全离线；实测数据落 decisions/STATUS；每步红→绿数字进本目录 devlog.md。
