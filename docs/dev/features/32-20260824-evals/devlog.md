# feature 32 开发日志

## 2026-08-24 · T1 公共件

- 目标：eval.sh 入口 + 工件索引 + evals/ 目录形态。
- 动了：`src/pai/evals/{__init__,artifacts}.py`（run 目录命名 / runs.jsonl
  逐行追加 / 状态白名单拒收，纯逻辑离线可测）、`evals/conftest.py`
  （makereport hookwrapper 记结果、autouse 落记录、`eval_artifact_dir`
  自动登记、HOME 隔离照抄 tests 铁律）、`eval.sh`（双开关对齐 test.sh）、
  `.gitignore` 加 `evals/.eval/`、`evals/README.md` 重写（旧「阶段 6 任务」
  计划收编为真模型纵切的扩展方向）。
- 红→绿：`tests/test_evals_artifacts.py` 3 条，红在 ModuleNotFoundError
  （collection error）→ `3 passed`。

## 2026-08-24 · T2 夹具铸造

- playground 真跑（真 DeepSeek，`--dangerously-skip-permissions
  --max-steps 8`，隔离 HOME）：任务「创建 问候.txt 写一行中文 → read_file
  确认 → 回答完成」。产出 v1 会话（id `60389d9b…`，3 轮 assistant：
  write_file / read_file / 文本收尾），产物 问候.txt 内容逐字正确。
- 复制入库 `evals/fixtures/20260824-greeting-file.jsonl`，溯源记
  fixtures/README.md（「真跑轨迹当夹具须入库」的既有规矩落地）。
- 过程小事故如实记：拼隔离 HOME 用了错误的相对基准（`$PWD` 已经 cd 进
  proj），会话落在嵌套错位的目录里——找回来了，夹具内容不受影响；
  铸造脚本类操作下次先 `pwd` 再拼路径。

## 2026-08-24 · T3 派生器

- 红：`tests/test_evals_replay.py` 4 条（真轨迹派生逐字断言 + v0 /
  含 compaction / 无 user 消息三类拒绝），collection error 起步。
- 实现 `src/pai/evals/replay.py`：`derive_replay` 搭 `load_session` +
  `build_messages` 的车（v0 与坏文件沿用既有拒绝语义），compaction 在
  build 之前显式拒绝（重建摘要不是模型真实输出，理由进 docstring）；
  assistant 消息转 fake_provider turn 形（arguments JSON 串解析回 dict）。
- 绿：`7 passed`（含 T1 的 3 条）。

## 2026-08-24 · T4 回放评测 + T5 真模型冒烟

- `evals/test_replay.py`：FakeProvider 装派生脚本 → 真 pai 子进程（once，
  权限姿态与铸造一致）→ 外部世界断言（问候.txt 存在且内容逐字一致）+
  「脚本已用完」兜底不许出现 + 会话快照进工件。`./eval.sh` →
  `1 passed, 1 deselected in 1.99s`，工件 runs.jsonl 与 sessions/ 齐。
- `evals/test_llm_smoke.py`：`--llm` + 环境 key 双门槛；真跑一次验证
  `1 passed, 1 deselected in 3.27s`（真 DeepSeek 写出 评测.txt）；
  无钥 + 开开关 → `1 passed, 1 skipped`（skip 语义对）。

## 2026-08-24 · T6 收尾

- 注入反证：`derive_replay` 丢弃 tool_calls（`calls = []`）→ 双层各红——
  评测层 `FAILED evals/test_replay.py::test_replay_greeting_trajectory_end_to_end`
  （红在「重放没有产出 问候.txt」，正是外部世界断言在起作用）、单测层
  `FAILED tests/test_evals_replay.py::test_derive_replay_from_real_trajectory`。
  复原后两层绿。
- 全量第一跑 1 红：撤掉 STATUS 的「mcp_client / evals · 未开始」占位行让
  viz 的 stage 键对账测试红了（pipeline 节点 `mcp_client` 引用的键随占位行
  消失）。修正：节点 stage 改指真实模块行 `mcp`，`NODE_SRC` 从 roadmap 指回
  `core/mcp.py`——顺手把同款陈旧的 skills 一并校正（阶段 6 交付后一直还
  指着 roadmap）。防漂移测试正是这样起作用的，两边各自手写、谁撤谁得对账。
- 全量：`1365 passed, 3 deselected`（+7：artifacts 3 + replay 4）。
- 遗留登记 TODO（见 README 遗留节）。
