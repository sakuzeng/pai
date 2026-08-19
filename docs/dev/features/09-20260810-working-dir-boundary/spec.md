# 09-20260810-working-dir-boundary · spec

2026-08-10 三问拍板定稿（问答完整存档见 [README](README.md)「候选方案与确认」）。
前置精读：[cc-pi-permission-boundaries.md](../../../../knowledge/permissions/cc-pi-permission-boundaries.md)。

## 背景与问题

feature 07 交付了权限引擎，但策略是空的：`decide()` 的兜底是常量
`default_decision="allow"`，于是无配置时 `read_file(~/.ssh/id_rsa)`、
`write_file(../别人的项目/x.py)` 全部放行。而 STATUS 写着「permissions 可用」——
这正是 pi `security.md` 警告的「进程内权限被误解为安全边界」。

CC 的对应实现里根本没有「默认决策常量」这个东西：兜底是
`in_working_dir ? allow : ask`（`filesystem.ts:1030-1193`，第 6 步与第 12 步）。
本需求把这条补上。

## 目标（做什么）

### 1. 工具自我声明「碰哪个路径、是读是写」

延续拍板问 2 的「语义下放给工具」，不在权限层按工具名分支：

- `Tool` 增两个字段：
  - `get_path: Optional[Callable[[dict], str]]` —— 从工具入参取出它要碰的路径；
  - `access: Optional[str]` —— `"read"` 或 `"write"`。
- 两者都有才参与目录边界判定。`read_file` 声明 `("read", 取 path)`；
  `write_file` / `edit_file` 声明 `("write", 取 path)`；
  `bash` 两者都不声明（拍板问 2 = A）。
- 对照 CC：CC 对没有 `getPath` 的工具返回 ask（后面有 `bashClassifier` 兜底）。
  pai 选择「不参与边界判定」——没有分类器却返回 ask 等于禁用 bash。
  这是与 CC 的明确差异，进 decisions。

### 2. `default_decision` 增加第四种取值 `workingdir`，并成为新默认

`KINDS` 仍是严格三态（`deny`/`ask`/`allow`），求值顺序不动（D#46 不受影响）。
变的只是兜底：

| `default_decision` | 兜底行为 |
|---|---|
| `workingdir`（新默认） | 参与边界的工具：读 → `in_working_dir ? allow : ask`；写 → `ask`。不参与边界的工具（bash）→ `ask`（2026-08-11 改，见下） |
| `allow` | 老行为，全放行（向后兼容：显式配了的人不受影响） |
| `ask` / `deny` | 白名单模式，不变 |

写为什么一律 ask 而不是「界内 allow」：照 CC——`checkWritePermissionForTool`
的兜底是第 5 步 `Default to asking`，没有读路径那个第 6 步的目录放行。
即 CC 默认模式下写文件一律确认，与用户描述一致。

与 D#48 的交互（须在 spec 里说清，这是本需求最大的行为变化）：
`ask` 在 once 模式无真人时降级为 `deny`。所以本需求落地后：

- REPL：越界读、任何写 → 弹确认；
- once：越界读、任何写 → 直接 deny + 理由回填，即 once 被限制在启动 cwd 内只读。

这是拍板时明确接受的代价。想恢复老行为的人配 `"defaultDecision": "allow"`。

2026-08-11 修订：bash 兜底从 `allow` 改为 `ask`（用户改选原问 2 的候选 C）。
原先写 allow 的推导是「不做目录边界 ⇒ 兜底 allow」，但这是两件事：
完全可以「不解析 bash 命令里的路径，但兜底仍然 ask」。
改后与 CC 的 Bash 默认行为一致（CC 默认模式下 Bash 每个命令首次都要确认）。
代价：`once` 模式撞到 ask 会按 D#48 降级 deny ⇒ bash 基本不可用，
必须配 `allow` 白名单或换模式——这正是下面第 7 节「模式」成为必需品而非可选项的原因。

### 3. 工作目录集合与 `additionalDirectories`

- 起点是启动时的 cwd，不是当前 cwd——照 CC 的 `getOriginalCwd()`，
  防止中途 `cd` 把边界带跑。
- `settings.json` 的 `permissions.additionalDirectories: [...]` 扩展该集合。
- 判定：待查路径全部落在允许目录内才算界内（CC 用 `.every`）。

### 4. 符号链接双路径（关掉 feature 07 TODO#3）

照 CC `getPathsForPermissionCheck`：一次算出「原始路径 + realpath 解析后路径」两条，
全链共用（CC 注释写明不这么做会有 30 次冗余 syscall）。

- deny / ask 规则：两条路径分别查，任一命中即拦；
- 边界判定：两条都必须在界内（`.every`）；
- 工作目录本身也要用同一个函数解析——CC 注释标了这个坑：
  不对称解析会让 macOS 的 `/System/Volumes/Data/...` 匹配不上未解析的工作目录，造成误拒。

`test_symlink_double_check_is_not_implemented`（07 留下的、钉当前有洞行为的测试）
应当在本需求中变红并被改写——这是它当初就写明的用途。

### 5. 危险路径清单（bypass 免疫）

照 CC 的 `DANGEROUS_FILES` / `DANGEROUS_DIRECTORIES`：持久化位点写不进去。
最小集合：`~/.bashrc`、`~/.zshrc`、`~/.profile`、`.git/hooks/**`、`~/.ssh/**`、
`~/.pai/settings.json`（防 agent 自己改自己的权限规则——这条 CC 有对应的
`isClaudeSettingsPath`）。

「bypass 免疫」的含义：即使 `default_decision="allow"`、
即使有 allow 规则命中，写这些路径仍然要 ask/deny。
实现上它必须排在 allow 规则之前——与 D#46 的求值顺序不冲突，
它是 deny 桶之后、ask 桶之前的一个内置检查。

### 6. hook 失败语义改 fail-closed（复议 D#50，拍板问 3）

- 运行期权限 hook（`run_pre_tool_use`）：崩溃 / 超时 / 起不来 → 返回 deny，
  不再返回 `None`。跟 pi（`emitToolCall` 不捕获异常，上层转拦截）
  与 CC（分类器解析失败即 block）一致。
- 开发期自律门禁 `guards/design_gate.py`：保持 fail-open（结尾的
  `except: sys.exit(0)` 不动）。它挡的是「AI 改自己源码时没走流程」，
  失败的代价是流程没走到；而运行期 hook 失败的代价是安全事故。
- 退出码非 0 非 2 的「非阻断错误」语义不变（那是脚本明确表达的「我没意见」，
  不是失败）。改的只有异常路径。

### 7. 权限模式（四态，2026-08-11 拍板）

照 CC 的 UI 名与语义，做四个（CC 对外共 5 个，`plan` 不做；`auto` 是 ant-only
且需分类器，做不了）：

| pai 模式 | CC 界面名 | 语义 |
|---|---|---|
| `default` | Default | 第 2 节那套兜底 |
| `acceptEdits` | Accept edits | 工作目录内的写自动放行；仍受边界与危险路径约束 |
| `dontAsk` | Don't Ask | 一切 `ask` 直接变 `deny`，不问 |
| `bypassPermissions` | Bypass Permissions | 全放行，但三条免疫（见下） |

模式不是全局开关，是插在求值链特定位置的放行条件（照 CC，笔记六点五节）。
完整求值链：

| 步 | 检查 | bypass 免疫？ |
|---|---|---|
| 1 | deny 规则 | ✅ 免疫 |
| 2 | 危险路径写检查（第 5 节） | ✅ 免疫 |
| 3 | 用户显式配的 ask 规则 | ✅ 免疫 |
| 4 | `bypassPermissions` 模式 → allow | — |
| 5 | `acceptEdits` 且是写 且在界内 → allow | — |
| 6 | allow 规则 → allow | — |
| 7 | 兜底（第 2 节：边界判定 / bash → ask） | ❌ 不免疫 |

第 3 步与第 7 步的区别是本节最容易实现错的地方：
用户显式写下的 `ask` 规则 bypass 免疫（CC 注释：「must be respected even in
bypass mode, just as deny rules are respected at step 1d」），
而兜底产生的 ask（界外读、bash）不免疫——否则 bypass 模式等于没有。
两者都是 `kind == "ask"`，区别只在 `Decision.rule` 是不是 None。

`dontAsk` 不在这条链上：它是对最终结果的后处理（`ask` → `deny`），
位置就是 `gate.py` 里 D#48 那个降级分支——即 pai 已经实现了它，只是没起名字。
所以：`asker is None`（once 无真人）等价于 `mode == "dontAsk"`，两者走同一段代码。

各模式默认值：`once` → `dontAsk`；REPL → `default`。

### 8. 模式的设置入口（自主判断，非拍板项，如实标注）

用户拍板「切换 UI 留到 TUI 阶段（TODO）」。但完全没有设置入口的话，
`acceptEdits`/`bypassPermissions` 是死代码，且 bash 兜底改 ask 之后 once 模式全被拒。
所以本轮做配置入口（不是交互切换）：

- `settings.json` 的 `permissions.defaultMode`（两层，项目层覆盖用户层）；
- CLI：`pai --permission-mode=<mode>`，以及 `--dangerously-skip-permissions`
  作为 `bypassPermissions` 的别名（照 CC 同名 flag，名字里带 dangerously 是故意的）。

留给 TUI 阶段的（登记 TODO）：REPL 的 `/mode` 命令、shift+tab 循环切换
（纯 REPL 的阻塞 `input` 拿不到组合键，与 steering 无输入源是同一个限制）。

## 非目标（明确不做）

- `bash` 的目录边界（拍板问 2 = A）。`bash("cat ../secret")` 会绕过本需求的全部成果。
  如实写进 STATUS 已知缺陷与 TODO，不做朴素路径提取——那是「看起来防住了」的错觉。
- 分类器模型（CC 的 `bashClassifier` / `yoloClassifier`）、沙箱、SSRF 守卫、
  路径 TOCTOU 拒绝、`denialTracking`（3 连拒回落人工）。
- `plan` 模式（拍板：留到 TUI 阶段连交互一起做——它的价值主要在
  「产出计划 → 用户批准 → 自动转 acceptEdits」那套流程，只做「写都 deny」意义不大）。
- `auto` 模式：CC 源码写死 ant-only（`isExternalPermissionMode` 里
  `mode !== 'auto' && mode !== 'bubble'`），外部用户拿不到，且需要分类器 + 熔断器。
- 交互式模式切换（`/mode` 命令、shift+tab）：留 TUI 阶段。
- `decisionReason` 结构化审计（pai 的 `Decision.reason` 仍是人话字符串）——
  值得做但不在本轮，登记 TODO。
- 运行期 `PermissionUpdate`（CC 的「本次会话记住这个选择」）。

## 验收标准

- 用户那句话可复现：在 `<tmp>/proj` 启动，`read_file("../outside.txt")`
  在 REPL 下弹确认、在 once 下 deny；`read_file("./src/x.py")` 直接放行。
- 写一律 ask：`write_file("./就在界内.txt")` 在默认姿态下也要确认。
- bash 兜底 ask：`bash("ls")` 在 REPL 弹确认、在 once 下 deny（`dontAsk`）。
- bash 不参与目录边界，且这个洞有测试钉住：配了 `allow=["Bash(cat *)"]` 之后，
  `cat ./界内` 与 `cat ../../etc/passwd` 待遇相同（都放行）——
  因为 bash 不声明 `get_path`，边界判定碰不到它。
  这才是「不做 bash 边界」的准确代价：它不是默认放行，而是一旦为了可用性配了
  allow 白名单，白名单内的命令就能越界。与 07 的 `test_env_runners_...` 同款做法写成测试。
- 模式四态各有测试：`acceptEdits` 免写确认但仍受边界与危险路径；
  `bypassPermissions` 放行兜底 ask，但 deny 规则 / 显式 ask 规则 / 危险路径三条免疫；
  `dontAsk` 把 ask 变 deny。
- 显式 ask 规则与兜底 ask 在 bypass 下待遇不同（最容易实现错的一条）：
  `ask=["Bash(git push *)"]` 在 bypass 下仍然问；界外读的兜底 ask 在 bypass 下放行。
- 向后兼容：显式 `"defaultDecision": "allow"` 时行为与 feature 07 逐字相同。
- 符号链接：07 那条 `test_symlink_double_check_is_not_implemented` 变红并被改写为
  「软链绕不过 deny」。
- 危险路径 bypass 免疫：`default_decision="allow"` + `allow=["write_file(*)"]`
  时写 `~/.bashrc` 仍被拦。
- hook fail-closed：`test_hook_timeout_does_not_block_work` 与
  `test_hook_crash_does_not_block_work` 变红并被改写为「超时/崩溃 → deny」；
  `guards/design_gate.py` 的 fail-open 有测试钉住不被误改。
- 注入验证（roadmap 硬要求，07 的三条注入是先例）：至少两条——
  把边界判定改成恒 `True`、把「写一律 ask」改成「写也走 in_working_dir」，
  各自断言确实变红。
- `./test.sh` 全绿全离线；每 task 红→绿真实数字进本目录 devlog；
  交付前先写 `复盘.md`；遗留逐条进 TODO。
