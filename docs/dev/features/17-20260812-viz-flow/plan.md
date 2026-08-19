# 17 viz-flow 实施计划

日期：2026-08-13。前置：[spec.md](spec.md) 已拍板。每个 task 一律 TDD：
先写测试贴红的输出，再实现贴绿的数字；devlog.md 一步一条。

## Task 拆分（依赖顺序）

### T1 `core/trace.py`：EventTrace + compose
- 测试：`tests/test_trace.py`
  - 11 种事件（除 `MessageDelta`）各序列化一行，round-trip 后 `event` 字段=类名、字段齐全；
  - `MessageDelta` 喂进去不产生行；
  - 路径推导：`SessionLog.path` 为 `X.jsonl` 时事件文件是 `X.events.jsonl`（同目录）;
  - 写失败不炸：目录只读时 `EventTrace` 吞掉 OSError，进程不抛，stderr 恰好一行；
  - `compose(a, b)`：两个 handler 都收到同一事件对象，其一抛异常不拦截（渲染器炸就该炸）。
- 实现：约 60 行（比 README 预估的 40 多在错误处理与路径推导）。

### T2 `RecallInjected` 事件
- 测试：`tests/test_events.py` 增补（union 成员数 +1、frozen、render_text 输出一行）；
  `tests/test_recall.py` 增补：注入成功路径发射 `RecallInjected(names=(...))`，
  空选/失败路径不发射。
- 实现：`core/events.py` 加 dataclass 入 union；`core/recall.py` 注入成功处发射。

### T3 装配四处（once ×1、interactive ×3）
- 测试：`tests/test_trace_wiring.py`——fake_llm 假客户端跑一回合（once 与 interactive 各一条），
  断言 `.events.jsonl` 存在且事件序列形如
  `AgentStart → TurnStart → AssistantMessage → ToolStart/ToolEnd → ... → AgentEnd`；
  `$HOME` 隔离由 conftest 兜着，测试自己再断言没写进真实 HOME（08-10 教训）。
- 实现：每处一行 `on_event=compose(渲染, EventTrace(session))`。

### T4 `viz/flow.py`：合并 + turn 分组 + 配对
- 测试：`tests/test_viz_flow.py`
  - 真实轨迹夹具 `tests/fixtures/real_turn.jsonl`：分出正确 turn 数、
    `tool_call_id` 配对齐全、耗时>0、usage 归到对的步；
  - 构造夹具：unfinished turn 保留且带标记；半行 JSONL 跳过并计数；
    events 文件缺失时 turns 照常、`has_events=False`；
  - 两文件按 ts 合并后事件落在所属 turn 内。
- 实现：纯函数模块（读文件路径进、dict 出），server 只做透传——离线可测的关键。

### T5 server 新端点
- 测试：`tests/test_viz_server.py` 增补（沿用随机端口 fixture）：
  - `/api/sessions` 列出 tmp 目录里的两个假会话、新→旧；
  - `/api/flow?session=...` 返回 T4 的形状；
  - `/api/events` cursor 语义：首拉只回行数不回历史；追加两行后增量恰好两条；游标推进；
  - `/api/reveal` 拒绝仓库外路径（`../`、绝对路径外部）返回 error；
    编辑器探测 monkeypatch 掉，测试不真开编辑器。
- 实现：`server.py` 加路由；sessions 目录从 `pai.core.paths` 取。

### T6 `collect.py`：代码位置 + 顺手修
- 测试：`tests/test_viz_collect.py` 增补：
  - 每个工具带 `src` 字段，形如 `src/pai/...py:<行号>`，文件真实存在；
  - `NODE_SRC` 覆盖全部带 stage 的节点、`EVENT_SRC` 键集合 == 事件类名集合（减 MessageDelta）、
    映射文件全部存在；
  - 红测先钉 bug：`` `core/tools/` 的 matcher `` 解析出的 key 不含反引号/空格
    （现状必红），再修 `_stage_key`。
- 实现：inspect 自省 + 两份映射数据 + 剥壳顺序修正。

### T7 前端（`index.html`，仍单文件零依赖）

三条结构性决定（先定死，再写码）：
1. turn 分组只存在于 Python 一处（T4），前端不重复实现——有新事件就重拉 `/api/flow`
   整体重渲时间线（本地文件解析毫秒级，2s 一次无感）。两处分组逻辑必然漂移，宁可多一次拉取；
2. 灯与卡解耦：`/api/events` 增量只驱动点亮队列，时间线只认 `/api/flow`——
   动画丢帧（页面开晚了、队列截断）不影响时间线的正确性；
3. XSS 姿势沿用 01：`innerHTML` 只搭骨架，数据（用户消息、工具参数/结果、事件字段）
   一律 `textContent`——工具结果是任意字符串，含 `<script>` 是正常输入不是攻击才怪。

页面布局（在现有三段之间插一段）：
`header`（+会话下拉 `#sessions` +实时开关 `#live`）→ 结构图（现有，通电）→
回合时间线 `#timeline`（新） → 阶段路线图（现有，不动）。

新增 JS（约 6 个函数，挂现有 `<script>` 里）：
- 状态：`cursor`（`"m:e"` 游标）、`liveOn`、`expandedTurns`（Set，重渲后保展开态）、`animQueue`；
- `loadSessions()` 填下拉；切会话 = 重置游标 + `loadFlow()`；
- `loadFlow(sess)` 拉 `/api/flow` → `renderTimeline(turns)`（卡片骨架照 `toolCard()` 的写法）；
- `poll()`：`setInterval` 2s，拉 `/api/events`；有新事件 → 入 `animQueue` + 重拉 flow；
- `playNext()`：队列逐档（600ms）出队，查 `STAGE` 映射，`hot()` 点亮节点/边（01 的教训在此
  复用：SVG 呈现属性不认 var()，点亮必须走 CSS 类，`.node.hot` 规则驱动）；
- `reveal(path, line)`：代码位置角标点击 → `/api/reveal`，错误显示在警告条。

CSS：全部复用现有 tokens；harness 事件行配色——权限=accent 紫、压缩=partial 黄、
熔断/未完成=err 红、记忆/召回=ok 绿；`unfinished` 卡片红色警示条。

测试与验收：
- 机器可判的进 `test_viz_server.py`：页面含 `id="timeline"`/`id="sessions"`、
  引用的每个 `/api/` 路径确有对应路由（防端点改名前端瞎了没人知道）、
  `STAGE` 映射引用的节点 id 都在 `_PIPELINE_NODES` 里（waku 承认这类漂移「测试抓不到，
  动画只是静默不亮」——pai 至少把 id 存在性钉住）；
- 人工验收对照 README 验收标准 1/2/4/5/6：终端 fake_provider 跑一回合 + 浏览器观察，
  截图/录屏归档 `evidence/`。

### T8 收尾
- STATUS.md：viz 行改写（含 Layer 2 事件流）；模块表加 `core/trace.py` 一行；
- TODO：关闭「不做自动刷新」复议条与 `_stage_key` bug 条，登记新遗留
  （scheduler 批次无事件源、用量聚合页仍未立项、events 文件无清理策略）；
- 档案 README「结果与总结」+ devlog 补全 + 复盘.md（四问，交付门槛）；
- 全局 devlog 里程碑一行。

## 风险与提前认账

- interactive 三处装配点各自拿 session 的方式可能不同——T3 动工时先读清楚
  三处的 session 生命周期（/clear 重开会话时 events 文件要跟着换），
  这是本计划里最可能返工的点；
- 事件文件无上限增长与清理策略：本轮不做，交付时记 TODO；
- `inspect.getsourcefile` 对装饰器包裹的函数拿到的是原函数文件（`@tool` 用 wraps 的话成立），
  T6 红测阶段先验证这个假设，不成立就取 `__wrapped__`。

## 验收口径

README「验收标准」7 条全过 + `./test.sh` 全绿（当前基线 999 passed，交付时贴实际数字）。
