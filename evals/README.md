# evals —— 评测（阶段 7）

入口：

- `./eval.sh`：既有无密钥回放；`--llm` 追加原有真模型套件，产生费用。
- `./eval.sh --tasks`：验证三类任务的初始失败状态与参考解可通过，不调用真实 API。
- `./eval.sh --tasks --llm`：显式运行 deepseek-flash 的三任务各三次真实基线；需要 DEEPSEEK_API_KEY。该入口设置 PAI_RUN_LLM_TESTS=1，费用守卫保留。

评测不进 `./test.sh` 的收集范围；能离线单测的逻辑住 `src/pai/evals/`。
任务自己的测试位于 tasks/，只在其工作区或评分副本执行，不被父套件意外收集。

## 任务评测的含义

题目来源由用户选定为专门构造的小型 Python 仓库：查实现、修边界 bug、补有效测试。
任务与程序判据见 [tasks](tasks/README.md)；设计与拍板记录见 [feature 56](../docs/dev/features/56-20261022-task-evals/README.md)。
这是一组小题基线，不能外推实际 pai 仓库开发成功率；本轮不比较模型或提示词变体。

- 每次最多 20 步、200000 token 请求前软熔断、180 秒；整个批次最多 1200 秒，串行，不自动补跑失败。
- 权限沿用 acceptEdits；无真人可问的请求拒绝。真人弹窗次数不适用。
- 完整成功要求正常 final 收尾且外部产物通过；产物通过率另列。正常进程退出不代表任务成功。
- pytest 验证设施是否完成；模型不必九次全胜。成功率、异常和未启动数看报告，不把 pytest passed 当模型效果。
- token 缺失保持 null；只汇总已报告的主请求 usage，有侧请求或不完整记录时标记覆盖不完整，不当成全部计费。

## 工件与隔离

既有 `.eval/<UTC时间戳>/runs.jsonl` 与 sessions/ 快照保持；schemaVersion 1 的 passed/failed/skipped 不变。
真实任务运行入口和持久工件在 `pai_playground/task-evals/<UTC时间戳-随机后缀>/`：

- manifest.json：Git 版本/dirty 状态、运行代码与案例哈希、prompt、模型配置、权限与预算；后端修订号无法确认则 unknown。
- task-results.jsonl / summary.json / report.md：逐次完整分类、两种通过口径及样本数/中位数/范围。
- 每个 trial：输入、stdout/stderr、worker 状态、会话/事件、最终工作区及外部评分输出。

worker 临时 cwd 位于仓库外，避免祖先 AGENTS/PAI/.env 混入；每次使用新的 HOME，结束后完整工作区快照保存到上述目录。
API key 只交给模型 client，构造后从 worker 环境移除；测试和评分子进程不继承 key。工件含 prompt、工具输出与文件内容，归档前检查。
该隔离不构成系统级沙箱。评测固定命令仍会执行工作区测试代码。

历史设计见 [feature 32](../docs/dev/features/32-20260824-evals/README.md)，单步工具选择见 [feature 47](../docs/dev/features/47-20260827-tool-choice-eval/README.md)。
判分沿用 dsh 文档的外部效果验证原则，跑批工件参照 pi 可读源码；来源等级与证据边界见 feature 56 前置记录。

## 完整历史项目任务（feature 57）

`./eval.sh --project-tasks` 默认仅验证三道开发题的冻结与离线参考契约；`--split holdout` / `--split all` 显式选择保留集。此入口拒绝 `--llm`，不产生模型费用；结果不是模型成功率。案例、判分与显式重新冻结规则见 [project_tasks](project_tasks/README.md)。原 `--tasks` 三固定题及旧入口语义保持。
