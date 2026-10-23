# 56-task-evals · 实施计划

已根据逐项拍板的 spec 定稿。按依赖顺序执行；每步先提交工作区测试、实际跑红，再写实现并跑绿；不做 Git commit。
各次实际命令、完整失败与最终摘要在 devlog/evidence 留痕，不把旧测试通过当成新功能 TDD。

## Task 1：案例与外部评分契约

目标文件：`tests/test_task_grading.py`、`src/pai/evals/task_grading.py`、`evals/tasks/{locate,fix,tests}/`。

先写 3 类正常/错误产物及夹具预检：查实现错误目标不得通过；原始 bug 必须失败、参考解必须通过；空测试/导入错误/漏测错误实现不得通过；越界改文件、删保护文件、软链不得通过。
命令：`python3 -B -m pytest tests/test_task_grading.py -q`，先保留缺实现的红，再实现 TaskCase/prepare/grade；外部 pytest 评分目录与 key 隔离。
验收：上述契约全绿，保护文件与评分器不由模型修改，正确参考解证明评分可达。

## Task 2：真实会话指标与汇总

目标文件：`tests/test_task_metrics.py`、`src/pai/evals/task_metrics.py`。

先以已提交的真实 greeting v1 会话写预期计数，再测试多调用、拒绝、缺 usage/可选字段、损坏记录、预算/步数与汇总分母。
命令：`python3 -B -m pytest tests/test_task_metrics.py -q`。红后实现会话/事件读取；缺失保持 null；正常结束与产物成功分列。
验收：真实中文 arguments 正确读取，工具尝试与开始执行可区分；计划数/异常/未启动不可被静默剔除。

## Task 3：worker、进程生命周期与隔离

目标文件：`tests/test_task_runner.py`、`src/pai/evals/task_worker.py`、`src/pai/evals/task_runner.py`。

先用 FakeClient 测 worker 的公开 run_once 装配与事件，再用已有 fake_provider 做真实 HTTP/子进程成功、权限拒绝、上限与超时测试；超时覆盖工具独立进程组的回收。
命令：`python3 -B -m pytest tests/test_task_runner.py -q`。红后实现白名单环境、显式模型与双门槛、父进程单调时钟、输出/会话/工作区快照；SDK 自动重试关闭。
验收：每次新 HOME/工作区，无个人配置和祖先指令混入；真实 key 不进评分进程和工件；截止后不再启动请求。

## Task 4：入口、串行跑批与报告

目标文件：`tests/test_task_entry.py`、`eval.sh`、`evals/task_suite.py` 以及 runner 汇总。
最终使用 task_suite.py 的显式收集文件名，替代初拟 test_tasks.py，避免旧默认入口意外收集新付费任务；入口测试已验证。

先验证旧入口不意外收集新付费任务，--tasks 默认离线、--tasks --llm 显式开启 9 次基线；缺 key/付费开关明确提示，失败不补跑。
命令：`python3 -B -m pytest tests/test_task_entry.py -q`；红后实现入口和报告。现有 runs.jsonl 的 v1 三态保持，详细任务状态另存引用。
验收：fake provider 完整纵切全绿；每次及总期限有硬停止，评分也有限期。

## Task 5：真实基线与交付

先冻结代码/夹具/评分器哈希和运行配置，开发运行入口与持久工件在 pai_playground；每次独立执行位置必须避开祖先指令混入，完整快照保存可翻看。
串行执行三题各三次 deepseek-flash；20 步、200000 token 请求前软熔断、180 秒/次、1200 秒/批。保留失败/未知/未启动，不自动补跑。

离线全量与 eval 回归通过后，将真实结果、汇总及必要原始会话复制到档案 evidence，更新文档与 TODO，写复盘再宣告交付。
合并、提交和推送不在本轮授权内。具体真实任务代码与 prompt 先固定，不根据跑分调题或调提示词。

完成证据与实施中发现的偏差统一见 [devlog](devlog.md)；真实基线与冻结元数据见 [报告](evidence/20261022-deepseek-flash-baseline/README.md)。
