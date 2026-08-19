# pai-viz:架构可视化工具设计

日期:2026-08-03。状态:已确认,进入实施计划。

## 目标

一个本地网页,直观展示 pai 的整体架构,并且代码变化(尤其是新增 `@tool` 工具)后刷新页面即可看到。
不做运行时观测/会话回放——那是以后的事。

## 用户确认过的决定

| 决定点 | 结论 |
|---|---|
| 核心用途 | 看程序整体架构;加了新功能(如新工具)后界面能反映 |
| 交付形态 | 本地小 server + 浏览器 |
| 内容范围 | ① 运行时结构图 ② 阶段路线图(带状态);不做用量卡片 |
| 实现方案 | 零依赖手写:stdlib http.server + 手写单页 HTML/SVG |
| CLI 入口 | 独立命令 `pai-viz`(不动 cli.py) |

## 对现有代码的影响:几乎为零

- 新增目录 `src/pai/viz/`(3 个文件,自成一体)
- `pyproject.toml` 加一行 console script:`pai-viz = "pai.viz.server:main"`
- `cli.py`、`core/`、`modes/` 一行不动。删掉 viz 目录和那一行,项目回原样。

## 文件布局

```
src/pai/viz/
  collect.py     数据收集:自省工具注册表 + 解析 STATUS.md + 概念图数据 → 打印 JSON
  server.py      stdlib http.server(零新依赖):
                   GET /              → 返回 index.html
                   GET /api/structure → 起子进程跑 collect,透传 JSON
  index.html     单页前端,dark 主题,手写 HTML/CSS/JS + SVG 连线
```

运行:`pai-viz`(可选 `--port`,默认 7777)→ 浏览器开 `http://localhost:7777`。

## 关键设计点:每次请求起子进程收集

server 是常驻进程,Python 模块 import 后有缓存,新加的 `@tool` 在老进程里刷不出来。
每次 `/api/structure` 起一个新解释器(`python -m pai.viz.collect`)现场收集,
约 100-200ms,本地开发无感。收益:

1. 改完代码 → 刷新浏览器 → 新工具立刻出现(核心体验)
2. 隔离性:代码写出语法错误时,子进程失败、错误显示在页面上,server 本身不挂

## 数据层(collect.py 输出的 JSON)

三块:

- `tools`(全自动):调 `get_tools()` 拿注册表,每个工具输出
  name / description / 参数列表(名字、类型、描述、是否必填)。
  全部来自 `@tool` 从签名生成的 schema,零手工维护。
- `pipeline`(手写数据、程序渲染):运行时结构图的节点与连线,定义为 collect.py 里的一份
  Python 数据:`user task → agent loop ⇄ LLM(显示当前 model 名)/ tools 组 → session 落盘 / 预算熔断`。
  将来接入 compaction、permissions 等环节时,改这份数据即可上图。
- `stages`(解析 STATUS.md):解析 `docs/dev/STATUS.md` 的「模块现状」表,
  每行输出 模块名 / 状态(可用、部分、未开始)/ 说明。
  不另造状态文件——STATUS.md 保持单一事实来源。

### 三类功能的上图机制(扩展规则)

| 功能类型 | 例子 | 怎么上图 | 自动化程度 |
|---|---|---|---|
| 工具 | web_fetch、ask_user_question、grep、子 agent 派发 | 用 `@tool` 写好即注册,刷新即现,含参数 schema | 全自动 |
| harness 环节 | compaction、permissions、streaming、memory、skills、mcp_client | pipeline 数据里占一个节点;接入 loop 时加节点+连线(几行) | 手工,但极轻 |
| 阶段状态 | 上述模块做到什么程度 | 解析 STATUS.md 表,更新表格即变色 | 跟文档自动走 |

### 结构图预画「未来节点」

pipeline 数据从第一版就把 compaction、permissions、streaming、memory、skills、mcp_client
等未实现环节画上(参照 Pi 仪表盘里 LLM OPS 虚线框的画法):

- 节点带 `stage` 字段,关联 STATUS.md 表里的模块名
- 状态「未开始」→ 虚线灰色;「部分」→ 黄色;「可用」→ 实线正常色
- 效果:结构图 = 完整蓝图 + 实时进度,每补完一个阶段,图上对应节点「点亮」

## 前端(index.html)

单页,dark 主题(参照 Pi Coding Agent 仪表盘的气质)。两个区域:

1. 运行时结构图:按 `pipeline` 数据渲染卡片分组
   (agent loop 框内含 LLM 节点;tools 组内每个工具一张卡,可展开看参数),
   卡片间用一层 SVG 画连线。
2. 阶段路线图:`stages` 渲染成网格卡片,
   绿=可用 / 黄=部分 / 灰=未开始,卡片附说明文字。

顶部状态栏:最后刷新时间 + 刷新按钮(重新 fetch,不刷整页)。不做自动轮询。

## 错误处理

| 情况 | 表现 |
|---|---|
| STATUS.md 表格式变了、解析失败 | 阶段区显示黄色警告条,结构图照常(两块互不拖累) |
| 子进程收集失败(如代码语法错误) | 页面红色错误条显示 stderr,顺手当编译检查用 |
| 端口被占 | 明确报错,提示用 `--port` 换端口 |

## 测试(全离线,零 API 费用)

- collect:工具自省输出含 bash/read_file/write_file/edit_file 且形状正确;
  STATUS.md 解析用内联 markdown 夹具测「正常表格」「畸形表格」两条路
- server:随机端口起服务,冒烟测两个端点返回 200 与 JSON 形状

## 刻意不做(YAGNI)

- 不做会话回放、用量仪表盘(以后需要再立项)
- 不做文件监听/自动刷新/WebSocket——点刷新按钮就够
- 不做 import 依赖图——展示的是概念架构,不是 import 关系
- 不引入任何前端框架或 Python 依赖
