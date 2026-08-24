# pi 的 evals：把真 AgentSession 适配进 vitest-evals 的行为评测

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `packages/evals/`，commit `4c01c709`（2026-08-02）。
  `README.md`(153) / `src/pi-harness.ts`(257) / `src/vitest-evals/{artifacts,setup,reporter,harness-table,summary}.ts` /
  `scripts/run-evals.mjs`(97) / `src/smoke.eval.ts`、`src/extensions.eval.ts`（示例）。
  证据等级：pi 是可读源码（D#69），本篇全部结论对着源码写。
- 精读日期：2026-08-24
- pai 锚点：roadmap 阶段 7（evals）、`src/pai/core/session.py`（会话 JSONL 即评测工件）、
  `tests/fake_provider.py`（pai 已有的「真进程回合」基建）、`docs/dev/features/32`（届时）
- 相关：[dsh-testing.md](dsh-testing.md)（另一家的路线：不做打分评测，做分层快照 + 带密钥冒烟）

## 一句话

pi 的 evals 不是另一套测试框架，是「把真 agent 会话包成 vitest 测试」：
`createPiCodingAgentHarness()` 起一个隔离的真 `AgentSession`（临时 cwd + 临时
agent 目录 + 内存 settings），跑完把原生会话 JSONL 当工件存档，评分交给
vitest-evals 的 judge，比较交给 reporter 算配对差值。评测=测试的超集，
不是并行的另一个世界。

## 结构：五个部件各管一段

1. 适配器 `pi-harness.ts`——唯一碰 pi 内部的地方。隔离三件套：
   `mkdtemp` 出 root，`workspace/` 当 cwd、`agent/` 当用户目录、
   `SettingsManager.inMemory()`——评测绝不读真用户配置（pai 对位：
   `tests/conftest.py` 的 `$HOME` 隔离已是同款约束，评测层要沿用）。
   `thinkingLevel: "off"` 硬编码：评测要可比，思考量是噪音源。
2. 转写归一化 `toTranscriptEvents()`：pi 内部消息 → vitest-evals 的
   `TranscriptEvent`（message / tool_call / tool_result 三种）。断言家族
   （`toolCalls(...)` 等）都建立在这个归一化形状上——评测断言不面对
   provider 原始形状。
3. 工件 `artifacts.ts` + `setup.ts`：跑完（哪怕失败）先把原生 session JSONL
   快照进内存（`setArtifact`），临时目录删掉之后由 eval 专属 `afterEach`
   把快照登记到 vitest 的 test task 上；reporter 再把它落到
   `.eval/<时间戳>_<uuid>/sessions/<sha256(runId)>/session.jsonl`，
   并在 `runs.jsonl` 里逐行索引（runId / 测试名 / usage / timings / errors /
   工件相对路径）。要点：工件目录权限 0o700、文件 0o600——评测产物含
   prompt、源码、工具输出，按敏感数据待遇。
4. 比较 `harness-table.ts` + `summary.ts`：`evalHarnessTable("集名",
   {baseline, candidate(s), repetitions})` 展开成 `describe.for` 的行；
   分组键 = repetition + `input.id`（无 id 则严格规范化 JSON 的 sha256——
   规范化拒绝 NaN/循环引用/稀疏数组，输入不可序列化当场报错不静默）。
   报告口径：judge 平均分 ≥1 记 pass，lift = candidate 通过率 − baseline
   通过率（百分点）；token/延迟/成本是独立的配对差值；缺 judge 分记
   incomplete、缺 telemetry 记 unavailable——三种「没有」各有名字，不混。
5. 跑批入口 `run-evals.mjs`：解析 `--provider/--model`（CLI 赢 env，
   必须成对给），准备工件目录，转身 spawn vitest。评测 runner 只是
   vitest 的一层薄壳。

## 最有迁移价值的六条

1. 评分是观察不是断言：比较型套件设 `judgeThreshold: null`，低分记录在案
   而不让 vitest 红——硬断言只留给「套件不变量与基建契约」。README 特意
   点名 `expect.soft(...)` 也会让测试失败，不能当打分用。pai 若把 evals
   接进 pytest，同样要分清这两类：行为分数进报告，基建坏了才红。
2. 结果的可信度建立在失败面的显式化上：`promptAgent` 检查
   `stopReason !== "stop"` 即抛（含 errorMessage）、无 assistant 文本即抛、
   清理失败与运行失败用 `AggregateError` 并列上抛——评测框架自己不许有
   静默失败，否则「分数低」与「基建坏」分不开。
3. 工件优先于展示：原生会话 JSONL 是第一等产物（先快照再删临时目录，
   雨天路径也存）。事后能重放/审计的评测才有积累价值——pai 的会话格式
   v1 + `replay_messages` 正好是这个位置的地基。
4. 模型选择三层：harness 显式 model > runner 默认（CLI/env）> 报错。
   显式选型的 harness 让「模型对比」评测不被 runner 默认值污染。
5. 隔离会话必须自证隔离：跑前断言 `getExtensionPaths().length === 0`
   （「隔离的评测会话不该带扩展进场」）。隔离是断言出来的，不是布置出来的。
6. 多步输入 `[{prompt}, {reload}, {prompt}]`：评「上一步创建的资源这一步
   能不能用」这类场景，reload 是显式步骤而非隐式副作用。

## pai 视角：能直接对位的与刻意不同的

- 对位：pai 的 `SessionLog`（JSONL 工件）、`fake_provider`（真进程回合）、
  `$HOME` 隔离、`replay_messages`（回放地基）四块都已存在，缺的是
  「评测入口 + 打分/比较 + 工件索引」三件。
- pi 没有「无密钥回放评测」：它的 evals 全部打真模型（行为评测），
  确定性回放那半边 pi 是空白——那半边的参照是 dsh（见
  [dsh-testing.md](dsh-testing.md) 的 llm-replay）。roadmap 阶段 7 的目标
  「真实会话轨迹回放评测 + 跑批」正好各取一家。
- pi 的 judge 是模型判分（vitest-evals 的 createJudge）；pai 的费用纪律
  （`--llm` 显式开关）意味着模型 judge 必须与真模型跑批同门槛，
  确定性判分（外部世界断言）该是默认档——这条与 dsh「验证外部世界，
  而非自我报告」合流。
