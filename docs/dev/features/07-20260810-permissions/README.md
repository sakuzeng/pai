# 07-20260810-permissions —— 权限层（三态规则 + 工具级匹配 + hooks）

状态：讨论中（等用户拍板；拍板后改「已拍板」，`.active` 已指向本目录）
分支：`feat/memory`（前置精读 + spec/plan）；实现分支待拍板后开

## 需求

roadmap 阶段 4：`before_tool_call` 挂点上的权限层。
**allow / ask / deny 三态**，求值顺序 deny → ask → allow（第一个匹配决定，特异性不改变顺序）；
**匹配语义下放给工具**（Bash 懂 shell 分隔符、fs 工具懂路径锚点）；
按 source 分桶（user / project）；外部命令 hook 走三种退出码。
anna 门禁思想回流：ask 只用在必须真人拍板的节点、**门禁必须带测试**（注入已知错误断言真会拦）。

## 候选方案与确认

### 2026-08-10 brainstorm 四问拍板（用户；问答完整存档，规矩 6）

**问 1**：ask 三态撞上「无真人可问」时怎么办？once 模式跑完即退，没人坐在那里拍板。
- 候选 A·**降级为 deny + 原因回填给模型**：拒绝，并把「这条需要人工确认，当前模式无人可问」
  当作工具结果回填——模型可以换个做法继续（正好接上现有「工具错误不 throw」的语义）。
  同一条规则在 REPL 里会真的弹 AskUserQuestion 问人：**同一套规则两种模式不同行为**。
- 候选 B·降级为 allow：代价是 **ask 规则在自动化场景下等于不存在**，而自动化正是最危险的场景。
- 候选 C·中止整个任务：一条小规则就能废掉整个长任务，已完成的工作白做。

**选择：A**。

**问 2**：「这条规则匹不匹配这次调用」由谁回答？
- 候选 A·**下放给工具**：`Tool` 增一个 `matches(specifier, args)` 能力，默认实现是通配符匹配；
  bash 覆写它处理**复合命令拆分**与**包装器剥离**，fs 工具覆写它处理路径锚点。
  权限层只管三态与求值顺序。与既有约束「调度靠能力标志不靠工具名 if-else」一致，
  也是官方原文的架构（K permissions-hooks.md 第四节）。
- 候选 B·权限层集中实现（大函数按工具名分支）：违反架构约束，且每加一个工具都要回来改权限层。
- 候选 C·只做工具名级别不做 specifier：`Bash` 要么全放要么全禁，
  表达不了「允许 `git *` 但禁 `git push *`」这种真实需求。

**选择：A**。

**问 3**：除了进程内 `before_tool_call` 回调，要不要同时支持**外部命令 hook**（退出码 2 = 阻断）？
- 候选 A·**两者都做**：进程内回调（权限层本身就是它的一个实现）+ 外部命令 hook
  （退出码 0/2/其他 三态，stderr 作为给模型的反馈）。**会自举**——pai 自己的
  `guards/design_gate.py` 就是这样一个 hook，做完之后 pai 能跑自己的门禁。
- 候选 B·只做进程内回调：roadmap 写的「门禁三种退出码」不做了，anna 方法论回流只回一半。
- 候选 C·只做外部命令 hook：每次工具调用都起子进程，内置规则也要写成脚本。

**选择：A**。

**问 4**：权限规则从哪里读？
- 候选 A·**`~/.pai/settings.json`（用户）+ `./.pai/settings.json`（项目）两层**：
  任一层 deny 都不能被另一层 allow 翻掉（官方语义）；按 source 分桶，
  以便 `/permissions` 能告诉你每条规则从哪来。官方的托管策略层不做。
- 候选 B·只做项目一层：「我在所有项目都禁止 `rm -rf`」这类个人安全线无处安放。
- 候选 C·规则写进 `PAI.md`（复用阶段 3 的分层加载）：**把「上下文」与「强制配置」
  混为一谈**——官方专门强调过两者不同（指令只影响模型想做什么，规则决定 harness 允许什么）。

**选择：A**。

### spec 阶段的一处自主判断（非拍板项，如实标注）

**没有任何规则命中时的默认决策 = allow**，理由与既有先例一致（压缩、事件、记忆三次接线
都是「不配置 = 行为与接线前逐字相同」）；`default_decision` 做成配置项，
想要「白名单模式」的人把它改成 `ask` 或 `deny` 即可。
**这是个有安全代价的选择**，写进 spec 与 decisions，不藏在代码里。

## 实施

superpowers 全链路：[spec.md](spec.md) → [plan.md](plan.md) → SDD。
分支：待拍板后开 `feat/permissions`。

## 结果与测试

<!-- 交付后填 -->

## 遗留问题

<!-- 交付后填，每条同步一行进全局 TODO -->

## 用到的知识

[knowledge/claude-docs/permissions-hooks.md](../../../../knowledge/claude-docs/permissions-hooks.md)（求值顺序、
Bash 匹配四坑、「语义下放给工具」原文、hook 决策协议）、
[knowledge/concepts/hooks-gates.md](../../../../knowledge/concepts/hooks-gates.md)、
[knowledge/anna/gates.md](../../../../knowledge/anna/gates.md)（本地不入库）
