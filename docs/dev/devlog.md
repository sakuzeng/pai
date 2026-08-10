# 开发日志

「做了什么」的时间线。为什么这么选见 [decisions.md](decisions.md)，
下一件该做什么见 [TODO.md](TODO.md)。

**2026-08-09 起**：本文件只保留「里程碑」区——一行一条（一致性测试强制），
功能细节住 `features/<NN>/devlog.md`。此前 17 条详细历史条目（2026-08-02 ~ 08-09）
已整体归档至 [archive/devlog-2026-08.md](archive/devlog-2026-08.md)，内容原样未改。

## 里程碑（2026-08-09 起的唯一合法追加区；一行一条，格式由 tests/test_docs_consistency.py 强制）

- 2026-08-02 harness 骨架落地——loop / 4 工具 / JSONL 落盘 / once 模式，`pai "任务"` 可真跑 → [archive](archive/devlog-2026-08.md)
- 2026-08-03 压缩地基与真实 usage 锚定（误差 1.3%）、框架对齐 pi、pai-viz 交付、冷眼评审消化、P0 五条清完 → [archive](archive/devlog-2026-08.md)
- 2026-08-09 模板与对账——features/_template 五件骨架、追认 00 基座档案、TODO 陈账 R#8/R#9 核销、STATUS 测试数对账 → [features/](features/README.md)
- 2026-08-09 R2#1 终裁「不入库」——knowledge/anna 与体系评审文件进 .gitignore，「失去版本控制备份」的代价如实记 → D#35
- 2026-08-09 knowledge 扩容——inbox.md 收件箱（准入唯一豁免区，首批 4 条）+ concepts/ 随 hooks-gates 首篇创建 → [knowledge/](../../knowledge/README.md)
- 2026-08-09 03-design-gate 立项→交付——方案未拍板不许改 src/tests 的 PreToolUse 门禁，注入验证真会拦 → [档案](features/03-20260809-design-gate/README.md)
- 2026-08-09 02-compaction brainstorm→spec 定稿——三问拍板完整存档，待批后进 plan → [档案](features/02-20260803-compaction/README.md)
- 2026-08-09 04-review-fixes 立项→交付——R3 全量代码梳理 15 条修 10，TDD 7 红转绿 92 passed → [档案](features/04-20260809-review-fixes/README.md)
- 2026-08-09 CLAUDE.md 新建——@AGENTS.md 自动加载入口（AGENTS 不进上下文本会话实证）；evals/playground 裁决不动 → CLAUDE.md
- 2026-08-09 借鉴 anna 三项——功能目录名带立项日期、拍板问答完整存档（02/03 回补全文）、evidence/ 按需规矩，94 passed → [features/](features/README.md)
- 2026-08-09 devlog 治理——里程碑区硬格式 + 一致性测试强制；宣布当天即被违反的长条目压缩至此（细节都在对应档案，未提交故不算改史）→ 本节即格式
- 2026-08-09 devlog 历史归档——17 条详细条目原样迁入 archive/devlog-2026-08.md，主文件 828→22 行 → [archive](archive/devlog-2026-08.md)
- 2026-08-09 decisions 加索引——36 条一行标题表+一致性测试钉住，正文一字未删；32-36 条错位节名归正 → [decisions.md](decisions.md)
- 2026-08-09 02-compaction spec 获批→plan 定稿——6 task 带全量代码严格 TDD，待提交现有改动后开 SDD 分支 → [plan](features/02-20260803-compaction/plan.md)
- 2026-08-09 02-compaction 阶段 1 主线交付——触发/切/摘/重建/熔断接进 loop，e2e 钉死单锚不可切的隐藏约束，113 passed → [档案](features/02-20260803-compaction/README.md)
- 2026-08-09 02-compaction SDD 六 task 完成——AnchorBook/find_cut_point/summarize/compact/熔断/接线全链 TDD，2 轮任务级修复（含 Critical：测试文件被重写当场恢复）→ [档案](features/02-20260803-compaction/README.md)
- 2026-08-09 02-compaction 终审通过——最强模型全分支审查 With fixes（Critical：摘要 usage 漏记预算，计划自带 bug）→ 修复波 4/4 复审 clean，115 passed；5 项 Minor 延后入 TODO → [档案](features/02-20260803-compaction/README.md)
- 2026-08-10 05-repl 立项→交付——阶段 2 前半程：事件流定型/双队列/中断到进程组/REPL/AskUser/状态行，8 task TDD，193 passed → [档案](features/05-20260810-repl/README.md)
