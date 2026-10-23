# 任务基线报告

计划 9 次，启动 9 次；完整成功 9 次，产物通过 9 次。

完整成功率 100.0%，产物通过率 100.0%。

小型构造任务的首轮基线，不外推实际仓库能力。真人弹窗不适用；缺 usage 是未知，主请求用量不等于全部计费。

| 任务 | 次数 | 执行 | agent 结束 | 产物 | 耗时 ms | 已报告 token | 工具尝试/执行/拒绝 |
|---|---|---|---|---|---|---|---|
| locate | 1 | completed | final | pass | 4703 | 8592 | 5/5/0 |
| locate | 2 | completed | final | pass | 6263 | 14028 | 8/7/1 |
| locate | 3 | completed | final | pass | 4039 | 8569 | 5/5/0 |
| fix | 1 | completed | final | pass | 6726 | 11787 | 5/4/1 |
| fix | 2 | completed | final | pass | 6044 | 9368 | 5/4/1 |
| fix | 3 | completed | final | pass | 6344 | 11746 | 5/4/1 |
| tests | 1 | completed | final | pass | 10036 | 15785 | 5/5/0 |
| tests | 2 | completed | final | pass | 7381 | 10433 | 4/4/0 |
| tests | 3 | completed | final | pass | 10062 | 16983 | 6/5/1 |

逐次结果见 task-results.jsonl，配置/哈希见 manifest.json；每个 trial 含原始会话、事件、输出、评分与最终工作区。
