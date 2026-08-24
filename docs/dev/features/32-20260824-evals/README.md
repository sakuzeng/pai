# 32-evals —— 阶段 7：真实会话轨迹回放评测 + 跑批
状态：已交付（2026-08-24，1365 passed + eval.sh 两纵切各绿；复盘见 复盘.md）
分支：`feat/32-evals`（自 `main` 开出，承担全部实现）
流程：superpowers 全链路（roadmap 阶段 7 规定；本档案先承载 brainstorm 的
方向拍板，spec/plan 随后）

## 需求

roadmap 阶段 7 原文：真实会话轨迹回放评测 + 跑批（evals/ 目录已预留）。
两半边的含义（前置精读后收窄）：

- 回放评测：拿真实会话 JSONL 当 fixture，无密钥、确定性地重放整个回合，
  断言 harness 行为（外部世界与固定 transcript 的 diff）——参照 dsh
  llm-replay（K evals/dsh-testing.md）。
- 跑批：打真模型的行为评测，带打分/比较/工件索引——参照 pi packages/evals
  （K evals/pi-evals.md）。

验收标准在 spec 阶段细化；方向拍板后再写。

## 候选方案与确认

### 方案 A · 回放优先（dsh 形态）

第一梯队只做回放跑道：会话 JSONL → fake_provider 脚本的派生器（pai 的
会话 v1 存的是装配后消息，回放粒度天然是整条 assistant 消息——分片层
已有 test_streaming 覆盖，这里明确不做分片重建）、评测用真轨迹签入
版本库（顺手关掉「pai_playground 被 gitignore、夹具溯源链断了」的旧债）、
断言走外部世界（重读文件/重跑命令）。跑批半边只留一个 `--llm` 门槛下的
最小冒烟。
取舍：零成本可日常跑、确定性、直接兑现「回放评测」；但回答不了
「prompt/skill/模型改了变好没」——回放测的是 harness 不是模型行为。

### 方案 B · 跑批优先（pi 形态缩水版）

第一梯队做评测入口 + 打分 + 工件：pytest 驱动的 eval 集（真 DeepSeek，
`--llm` 同款双开关）、确定性 judge 优先（外部世界断言，模型 judge 缓做）、
工件索引（evals/.eval/runs.jsonl + 会话 JSONL 快照，抄 pi 的「先快照再删
临时目录」）、baseline/candidate 比较与 repetitions。回放半边推后。
取舍：能真正度量行为变化；但花钱、结果有方差，且 pai 当前没有「要比较的
两个候选」的现实压力——先建比较机器有过度设计风险。

### 方案 C · 最小合体（两条最小纵切）

先立公共件：evals/ 目录形态、运行入口与 pytest 标记、工件落盘
（runs.jsonl 索引 + 会话 JSONL 快照）。然后各切一条最小纵切打通全链：
一条回放评测（拿一份真轨迹派生脚本、外部世界断言）+ 一条真模型冒烟评测
（`--llm` 门槛、确定性判分）。比较/repetitions/模型 judge 全部等真实
使用压力出现再扩。
取舍：两半边都见底、公共件被两个消费方约束着不会长歪；代价是第一梯队
交付的每半边都薄，「能比较」要等第二轮。

### 确认

问 1（2026-08-24，方向）：阶段 7 evals 第一梯队按哪个方案走？
（三案取舍原文见上方「方案 A/B/C」节，提问时逐案给了取舍描述）
- 候选 A · 回放优先（dsh 形态）：零成本确定性可日常跑，但回答不了
  「改了 prompt/skill 变好没」；
- 候选 B · 跑批优先（pi 形态缩水版）：能度量行为变化，但花钱、有方差，
  且当前没有「要比较的两个候选」的现实压力——先建比较机器有过度设计风险；
- 候选 C · 最小合体（AI 推荐）：先立公共件（evals/ 目录、pytest 入口、
  runs.jsonl 工件索引），再各切一条最小纵切（回放评测 + 真模型冒烟评测），
  比较机器等真实压力再扩。
选择：C。用户经 AskUserQuestion 选中「C 最小合体（推荐）」，未附加说明。
理由（提问时陈述、用户以选择确认）：两半边都见底、公共件被两个消费方
约束不长歪；代价是第一轮每半边都薄，「能比较」要等第二轮。

## 结果与总结

方案 C 全部落地：`./eval.sh` 评测入口（与 ./test.sh 口径隔离，testpaths
不动）+ 工件索引（`evals/.eval/<时间戳>/runs.jsonl` 逐 case 一行 + 会话
快照，抄 pi「工件优先于展示」）；回放纵切——playground 真 DeepSeek 铸造
v1 轨迹入库（fixtures/README 溯源）、`derive_replay` 派生 fake_provider
脚本、真 pai 子进程重放整回合、外部世界断言；真模型纵切——`--llm` 双门槛
冒烟（真跑一次 3.27s 过，无钥 skip 语义验证过）。验收 5 条全对账（细目与
红→绿数字见 devlog.md）：`./eval.sh` 无密钥全绿 ✅、派生器单测拿真实轨迹
输入且三类拒绝 ✅、`--llm` 手工验证 ✅、注入反证双层各红 ✅、全量
`1365 passed, 3 deselected` ✅。roadmap 阶段 1-7 至此全部有交付。

## 遗留问题

（每条已同步登记 ../../TODO.md「feature 32（evals）遗留」节）

1. 任务文本启发式取「首条非空 user 消息」——录制会话若带指令消息
   （PAI.md 注入），会误取指令当任务。铸造夹具无指令故本轮无害。
2. 回放判分是逐夹具手写断言，没有「期望产物」的声明式描述；夹具多了会
   重复。等第二三份夹具出现看形状再抽。
3. 单场景：回放 1 个夹具、真模型 1 个任务。扩成任务集与成功率统计
   （evals/README 旧计划）等真实使用压力。
4. roadmap 阶段 7 的「反向对照（交付前真跑 N 场景）」按原意是对照外部
   参照的行为——本轮铸造与真模型评测共两次真跑，但没有做成体系的
   多场景对照，勾选项留空如实反映。

## 用到的知识

- K [evals/pi-evals.md](../../../knowledge/evals/pi-evals.md)（跑批半边参照）
- K [evals/dsh-testing.md](../../../knowledge/evals/dsh-testing.md)（回放半边参照 + 判分方法论）
- [features/23](../23-20260822-model-visible-is-recorded/README.md)（replay_messages 是 evals 地基）
- [features/24](../24-20260822-session-format-and-resume/README.md)（会话格式 v1）
- [features/15](../15-20260811-fake-provider/README.md)（fake_provider，回放的执行端）
