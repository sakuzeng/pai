# 设计决策记录

每个阶段完成后追加一节：pi/Claude Code 怎么做的 → pai 怎么做的 → 为什么。这是面试话术的直接来源。

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

19. 那 1.5 倍的系统偏差**不修**。
    分工定了之后它就无害了：
      「该不该压」→ context_tokens（真实值锚定，绝对值准）
      「在哪下刀」→ estimate_tokens（只需相对准；均匀偏差同时作用于所有消息，切点几乎不动）
    去补「每条 25 token 框架开销」「schema ×1.5」是在给一个不需要准的地方增加复杂度，
    且这些补正值随模型/协议版本漂移，等于给自己埋维护债。
    唯一仍靠纯估算的场合是首次请求（无锚可依），那时上下文才几百 token，离阈值差几个数量级。

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
      3) 真实 API 测试改为显式选择加入（第 22 条）。

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
