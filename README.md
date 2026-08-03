# pai

从零手写的最小编码 agent harness（Python）。架构参照精读 pi（github.com/earendil-works/pi，MIT）与对 Claude Code 的实现分析得出的设计，零代码依赖两者——所有实现都是独立写的，取舍见 docs/dev/decisions.md。

前身是单文件实验 `experiments/mini-pi/`（保留不动，作为学习轨迹第一课）。pai 是它的毕业版：src 布局、模块化、带测试，按阶段生长成完整 harness。

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
./test.sh              # 离线，66 passed
./test.sh --llm        # 额外跑真实 API 冒烟，会产生费用
```

## 结构与阶段映射

模块按学习路线图（job/agent/agent面试准备/学习开发路线图.md）的阶段切分，一个阶段一个模块，/code-check 按此验收：

```
src/pai/
  cli.py           命令行入口：只管参数解析与分发，不含业务逻辑
  config.py        env / client 工厂（OpenAI 兼容协议，默认 DeepSeek）
  core/            业务核心——不关心是单次执行还是 REPL
    loop.py        agent loop（依赖注入、max_steps 兜底、usage 落盘、预算熔断）
    tools/         工具系统：__init__.py 注册表 + @tool 装饰器；fs.py / shell.py
    session.py     JSONL 会话落盘（审计与回放的地基）
    compaction.py  阶段 1：上下文压缩（秤/警戒线/拍平机已就位，压缩本身未接）
    ── 以下按阶段生长 ──
    memory/        阶段 1.5：文件型长期记忆
    permissions.py 阶段 3：before_tool_call 钩子 + 权限
    streaming.py   阶段 4
    skills.py      阶段 5
    mcp_client.py  阶段 9
  modes/           交互形态——同一套 core，不同的进入与输出方式（学 pi 的 modes/）
    once.py        单次任务，跑完即退出（对应 pi 的 print-mode）
    ── 将来 ──
    interactive.py REPL
  viz/             架构可视化：pai-viz 起本地网页，结构图（工具自动自省）+ 阶段路线图（解析 STATUS.md）
evals/             阶段 6：评测集与跑批
tests/             pytest；tests/fake_llm.py 是假 provider（学 pi 的 faux provider 模式）
test.sh            统一测试入口，默认不打真实 API
docs/dev/          开发记录：decisions（为什么这么选）/ devlog（做了什么）/ STATUS（现在到哪）/ TODO / reviews
refs/              外部参考资料（DeepSeek 文档快照，不入库，用脚本生成）
```

## 已知缺口（刻意的，按路线图逐阶段补）

无压缩、无权限确认、无流式、无长期记忆、无评测集。每补一块，在 docs/dev/decisions.md 记一条"pi/CC 怎么做的、我怎么做的、为什么"。
