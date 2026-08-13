# pai

从零手写的最小编码 agent harness（Python）。架构参照精读 pi（github.com/earendil-works/pi，MIT）、
对 Claude Code 的实现分析、以及 deepseek-harness（github.com/deepseek-ai/deepseek-harness，MIT）
得出的设计，零代码依赖三者——所有实现都是独立写的，取舍见 docs/dev/decisions.md。

## 安装与运行

```bash
mkvirtualenv pai            # 本机统一用 virtualenvwrapper
cd ~/improve/coding/agent/projects/pai
pip install -e ".[dev]"
cp .env.example .env        # 填入 DEEPSEEK_API_KEY（或放 ~/.pai/.env，在任何目录都生效）

pai                         # 不带参数 → 交互模式 REPL
pai "在当前目录创建 hello.txt 写入 hello world 并读出来确认"   # 带任务 → 单次执行，跑完即退
```

交互模式里：`/help` 看命令、`/status` 看上下文与熔断状态、`/memory` 看加载了哪些指令文件、
`!命令` 直接跑 shell（不打模型）、行尾 `\` 续行、`Ctrl+C` 中断当前工作、`Ctrl+D` 退出。

测试（默认不打真实 API——花钱的副作用不能是默认行为）：

```bash
./test.sh              # 离线，1069 passed
./test.sh --llm        # 额外跑真实 API 冒烟，会产生费用
```

可视化(本地网页，看**架构**与**运行时流转**)：

```bash
pai-viz                 # 默认端口 7777，自动打开浏览器
pai-viz --port 8080      # 换端口
pai-viz --no-open       # 不自动打开浏览器
```

页面**纯观察，没有对话输入**——交互归 TUI，浏览器只负责看。三块内容：

**① 运行时结构图**：agent loop 的数据流 + 工具卡片(从 `@tool` 注册表自动自省——新加一个
工具，刷新页面就出现，含参数 schema)。未来环节(skills/MCP)预画成虚线灰卡，状态跟
STATUS.md 联动，做完一块图上亮一块。**每处都标着它住在哪个文件**(工具的 `file:line`
是 `inspect` 自省出来的，不是手写)，点一下用 VS Code / Cursor 打开——
CLI 不在 PATH 也行，会退回 `vscode://file/...` URL scheme 跳到已开着的窗口：

![运行时结构图](docs/assets/pai-viz-structure.jpg)

**② 回合时间线**：终端里跑 pai，浏览器 2 秒内自己长出新回合(不用刷新)，结构图上对应
节点依次点亮。展开看每一步：模型名、上下文大小、缓存命中、工具参数与结果与耗时、
以及 **harness 内部事件**(权限判定/压缩/召回/熔断/中断)——这些此前只在终端一闪而过，
现在留了下来。会话下拉框可回放历史(跨项目，`✦` 表示该会话有 harness 事件)：

![回合时间线](docs/assets/pai-viz-timeline.jpg)

token 显示三个**加起来有意义**的数：`上下文`(末步输入量，离窗口上限多远)、
`未命中`(缓存命中便宜 50 倍，这才是真正花钱的)、`输出`(不打折)。
**不显示金额**——定价会变，token 才是 ground truth。

**③ 阶段路线图**：解析 STATUS.md「模块现状」表，绿=可用 / 黄=部分 / 灰=未开始。
STATUS.md 是唯一事实来源，更新表格即变色(viz 自己也在图里)：

![阶段路线图](docs/assets/pai-viz-roadmap.jpg)

数据来自 pai 自己落的两个文件：会话 JSONL(审计流，不可再生)与并排的
`<同名>.events.jsonl`(观测流，harness 事件，可再生)。

## 数据存哪

pai 会在**用户目录**下留东西，不碰你的项目目录（布局对齐 Claude Code）：

```
~/.pai/
  .env                                  可选：放在这里的 key 在任何目录都生效
  PAI.md                                可选：用户级指令（所有项目都加载）
  history/<cwd 哈希>                     REPL 输入历史（↑/↓ 翻的就是它，按工作目录分）
  projects/-Users-you-path-to-proj/     一个项目一个目录，名字是可读的全路径
    memory/MEMORY.md                    自动记忆索引（模型用 remember 工具写）
    memory/<主题>.md                     主题笔记，按需读
    sessions/20260810-221805-36c2fc1a.jsonl          会话记录（每条带 sessionId 与 cwd）
    sessions/20260810-221805-36c2fc1a.events.jsonl   harness 事件（pai-viz 用；删了不损失历史）
```

项目里可以放 `PAI.md`（团队共享，进版本控制）与 `PAI.local.md`（个人，gitignore）——
从当前目录向上逐级加载，支持 `@path` 导入。

## 结构与阶段映射

模块按阶段切分，一个阶段一个模块；阶段定义与顺序以 docs/dev/roadmap.md 为准（本仓库唯一路线图），/code-check 按此验收：

```
src/pai/
  cli.py           命令行入口：只管参数解析与分发，不含业务逻辑
  config.py        env / client 工厂（OpenAI 兼容协议，默认 DeepSeek）
  core/            业务核心——不关心是单次执行还是 REPL
    loop.py        agent loop（依赖注入、事件流、双队列注入点、中断、压缩接线、预算熔断）
    events.py      结构化事件（frozen dataclass 扁平联合）+ 默认渲染器
    queue.py       steering / followUp 两条待注入消息队列
    interrupt.py   中断标志（Ctrl+C 只置标志，执行侧自己找地方收尾）
    paths.py       用户级路径唯一事实源：~/.pai/projects/<可读 slug>/{memory,sessions}
    session.py     JSONL 会话落盘（每条带 sessionId 与 cwd）——审计流，不可再生
    trace.py       观测流落盘：harness 事件进 <会话同名>.events.jsonl，供 pai-viz 回放
    compaction.py  上下文压缩（触发→切→摘→重建→熔断，已全链接进 loop）
    memory.py      分层指令加载（PAI.md）+ 自动记忆索引 + @path 导入
    tools/         工具系统：__init__.py 注册表 + @tool 装饰器
                   fs.py（原子写）/ shell.py（可中断到进程组）/ ask.py / memory_tool.py
    ── 以下按 roadmap 阶段生长（阶段号见 docs/dev/roadmap.md，此处不重复维护）──
    permissions.py before_tool_call 钩子 + 权限
    streaming.py   流式
    skills.py      skills
    mcp_client.py  MCP client
  tui/             终端 UI（阶段 2 后半程）：scrollback 在上、pai 接管的 dock 在下
                   **只有 renderer.py 与 terminal.py 碰终端**，其余全是纯函数或纯状态机——
                   这条边界是本模块可测性的全部来源
    component.py   Component 契约（render(width) -> list[str]）/ Container / CURSOR_MARKER
    renderer.py    dock 整块重绘 + commit（dock 与 scrollback 之间唯一的通道）
    keys.py        字节 → 按键（带状态：多字节字符与转义序列会被拆成两次 read 送达）
    editor.py      行编辑器（纯状态机，替掉 readline）
    arbiter.py     **输入归属仲裁**——治「一个输入流两个消费者抢」的病
    dialog.py      权限 ask 与 AskUserQuestion 共用一套
    dock.py        活动区 / 队列区 / 状态行 / footer
    theme.py       配色与字形（**不用 emoji**：字体缺字 + 宽度不确定）
    logo.py        启动 logo 与流光动画（同一份字形，每帧只改配色）
    terminal.py    raw mode 进出 / SIGWINCH / 退出无条件复原 / 非 tty 闸门
    screen.py      终端模拟器（字节 → 屏幕）——**测试断言与回放出图共用同一份**
    record.py      PAI_TUI_RECORD 录下写给终端的字节
    replay.py      回放成屏幕并出 PNG（pai-replay），让 AI 自己看得见界面
  modes/           交互形态——同一套 core，不同的进入与输出方式（学 pi 的 modes/）
    once.py        单次任务，跑完即退出（对应 pi 的 print-mode）
    interactive.py 交互模式接线：真 tty 走 TUI，非 tty 退回纯 REPL（行为一个字不变）
    statusline.py  工具调用状态行（纯函数 render，按终端列宽算中文宽度）
  viz/             可视化：pai-viz 起本地网页——结构图（工具自动自省）+ 回合时间线（读会话与事件 JSONL，2s 轮询实时点亮）+ 阶段路线图（解析 STATUS.md）
    flow.py        两个 JSONL 归并成回合：分组、tool_call_id 配对、未完成回合标红
evals/             评测集与跑批
tests/             pytest。两套假 provider 分工是硬的：fake_llm.py 是**注入式**假客户端（测装配与逻辑），
                   fake_provider.py **起真 HTTP 服务**说 OpenAI 兼容协议，让真 pai 进程经 PAI_BASE_URL 打进来，
                   于是 test_e2e_tui.py 能在真 pty 里跑完整回合并断言屏幕上有什么
test.sh            统一测试入口，默认不打真实 API
docs/dev/          开发记录：decisions（为什么这么选）/ devlog（做了什么）/ STATUS（现在到哪）/ TODO / roadmap（阶段地图）/ reviews
knowledge/         学习沉淀：官方文档精读、源码走读、方法论回流（索引与规约见 knowledge/README.md）
refs/              外部参考资料（DeepSeek 文档快照，不入库，用脚本生成）
```

## 已知缺口（刻意的，按路线图逐阶段补）

**没有 skills / MCP**（阶段 6）、**没有评测集**（阶段 7）、**没有会话恢复**（`--resume`）。

TUI 已交付（阶段 2 后半程，tag `tui-v1`）：scrollback 在上、pai 接管的 dock 在下——
输入归属由一个仲裁函数算出来、`/mode` 与 shift+tab 切权限模式、干活时打的字排队、
并发按动作聚合可见。**但它只接管底部**，所以**工具结果不能点、transcript 不能滚**——
那要整屏归 pai（alt-screen），已单独立项 [features/13](docs/dev/features/13-20260811-alt-screen/README.md)。
权限（阶段 4）与流式（阶段 5）也已交付。

每补一块，在 `docs/dev/decisions.md` 记一条「pi/CC 怎么做的、我怎么做的、为什么」；
每个需求一个档案在 `docs/dev/features/`（需求→方案→拍板问答→红绿数字→复盘），
待办唯一入口是 `docs/dev/TODO.md`，用户提的想法先进 `docs/dev/需求池.md`。
