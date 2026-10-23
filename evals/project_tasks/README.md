# 完整历史项目任务（离线契约）

六题取 pai 固定历史提交的完整源码、原测试和构建配置，按不同问题族分成 development/holdout；来源、所有选择和限制见 [feature 57](../../docs/dev/features/57-20261023-project-task-evals/README.md)。

```bash
./eval.sh --project-tasks                 # 默认仅开发集，验证冻结后执行离线参考契约
./eval.sh --project-tasks --split holdout # 显式验证保留集
./eval.sh --project-tasks --split all     # 显式验证全部六题，报告仍按 split 标记
```

| 集合 | 任务 | 来源行为 |
|---|---|---|
| development | 查实现 | 压缩历史的保留切点 |
| development | 修 bug | 文件权限规则不应受 JSON 参数键序影响 |
| development | 补测试 | 消息队列按谓词抽取、保留及 FIFO |
| holdout | 查实现 | 流式响应正文/工具调用/用量装配 |
| holdout | 修 bug | 无参 resume 只选当前 cwd 的录制会话 |
| holdout | 补测试 | 目录边界、相似前缀与路径归一化 |

这些命令不会调用模型，拒绝 --llm。输出是 reference_contract，不是模型任务成功率。
报告默认保存到 pai_playground/project-task-evals 的唯一目录，也可用 --output 指定新目录。

freeze.json 固定逐题 prompt、允许文件、历史 commit/tree、原始 archive 与保留文件哈希、排除清单、外部测试/参考解/错误探针、评分实现及 Python/依赖版本。默认只校验选中集合，漂移即停止，不自动更新。
有意修改题目后须先检查差异，再显式执行 --split all --freeze：全部参考/原始反证通过后才写冻结清单；会替换旧清单，不能用它掩盖基线变化。旧清单历史由 Git 保留。

快照移除 docs/dev、knowledge、refs、旧 evals、Git 历史、agent 指令/配置和 .env，不把答案与后续交付说明放到被测目录；实际移除项逐文件可查。其他源码/原测试/构建配置保留，不拆成小型夹具。评分用独立副本和 HOME，导入历史 src，并复制相关回归到外部 pytest 目录以避开原 conftest。resume 题冻结了两条原有回归函数选择，导入/辅助函数保留。

参考修复按真实修复 commit 验证原字节；补测试题的 mutants 是人为评分探针。保留集用于限制后续调参，不代表训练污染不存在。本轮未进行模型基线、提示词 A/B 或完整历史版本全量回归。
