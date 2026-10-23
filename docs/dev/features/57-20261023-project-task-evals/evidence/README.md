# Feature 57 · 离线交付证据

本轮用户选择完整历史快照、先完成离线设施、相关回归/独立判据、默认开发集且保留集显式。原始问答在 [档案](../README.md)。本轮没有真实模型调用，没有模型成功率数据。

| 验证 | 实际结果 | 证据 |
|---|---|---|
| 新功能单测最终组合 | 32 passed in 15.97s | [输出](final-unit-green.txt) |
| 首轮完整离线 | 1996 passed、1 failed、8 deselected；唯一失败是 STATUS 旧数量 | [原输出](full-first-output.txt)、[JUnit](full-first.junit.xml) |
| 最终标准完整离线 | 1997 passed、8 deselected in 224.05s | [原输出](full-final-output.txt)、[JUnit](full-final.junit.xml)、[分类核对](full-suite-audit.json) |
| 全六题显式冻结 | 6 个 reference_contract 通过 | [报告](freeze/report.md)、[明细](freeze/report.json)、[冻结清单](../../../../../evals/project_tasks/freeze.json) |
| 默认开发集 | 仅 3 个 development 参考契约通过 | [明细](development/report.json) |
| 显式保留集 | 仅 3 个 holdout 参考契约通过 | [明细](holdout/report.json) |
| 原回放 / 三固定题离线 | 1 passed、5 deselected / 1 passed、1 deselected | [回放输出](old-replay-output.txt)、[旧任务输出](old-tasks-output.txt) |
| 判分原始输出 | 62 个文件逐字节归档并校验 | [哈希索引](archive-index.json)，三个分组目录下 JUnit/output |

TDD 每一步红与绿、首次相对 CLI 冻结失败均保留，过程见 [devlog](../devlog.md)。首次相对输出失败没有写冻结清单；补入口反证、修正绝对路径后才重新冻结。运行副本仍在 pai_playground/project-task-evals，可由固定 Git 对象、材料和依赖重建，不重复提交整个仓库副本。

本轮验证的是外部评分与参考解，不是真实 once/LLM 运行；没有做提示词 A/B、模型比较、真人交互或全历史版本的完整回归。后续真实执行适配与预算登记在 TODO。
