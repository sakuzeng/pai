# 当前状态快照

最后更新：2026-08-10（阶段 2 REPL + 阶段 3 记忆交付；交付后五个补漏，见 features/05 devlog）。
**数字由机器对账**：`test_status_reports_the_current_test_count` 会在完整跑时校验本页的 passed 数——漂了三次之后不再靠人肉。
给接手者（人或 AI）一页看清现状。
「做了什么」的时间线见 [devlog.md](devlog.md)，「为什么这么选」见 [decisions.md](decisions.md)，
功能级故事线见 [features/](features/README.md)，阶段地图见 [roadmap.md](roadmap.md)。

## 一句话

agent loop + 工具系统 + 会话落盘 + 阶段 1 压缩闭环已跑通；阶段 2 前半程**交互模式（纯 REPL）
已交付**——结构化事件流、steering/followUp 双队列、中断到进程组、`/` 命令与 `!` shell 模式、
AskUserQuestion、工具状态行。`pai` 不带参数即进 REPL。
阶段 3 **记忆已交付**——`PAI.md` 三层加载 + `@` 导入 + 自动记忆索引 + `remember` 写回，
且**压缩后从磁盘重读重注入**（不做就是长会话里指令静默失效）。
两个功能全貌见 [features/02-20260803-compaction/](features/02-20260803-compaction/README.md)
与 [features/05-20260810-repl/](features/05-20260810-repl/README.md)。

## 模块现状

| 模块 | 状态 | 说明 |
|---|---|---|
| `core/loop.py` | 可用 | agent loop：依赖注入、max_steps 兜底、每条消息落盘、usage 落盘、用量预算熔断、自动压缩触发/熔断 |
| `core/tools/` | 可用 | `@tool` 从签名生成 schema；bash / read_file / write_file / edit_file |
| `core/compaction.py` | 可用 | 见下——阶段 1 主线（触发→切→摘→重建→熔断）全部接进 loop |
| `modes/once.py` | 可用 | 单次任务，跑完即退出（对应 pi 的 print-mode）。client/model 可注入故可离线测；`context_window()` + `CompactionSettings()` 默认透传 |
| `viz/` | 可用 | `pai-viz` 本地架构可视化：工具自省自动上图，阶段状态解析本表 |
| `cli.py` / `config.py` | 可用 | cli 只做参数解析与分发；OpenAI 兼容协议打 DeepSeek；`context_window()` 读 `PAI_CONTEXT_WINDOW`，默认 1_000_000（v4-flash） |
| `modes/interactive.py` | 可用 | REPL：跨轮持有 messages/锚点簿/熔断状态；历史（按 cwd 分文件、连续重复只记一条）、`\` 续行、`!` shell 模式、`/help /status /compact /clear /exit`、两级 Ctrl+C；API 出错不炸会话 |
| `core/events.py` | 可用 | 10 个 frozen dataclass 扁平联合 + `render_text` 默认渲染器（D#39）。`on_event` 现在收事件对象，渲染下放 modes 层 |
| `core/queue.py` | 可用 | `PendingMessageQueue`（all/single 两种 drain）。followUp 已通电；**steering 有注入点无输入源**（阻塞 input 拿不到「干活时打字」，等 TUI/流式） |
| `core/interrupt.py` | 可用 | 进程级中断标志（D#40）。loop 在步边界与每个 tool_call 前查，bash 在轮询里查 |
| `modes/statusline.py` | 可用 | `render_tool_line(events, width)` 纯函数（按终端列宽算中文宽度）+ `\r` 原地刷新；真 tty 才启用，非 tty 退回滚动行 |
| `core/tools/ask.py` | 可用 | AskUserQuestion，asker 装配期注入；**默认工具集不含它**（once 无真人可问） |
| `core/paths.py` | 可用 | pai 用户级路径唯一事实源：`~/.pai/projects/<可读 slug>/{memory,sessions}/`，slug 用全路径连字符（D#44，对齐 CC） |
| `core/session.py` | 可用 | append-only JSONL，落**用户目录**不再写当前工作目录；每条带 `sessionId`/`cwd`；文件名带短 id（D#45，关掉 R#15） |
| `core/memory.py` | 可用 | 分层指令发现（用户级→根→cwd，local 在后，**不读 AGENTS.md** D#43）、`@path` 导入（相对基准/4 跳/环检测/代码块内不算）、自动记忆索引（git 根定 key，200 行 + 25KB 双上限，截断留提示） |
| `core/tools/memory_tool.py` | 可用 | `remember(topic, fact)` 写主题文件 + 维护索引；topic 白名单校验挡路径穿越；目录与通知回调走注入点 |
| permissions / streaming / skills / mcp_client / evals | 未开始 | 路线图后续阶段，见 [roadmap.md](roadmap.md)。阶段 2 后半程 TUI 亦未开始 |

## compaction.py 里有什么

| 函数 | 干什么 | 接进 loop 了吗 |
|---|---|---|
| `estimate_tokens` | 单条消息 token 估算，中英文分别按官方系数（0.6 / 0.3） | 间接 |
| `estimate_conversation_tokens` | 整段消息求和 | 间接 |
| `estimate_request_tokens` | 加上工具 schema，对齐 provider 的 prompt_tokens 口径 | 间接 |
| `context_tokens` | **以真实 usage 为锚 + 增量估算**，误差 1.3% | ✅ 每步算，落盘，且是压缩触发判断的输入 |
| `should_compact` | 阈值判断（`tokens > window - reserve_tokens`） | ✅ 每步触发检查 |
| `find_cut_point` | 在哪下刀，按锚点真实差值反推，绝不切在孤儿 tool_result 上 | ✅ 触发时调用；单锚（刚压完只有 1 个真实点）时如实返回「无可压」，走警告分支——这条约束在 e2e 写夹具时被撞出来，见下方遗留 |
| `serialize_conversation` | 拍平成文本喂摘要模型 | ✅ 经 `summarize` 调用 |
| `summarize` | 调模型生成摘要，`style` 默认 `flat`（D#37 实测裁决） | ✅ 经 `compact` 调用 |
| `compact` | 切 + 摘 + 重建，调用方随后 reset 锚并置 `awaiting_verify` | ✅ 触发且有可压时调用 |
| `CompactionState` / `verify_compaction` / `MAX_COMPACT_FAILURES` | 熔断状态机，成败只认压缩后首次真实 usage（D#34） | ✅ 每步 verify，熔断后触发块整体跳过 |
| `CompactionSettings` | `reserve_tokens=16384`、`enabled=True`、`keep_recent_tokens=20000` | ✅ `once.run_once` 默认值透传 |

## 实测数据（真实跑出来的，非推测）

- 上下文估算误差：无锚 **-33%** → 锚定后 **-1.3%**
- 缓存命中率：单次会话 **91.6%**，全天统计 **84.7%**
- `deepseek-v4-flash`：上下文 **1M**、输出上限 **384K**；缓存命中 0.02 元/M vs 未命中 1 元/M（**50 倍**）
- 按 `reserve_tokens=16384`，压缩触发点是 **983,616** token——以当前用量（全天 3 万）几乎不会触发

## 测试

共收集 **279 项**（阶段 2 REPL 8 task + 阶段 3 记忆 7 task + 交付后五个补漏 + 文档一致性）：

- `./test.sh` → **276 passed, 3 deselected**，全部离线（`tests/fake_llm.py` 假 provider）。**这是默认路径。**
- `./test.sh --llm` → 额外跑打真实 API 的冒烟测试，**会产生费用**。
  需同时满足有 `DEEPSEEK_API_KEY` 且 `PAI_RUN_LLM_TESTS=1`——花钱的副作用不能是默认行为。

两份真实轨迹夹具内联在 `tests/test_compaction.py`：
`REAL_TRAJECTORY`（含一条真实的 sed 失败）、`REAL_USAGE_TRAJECTORY` + `REAL_USAGE_STEPS`。

## 已知缺陷（详细条目在 [archive/devlog-2026-08.md](archive/devlog-2026-08.md)）

1. **锚与压缩天然冲突，重置后有读数盲区——且接进 loop 后暴露出比原评审更具体的一条约束**
   （评审 R#7，D#34 已裁决熔断器只认真实 usage，本条按接线后的实况改写）。
   `compact()` 重置锚点簿之后，**下一次真实 usage 回来前只有 0 或 1 个锚点**；
   `find_cut_point` 严格要求 ≥2 个锚才能算出真实差值（`test_returns_1_when_nothing_can_be_cut`
   已钉死单锚恒返回 1）。后果：压缩后若仍处于超线状态，**下一步的触发检查必然先撞见
   「无可压」警告**，要再等一步真实 usage 落盘才能凑够两个锚点、算出下一次真实切点——
   e2e 测试 `test_breaker_stops_auto_compaction` 把这条约束从「设计推论」变成了「跑出来的
   事实」：每个熔断周期在脚本层面是 warn-turn + build-turn，不是简报原稿设想的
   「一超线就压」单轮节奏。这不是 bug，是锚定法必然的代价，只是此前没人把它摆到台面。
2. `estimate_tokens` 系统性低估约 **1.5 倍**（chat template 框架开销 + 工具 schema）。
   **仍不修**，理由见 decisions 第 19 条（划掉保留）与第 32 条（改用真实 usage 差值定切点）。
   补充实测：偏差**不均匀**——短 tool 结果低估 4-5 倍，长消息只低估约 2%。
3. `reserve_tokens=16384` / `keep_recent_tokens=20000` **仍无真实生产数据校准**，只在
   loop 接线阶段用 e2e 夹具反推确认过阈值公式本身正确（`tokens > window - reserve`，
   `test_should_compact_threshold_is_strictly_greater` 钉死）；真实摘要长度、真实触发频率
   要等 `PAI_RUN_LLM_TESTS=1` 或生产使用后才能校准，登记见 TODO P1。
4. `should_compact` 的退化情形（`window <= reserve_tokens` 时恒为 True）**已有上层熔断器
   兜底**——`MAX_COMPACT_FAILURES=3` 接进 loop 触发块，连续压缩后仍超线会 tripped，
   不再无限重试（`test_breaker_stops_auto_compaction` 覆盖）。此前记的「尚未实现」已过时。
5. 拍平 vs 原样发（decisions 第 12/16 条）：**已实测裁决**，默认 `style="flat"`（D#37），
   loop 调 `compact` 不传 style，用默认值。原样发的不听话率数据留档见
   `evidence/20260809-拍平vs原样发实测/`。
6. `pai_playground/sessions/` 被 .gitignore 排除，而测试夹具的原始出处在那里——溯源链断了。

## 下一步

阶段 2 前半程（REPL）与阶段 3（记忆）已交付。下一步是**阶段 4 权限**——
动工前要补前置精读缺口（官方 permissions + hooks 两章尚未落笔记）。
阶段 2 后半程 TUI 暂缓。

阶段 1 遗留的两条候选仍在 TODO：
- **reserve_tokens / keep_recent_tokens 实测校准**——目前仍是从 pi 借来的经验值，
  需要真实会话（或 `--llm` 冒烟测试）的真实摘要长度与触发频率数据才能定。
- **microcompact 评估**（K source-walks/cc-compaction.md）——pai 的 4 个工具全部可重放，
  按 tool_call_id 清旧结果不用调模型，可能是性价比最高的第二级压缩，阶段 1 跑通后评估。

阶段 2 REPL 的 6 条遗留见 TODO「feature 05（REPL）遗留」小节，其中两条值得先知道：
**`Tool.run` 的返回契约分不出工具内部错误**（状态行因此标不出红叉）、
**steering 无真实输入源**（结构已就位，等 TUI/流式通电）。
