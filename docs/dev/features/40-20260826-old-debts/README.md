# 40-old-debts
状态：已交付
分支：`refactor/40-old-debts`
流程：中等改动直做（无 spec/plan）。理由：三件互不相干的旧账各自独立，
      没有整体方案可设计；每件的判据都早就写在 TODO 里，本轮是回去执行它们。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

用户 2026-08-26 从四个候选里选了「还旧账：夹具层 + 拆文件 + 方法论笔记」。

这三类的共同点，也是它们值得一起还的理由：判据早就写下来了，而没人回来查。
这正是本仓库这几轮反复撞到的那个毛病（feature 35 复盘写过一次、38 复盘又写过一次），
所以这次不是「顺手清理」，是把「触发条件到了要回来看」这件事真做一遍。

三件事各自的判据与现状：

1. 共享测试夹具层。条目写的触发条件是「测试文件到 10 个左右」——现在 80 个、
   1503 条用例。更实的证据是跨测试文件的 import 已经出现 5 处
   （`from tests.test_skills import _repl`、`from tests.test_recall import reply`、
   `from tests.test_memory_scan import write_memory`、
   `from tests.test_compaction import REAL_TRAJECTORY / REAL_USAGE_TRAJECTORY`），
   以及 `_OPEN` 在 5 个文件里各定义一遍、脚本化 reader 在 3 个文件里各写一遍
   （其中两个变体是我今天刚加的）。
2. 拆文件。`compaction.py` 那条的触发条件是「等 summarize 落地（预计 +300 行）再拆」
   ——落地了，但文件只有 392 行，不是预计的量级；而条目自己写着「pi 的
   compaction.ts 到 893 行才拆」。所以本轮要做的是重估，不是照着勾打钩。
   真正该拆的是另一个文件，见「结果」。
3. 方法论笔记。TODO 里躺着 12 条「够格升格 / 值得记进方法论」，最早的
   2026-08-10，最新的今天。我在 35 复盘里专门给「升格」定过触发点，
   然后 36/37/38/39 又各添一条——这是唯一一类我反复承诺又反复没做的账。

验收标准：

1. 夹具层：跨测试文件的 import 归零，重复的 helper 各自只剩一份；
   行为不变（测试数字与内容不因搬家而变）。
2. 拆文件：拆或不拆都要给出理由并落进 TODO；拆的那个必须行为逐字不变。
3. 方法论：写出来的每篇都带 pai 锚点（写不出锚点的就地降级，说明为什么），
   对应 TODO 条目销账。
4. `./test.sh` 全绿，STATUS 数字同步。

## 候选方案与确认

本轮无需拍板：三件事的做法都在原条目里写着，我要做的是执行与重估。
一处例外记在下面（`compaction.py` 重估的结论与条目预期相反），
按「先看代码现状再看条目描述」的规矩，结论与理由一并写进 TODO。

## 结果与总结

三件事都不改行为，所以全量测试数字从头到尾没动过：`1503 passed, 5 deselected`。
这既是目标也是验收——纯搬家最好的证明就是数字一个不变。

一、共享测试夹具层。跨测试文件的 import 归零（此前 5 处，还分两种写法）；
`_OPEN` 从 5 份变 1 份、脚本化 reader 从 5 个变体变 1 个。落点分两处：
`tests/trajectories.py`（数据：真实轨迹夹具 + 出处 + 溯源链断了的诚实边界）与
`tests/helpers.py`（动作：`OPEN_RULES` / `scripted_reader` / `write_memory` /
`recall_reply` / `run_repl`）。搬家验收是「值逐字相等」而不是「测试还绿」：
拿 HEAD 的旧实现对同一批输入比结果，全等。

二、拆文件，一个不拆一个真拆。`compaction.py` 重估后不拆——触发条件的字面满足了，
但它自带的参照（pi 893 行）与 AGENTS 的「一个阶段一个模块」都不支持，
392 行不该拆成 5 个文件；重估判据留给下次。真该拆的是 `interactive.py`
（1365 行，且 feature 31 抽走装配后反而更大了），抽出 `modes/commands.py`：
`/命令` 与 `!shell` 那一簇被两条主循环共用，共用的东西不该住在其中一条的文件里。
顺带把中断三件套搬回 `core/interrupt.py`（论主题它本就该在那儿，也避开了环）。
`interactive.py` 1365 → 1007。公开面用 AST 对账，两边差集都为空。

三、方法论欠账清 6 条：两篇新笔记
（[green-but-which-path](../../../../knowledge/engineering/green-but-which-path.md)、
[todo-drift](../../../../knowledge/engineering/todo-drift.md)）+ 两处追记
（注入反证第五条坑、raw mode 之后要接管什么）。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处 -->

- 方法论欠账还剩 6 条（40 遗留）：要么已并进这两篇、要么是「工程习惯小条」
  不够独立一篇。已登记 TODO。
- 「登记时写错落点」比「忘了写」更常见（40 发现）：6 条欠账里 5 条指着
  `knowledge/concepts/`，而那个目录早就并进 `knowledge/engineering/` 了。
  已登记 TODO。
- `interactive.py` 还有 1007 行，`_run_tui`（304）与 `run_interactive`（234）
  是剩下的大头，它们是真的复杂而不是堆积——不设触发条件、不预约下一次拆。

## 用到的知识

本轮产出知识：见 knowledge/engineering/（新笔记与追记，交付时列全）。
