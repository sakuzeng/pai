# 42-tests-and-git-tools

状态：已交付
分支：`feat/42-tests-and-git-tools`
流程：中等改动直做（无 spec/plan）。理由：形状的四处选择在动工前已由用户
      AskUserQuestion 一次拍板（原文见「候选方案与确认」），实现路径明确。
      唯一动到核心的是权限层新增 `EXEC` 档，但那也是拍板项之一，
      且改动面已在拍板时列清（三处连带复核点）。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

用户 2026-08-26（feature 41 交付后）：把跑测试和 git 从 bash 里摘出来。

出处是 feature 41 交付汇报里我自己写的那句「现在还差什么才算能用」的第一条：
41 把「读文件」与「找代码」从 bash 手里摘出来了，但 `pytest` / `git status` /
`git diff` 结构上仍然只能走 bash，而 bash 不声明路径语义 → 兜底 ask。
于是查和读不被打断，一到「验证」这一步还是弹窗。

动工前核实的四条结构性证据（不是推测）：

1. 项目级与用户级 `settings.json` 都不存在，所以今天每一次 bash 调用都落到
   `_boundary_fallback` 的最后一档 ask——没有任何规则能提前放行。
2. bash 默认超时 `TIMEOUT_SECONDS = 120`，而本仓库全量测试跑 183s。
   也就是说今天就算用户点了「允许」，`bash ./test.sh` 也会在第 120 秒
   连同整个进程组被杀掉。跑测试今天不是「烦」，是结构上做不到。
3. bash 的输出截断是头部截断（`output[:MAX_OUTPUT_CHARS]`），而 pytest 的判决
   在尾部——4000 字符正好把 `1534 passed` 那一行扔掉。
4. 三家参照都没有专用的测试/git 工具，都是 bash + 权限规则。CC 能这么活是因为
   它有分类器模型补上「bash 碰了哪些路径」那一段（`knowledge/permissions/
   path-boundary-checks.md` 第 85 行），pi 是干脆不带沙箱且明说「部分进程内沙箱
   容易被误解为安全边界」。pai 两样都没有（D#52 认下的洞），所以这次是
   主动偏离三家，理由要进 decisions。

验收标准：

1. 在工作目录内跑测试与看 git，一次都不问（走边界兜底，不需要用户配任何规则）；
   界外要问。两半都要有测试钉，不能靠推理。
2. 跑测试的输出必须保住尾部判决行——「保住 `N passed`」是可断言的判据，
   不是「输出看起来还行」。
3. `git_read` 结构上不过 shell：`git status; rm -rf x` 不该是「被拆分匹配拦下」，
   而该是「压根构造不出来」。写操作（add/commit/push）不进白名单。
4. 新增 `EXEC` 档不许把既有两档的行为改掉一个字：`acceptEdits` 第 5 步、
   危险写检查、`participates_in_boundary` 三处各钉一条。
5. 每个新工具带正常路径 + 一个错误路径的单测；每条改动做注入反证。
6. `./test.sh` 全量绿，STATUS 数字同步。

## 候选方案与确认

四处形状由用户 2026-08-26 用 AskUserQuestion 一次拍板，四问全选推荐项。

### 问 1：跑测试这件事取什么形状？

- 候选 A·专用 `run_tests(filter, path)`，命令不由模型选（用户选中）。
  跑什么来自 settings 的 `tests.command`；未配时自动探测（有 `./test.sh` 就用它，
  否则按 `pyproject.toml` / `package.json` / `Cargo.toml` 推 pytest / npm test /
  cargo test）。模型只能给过滤表达式与路径——这正是它能自动放行而 bash 不行的原因。
  自己一档超时（bash 的 120s 会把本仓库 183s 的全量掐死），输出保头保尾。
  代价：只解决跑测试，lint/typecheck 仍走 bash。
- 候选 B·通用 `project_command(name, args)`，settings 里配一张命令表。
  一个工具覆盖 test/lint/typecheck/build 一整类，以后加 lint 不用再立工具。
  代价：不配就等于没有（要给每一类都做自动探测就是四倍工作量，不做则首次使用
  体验是「工具在那里但什么都跑不了」）；且超时与输出截断策略对 lint 与 test
  其实不同，一个工具得吃同一套。
- 候选 C·不立工具，给 bash 配受信命令前缀。零新工具。
  代价：要让它不变成 D#76 刚拒掉的那个白名单，就得给 bash 补边界——而那要做
  路径提取，D#52 已经判定过它是「看起来防住了」的半吊子。且超时与头部截断
  两个结构问题它一个也不解决。

用户选 A。

### 问 2：git 取什么形状？

三个候选都只收只读子命令，add/commit/push 一律不进——与 AGENTS
「永远不要未经要求就 commit」一致。

- 候选 A·一个 `git_read(subcommand, args)` + 子命令白名单（用户选中）。
  argv 由 pai 自己拼、不过 shell，于是 `git status; rm -rf x` 这种复合命令
  结构上不存在，不靠分隔符拆分去拦。还要挡 git 自己的注入面
  （`-c`、`-C`、`--exec-path`、`--upload-pack`、`--output` 这类能借 git
  跑任意命令或改目标仓库的 flag）。
  代价：args 仍是一个字符串，模型得知道 git 语法；白名单是硬编码名单。
- 候选 B·拆成 `git_status` / `git_diff` / `git_log` 三个工具。
  每个 schema 自解释，坏参数在 schema 层就少一半。
  代价：三份 schema 占三份 token，加 blame/show 要再写一个，三套接线写三遍。
- 候选 C·git 也走问 1 的通用命令表。最少的代码。
  代价全在 args 那一格：不许带参数则 `git diff <某文件>` 做不了（而那正是改代码时
  最常用的），许带任意参数则等于 `Bash(git *)`，`-c core.pager='sh -c …'` 原样通过。

用户选 A。

实现时对 A 做了一处收紧，形状不变但失效方向反过来：拍板时我把代价写成
「flag 黑名单漏一个就是一个洞」，实现改成**按子命令的 flag 白名单**——
不在白名单里的 flag 一律拒，并在错误文案里列出允许的。失效方向从
「漏写就放行」变成「漏写就拒绝」，与「判不出来就当不安全」同一条doctrine。
这条偏离记在这里而不是悄悄做掉。

### 问 3：「执行类」工具在边界模型里算哪一档？

`access` 现在只有 READ / WRITE 两档，而跑测试既不是读也不是写。

- 候选 A·新增 `EXEC` 第三档（用户选中）。`_boundary_fallback` 加一支：
  EXEC 且界内 → allow，界外 → ask。好处是 `access` 这个字段不说谎，
  且给将来的执行类工具留了位置（形状照 D#73 给 skill 新开一个豁免位，
  而不是在判定里写 if）。
  代价：动的是权限层的核心枚举，三处要连带复核并各钉一条测试——
  `participates_in_boundary` 的 `access in (READ, WRITE)`、
  `acceptEdits` 第 5 步的 `access == WRITE`（EXEC 不该蹭进去）、
  `_dangerous_write_check`（只看 WRITE，不该变）。
- 候选 B·就声明成 READ。零权限层改动，立刻达成「界内不问」。
  代价：`access` 从此有一个说谎的取值——下一个人看到 `run_tests` 写着 READ
  会以为它只读，而它会跑任意项目代码（写文件、联网、删东西都可能）。
  这类谎不会让任何测试变红，只会在某次有人按 access 分类做决策时出错。
- 候选 C·用现有的 `boundary_exempt`（D#73）。零权限层改动。
  代价：D#73 的判据是两条——入参表达不了路径，且它真正碰的路径由 pai 自算
  （skill 指的是装配期扫描出的文件）。`run_tests` 只满足前半；把「在 cwd 起一个
  进程」也算进去，就把豁免位撑宽成「反正判不了就放行」，而它现在只有一个用户，
  正是撑宽最容易发生的时候。

用户选 A。

一处由此顺下来的判断（不另开一问）：`git_read` 也声明 EXEC 而不是 READ。
它同样是起一个进程，把它写成 READ 是同一类谎的小号版本；而 EXEC 给出的
放行结果与 READ 完全一样，没有付出代价。于是 EXEC 的语义定成
「起一个进程」，而不是「碰一个文件」——这也让它和 READ/WRITE 的分界线
在下一个工具到来时是可判的。

### 问 4：本轮范围

- 候选 A·就这两条（用户选中）。两个新工具 + 权限层新档位已经是一次交付的量。
- 候选 B·再带 `edit_file` 按行号替换。41 的 offset 让模型拿到了行号，
  而 edit_file 只有唯一精确替换，两边坐标系没接上。
  代价：行号会因为自己前面的修改而漂，是个有真坑的设计，不是顺手活。
- 候选 C·再带 diff 呈现。
- 候选 D·再带任务清单。它不是一个工具，是跨轮状态 + UI + 压缩后怎么活下来。

用户选 A。其余登记 TODO。

## 结果与总结

三个 Task 都做了，全量 `1575 passed`（此前 1534）。过程见 [devlog.md](devlog.md)，
取舍升格成 [D#77](../../decisions.md)（为什么偏离三家参照）与 D#78（为什么加 EXEC 档）。

- `EXEC` 第三档：`_boundary_fallback` 里与 READ 同待遇（界内 allow / 界外 ask），
  但保留为两个取值——买到的不是行为，是「下一个执行类工具算哪一档」的判据。
- `run_tests(filter, path)`：命令来自 `tests.command` 或自动探测（五种项目），
  模型只能给「跑哪一部分」。默认超时 600s（本仓库实测 183s 的三倍余量），
  输出保头保尾。
- `git_read(subcommand, args)`：argv 由 pai 拼、不过 shell；子命令白名单 +
  按子命令的 flag 白名单；写操作不进白名单，仍走 bash 的 ask。

验收标准六条的对账：

1. 界内不问 / 界外要问 —— 两个工具各两条，走真的 `permissions.decide`。
2. 保住尾部判决 —— `test_long_output_keeps_the_verdict_at_the_end` 断言
   `1534 passed` 还在，且注入「改回头部截断」当场变红。
3. 不过 shell —— `test_a_semicolon_cannot_smuggle_a_second_command` 断言的是
   第二条命令**根本没跑**（那个文件不存在），不是「被拦下了」。
4. 不改既有两档 —— 三条连带复核各一条测试，其中 `acceptEdits` 那条的可观察点
   找了两次才找对（见 devlog）。
5. 正常路径 + 错误路径 —— `run_tests` 三条错误路径（探测不到 / path 不存在 /
   非法超时配置），`git_read` 四条（非白名单子命令 / 危险 flag / 未列出的 flag /
   引号不闭合）。注入反证共 21 条（5 + 9 + 7），全部变红。
6. 全量绿 + STATUS 同步 —— 都做了。另在真仓库手工冒烟一遍（见 devlog）。

## 遗留问题

每条已同步登记 TODO（「feature 42 遗留与发现」节）。

- `run_tests` 的 `filter` 按 pytest 的 `-k` 传递，`tests.command` 配成别的跑法时
  那边可能不认——已知限制，不在代码里假装通用。
- 探测表只认五种项目（test.sh / Python / Node / Rust / Go），认不出就报错指路。
- `git_read` 的 flag 白名单不全，漏写的合法 flag 会被拒（失效方向是安全的那一侧）。
- `git_read` 没有 path 参数（`-C` 也在拒绝名单里），只能在 cwd 跑。
- `output.py` 只收编了 `fs.py` 与 `shell.py` 两处拷贝，`search.py` 仍自己做头部截断。
- 「跑什么不由模型决定」是这两个工具自动放行的**存续条件**，而它今天只写在
  注释与 decisions 里，没有任何机器检查。

## 用到的知识

- `knowledge/permissions/path-boundary-checks.md`（CC 用分类器补 bash 那一段，pai 没有）
- `knowledge/permissions/cc-pi-permission-boundaries.md`（pi 不带沙箱及其原话）
- `knowledge/engineering/process-groups-and-interrupts.md`（跑测试要复用 shell 的整组收割）
- `knowledge/engineering/mutation-testing-pitfalls.md`（注入反证第五条：反证不红时先怀疑实现）
- `knowledge/engineering/instruments-lie.md`（这轮的仪器是我临时写的 shell 函数，zsh 不做词分割）

