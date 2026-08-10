# 09-20260810-working-dir-boundary · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-11 · Task 1：工具自我声明 `get_path` 与 `access`

**目标**：目录边界要知道「这次调用碰哪个路径、是读是写」，而这只有工具自己知道。
延续拍板问 2 的「语义下放给工具」，**权限层不许按工具名分支**。

**改动**：
- `src/pai/core/tools/__init__.py`：`Tool` 加 `get_path` / `access` 两字段；
  新增 `PathGetter` 类型、`READ`/`WRITE` 常量、`participates_in_boundary()`、
  `path_access_for()` 装饰器
- `src/pai/core/tools/fs.py`：三件套各自声明（read 一个、write 两个）
- `tests/test_permissions.py`：+5 条
- `docs/dev/STATUS.md` 测试数字 329 → 334

**测试**：红 `5 failed, 29 passed`（`AttributeError: 'Tool' object has no attribute 'access'`），
绿 `34 passed in 0.38s`。
全量：`329 passed, 3 deselected` → **`334 passed, 3 deselected`**。

**比 plan 多写一条**（plan 说 +4 → 333，实际 +5 → 334）：
补了 `test_path_access_for_rejects_unregistered_tool`——与 `matcher_for` 同款的
「挂到没注册的工具上当场抛」。理由同 feature 07：默默不生效意味着一个工具
静默退出边界保护，而那正是最不该静默的地方。

**中间红了一次、且是该红的**：`test_status_reports_the_current_test_count`。
我按 plan 写的 +4 去改 STATUS（写成 333），实际是 +5（334），当场被机器对账逮住。
**这正是 07 立这条规矩时想防的**——plan 里的预估数字不等于实际数字，
靠人肉记会漂。

**「bash 进不了边界判定」是结构性的，不是 if**：`test_bash_declares_neither` 断言
`bash.access is None and bash.get_path is None and not bash.participates_in_boundary()`。
拍板问 2 的结论落在**工具没有声明**上，而不是权限层里一句
`if tool_name == "bash": skip`——后者会在加第五个工具时被人照抄成新的分支。

**一处 plan 没写但值得记的**：`get_path` 取的是**声明的那个参数**，
不是「第一个参数值」（默认 matcher 那套）。fs 三件套碰巧都是 `path` 打头，
写成「取第一个」现在也能过，但加第四个碰路径的工具时会静默取错参数。
`test_get_path_reads_the_declared_argument` 用 `edit_file(path, old, new)` 钉这条。

**遗留**：无（本 task 只加声明，未接线）。

## 2026-08-11 · Task 2：边界判定核心（纯函数，先不接线）

**目标**：`core/boundary.py` —— 提供 CC 那个 `in_working_dir`，纯函数，
不 import permissions（反向依赖）。

**改动**：
- 新增 `src/pai/core/boundary.py`（`WorkingDirs` / `path_in_working_path` /
  `paths_all_inside`）
- 新增 `tests/test_boundary.py`（10 条）
- `docs/dev/STATUS.md` 测试数字 334 → 344

**测试**：红是 collection error（`ModuleNotFoundError: No module named 'pai.core.boundary'`），
绿 `10 passed in 0.36s`。
全量：`334 passed, 3 deselected` → **`344 passed, 3 deselected`**（+10，plan 估的是 +7）。

**多写的三条里有一条是 plan 完全没想到的**，而且它是本 task 最重要的一条：

`test_relative_paths_resolve_against_current_cwd_not_the_boundary`
——**与 plan 那条 `test_boundary_uses_startup_cwd_not_current_cwd` 配对，方向相反，
两条必须同时成立**：

- 边界集合锚在**启动 cwd**（照 CC `getOriginalCwd()`）：agent 中途 `cd` 出去，
  边界不跟着跑；
- 但**相对路径按进程当前 cwd 解析**：因为工具真正 `open()` 的就是那个路径。

写 plan 时我只想到前者。真去实现才发现：如果相对路径也按启动 cwd 解析，
那么 `cd /etc` 之后 `read_file("passwd")` 会被算成 `<proj>/passwd`（界内、放行），
**而实际读到的是 `/etc/passwd`**——一条干净的 cd 逃逸。
两条锚点必须不同，这是本模块最反直觉的地方，docstring 里写了理由。

另两条补的：`test_empty_path_is_not_inside`（`get_path` 拿到脏输入会返回空串，
此时不能默认放行）、`test_dotdot_traversal_is_normalized`。

**`test_prefix_is_not_enough` 是真会咬人的一条**：
`"/tmp/proj-evil".startswith("/tmp/proj")` 为 True。边界判定写成朴素前缀比较的话，
攻击者在项目旁边建一个 `<项目名>-evil` 目录就越界了。实现里比到**分隔符边界**
（`base.rstrip(sep) + sep`），测试里先断言 `startswith` 确实会误判、再断言我们没误判。

**`paths_all_inside([])` 返回 False，不是 True**：空集合意味着「判不出来」，
而 `all([])` 的数学惯例是 True。这里刻意反直觉——判不出来不等于没问题。
Task 4 的符号链接双路径会依赖这条。

**遗留**：本模块刻意不 realpath（符号链接双路径是 Task 4）。
现在只看给定路径，与 feature 07 的 `fs.target_path` 同款边界。

## 2026-08-11 · Task 3：兜底接线（**分水岭：行为在此改变**）

**目标**：把 `default_decision` 从常量变成**函数**——读 → 界内 allow / 界外 ask；
写 → 一律 ask；bash → ask。这一步之后 pai 的默认姿态才真正不同于 feature 07。

**改动**：
- `src/pai/core/permissions.py`：新增 `WORKING_DIR` 取值与 `_boundary_fallback()`；
  `RuleSet.default_decision` 默认值 `allow` → `workingdir`；`decide()` 加 `working_dirs` 注入点
- `src/pai/core/hooks.py`、`src/pai/core/gate.py`：透传 `working_dirs`
- `src/pai/modes/{once,interactive}.py`：**新增 `rules` 注入点**（见下）
- `tests/test_permissions.py`：+9 条，**另改了 feature 07 的 3 条**
- `tests/test_modes.py`、`tests/test_interactive.py`：**改了 6 条**（见下）
- `docs/dev/STATUS.md` 测试数字 344 → 353

**测试**：红 `9 failed, 34 passed`（`TypeError: decide() got an unexpected keyword
argument 'working_dirs'`）。绿之后全量跑出**两波预期外的红**，两波都值得记。

**行为变化已生效**（`test_once_degrades_boundary_ask_to_deny` 钉死）：

```
once 模式：  read_file(<proj>/a.py)  → allow
            read_file(/etc/passwd)   → deny
            write_file(<proj>/a.py)  → deny
            bash("ls")               → deny
```

即 **once 从「什么都能干」变成「启动 cwd 内只读」**。这是拍板时明确接受的代价。

### 第一波红：feature 07 的 3 条测试（预期内，但 plan 没预告）

`test_no_match_falls_back_to_default_decision`、`test_tool_name_glob_matches_whole_name`、
`test_default_matcher_globs_first_argument` 变红。原因不是它们测错了，而是它们
**拿「没匹配上 → allow」当信号**——而默认值刚被我改掉。

改法是**显式化前提**而非改断言：给它们传 `default_decision="allow"`。
这三条测的是规则匹配逻辑（glob 范围、第一个参数匹配、没命中就走兜底），
不是「默认值是什么」；后者由新的 `test_default_is_now_workingdir` 单独钉。

### 第二波红：6 条 e2e（**这波暴露了一个 plan 没想到的接线缺口**）

`test_once_event_output_is_byte_identical`、`test_repl_shows_memory_writes`、
`test_asker_*` 等 6 条全红，报错都是同一个形状：

```
🔧 bash({'command': 'echo hi'}) → 权限被拒绝，该工具调用未执行。原因：`bash` 不参与
工作目录边界判定（未声明路径语义），按最保守处理；这条规则要求人工确认，而当前模式无人可问
```

它们测的是**事件流渲染与 asker 接线**，跟权限无关，却被新兜底整体拦住了。
根因是 `run_once` / `run_interactive` **没有权限注入点**——权限规则是装配层
从磁盘 `load_rules()` 硬读的，测试无从旁路。

处置：给两个 modes 加 `rules` 注入点（`None` = 从磁盘读），受影响的测试注入
`RuleSet.from_lists(default_decision="allow")` 并在注释里写明「本测试不关心权限」。
合「依赖注入优先」的架构约束，Task 6 的模式注入也会复用这个位置。

**其中一条的修法是反的，值得单记**：`test_slash_permissions_lists_rules_with_source`
测的**正是**「从磁盘读到的规则要显示出来」，被 `_run` helper 里
`kwargs.setdefault("rules", _OPEN)` 一并覆盖后反而失败了。它必须**显式传 `rules=None`**
才能走回磁盘读取路径。同一个注入点，一半测试用它旁路、一半测试要绕开它——
这种地方最容易在将来被人「统一一下」改坏。

**一处实现取舍**：`_boundary_fallback` 对**没注册/没声明**的工具返回 `ask` 而不是 `allow`。
CC 在这种情况返回 ask（后面有 bashClassifier 兜），pai 没有分类器但仍选 ask——
「判不出来」应该落到最保守的一档，与 `paths_all_inside([]) == False` 是同一条原则。

**遗留**：
- `visible_tools` 与边界无关，裸名 deny 仍照旧工作，未受影响。
- 模式（`acceptEdits` 等）还没有，所以现在**没有任何办法让 once 跑 bash**——
  只能配 allow 白名单。Task 6 补 `bypassPermissions` 与 CLI flag 之前，
  这是个真实的可用性缺口，不要在此状态下宣告交付。

## 2026-08-11 · Task 4：符号链接双路径（关掉 feature 07 TODO#3）

**目标**：一条路径展开成「原始 + realpath 解析后」两条，全链共用。
关掉 07 留下的洞：一条软链就能绕开 deny 规则。

**改动**：
- `src/pai/core/boundary.py`：新增 `get_paths_for_permission_check()`；
  `WorkingDirs` 加 `all_resolved()` / `_contains_one()`，`contains()` 改为双路径
- `src/pai/core/tools/fs.py`：`path_matcher` 对两条路径分别比对；
  删掉「已知洞」那段注释
- `tests/test_boundary.py`：+5 条
- `tests/test_permissions.py`：**改写 1 条**（07 那条）+ **新增 1 条**
- `docs/dev/STATUS.md` 测试数字 353 → 359

**测试**：红 `6 failed, 53 passed`，绿 `59 passed in 0.42s`。
全量：`353 passed, 3 deselected` → **`359 passed, 3 deselected`**。

**预期内的改写（plan 就是这么写的）**：
`test_symlink_double_check_is_not_implemented` → `test_symlink_cannot_bypass_deny`。
07 那条钉的是「软链能绕开 deny」的**当时行为**，本 task 做完它按设计变红，
于是改写成正向断言。**这是「把已知洞写成测试」这个做法的完整闭环**——
洞被堵上时，那条测试会主动告诉你「该改我了」，而不是悄悄地继续绿着。

**`require_all` 在这里第二次派上用场，而且不用加任何新参数**：
- allow 判定（`require_all=True`）：**两条路径都干净**才放行；
- deny/ask 判定（`False`）：**任一条脏**就拦。

feature 07 spec 里那句「与官方符号链接规则的不对称是同一个思想」，
到这一步才真正兑现。新增的 `test_symlink_allow_requires_both_paths_clean` 钉死它：
名字在 `src/` 下、真身在界外的软链，**不该**被 `allow=["read_file(/src/**)"]` 放行。

**一条 CC 注释救了我一次误拒**：`test_working_dirs_are_resolved_the_same_way`。
工作目录本身若是软链（`/tmp/link-proj` → `/tmp/real-proj`），
待查路径 realpath 之后是 `/tmp/real-proj/...`，拿它跟未解析的 `/tmp/link-proj`
比就永远不匹配——**把本该放行的全拒了**。CC 的注释专门标了这个坑
（举的例子是 macOS 的 `/System/Volumes/Data/...`）。
所以 `all_resolved()` 对工作目录用的是同一个展开函数，两边对称。

**替换了 plan 的一条测试，如实记**：plan 写的是
`test_paths_to_check_computed_once`（白盒断言 realpath 只算一次，
CC 注释说不这么做是 30 次 syscall）。实际写成了
`test_paths_for_permission_check_returns_both` +
`test_paths_for_permission_check_dedups_when_not_a_symlink` 两条**语义测试**。
理由：调用次数是性能特征，用 monkeypatch 计数去钉它，测试会随任何一次无害重构
（多一层缓存、换个调用点）变红，属于典型的脆测试。
**性能这条只在 docstring 里记了理由，没有测试保护**——如实说明，不假装覆盖了。

**遗留**：
- 双路径展开每次判定都会做 `realpath`（未缓存）。CC 用 `memoize` 缓存工作目录的
  解析结果，pai 没做——工作目录集合是会话级不变量，值得缓存。登记 TODO（P2，性能）。

## 2026-08-11 · Task 5：危险路径清单（bypass 免疫）

**目标**：写**持久化位点**一律要确认，且 allow 规则与 `default_decision="allow"`
都翻不过它。挡的不是「重要文件」，是「写进去之后 pai 退出了那段代码还会执行」的位置。

**改动**：
- `src/pai/core/boundary.py`：新增 `is_dangerous_write()` + 三张清单
- `src/pai/core/permissions.py`：新增 `_dangerous_write_check()`，
  插在 **deny 之后、ask/allow 之前**
- `tests/test_boundary.py`：+5 条；`tests/test_permissions.py`：+4 条
- `docs/dev/STATUS.md` 测试数字 359 → 368

**测试**：红 `7 failed, 61 passed`，绿 `68 passed in 0.44s`。
全量：`359 passed, 3 deselected` → **`368 passed, 3 deselected`**。

**插入位置是本 task 唯一需要想清楚的事**：排在 **deny 桶之后**（deny 不能被降级成
ask，`test_deny_rule_still_takes_precedence_over_dangerous_check` 钉死），
但排在 **ask/allow 规则命中的返回之前**——这就是「bypass 免疫」的实现位置。
写成「求值链最后再查一次」是不行的：allow 规则一旦命中就直接返回了，根本走不到。

**清单里最该解释的一条是 `~/.pai/settings.json`**（CC 有对应的 `isClaudeSettingsPath`）。
不挡它的话，「帮我把这条规则加进 settings.json」就是一条**合法的提权路径**——
agent 改掉自己的权限规则，下一轮就畅通无阻了。项目级 `.pai/settings.json` 同理。

**`.git/hooks` 用「路径里含这一段就挡」而不是锚定项目根**：
git hooks 在**任何**仓库里都是执行点，agent 可能在子模块、临时 clone 里写。
`test_git_hooks_are_protected` 里那条 `nested/.git/hooks/post-merge` 钉的是这个。
同时只挡 `hooks` 不挡整个 `.git`（`.git/config` 仍可写）。

**只挡写不挡读**（`test_dangerous_read_is_not_blocked`）：挡读会让 agent 连自己的
配置都看不了，而读走漏的风险归工作目录边界那层管——`~/.ssh` 本来就在界外，
默认就要确认。两层职责不重叠。

**危险路径也走双路径检查**：软链指向 `~/.bashrc` 同样拦，与 deny 规则同款
「任一脏就拦」。Task 4 的 `get_paths_for_permission_check` 在这里第三次复用。

**遗留**：
- 清单是**硬编码**的，用户不能增删。CC 的清单也基本是硬编码，
  但 pai 连「看一眼当前清单」的入口都没有（`/permissions` 不列它）。登记 TODO。
- Windows 路径（`AppData`、注册表相关）完全没考虑——pai 目标平台是 macOS/Linux，
  但清单里 `.bashrc` 这种写法在 Windows 上静默失效，如实记。

## 2026-08-11 · Task 6：权限模式四态 + 配置入口

**目标**：`default` / `acceptEdits` / `dontAsk` / `bypassPermissions`，
并补上 Task 3 留下的可用性缺口（once 撞到 ask 全被拒、没有任何出路）。

**改动**：
- `src/pai/core/permissions.py`：`MODES` 四常量；`RuleSet.mode`；
  **`decide()` 整体重构**成显式七步求值链；`load_rules` 读 `defaultMode`
- `src/pai/core/gate.py`：`dontAsk` 后处理，与 `asker is None` 合流
- `src/pai/core/hooks.py`：透传 `mode`
- `src/pai/cli.py`：`--permission-mode` + `--dangerously-skip-permissions`
- `src/pai/modes/{once,interactive}.py`：`mode` 参数；once 默认 `dontAsk`
- 新增 `tests/test_permission_modes.py`（14 条）
- `docs/dev/STATUS.md` 测试数字 368 → 382

**测试**：红是 collection error（`ImportError: cannot import name 'ACCEPT_EDITS'`），
中间红过一次 `make_before_tool_call() got an unexpected keyword argument 'mode'`
（求值链改完但 gate 还没接），绿 `14 passed in 0.38s`。
全量：`368 passed, 3 deselected` → **`382 passed, 3 deselected`**。

**缺口已补上**（Task 3 devlog 里记的那条遗留）：

```
once 默认（dontAsk）       bash('ls -la') → deny
once + 白名单             bash('ls -la') → allow
--dangerously-skip       bash('ls -la') → allow
```

**`decide()` 整体重构了，这是本 task 最实质的改动**。原先是
`for kind in KINDS: 找规则 → 命中就返回`，模式没有插入的位置。
改成显式七步之后，spec 那张表和代码一一对应，每一步为什么在那个位置都能读出来。

重构顺手修掉一处**原本就别扭的写法**：危险路径检查原先写成
「在循环里 `if kind != "deny"` 时查一次，循环外再查一次」——同一个检查出现两处，
是被循环结构逼出来的。现在它就是第 2 步，只有一处。

**第 3 步与第 7 步的区分是本 task 的核心，也是最容易实现错的地方**：
两者都产出 `kind == "ask"`，但

- 第 3 步是**用户显式写下的** ask 规则（`Decision.rule` 非 None）→ **bypass 也要问**；
- 第 7 步是**兜底**产生的 ask（界外读、bash）→ bypass 放行。

混同的后果是二选一：要么 bypass 等于没有（全都免疫），要么 bypass 变成万能开关
（全都放行，用户写的 `ask=["Bash(git push *)"]` 被无视）。
`test_bypass_is_immune_to_explicit_ask_rules` 在**同一个 RuleSet 下**同时断言两种，
Task 7 还要为它单加一条注入验证。

**`acceptEdits` 的 `&& dirs.contains(...)` 不能省**（照 CC 的
`mode === 'acceptEdits' && isInWorkingDir`）：省了就变成「接受编辑」=「接受任何位置的写」，
包括 `../别人的项目/`。`test_accept_edits_still_respects_boundary` 钉死。

**D#48 显式化的收获比预期大**：`asker is None` 与 `mode == DONT_ASK` 合流成一行
`if asker is None or mode == DONT_ASK`。`test_no_human_is_equivalent_to_dont_ask`
断言两条路径结果相同。feature 07 时把它当特例写在 gate 里，现在它有了名字、
能被配置、能被 CLI 覆盖——**同一段代码，从「特例」变成「模式」只差一个名字**。

**一处 spec 没写、实现时定的**：`--dangerously-skip-permissions` 与
`--permission-mode=<非 bypass>` 同时给会 `parser.error` 报冲突，而不是静默取其一。
两个 flag 表达相反意图时，猜用户想要哪个是最坏的选择。

**遗留**：
- **`/mode` 命令与 shift+tab 未做**（拍板：留 TUI 阶段）。所以 REPL 里换模式
  当前只能重启 pai 加 flag。登记 TODO。
- `/permissions` 不显示当前模式——用户看不到自己在哪个模式下。登记 TODO（小修）。

## 2026-08-11 · Task 7：hook 改 fail-closed（复议 D#50）+ 注入验证

**目标**：运行期权限 hook 的失败语义从 fail-open 改成 fail-closed，
开发期自律门禁保持 fail-open；然后用注入反证证明前六个 task 的测试不是摆设。

**改动**：
- `src/pai/core/hooks.py`：超时 / 起不来 → `deny`；新增 `NOT_RUNNABLE_EXIT_CODES`
- `tests/test_hooks.py`：**改写 2 条** + 新增 2 条
- `tests/test_design_gate.py`：+1 条（钉住 design_gate 的 fail-open 不被误改）
- `docs/dev/STATUS.md` 测试数字 382 → 385

**测试**：绿 `29 passed`（hooks + design_gate）。
全量：`382 passed, 3 deselected` → **`385 passed, 3 deselected`**。

### 拍板说「崩溃 → fail-closed」，但子进程语境下「崩溃」有歧义

实现时撞上的：脚本 `raise` 与脚本主动 `exit 1`，**退出码都是 1，分不出来**。
而 CC 协议明确把「其他退出码」定义为脚本*能够表达*的一种状态（我跑完了、有问题、别拦）。
一并改成 deny 就是改掉协议本身，且会让任何一个写得不严谨的 hook 变成一道随机的墙。

所以 fail-closed 的范围收敛到**「pai 侧没拿到判定」**：

| 情况 | 结果 |
|---|---|
| 超时 | **deny**（改了） |
| 起不来（退出码 126/127 或 OSError） | **deny**（改了） |
| 退出码 0 + 有效 JSON / 退出码 2 | 按脚本说的（没变） |
| 退出码 0 无有效 JSON / **其他退出码** | 无意见（**没变**） |

**与 pi 的差异如实记**：pi 的钩子是进程内 JS 函数，异常能被 `runner.ts` 捕获转拦截，
它**区分得出**「没跑完」；pai 的 hook 是子进程，只有退出码可看。
`test_nonzero_exit_is_still_non_blocking_and_this_differs_from_pi` 把这条差异钉成测试。

**`shell=True` 让「起不来」这条差点是死代码**：原本写的是捕获 `OSError`，
但用 `shell=True` 起子进程时命令不存在**不会抛 OSError**——shell 自己吞掉并返回 127。
测试 `test_hook_cannot_be_started_blocks` 当场红了，才发现这条分支实际触发不到。
补上 126/127（shell 的标准约定）之后才真正生效。
代价如实记在常量注释里：hook 脚本**内部**调了个不存在的命令并透传 127 时会被误判。

### 注入验证（roadmap 硬要求）

**注入 1：`path_in_working_path` 恒 `True`**（边界形同虚设）

```
FAILED tests/test_boundary.py::test_relative_paths_resolve_against_current_cwd_not_the_boundary
FAILED tests/test_boundary.py::test_all_paths_must_be_inside
FAILED tests/test_boundary.py::test_dotdot_traversal_is_normalized
FAILED tests/test_boundary.py::test_symlink_out_of_boundary_is_outside
FAILED tests/test_permissions.py::test_read_outside_cwd_asks
FAILED tests/test_permissions.py::test_once_degrades_boundary_ask_to_deny
FAILED tests/test_permission_modes.py::test_accept_edits_still_respects_boundary
======================== 12 failed, 70 passed in 0.58s =========================
```

**注入 2：写也走 `in_working_dir`**（写不再一律 ask）

```
FAILED tests/test_permissions.py::test_write_always_asks_even_inside
FAILED tests/test_permissions.py::test_once_degrades_boundary_ask_to_deny
FAILED tests/test_permission_modes.py::test_default_mode_is_the_baseline
========================= 3 failed, 59 passed in 0.45s =========================
```

**注入 3：危险路径检查挪到 allow 规则之后**（bypass 免疫失效）

```
FAILED tests/test_permissions.py::test_dangerous_write_is_blocked_even_with_allow_rule
FAILED tests/test_permissions.py::test_dangerous_write_reason_names_the_path
FAILED tests/test_permission_modes.py::test_bypass_is_immune_to_dangerous_paths
========================= 3 failed, 59 passed in 0.46s =========================
```

**注入 4：第一次注错了，这条值得单记。**

原本想验「第 3 步（显式 ask）与第 7 步（兜底 ask）的区分」，
第一次把 `bypassPermissions` 从第 4 步挪到第 7 步之前——**结果 14 条全绿**。

一瞬间以为这个区分没被测住。复查后发现是**注入没打中**：显式 ask 的检查仍在
bypass 之前，所以它照样先命中返回，区分根本没被破坏。
改成把 bypass 提到**显式 ask 之前**（注入 4b），才真正取消区分：

```
FAILED tests/test_permission_modes.py::test_bypass_is_immune_to_explicit_ask_rules
========================= 1 failed, 13 passed in 0.41s =========================
```

**教训**：注入验证本身也会写错，而且**注错的表现与「测试无效」一模一样**（都是全绿）。
区分方法只有一个——注入之后先问「我改的这行，在目标场景里真的会被执行到吗」。
feature 07 的三条注入没撞上这个问题是运气好。这条进复盘。

四次注入还原后复跑：**`385 passed, 3 deselected`**，`grep` 确认无残留。

**遗留**：无（本 task 的遗留已并入下面的交付清单）。
