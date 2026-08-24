# dsh 的测试策略：分层车道 + 会话回放，不做打分评测

- 来源：deepseek-harness（github.com/deepseek-ai/deepseek-harness，MIT），
  commit `47f9438`（2026-08-13，与 dsh-loop.md 同 commit）。
  `docs/testing.zh.md`（第一方文档）/ `packages/test-support/llm-replay/README.zh.md`
  （第一方文档）/ 源码对照：`packages/core/agent-loop/tests/contract-regressions.spec.ts`、
  `packages/test-support/` 目录、全仓 `*.spec.ts` 与 `*.e2e.ts` 计数。
  证据等级（D#69）：dsh 文档与源码同仓同 commit，正文里逐处标「文档说」还是「源码是」。
- 精读日期：2026-08-24
- pai 锚点：roadmap 阶段 7（evals）、`tests/fake_provider.py`（pai 的回放半成品）、
  `src/pai/core/session.py`（回放的数据源）、`docs/dev/STATUS.md` 测试节
- 相关：[pi-evals.md](pi-evals.md)（打分评测那半边的参照）、
  [../loop/session-format-three-way.md](../loop/session-format-three-way.md)（会话格式，回放的地基）

## 一句话

dsh 没有「evals」这个词——它把同一个需求拆进五条车道（单元 / 覆盖率门禁 /
带密钥真 API e2e / 无密钥快照回放 / 浏览器快照），用「会话 JSONL 当 fixture
回放模型流」替代打分：断言的不是分数，是外部世界与固定 transcript 的 diff。

## 五条车道（文档说，源码对照过的标了数）

1. 单元（`pnpm run test`）：源码对照——全仓 692 个 `*.spec.ts`；
   文档点名的 `contract-regressions.spec.ts` 实存，37 条（约定回归的永久测试，
   对位 pai 拿测试钉已知洞的做法）。
2. 覆盖率门禁：对 `packages/*/*/src` 按文件 100% 行覆盖。文档自己先把话说死：
   未覆盖的行往往是「该删的死代码」而非「该补的测试」，且行覆盖是必要条件
   永远不是充分条件。pai 不抄这条门禁（学习项目成本不划算），但「覆盖率证明
   行被执行过，不证明功能对」这句判词值得留着。
3. 带密钥真 API e2e：129 个 `*.e2e.ts`（含无密钥的构建产物冒烟，文档口径下
   带密钥的是其中一部分）；每个密钥各自控制、缺密钥自动跳过让无密钥 CI 绿。
   ★ 文档原话级的态度：「我们是 DeepSeek，不要吝惜真实 API 测试……自动跳过
   不是成本信号」。pai 的语境相反（个人项目、花钱的副作用不能是默认行为，
   D#23），抄结构不抄态度：`--llm` 双开关保留，但「价值最高的是冒烟测试——
   它捕获单元测试全绿、产品却坏了的问题」这条判断与 pai 的 feature 15
   （假 provider + 真 pty e2e）互为印证。
4. 快照（无密钥）：录一次真实会话 → 签入 JSONL → 回放断言归一化输出的 diff。
   record / replay / refresh 三个动词分开（`test:snapshot:record` 只在模型
   transcript 变化时用，refresh 只在回放输入仍有效时用），CI 强制只读
   `DSH_SNAPSHOT=replay` 绝不写预期——「谁能改标准答案」是被制度约束的。
5. 浏览器快照：同 4，对象换成 Chromium 渲染结果。pai 对位物是
   `pai-replay` 出 PNG（feature 14），暂无 diff 门禁。

## llm-replay：回放评测的完整参考设计（文档说；src 仅 index/invariant 两文件）

fixture 就是持久化会话日志本身，不另造格式——`assistant/chunk` 事件按
`(turn, step)` 分组即可重建每次 `stream()` 调用的分片序列。要点四条：

1. 两种失败面承认「重放不出来」：产生分片前就抛（如 401，日志里只有
   `turn/end {error}`）与取消/挂起（差异在时序不在分片）——用伴随文件
   `replay.override.json` 显式补（整体替换或按调用索引打补丁），
   不硬造不静默。`hang` 条目配 `readyFile` 空标记让外部驱动确定性取消。
2. `{{fromRequest:<regex>}}` 占位符：录制时不可能预知的值（模型必须回填的
   随机 id）从实时请求正则捞——回放脚本不是死磁带，有一个最小的活口。
   模式匹配不到、非法、未闭合都明确报错。
3. 嵌套 agent 按会话键控：父子会话各一份日志，实时会话 id 每次都是新的，
   按「首次调用顺序」绑定到按 `createdAt` 排序的脚本；超出脚本数明确报错。
4. 压缩摘要的回放另立规则：`compaction/summary` 带 `llmStreamCall: true` 才
   重建成功流；「有 rawOutput 不等于发生过本地 LLM 调用」——模板摘要器也会
   留全文。回放器对「这条记录是不是一次模型调用」的判定是显式字段不是猜。

pai 对位：`fake_provider` 已是「按脚本回真 SSE」的服务，缺的是「从会话
JSONL **派生**脚本」这一步；`SessionLog` 的 v1 格式存的是装配后的消息而非
逐 chunk 事件——意味着 pai 的回放粒度天然是「整条 assistant 消息」而不是
「分片序列」，够不够用要在方案里明确取舍（评测断言基本落在消息层，分片层
只有流式装配自己的测试需要，而那块已有 `tests/test_streaming.py`）。

## 方法论三条（文档说，可直接迁移）

1. 验证外部世界，而非自我报告：e2e 断言应重新运行命令或从外部重读文件，
   「对 agent 自身输出做关键词探测会让作弊的 agent 通过」。这是评测判分的
   第一原则——pai 的判分默认档应当是外部世界断言，模型 judge 是补充。
2. 只 mock 贵或不确定的边界（LLM 适配器、网络、时钟），下游一切保持真实
   ——与 pai 两套假 provider 的分工（注入的假客户端测逻辑 / 真 HTTP 服务
   测全链）同一条光谱。
3. 共享 fixture 放普通模块绝不放另一个 `*.e2e.ts`：导入一个 spec 会重注册
   其 describe，真 API 调用重复执行。pytest 语境的对位是「fixture 进
   conftest，不许从测试文件互相 import」。

## 反向对照记录（本次核对）

- 文档五条车道的命令与目录结构、`contract-regressions.spec.ts`（37 条）、
  `packages/test-support/{llm-replay,llm-mock-server,acp-snapshot,
  agent-loop-testkit,loader-smoke}` 均实存——本篇范围内文档与源码未见打脸。
  未逐行核对 llm-replay 实现与其 README 的一致性（src 两个文件，届时动工
  若抄其派生算法再核）。
