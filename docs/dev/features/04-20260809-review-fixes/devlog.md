# 04-20260809-review-fixes · 开发日志

## 2026-08-09 · 一次交付：10 条评审修复，严格 TDD

**目标**：修掉代码梳理评审（R3）用户选定的 10 条。

**改动**：`guards/design_gate.py`（target_path/正则/诚实边界）、
`src/pai/core/tools/__init__.py`（类型校验/返回强转）、`shell.py`（超时部分输出）、
`cli.py`（负数校验）、`config.py`（load_dotenv 入 model_name）、
`viz/collect.py`（删补位）、`knowledge/permissions/hooks-gates.md`（旁路声明）；
测试四文件 +7 条新钉、2 条修实。

**测试**：红 **7 failed, 85 passed** → 绿 **92 passed, 1 deselected**。
红阶段每条失败都精确指向对应缺口（NotebookEdit 恒放行、非 str 返回、
超时丢输出、负数预算、跨行正则、dotenv 顺序、恒真断言）。

**遗留**：R3#5/6/8/15/16 未修，已登记 TODO。
