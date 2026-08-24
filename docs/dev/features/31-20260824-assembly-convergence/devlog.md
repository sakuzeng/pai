# feature 31 开发日志

## 2026-08-24 · 一步交付：抽 assembly + atexit→finally

目标：验收 1-4 一次做完（改动面是「两个装配点 + 一个新模块」，拆步只会让
中间态两处装配一半一半，没有可独立验收的切分点）。

动了哪些文件：

- `src/pai/modes/assembly.py` 新建：`Assembly` dataclass + `assemble()`，
  承载 rules/hooks → skills 信任 → MCP 信任与并表 → boundary → gate →
  memory → recall 的共用序列。三条实现约束：不 import loop 内部
  （AGENTS 架构约束）；MCP 走 `mcp.` 模块属性调用（调用点解析，测试打得了
  桩——test_assembly.py 与 test_mcp.py 的 `mcp_mod.…` 同口径）；MCP 关闭
  刻意不在本模块（生命周期归调用方单出口 finally）。
- `src/pai/modes/once.py`：装配段（原 47-124 行的手抄）替换为一次
  `assemble(...)` 调用 + 差异点参数（asker=None、mode 默认 DONT_ASK、
  recall_model 兜底）；finally 关闭改走 `mcp.close_all_mcp`。
- `src/pai/modes/interactive.py`：装配段（原 384-439 行的手抄）替换为
  `assemble(...)` + 解包；`import atexit` 与 `atexit.register` 删除，
  TUI 分流 + REPL 主循环整体包进 try/finally（机械缩进，逐行只加 4 空格），
  finally 里 `mcp.close_all_mcp(mcp_sessions)`——正常退出 / EOF / 异常上抛 /
  TUI return 四条路统一收口。17 个失去用途的 import 清掉（逐符号 grep 计数
  核对，`build_context`/`memory_dir` 等仍有 /memory 与 `_guarded_run`
  的真实使用，保留）。
- `tests/test_assembly.py` 新建：两条钉验收 3。

红→绿（TDD，先测后改）：

- 红：`test_repl_closes_mcp_sessions_before_returning` +
  `test_repl_closes_mcp_sessions_when_loop_raises` →
  `2 failed in 0.45s`（atexit 注册的关闭在 run_interactive 返回时不触发，
  `closed == []`）。
- 绿：改完后同两条过；相邻五个文件
  `test_assembly + test_interactive + test_modes + test_mcp + test_skills`
  → `183 passed in 3.99s`。
- 全量：`1353 passed, 3 deselected`（新增 2 条；既有测试零改动——
  验收 2「行为与输出逐字不变」的判据）。
- 行为不变的功能级复核：功能测试 20260824 的 28 个冒烟场景
  （skills 8 / MCP 9 / 权限边界 8 / 会话压缩 3，断言的正是 warn 文案、
  信任问答文案、工具集内容、拒绝理由）对重构后代码复跑，4 套全过。

留下的已知情况：

- 无新增待办。三条记录性疑问（assemble 参数面、Assembly 返回面偏宽、
  候选 B 的全局注入位原样保留）写在 [复盘.md](复盘.md)，不够格立 TODO。
