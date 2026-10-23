# Feature 56 · 前置核对证据（2026-10-22）

此记录来自本轮只读检查，不含真实 API 调用或任务结果。

## 本地基线

- 起点：main `9937c0288b731f5ae3fd333a7e422642c1e045d9`；工作分支 `feat/56-task-evals`。
- 现有入口：`eval.sh`、`evals/test_replay.py`、`evals/test_llm_smoke.py`；基础契约在 `tests/test_evals_artifacts.py` / `tests/test_evals_replay.py`。
- 检查命令：`PYTHONDONTWRITEBYTECODE=1 ~/.virtualenvs/pai/bin/python3 -B -m pytest tests/test_evals_artifacts.py tests/test_evals_replay.py -m 'not llm' -p no:cacheprovider --basetemp=/private/tmp/pai56-existing-eval-contracts -q`。
- 实际输出：`9 passed in 0.57s`。只覆盖现有离线基础。

## 参照分级与反查

- pi：可读源码。`knowledge/evals/pi-evals.md` 固定版本为 `4c01c709`；本地 pi-mono HEAD 与之相符。
  查 `packages/evals/src/pi-harness.ts`：隔离 tmpdir、内存设置、真实 session、执行后快照和 usage；这是源码事实。
- dsh：第一方文档与第一方源码分开引用。当前本地 HEAD 已漂移，因此用 `git show 47f9438:<path>` 查固定版本。
  文档 `packages/test-support/llm-replay/README.zh.md` 说明 JSONL 回放、请求覆盖和显式压缩调用；
  这些是文档承诺。本轮未逐行核验 llm-replay 派生实现；已有笔记也明确保留此边界，不用文档意图代替源码或运行证据。
- CC：反编译源码档；本轮没有核验它的任务评测设施，不据此声称采用了 CC 的具体实现。
- 没有引入上述项目代码。roadmap 的「真实场景反向对照」仍未完成。

## pai 源码约束

- `modes/once.py::run_once` 可注入 model、on_event、rules、mode；使用实际 assemble 和 run_agent，finally 关闭 MCP。
- `core/events.py::PermissionDecided` 是最终权限判定，被拒绝调用没有 ToolStart；真人询问过程不可从此事件反推。
- `core/events.py::ToolEnd.is_error` 只覆盖 loop 自造错误，不能完整表示工具内部错误。
- `core/events.py::AgentEnd` 提供结束原因；CLI exit 0 不足以判任务成功。
- `core/trace.py::EventTrace` 保存非增量事件；session 的 usage 旁账可供指标计算，但缺失或侧请求须如实标注。
- `core/tools/tests_tool.py` 的测试命令来自设置/探测，模型只能选择 path/filter；本轮夹具采用固定测试命令。
- `core/permissions.py` 的 acceptEdits 不是系统沙箱；本轮不增加任意 bash 放行。
