# 首轮真实任务基线 · 2026-10-22

配置模型：deepseek-flash；请求未额外覆盖 temperature/thinking，provider 具体后端修订号 unknown。
本轮固定小仓库三任务各三次，acceptEdits；以正常 final 收尾且外部判据全部通过计完整成功。

| 任务 | 完整成功 | 产物通过 | agent 耗时中位数（秒） | 主请求 token 中位数 |
|---|---|---|---|---|
| 查实现 | 3/3 | 3/3 | 4.703 | 8592 |
| 修小 bug | 3/3 | 3/3 | 6.344 | 11746 |
| 补测试 | 3/3 | 3/3 | 10.036 | 15785 |

完整成功率与产物通过率均为 9/9。真实入口（含离线预检）实际输出：`2 passed in 69.12s (0:01:09)`，未补跑。
累计 43 条主请求 usage、107291 token；工具尝试 48 次、开始执行 43 次、权限拒绝 5 次，均为 bash。
拒绝分布：查实现 1、修 bug 3、补测试 1；模型均恢复并完成。真人弹窗次数不适用，不是 0 次。

agent 累计耗时 61.598 秒，九次试验的全过程累计 66.959 秒；表内 agent 耗时含进程启动/装配，不含外部评分。
全部试验均远低于 180 秒/20 步/200000 token 软阈值，批次低于 20 分钟；没有 timeout、provider/protocol/harness error 或未启动项。
主请求 usage 覆盖完整；没有压缩/召回等侧请求，不把 token 换算成未验证的全部费用。

## 如何核对

- [report.md](report.md)：逐次执行、结束原因、产物与工具指标。
- [summary.json](summary.json) / [task-results.jsonl](task-results.jsonl)：汇总与逐次完整分类。
- [manifest.json](manifest.json)：分支基点、dirty 状态、代码/案例哈希、权限、预算和依赖版本。
- [archive-index.json](archive-index.json)：152 个原始工件的大小/哈希与 9 次会话核对。
- [pytest-output.txt](pytest-output.txt)：真实入口原始输出。

每个 trial 的 workspace 是最终模型产物；grading/ 是独立评分副本，含错误实现的执行材料，不能把它当作最终产品。
sessions/ 与 trace.events.jsonl 保留原始时间字段；它们是本次证据，不是新增自动化测试夹具。
已逐字节验证归档与原件相等；API key 检查无命中。预先冻结的代码/案例哈希与真实 manifest 全部一致，未按结果改题或调提示词。
九个会话各只有一条用户任务且与冻结 prompt 一致；usage 的 model 字段是请求配置名，不是服务端修订号证明。

Git 尚未提交：sourceRev 是分支基点，不能把它单独当作包含新实现的提交。运行实现由当前工作区与 codeHash 标识。

## 结论边界

这些是专门构造的三个小题，只有各三次。9/9 不证明真实项目成功率、跨版本稳定性、权限体验或提示词改进收益。
本轮只有一组基线，没有 A/B 变体。5 次权限拒绝是绕路观察，不据此认定哪个提示词或权限方案更好。
原始现场仍位于 pai_playground/task-evals/20261022T124706Z-5be434f3；版本库内本目录为可长期核查副本，省略工作区的 .git 与运行缓存。
