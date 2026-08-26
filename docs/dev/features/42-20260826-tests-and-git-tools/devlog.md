# 42-tests-and-git-tools 开发日志

## Task 1 · 权限层新增 `EXEC` 档（2026-08-26）

目标：让「执行类」工具能被边界判定，且 `access` 这个字段不说谎。
形状按拍板问 3·A。

动的文件：`src/pai/core/tools/__init__.py`（新增 `EXEC` 与 `ACCESS_KINDS`，
`participates_in_boundary` 与 `path_access_for` 改用后者）、
`src/pai/core/permissions.py`（`_boundary_fallback` 的读那一支改成 `in (READ, EXEC)`）、
`tests/test_boundary.py`（+6 条）。

红：`6 failed`。绿：`tests/test_boundary.py + test_permissions.py +
test_permission_modes.py` `90 passed`。

注入反证五条。第一轮有一条没红——`acceptEdits 放宽成「不是 READ 就算」`。
按 mutation-testing-pitfalls 第五条先查实现，实现是对的，问题在我的测试挑错了场景：

- 界外：第 5 步自带 `dirs.contains` 守卫，放宽与否都进不去；
- 界内：兜底本来就 allow，两条路殊途同归。

唯一能把两者分开的是**兜底不是 `workingdir` 的时候**——`default_decision="deny"`
下第 5 步是 allow、第 7 步是 deny，放宽就会把 deny 变成 allow。改用这个场景后
注入即红。顺手加了反向守卫：同场景下「写」必须照旧被 `acceptEdits` 放行，
否则这条测试就不是在钉「EXEC 不蹭」，而是在钉「第 5 步坏了」。

## Task 2 · `run_tests`（2026-08-26）

先做了两件共用件，都是行为不变的重构，由既有测试守：

- 新增 `core/tools/output.py`：`MAX_OUTPUT_CHARS` 的家搬到这里（此前 `fs.py`
  与 `shell.py` 各一份拷贝，`recall.py` / `rules.py` 的注释还各自引用着
  「read_file 的那个 4000」——同一个数四处引用、两处定义，本轮要加第三第四个
  工具，与其变成四份不如先收口），两个老模块原样再导出，既有 import 一个字不改。
  同时放 `head_and_tail()`。
- `shell.py` 抽出 `run_process(command, seconds, *, cwd, shell)`，`bash()` 改调它；
  `_Killed` 升为公开的 `Killed`（旧名保留别名）。共用的不是「起个进程」那几行，
  是整组收割 + 心跳 + 中断 + 超时那一整套已经踩过坑的语义——第二个实现只会把
  `sleep 30 &` 留下的孙进程那类坑再踩一遍。

然后是工具本体：`core/tools/tests_tool.py`、settings 两个键
（`tests.command` / `tests.timeoutSeconds`）、装配层接线、`tests/test_run_tests_tool.py`（19 条）、
`tests/test_assembly.py`（+1 条接线测试）。

红：`19 errors`（模块不存在）。绿：`tests/test_run_tests_tool.py` `19 passed`；
接上装配后 `test_assembly + test_run_tests_tool + test_settings` `50 passed`。

三处值得记的：

一、输出保头保尾，不是头部截断。这条是本工具与 bash 最实质的差别：
bash 现在就是 `output[:MAX_OUTPUT_CHARS]`，而 pytest 的判决在最后一行——
4000 字符恰好把 `1534 passed` 扔掉，模型拿到一堆用例名却不知道过没过。
这不是假想的失效模式，是今天走 bash 跑测试就会撞上的那一个。

二、默认超时 600s 有来源：本仓库全量实测 183s，取三倍余量；而 600 本身不是新数，
它就是 bash 那边 CC 与 dsh 两家收敛出的上限。上限 3600s 是**未实测**的天花板，
如实写在注释里。

三、加了 settings 键就补一条装配接线测试。出处是 feature 33 H9 的教训：
`additionalDirectories` 在文档与 STATUS 里声称存在、实际从没接进装配——
配了静默不生效比没有这个键更糟。那次教训唯一可执行的落点就是这条习惯。

注入反证九条，全部变红（含「settings 没接进装配」那条）。
过程中踩了一个 zsh 坑：`python3 -m pytest $T`（`T="a b"`）在 zsh 下不做词分割，
第一轮九次注入全部「no tests ran」而我差点当成「反证不红」。
仪器又骗了我一次，且这次仪器是我临时写的 shell 函数。

## Task 3 · `git_read`（2026-08-26）

`core/tools/git_tool.py` + `tests/test_git_tool.py`（15 条）。
红：`14 failed, 1 passed`。绿：`15 passed`。

对拍板的一处收紧，形状不变但失效方向反过来：拍板时 flag 说的是黑名单，
我把代价写成「漏一个 flag 就是一个洞」；实现改成**按子命令的 flag 白名单**——
漏写只会让某个合法 flag 被拒（模型收到一句话就能改）。
与「判不出来就当不安全」同一条 doctrine。这条偏离记在档案而不是悄悄做掉。

两处值得记的：

一、`test_a_semicolon_cannot_smuggle_a_second_command` 断言的不是「被拦下了」，
是**第二条命令根本没跑**（`; touch 被注入了` 之后那个文件不存在）。
「拦下了」和「构造不出来」是两种强度不同的保证，测试该钉后者。

二、能力标志**收 input** 的第一个真实用户出现了。`Capability` 的签名从 feature 11
就留着这一手，注释写着「pai 今天还没有这样的工具」——`git_read` 正是：
`git log` / `show` / `branch` / `blame` / `ls-files` 是纯读、能并发；
`git status` / `diff` 会刷新索引、要拿 `.git/index.lock`，两个并发跑会撞锁。
静态布尔二选一都是错的：全 True 真会撞锁，全 False 白白放掉能并发的那一半。
`tools/__init__.py` 里那句过期的注释同时改掉了。

注入反证七条，全部变红。

## 真跑冒烟（2026-08-26）

离线全绿 ≠ 真能用（feature 38 的教训），所以在本仓库真调了一遍：

- `resolve_command` → `('./test.sh', '自动探测：项目自带的 ./test.sh（test.sh）')`
- `git_read("status", "-s")` → 真列出本轮改动的文件
- `git_read("log", "--oneline -n 3")` → 三条真提交，`[退出码 0]`
- `git_read("commit", "-m x")` → 被拒，文案指回 bash
- `run_tests(filter="exec")` → 真跑 `./test.sh -k exec`，尾部 `14 passed` 完整保留

冒烟里发现一处文案嵌套括号（`（自动探测（…））`），顺手改成破折号形式，
并把「出处」纳入断言（此前只断言了命令本身）。

## 交付（2026-08-26）

`./test.sh` 全量：`1575 passed`（此前 1534；新增 41 条 = EXEC 6 + run_tests 19
+ 装配接线 1 + git_read 15）。

刻意没做、已登记 TODO：`filter` 的 `-k` 是 pytest 写法（配成别的跑法时那边
可能不认）、探测表只认五种项目、flag 白名单不全、`git_read` 没有 path 参数、
`output.py` 只收编了两个老模块（`search.py` 仍自己做头部截断）。
