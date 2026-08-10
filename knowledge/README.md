# knowledge —— 学习沉淀

官方文档精读、pi/CC 源码走读、方法论回流。与 `docs/dev/`（开发证据）正交：
那边记「pai 做了什么、为什么」，这边记「外面的世界怎么做、我学到了什么」。

## 结构

```
claude-docs/     Claude Code 官方文档按模块精读笔记，一模块一文件
source-walks/    源码走读，文件名前缀 cc-/pi- 区分来源，不建子目录
concepts/        横切概念笔记（hooks/门禁这类不专属某家源码的），一概念一文件
anna/            anna 工作区方法论回流（本地不入库，R2#1 裁决）
inbox.md         待消化收件箱：看到但还不知道怎么用的工具/想法，一行一项
```

目录随第一篇笔记创建，禁止空目录占位；不嵌套二级目录。

## 使用规约

1. **按需精读，动工前补笔记，禁止囤积式通读**。只读 roadmap 当前阶段
   「前置精读」列出的章节（见 [../docs/dev/roadmap.md](../docs/dev/roadmap.md)）。
2. **准入一问**：这篇笔记能否锚到**已存在的东西**（某个源文件、已写下的 decisions
   条目、或已动工/即将动工的 roadmap 阶段的前置精读清单）？只能锚到遥远未来阶段的，
   先在该阶段「前置精读」记一行待读，动工那天再落笔记——否则就是囤积。
   面经、考点、通识囤积去面试准备仓库。
   **唯一豁免：[inbox.md](inbox.md)**——还写不出锚点的新工具/想法在那里一行一项地待着，
   升格成正式笔记时才须过准入一问；升格或裁决不做后从 inbox 划掉。
3. **指针笔记是一等公民**：面试准备仓库已有的深度文档只写一页指针
   （链接原文 + 摘 pai 视角结论），不搬运正文。

## 笔记模板

```markdown
# <标题>
- 来源：<官方文档 URL / 仓库内相对路径。本机绝对路径不进笔记正文——
  收进本页「外部参照」一节，正文以「外部参照 N」引用>
- 精读日期：YYYY-MM-DD
- pai 锚点：<src/pai/... | docs/dev/decisions.md #N | roadmap 阶段 N>

<正文>
```

## 登记表

状态取值：**指针** = 只链接原文 + 摘 pai 视角结论；**精读** = 对照来源逐点写的完整笔记；
**沉淀** = 无单一原文可链的原创整理（如方法论回流）。指针升精读的时机：动工时发现
指针的结论粒度不够用。

| 笔记 | 一句话 | 状态 | pai 锚点 |
|---|---|---|---|
| [claude-docs/context-management.md](claude-docs/context-management.md) | 官方上下文窗口与 compact 机制，对照 pai 压缩现状 | 精读 | src/pai/core/compaction.py |
| [claude-docs/interactive-mode.md](claude-docs/interactive-mode.md) | 官方交互契约（中断两级 / 干活时输入 / `!` shell 模式 / 历史），及 pai REPL 取舍 | 精读 | roadmap 阶段 2 |
| [claude-docs/memory.md](claude-docs/memory.md) | 官方两套记忆（人写的分层指令 / 模型自写的自动记忆）、加载算法，及压缩重注入这条 pai 尚不存在的 bug | 精读 | roadmap 阶段 3 |
| [claude-docs/map.md](claude-docs/map.md) | 官方文档章节 → pai 归属/不做 的覆盖图 | 沉淀 | docs/dev/roadmap.md |
| [source-walks/cc-compaction.md](source-walks/cc-compaction.md) | CC 四级递进压缩策略要点 | 指针 | roadmap 阶段 1 |
| [source-walks/pi-agentloop.md](source-walks/pi-agentloop.md) | pi 四层分层 + 钩子 + 双队列 | 指针 | roadmap 阶段 2 |
| [concepts/hooks-gates.md](concepts/hooks-gates.md) | hooks 事件与工具调用门禁模式（阶段 4 设计输入） | 沉淀 | roadmap 阶段 4 |
| [concepts/context-management.md](concepts/context-management.md) | 上下文管理全梯度 + 「窗口用不满≠不用管」的实测认知 | 沉淀 | src/pai/core/compaction.py |
| [inbox.md](inbox.md) | 待消化收件箱（准入豁免区，一行一项） | 常驻 | 升格前豁免 |
| [anna/gates.md](anna/gates.md) | anna 确定性门禁方法论（含短板教训）。**本地不入库**（R2#1 裁决，.gitignore 排除）——克隆本仓库的读者看不到此文件 | 沉淀 | roadmap 阶段 4 |

## 外部参照（本机路径，对外部读者是死链；笔记正文以「外部参照 N」引用）

面试准备仓库 `/Users/sakuzeng/improve/job/agent/agent面试准备/`：

1. `09_项目连接_pi-agent/README.md` —— 知识点 → pi/CC/mini-pi/pai 代码位置速查表（精确到行号）
2. `01_Agent核心机制/深度_agentloop三层对照.md` —— mini-pi / pi / CC 三层 agent loop 对照
3. `02_上下文工程与记忆/深度_compaction源码走读.md` —— pi 压缩全家走读 + CC 摘要请求与 usage 口径对照（655 行；CC 压缩策略部分见本库 cc-compaction.md，不在此文）
4. `11_工具系统/README.md`、`13_安全与权限/深度_权限与安全.md`、`12_记忆系统/深度_CC记忆系统.md`

参照仓库：

5. pi-mono `/Users/sakuzeng/improve/coding/agent/pi-mono/`
6. CC 反编译源码 `/Users/sakuzeng/improve/coding/agent/projects/claude-code-source-code/`（v2.1.88）
7. anna 工作区（本机私有目录，路径不公开——含雇主内部信息，见 [anna/gates.md](anna/gates.md) 来源说明）
