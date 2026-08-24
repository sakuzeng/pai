# 31-assembly-convergence —— 装配收敛（once/interactive 两份手抄合一）
状态：已交付（2026-08-24，1353 passed；复盘见 复盘.md）
分支：`refactor/31-assembly-convergence`（自 `main` 开出，承担全部实现）
流程：中等改动直做（无 spec/plan）+ 一句话理由：改动是纯 refactor（行为与
文案逐字不变，1351 条既有测试就是判据），方案空间在需求池评估时已收敛成
三个候选并经用户拍板，不需要 brainstorm/plan 两级产物；验收项按
features/README 规矩 9 的教训写进下方「需求」节。

## 需求

`once.py:47-124` 与 `interactive.py:384-439` 是同一套装配序列
（settings→rules/hooks→skills 信任→MCP 信任→工具并表→boundary→gate→
memory→recall）的两份手抄，feature 25/28/29 三轮都同步改了两处，
TODO「优化检查 2026-08-24」已登记「装配巨石」候选。本需求把共用段抽成
一份 assembly 模块，once/interactive 只注入差异点（asker、默认权限模式、
事件通道）；顺带把 interactive 的 MCP 关闭从 atexit 改成单出口 finally
（29 遗留 7 的「若 run_interactive 重构出单一出口，顺手改确定性关闭」
条件由本次重构兑现）。

验收标准（怎么算做完）：

1. 装配逻辑只剩一份：once 与 interactive 的装配段都改为调用共用 assembly，
   两处不再各自手抄 skills/MCP/memory/recall/gate 的接线；
2. 行为与输出逐字不变（refactor 判据）：全部既有测试零改动通过
   ——warn 文案、信任问答文案、工具集内容与顺序、拒绝理由都不许变；
3. MCP 关闭从 atexit 改单出口 finally：REPL/TUI 无论正常退出、EOF 还是
   异常上抛，`close_all_mcp` 都在 run_interactive 返回前确定性执行，
   有新测试钉住（修前红：atexit 在函数返回时不触发）；
4. `./test.sh` 全绿，数字进 STATUS；29 遗留 7 从 TODO 销账。

## 候选方案与确认

### 方案 A · 装配收敛

新建共用 assembly 模块承载「settings→rules/hooks→skills 信任→MCP 信任→
工具并表→boundary→gate→memory→recall」序列，once/interactive 只注入差异点
（asker、默认模式、事件通道）；顺带 29 遗留 7（atexit→单出口 finally）。
取舍：消除三轮同步增补证实的重复面，代价是改动面大（两个装配点同时动）、
且提前兑现 TODO 既有裁决「等装配段加第三样东西时一起」的时机。

### 方案 B · 工具注入点去全局化

`skill_tool.set_catalog/set_tracker`、`memory_tool.set_memory_dir/
set_notifier/set_origin_session`、`ask.set_asker` 这批模块级全局可变注入位
改为构造期注入。取舍：与 AGENTS「依赖注入优先」对齐、消除同进程多实例互串，
但改动面在 tools 层 + 两个装配方，且互串在单进程 CLI 的现实用法里未真实撞到。

### 方案 C · 维持现状

1350 全绿、模块按学习阶段切的边界清晰，「长」不等于「乱」；装配巨石条目
维持既有裁决的时机等待。

### 确认

问 1（2026-08-24，功能测试报告「代码结构优化」节，三候选原文见
[需求池](../../需求池.md) 2026-08-24 条与该报告）：代码结构优化选哪条路？
- 候选 A·装配收敛：如上；
- 候选 B·工具注入点去全局化：如上；
- 候选 C·维持现状：如上。
选择：A。用户原话：「先把能够修改的改了 A」（前半句是对功能测试三条低级
发现的处置指示——当日 !小修 清零；「A」是本问的拍板）。
理由：用户未展开；报告中已说明选 A 等于提前兑现 TODO「等装配段加第三样
东西时一起」的时机裁决，拍板即视为接受提前。

## 结果与总结

交付：`modes/assembly.py`（`Assembly` dataclass + `assemble()`）承载共用装配
序列；once 装配段（原 47-124 行）与 interactive 装配段（原 384-439 行）各替换
为一次 `assemble` 调用 + 差异点参数；interactive 的 MCP 关闭 atexit→单出口
finally（TUI return / EOF / 异常上抛统一收口），`import atexit` 删除；
interactive 清掉 17 个失去用途的 import；扩展点.md 增补「装配」条目。

验收对账：1 装配只剩一份 ✅；2 行为逐字不变——既有测试零改动全绿，且功能
测试 20260824 的 28 个冒烟场景（断言 warn 文案/信任问答/拒绝理由/工具集）
复跑 4 套全过 ✅；3 finally 关闭有 `tests/test_assembly.py` 两条钉住
（修前红 `2 failed`：atexit 在函数返回时不触发）✅；4 全量
`1353 passed, 3 deselected`，STATUS 数字已更，29 遗留 7 已销账 ✅。

总结：三轮（25/28/29）同步增补证实的重复面收掉了；「等装配段加第三样东西」
的时机裁决由用户拍板 A 提前兑现。红→绿数字与实现细节见 [devlog.md](devlog.md)。

## 遗留问题

无新增待办。三条记录性疑问（assemble 参数面会随第三个消费方膨胀、Assembly
返回面偏宽、候选 B 的全局注入位被包了一层更不显眼）在 [复盘.md](复盘.md)
「我现在质疑什么」，不够格立 TODO——第三个消费方（阶段 7 evals 装配）出现时
一并重估。

## 用到的知识

- [扩展点.md](../../扩展点.md)——「要加 X 去哪里」的既有地图，本次把
  「装配段」从两处收敛为一处后需同步；
- TODO「优化检查 2026-08-24」装配巨石条目、「feature 29 遗留」第 7 条
  （atexit 取舍与解除条件）。
