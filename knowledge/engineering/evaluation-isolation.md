# 评测隔离的三个加载边界

- 来源：本仓库 [feature 56 的反证与实际输出](../../docs/dev/features/56-20261022-task-evals/evidence/tdd-output.md)；本轮已安装 pytest 8.4.2 的 `_pytest.config.PytestPluginManager._is_in_confcutdir` 源码；JUnit 实际工件。
- 精读日期：2026-10-22
- pai 锚点：`src/pai/evals/task_grading.py`、`src/pai/evals/task_runner.py`、`tests/test_task_grading.py`、`tests/test_task_runner.py`
- 相关：[进程组与中断](process-groups-and-interrupts.md)、[观测仪器的误导](instruments-lie.md)

## 配置发现范围要逐个验证

新 cwd 和 HOME 只改变路径起点。加载器若向全部祖先查配置，临时目录位于被测源码内部时仍会继承外部指令。
验证方法是在上层目录放一个可观察的配置，再检查它是否被加载；不要用「目录是新建的」推导隔离已成立。
执行目录应避开这些祖先，或通过加载器公开接口明确约束范围；持久工件可以保存到另外的位置。

## pytest 的 confcutdir 是祖先截断

本轮检查的源码实现返回 `path not in self._confcutdir.parents`。
它阻止加载指定目录上方的 conftest，并不承诺只加载指定目录内部的 conftest；来自另一棵源码树的显式测试文件仍可能带入自己的配置。
因此外部评分测试也应复制到评分副本，再执行副本中的文件，配合受控 HOME、环境与插件设置。

有鉴别力的反证是让源目录上方的 conftest 立即报错：评分参考解仍应通过。只检查评分子进程 cwd 无法发现这类污染。
这是本轮已安装版本的源码与运行证据，不保证所有历史或未来 pytest 版本同形。

## 结果格式与执行成功要分开

本轮 JUnit 的 failure 元素没有 type 属性，异常种类在失败正文末行；不能把属性缺失当作没有断言失败。
同样，pytest 全跳过可以退出 0。有效测试需要检查实际收集、失败、错误与跳过数，不能只检查进程退出码。
构造错误实现时，收集失败、导入错误或超时并不能证明测试检测到了行为差异。

具体判据必须由参考解和无效产物共同验证，解析格式也应以实际工件作为测试输入。
