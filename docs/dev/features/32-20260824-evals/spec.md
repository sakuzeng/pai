# feature 32 · spec（方案 C：最小合体）

拍板依据：README 问 1 选 C。参照：K evals/pi-evals.md（跑批半边）、
K evals/dsh-testing.md（回放半边 + 判分方法论）。

## 1. 形态总览

```
evals/                     评测套件（pytest 文件；不进 ./test.sh 的收集范围）
  conftest.py              工件 fixture：每条 eval 落一行 runs.jsonl + 会话快照
  fixtures/                签入版本库的真实轨迹（来源与铸造方式见 README.md）
  test_replay.py           回放纵切：真轨迹 → 派生脚本 → 真 pai 子进程重放
  test_llm_smoke.py        真模型纵切：--llm 双开关，程序判定成败
  .eval/                   工件输出（gitignore）：<UTC时间戳>/runs.jsonl + sessions/
eval.sh                    评测入口（对位 test.sh；默认只跑无密钥回放евals）
src/pai/evals/replay.py    派生器：会话 v1 JSONL → fake_provider 脚本
tests/test_evals_replay.py 派生器单测（离线，进 ./test.sh 默认收集）
```

关键隔离：`pyproject` 的 `testpaths = ["tests"]` 不动——`./test.sh` 的口径与
STATUS 对账数字不受 evals 影响；evals 只经 `./eval.sh`（内部 `pytest evals`）跑。

## 2. 公共件

- 工件（抄 pi 的「工件优先于展示”）：evals/conftest.py 提供 autouse fixture，
  每条 eval 结束（含失败）追加一行 `runs.jsonl`：
  `{case, status, durationMs, artifacts:[相对路径]}`；被评测 pai 进程的会话
  JSONL 复制进 `.eval/<运行时间戳>/sessions/<case>/`。目录时间戳一次运行一个
  （pytest session 级 fixture 定值）。
- `eval.sh`：`./eval.sh` 跑无密钥回放集；`./eval.sh --llm` 追加真模型集
  （与 test.sh 同款双开关语义与警示文案）。
- 判分第一原则（dsh）：外部世界断言——重读文件、检查产物，不对 agent
  自述文本做关键词探测。模型 judge 不在本轮（非目标）。

## 3. 回放纵切

- 夹具铸造：在 pai_playground 用真 DeepSeek 跑一个小任务（写文件类，
  产物可程序判定），把产出的 v1 会话 JSONL 复制进 `evals/fixtures/`，
  溯源（何时、什么任务、哪次真跑）记 `evals/fixtures/README.md`——
  顺手兑现「真跑轨迹被当夹具须复制进版本库」的既有规矩。
- 派生器 `derive_provider_script(path) -> list[turn]`：读 v1 会话
  （`load_session`，v0 与坏文件沿用其拒绝语义），取 assistant 消息按序
  转成 `fake_provider.turn`（content + tool_calls，arguments JSON 串解析回
  dict）。粒度取舍（K evals/dsh-testing.md 已论证）：pai v1 存的是装配后
  消息，回放粒度就是整条 assistant 消息，不重建分片——分片层已有
  test_streaming 覆盖；fake_provider 发流时本来就会按字符重新切分。
  含 compaction 条目的会话本轮拒绝（回放语义未定，报错不静默）。
- 回放执行：临时 git 项目 + 隔离 HOME + FakeProvider 装载派生脚本 →
  真 pai 子进程（once 模式，任务文本取录制会话的首条 user 消息）→
  断言外部世界（录制回合写过的文件在重放项目里同样出现、内容一致）+
  回合正常结束。
- 派生器单测拿这份真实轨迹当输入（AGENTS「至少一条真实轨迹」规约）。

## 4. 真模型纵切

- `evals/test_llm_smoke.py`：一条端到端任务（创建/修改文件，成败由重读
  文件判定——execution accuracy，收编 evals/README.md 的旧计划）。
- 门槛：`DEEPSEEK_API_KEY` 存在且 `PAI_RUN_LLM_TESTS=1` 才跑，否则 skip
  （与 tests/test_llm_smoke.py 同款；花钱的副作用不能是默认行为 D#23）。

## 5. 验收标准

1. `./eval.sh` 无密钥全绿：回放 eval 跑通全链（真 pai 子进程 + 真 SSE +
   派生脚本），外部世界断言通过；工件目录出现 runs.jsonl 且每条 eval 一行、
   会话快照在场。
2. 派生器单测（离线，./test.sh 收集）拿签入的真实轨迹当输入：assistant
   序列、tool_calls arguments、中文内容逐项对得上；v0 / 坏文件 / 含
   compaction 三类输入明确报错不静默。
3. `./eval.sh --llm`（有钥时手工验证一次）真模型冒烟成功，成败由外部
   世界判定；缺钥/未开开关自动 skip，无密钥 CI 语义不变。
4. 注入反证：派生器丢弃 tool_calls（只回 content）→ 回放 eval 必红
   （红的输出进 devlog）。
5. `./test.sh` 全绿，数字进 STATUS；`testpaths` 不动。

## 6. 非目标（v1 刻意不做，压力出现再扩）

- baseline/candidate 比较、repetitions、lift 报告（pi 的比较机器）；
- 模型 judge（vitest-evals createJudge 对位物）；
- 分片级回放、`replay.override` 伴随文件、`{{fromRequest}}` 活口（dsh）；
- 含 compaction 会话的回放；嵌套/多会话键控；
- 跑批并行与成本仪表盘；工件文件权限收紧（0o600——个人机器，记录即可）。
