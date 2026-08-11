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
| 37 | 拍平 vs 原样发实测裁决：默认 flat 维持；raw 缓存优势待大轨迹复测（evidence 归档） |
| 38 | 阶段 2「core 不动」作废：core 可动但只加不改语义 |
| 39 | 事件流用 dataclass 扁平联合，砍掉不流式就没意义的 turn_end |
| 40 | 工具的运行期上下文走进程级注入点，不进函数签名 |
| 41 | 中断按「回填已取消结果」实现，不抛异常 |
| 42 | 指令进第一条 user 消息（照官方），代价是必须自己实现压缩后重注入 |
| 43 | 只读 PAI.md 三层，不读 AGENTS.md/CLAUDE.md |
| 44 | 项目标识用全路径连字符 slug，接受与 CC 同款的碰撞 |
| 45 | 会话文件名保留时间戳前缀，不用 CC 的纯 uuid |
| 46 | 权限求值顺序 deny → ask → allow，特异性不参与排序 |
| 47 | 没有规则命中时默认 allow——有安全代价，交付后自我复议 |
| 48 | ask 无真人时降级为 deny 而不是 allow |
| 49 | 匹配语义下放给工具，签名加 MatchContext（偏离已拍板 spec，待复议） |
| 50 | ~~hook 崩溃/超时绝不阻断工作~~ **已复议，见 54** |
| 51 | 默认兜底从常量改为工作目录边界函数（复议 47） |
| 52 | bash 不参与目录边界、兜底 ask——与 CC 的明确差异 |
| 53 | 权限模式四态；dontAsk 与「无真人」合流 |
| 54 | hook fail-closed，但只覆盖「没拿到判定」（复议 50） |
| 55 | 记忆索引是**投影**不是账本——从 frontmatter 重建，代价是手编被覆盖 |
| 56 | 召回照 CC 做框架侧查询，但加空目录短路 + 连续失败停用 + usage 计进熔断 |
| 57 | 一次流式响应装配成**一条** assistant 消息——拒绝 CC 的 block 级记录 |
| 58 | usage「每块都看」而不是照文档认 `include_usage`（实测与文档不符） |
| 59 | 权限**按批前置**判定，偏离 CC 的「执行时判」 |
| 60 | TUI 走**方案 A 底部活动区**，不持有整份文档——推翻方案 B 的理由是「清了画不回来」 |
| 61 | 对话框**不抢焦点**：用户在打字就压住，停手 1500ms 才弹（照 CC 源码，推翻 pai 自己凭文档推出的判断） |
| 62 | 会变的依赖一律传**可变持有者**而非值——同一个坑在 feature 12 里连撞两次 |
| 63 | TUI 的字形**不用 emoji**，且用测试把物理约束卡死 |

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

37. 拍平 vs 原样发实测裁决（2026-08-09，关闭 D#12/D#16 悬案）：**默认 flat（拍平）维持**。
    实测（各 3 次真实 DeepSeek 摘要请求，原始数据归档
    features/02-20260803-compaction/evidence/20260809-拍平vs原样发实测/）：
    - 不听话率 **0/6**，两种模式全部输出真摘要——CC 自陈的「原样发有百分之几误解成
      继续干活」在 DeepSeek 上未复现（样本小、轨迹短，不能下强结论，如实记）。
    - prompt 成本 flat 520 vs raw 507 token，短轨迹上无差；**raw 的真正优势
      （复用主对话缓存前缀，50 倍价差）本实验设计测不出**——实验是独立会话，
      两种模式都只吃到自己前一轮的缓存（flat 512 / raw 384 hit）。理论账保留。
    - 质量：flat 三次全是结构完整的交接摘要；raw 波动大（completion 345~1671，
      raw-run1 仅 406 字符偏简略）。
    裁决理由：不听话顾虑未现但 flat 结构更稳；成本差在当前量级可忽略；raw 留作
    大轨迹真实压缩场景的复测选项（届时缓存优势才兑现，值得重开）。
    顺带首个实测参照：摘要 completion ≤ 1671（含 reasoning），
    `reserve_tokens=16384` 充裕（STATUS 缺陷 3 从「无实测依据」改「有实测参照，维持」）。


38. **roadmap 阶段 2「core 不动」正式作废**（2026-08-10，feature 05 拍板）：
    原文写「`modes/interactive.py` 纯 REPL 先行（core 不动）」，但同一段的范围又写
    「事件流定型 + steering/followUp 双队列」——后者必然要改 `loop.on_event` 的签名，
    用户拍板中断做到「工具执行中途可断」又必然要改 `tools/shell.py`。两者不可兼得。
    改为：**core 可动，但只加不改语义**——新参数一律 keyword-only 且默认值维持旧行为
    （沿用压缩接线的先例），唯一的破坏性改动是 `on_event` 的参数类型，用户已知情选择。
    对照：pi 把可变性全部收进 `AgentLoopConfig` 钩子（K source-walks/pi-agentloop.md），
    pai 用「keyword-only + 默认 None」达到同样效果而不引入配置对象——工具少时更直接。

39. **事件流用 frozen dataclass 扁平联合，且砍掉 `turn_end`/`message_update`**
    （2026-08-10，feature 05 task 1）：pi 的 `AgentEvent` 有三层生命周期
    （agent/turn/message）共 9 种事件，pai 只取 8 种并去掉 `turn_end` 与 `message_update`。
    理由：**不流式时 `turn_end` 与 `AssistantMessage` 是同一时刻的同一信息**，
    设了只是为了凑 pi 的形状；`message_update` 更是纯流式产物。阶段 5 真出现
    「一轮内多次增量」时再补——那时它们才承载新信息。
    代价如实记：阶段 5 补事件时，REPL/状态行的渲染层要跟着改一次。

40. **工具需要的运行期上下文走进程级注入点，不进函数签名**（2026-08-10，
    feature 05 task 3/6）：`@tool` 从函数签名生成 schema（架构约束「schema 与代码同源」），
    所以给 `bash` 加个 `interrupt_flag` 参数、给 `ask_user_question` 加个 `asker` 参数，
    **模型就会看见一个它不该填的参数**。取舍：本仓库其他地方一律依赖注入，这里破例用
    模块级单例（`interrupt.set_current` / `ask.set_asker`），代价是全局状态——
    靠「`current()` 永不返回 None」+ 测试用 contextmanager 复位兜住。
    这是「schema 与代码同源」这条约束的**直接代价**，不是偷懒；真要消除它得让 Tool
    携带运行期上下文对象，那是比全局状态更大的改动。

41. **中断按「剩余工具各回填一条已取消」实现，不抛异常**（2026-08-10，feature 05 task 5）：
    直觉做法是让中断抛异常一路弹出 loop。但 D#2 已经定下「`tool_call_id` 配对由 loop
    唯一负责，任何分支都回填 tool 消息」——一轮 3 个 tool_calls 只回 1 条，
    下一轮请求就是 400（R#11 有真实复现）。所以中断是**数据路径**不是异常路径：
    置标志 → 剩余 tool_calls 各回一条「(已取消，用户中断)」→ 在下一次 create() 前干净返回。
    同理 REPL 里干活期间的 SIGINT 只置标志不抛 KeyboardInterrupt——抛了会把
    已完成的工作连同栈一起丢掉，而官方对中断的承诺恰恰是「保留迄今完成的工作」
    （K claude-docs/interactive-mode.md）。

42. **分层指令进「system 之后的第一条 user 消息」，不塞进 system**（2026-08-10，
    feature 06 拍板问 1）：CC 就是这么做的，并自陈「因此没有严格遵守的保证」。
    被否掉的 A 方案（拼进 system）其实有三个工程好处：**压缩后自动存活**
    （`compact()` 重建的就是 `[system]+[摘要]+[保留尾部]`）、system 是稳定前缀对缓存友好
    （实测命中率 91.6%，50 倍价差）、遵守度更高。
    **选 B 是为了把 CC 的真实机制连同它的代价完整实现一遍**——代价就是
    「压缩后必须从磁盘重读并重注入指令」，不做就是长会话里 PAI.md 静默失效。
    实现要点：重注入**重新调用 loader**（= 从磁盘重读，官方原话），不复用启动时的字符串；
    `test_reinjected_instructions_are_re_read_from_disk` 中途改文件来区分这两者——
    其余测试对二者表现一致，只有这条分辨得出。

43. **只读 `PAI.md` / `PAI.local.md` / `~/.pai/PAI.md`，不读 `AGENTS.md`、`CLAUDE.md`**
    （2026-08-10，feature 06 拍板问 2）：通行的 `AGENTS.md` 看似能白捡「零配置可用」，
    但它写的是**给开发这个仓库的 AI 的规矩**（先写测试跑红、留痕、档案门禁）——
    pai 自己当 agent 跑起来读到，会把开发规约当成任务指令。
    官方对 AGENTS.md 的处理也不是直接读，而是让用户写 `@AGENTS.md` 导入；
    pai 同样保留这条路，主动权在用户手里。`test_agents_md_is_not_read` 钉死这条，
    否则以后有人「顺手加上」。

44. **项目标识用「全路径连字符」slug，并接受与 CC 同款的碰撞**（2026-08-10，feature 08）：
    原先是 `sha1(路径)[:16]`，用户翻 `~/.pai` 时问「`2b0a92ef14633a56` 又是什么鬼」——
    哈希谁也认不出来。改成 CC 的做法：git 仓库根的绝对路径把 `/` 换成 `-`
    （`-Users-sakuzeng-improve-coding-agent-projects-pai`）。
    **已知代价**：`/a-b/c` 与 `/a/b-c` 撞成同一个 slug。**不修**——CC 就是这么拼的，
    一旦加转义目录名就不再与 CC 同形，而「可读、与 CC 一致」正是本需求的诉求；
    真实概率极低。做法是**把这条缺陷钉成测试**（`test_known_slug_collision_is_documented`），
    让将来想「顺手修好」的人先撞见它并读到理由——TODO 是给想找活干的人看的，
    测试是拦住想改东西的人的。

45. **会话文件名保留时间戳前缀，不用 CC 的纯 uuid**（2026-08-10，feature 08）：
    CC 用 `<sessionId>.jsonl`（如 `0f256d8a-643a-....jsonl`），唯一性优先。
    pai 用 `%Y%m%d-%H%M%S-<短 id>.jsonl`。理由：08 之后会话集中存到
    `~/.pai/projects/<slug>/sessions/`，一个目录里会攒下几十个会话，
    **按时间排序比认 uuid 容易得多**；短 id 已足够去碰撞（顺带关掉 R#15：
    原先精确到秒，同秒建两个 SessionLog 会写同一个文件）。
    这是本仓库少数几处**刻意不与 CC 一致**的地方，理由是使用场景不同而非做不到。


## 阶段 4 · 权限（2026-08-10，feature 07）

46. **求值顺序 `deny → ask → allow`，桶内按书写顺序取第一个命中，特异性不参与排序**
    （2026-08-10，feature 07 task 1）。备选：按特异性排序（更特异的规则赢）。
    官方语义就是前者，pai 照抄。**这条单独立项是因为它是本模块最容易被「优化」掉的地方**：
    `deny=["Bash(aws *)"]` 配 `allow=["Bash(aws s3 ls)"]` 时，
    「更特异的应该赢」听起来非常合理，而改了之后不会报错、不会变红、
    只在被人利用时才现形。处置同 D#44：**把它钉成测试**
    （`test_deny_beats_more_specific_allow`），让想改的人先撞见。
    交付时做了注入反证：把 `KINDS` 翻成 `("allow", "ask", "deny")`，4 条测试变红。

47. ~~**没有任何规则命中时的默认决策 = `allow`**~~（2026-08-10，feature 07 spec 自主判断）。
    **⚠️ 已于 2026-08-11 被 D#51 推翻**（feature 09，用户拍板）。下文保留原始记录。
    备选：默认 `ask`（白名单模式）或默认 `deny`。
    spec 阶段的理由是「与压缩、事件、记忆三次接线一致——不配置 = 行为与接线前逐字相同」。
    ⚠️ **交付后自我复议（复盘「我现在质疑什么」）：这个类比不成立。**
    那三次接线不配置的代价是「少一个优化」；这次不配置的代价是**权限层完全不存在**，
    而 STATUS 上却写着「permissions 可用」——虚假安全感比没有更危险。
    **仍不改默认值**（改是破坏性变更，且 pai 没有「只读命令免提示集合」，
    默认 `ask` 会烦到没法用），但已登记 TODO：首启时两层 settings.json 都不存在，
    应当明确告知「当前无任何权限规则，一律放行」。

48. **`ask` 命中而当前模式没有真人可问时，降级为 `deny` + 理由回填，不降级为 `allow`**
    （2026-08-10，feature 07 拍板问 1，用户拍板）。备选：降级 allow / 中止整个任务。
    降级 allow 的代价是 **ask 规则在自动化场景下等于不存在**，而自动化正是最危险的场景；
    中止整任务的代价是一条小规则废掉整个长任务。
    实现上的关键是**这个降级发生在装配层（`core/gate.py`）而不是 loop**：
    loop 收到的 Decision 只被问一句「是不是 allow」，它**不认识 ask 这个概念**。
    不这么做的话「有没有真人」这个模式差异会渗进两个模式共用的 loop。

49. **匹配语义下放给工具（拍板问 2），但 matcher 签名从 spec 定的 3 参改成 4 参**
    （2026-08-10，feature 07 task 4）。**这是对已拍板 spec 的偏离，待用户复议。**
    spec 第 2 节钉的是 `(specifier, args, require_all) -> bool`，
    而 spec 第 4 节要求路径型 specifier 的 `/` 前缀锚到**写下这条规则的设置文件**。
    两条凑不到一起：锚点是**规则的属性**，既不在 specifier 里也不在工具参数里，
    三参签名没有它的出口。实现取的是加第 4 个参数 `ctx: MatchContext(anchor, cwd, home)`。
    否掉的两条：① 权限层把 anchor 拼进 specifier 再传——要求权限层判断
    「这个 specifier 是不是路径」，正好违反拍板问 2；② 再加一个 `normalize_specifier`
    钩子——多一层机制解决同一件事。
    代价：`Tool.matches()` 的 `ctx` 有默认值，所以只有**自定义 matcher** 受影响（5 处）。

50. ~~**hook 自身崩溃或超时一律按「非阻断」处理**~~（2026-08-10，feature 07 task 6）。
    **⚠️ 已于 2026-08-11 被 D#54 复议修正**（feature 09，用户拍板）。下文保留原始记录。
    备选：挂了就拦（fail-closed）。`guards/design_gate.py` 结尾那个
    `except: sys.exit(0)` 是同一条铁律的先例。
    **如实记安全代价：这意味着杀掉 hook 进程就能绕过它。**
    仍这么选，是因为 fail-closed 的代价更大——一个写错的钩子会让整个 agent 罢工，
    而人在那种情况下通常直接把钩子全关掉，等于一道门禁都不剩。
    配套的一条实现约束：`run_pre_tool_use` 返回 `None` 表示「**没意见**」而非「放行」，
    两者混同的话，一个崩掉的 hook 就等于一次静默放行。


## 阶段 4 补课 · 工作目录边界与权限模式（2026-08-11，feature 09）

51. **默认兜底从常量改为「工作目录边界函数」**（2026-08-11，feature 09 拍板问 1，
    用户选 A）。**这条推翻 D#47。**备选：抄 pi 的诚实（保持 allow + 明写免责声明）、
    只对写生效。
    起因是用户实测质疑：「我在当前目录下运行 pai，照理来说上级目录下应该是不能看的」——
    当时 `read_file(~/.ssh/id_rsa)`、`write_file(../别人的项目/x.py)`、
    `bash(rm -rf ~/Documents)` **全部 allow**。
    根因不是参数没调对，是**结构性差异**：CC 的 `checkReadPermissionForTool` 里
    根本没有「默认决策常量」这个东西，兜底是 `in_working_dir ? allow : ask`
    （`filesystem.ts` 第 6 步与第 12 步），写路径兜底则一律 ask、**没有**目录放行那一步。
    pai 照抄了 CC 的引擎（三态、求值顺序、匹配下放）却把兜底抄成常量——
    D#47 当初的类比「与压缩/事件/记忆三次接线一致，不配置 = 行为不变」不成立：
    那三次不配置的代价是少一个优化，这次是**权限层完全不存在**。
    **明确接受的代价**：破坏性变更，once 模式被限制在启动 cwd 内只读
    （越界 ask 按 D#48 降级 deny）。显式配 `"defaultDecision": "allow"` 可退回旧行为，
    有测试钉住。

52. **`bash` 不参与目录边界，兜底 `ask`**（2026-08-11，feature 09 拍板问 2，
    用户先选「不做边界」、后改选「兜底 ask」）。备选：朴素路径提取（正则找 `../`）、
    bash 也做边界。
    CC 靠 `bashClassifier`（分类器模型）判断 bash 命令碰了哪些路径，pai 明确不做分类器。
    做朴素路径提取会误判（`echo "../"`、`grep -r /etc` 全中）且防不住 `$(...)` 与变量拼接
    ——**给出「看起来防住了」的错觉，正是 pi 警告的那种半吊子**。
    **与 CC 的明确差异**：CC 对没有 `getPath` 的工具返回 ask 后由分类器兜底，
    pai 没有分类器，选择「不参与边界判定 + 兜底 ask」。
    实现上这是**结构性的**：bash 不声明 `get_path`/`access`，边界判定碰不到它，
    而不是权限层里一句 `if tool_name == "bash"`（后者会在加第五个工具时被照抄成新分支）。
    **洞的准确形状（交付后复盘修正）**：洞不在默认路径上（bash 默认 ask 已是最保守），
    而在**用户为了可用性必然要走的那条路上**——配了 `allow=["Bash(cat *)"]` 之后
    `cat ../../etc/passwd` 畅通无阻。已登记 TODO：应在 `/permissions` 与首启明确提示。

53. **权限模式四态：`default` / `acceptEdits` / `dontAsk` / `bypassPermissions`**
    （2026-08-11，feature 09 追加拍板）。不做 `plan`（价值主要在「产出计划→用户批准→
    自动转模式」那套交互，留 TUI 阶段）；不做 `auto`（CC 源码写死 ant-only，
    `isExternalPermissionMode` 排除 `auto`/`bubble`，外部用户拿不到，且需分类器 + 熔断器）。
    核实纠正用户两处认知：CC 界面**没有 `manual`**（是 `Default`）；
    用户感觉的「auto 不弹 ask」很可能是 `Accept edits`——四个模式共用 `⏵⏵` 符号。
    **模式不是全局开关，是插在求值链特定位置的放行条件**：`acceptEdits` 是
    `mode == acceptEdits && 是写 && 在界内`（**不免边界**，照 CC 的 `&& isInWorkingDir`）；
    `bypassPermissions` 有三条免疫（deny 规则、**用户显式配的 ask 规则**、危险路径）。
    **最容易实现错的一条**：第 3 步（显式 ask）与第 7 步（兜底 ask）都产出 `kind=="ask"`，
    但前者 bypass 也要问、后者 bypass 放行；混同的后果是二选一——bypass 等于没有，
    或 bypass 变成万能开关无视用户写的规则。
    **`dontAsk` 与「无真人」合流**：D#48 那个「once 无真人时 ask→deny」的特例，
    其实就是 CC 的 `dontAsk` 模式。合流后 once 的默认模式即 `dontAsk`，
    同一段代码从「特例」变成「模式」只差一个名字。
    ⚠️ **交付后自我质疑**：合流的副作用是 once 下用户显式配 `defaultMode: "default"`
    被**静默忽略**（没真人，照样降级）。行为对但不该静默，已登记 TODO。

54. **hook 改 fail-closed，但只覆盖「pai 侧没拿到判定」**（2026-08-11，
    feature 09 拍板问 3，用户选「分场景改」）。**这条复议修正 D#50。**
    D#50 当初的理由是「`design_gate.py` 已有先例」，那是**场景错配**：
    `design_gate.py` 挡的是「AI 改自己源码时没走流程」，失败代价是流程没走到；
    运行期权限 hook 挡的是「agent 动用户的机器」，失败代价是安全事故。
    调研佐证：pi（`emitToolCall` 不捕获异常，上层转拦截）与 CC（分类器解析失败即 block）
    **两个独立实现都选了 fail-closed**。
    **但实现时收敛了范围**：子进程语境下「崩溃」有歧义——脚本 `raise` 与主动 `exit 1`
    退出码都是 1，分不出来；而 CC 协议明确把「其他退出码」定义为脚本*能够表达*的状态
    （我跑完了、有问题、别拦）。一并改成 deny 就是改协议本身。
    最终：**超时 / 起不来（126、127、OSError）→ deny**；其他退出码维持非阻断。
    与 pi 的差异如实记成测试：pi 的钩子是进程内函数，**区分得出**「没跑完」，
    pai 的是子进程，只有退出码可看。
    `guards/design_gate.py` 保持 fail-open，并加测试钉住不被「统一一下」误改。

55. **记忆索引 `MEMORY.md` 是投影，不是账本**（2026-08-11，feature 10 拍板问 2，
    用户选「投影」并认下代价）。
    **CC 怎么做**：模型自己写记忆文件的 frontmatter，**也自己**往 `MEMORY.md` 加一行；
    两份文案（frontmatter 的 `description` 给召回器读、索引行的钩子给主模型读）
    互相独立，框架不做一致性检查——本机实测样本证实两串文字确实不同。
    **pai 怎么做**：`remember` 落盘后**重新渲染**整个 `MEMORY.md`
    （`render_index(scan_memories(dir))`），并且**读侧根本不读盘上那份**，
    每次现扫现渲染进上下文。
    **为什么**：召回层本来就要写扫描代码（每文件前 30 行取 frontmatter），
    索引重建只是同一个扫描结果的第二个消费者，**零新增机制**；
    而账本方案要写四类补丁（新增/描述变更/文件被删/去重），其中「文件被删」
    只有全量扫描才知道——账本迟早也要扫描。旧实现的去重还是子串匹配
    （`if f"{name}.md" in existing`），文件多起来后 `a.md` 会在 `xa.md` 那行误命中。
    **代价（用户明确认下）**：手编 `MEMORY.md` 会在下次 `remember` 时被覆盖，
    所以文件头写明它是生成物。CC 没有这个代价，因为它的索引本来就是模型手写的。
    **连带的一条**：相对时间（「47 天前」）**只渲染进上下文、不写进文件**——
    它是渲染时刻的函数，落盘就会腐坏，而「三个月前的记忆在文件里写着『今天』」
    正是新鲜度这个特性要防的东西。

56. **召回照 CC 做框架侧查询，但补三处 pai 特有的成本约束**（2026-08-11，
    feature 10 拍板问 1，用户原话「按cc的来」）。
    **候选**：甲不做（只把索引做厚，靠模型自己 `read_file`）／乙做成 `recall_memory` 工具
    （不额外打模型，但「模型压根没想起来」时和 `read_file` 一样叫不动）／
    丙照 CC 每轮打一次便宜模型选文件。**选丙**——甲乙都在绕开走读里唯一识别出的机制落差
    （06 复盘悬案：pai 少的是一整层机制，不是实现质量）。
    **连带锁死两条**：粒度必须是**一事一文件**（否则 description 与 mtime 都只是半真半假）；
    召回块**入 messages** 跨轮留存（正因留存才需要 `alreadySurfaced` 去重）。
    **比 CC 多的三处**，都是 pai 的预算文化逼出来的：
    ① 记忆目录为空 / 全部已注入 → **不发请求**；
    ② 侧查询的 usage **计进 `max_total_tokens` 熔断账**（同压缩那次，`loop.py`）；
    ③ 连续 3 次失败 → 本会话停用。CC 是「失败返回 `[]` 不阻断」，
    在 pai 那等于每轮白打一次请求（同 D#14 压缩熔断的理由）。
    **少的一处**：`recentTools` 去噪（CC 会区分「正在用的工具，用法文档不选、
    但坑与警告要选」）没做，记忆量还没到需要它的规模，已登记 TODO。
    **不押在 provider 上的一处**：CC 用 JSON schema 强制输出，
    DeepSeek 兼容层的严格 `json_schema` 未必支持，所以只用 `json_object`，
    正确性靠防御式解析 + 文件名白名单兜底。
    ⚠️ **交付当天真跑校正（用户授权花钱）**：`json_object` 被接受，但抄 CC 的另外两个
    前提**在 DeepSeek 上不成立**，当时召回真实环境 100% 失效且完全静默——
    ① `max_tokens=256` 是给**不推理**的 Sonnet 档定的，而 `deepseek-v4-flash` 的
    `reasoning_tokens` 计进该上限（实测同 query 思考量 218/112/1941，差 17 倍），
    预算被吃光后 `content` 变空串 → 改 4096；
    ② 白名单要求**逐字相等**，而模型把 manifest 行的 `[type]` 装饰一起抄了回来 →
    改成「在回复里找已知文件名、取最长匹配」，白名单仍然说了算。
    连带把「解析不出来」与「明确选了空列表」在解析层分开（前者才是故障），并加
    `RecallFailed` 事件。**教训**：抄来的常数带着它原本的模型假设，前提不会自己跟过来。
    见 [K concepts/reasoning-models-max-tokens.md](../../knowledge/concepts/reasoning-models-max-tokens.md)。

57. **一次流式响应装配成一条 assistant 消息**（2026-08-11，feature 11 Task 1）。

    **CC 怎么做**：走 Anthropic 协议，流式并行工具调用时**每个 content block 变成一条
    独立的 assistant 记录**，它们共享同一个 `message.id`。代价是必须再写一个
    `getAssistantMessageId`：从后往前找「最后一次真实 usage」当锚点时，会锚在同一响应的
    最后一个分片上，而该分片的 usage 其实覆盖了前面几个分片 → 前面那些被重复计入。
    于是找到锚之后还要继续往前挪，直到同一响应的第一个分片。

    **pai 怎么做**：`streaming.assemble` 把整个 chunk 序列装成**一条**消息，
    形状与非流式的 `response.choices[0].message` 兼容，loop 那一侧一个字都不用改。

    **理由**：那个补丁存在的唯一原因是 CC 的**建模选择**，不是流式的固有代价。
    保持一对一，补丁就永远不需要。这条推翻了 TODO 里挂了很久的「接流式前必修：
    并行工具调用会让 usage 重复累加」——**它的前提在 OpenAI 兼容协议下不成立**
    （实测：2 个并行 tool_calls、1 份 usage，流式与非流式一致）。

    **反过来仍要警惕**：若将来为了「边流边显示」把一次响应拆成多条记录，
    就是亲手复制这个 bug。判据写在 [K concepts/streaming-tool-calls.md](../../knowledge/concepts/streaming-tool-calls.md) 第四节：
    **问「一次 API 响应在我的数据结构里变成了几条记录」**。

58. **usage 的取法是「每块都看，最后一个非空的赢」，不照文档认 `include_usage`**
    （2026-08-11，feature 11 Task 1，实测证据见
    [features/11 evidence](features/11-20260811-streaming/evidence/20260811-流式探针/说明.md)）。

    **文档怎么说**（DeepSeek 官方，`refs/deepseek-api/api/create-completion.md`）：
    设 `stream_options={"include_usage": true}` 时，在 `[DONE]` 之前多传**一个额外的块**，
    该块 `usage` 有值而 **`choices` 始终是空数组**。

    **实测是什么**（三方对照：不传 / `False` / `True`）：`include_usage` 是**空操作**，
    usage 一律挂在带 `finish_reason` 的**末块**上，该块 `choices` **从来不为空**，
    那个「额外块」从未出现。

    **pai 怎么做**：不管 `choices` 空不空，**每块都看一眼 `chunk.usage`**，最后一个非空的赢。

    **理由**：OpenAI 生态最常见的写法是 `if not chunk.choices: usage = chunk.usage`——
    在 DeepSeek 上那个分支**永不触发**，usage 恒为 None，而 usage 是预算熔断与上下文锚点的
    唯一输入，两者会一起**静默**失效。反过来假设「usage 一定在末块」也不安全（标准 OpenAI
    会给独立块）。「每块都看」是唯一同时吃得下两种形状的写法。

59. **权限判定按批前置，不在执行时判**（2026-08-11，feature 11 Task 5）。

    **CC 怎么做**：权限在 `runToolUse` 内部判，与工具执行交织。

    **pai 怎么做**：每批开始前**串行判完该批所有工具的权限**，只把 allow 的派发给调度器。

    **理由两条**：① CC 的做法下，同批两个并行工具可能同时要求问真人——正好撞上
    TODO 里「asker 与 REPL 抢同一个输入流」那条已知缺陷；按批前置让它结构上不存在。
    ② **语义变化被限制在批内**：并发批里全是只读工具，不改变彼此的判定前提；
    批与批之间仍保持「先执行前一批、再判定后一批」，所以「工具 A 建了目录、B 才写得进去」
    这类依赖不受影响。

    **前提被钉进代码**：调度器要求 `read_only` **且** `concurrency_safe` 都为真才并发
    （`scheduler._parallelizable`）。只看 `concurrency_safe` 的话，将来出现一个
    「并发安全但会写」的工具，理由②会**静默失效**——所以前提放在代码里，不放在文档里。


60. **TUI 走「底部活动区」，pai 不持有整份文档**（2026-08-11，feature 12 拍板问 1）。

    **pi 怎么做**：main-screen 每帧渲染**整份文档**并做行数组 diff；宽度一变就
    `\x1b[2J\x1b[H\x1b[3J` 全量重绘——**连 scrollback 一起清掉**。

    **CC 怎么做**：主形态其实同 pai——已提交的消息进 scrollback 就不再重渲染
    （`utils/staticRender.tsx` 的注释：渲染成字符串再 print），只有可选的 fullscreen
    模式才是全帧。

    **pai 怎么做**：只接管屏幕底部的 dock（活动区/队列区/输入行/状态行），
    上面的历史打出去就归终端所有。`DockRenderer` **绝不发 `2J`/`3J`**。

    **理由**：pi 敢清 scrollback，是因为它持有整份文档、清完能重画回来；
    **pai 不持有，清掉就画不回来**。这条是方案 B 被否的全部理由——
    不是「B 更贵」，是「B 的前提 pai 不满足，除非连带把持有整份文档也做了」。

    **代价（拍板时已知并接受）**：transcript 内不能滚动/搜索、工具结果不能原地展开、
    不能点击。用户 2026-08-11 真跑后提出这三条需求，追下去正是同一个约束，
    已另立档案 [features/13-alt-screen](features/13-20260811-alt-screen/README.md) 复议。

61. **对话框不抢焦点：用户在打字就压住它**（2026-08-11，feature 12 拍板问 3）。

    **pai 原先的判断**：TODO 里写着「真正的解法是模态输入——问题框接管输入焦点，
    CC 的 AskUserQuestion 就是这么做的」。那是**从官方文档推的**。

    **源码里 CC 实际怎么做**：`REPL.tsx` 的 `getFocusedInputDialog()` 第三行就是
    `if (isPromptInputActive) return undefined`——输入框非空即**压住所有对话框**，
    停手 1500ms 才放行，被压期间输入框下方显式显示 `Waiting for permission…`。
    仲裁**偏袒正在打字的人**，方向与 pai 原先的判断相反。

    **pai 怎么做**：照抄。`InputArbiter` 一处仲裁、每个消费者一个 `is_active`。

    **理由**：这条修正的价值不在语义本身，在**它是怎么被发现的**——
    原判断来自文档推理，被源码走读推翻。与 D#58（`include_usage` 实测与文档不符）
    是同一类：**凡是「官方大概是这么做的」，都要落到源码或实测才算数。**

62. **会变的依赖一律传可变持有者，不传值**（2026-08-11，feature 12 T5 + 交付后修复）。

    **原先怎么写**：`make_before_tool_call(..., mode="default", asker=fn)`——
    装配期把值烤进闭包。

    **撞了两次**：① 权限模式：`/mode` 与 shift+tab 运行时改不动（T5 动工前发现）；
    ② 问答通道：TUI 起来后权限框仍走 REPL 的老 asker 去调 `input()`，
    而 stdin 已在 raw mode，**整个程序死住，Ctrl+C/D 都退不出去**（用户真跑发现）。

    **pai 怎么做**：`PermissionModeState` 与 `AskerRef` 都可调用/可取，
    gate **每次判定现取**；同时保留「也能传值」以免破坏 once 的调用路径。

    **理由与更值钱的那条**：第二次撞坑时，代码里那个模式我一天前刚修过一遍。
    修第一个时想的是「模式要能切」，而不是「装配期捕获这个模式还有几处」。
    → 沉淀为 [K concepts/injection-seams.md](../../knowledge/concepts/injection-seams.md)：
    **修掉一个装配期捕获的 bug 之后，立刻把同一个装配函数的其余参数逐个过一遍。**

63. **TUI 的字形不用 emoji，且用测试把物理约束卡死**（2026-08-11，feature 12 T9）。

    **起因**：答案前缀用了 `🤖`，用户终端上渲染成方块（字体缺字）。

    **pai 怎么做**：界面自己的字形一律用文本呈现的符号（`●` `✳` `└` `─` `❯` `⧗`），
    并加一条测试遍历所有字形，断言「码位 < U+1F000」且「不是宽字符」且「显示宽度为 1」。

    **理由**：这看着像审美问题，**其实是物理问题**——emoji 的宽度在各终端不一致，
    只要终端与应用差一列，整行光标定位就错，症状与「终端替你折行」同源。
    **审美判断不好测，物理约束好测**，那就把能测的那部分测住。
