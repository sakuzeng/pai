# 40-old-debts · 开发日志

一步一条。全局 devlog 只记里程碑一行 + 指到这里。

## 2026-08-26 · 立项

用户从四个候选里选了「还旧账：夹具层 + 拆文件 + 方法论笔记」。三件事的共同点是
判据早就写下来了而没人回来查——所以这轮不是顺手清理，是把「触发条件到了要回来看」
这件事真做一遍。

改动：新建档案、`.active` 指过来、开分支 `refactor/40-old-debts`。

## 2026-08-26 · 一：共享测试夹具层

条目写的触发条件是「测试文件到 10 个左右」——发现时 80 个、1503 条用例。
但真正让我确信该动手的不是行数，是先数了一遍跨测试文件的 import：
5 处（`from tests.test_skills import _repl`、`from tests.test_recall import reply`、
`from tests.test_memory_scan import write_memory`、
`from tests.test_compaction import REAL_TRAJECTORY / REAL_USAGE_TRAJECTORY`），
还分成 `from tests.x` 与 `from x` 两种写法。测试文件 A import 测试文件 B，
意味着 B 的任何改动都可能让 A 假失败，而 A 的作者根本不知道自己依赖了 B。

落点两个而不是一个：`tests/trajectories.py`（真实会话轨迹夹具，带出处与
「pai_playground 不入库所以溯源链断了」那条诚实边界）与 `tests/helpers.py`
（`OPEN_RULES`、`scripted_reader`、`write_memory`、`recall_reply`、`run_repl`）。
分开是因为它们是两种东西：前者是数据，后者是动作。

数字：`_OPEN` 从 5 份变 1 份；脚本化 reader 从 5 个变体变 1 个
（其中两个变体是我前一天刚加的——重复正在以肉眼可见的速度增长）；
跨测试文件的 import 归零（剩下的 `fake_llm` / `tui_screen` 本就是 helper 模块，
不是测试文件）。

刻意没有归一的一处：`test_interactive.py` 里那个「每读一行就顺手改盘上的 PAI.md」
的 reader。它是真的 bespoke，硬套 `scripted_reader` 只会让共享的那个长出参数。

搬家验收不是「测试还绿」，是值逐字相等：拿 `git show HEAD:` 的旧实现与新 helper
对同一批输入比结果（`write_memory` 3 组含 mtime、`recall_reply` 3 组），全等。
过程中被自己的验收脚本绊了两次，都记下来：其一，旧 `write_memory` 的签名用了
`float | None`，在 3.9 运行期要靠文件头的 `from __future__ import annotations`
才合法，单独 exec 那个函数节点会当场 TypeError（补 `compiler_flag` 才过）——
这正是 AGENTS 里那条「3.9 目标运行期」的实例；其二，第一版比 mtime 时把
「没传 mtime」的那组也算进去了，而那组两次写入的时刻本就不同，是我的比较口径错。

全量 1503 passed 一个数字都没动——纯搬家最好的证明就是这个。

## 2026-08-26 · 二：拆文件（一个不拆，一个真拆）

`compaction.py`：重估之后不拆。触发条件的字面（「等 summarize 落地」）确实满足了，
但它自带的两个参照都不支持动手——条目自己写着「pi 的 compaction.ts 到 893 行才拆」，
而这边落地后只有 392 行（summarize 34 行，不是预估的 +300）；更硬的一条是 AGENTS
架构约束「模块边界按学习阶段切：一个阶段一个模块」，compaction 就是阶段 1，
拆成 5 个文件与那条约束直接相抵。重估的判据写进 TODO 留给下次（超 800 行，
或它开始装第二个阶段的逻辑）。

真该拆的是 `interactive.py`：1365 行，是第二大文件的两倍，且 feature 31 抽走装配
之后它反而更大了（1254 → 1365，因为 35~39 又往里加东西）。

抽的理由不是行数，是位置：`/命令` 与 `!shell` 那一簇被 REPL 主循环与 TUI 主循环
共用，而共用的东西住在其中一条循环所在的文件里，本身就是位置错误
（与 feature 36 把宽度原语从 statusline 挪进 `tui/width.py` 是同一条判据）。

动手前先量了耦合面：这一簇 12 个定义共 313 行，只用到 interactive 的 5 个模块级
名字，其中 4 个跟着一起搬，剩下 1 个是 `_interruptible`。于是先把中断三件套
（`_interruptible` / `_install_sigint` / `_restore_sigint`）搬回 `core/interrupt.py`
——论主题它本来就该在那儿，而且这样 `commands.py` 与 `interactive.py` 之间没有环。

结果：`interactive.py` 1365 → 1007，新增 `modes/commands.py` 379 行。
测试里那些私有名字的 import 改指真正的家（不做 re-export：私有名字的家应当唯一）。

验收两条：全量 1503 一个不变；以及公开面对账——用 AST 比较「旧 interactive 的
公开名字集合」与「新 interactive + commands 的并集」，两边差集都为空。

## 2026-08-26 · 三：方法论欠账

TODO 里躺着 12 条「够格升格 / 值得记进方法论」，最早的 2026-08-10。本轮清掉 6 条：

两篇新笔记：

- `knowledge/engineering/green-but-which-path.md`——「绿的是哪条路」。
  把四次同族事故合成一篇：测试为跑起来注入的参数正是真实路径卡住的地方 /
  基准注入的到达形态真实路径上不存在 / 两个坐标系在测试里恰好相等 /
  仪器把会变的量常量化让下游分支永远走同一边。共同点是「绿只证明了这套测试
  环境里被执行的那条路是对的」。
- `knowledge/engineering/todo-drift.md`——待办清单的四种失真与复核三问。
  四种里有三种是这三轮批清逐条复核时实测到的，不是推理出来的。

两处追记：

- `mutation-testing-pitfalls.md` 加第五条：反证不红时先怀疑实现，不要先怀疑测试
  （feature 39 一次交付里连撞两次：多写的无害行与漏写的有害行在测试上表现一样）。
- `process-groups-and-interrupts.md` 加第六节：进 raw mode 等于辞退操作系统的
  一批服务（ISIG / ICRNL / 行编辑），要逐条接管；漏掉的共同症状是「某个键没反应」，
  而它太容易被解释成「程序在忙」——feature 39 那条 Ctrl+C 停不了 `!命令`
  就是这么挂了十五天的。

顺带查明一件事：6 条欠账里有 5 条把落点写成了 `knowledge/concepts/`，
而那个目录早就并进了 `knowledge/engineering/`。「登记时写错落点」比「忘了写」
更常见——这条本身登记进 TODO。

## 2026-08-26 · 交付

`./test.sh`：`1503 passed, 5 deselected in 184.04s`。三件事都是不改行为的还账，
所以测试数字从头到尾没动过——这既是目标也是验收。
