# 合并前整体离线测试

结论：本轮离线合并前检查通过，未发现阻塞合并的问题。测试的是已推送提交 `ba56d1914434673f279a5da731f84e30d2e48b01`，不是新合并提交。源码、测试和任务材料在测试前后逐文件哈希一致；本轮只新增测试记录，没有合并、提交或推送。

用户原话：「在合并到main之前可以先做一下整体的测试吗」。运行环境 Python 3.9.6、pytest 8.4.2；全部入口显式关闭真实 LLM 开关。

## 实际结果

| 检查 | 实际输出或核对结果 | 证据 |
|---|---|---|
| 标准完整 ./test.sh | 1997 passed、8 deselected in 221.76s | [原始输出](full-output.txt)、[JUnit](full.junit.xml) |
| 全量独立核对 | 1997 选中；failure/error/skip 均 0，包含 57 的 32 项、56 的 38 项及 36 项 pty e2e | [分类统计](full-suite-audit.json) |
| 原 eval 回放 | 1 passed、5 deselected in 2.57s | [输出](replay-output.txt) |
| 原三任务离线入口 | 1 passed、1 deselected in 2.12s | [输出](tasks-output.txt) |
| 默认开发集 | 只执行 development 三题，参考契约 3/3 | [报告](development/report.json) |
| 显式保留集 | 只执行 holdout 三题，参考契约 3/3 | [报告](holdout/report.json) |
| 六题冻结/已有证据 | 六题冻结无漂移、原有 62 个归档哈希一致 | [核对](integrity.json) |
| 旧真实基线完整性与指标 | 152 个原始工件、九次会话指标及汇总一致 | [核对](legacy-integrity.json) |
| 九份历史产物独立重判 | 9/9 通过，新模型调用 0 | [摘要](legacy-regrade-output.txt)、[明细](regrade-results.json) |
| Python/脚本语法 | 197 个 Python 文件在内存编译，test.sh/eval.sh 的 bash -n 通过 | [核对](syntax.json) |
| 依赖与 CLI 冒烟 | pip check 无损坏依赖，pai --help 正常返回 | [依赖输出](dependencies-output.txt)、[CLI 输出](cli-help-output.txt) |

原始用例与命令、起始 Git 状态、测试材料哈希在 [manifest](manifest.json)，总体结果在 [summary](summary.json)。本轮评分子进程只保留有内容的产物，清理了 21 个新生成的空 HOME/目录以符合文档目录规则，未删除原始输出或改变判据。
pip check 提示真实缓存目录不可写并自动禁用缓存，依赖检查仍通过；没有修改用户缓存权限或安装依赖，这不是项目回归。

## 合并条件与边界

fetch 后 origin/main 为 `9937c02`，本地 main 为 `861cec7`，均为本次测试提交祖先；分别落后四条/两条提交，没有分叉。目前可快进整合，因此快进后的代码树与已测试 HEAD 相同。本轮没有执行合并。

8 项真实 LLM 测试按标准入口排除；没有测试在线 provider 可用性或调用付费模型。九份重判属于历史产物复核，六题通过属于离线参考契约，不是新的模型成功率。36 项 pty e2e 使用假 provider，不代替真人中文 IME、真实鼠标、终端主题等体验验收。
