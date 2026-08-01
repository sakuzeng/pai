# pai

从零手写的最小编码 agent harness（Python）。架构参照精读 pi（github.com/earendil-works/pi）与 Claude Code 反编译源码得出的设计，零代码依赖两者——所有实现都是独立写的，取舍见 docs/decisions.md。

前身是单文件实验 `experiments/mini-pi/`（保留不动，作为学习轨迹第一课）。pai 是它的毕业版：src 布局、模块化、带测试，按阶段生长成完整 harness。

## 安装与运行

```bash
mkvirtualenv pai            # 本机统一用 virtualenvwrapper
cd ~/improve/coding/agent/projects/pai
pip install -e ".[dev]"
cp .env.example .env        # 填入 DEEPSEEK_API_KEY
pai "在当前目录创建 hello.txt 写入 hello world 并读出来确认"
```

测试（无 API key 时自动跳过 llm 标记的用例，其余全部离线可跑）：

```bash
pytest
```

## 结构与阶段映射

模块按学习路线图（job/agent/agent面试准备/学习开发路线图.md）的阶段切分，一个阶段一个模块，/code-check 按此验收：

```
src/pai/
  loop.py          agent loop（种子，已从 mini-pi 移植 + max_steps/依赖注入）
  tools/           工具系统：__init__.py 注册表 + @tool 装饰器；fs.py / shell.py
  session.py       JSONL 会话落盘（审计与回放的地基，阶段 1 会用到）
  config.py        env / client 工厂（OpenAI 兼容协议，默认 DeepSeek）
  cli.py           命令行入口
  ── 以下按阶段生长 ──
  compaction.py    阶段 1：上下文压缩
  memory/          阶段 1.5：文件型长期记忆
  permissions.py   阶段 3：before_tool_call 钩子 + 权限
  streaming.py     阶段 4
  skills.py        阶段 5
  mcp_client.py    阶段 9
evals/             阶段 6：评测集与跑批
tests/             pytest；tests/fake_llm.py 是假 provider（学 pi 的 faux provider 模式）
docs/decisions.md  每个阶段记录与 pi/CC 的设计差异及理由
```

## 已知缺口（刻意的，按路线图逐阶段补）

无压缩、无权限确认、无流式、无长期记忆、无评测集。每补一块，在 docs/decisions.md 记一条"pi/CC 怎么做的、我怎么做的、为什么"。
