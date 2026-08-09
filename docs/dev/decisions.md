# 设计决策记录

每个阶段完成后追加一节：pi/Claude Code 怎么做的 → pai 怎么做的 → 为什么。这是面试话术的直接来源。

## 索引（定点跳转用；与正文一一对应由 tests/test_docs_consistency.py 校验）

| # | 决策一句话 |
|---|---|
| 1 | 工具异常在 Tool.run() 内转字符串结果，loop 不感知 |
| 2 | tool_call_id 配对由 loop 唯一负责，任何分支都回填 tool 消息 |
| 3 | max_steps 用 for 而非 while True + 计数 |
| 4 | 会话 JSONL 从第一天就有 |
| 5 | 参数非法 JSON 不 crash，回填错误让模型重试 |
| 6 | token 估算用 ceil(字符/4)，不引 tiktoken（后被 #15 替代） |
| 7 | 估算计入 tool_calls 的 name+arguments，不计 id/tool_call_id |
| 8 | 未知 role 记 0 且不参与拍平 |
| 9 | should_compact 用严格大于，enabled=False 短路 |
| 10 | 截断按字段做，默认 5000 字符并标注 |
| 11 | 拍平保留 tool_call_id 对应关系 |
| 12 | 摘要请求选 pi 的拍平，不选 CC 原样发（后被 #16 反转，待实测） |
| 13 | 压缩阈值从百分比改为减固定预留量 |
| 14 | 熔断器：压缩连续失败要停 |
| 15 | 估算改用官方系数、中英文分开，废弃 chars/4 |
| 16 | 拍平 vs 原样发的成本账已反转——先不改实现，等实测 |
| 17 | 缓存是尽力而为，不能当契约 |
| 18 | 「该不该压」靠真实 usage 锚 + 增量估算，不靠纯估算 |
| 19 | ~~1.5 倍系统偏差不修~~（原论证被推翻，划掉保留，见 #32） |
| 20 | usage 记录挂 type 而非 role，绝不挂到 message 上 |
| 21 | 用量预算做成 loop 层熔断（平台没有限额可依赖） |
| 22 | 预算检查放在发下一次请求之前 |
| 23 | 真实 API 测试必须显式选择加入 |
| 24 | core/（业务）与 modes/（交互形态）提前分开 |
| 25 | cli 只做解析分发，接线进 modes/once |
| 26 | compaction.py 暂不拆目录，设触发条件 |
| 27 | 开发记录进 docs/dev/，docs/ 根留给用户文档 |
| 28 | test.sh 统一入口，默认不打真实 API |
| 29 | viz 每次请求起子进程收集，不常驻 import |
| 30 | viz 前端零依赖手写单页，不用框架/mermaid |
| 31 | 阶段状态解析 STATUS 表，不另造状态文件 |
| 32 | 切点也用真实 usage 差值（锚点列表）；注记：比 pi 更强的约束，超长单轮需兜底 |
| 33 | thinking mode 实测压过文档：不回传 reasoning_content，锚不受影响 |
| 34 | 压缩成败只认压缩后首次真实 usage 回传 |
| 35 | 知识入仓 knowledge/ 不建独立仓库；补记：主要代价是雇主内容披露，裁决 anna 篇不入库 |
| 36 | 功能档案按目录组织；注记：devlog 下沉、decisions 保持全局 |

## 种子版（2026-08-02）

1. 工具异常在 Tool.run() 内转成字符串结果，loop 不感知。
   pi 在 loop 层 catch 后 createErrorToolResult；CC 在 executor 层。pai 收进 Tool 自身，理由：Python 里装饰器 + 方法边界最自然，且保证"任何调用路径"都不会漏（未来子 agent 直接调工具也安全）。
2. tool_call_id 配对由 loop 唯一负责，任何分支（未知工具、参数非法 JSON、执行异常）都必须回填一条 tool 消息。
   来源：CC query.ts 的孤儿 tool_result 防护——API 层面 tool_use 与 tool_result 必须严格成对，这是三个实现共同的硬约束。
3. max_steps 用 for 而不是 while True + 计数。
   mini-pi 没有步数上限；pi 用 maxIterations、CC 也有兜底。防的是模型永不收敛时烧钱。
4. 会话 JSONL 从第一天就有。
   pi 的 session 是 harness 核心；先落地最小版（append-only 每消息一行），阶段 1 compaction 时"原始数据不删只改视图"的架构才接得上。
5. 参数非法 JSON 不 crash，回填错误让模型重试。
   真实 provider 偶发输出坏 JSON；mini-pi 会直接 json.loads 崩掉。

## 阶段 1 · 第 1-2 步：token 秤与拍平机（2026-08-02）

6. token 估算用 `ceil(字符数 / 4)`，不引 tiktoken。
   pi/CC 都以 provider 回传的 usage 为准，本地估算只用于"该不该压"的触发判断。pai 同样只求量级：装 tokenizer 换来的精度，对一个阈值比较没有价值，却引入了与模型绑定的依赖。向上取整是刻意的——低估会让压缩来得太晚，那是唯一会炸窗口的方向。已知缺陷：中文按 4 字符/token 会显著低估（真实约 1-1.5 token/汉字），后续接 usage 回传做校准。
7. `estimate_tokens` 计入 tool_calls 的 `name` + `arguments`，但不计 `id` / `tool_call_id`。
   arguments 是 JSON 字符串，一次 write_file 就几千字符，漏算会让整条轨迹低估一个数量级。id 是定长管道噪音，计入它会让"400 字符 = 100 token"这条心智模型对 tool 消息失效（多出 1 个 token），可读性损失大于精度收益。
8. 未知 role 一律记 0 且不参与拍平，而不是尽力猜。
   宁可在下游明显缺失，也不要一个来路不明的数悄悄进入阈值判断。
9. `should_compact` 用严格大于，且 `enabled=False` 时短路。
   压线不动手，避免阈值上反复横跳（压完仍在线上会立刻再触发）。
10. 截断在"每个字段"而不是"整段文本"上做，默认 5000 字符，并标注 `[... N more characters truncated]`。
    整段截断会让最近的消息被切掉，而最近的恰恰最重要；按字段截则是一条 bash 结果撑不爆摘要预算。标注截掉多少是给摘要模型的信号：你看到的是残缺内容，别当全貌总结。
11. 拍平保留 tool_call_id 的对应关系。
    摘要模型需要能看出"谁调了什么、结果是啥、哪一步失败过"——真实轨迹里那条 sed 报错就是压缩最该保住的信息（不然模型压完会重蹈覆辙）。

## 阶段 1 · 拍平（serialize）：pi 与 CC 给了相反的答案（2026-08-02）

12. 摘要请求怎么发？pai 选 pi 的「拍平」，不选 CC 的「原样发」。

    **pi**（`pi-mono/packages/coding-agent/src/core/compaction/utils.ts:109`）：
    `serializeConversation()` 把 N 条消息压成一段文本，塞进**一条** user 消息发出去。
    源码注释：`// Serialize conversation to text so model doesn't try to continue it`。
    附带截断 tool 结果到 2000 字符（`TOOL_RESULT_MAX_CHARS`）。

    **CC**（`claude-code-v2.1.88/src/services/compact/compact.ts:441`）：
    不拍平。`messages: messagesToSummarize` 原样发，末尾追加一条 user 消息装摘要指令。
    整个 services/compact/ 目录没有 serialize 函数。

    **CC 为什么敢原样发**：prompt cache。`compact.ts:1179` 注释写明用 forked agent
    复用主对话的缓存前缀（system / tools / model / messages prefix 必须逐字节一致），
    feature flag `tengu_compact_cache_prefix` 默认 true。为保住缓存，他们甚至刻意不设
    maxOutputTokens——设了会改 thinking 配置导致 cache key 不匹配。

    **CC 的代价是可量化的**：不拍平就挡不住"模型接着干活"，只能靠 prompt 硬掰
    （`prompt.ts:19` 的 NO_TOOLS_PREAMBLE，含"工具调用会被拒绝，你会失败"的威胁）。
    其源码注释自陈：在较新的模型上，仍有百分之几的概率会去调工具而非总结，白白浪费掉唯一一轮；
    较旧的模型上这个比例低两个数量级。

    **pai 选拍平的理由**：pai 走 OpenAI 兼容协议打 DeepSeek，且 loop 当前是单次任务
    执行完即退出，没有 CC 那种跨会话的缓存前提。"因为有缓存所以可以浪费"这个前提不成立时，
    照抄 CC 是两头不讨好——既没省到钱，又要承担那个百分之几的不听话率。
    ⚠️ 此结论绑定"无缓存"这个前提。若 pai 改成 REPL 且实测 DeepSeek 缓存命中率高，
    这条要重新算账（见 devlog 待办）。

13. 阈值算法要改：从「百分比」改成「减固定预留量」。
    pai 现在是 `tokens > window * 0.8`；pi 是 `contextTokens > contextWindow - reserveTokens`
    （16384）；CC 是 `窗口 - min(模型最大输出, 20000) - 13000`（`autoCompact.ts:30,62`），
    且 CC 的预留量有统计依据：其注释说明该值取自压缩摘要输出长度的极高分位数（约两万 token 量级）。
    两家都用绝对量，因为"下一轮要留多少空间"是个绝对需求（一轮回复 + 几个工具结果），
    与窗口多大无关。百分比在大窗口上会过早触发：200k 窗口下 pai 在 160k 就压，CC 在 167k。
    → 待改，见 devlog。

14. 熔断器：压缩连续失败要停，不能无限重试。
    CC 把连续失败上限设为 3，其源码注释记录了设这个限制的起因：在没有熔断之前，
    个别会话出现过数千次连续压缩失败，全局每天因此浪费大量 API 调用。
    上下文一旦不可逆地超限，重试只会烧钱。
    pai 实现自动压缩时必须带这个，别等踩坑。

## 阶段 1 · 用官方系数替换通用经验值 + 缓存改写了拍平之争（2026-08-02）

15. token 估算改用 DeepSeek 官方系数，中英文分开算，废弃 `chars/4`。
    依据 refs/deepseek-api/quick_start/token_usage.md：「1 个英文字符 ≈ 0.3 个 token、
    1 个中文字符 ≈ 0.6 个 token」。此前 pai 与 pi 都用 `chars/4`（=0.25），
    对英文低估 17%、对中文低估 2.4 倍（不是此前 devlog 猜的 3-4 倍）。
    pi 用通用值是因为它要面对任意 provider；pai 只打 DeepSeek，没有理由放着官方系数不用。
    全角标点（U+3000-303F、U+FF00-FFEF）划入中文侧——中文正文里占比不低，划错会系统性偏低。
    实测：REAL_TRAJECTORY 从 161 → 243 token（+51%）。
    仍是估算：官方同句写明「实际以模型返回为准」，精确校准等 usage 回传（官方另有离线
    tokenizer 可下载，见同文档）。

16. 第 12 条（拍平 vs 原样发）的账已反转——但先不改实现，等实测。
    当初选拍平的理由是「pai 没有 CC 那种缓存前提」。该前提已被两份证据推翻：
    - refs/deepseek-api/guides/kv_cache.md：硬盘缓存对所有用户**默认开启**，无需改代码；
      前缀单元在「用户输入结束位置」与「模型输出结束位置」落盘。agent loop 每步重发递增
      前缀，天然命中——这正是 CC「原样发 + 末尾追加指令」能命中缓存的机制，在 DeepSeek 同样成立。
    - 用户 2026-08-02 全天用量实测：输入缓存命中率 **84.7%**（23,424 / 27,640）。
    价格差（refs/deepseek-api/quick_start/pricing.md，deepseek-v4-flash）：
      缓存命中 0.02 元/M vs 未命中 1 元/M —— **50 倍**，不是此前估的 10 倍。
    重算摘要请求成本：
      拍平（pi）  0.64× token × 1 元    = 0.64  ← 新前缀，必然全部未命中
      原样发（CC）1.0×  token × 0.02 元 = 0.02  ← 匹配已落盘前缀单元
    **CC 的做法在 DeepSeek 上便宜约 32 倍。**
    未改实现的原因：CC 自陈原样发有百分之几的概率让模型去调工具而非总结（其在较新模型上的实测），
    该数在 DeepSeek 上完全未知。拿一个未验证假设换另一个不是改进。
    → 实现 summarize 时先做原样发 + 记录不听话率，serialize_conversation 保留为兜底路径
      （摘要请求自身超长时用它压缩，对应 CC 的 prompt_too_long 重试）。

17. 缓存是「尽力而为」，不能当契约。
    kv_cache.md 明确：不保证 100% 命中；缓存构建耗时秒级；不再使用后几小时到几天自动清空。
    所以缓存只能用于优化成本，不能用于正确性假设（例如不能假设「反正命中，随便发」）。

## 阶段 1 · 上下文大小以真实 usage 为锚（2026-08-03）

18. 「该不该压」不靠估算，靠 provider 回传的真实值做锚，只估锚之后新增的消息。
    背景：改用官方 0.3/0.6 系数后，本地估算对 DeepSeek 仍系统性低估约 1.5 倍
    （实测见 devlog.md）。差额来自两处我们根本没数的东西：chat template 的
    每条消息框架开销（约 25 token/条）与服务端格式化后的工具 schema（比 json.dumps 贵约 1.5 倍）。
    结论不是继续调系数——那是在追一个永远追不上的目标（分词器细节不可能靠字符统计复现），
    而是**换掉估算的作用位置**：
      context_tokens = 上一步真实 prompt_tokens + 该步真实 completion_tokens
                     + 估算(此后新增的 tool 结果)
    加 completion_tokens 是因为紧随其后那条 assistant 消息的真实 token 数就是它——白送的精确值。
    于是 1.5 倍的偏差只乘在几十个 token 的尾部上。实测误差从 -33% 降到 **-1.3%**。
    pi 同样这么做（compaction.ts:189「using the last assistant usage when available」），
    这也解释了 pi 为何敢用粗糙的 chars/4：它根本不靠估算撑全局。

19. ~~那 1.5 倍的系统偏差**不修**。分工定了之后它就无害了：「该不该压」→ context_tokens
    （真实值锚定，绝对值准）；「在哪下刀」→ estimate_tokens（只需相对准；**均匀偏差同时作用于
    所有消息，切点几乎不动**）。去补「每条 25 token 框架开销」「schema ×1.5」是在给一个不需要准的
    地方增加复杂度，且这些补正值随模型/协议版本漂移，等于给自己埋维护债。~~

    **【2026-08-03 推翻，原文保留为记录】** 上面划掉的论证有两处错，外部评审指出了一处，
    复核时又发现一处更严重的。结论（不修估算器）碰巧仍然成立，但**理由完全换了**。

    **错误一（评审 R#4 指出）：「均匀偏差不影响切点」只在切点按比例定义时成立。**
    pi 的 findCutPoint（`compaction.ts:417`）是从后往前累加估算值，与**绝对预算**比较：
    ```ts
    accumulatedTokens += messageTokens;            // estimateTokens 估出来的
    if (accumulatedTokens >= keepRecentTokens) {   // 与常数 20000 比
    ```
    低估 1.5 倍 = 累加到「估算的 2 万」时实际已保约 3 万，挤占 reserve 余量。
    只有「保最近 30% 的消息」这类比例式切法，分子分母同缩放才会抵消。

    **错误二（复核实测发现，比错误一更致命）：偏差根本不均匀。**
    用相邻两次 usage 反推真实段成本，对照字符估算：
    | 段 | 估算 | 真实 | 倍数 |
    |---|---|---|---|
    | `已写入 usage_check.txt（17 字符）` | ~10 | 42 | **4.2×** |
    | `alpha\nbeta\ngamma\n` | ~6 | 33 | **5.5×** |
    每条消息约 25-30 token 的 chat template 框架开销是**固定量**，占比随消息变短而暴涨：
    短 tool 结果低估 4-5 倍，几千字符的长消息只低估约 2%。
    **「均匀」这个前提本身就不成立**——而切点附近往往正是短 tool 结果。

20. usage 记录挂 `type` 而非 `role`，且绝不挂到 message 上。
    多一个字段就改变请求前缀，而 DeepSeek 硬盘缓存要求「完整匹配缓存前缀单元」
    （refs/deepseek-api/guides/kv_cache.md）——污染消息等于把命中率打到 0。
    附带好处：estimate_tokens 对无 role 记录返回 0、serialize_conversation 直接跳过，
    usage 记录天然不会被误当成消息。有测试钉住（test_usage_never_leaks_into_messages_sent_to_api）。

## 阶段 1 · 烧钱防线（2026-08-03）

21. 用量预算做成 loop 层的熔断，而不是指望平台限额——因为平台根本没有。
    查证 refs/deepseek-api/quick_start/rate_limit.md：DeepSeek 只提供**并发限速**
    （v4-flash 2500、v4-pro 500，按账号计、与 API Key 无关），**没有任何消费限额或配额功能**。
    另有 `GET /user/balance` 可查余额（api/get-user-balance.md），但那是只读的，挡不住花钱。
    所以三层防线，从硬到软：
      1) 账户只充小额——唯一无法被代码 bug 绕过的保障，没有的钱花不掉；
      2) loop 层 `max_total_tokens` 熔断（本条）；
      3) 真实 API 测试改为显式选择加入（第 23 条）。

22. 预算检查放在「发下一次请求之前」，不放在收到响应之后。
    请求一旦发出就无法撤销，检查点放在循环开头意味着**超支上限被钳制在一次请求内**。
    代价是最后一次请求必然超出预算一点点（实测：上限 1500，实际停在 1695）——
    这是可接受的，因为唯一的替代方案是预估下次请求的开销再决定发不发，
    而预估本身就有 1.5 倍误差（decisions 第 18 条），拿一个不准的数去省一次请求不划算。
    provider 不回 usage 时预算自动失效，此时仅靠 max_steps 兜底——已知取舍，有测试钉住。

23. 真实 API 测试必须**显式选择加入**，光有 key 不够。
    原实现是「有 DEEPSEEK_API_KEY 就自动跑 llm 标记的测试」。后果：任何配好 .env 的人
    跑一次 pytest 就静默产生 API 费用——外部评审时评审者本人就中招了（见 reviews 第 2 条）。
    改为双重条件：有 key **且** `PAI_RUN_LLM_TESTS=1`。
    原则：花钱的副作用永远不能是默认行为。

## 阶段 1 · 框架对齐 pi（2026-08-03）

24. 提前把 `core/`（业务核心）与 `modes/`（交互形态）分开，趁代码只有 587 行。
    pi 的分法：`src/core/`（tools / compaction / session-manager / system-prompt…）
    与 `src/modes/`（interactive TUI / print-mode / rpc）。核心不关心自己被谁调用。
    pai 路线图里有 REPL，等 REPL 写完再分就是一次大搬家 + 所有 import 改一遍；
    现在搬只动 32 个 import 点，有 52 个测试兜底，半小时的事。
    这是**为了避免以后变来变去而现在就变一次**——判断依据是搬家成本随模块数线性增长，
    而当前模块数是历史最低点。

25. `cli.py` 只做参数解析与分发，跑任务的接线放进 `modes/once.py`。
    对应 pi 的 `cli.ts` → `modes/print-mode.ts`。收益不在当下（两个文件各 30 行，
    确实碎），在于加 REPL 时的形状：cli 多一个分支、modes 多一个文件，core 一行不动。
    `run_once` 的 client/model 可注入，因此接线层也能离线测——否则接错线要打真实 API 才发现
    （已补 4 条测试）。

26. `compaction.py` 暂不拆成目录，设触发条件而不是拍脑袋。
    pi 的 `core/compaction/` 是目录，但其 compaction.ts 到 893 行才拆；
    pai 现在 189 行，拆成 4 个 50 行文件是过度设计，更糟的是会在还不知道
    find_cut_point / summarize 长什么样时就把边界钉死。
    触发条件：等 summarize 落地（预计 +300 行）再拆，拆法照 pi。已登记进 TODO.md。

27. 开发记录进 `docs/dev/`，`docs/` 根目录留给面向用户的文档。
    pi 的 `docs/` 是 30 篇用户文档（quickstart / settings / skills…），开发记录不在里面。
    pai 此前把 decisions/devlog/STATUS/reviews 全放 `docs/`，仓库公开后来访者找不到「怎么用」。
    历史 devlog 条目正文里的旧路径**保持原样未改写**——那是记录，不是导航。

28. `test.sh` 统一入口，默认 `-m "not llm"`。
    学 pi 顶层的 test.sh。把「不花钱」做成默认路径，而不是要求人记住加参数——
    与第 23 条同一个原则：花钱的副作用不能是默认行为。

## pai-viz · 架构可视化（2026-08-03）

29. 每次 `/api/structure` 请求起子进程收集，而不是 server 常驻进程里直接 import。
    动机是 viz 的核心承诺：加一个 `@tool`、刷新浏览器就能看到。常驻进程的模块缓存
    会把工具注册表冻在启动时刻，reload 方案（importlib.reload）在装饰器注册模式下
    边界情况很多。子进程新解释器每次 ~100-200ms，本地开发无感；附赠隔离性——
    用户代码写出语法错误时子进程报错、页面红条显示 stderr，server 不死，
    顺手当编译检查用。

30. 前端零依赖手写单页，不用框架也不用 mermaid。备选是 FastAPI+mermaid（代码最少）
    或 pydeps 依赖图（全自动）。否决理由：mermaid 样式控制力弱、依赖 CDN 离线不可用；
    pydeps 画的是 import 关系不是概念架构。pai 全项目的立意是「从零手写、每层都理解」，
    可视化工具没道理例外。卡片+一层 SVG 贝塞尔连线足以复刻仪表盘效果。
    踩过的坑：SVG 连线的 stroke 用 presentation attribute 写 `var(--line)` 多数浏览器
    不解析（回退成 none，线整体隐形），必须用 CSS 规则 `#wires path { stroke: ... }`——
    最终整支评审在浏览器实测前抓住了它。

31. 阶段状态解析 STATUS.md「模块现状」表，不另造状态文件；pipeline 概念图从第一版
    就预画未来节点（compaction/permissions/streaming/memory/skills/mcp_client），
    未开始渲染为虚线灰。单一事实来源：状态本来就在 STATUS.md 手工维护，再造一份
    JSON 必然漂移。预画的收益是图 = 完整蓝图 + 实时进度，每补一个阶段图上「点亮」
    一块。防漂移的守卫：测试断言真实 STATUS.md 解析非空，且 pipeline 节点引用的
    stage key 全部能在表里找到——表格式一变、测试先红。

## 阶段 1 · P0 清障裁决（2026-08-03）

32. 「在哪下刀」也用真实 usage，把锚定法从触发判断扩展到切点计算。
    既然估算器不能信，正确的修法不是给它打补丁（补正值会随模型/协议漂移，这一点原判断没错），
    而是**换掉数据源**：pai 每步都落了真实 `prompt_tokens`，相邻两次相减即得该轮新增消息的真实成本：
    ```
    第 N 轮后新增消息的真实 token = prompt_{N+1} − (prompt_N + completion_N)
    ```
    实测验证（4 步任务）：42 / 33 / 43 token，全部为真实值而非估算。

    **粒度天然匹配**：切点只能落在轮次边界（绝不在 tool 结果上切，否则产生孤儿 tool_result），
    而真实用量也恰好只能按轮次反推——两者对齐，不需要更细的粒度。

    实现要求：loop 需保留**锚点列表** `[(message_index, real_tokens), ...]` 而非只留最新一个。
    仅最新的未锚定尾部仍用字符估算，那部分通常只有一两条消息。

    ⚠️ 前提：此法依赖 append-only 历史。压缩会改写历史，压缩后旧锚点全部作废，需清空重建
    （与 D#18 的 anchor 重置是同一件事）。

    ⚠️ 当前实际影响有限：1M 窗口下多保 1 万 token 是噪音。这条主要是把正确性做对，
    以及为将来窗口更小的模型留余地——**不是救火**。
    ⚠️ 注记（2026-08-09，R2#3）：「只切轮次边界」是比 pi **更强**的约束——pi 的
    findValidCutPoints 只排除 toolResult，显式允许劈开单轮（isSplitTurn + turnStartIndex）。
    代价：单轮超过保留预算时 pai 无法在轮内下刀，届时需要兜底方案。

33. thinking mode：默认开着，`reasoning_content` 照丢，锚不受影响——但这是**实测结论压过文档结论**。
    官方文档（refs/deepseek-api/guides/thinking_mode.md）两处硬约束：
    「思考模式默认打开，effort 默认 high」以及「携带 tools 的请求，后续必须完整回传
    `reasoning_content`，否则 API 返回 400」。而 pai 的 loop 从来不回传，却从未报过 400。
    探针实测（2026-08-03，5 组请求）：
    - 思考确实默认开：无 tools / 带 tools 都返回非空 `reasoning_content`，
      全部 session 合计 reasoning 占输出 12.5%（81/650）。**文档这条正确。**
    - 不回传 `reasoning_content` **未触发 400**，测了 3 次，含 reasoning 达 181 token 的
      重推理场景。**文档这条未复现。**
    - 锚（`prompt_N + completion_N`）不受影响：实测「下轮 prompt 增长 − completion」
      恒为 +13~+22 的小正数，与 reasoning 量（0 / 8 / 22 / 181）**完全无关**。
      若 reasoning 真的不进下轮上下文，该差值应随 reasoning 增大而变成大负数——没有发生。
    取舍：**保持现状不回传**。理由：实测安全，且回传会让 prompt 变大（服务端看来已计入，
    再传一份是重复付费）。风险：文档白纸黑字说会 400，说明这是**未解释的偏差**，
    可能随模型/版本变化。
    ⚠️ 监控条件：一旦出现 reasoning 相关的 400，立即改为回传——已登记 TODO。
    机制未查明：为何丢弃了 reasoning 而下轮 prompt 仍按含 reasoning 的量增长，
    目前只有实测事实，没有解释。**不要在面试里编造机制解释。**

34. 压缩是否成功，**只认压缩后第一次真实 usage 回传**，不认估算值。
    背景（评审 R#7）：`compact()` 重置 `anchor=None` 后，下一次 `context_tokens` 退化为
    纯估算（实测 -33%），而那正是熔断器最需要准确读数的时刻——它要判断
    「压完还超线吗，要不要再压一次」。
    **低估方向在这里格外危险**：压缩后的上下文会**看起来比实际小**，
    于是误判「压成功了」而放行，下一轮直接爆窗口；
    或反过来在真的没压下去时以为压下去了，把熔断器该拦的循环放过去。
    裁决：
      - `compact()` 后不立即判断成败，只标记「等待压缩后首次真实读数」；
      - 熔断器的失败计数以**压缩后第一次 API 响应的真实 prompt_tokens** 为准；
      - 该读数仍超阈值 → 计一次失败；连续失败达上限（CC 用 3）→ 停止自动压缩。
    这条与第 18 条同源：**能拿到真实值的地方绝不用估算**——
    区别只在第 18 条管稳态、这条管压缩后的空窗期。
    ⚠️ 代价：熔断判断被推迟一个来回。可接受，因为替代方案（信估算）会在最关键处出错。

## 体系 · 知识库与功能档案（2026-08-09）

35. 学习知识放仓库内 knowledge/，不建独立知识库仓库。备选：独立知识库仓库
    （pai 与面试准备都引用），或全部沉淀进面试准备仓库。
    pi 把设计文档直接放仓库根（tui-plan.md，36KB）；anna 把 knowledge/ 放工作区内
    与任务代码同层，但工作区不是 git 仓库——「追加不改写」「基线不可再生」全靠自觉，
    是那套体系最大的单点。pai：knowledge/ 入仓，与 src/、docs/ 同层。
    理由：① 单人项目跨仓库链接是纯摩擦——笔记的核心价值是「笔记 ↔ 代码 ↔ decisions
    互链」，同仓相对路径稳定、随 git 演化；② 继承 anna「工作区即 harness」的形态，
    同时用 git 补上它的最大短板；③ 边界靠规约不靠仓库边界：knowledge/ 准入一问
    （写不出 pai 锚点不进来），面试向内容仍去面试准备仓库，两边索引互指不搬运。
    代价：本机绝对路径的外部参照对公开仓库读者是死链——集中收在 knowledge/README
    「外部参照」一节并明示，不散落进笔记正文。
    ⚠️ 补记（2026-08-09，R2#1/R2#15）：入仓的**主要**代价原文写反了方向——死链是外人
    点不开，真风险是**公开仓库会带出雇主工作区内容**（anna 的内部路径/任务名/事故细节）。
    处置：anna 笔记去标识化（只留可迁移方法论），雇主路径从全库清除；披露边界的最终
    确认在 TODO（R2#1 残余）。
    裁决（2026-08-09，用户）：**不入库**——knowledge/anna/ 与当日评审文件进 .gitignore，
    本地保留；代价是 gates.md 失去版本控制备份（其头部与 TODO 已如实声明）。另两处自我削弱如实记：外部参照本身就是跨仓库链接
    （摩擦换了方向而非消除）；「互指」目前单向（反向在 TODO）。

36. 功能档案按目录组织：docs/dev/features/<NN>-<名称>/，superpowers 的 spec/plan 迁入
    对应功能目录（原 docs/superpowers/ 撤销）。备选：继续按类型集中放（specs/ + plans/），
    或只在 STATUS 加一张功能状态表。
    pi 按类型组织（设计文档放仓库根，如 tui-plan.md）；anna 按任务目录组织
    （tasks/NN + 档案四件套 + evidence，本条的直接原型）；CC 无此层。
    pai：按功能目录，但**全局单一入口不拆**——TODO 仍是唯一待办入口（档案「遗留问题」
    每条必须同步登记）、decisions 仍是唯一取舍记录（够格的取舍进本文件并与档案互链）、
    devlog 仍是唯一时间线（条目短写 + 链接档案）。
    理由：①回看一个功能的完整故事线（需求→方案→选择→结果→测试→问题）此前要横跨
    4 个按类型组织的文件自己拼；②devlog/decisions 承载细节会无限变长——细节住档案，
    全局文件回归索引与时间线；③状态只在档案头部维护一份，消灭多处维护。
    代价：多一层目录与文件。防臃肿：小修不立档案；档案指针优先，能链接绝不抄正文。
    ⚠️ 注记（2026-08-09，用户裁决）：devlog **下沉**——之后功能开发的详细日志写
    features/<NN>/devlog.md，全局 devlog 只记里程碑一行 + 链接；decisions 维持全局
    （理由：D#n 编号被全库引用、取舍常跨功能、全局检索对比是其核心价值）。
    既有历史条目一律冻结原样，不迁移。

