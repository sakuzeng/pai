# 17 viz-flow：运行时流转可视化设计

日期：2026-08-13。状态：已拍板（四问见 [README](README.md)「确认」），本文是拍板后的设计。

## 目标

pai-viz 从「静态结构图」升级为「运行时观察者」：终端跑 pai，浏览器上看每个回合
流过 harness——模型调用 / 工具执行 / session 落盘 / harness 内部事件依次点亮，
图下方是可展开的回合时间线；每处流转标注**发生在哪个代码文件**；pai 没在跑时可回放历史会话。
页面纯观察，**没有对话输入**。

## 已拍板的决定

| 决定点 | 结论 |
|---|---|
| 范围 | Layer 1（读 session JSONL）+ Layer 2（新增 harness 事件落盘） |
| 代码位置标注 | 工具 `file:line` 自省自动取；节点/事件→文件手写映射；点击经白名单跳本机编辑器 |
| 事件落点 | 并排新文件 `sessions/<同名>.events.jsonl`，session 审计流格式不动 |
| 实时性 | HTTP 轮询 + 行号游标（2s），01 的「不做自动刷新」YAGNI 正式作废（对象不同） |

## 数据层

### Layer 1：session JSONL（已存在，零改动）

五种记录（2026-08-12 实测盘点）：`system`/`user`/`assistant`（含 `tool_calls`）/
`tool`（含 `tool_call_id`）/`usage`（含 `model`/`step`/tokens/缓存明细）。
工具耗时 = `assistant.ts` 与对应 `tool.ts` 之差。

### Layer 2：`core/trace.py`（新增，事件落盘）

- 一个类 `EventTrace`，可当 `on_event` 用（`__call__(ev: AgentEvent) -> None`）：
  每个事件追加一行 JSONL 到 `<session 文件同名>.events.jsonl`（路径从 `SessionLog.path` 推导）。
- 序列化：`{"event": type(ev).__name__, "ts": time.time(), **asdict(ev)}`。
  **`MessageDelta` 不落盘**——量大且正文已在 session 文件里，落它只会把观测流写成第二份正文
  （waku 对 `text` 增量同一处理）。其余 **13 种**全落（T2 的 `RecallInjected` 之后是 14），
  `AgentStart`/`TurnStart`/`AgentEnd` 是分组边界，必须有。
- `compose(*handlers)` 扇出 helper：把渲染器与 tracer 组成一个 `on_event`。
- **写失败不炸 loop**：内部 `try/except OSError`，首次失败往 stderr 打一行，之后静默——
  观测流挂了不能连累正事（与「工具错误不 throw」同一条底线）。
- 装配点四处：`modes/once.py` 一处、`modes/interactive.py` 三处，各改一行
  （`on_event=compose(原渲染, EventTrace(session))`）。**默认开启**：它就是观测地基，
  开销是每事件一次文件 append。

### 新事件 `RecallInjected`

成功召回目前没有事件（只有 `RecallFailed`），「召回选中了哪几篇」在 Layer 2 里是个哑点。
补 `RecallInjected(names: Tuple[str, ...])`，在 `core/recall.py` 注入成功处发射。
这是本档案唯一新增的事件类型；scheduler 并发批同样无事件源，**本轮刻意不补**（记遗留）。

### 代码位置

- **工具（全自动）**：`collect.py` 自省时从注册表函数对象取
  `inspect.getsourcefile` + `getsourcelines`，转成仓库相对路径 `src/pai/core/tools/bash.py:12`。
  手写 schema 禁令的延伸：file:line 也不许手写。
- **pipeline 节点与事件类型（手写映射）**：`collect.py` 里两份数据
  `NODE_SRC`（节点 id → 文件）与 `EVENT_SRC`（事件类名 → 文件），如
  `PermissionDecided → src/pai/core/gate.py`、`Compacted → src/pai/core/compaction.py`。
  「机制住在哪」是设计知识，程序推不出来——与 01 的 pipeline 手写数据同一取舍。
  一致性由测试钉住：`EVENT_SRC` 的键集合 == `core/events.py` 的事件类名集合（减 `MessageDelta`）、
  映射到的文件必须存在。

## server 层（`viz/server.py` 扩展）

`/api/structure` 的子进程模式**不动**（那是为了 @tool 的 import 缓存）。
新端点都是读 JSONL 文件，无缓存问题，**进程内直读**：

| 端点 | 语义 |
|---|---|
| `GET /api/sessions` | 列 `paths.sessions_dir()` 下的会话：文件名/mtime/大小/有无 events 文件，mtime 新→旧 |
| `GET /api/flow?session=<name>` | 全量解析：两文件按 `ts` 合并 → turn 分组 → 返回 `turns[]` |
| `GET /api/events?session=<name>&cursor=<m>:<e>` | 增量：session 第 m 行、events 第 e 行之后的新记录，按 ts 合并返回 + 新游标；无 cursor 时只回当前行数（从现在开始看，不重放历史——waku `events_since` 同款） |
| `GET /api/reveal?path=<仓库相对路径>&line=<n>` | 白名单跳编辑器（见下） |

`session=latest`（默认）= mtime 最新的文件——「终端正跑着的那个」。

**turn 分组**（waku `collect()` 60 行改造 + pai 语义）：
`user` 记录开新 turn；`usage`/`assistant`/`tool`/harness 事件归入当前 turn；
无 `tool_calls` 的 `assistant`（或 `AgentEnd` 事件）收尾；
文件读完还没收尾的 turn **保留并标 `unfinished: true`**——挂起/被杀的现场证据，不许丢弃。
`tool_call_id` 配对在 server 侧做完，前端拿到的是配好对、带耗时的步骤列表。

**reveal 的安全边界**（页面上唯一会执行本机命令的端点）：
- 路径 `resolve()` 后必须在仓库根内，否则拒绝（防 `../`）；
- 命令只认 PATH 上的 `code` / `cursor`，argv 列表直接 exec **不过 shell**；
- 都找不到 → 返回错误与完整路径（用户自己开），不做 Finder fallback；
- server 照旧只绑 `127.0.0.1`。

## 前端（`index.html` 扩展，仍单文件零依赖）

- **顶部**：会话下拉（默认 latest）+ 实时开关（默认开）。实时开 = 2s 轮询 `/api/events`。
- **结构图通电**：waku `STAGE` 映射同款——
  `usage → llm`、`tool → tools`、每条新记录 → `session`、
  `PermissionDecided → permissions`、`Compacted/CompactionSkipped → compaction`、
  `MemoryWritten/RecallInjected/RecallFailed → memory`。
  点亮 = 加 CSS 类 + 600ms 后摘除，队列逐档播放（一次拉到 N 条就排队闪 N 下）。
- **节点角标**：代码位置小字（`core/gate.py`），点击调 `/api/reveal`。
- **回合时间线**（新 section）：每 turn 一张卡，收起态显示
  「用户消息前 60 字 · N 步 · 耗时 · Σtokens · 缓存命中率」；展开逐步显示
  模型名/in-out tokens/命中率、工具参数与结果（截断可再展开）、耗时、权限判定；
  harness 事件按类型着色成行插在发生位置；`unfinished` 卡片红色警示条。
- 显示 tokens 不显示金额——pai 不建价格表（tokens 是 ground truth，定价会变；
  waku `pricing.py` 的思路记入档案「用到的知识」即可）。

## 错误处理

| 情况 | 表现 |
|---|---|
| 无 `.events.jsonl`（Layer 2 之前的老会话） | 时间线照常（Layer 1 数据齐全），顶部提示「此会话无 harness 事件」 |
| JSONL 尾部半行（进程被杀） | 跳过该行并计数，警告条显示跳过数——**绝不因半行拒绝整个文件** |
| sessions 目录不存在/为空 | 提示从项目根目录跑过 pai 之后再来 |
| reveal 找不到编辑器 | 错误提示含完整路径 |

## 顺手修（同文件小修，随本档案走）

`collect.py` `_stage_key` 剥反引号只剥两端的 bug（TODO 已登记）：调整剥壳顺序 +
新增反向断言测试（解析出的每个 key 必须无反引号/空格等垃圾字符）。

## 测试（全离线）

- tracer：11 种事件序列化往返、`MessageDelta` 排除、写失败不炸（把目录设成只读）；
- 装配：`tests/fake_llm.py` 假客户端跑一回合，断言 `.events.jsonl` 的事件序列；
- flow 解析：**真实轨迹夹具**（`tests/fixtures/real_turn.jsonl`，老规矩）+
  构造的 unfinished 夹具 + 半行夹具；`tool_call_id` 配对与耗时计算；
- server：随机端口冒烟（照 `test_viz_server.py` 模式）、cursor 语义
  （首拉只回行数 / 追加后增量正确）、reveal 拒绝仓库外路径；
- e2e（一条即可）：`tests/fake_provider.py` 真跑 pai 进程，断言 events 文件生成且可分组。

## 刻意不做（YAGNI，均记 TODO 或本档案遗留）

- 页面对话/任何交互输入——交互归 TUI；
- 跨会话聚合的用量仪表盘（TODO 那条保持未立项）；
- 金额换算（无价格表）；
- scheduler 并发批可视化（无事件源，补事件是下一轮的事）;
- WebSocket/SSE、前端框架、任何新依赖。
