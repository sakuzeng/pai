# 官方权限与 hooks 精读

- 来源：https://code.claude.com/docs/zh-CN/permissions 、https://code.claude.com/docs/zh-CN/hooks
  （2026-08-10 抓取；两章合成一篇，因为它们讲的是同一件事的两层）
- 精读日期：2026-08-10
- pai 锚点：roadmap 阶段 4、`guards/design_gate.py`（pai 已有的 PreToolUse 门禁实践）、
  [concepts/hooks-gates.md](../concepts/hooks-gates.md)

## 一、求值顺序是整套系统的骨架

> 规则按顺序评估：**deny、ask，然后 allow**。该顺序中的第一个匹配项决定结果，
> **规则特异性不会改变顺序**。

这一句话推出三个反直觉的后果，全都要抄：

1. **宽 deny 不能开例外**：`Bash(aws *)` 拒绝会挡掉 `Bash(aws s3 ls)` 的 allow。
   想开口子只能把 deny 写窄，不能靠「更具体的 allow 赢」。
2. **ask 也压 allow**：匹配的 ask 规则即使有更具体的 allow 也照样提示。
3. 设置层级同理：**任何一层 deny 都不能被别的层 allow 翻掉**（托管 > 命令行 > 本地项目 >
   项目 > 用户）。

pai 的取舍：**照抄这个顺序**，并且要有一条测试专门钉死「更具体的 allow 赢不了宽 deny」——
这是最容易被「优化成按特异性排序」的地方，而那样改会静默放开一个洞。

## 二、裸工具名 deny 与带 specifier 的 deny 是**两种东西**

> 像 `Bash` 这样的裸工具名称会**将工具从 Claude 的上下文中完全移除**，因此 Claude 永远看不到它。
> 像 `Bash(rm *)` 这样的范围化规则会**保留工具的可用性**，并在 Claude 尝试时阻止匹配的调用。

即：拒绝有两种实现层次——**不给看**（从工具 schema 里摘掉）与**给看但拦**。
pai 现在 `get_tools()` 已经有「子集选取」的能力（`INTERACTIVE_ONLY` 就是这么做的），
裸工具名 deny 正好落在同一个机制上，几乎不用新代码。

## 三、Bash 匹配的四个坑（pai 必抄，否则前缀匹配就是纸糊的）

1. **复合命令必须逐段独立匹配**。识别的分隔符：`&&`、`||`、`;`、`|`、`|&`、`&`、换行。
   `Bash(safe-cmd *)` **不会**放行 `safe-cmd && other-cmd`。
   ——不做这条，权限系统等于零：谁都会写 `ls && rm -rf /`。
2. **进程包装器要剥离**：内置剥 `timeout`、`time`、`nice`、`nohup`、`stdbuf`，
   以及**不带标志的** `xargs`。所以 `Bash(npm test *)` 也匹配 `timeout 30 npm test`。
   但 `direnv exec` / `devbox run` / `npx` / `docker exec` **不在列表里**，
   官方明说 `Bash(devbox run *)` 会连 `devbox run rm -rf .` 一起放行——
   这类「环境运行器」必须连内层命令一起写规则。
   另有一类**永远提示**、前缀规则不管用的：`watch`、`setsid`、`ionice`、`flock`，
   以及带 `-exec` / `-delete` 的 `find`。
3. **`*` 前的空格决定词边界**：`Bash(ls *)` 匹配 `ls -la` 但**不**匹配 `lsof`；
   `Bash(ls*)` 两个都匹配。`:*` 后缀等价于尾部 ` *`（且只在模式末尾被识别）。
4. **官方自己承认参数级约束是脆弱的**。原文用 `curl http://github.com/ *` 举例，
   列了五种绕法（选项前置、换协议、重定向、变量、多空格），并建议改用
   「deny 掉网络命令 + WebFetch 域名规则」或「PreToolUse hook 验 URL」。
   **这条要原样记进 pai 的 decisions**：前缀匹配是给「常规误伤」用的，不是给对抗用的。

## 四、「规则语义下放给工具解释」的官方原文长什么样

roadmap 阶段 4 写的「规则语义下放给工具解释」，在文档里对应这段：

> 工具已经用自己的规范化规则匹配的字段**不能**以 `Tool(param:value)` 的方式匹配：
> Bash 和 PowerShell 的 `command`、Read/Edit/Write 的 `file_path`、Grep/Glob 的 `path`、
> NotebookEdit 的 `notebook_path` 和 WebFetch 的 `url`。
> 像 `Bash(command:rm *)` 这样的规则可以通过复合命令绕过，因此 Claude Code **忽略它并在启动时发出警告**。

也就是说：通用的「按输入参数匹配」是**兜底**，而每个工具对自己的关键字段有**专属的
匹配语义**（Bash 懂 shell 分隔符、Read 懂 gitignore 路径、WebFetch 懂域名通配），
框架不越俎代庖。这正是 pai 要抄的架构：**权限层只管三态与求值顺序，
「这条规则匹不匹配这次调用」问工具自己**。

## 五、路径规则：gitignore 语义 + 四种锚点

| 模式 | 含义 | 例 |
|---|---|---|
| `//path` | 文件系统根绝对路径 | `Read(//Users/alice/secrets/**)` |
| `~/path` | 主目录 | `Read(~/Documents/*.pdf)` |
| `/path` | **相对于「定义它的设置文件」** | 项目设置里的 `Edit(/src/**)` = `<项目根>/src/**` |
| `path` / `./path` | 相对当前目录 | `Read(*.env)` |

**最大的坑**：单个前导斜杠**不是**绝对路径，它锚在设置源。用户设置里写
`Read(/secrets/**)` 挡的是 `~/.claude/secrets/**`，不是项目里的 `secrets/`。
裸文件名按 gitignore 语义在任意深度匹配，所以 `Read(.env)` ≡ `Read(**/.env)`。

**符号链接的处理是不对称的，这是安全设计的范例**：

- allow 规则：**符号链接路径与它的目标都匹配**才放行；
- deny 规则：**任一匹配**即拦。

即「放行要求两头都干净，拒绝只要一头脏」。pai 若做路径匹配，这条必须一起抄，
否则 `./project/key -> ~/.ssh/id_rsa` 就是个洞。

## 六、hooks：pai 已经在用的那层，官方的完整协议

pai 的 `guards/design_gate.py` 已经是一个 PreToolUse hook（JSON 出参 + 永不阻断的兜底）。
官方协议里 pai 还没用上的部分：

**退出码语义**（三态，pai 现在只用了「0 + JSON」这一种）：

| 码 | 含义 | PreToolUse 的效果 |
|---|---|---|
| 0 | 成功 | 解析 stdout 的 JSON |
| **2** | **阻断** | 忽略 stdout，**stderr 作为给模型的反馈**，拦掉工具调用 |
| 其他 | 非阻断错误 | 只给用户看 stderr，继续执行 |

**PreToolUse 的 JSON 决策**：`permissionDecision` ∈ `allow | deny | ask | defer`，
外加 `permissionDecisionReason`、`updatedInput`（**可以改写工具入参**）、`additionalContext`。
多个 hook 给出不同决策时的优先级：**deny > defer > ask > allow**。

**两条边界必须记牢**（否则会把 hook 当成万能开关）：

- **hook 的 `allow` 绕不过规则**：deny/ask 规则照常评估，匹配的 deny 仍然拦、
  匹配的 ask 仍然提示。
- **反过来，阻断的 hook 优先于 allow 规则**：退出码 2 在权限规则评估之前就停住了。
  官方给的用法很实用：「allow 掉整个 `Bash`，再用 PreToolUse hook 拒掉那几条」。

**matcher 语法**：`*` / 空 / 省略 = 匹配全部；纯字母数字加 `_-,|` = 精确串或列表
（`Edit|Write`）；含其他字符 = **JavaScript 正则（不锚定）**。

## 七、权限模式（pai 只抄两个）

官方六个：`default`（每工具首次提示）、`acceptEdits`、`plan`、`auto`（模型后台安全检查）、
`dontAsk`（未预批准即拒）、`bypassPermissions`。

对 pai 有意义的是 `default` 与 `bypassPermissions`（**非交互场景必须有一个「不问」模式，
否则 once 模式撞到 ask 就死锁**）——这正是阶段 4 要拍板的第一个问题。
`auto` 需要一个分类器模型，`plan` 需要计划态，都超出精简边界。

**另一条与 pai 直接相关的**：`bypassPermissions` 下仍然会提示的例外里，
有一条是「针对文件系统根目录或主目录的删除（如 `rm -rf /`、`rm -rf ~`）**作为断路器**仍然提示」，
且 v2.1.208 起连 `$(...)`、反引号、`<(...)` 里的替换形式也认。
即：**再怎么 bypass 也留一条硬断路器**。

## 八、贯穿两章的一句话（与 memory 那篇同一条）

> 权限规则**由 Claude Code 强制执行，而不是由模型**。您的提示或 `CLAUDE.md` 中的说明会
> 影响 Claude 尝试执行的操作，但它们**不会改变 Claude Code 允许的操作**。

这与 K memory.md 第四节是同一条，也正是 pai 立 `design_gate.py` 的理由
（AGENTS.md 的「先讨论再动手」是提示词层软约束，会被忽略）。
阶段 4 的权限层必须长在**代码里的挂点**上，不是长在 SYSTEM_PROMPT 里。

## 九、pai 阶段 4 的落地结论（本笔记的产出）

1. **求值顺序 deny → ask → allow**，第一个匹配决定；有测试钉死「具体 allow 赢不了宽 deny」。
2. **`before_tool_call` 挂点**（参照 pi 的 `beforeToolCall` 返回 block+reason）：
   pai 已有的事件流与工具循环里正好有位置。
3. **匹配语义下放给工具**：权限层问工具「这条规则匹不匹配这次调用」，
   Bash 自己处理复合命令拆分与包装器剥离，fs 工具自己处理路径锚点。
4. **ask 在无真人时怎么办**（once 模式）——阶段 4 的第一个拍板点。
5. **门禁必须带测试**（roadmap 已写死，且是对 anna 短板的修正）：
   注入已知错误、断言真的会拦。pai 的 `design_gate.py` 已有这个先例。
