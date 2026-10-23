# 57-project-task-evals · plan

依据四项用户选择与 spec 执行；各步先写测试并实际跑红，再写实现跑绿。详细输出进本档案 evidence，不把参考解验证叫模型评测。开发不 commit 57。

## T1 · 历史快照与目录边界

新 tests/test_project_tasks.py，先覆盖本地临时 Git 仓库的 commit 固定、完整 src/tests 保留、答案/配置过滤、dirty 不影响、危险 archive/软链拒绝。预期缺少 src/pai/evals/project_tasks.py 而红。
实现案例目录加载、split 校验、snapshot_prepare、源 commit/tree 与文件哈希记录，输入只接受已冻结完整 commit id。
绿后再处理六题材料，不先写实现。

## T2 · 外部判分与隔离

先添加 locate/fix/tests 的有效与无效产物测试，目标 src 导入验证、祖先 conftest 投毒、空/跳过/导入错误、受保护文件与软链反证。
实现独立历史评分副本、相关回归复制、类型分支判据；复用 56 的 snapshot、Grade 与 JUnit 统计能力，既有评分函数语义不改变。
每个评分进程有独立期限，输出路径唯一，正确与错误变体各自新副本；本轮无网络/密钥。

## T3 · 六个实际案例与来源验证

先添加真实本仓库历史六题的参数化契约测试：起点/参考 id 真实可达，完整工作区保留，参考全部过，两条原始 bug 必须 AssertionError 失败。
再补齐目录 case.json、外部测试、参考测试与错误探针；外部判分不依赖模型自述或执行完整历史套件。
分组由问题族校验，修复/参考链接与实际保留材料哈希入冻结清单。

## T4 · 默认分组、离线入口与漂移

先测试 default development、holdout/all 显式选择、未知参数与 --llm 拒绝、缺冻结和改材料时报错、不自动刷新。
实现显式 --project-tasks 入口、只离线的报告与显式冻结动作；默认 ./eval.sh 和 --tasks 原行为不变。冻结哈希不包含它自身/临时报告。
离线 preflight 全部六题通过后显式冻结，默认报告只输出开发组三题。

## T5 · 验收与复盘

跑既有任务评测与新功能相关回归，跑两个旧离线 eval 入口和新入口（含显式 holdout 验收），最后标准 ./test.sh 完整离线回归。
以实际选中数量更新唯一 STATUS 数字，原始输出归档；不重复已绿检查凑数字。写复盘四问，具体遗留同步 TODO；57 不提交、不推送、不调用真实模型。
