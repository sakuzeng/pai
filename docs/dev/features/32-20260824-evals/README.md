# 32-evals —— 阶段 7：真实会话轨迹回放评测 + 跑批
状态：已拍板（2026-08-24 问 1·方向选 C；细化见 spec.md / plan.md）
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

（交付时填。）

## 遗留问题

（交付时填；每条同步一行登记 ../../TODO.md。）

## 用到的知识

- K [evals/pi-evals.md](../../../knowledge/evals/pi-evals.md)（跑批半边参照）
- K [evals/dsh-testing.md](../../../knowledge/evals/dsh-testing.md)（回放半边参照 + 判分方法论）
- [features/23](../23-20260822-model-visible-is-recorded/README.md)（replay_messages 是 evals 地基）
- [features/24](../24-20260822-session-format-and-resume/README.md)（会话格式 v1）
- [features/15](../15-20260811-fake-provider/README.md)（fake_provider，回放的执行端）
