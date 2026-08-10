# 03-20260809-design-gate —— 方案门禁硬约束
状态：已交付（2026-08-09，待真实会话中验证 hook 生效后转已验收）
分支：早于本字段的规矩（2026-08-10 立），未回填——分支线性叠，事后用 git 推不出「在哪条上做的」

## 需求

需求未与用户讨论确认（档案未到「已拍板」）时，**代码层门禁**拒绝修改 `src/` 与
`tests/`——把「先讨论再动手」从提示词层（AGENTS.md 规矩，会被忽略）降到确定性层。
验收标准：判定逻辑有 pytest 覆盖且注入已知错误真会拦；hook 在 `.claude/settings.json`
真实挂载。

## 候选方案与确认

### 方案 A：PreToolUse hook 读档案状态（选定）

Edit/Write 命中 `src/**`/`tests/**` 时，读 `features/.active` 指向的档案 README，
状态未到「已拍板」即 deny。复用档案已有的状态字段，不新造状态文件。

### 方案 B：维持纯提示词规约（现状）

已被 anna 实践与本仓评审（R2#5）证明不可靠——软约束会被忽略。

### 方案 C：git pre-commit hook

拦得太晚：代码已经写完才拦，浪费的工作量已经发生；且拦不住「写了不提交先跑」。

### 确认（2026-08-09 三问拍板；问答完整存档，规矩 6 回补）

**问 1**：方案门禁硬约束现在就做吗？
- 候选 A·现在就做：立档案写 guard+hook+pytest，下个需求（压缩主线）开始就受保护
- 候选 B·登记 TODO 以后做：先继续压缩主线，门禁作为独立需求排期
**选择**：A（现在就做）。

**问 2**：「小修小补」的放行通道怎么设？（小修不立档案，但门禁会拦住它）
- 候选 A·`.active` 写 `!` 前缀（如 `!小修:修 typo`）：直接放行但理由留在文件里
  事后可查——绕过是显式动作不是默认
- 候选 B·小修也弹 ask：每次小修都要真人点一下，最硬但打断多
- 候选 C·不设通道：小修也必须立档案，与「小修不立档案」规矩冲突需同时改规矩
**选择**：A（`!` 前缀显式放行留痕）。

**问 3**：结果导向的精简汇报放在哪？
- 候选 A·features/README 交付总览表：功能|状态|一句话结果，一张表看完全部交付；
  不新建文件，状态仍以各档案头部为准，表只做索引
- 候选 B·独立 docs/dev/REPORT.md：专门汇报文件，多一个要同步维护的文件
- 候选 C·用里程碑模式的全局 devlog 充当：不新增东西，但历史重条目混在其中
**选择**：A（交付总览表）。

门禁方案本身选定方案 A（见上），落地时修正 anna 三条短板
（knowledge/anna/gates.md）：判定抽纯函数带测试、不硬编码任务路径
（读 `.active` 指针）、绕过是显式动作不是默认。

## 结果与总结

`guards/design_gate.py`（decide 纯函数 + main 只做 IO）+ `.claude/settings.json`
PreToolUse 注册 + `docs/dev/features/.active` 指针。测试 **10 条**全绿
（tests/test_design_gate.py，含注入已知错误：无 .active / 空 / 档案缺失 /
状态未拍板全部 deny；`!` 前缀放行；真实 .active 指针一致性防烂）。
端到端灌 JSON 验证：有档案且状态合法 → 静默 exit 0；无 .active → deny JSON
含补救步骤。全套 **85 passed, 1 deselected**。详细日志见 [devlog.md](devlog.md)。

## 遗留问题

- hook 在**本会话**注册，配置快照机制下可能需重启会话才生效——下次会话实测
  被拦一次才算「已验收」（已登记 TODO）。

## 用到的知识

[knowledge/concepts/hooks-gates.md](../../../../knowledge/concepts/hooks-gates.md)、
knowledge/anna/gates.md（本地）
