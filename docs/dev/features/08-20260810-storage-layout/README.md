# 08-20260810-storage-layout —— 落盘布局对齐 CC

状态：已交付（2026-08-10，4 task TDD，276 passed；已合并 main。端到端实测「别人的项目里不再拉 sessions/」已过，其余待用户逐项验收）
分支：`feat/08-storage-layout`（自 `main` 开出，不叠在旧分支上；按 2026-08-10 立的命名规约带档案编号，分支名自己指得回本档案）

## 需求

来源 [需求池](../../需求池.md)：用户翻自己的 `~/.pai` 时问「`~/.pai/projects/2b0a92ef14633a56/memory`
又是什么鬼，为什么不和 cc 一致呢（包括 session 记录和 memory）」。

三处不一致：

| | CC | pai 现状 | 判定 |
|---|---|---|---|
| 项目标识 | `-Users-sakuzeng-improve-...`（可读全路径） | `2b0a92ef14633a56`（16 位哈希） | 改 |
| 会话 JSONL | `~/.claude/projects/<slug>/` | **当前工作目录 `./sessions/`** | 改（最严重） |
| 记忆 | `~/.claude/projects/<slug>/memory/` | `~/.pai/projects/<hash>/memory/` | 位置对，改名 |

**最严重的是第二行**：pai 的立意是**在别人的项目里跑**，而它会往人家仓库里写 `sessions/` 目录。
本仓库因为 `.gitignore` 挡着所以一直没察觉。

## 候选方案与确认

### 2026-08-10 两问拍板（用户）

**问 1**：项目标识（目录名）用哪种？
- 候选 A·**完全照 CC：全路径连字符** `-Users-sakuzeng-improve-coding-agent-projects-pai`。
  一眼看出是哪个项目、与 CC 完全一致、无碰撞；代价是目录名很长。
- 候选 B·仓库名 + 短哈希 `pai-2b0a92ef`。短、`ls` 清爽；但与 CC 不一致
  （而用户提的正是「为什么不和 cc 一致」），且同名仓库在不同路径时仍要靠眼睛对哈希。

**选择：A**。

**问 2**：会话 JSONL 要不要一并挪进 `~/.pai/projects/<slug>/sessions/`？
- 候选 A·**挪进去，对齐 CC**：不再污染别人的项目、同项目会话集中可查、与记忆同居。
  代价：`ls` 当前目录不再直接看到会话文件。
- 候选 B·继续写当前目录：改动最小，但**在别人项目里跑会当场拉一坨**，而那正是 pai 的主场景。
- 候选 C·默认挪走但加 `--session-dir` 参数：多一个参数要维护与测试。

**选择：A**。

### 更早已定（2026-08-10，用户在讨论中裁决）

**老数据直接删除，不写迁移代码。** 所以本功能**不含**任何迁移逻辑——
旧的 `~/.pai/projects/<hash>/` 与各处 `./sessions/` 由用户自行删除（清理 `~/.pai` 时已删过一批）。

### 为什么是一个档案而不是两个

按 [features/README 规矩 7](../README.md) 的判据（「这次改动是在**完成**那次交付，
还是在**改变**那次交付的结果」）：session 位置与 memory 目录名是**同一次交付**——
同一批改动、同一套测试、同一个「老数据怎么办」的决定。拆成两个会得到两份几乎一样的 spec。
它改变的是 feature 00（session）与 06（memory）的交付结果，所以**新建**档案，
旧档案冻结不改。

## 实施

[spec.md](spec.md) → [plan.md](plan.md) → TDD。

## 结果与测试

4 个 task TDD，`259 → 272 passed`，每步数字见 [devlog.md](devlog.md)。

**端到端实测**（整个需求的初衷）：在 `/tmp/othersproject` 里跑完一轮再退出——
`ls -a` 只有 `.` 与 `..`，**没有被拉一坨 `sessions/`**；会话落在
`~/.pai/projects/-private-tmp-othersproject/sessions/20260810-221805-36c2fc1a.jsonl`，
记录里 `cwd = /private/tmp/othersproject`（集中存放后仍分得清在哪跑的）。

顺带关掉旧账 **R#15**（同秒建两个 SessionLog 写同一文件）。
两条取舍进 decisions：**D#44** slug 用全路径连字符并接受与 CC 同款的碰撞、
**D#45** 会话文件名保留时间戳前缀而非 CC 的纯 uuid。

## 遗留问题

5 条全在 TODO「feature 08（落盘布局）遗留」。其中两条来自[复盘](复盘.md)的质疑节，
是对**本次做法本身**的质疑：「顺手并入」的判据太松（`sessionId` 是搭便车的）、
涉及删除的拍板没说清「执行时你能否分辨要删什么」。

## 用到的知识

[knowledge/source-walks/cc-memdir.md](../../../../knowledge/source-walks/cc-memdir.md)（CC 的记忆目录布局与召回机制）、
[knowledge/claude-docs/memory.md](../../../../knowledge/claude-docs/memory.md)（官方：存储位置按 git 仓库归并，worktree 共享）
