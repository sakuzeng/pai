# 官方交互模式（interactive-mode）精读

- 来源：https://code.claude.com/docs/zh-CN/interactive-mode （2026-08-10 抓取）
- 精读日期：2026-08-10
- pai 锚点：roadmap 阶段 2（REPL）、`src/pai/modes/once.py`（REPL 的兄弟模式）、
  `src/pai/core/loop.py` 的 `on_event`

这页是什么、不是什么：它是产品交互参考（快捷键、输入模式、可见行为），
不讲实现。所以本笔记从它取的是交互契约——「一个交互式 coding agent 必须提供哪些
交互」——而实现结构仍看 [pi-agentloop.md](../loop/pi-agentloop.md)（事件流、双队列）。
官方页面全程不提「steering / followUp 队列」这类内部语义，别把 pi 的词硬塞给它。

## 一、对 pai 阶段 2 真正有用的四条

### 1. 中断语义分两级，且「保留已完成工作」是明确承诺

| 键 | 官方行为 |
|---|---|
| `Esc` | 中断 Claude 或关闭对话框——「停止当前响应或工具调用中途，以便您可以重定向。Claude 保留迄今为止完成的工作」。有对话框打开时 `Esc` 归对话框，不中断 |
| `Ctrl+C` | 有操作在跑 → 中断；没有 → 第一次清输入，第二次退出 |
| `Ctrl+D` | EOF，退出会话 |

对 pai：「保留已完成工作」是可以在无流式的 REPL 上兑现的——中断粒度落在
loop 的步边界（工具执行完、下一次 `create()` 之前），已追加进 `messages` 的
assistant/tool 消息原样留下。真正的「响应中途中断」要等阶段 5 流式。
`Ctrl+C` 的两级语义（先清输入再退出）零成本，纯 REPL 也能照做。

### 2. 用户可以在 agent 干活时输入——这是交互模式与 print 模式的本质差异

官方没有单独一节讲「排队」，但三处旁证摆着：`/btw` 明写「即使 Claude 正在处理响应时
您也可以运行」；`Ctrl+B` 把正在跑的 Bash 移到后台后「Claude Code 可以在命令继续执行时
响应新提示」；`Esc` 的说法是「中断……以便您可以重定向」——重定向的前提是能在
非空闲时刻表达意图。

对 pai：这就是双队列（steering 在工具执行后注入 / followUp 在本该停下时注入）要解决的
问题，设计来源记在 pi 笔记，不是本页给的。纯 REPL（阻塞 `input()`）拿不到「干活时
打字」，所以阶段 2 的诚实做法是：队列结构先立、注入点先钉死测试，输入源在 REPL 阶段
只能是「上一轮结束后排队的输入」；真正的并发输入等 TUI/流式。

### 3. `!` shell 模式：绕开模型直接跑命令，输出进上下文

* 命令与输出都加进对话上下文，显示实时进度
* 不需要模型解释或批准
* v2.1.186 起输出进上下文后模型会自动接话（「跑完 `! npm test` 直接得到失败解释」），
  想要旧行为得关 `respondToBashCommands`
* 空提示上 `Escape`/`Backspace`/`Ctrl+U` 退出 shell 模式

对 pai：这是 REPL 里性价比最高的一个功能——复用已有的 `bash` 工具，不经模型，
把 `{"role":"user"}` 一条命令回显塞进 `messages` 即可。「跑完要不要自动接话」是个真
取舍（自动接话 = 每次 `!` 都花一次请求钱），CC 自己也把它做成了开关。

### 4. 命令历史的三条细节（抄之前先知道）

* 按工作目录存储（不是全局一条流）
* `/clear` 开新会话时输入历史重置，但上一轮对话仍可恢复
* 连续两次提交相同提示只记一条——所以按 ↑ 直接跳到上一个*不同*的提示
* `Ctrl+R` 反向搜索：加载所选范围内最近 100 条唯一提示，范围可在
  「本会话 / 本项目 / 所有项目」间用 `Ctrl+S` 循环
* 历史扩展（`!`）默认禁用——即 bash 那套 `!!`、`!$` 不生效，因为 `!` 已被 shell 模式占用

对 pai：Python `readline` 免费给到「↑/↓ + Ctrl+R」，pai 要自己做的只有
「按 cwd 分文件存」与「连续重复只记一条」这两条语义。

## 二、多行输入：唯一全终端可用的是 `\` + Enter

| 方法 | 键 | 适用 |
|---|---|---|
| 快速转义 | `\` + `Enter` | 所有终端 |
| Option 键 | `Option+Enter` | macOS 配好 Option-as-Meta |
| Shift+Enter | `Shift+Enter` | iTerm2 / WezTerm / Ghostty / Kitty / Warp / Apple Terminal / Windows Terminal 开箱即用；VS Code、Cursor、Alacritty、Zed 要跑 `/terminal-setup` |
| 控制序列 | `Ctrl+J` | 任何终端，无需配置 |
| 粘贴模式 | 直接粘贴 | 代码块、日志 |

对 pai：纯 REPL（阻塞 `input()`）只能实现 `\` + Enter 与 `Ctrl+J`（后者本就是 LF）——
其余全依赖终端 key protocol，属 TUI 阶段。这张表的真正价值是说明了为什么 TUI 不能
只绑 Shift+Enter：一半终端根本发不出这个序列。

## 三、明确记下但 pai 不做的

| 官方功能 | 不做的理由 |
|---|---|
| Vim 编辑器模式（NORMAL/VISUAL/文本对象全套） | 输入层玩具，与 harness 学习目标无关 |
| 转录查看器（`Ctrl+O`）、全屏渲染、鼠标 | roadmap 阶段 2「不做」已写死：无 alt-screen、无主题、无鼠标 |
| 提示建议（灰显补全，复用父对话 prompt cache） | 产品体验功能；机制值得知道（后台请求蹭缓存，缓存冷时直接跳过省钱）但不实现 |
| 会话回顾 `/recap`、PR 审查状态、语音输入 | 同上，产品面 |
| `Ctrl+B` 后台任务、`Ctrl+X Ctrl+K` 杀后台子代理 | 后台任务依赖并发执行器；子代理在 map.md 已裁定不做 |
| `@` 文件路径补全、`/` 命令菜单的交互式筛选 | 补全 UI 属 TUI；`/` 命令本身可做最小集（见下） |
| `/btw` 侧问题 | 有意思的设计（看得见全上下文但无工具 = subagent 的反面），但要一个覆盖层 UI；记在这里备查 |

## 四、顺手记的两条事实（与其他阶段挂钩）

* 任务列表在上下文压缩中持续存在（`Ctrl+T` 那节原话）——即 CC 把待办清单排除在压缩
  可丢弃内容之外。与阶段 1 的「摘要六项保留清单」是同一思路的两种实现，见
  [context-management.md](context-management.md)。
* 后台任务输出超 5GB 自动终止、写文件由模型用 Read 取回——大输出隔离的产品级解法。
  pai 现在靠 `read_file` 截断提示兜（TODO R#17），量级差得远，如实标注。

## 五、pai 阶段 2 REPL 的最小 `/` 命令集（本笔记的落地结论）

官方 `/` 菜单包含内置命令、skills、plugins、MCP 贡献的命令——pai 现在只有第一类。
从本页交互契约倒推，REPL 真正缺不了的是四个：`/exit`（对应 `Ctrl+D`）、
`/clear`（对应「开新会话 + 重置输入历史」）、`/compact`（把阶段 1 的自动压缩变成手动可触发）、
`/status`（估算 token / 步数 / 熔断状态——pai 已有全部数据，只差一个出口）。
其余（`/config`、`/resume`、`/theme`…）在 map.md 里已归「产品配置类，不做」。
