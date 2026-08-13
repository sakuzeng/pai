# 17-viz-flow —— 运行时流转可视化（viz v2）
状态：已交付
分支：feat/17-viz-flow（立项、四问拍板、T1–T8 全部实现与交付）
流程：superpowers 全链路（brainstorm 2026-08-12 会话完成 → 四问拍板 2026-08-13 →
      [spec.md](spec.md) → [plan.md](plan.md) → SDD。理由：动 core 装配 + viz 前后端两头）

改**已交付**功能 [01-viz](../01-20260803-viz/README.md) 的结果（规矩 7：改变而非完成），
旧档案冻结，本档案链回。参照实现：[waku-agent](https://github.com/ShenSeanChen/waku-agent)
（MIT，已 clone 到 `../waku-agent`，与 pai 同为 stdlib http.server 零依赖路线；
其 `waku/ops/dashboard.py` + `static/js/diagram.js` + `tracing.py` 是本档案的主要参照）。

## 需求

用户原话见 [需求池 2026-08-12](../../需求池.md)。三处决定性细节：
**要流转不要对话**（页面纯观察，交互归 TUI）；「落盘」也是要看的流转；
**每个流转标注发生在哪个代码文件**（把观测页面同时当 harness 教材用）。

一句话：pai-viz 从「静态结构图」升级为「运行时观察者」——终端里跑 pai，
浏览器上看每个回合怎么流过 harness：模型调用、工具执行、session 落盘、
harness 内部事件（权限判定/压缩/召回/熔断/中断）依次点亮，
图下方长出可逐步展开的回合时间线；pai 没在跑时可选历史会话回放。

### 数据现状（2026-08-12 实测盘点，方案的事实基础）

对真实 session 文件（`~/.pai/projects/<slug>/sessions/20260811-165940-*.jsonl`）的记录类型盘点：

| 想看的流转 | 数据在哪 | 状态 |
|---|---|---|
| 模型调用 | `usage` 记录：`model`/`step`/tokens/缓存命中明细 | ✅ 已落盘 |
| 工具流转 | `assistant.tool_calls` ↔ `tool` 按 `tool_call_id` 配对，`ts` 差=耗时 | ✅ 已落盘 |
| 落盘本身 | 每行即一次落盘 | ✅ 天然存在 |
| turn 切分 | `user` 开新 turn，无 `tool_calls` 的 `assistant` 收尾 | ✅ 可推导 |
| harness 内部事件 | `core/events.py` 12 个 dataclass 只流过 `on_event`，**不落盘** | ❌ 缺口 |

## 验收标准（怎么算做完）

1. 终端真跑一个回合，浏览器**不点刷新**即可看到：结构图节点按序点亮 + 新 turn 卡片出现；
2. turn 卡片展开可见每步：模型名 / in-out tokens / 缓存命中率 / 工具参数与结果 / 耗时 / 权限判定；
3. harness 事件（`PermissionDecided`/`Compacted`/`CompactionSkipped`/`BreakerTripped`/
   `RecallFailed`/`MemoryWritten`/`Interrupted`）出现在时间线对应位置（若问 1 拍板含 Layer 2）；
4. 每个 pipeline 节点、每张工具卡、每类 harness 事件标注**代码位置**；
   工具的 `file:line` 必须自动自省（`@tool` 注册表 + `inspect`），不许手写；
5. 会话下拉框可选历史 session 回放；无收尾的 turn 显式标「未完成」而不是丢弃；
6. 页面上**没有**对话输入；
7. 测试全离线，turn 分组/配对逻辑至少一条测试拿真实 session 轨迹当输入（老规矩）。

## 候选方案与确认

<!-- 拍板时按模板补「选择/理由」，问题与候选先立在这里 -->

### 问 1：范围——只读现有落盘，还是补齐 harness 事件落盘？

- 候选 A·**只做 Layer 1（零 core 改动）**：viz server tail session JSONL
  （waku `events_since` 的游标模式），能交付模型/工具/落盘三种流转 + 时间线 + 回放。
  取舍：**最想看的 harness 内部事件依然不可见**（gate 判了什么、压缩何时触发全没有），
  需求的学习目的只满足一半。
- 候选 B·**Layer 1 + Layer 2（推荐）**：另加一个 Tracer observer——照 waku
  `tracing.compose()` 扇出模式，把「终端渲染」与「事件落盘」组合注入现有 `on_event`
  （注入点现成，12 个 frozen dataclass 序列化即可，估约 40 行 + 装配一行）。
  取舍：动 core 装配；要为 12 个事件定序列化格式（连带问 3）。
- 候选 C·接外部 OTel/Phoenix（waku 也这么做了一半）：不自建前端。
  取舍：违背 pai 零依赖 + 从零实现的学习定位，列出仅为对照，不推荐。

### 问 2：「发生在哪个代码文件」怎么标？

- 候选 A·**工具自动自省 + 其余手写映射（推荐）**：工具卡的 `file:line` 从注册表函数对象
  `inspect.getsourcefile/getsourcelines` 取（零维护，schema 同源原则的延伸）；
  pipeline 节点与 harness 事件类型 → 代码位置是**手写映射**（`PermissionDecided → core/gate.py`
  这类对应关系是设计知识，程序推不出来，与 01 的 pipeline 手写数据同一取舍）。
  可选加一档：点节点用本机 `code`/`cursor` CLI 打开文件（waku `reveal_path` 模式）。
- 候选 B·运行时抓调用栈：tracer 落盘时记录 emit 方的栈帧。
  取舍：拿到的是「谁调了 on_event」（多半是 loop.py），不是「这个机制住哪」，
  信息更准确却更没用，且每事件多一次栈遍历。不推荐。

### 问 3（若问 1 选 B）：harness 事件落到哪里？

- 候选 A·**并排新文件（推荐）**：`sessions/<同名>.events.jsonl`。
  session JSONL 保持「审计流 = messages + usage」的既有语义，消费者（压缩、将来 `--resume`、
  evals）不需要学会跳过 12 种新记录；两个文件同名配对，viz 合并读。
- 候选 B·混入同一个 session 文件：单文件省事，游标只有一个。
  取舍：改变已交付文件格式的语义（08/14 的消费者假设），且事件流是可再生的观测数据、
  审计流是不可再生的历史，**生命周期不同的数据不该同文件**。

### 问 4：实时性怎么做？

- 候选 A·**HTTP 轮询 + 行号游标（推荐）**：`/api/events?cursor=N`，前端 2s 一拉，
  点亮队列 waku 式逐档播放。零新依赖，server 仍是无状态 stdlib。
  注：这会**推翻 01 的「不做自动刷新（YAGNI）」**——当时不做的是静态结构图的刷新，
  本轮的对象是时间性的流转，不刷新等于没做。TODO 对应条目已注明复议。
- 候选 B·SSE/WebSocket 推送：延迟更低。
  取舍：本地单人观察页，2s 轮询的延迟无感；SSE 要 server 持长连接、复杂度不成比例。不推荐。

### 确认（2026-08-13，AskUserQuestion 四问，用户逐项选择）

**问 1 原文**：「范围怎么定？harness 内部事件（权限判定、压缩、召回、熔断）现在不落盘，
页面上想看到它们就得给 core 加一个约 40 行的 Tracer observer（注入点现成）。」
- 候选 A·Layer 1 + 2：读 session JSONL + 新增事件落盘，全部流转可见；代价动 core 装配、定 12 个事件的序列化格式
- 候选 B·只做 Layer 1：零 core 改动，但 gate/压缩等最想看的看不到
- 候选 C·接外部 OTel：违背零依赖与从零实现定位，仅对照

**选择**：A（Layer 1 + 2）。理由：需求的目的就是看 harness 内部，只做 Layer 1 交付一半。

**问 2 原文**：「『发生在哪个代码文件』怎么标注？」
- 候选 A·自省 + 手写映射 + 点击跳编辑器：工具 file:line 用 inspect 自动取（零维护）；
  节点/事件 → 文件是手写映射（设计知识程序推不出）；点节点用本机 code/cursor CLI 打开
- 候选 B·同上但不做点击跳转：少一个「viz server 能执行本机命令」的面
- 候选 C·运行时抓调用栈：拿到的是「谁调了 on_event」不是「机制住哪」，更准确却更没用

**选择**：A（含点击跳编辑器）。理由：学习场景里「看到就能跳进去读」闭环价值大；
跳转命令白名单限定 code/cursor、路径限定仓库内（spec 落约束）。

**问 3 原文**：「（若做 Layer 2）harness 事件落到哪个文件？」
- 候选 A·并排新文件 `sessions/<同名>.events.jsonl`：审计流语义不变，既有消费者零影响；
  审计流（不可再生）与观测流（可再生）生命周期不同，不该同文件
- 候选 B·混入 session 同一文件：单游标省事，但改已交付格式语义，08/14 消费者假设全要重审

**选择**：A（并排新文件）。理由：如上，不动已交付格式。

**问 4 原文**：「实时性怎么做？（选轮询即推翻 01 的『不做自动刷新』YAGNI，TODO 已注明复议）」
- 候选 A·HTTP 轮询 + 行号游标：2s 一拉，点亮队列逐档播放，零新依赖、server 无状态
- 候选 B·SSE 推送：延迟更低，但长连接复杂度对本地单人观察页不成比例

**选择**：A（轮询 + 游标）。理由：本地页面 2s 延迟无感；01 那条 YAGNI 正式作废
（对象不同：当时是静态结构图，本轮是时间性流转），TODO 对应条目待交付时改写关闭。

## 结果与总结

交付了 spec 里的全部 7 条验收标准。`./test.sh` → **1069 passed, 3 deselected**（约 82s，全离线）。
详细日志见 [devlog.md](devlog.md)（8 个 task 各一条），页面证据见
[evidence/20260813-页面验收/](evidence/20260813-页面验收/)。

**交付了什么**（终端跑 pai，浏览器看流转）：

| 能力 | 落点 |
|---|---|
| harness 事件落盘 | 新增 `core/trace.py`：`EventTrace` 当 `on_event` 用，14 种事件进 `<会话同名>.events.jsonl` |
| 成功召回也发事件 | 新增 `RecallInjected`（此前只有失败发事件，成功是哑的） |
| 会话内分段留痕 | 新增 `ConversationCleared`；手动 `/compact` 补发 `Compacted`（此前只 print） |
| 回合分组与配对 | 新增 `viz/flow.py`：两流按 ts 归并、`tool_call_id` 配对、未完成回合标红、坏行跳过计数 |
| 观测端点 | `server.py` +4：`/api/sessions`（跨项目）、`/api/flow`、`/api/events`（游标增量）、`/api/reveal` |
| 代码位置 | 工具 `file:line` **自省**；节点/事件→文件手写映射 + 测试防漂移；点击跳编辑器（CLI 或 URL scheme） |
| 前端 | `index.html` +时间线 section +约 200 行 JS：卡片展开、结构图点亮、会话下拉、代码角标 |

**刻意没做的**（都在 spec「刻意不做」或用户当场裁决）：页面对话输入、金额换算与价格表、
会话级合计（用户 2026-08-13 明确说不加）、scheduler 并发批可视化（无事件源）、
SSE/WebSocket、任何新依赖。

**交付过程中被用户当场纠正的一处口径**：回合卡片原本显示各步 `prompt_tokens` 之和并标作
「计费」。用户指出**缓存命中便宜 50 倍**，这么加既不是钱也不是上下文大小。改为三个
「加起来有意义」的数：**上下文**（末步输入，离窗口上限多远）、**未命中**（真正贵的部分）、
**输出**（不打折）。原始 `tokens_in` 留在载荷里但页面不再当计费显示。

## 遗留问题

均已登记 [TODO](../../TODO.md)：

1. 事件文件无上限增长、无清理策略（P2）；
2. TUI 下 `MemoryWritten`/`RecallFailed` 直接打 stdout 可能弄花 dock（P2，**非本轮引入**，
   是 feature 12/13 就存在的事件路由问题）；
3. `@tool` 注册表是进程级全局，测试注册的工具会漏进后续测试（P2，本轮绕开未根治）；
4. scheduler 并发批与 queue 进出无事件源，页面上看不见（P2）；
5. 不显示金额、无会话级合计（P3，用户裁决）。

**同时关闭了两条旧 TODO**：`_stage_key` 反引号 bug（T6 修）、
「pai-viz 的会话回放」（本轮交付；用量聚合仍未立项）。
「pai-viz 不做自动刷新」按拍板结论改写关闭（结构图照旧手动，时间线 2s 轮询）。

## 用到的知识

waku-agent 源码走读（2026-08-12/13，MIT，clone 在 `../waku-agent`）。借鉴对照表——
借的全是**观测侧**的机制骨架，不借**交互侧**的任何东西：

**机制照搬（代码不抄）**：

| pai 设计 | waku 出处 | 借的是什么 |
|---|---|---|
| `/api/events` 游标轮询 | `dashboard.py::events_since` | 游标=行号；**无 cursor 首拉只回行数不重放历史** |
| turn 分组 | `dashboard.py::collect` 的 trace→turns 段 | 开组/归入/收尾；**没收尾的 turn 标「未完成」不丢弃**（挂起现场证据） |
| 结构图通电 | `static/js/diagram.js` 的 `STAGE` + `hot()` | 事件→节点/边映射表；CSS 类点亮 + 队列逐档播放 |
| `compose()` 扇出 | `tracing.py::compose` | 渲染器与 tracer 组成一个 on_event |
| 增量不落盘 | `Tracer.event` 的 `if kind=="text": return` | `MessageDelta` 同理挡在事件流外 |
| reveal 跳编辑器 | `dashboard.py::reveal_path` | PATH 探测 code/cursor、argv 不过 shell、路径 resolve 后限边界内 |
| 坏行容错 | `collect()` 逐行 try/except | 绝不因半行拒绝整个文件，跳过并计数 |

**借思路但反着做**：「图必须诚实」的两分法（能自动的必须自动——工具 file:line 自省；
手写的必须有测试防漂移——`EVENT_SRC` 键集合钉死）；「tokens 是 ground truth 金额是衍生品」
（`tracing.py` 注释）——pai 走更远，连换算都不做；「生命周期不同的数据不同文件」
（它的 traces 可重置 / `usage.jsonl` 永不擦除）——用在 session（审计）与 events（观测）的切分上，
即问 3 的拍板理由。

**明确不借**：chat dock 与全部 SSE 交互（它一半复杂度在此）、pricing/catalog/Arena/evals 面板、
前端拆 10 个 js（pai 未到疼点）、OTel 双输出（问 1 候选 C 落选）。
