# 03-20260809-design-gate · 开发日志

## 2026-08-09 · 一次交付：门禁脚本 + hook 注册 + 测试

**目标**：档案未拍板不许改 src/tests，从提示词层降到确定性层。

**改动**：`guards/design_gate.py`（判定抽纯函数 `decide()`，IO 全在 main——
修 anna「无可注入边界」的短板）、`.claude/settings.json`（PreToolUse 注册）、
`docs/dev/features/.active`（指针，`!` 前缀显式放行）、`tests/test_design_gate.py`。

**测试**：新增 10 条 → `./test.sh` **75 → 85 passed, 1 deselected**。
注入验证：状态「讨论中」/ 无 .active / 档案缺失均 deny；四个合法状态均 allow。
端到端：灌真实 hook JSON，放行静默 exit 0、拦截输出 deny JSON（含补救步骤与
「不要代替用户拍板」）。

**遗留**：hook 配置快照——本会话内注册可能不生效，下次会话实测被拦后转已验收。
