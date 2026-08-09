# pai

从零手写的最小编码 agent harness（Python）。架构参照精读 pi（github.com/earendil-works/pi，MIT）与对 Claude Code 的实现分析得出的设计，零代码依赖两者——所有实现都是独立写的，取舍见 docs/dev/decisions.md。

## 安装与运行

```bash
mkvirtualenv pai            # 本机统一用 virtualenvwrapper
cd ~/improve/coding/agent/projects/pai
pip install -e ".[dev]"
cp .env.example .env        # 填入 DEEPSEEK_API_KEY
pai "在当前目录创建 hello.txt 写入 hello world 并读出来确认"
```

测试（默认不打真实 API——花钱的副作用不能是默认行为）：

```bash
./test.sh              # 离线，75 passed
./test.sh --llm        # 额外跑真实 API 冒烟，会产生费用
```

架构可视化(本地网页，看运行时结构图与阶段路线图，改代码刷新即现)：

```bash
pai-viz                 # 默认端口 7777，自动打开浏览器
pai-viz --port 8080      # 换端口
pai-viz --no-open       # 不自动打开浏览器
```

必须在项目根目录运行——「阶段路线图」靠相对路径读 `docs/dev/STATUS.md`，不在根目录跑
不会报错，但该区域会为空并显示警告条(结构图部分不受影响)。

**运行时结构图**：agent loop 的数据流 + 工具卡片(从 `@tool` 注册表自动自省——新加一个
工具，刷新页面就出现，含参数 schema)。未来环节(压缩/权限/流式/记忆/skills/MCP)从第一
天就预画成虚线灰卡，状态跟 STATUS.md 联动，做完一块图上亮一块。点工具卡展开参数表：

![运行时结构图](docs/assets/pai-viz-structure.jpg)

**阶段路线图**：解析 STATUS.md「模块现状」表，绿=可用 / 黄=部分 / 灰=未开始。
STATUS.md 是唯一事实来源，更新表格即变色(viz 自己也在图里)：

![阶段路线图](docs/assets/pai-viz-roadmap.jpg)

## 结构与阶段映射

模块按阶段切分，一个阶段一个模块；阶段定义与顺序以 docs/dev/roadmap.md 为准（本仓库唯一路线图），/code-check 按此验收：

```
src/pai/
  cli.py           命令行入口：只管参数解析与分发，不含业务逻辑
  config.py        env / client 工厂（OpenAI 兼容协议，默认 DeepSeek）
  core/            业务核心——不关心是单次执行还是 REPL
    loop.py        agent loop（依赖注入、max_steps 兜底、usage 落盘、预算熔断）
    tools/         工具系统：__init__.py 注册表 + @tool 装饰器；fs.py / shell.py
    session.py     JSONL 会话落盘（审计与回放的地基）
    compaction.py  上下文压缩（秤/警戒线/拍平机已就位，压缩本身未接）
    ── 以下按 roadmap 阶段生长（阶段号见 docs/dev/roadmap.md，此处不重复维护）──
    memory/        文件型长期记忆
    permissions.py before_tool_call 钩子 + 权限
    streaming.py   流式
    skills.py      skills
    mcp_client.py  MCP client
  modes/           交互形态——同一套 core，不同的进入与输出方式（学 pi 的 modes/）
    once.py        单次任务，跑完即退出（对应 pi 的 print-mode）
    ── 将来 ──
    interactive.py REPL
  viz/             架构可视化：pai-viz 起本地网页，结构图（工具自动自省）+ 阶段路线图（解析 STATUS.md）
evals/             评测集与跑批
tests/             pytest；tests/fake_llm.py 是假 provider（学 pi 的 faux provider 模式）
test.sh            统一测试入口，默认不打真实 API
docs/dev/          开发记录：decisions（为什么这么选）/ devlog（做了什么）/ STATUS（现在到哪）/ TODO / roadmap（阶段地图）/ reviews
knowledge/         学习沉淀：官方文档精读、源码走读、方法论回流（索引与规约见 knowledge/README.md）
refs/              外部参考资料（DeepSeek 文档快照，不入库，用脚本生成）
```

## 已知缺口（刻意的，按路线图逐阶段补）

无压缩、无权限确认、无流式、无长期记忆、无评测集。每补一块，在 docs/dev/decisions.md 记一条"pi/CC 怎么做的、我怎么做的、为什么"。
