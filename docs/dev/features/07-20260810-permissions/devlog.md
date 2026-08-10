# 07-20260810-permissions · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-10 · Task 1：规则解析与三态求值

**目标**：`core/permissions.py` 的地基——`Rule` / `RuleSet` / `Decision` 三个 dataclass
加一个 `decide()`，把「求值顺序 deny → ask → allow、桶内取第一个命中、特异性不参与排序」
这条不变量用测试钉死。

**改动**：
- 新增 `src/pai/core/permissions.py`（规则解析 + 三态求值）
- 新增 `tests/test_permissions.py`（7 条）
- `docs/dev/features/07-.../README.md` 状态「讨论中」→「已拍板」（用户 2026-08-10 拍板按 plan 走）
- `docs/dev/STATUS.md` 测试数字 276 → 283

**测试**：红是 collection error（`ImportError: cannot import name 'permissions' from 'pai.core'`），
不是断言失败——新模块还不存在，7 条一条都没跑起来。补上实现后：

```
tests/test_permissions.py .......                                        [100%]
============================== 7 passed in 0.36s ===============================
```

全量：`276 passed, 3 deselected` → **`283 passed, 3 deselected`**（+7，与 plan 的验收数字一致）。

中间还红了一次、且是**该红的**：`test_status_reports_the_current_test_count` 拿
`session.testscollected` 跟 STATUS.md 里的数字对账，Task 1 加了 7 条就立刻炸。
plan 原本写的是「全部完成后更新 STATUS」——对不上，这个数字得**每个 task 都同步**，
否则中间六个 task 全程带着一条红。已按每 task 同步处理。

**几处实现取舍**（够格的到交付时再升格进 decisions）：
- 未锚定的工具名 glob（`*_file`）**直接拒绝解析**而不是官方的「跳过 + 告警」。
  告警会被淹没，而一条「以为生效其实没生效」的 deny 比压根没写更危险。
  裸 `*`（全部）与 `前缀*` 仍然合法。
- specifier 的正则贪婪匹配到最后一个 `)`，这样 `Bash(echo (x))` 不会被截断。
- `_specifier_matches()` 单独抽成函数：Task 2 要把它换成「下放给工具」，
  换的时候只动这一处，Task 1 的 7 条测试是那次改动的回归网。

**遗留**：
- 匹配目前是「拿第一个参数值做 fnmatch」的占位实现，**复合命令与路径锚点都还没有**
  ——`allow=["Bash(ls *)"]` 此刻会放行 `ls && rm -rf /`。Task 3 是分水岭，
  在它做完之前权限层不具备真实防护力，不要中途接线进 loop。

## 2026-08-10 · Task 2：匹配语义下放给工具

**目标**：把「这次调用算不算命中这条规则」从权限层挪进工具（拍板问 2）。
权限层只剩三态与求值顺序，**不许出现任何工具名分支**——这条用白盒测试证明，
不是靠口头约定。

**改动**：
- `src/pai/core/tools/__init__.py`：`Tool` 加 `matcher` 字段与 `matches()` 方法；
  新增 `default_matcher()`（第一个参数值做通配符）、`matcher_for()` 装饰器、`all_tools()`
- `src/pai/core/permissions.py`：`_specifier_matches()` 改为向工具要匹配结果；
  `decide()` 加可注入的 `tools` 参数
- `tests/test_permissions.py`：+4 条
- `docs/dev/STATUS.md` 测试数字 283 → 287

**测试**：红是 `TypeError: __init__() got an unexpected keyword argument 'matcher'`
（`Tool` 还没有这个字段），`4 failed, 7 passed`。补上实现后 `11 passed in 0.38s`。

全量：`283 passed, 3 deselected` → **`287 passed, 3 deselected`**（+4，与 plan 一致）。

**三处实现取舍**：
- **`decide()` 的 `tools` 参数可注入**，不直接读全局 REGISTRY。一是合「依赖注入优先」，
  二是白盒测试要给假工具挂 spy matcher 才能证明「权限层没按工具名分支」，
  三是不注入时测试之间会用 REGISTRY 互相污染。
- 新增 `all_tools()` 而不复用 `get_tools()`：后者会滤掉 `INTERACTIVE_ONLY`，
  但「不摆给模型看」不等于「不会被调用」，权限判定必须认得每一个工具。
  它显式 import 各子模块——否则判定结果取决于谁先 import 了谁，会变成顺序相关的偶发行为。
- `matcher_for` 挂到没注册的工具上**当场抛 ValueError**。默默不生效意味着一条
  以为写好的匹配规则静默失效，和 Task 1 拒绝未锚定 glob 是同一个理由。

**`require_all` 的不对称在此通电**：allow 判定传 `True`（每个子命令都要匹配），
deny/ask 传 `False`（任一命中即算）。`test_require_all_flag_is_passed_through` 断言
三个桶收到的正是 `[("a", False), ("b", False), ("c", True)]`。
这个不对称就是权限系统的牙齿，但**现在还咬不动**——默认 matcher 眼里没有「多个子命令」
这回事，`require_all` 收到了也没用。要等 Task 3 的 bash 匹配器才真正生效。

**遗留**：同 Task 1——`allow=["Bash(ls *)"]` 此刻仍会放行 `ls && rm -rf /`。
Task 3 是分水岭。

## 2026-08-10 · Task 3：bash 匹配器（分水岭）

**目标**：让 `require_all` 的不对称真正咬得动——拆复合命令、剥进程包装器、
前缀带词边界。这一步之前权限层是纸糊的。

**改动**：
- `src/pai/core/tools/shell.py`：新增 `split_commands()` / `strip_wrappers()` /
  `match_one()` 三个纯函数 + `@matcher_for(bash)` 的 `bash_matcher()`
- `tests/test_permissions.py`：+7 条
- `docs/dev/STATUS.md` 测试数字 287 → 294

**测试**：红 `5 failed, 13 passed`，绿 `18 passed in 0.37s`。
全量：`287 passed, 3 deselected` → **`294 passed, 3 deselected`**（+7，与 plan 一致）。

**红的时候有两条是绿的，如实记**：`test_env_runners_are_not_stripped_and_this_is_a_known_hole`
与 `test_word_boundary_before_star` 在实现之前就过了——因为默认 matcher 的朴素 fnmatch
恰好给出同样的答案。也就是说这两条在红阶段**不具备鉴别力**，它们钉的是「别在
`strip_wrappers` 里顺手把环境运行器也剥了」「别把词边界改成子串」这类**未来的**回归，
不是本次实现的正确性。写下来免得下次看红绿数字以为 7 条都验过了。

**一处 plan 没写、实现时必须定的语义**：尾部 ` *` 到底算不算匹配「后面什么都没有」。
plan 的 Task 3 第 4 条要求 `Bash(npm test *)` 匹配 `timeout 30 npm test`，
而剥掉包装器之后命令就是 `npm test`——尾部空无一物。所以 ` *` / `:*` 必须实现成
**前缀 + 词边界**（`ls *` 匹配 `ls` 与 `ls -la`，不匹配 `lsof`），
而不是 fnmatch 那种「星号至少要有东西对上」。不带空格的 `ls*` 保留朴素通配语义，
两种写法的区别是故意的。

**边界，不吹**：匹配是前缀式的，官方原话是「基于前缀的匹配防不住刻意绕过」。
挡手滑可以，挡对抗不行。`devbox run rm -rf .` 会被 `Bash(devbox run *)` 放行，
这条已写成测试摆在明面上。

**遗留**：
- 环境运行器的洞（`devbox run` / `npx` / `docker exec`）——已知不修，进 TODO。
- 拆分是正则不是真 shell 解析：引号里的 `&&`（`echo "a && b"`）会被误拆成两条。
  误拆的方向是**更保守**（allow 更难通过），所以不是安全洞，但会误伤正常命令。
  登记 TODO。

## 2026-08-10 · Task 4：fs 匹配器（路径锚点）

**目标**：四种路径前缀四种含义，重点是官方自标的最大的坑——单斜杠锚到
**写下这条规则的设置文件**，不是文件系统根也不是 cwd。

**改动**：
- `src/pai/core/tools/__init__.py`：新增 `MatchContext`；matcher 签名加第 4 个参数；
  `Tool.matches` 相应改造（`ctx` 给了默认值，直接调用 `matches()` 的老写法不受影响）
- `src/pai/core/tools/fs.py`：新增 `_glob_to_regex()` / `expand_pattern()` /
  `target_path()` / `path_matcher()`，挂到 read/write/edit 三件套
- `src/pai/core/permissions.py`：`Rule` 加 `anchor` 字段；`decide()` 加 `cwd` / `home`
  注入点；逐条规则构造 `MatchContext`
- `src/pai/core/tools/shell.py`：`bash_matcher` 补第 4 个参数（用不上，签名统一）
- `tests/test_permissions.py`：+6 条，另**改了 Task 2 的两个 spy 签名**
- `docs/dev/STATUS.md` 测试数字 294 → 300

**测试**：第一次红是 `TypeError: from_lists() got an unexpected keyword argument 'anchor'`，
`6 failed, 18 passed`。补实现后第二次红是签名不匹配引发的连锁
（`15 failed, 9 passed`，`TypeError: bash_matcher() takes 3 positional arguments but 4 were given`）
——这次红**是我自己改签名造成的**，不是需求的一部分，如实记下。改完 bash_matcher 与
两个 spy 后 `24 passed in 0.39s`。

全量：`294 passed, 3 deselected` → **`300 passed, 3 deselected`**（+6，与 plan 一致）。

### 一处对已拍板 spec 的偏离（须复议）

spec 第 2 节把 matcher 签名钉成 `(specifier, args, require_all) -> bool`，
plan 的 Task 4 又要求「`Rule` 带 `anchor` 目录（由 source 决定）」。**这两条凑不到一起**：
`/secrets/**` 的含义取决于哪个设置文件写的它，这个信息既不在 specifier 里、
也不在工具参数里，三参签名根本没有它的入口。

实现时取的是**加第 4 个参数 `ctx: MatchContext`（anchor / cwd / home）**。
考虑过但否掉的两条：
- **在权限层把 anchor 拼进 specifier 再传给 matcher**：要求权限层判断
  「这个 specifier 是不是路径」，而 bash 的 `git push *` 显然不能拼锚点——
  等于把工具语义搬回权限层，正好违反拍板问 2。
- **给工具再加一个 `normalize_specifier` 钩子**：多一层机制，解决的还是同一件事。

代价说清楚：签名从 3 参变 4 参，Task 2 已绿的两个 spy 测试被改了。
`Tool.matches()` 的 `ctx` 留了默认值，所以只有**自定义 matcher** 受影响，共 5 处（bash + fs 三件套 + 测试 spy）。
**这条要进 decisions 并请用户复议**——改的是拍板过的接口形状，不该由我一个人定。

**两处 plan 没写但必须定的**：
- **单星不跨 `/`**。用 fnmatch 的话 `*` 会吃掉路径分隔符，`allow=["read_file(src/*)"]`
  就会连 `src/secret/deep.key` 一起放行——allow 方向的过度放宽是安全问题，
  所以自己把 glob 编译成正则（`*` → `[^/]*`，`**/` → `(?:[^/]*/)*`）。
  `test_relative_pattern_anchors_to_cwd` 里那条 `src/deep/a.py` 断言就是钉这个的。
- **`target_path()` 刻意不 realpath**。做一半的符号链接检查比不做更误导。

**遗留**：
- **符号链接双路径检查未做**——一条软链就能绕开 deny 规则，
  `test_symlink_double_check_is_not_implemented` 钉的是当前（有洞的）行为，
  将来做了它应该变红并被改写。进 TODO。
- matcher 签名 3 参 → 4 参偏离已拍板 spec，进 decisions + TODO 请用户复议。

## 2026-08-10 · Task 5：配置加载与裸名 deny 摘工具

**目标**：两层设置文件读进一个 RuleSet，跨层 deny 翻不过来；裸名 deny 的工具
直接从发给模型的 schema 里消失。

**改动**：
- `src/pai/core/permissions.py`：新增 `_read_settings()` / `load_rules()` / `visible_tools()`
- `tests/test_permissions.py`：+5 条
- `docs/dev/STATUS.md` 测试数字 300 → 305

**测试**：红 `5 failed, 24 passed`（`AttributeError: module 'pai.core.permissions'
has no attribute 'visible_tools'`），绿 `29 passed in 0.37s`。
全量：`300 passed, 3 deselected` → **`305 passed, 3 deselected`**（+5，与 plan 一致）。

**「跨层 deny 优先」没写一行专门的逻辑**：合并是往三个桶里**追加**，
而 deny 桶本来就最先求值，所以「任一层 deny 都翻不过来」是 Task 1 求值顺序的自然结果。
测试仍然双向各钉一次——将来若有人把合并改成「后读的层覆盖前一层」，
这条性质会静默消失，而它不该靠「我记得当初是追加」来保证。

**两层锚点不一样，不是笔误**：用户级锚在设置文件所在的 `~/.pai`，
项目级锚在**项目根**（不是 `<项目根>/.pai`）。这是照抄官方语义，
`test_loads_user_then_project_settings` 把两个锚点都断言了，免得日后被「统一一下」抹平。

**plan 留的选择题（`get_tools` 侧还是 loop 侧摘除）选了第三个**：
新写 `permissions.visible_tools(tools, rules)`，在**装配层**调用。
- 不放 `get_tools()`：那是「注册表取子集」的纯函数，塞进权限概念就得让它认得 RuleSet，
  职责会糊。
- 不放 loop：loop 已经有 8 个注入点，再加一个「工具集过滤」会让它更胖，
  而且 loop 拿到的 tools 本来就该是**已经过滤好的**——过滤是装配期的事，不是运行期的。

**遗留**：
- `visible_tools` 目前要装配层显式调用，**忘了调就等于裸名 deny 不生效**。
  Task 7 接线时两个模式都要接上；接完之前这是个真实的失效路径。登记 TODO。

## 2026-08-10 · Task 6：外部命令 hook

**目标**：`core/hooks.py` —— 三种退出码、多 hook 冲突取最严、两条边界，
以及「hook 自身崩溃/超时绝不阻断工作」这条铁律。

**改动**：
- 新增 `src/pai/core/hooks.py`（`HookSpec` / `run_pre_tool_use` / `decide_with_hooks`）
- 新增 `tests/test_hooks.py`（11 条）
- `docs/dev/STATUS.md` 测试数字 305 → 316

**测试**：红是 collection error（`ImportError: cannot import name 'hooks' from 'pai.core'`），
绿 `11 passed in 1.28s`。
全量：`305 passed, 3 deselected` → **`316 passed, 3 deselected`**。

**比 plan 多写了 2 条**（plan 说 +9 → 314，实际 +11 → 316）：
- `test_hook_receives_the_event_on_stdin`：hook 靠 stdin 拿工具名与入参。
  不测这条的话，「pai 能跑自己的 design_gate」这个拍板问 3 的卖点是空的——
  design_gate 正是靠读 stdin 的 `tool_name` / `tool_input` 才判得出该不该拦。
- `test_no_hooks_means_no_opinion`：没配 hook 时行为与不接线逐字相同。

**一处设计上想清楚了才写的**：`run_pre_tool_use` 返回 `None` 表示「**没意见**」，
不是「放行」。这两者混同的话，一个崩掉的 hook 就等于一次静默放行——
恰好是最不该放行的时候放行。所以 `decide_with_hooks` 里 `None` 会被
`_strictest` 直接滤掉，让规则判定说了算。

**三条性质由同一个 `_strictest` 兑现**：多 hook 冲突取最严、hook 的 allow 压不过
规则的 deny（边界一）、规则的 allow 压不过 hook 的阻断（边界二）。
它们本来就是同一条「取 deny > ask > allow 里最严的那个」，
写成三段 if 反而会让三者可能各自漂移。

**铁律的安全代价，如实记**：hook 超时/崩溃不阻断，意味着**杀掉 hook 进程就能绕过它**。
反过来做（挂了就拦）的代价更大——一个写错的钩子会让 agent 整个罢工，
而人在那种情况下通常直接把钩子全关掉，等于一道门禁都不剩。

**遗留**：
- hook 只做了 `PreToolUse` 一种，且没有 `defer` 决策与 `updatedInput`（spec 明确不做）。
- hook 配置还没接进 `load_rules`——`settings.json` 里的 `hooks.PreToolUse` 目前
  没人读，要 Task 7 装配时接上。登记 TODO。

## 2026-08-10 · Task 7：接进 loop / ask 降级 / /permissions / 注入验证

**目标**：把前六个 task 攒的能力真正接到工具调用路径上，并用注入反证证明这些测试
不是摆设。

**改动**：
- `src/pai/core/events.py`：新增 `PermissionDecided` 事件 + 渲染（allow 不打印，
  逐条打出来只会淹没真正要看的）
- `src/pai/core/loop.py`：`run_agent` 加 keyword-only `before_tool_call`；
  判定点在 `ToolStart` **之前**；非 allow 则不执行、回填 `DENIED_PREFIX + 理由`
- 新增 `src/pai/core/gate.py`：`make_before_tool_call()`（规则 + hook + ask 解析）
- `src/pai/modes/once.py`、`src/pai/modes/interactive.py`：两处装配
- `src/pai/modes/interactive.py`：`/permissions` 命令 + HELP 一行
- `tests/test_loop.py` +5、`tests/test_modes.py` +3、`tests/test_interactive.py` +2
- `docs/dev/STATUS.md` 测试数字 316 → 326

**测试**：红 `9 failed, 95 passed`（`test_no_before_tool_call_preserves_old_behavior`
在红阶段就是绿的——它测的正是「还没接线时的行为」，本该如此）。
绿 `144 passed`（五个相关文件）。
全量：`316 passed, 3 deselected` → **`326 passed, 3 deselected`**（+10）。

### 注入验证（roadmap 硬要求）

plan 只要求注入一条，实际做了三条——只翻求值顺序的话，Task 3 的分水岭没被验到。

**注入 1：求值顺序 `KINDS` 改成 `("allow", "ask", "deny")`**

```
FAILED tests/test_permissions.py::test_deny_beats_more_specific_allow
FAILED tests/test_permissions.py::test_ask_beats_allow
FAILED tests/test_permissions.py::test_require_all_flag_is_passed_through
FAILED tests/test_permissions.py::test_deny_in_either_layer_beats_allow_in_the_other
========================= 4 failed, 25 passed in 0.41s =========================
```

**注入 2：`require_all = kind == "allow"` 改成恒 `False`**（复合命令不再逐条要求）

```
FAILED tests/test_permissions.py::test_require_all_flag_is_passed_through
FAILED tests/test_permissions.py::test_compound_command_requires_every_subcommand_to_match
FAILED tests/test_permissions.py::test_all_separators_split
========================= 3 failed, 26 passed in 0.42s =========================
```

**注入 3：`split_commands()` 不拆，整条命令原样返回**

```
FAILED tests/test_permissions.py::test_compound_command_requires_every_subcommand_to_match
FAILED tests/test_permissions.py::test_any_subcommand_matching_deny_blocks
FAILED tests/test_permissions.py::test_all_separators_split
========================= 3 failed, 26 passed in 0.39s =========================
```

三次还原后复跑：**`326 passed, 3 deselected`**，`grep` 确认无残留。

**注入验证暴露的一件事**：注入 1 只打红了 4 条，而 Task 3 那 7 条里
**一条都没红**——求值顺序与复合命令拆分是两条正交的防线，
只验前者会给人「权限系统被测住了」的错觉。这正是多做两条注入的理由。

**一处 plan 没写的设计决定**：`loop` **不认识 `ask`**。
`before_tool_call` 返回的 Decision 到了 loop 只被问一句「是不是 allow」，
ask 在装配层（`gate.py`）就已经解析成 allow 或 deny 了。
不这么做的话，「有没有真人可问」这个**模式差异**会渗进 loop，
而 loop 是两个模式共用的。

**为什么新开 `core/gate.py` 而不是塞进 permissions 或 hooks**：
`permissions` 不能 import `hooks`（后者反过来 import 它，成环）；
而「ask 遇到没真人时怎么办」既不属于规则也不属于子进程协议，是**装配期**的决定。
三件事各归各位之后 loop 才能只认 allow。

**遗留**：见下一条——写这段遗留时发现的洞当场补掉了，没留到 TODO。


## 2026-08-10 · 补：hook 配置从 settings.json 读（spec §6 漏接的一根线）

**目标**：写 Task 7 的「遗留」时发现 `settings.json` 的 `hooks.PreToolUse`
**根本没人读**——`HookSpec` 与 `run_pre_tool_use` 都能用，但两个模式装配时
`hooks=()` 是硬编码的空。这不是「遗留」，是 **spec §6 明确写了而没做的部分**：

> 配置：`settings.json` 的 `hooks.PreToolUse: [{matcher, command, timeout}]`

不补的话，「pai 能跑自己的 design_gate」这个拍板问 3 的**唯一卖点**是空话——
库函数齐全但没有任何路径能把用户配的 hook 送进去。所以按 TDD 补齐而不是记 TODO。

**改动**：
- `src/pai/core/hooks.py`：新增 `load_hooks()`（复用 permissions 的 `_read_settings`
  读盘与容错，坏条目跳过并告警）
- `src/pai/modes/once.py`、`src/pai/modes/interactive.py`：两处装配接上
- `src/pai/modes/interactive.py`：`/permissions` 顺带列出 hook
- `tests/test_hooks.py`：+3 条（含一条端到端：settings.json 配一条 hook，
  真的拦下一次 `run_once` 里的工具调用）

**测试**：红 `3 failed, 11 passed`；补 `load_hooks` 后剩 1 条红
（`assert '门禁说不行' in 'hi\n'`——库函数有了但装配没接，**红得正好指向真因**）；
接上两处装配后 `14 passed in 1.30s`。
全量：`326 passed, 3 deselected` → **`329 passed, 3 deselected`**。

**自举验证（拍板问 3 的卖点，真跑）**：在 `pai_playground/gate-selfhost/` 里造一个
状态为「讨论中」的假档案，让 pai 的 hook 层跑 pai 自己的 `guards/design_gate.py`：

```
决策: deny
理由: 方案门禁：99-demo 当前状态是「讨论中」，未到「已拍板」。
```

同一个脚本喂本仓库（档案已拍板）则返回 `None`（无意见 → 放行）。
`design_gate.py` 用的是退出码 0 + `hookSpecificOutput` 嵌套 JSON 那条路径，
这也顺带验证了 `_parse_stdout` 对嵌套形式的支持不是纸上谈兵。

**遗留**：`load_hooks` 只认 `PreToolUse` 一种事件（spec 明确只做这一种）。
