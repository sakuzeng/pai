# evals —— 评测（阶段 7，feature 32）

入口 `./eval.sh`（默认无密钥回放评测；`--llm` 追加真模型评测，花钱）。
评测不进 `./test.sh` 收集范围；能离线单测的逻辑住 `src/pai/evals/`，
这里只放评测套件本体与夹具。设计与取舍见
[features/32](../docs/dev/features/32-20260824-evals/README.md)（spec/plan 同目录），
参照笔记见 knowledge/evals/ 两篇（pi 的跑批 / dsh 的回放）。

- `fixtures/`：签入版本库的真实会话轨迹（溯源见其 README）。
- `.eval/`（gitignore）：每次运行一个 `<UTC时间戳>/` 目录——`runs.jsonl`
  逐 case 一行 + `sessions/` 会话快照。含 prompt 与工具输出，别外传。
- 判分第一原则（dsh）：验证外部世界，而非自我报告——重读文件、重跑命令，
  不对 agent 自述文本做关键词探测。
- 旧计划（10~20 个可程序判定的文件操作任务、跑批统计成功率与成本、改
  prompt 回归对比）收编为真模型纵切的扩展方向；baseline/candidate 比较
  机器是 spec 非目标，等真实压力再扩。
