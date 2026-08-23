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
| 50 | ~~hook 崩溃/超时绝不阻断工作~~ 已复议，见 54 |
| 51 | 默认兜底从常量改为工作目录边界函数（复议 47） |
| 52 | bash 不参与目录边界、兜底 ask——与 CC 的明确差异 |
| 53 | 权限模式四态；dontAsk 与「无真人」合流 |
| 54 | hook fail-closed，但只覆盖「没拿到判定」（复议 50） |
| 55 | 记忆索引是投影不是账本——从 frontmatter 重建，代价是手编被覆盖 |
| 56 | 召回照 CC 做框架侧查询，但加空目录短路 + 连续失败停用 + usage 计进熔断 |
| 57 | 一次流式响应装配成一条 assistant 消息——拒绝 CC 的 block 级记录 |
| 58 | usage「每块都看」而不是照文档认 `include_usage`（实测与文档不符） |
| 59 | 权限按批前置判定，偏离 CC 的「执行时判」 |
| 60 | TUI 走方案 A 底部活动区，不持有整份文档——推翻方案 B 的理由是「清了画不回来」 |
| 61 | 对话框不抢焦点：用户在打字就压住，停手 1500ms 才弹（照 CC 源码，推翻 pai 自己凭文档推出的判断） |
| 62 | 会变的依赖一律传可变持有者而非值——同一个坑在 feature 12 里连撞两次 |
| 63 | TUI 的字形不用 emoji，且用测试把物理约束卡死 |
| 64 | 备用屏常驻但不接管鼠标——先要屏幕，不要鼠标（拿走鼠标 = 拿走终端原生的选中复制） |
| 65 | 退出备用屏不回吐完整文档，只打一行会话提示（照 CC 不照 pi），代价是欠下 `--resume` |
| 66 | 绝不重发 `?1049h`、绝不 `2J`——实测硬约束，推翻了 CC 源码里的一处注释 |
| 67 | 鼠标只发 1002（不照抄 CC 的 1003）——它多买的 hover 是非目标，而代价是真的 |
| 68 | 排队消息：单队列取自 CC、第二出口取自 pi——两家各拿一半，拒的那一半也写明 |
| 69 | 参照源加第三家 deepseek-harness（平级），但证据等级分三档且架构不可对拿 |

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

    pi（`pi-mono/packages/coding-agent/src/core/compaction/utils.ts:109`）：
    `serializeConversation()` 把 N 条消息压成一段文本，塞进一条 user 消息发出去。
    源码注释：`// Serialize conversation to text so model doesn't try to continue it`。
    附带截断 tool 结果到 2000 字符（`TOOL_RESULT_MAX_CHARS`）。

    CC（`claude-code-v2.1.88/src/services/compact/compact.ts:441`）：
    不拍平。`messages: messagesToSummarize` 原样发，末尾追加一条 user 消息装摘要指令。
    整个 services/compact/ 目录没有 serialize 函数。

    CC 为什么敢原样发：prompt cache。`compact.ts:1179` 注释写明用 forked agent
    复用主对话的缓存前缀（system / tools / model / messages prefix 必须逐字节一致），
    feature flag `tengu_compact_cache_prefix` 默认 true。为保住缓存，他们甚至刻意不设
    maxOutputTokens——设了会改 thinking 配置导致 cache key 不匹配。

    CC 的代价是可量化的：不拍平就挡不住"模型接着干活"，只能靠 prompt 硬掰
    （`prompt.ts:19` 的 NO_TOOLS_PREAMBLE，含"工具调用会被拒绝，你会失败"的威胁）。
    其源码注释自陈：在较新的模型上，仍有百分之几的概率会去调工具而非总结，白白浪费掉唯一一轮；
    较旧的模型上这个比例低两个数量级。

    pai 选拍平的理由：pai 走 OpenAI 兼容协议打 DeepSeek，且 loop 当前是单次任务
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
    - refs/deepseek-api/guides/kv_cache.md：硬盘缓存对所有用户默认开启，无需改代码；
      前缀单元在「用户输入结束位置」与「模型输出结束位置」落盘。agent loop 每步重发递增
      前缀，天然命中——这正是 CC「原样发 + 末尾追加指令」能命中缓存的机制，在 DeepSeek 同样成立。
    - 用户 2026-08-02 全天用量实测：输入缓存命中率 84.7%（23,424 / 27,640）。
    价格差（refs/deepseek-api/quick_start/pricing.md，deepseek-v4-flash）：
      缓存命中 0.02 元/M vs 未命中 1 元/M —— 50 倍，不是此前估的 10 倍。
    重算摘要请求成本：
      拍平（pi）  0.64× token × 1 元    = 0.64  ← 新前缀，必然全部未命中
      原样发（CC）1.0×  token × 0.02 元 = 0.02  ← 匹配已落盘前缀单元
    CC 的做法在 DeepSeek 上便宜约 32 倍。
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
    而是换掉估算的作用位置：
      context_tokens = 上一步真实 prompt_tokens + 该步真实 completion_tokens
                     + 估算(此后新增的 tool 结果)
    加 completion_tokens 是因为紧随其后那条 assistant 消息的真实 token 数就是它——白送的精确值。
    于是 1.5 倍的偏差只乘在几十个 token 的尾部上。实测误差从 -33% 降到 -1.3%。
    pi 同样这么做（compaction.ts:189「using the last assistant usage when available」），
    这也解释了 pi 为何敢用粗糙的 chars/4：它根本不靠估算撑全局。

19. ~~那 1.5 倍的系统偏差不修。分工定了之后它就无害了：「该不该压」→ context_tokens
    （真实值锚定，绝对值准）；「在哪下刀」→ estimate_tokens（只需相对准；均匀偏差同时作用于
    所有消息，切点几乎不动）。去补「每条 25 token 框架开销」「schema ×1.5」是在给一个不需要准的
    地方增加复杂度，且这些补正值随模型/协议版本漂移，等于给自己埋维护债。~~

    【2026-08-03 推翻，原文保留为记录】 上面划掉的论证有两处错，外部评审指出了一处，
    复核时又发现一处更严重的。结论（不修估算器）碰巧仍然成立，但理由完全换了。

    错误一（评审 R#4 指出）：「均匀偏差不影响切点」只在切点按比例定义时成立。
    pi 的 findCutPoint（`compaction.ts:417`）是从后往前累加估算值，与绝对预算比较：
    ```ts
    accumulatedTokens += messageTokens;            // estimateTokens 估出来的
    if (accumulatedTokens >= keepRecentTokens) {   // 与常数 20000 比
    ```
    低估 1.5 倍 = 累加到「估算的 2 万」时实际已保约 3 万，挤占 reserve 余量。
    只有「保最近 30% 的消息」这类比例式切法，分子分母同缩放才会抵消。

    错误二（复核实测发现，比错误一更致命）：偏差根本不均匀。
    用相邻两次 usage 反推真实段成本，对照字符估算：
    | 段 | 估算 | 真实 | 倍数 |
    |---|---|---|---|
    | `已写入 usage_check.txt（17 字符）` | ~10 | 42 | 4.2× |
    | `alpha\nbeta\ngamma\n` | ~6 | 33 | 5.5× |
    每条消息约 25-30 token 的 chat template 框架开销是固定量，占比随消息变短而暴涨：
    短 tool 结果低估 4-5 倍，几千字符的长消息只低估约 2%。
    「均匀」这个前提本身就不成立——而切点附近往往正是短 tool 结果。

20. usage 记录挂 `type` 而非 `role`，且绝不挂到 message 上。
    多一个字段就改变请求前缀，而 DeepSeek 硬盘缓存要求「完整匹配缓存前缀单元」
    （refs/deepseek-api/guides/kv_cache.md）——污染消息等于把命中率打到 0。
    附带好处：estimate_tokens 对无 role 记录返回 0、serialize_conversation 直接跳过，
    usage 记录天然不会被误当成消息。有测试钉住（test_usage_never_leaks_into_messages_sent_to_api）。

## 阶段 1 · 烧钱防线（2026-08-03）

21. 用量预算做成 loop 层的熔断，而不是指望平台限额——因为平台根本没有。
    查证 refs/deepseek-api/quick_start/rate_limit.md：DeepSeek 只提供并发限速
    （v4-flash 2500、v4-pro 500，按账号计、与 API Key 无关），没有任何消费限额或配额功能。
    另有 `GET /user/balance` 可查余额（api/get-user-balance.md），但那是只读的，挡不住花钱。
    所以三层防线，从硬到软：
      1) 账户只充小额——唯一无法被代码 bug 绕过的保障，没有的钱花不掉；
      2) loop 层 `max_total_tokens` 熔断（本条）；
      3) 真实 API 测试改为显式选择加入（第 23 条）。

22. 预算检查放在「发下一次请求之前」，不放在收到响应之后。
    请求一旦发出就无法撤销，检查点放在循环开头意味着超支上限被钳制在一次请求内。
    代价是最后一次请求必然超出预算一点点（实测：上限 1500，实际停在 1695）——
    这是可接受的，因为唯一的替代方案是预估下次请求的开销再决定发不发，
    而预估本身就有 1.5 倍误差（decisions 第 18 条），拿一个不准的数去省一次请求不划算。
    provider 不回 usage 时预算自动失效，此时仅靠 max_steps 兜底——已知取舍，有测试钉住。

23. 真实 API 测试必须显式选择加入，光有 key 不够。
    原实现是「有 DEEPSEEK_API_KEY 就自动跑 llm 标记的测试」。后果：任何配好 .env 的人
    跑一次 pytest 就静默产生 API 费用——外部评审时评审者本人就中招了（见 reviews 第 2 条）。
    改为双重条件：有 key 且 `PAI_RUN_LLM_TESTS=1`。
    原则：花钱的副作用永远不能是默认行为。

## 阶段 1 · 框架对齐 pi（2026-08-03）

24. 提前把 `core/`（业务核心）与 `modes/`（交互形态）分开，趁代码只有 587 行。
    pi 的分法：`src/core/`（tools / compaction / session-manager / system-prompt…）
    与 `src/modes/`（interactive TUI / print-mode / rpc）。核心不关心自己被谁调用。
    pai 路线图里有 REPL，等 REPL 写完再分就是一次大搬家 + 所有 import 改一遍；
    现在搬只动 32 个 import 点，有 52 个测试兜底，半小时的事。
    这是为了避免以后变来变去而现在就变一次——判断依据是搬家成本随模块数线性增长，
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
    历史 devlog 条目正文里的旧路径保持原样未改写——那是记录，不是导航。

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
    而是换掉数据源：pai 每步都落了真实 `prompt_tokens`，相邻两次相减即得该轮新增消息的真实成本：
    ```
    第 N 轮后新增消息的真实 token = prompt_{N+1} − (prompt_N + completion_N)
    ```
    实测验证（4 步任务）：42 / 33 / 43 token，全部为真实值而非估算。

    粒度天然匹配：切点只能落在轮次边界（绝不在 tool 结果上切，否则产生孤儿 tool_result），
    而真实用量也恰好只能按轮次反推——两者对齐，不需要更细的粒度。

    实现要求：loop 需保留锚点列表 `[(message_index, real_tokens), ...]` 而非只留最新一个。
    仅最新的未锚定尾部仍用字符估算，那部分通常只有一两条消息。

    ⚠️ 前提：此法依赖 append-only 历史。压缩会改写历史，压缩后旧锚点全部作废，需清空重建
    （与 D#18 的 anchor 重置是同一件事）。

    ⚠️ 当前实际影响有限：1M 窗口下多保 1 万 token 是噪音。这条主要是把正确性做对，
    以及为将来窗口更小的模型留余地——不是救火。
    ⚠️ 注记（2026-08-09，R2#3）：「只切轮次边界」是比 pi 更强的约束——pi 的
    findValidCutPoints 只排除 toolResult，显式允许劈开单轮（isSplitTurn + turnStartIndex）。
    代价：单轮超过保留预算时 pai 无法在轮内下刀，届时需要兜底方案。

33. thinking mode：默认开着，`reasoning_content` 照丢，锚不受影响——但这是实测结论压过文档结论。
    官方文档（refs/deepseek-api/guides/thinking_mode.md）两处硬约束：
    「思考模式默认打开，effort 默认 high」以及「携带 tools 的请求，后续必须完整回传
    `reasoning_content`，否则 API 返回 400」。而 pai 的 loop 从来不回传，却从未报过 400。
    探针实测（2026-08-03，5 组请求）：
    - 思考确实默认开：无 tools / 带 tools 都返回非空 `reasoning_content`，
      全部 session 合计 reasoning 占输出 12.5%（81/650）。文档这条正确。
    - 不回传 `reasoning_content` 未触发 400，测了 3 次，含 reasoning 达 181 token 的
      重推理场景。文档这条未复现。
    - 锚（`prompt_N + completion_N`）不受影响：实测「下轮 prompt 增长 − completion」
      恒为 +13~+22 的小正数，与 reasoning 量（0 / 8 / 22 / 181）完全无关。
      若 reasoning 真的不进下轮上下文，该差值应随 reasoning 增大而变成大负数——没有发生。
    取舍：保持现状不回传。理由：实测安全，且回传会让 prompt 变大（服务端看来已计入，
    再传一份是重复付费）。风险：文档白纸黑字说会 400，说明这是未解释的偏差，
    可能随模型/版本变化。
    ⚠️ 监控条件：一旦出现 reasoning 相关的 400，立即改为回传——已登记 TODO。
    机制未查明：为何丢弃了 reasoning 而下轮 prompt 仍按含 reasoning 的量增长，
    目前只有实测事实，没有解释。不要在面试里编造机制解释。

34. 压缩是否成功，只认压缩后第一次真实 usage 回传，不认估算值。
    背景（评审 R#7）：`compact()` 重置 `anchor=None` 后，下一次 `context_tokens` 退化为
    纯估算（实测 -33%），而那正是熔断器最需要准确读数的时刻——它要判断
    「压完还超线吗，要不要再压一次」。
    低估方向在这里格外危险：压缩后的上下文会看起来比实际小，
    于是误判「压成功了」而放行，下一轮直接爆窗口；
    或反过来在真的没压下去时以为压下去了，把熔断器该拦的循环放过去。
    裁决：
      - `compact()` 后不立即判断成败，只标记「等待压缩后首次真实读数」；
      - 熔断器的失败计数以压缩后第一次 API 响应的真实 prompt_tokens 为准；
      - 该读数仍超阈值 → 计一次失败；连续失败达上限（CC 用 3）→ 停止自动压缩。
    这条与第 18 条同源：能拿到真实值的地方绝不用估算——
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
    ⚠️ 补记（2026-08-09，R2#1/R2#15）：入仓的主要代价原文写反了方向——死链是外人
    点不开，真风险是公开仓库会带出雇主工作区内容（anna 的内部路径/任务名/事故细节）。
    处置：anna 笔记去标识化（只留可迁移方法论），雇主路径从全库清除；披露边界的最终
    确认在 TODO（R2#1 残余）。
    裁决（2026-08-09，用户）：不入库——knowledge/anna/ 与当日评审文件进 .gitignore，
    本地保留；代价是 gates.md 失去版本控制备份（其头部与 TODO 已如实声明）。另两处自我削弱如实记：外部参照本身就是跨仓库链接
    （摩擦换了方向而非消除）；「互指」目前单向（反向在 TODO）。

36. 功能档案按目录组织：docs/dev/features/<NN>-<名称>/，superpowers 的 spec/plan 迁入
    对应功能目录（原 docs/superpowers/ 撤销）。备选：继续按类型集中放（specs/ + plans/），
    或只在 STATUS 加一张功能状态表。
    pi 按类型组织（设计文档放仓库根，如 tui-plan.md）；anna 按任务目录组织
    （tasks/NN + 档案四件套 + evidence，本条的直接原型）；CC 无此层。
    pai：按功能目录，但全局单一入口不拆——TODO 仍是唯一待办入口（档案「遗留问题」
    每条必须同步登记）、decisions 仍是唯一取舍记录（够格的取舍进本文件并与档案互链）、
    devlog 仍是唯一时间线（条目短写 + 链接档案）。
    理由：①回看一个功能的完整故事线（需求→方案→选择→结果→测试→问题）此前要横跨
    4 个按类型组织的文件自己拼；②devlog/decisions 承载细节会无限变长——细节住档案，
    全局文件回归索引与时间线；③状态只在档案头部维护一份，消灭多处维护。
    代价：多一层目录与文件。防臃肿：小修不立档案；档案指针优先，能链接绝不抄正文。
    ⚠️ 注记（2026-08-09，用户裁决）：devlog 下沉——之后功能开发的详细日志写
    features/<NN>/devlog.md，全局 devlog 只记里程碑一行 + 链接；decisions 维持全局
    （理由：D#n 编号被全库引用、取舍常跨功能、全局检索对比是其核心价值）。
    既有历史条目一律冻结原样，不迁移。

37. 拍平 vs 原样发实测裁决（2026-08-09，关闭 D#12/D#16 悬案）：默认 flat（拍平）维持。
    实测（各 3 次真实 DeepSeek 摘要请求，原始数据归档
    features/02-20260803-compaction/evidence/20260809-拍平vs原样发实测/）：
    - 不听话率 0/6，两种模式全部输出真摘要——CC 自陈的「原样发有百分之几误解成
      继续干活」在 DeepSeek 上未复现（样本小、轨迹短，不能下强结论，如实记）。
    - prompt 成本 flat 520 vs raw 507 token，短轨迹上无差；raw 的真正优势
      （复用主对话缓存前缀，50 倍价差）本实验设计测不出——实验是独立会话，
      两种模式都只吃到自己前一轮的缓存（flat 512 / raw 384 hit）。理论账保留。
    - 质量：flat 三次全是结构完整的交接摘要；raw 波动大（completion 345~1671，
      raw-run1 仅 406 字符偏简略）。
    裁决理由：不听话顾虑未现但 flat 结构更稳；成本差在当前量级可忽略；raw 留作
    大轨迹真实压缩场景的复测选项（届时缓存优势才兑现，值得重开）。
    顺带首个实测参照：摘要 completion ≤ 1671（含 reasoning），
    `reserve_tokens=16384` 充裕（STATUS 缺陷 3 从「无实测依据」改「有实测参照，维持」）。


38. roadmap 阶段 2「core 不动」正式作废（2026-08-10，feature 05 拍板）：
    原文写「`modes/interactive.py` 纯 REPL 先行（core 不动）」，但同一段的范围又写
    「事件流定型 + steering/followUp 双队列」——后者必然要改 `loop.on_event` 的签名，
    用户拍板中断做到「工具执行中途可断」又必然要改 `tools/shell.py`。两者不可兼得。
    改为：core 可动，但只加不改语义——新参数一律 keyword-only 且默认值维持旧行为
    （沿用压缩接线的先例），唯一的破坏性改动是 `on_event` 的参数类型，用户已知情选择。
    对照：pi 把可变性全部收进 `AgentLoopConfig` 钩子（K loop/pi-agentloop.md），
    pai 用「keyword-only + 默认 None」达到同样效果而不引入配置对象——工具少时更直接。

39. 事件流用 frozen dataclass 扁平联合，且砍掉 `turn_end`/`message_update`
    （2026-08-10，feature 05 task 1）：pi 的 `AgentEvent` 有三层生命周期
    （agent/turn/message）共 9 种事件，pai 只取 8 种并去掉 `turn_end` 与 `message_update`。
    理由：不流式时 `turn_end` 与 `AssistantMessage` 是同一时刻的同一信息，
    设了只是为了凑 pi 的形状；`message_update` 更是纯流式产物。阶段 5 真出现
    「一轮内多次增量」时再补——那时它们才承载新信息。
    代价如实记：阶段 5 补事件时，REPL/状态行的渲染层要跟着改一次。

40. 工具需要的运行期上下文走进程级注入点，不进函数签名（2026-08-10，
    feature 05 task 3/6）：`@tool` 从函数签名生成 schema（架构约束「schema 与代码同源」），
    所以给 `bash` 加个 `interrupt_flag` 参数、给 `ask_user_question` 加个 `asker` 参数，
    模型就会看见一个它不该填的参数。取舍：本仓库其他地方一律依赖注入，这里破例用
    模块级单例（`interrupt.set_current` / `ask.set_asker`），代价是全局状态——
    靠「`current()` 永不返回 None」+ 测试用 contextmanager 复位兜住。
    这是「schema 与代码同源」这条约束的直接代价，不是偷懒；真要消除它得让 Tool
    携带运行期上下文对象，那是比全局状态更大的改动。

41. 中断按「剩余工具各回填一条已取消」实现，不抛异常（2026-08-10，feature 05 task 5）：
    直觉做法是让中断抛异常一路弹出 loop。但 D#2 已经定下「`tool_call_id` 配对由 loop
    唯一负责，任何分支都回填 tool 消息」——一轮 3 个 tool_calls 只回 1 条，
    下一轮请求就是 400（R#11 有真实复现）。所以中断是数据路径不是异常路径：
    置标志 → 剩余 tool_calls 各回一条「(已取消，用户中断)」→ 在下一次 create() 前干净返回。
    同理 REPL 里干活期间的 SIGINT 只置标志不抛 KeyboardInterrupt——抛了会把
    已完成的工作连同栈一起丢掉，而官方对中断的承诺恰恰是「保留迄今完成的工作」
    （K tui/claude-interactive-mode.md）。

42. 分层指令进「system 之后的第一条 user 消息」，不塞进 system（2026-08-10，
    feature 06 拍板问 1）：CC 就是这么做的，并自陈「因此没有严格遵守的保证」。
    被否掉的 A 方案（拼进 system）其实有三个工程好处：压缩后自动存活
    （`compact()` 重建的就是 `[system]+[摘要]+[保留尾部]`）、system 是稳定前缀对缓存友好
    （实测命中率 91.6%，50 倍价差）、遵守度更高。
    选 B 是为了把 CC 的真实机制连同它的代价完整实现一遍——代价就是
    「压缩后必须从磁盘重读并重注入指令」，不做就是长会话里 PAI.md 静默失效。
    实现要点：重注入重新调用 loader（= 从磁盘重读，官方原话），不复用启动时的字符串；
    `test_reinjected_instructions_are_re_read_from_disk` 中途改文件来区分这两者——
    其余测试对二者表现一致，只有这条分辨得出。

43. 只读 `PAI.md` / `PAI.local.md` / `~/.pai/PAI.md`，不读 `AGENTS.md`、`CLAUDE.md`
    （2026-08-10，feature 06 拍板问 2）：通行的 `AGENTS.md` 看似能白捡「零配置可用」，
    但它写的是给开发这个仓库的 AI 的规矩（先写测试跑红、留痕、档案门禁）——
    pai 自己当 agent 跑起来读到，会把开发规约当成任务指令。
    官方对 AGENTS.md 的处理也不是直接读，而是让用户写 `@AGENTS.md` 导入；
    pai 同样保留这条路，主动权在用户手里。`test_agents_md_is_not_read` 钉死这条，
    否则以后有人「顺手加上」。

44. 项目标识用「全路径连字符」slug，并接受与 CC 同款的碰撞（2026-08-10，feature 08）：
    原先是 `sha1(路径)[:16]`，用户翻 `~/.pai` 时问「`2b0a92ef14633a56` 又是什么鬼」——
    哈希谁也认不出来。改成 CC 的做法：git 仓库根的绝对路径把 `/` 换成 `-`
    （`-Users-sakuzeng-improve-coding-agent-projects-pai`）。
    已知代价：`/a-b/c` 与 `/a/b-c` 撞成同一个 slug。不修——CC 就是这么拼的，
    一旦加转义目录名就不再与 CC 同形，而「可读、与 CC 一致」正是本需求的诉求；
    真实概率极低。做法是把这条缺陷钉成测试（`test_known_slug_collision_is_documented`），
    让将来想「顺手修好」的人先撞见它并读到理由——TODO 是给想找活干的人看的，
    测试是拦住想改东西的人的。

45. 会话文件名保留时间戳前缀，不用 CC 的纯 uuid（2026-08-10，feature 08）：
    CC 用 `<sessionId>.jsonl`（如 `0f256d8a-643a-....jsonl`），唯一性优先。
    pai 用 `%Y%m%d-%H%M%S-<短 id>.jsonl`。理由：08 之后会话集中存到
    `~/.pai/projects/<slug>/sessions/`，一个目录里会攒下几十个会话，
    按时间排序比认 uuid 容易得多；短 id 已足够去碰撞（顺带关掉 R#15：
    原先精确到秒，同秒建两个 SessionLog 会写同一个文件）。
    这是本仓库少数几处刻意不与 CC 一致的地方，理由是使用场景不同而非做不到。


## 阶段 4 · 权限（2026-08-10，feature 07）

46. 求值顺序 `deny → ask → allow`，桶内按书写顺序取第一个命中，特异性不参与排序
    （2026-08-10，feature 07 task 1）。备选：按特异性排序（更特异的规则赢）。
    官方语义就是前者，pai 照抄。这条单独立项是因为它是本模块最容易被「优化」掉的地方：
    `deny=["Bash(aws *)"]` 配 `allow=["Bash(aws s3 ls)"]` 时，
    「更特异的应该赢」听起来非常合理，而改了之后不会报错、不会变红、
    只在被人利用时才现形。处置同 D#44：把它钉成测试
    （`test_deny_beats_more_specific_allow`），让想改的人先撞见。
    交付时做了注入反证：把 `KINDS` 翻成 `("allow", "ask", "deny")`，4 条测试变红。

47. ~~没有任何规则命中时的默认决策 = `allow`~~（2026-08-10，feature 07 spec 自主判断）。
    ⚠️ 已于 2026-08-11 被 D#51 推翻（feature 09，用户拍板）。下文保留原始记录。
    备选：默认 `ask`（白名单模式）或默认 `deny`。
    spec 阶段的理由是「与压缩、事件、记忆三次接线一致——不配置 = 行为与接线前逐字相同」。
    ⚠️ 交付后自我复议（复盘「我现在质疑什么」）：这个类比不成立。
    那三次接线不配置的代价是「少一个优化」；这次不配置的代价是权限层完全不存在，
    而 STATUS 上却写着「permissions 可用」——虚假安全感比没有更危险。
    仍不改默认值（改是破坏性变更，且 pai 没有「只读命令免提示集合」，
    默认 `ask` 会烦到没法用），但已登记 TODO：首启时两层 settings.json 都不存在，
    应当明确告知「当前无任何权限规则，一律放行」。

48. `ask` 命中而当前模式没有真人可问时，降级为 `deny` + 理由回填，不降级为 `allow`
    （2026-08-10，feature 07 拍板问 1，用户拍板）。备选：降级 allow / 中止整个任务。
    降级 allow 的代价是 ask 规则在自动化场景下等于不存在，而自动化正是最危险的场景；
    中止整任务的代价是一条小规则废掉整个长任务。
    实现上的关键是这个降级发生在装配层（`core/gate.py`）而不是 loop：
    loop 收到的 Decision 只被问一句「是不是 allow」，它不认识 ask 这个概念。
    不这么做的话「有没有真人」这个模式差异会渗进两个模式共用的 loop。

49. 匹配语义下放给工具（拍板问 2），但 matcher 签名从 spec 定的 3 参改成 4 参
    （2026-08-10，feature 07 task 4）。这是对已拍板 spec 的偏离，待用户复议。
    spec 第 2 节钉的是 `(specifier, args, require_all) -> bool`，
    而 spec 第 4 节要求路径型 specifier 的 `/` 前缀锚到写下这条规则的设置文件。
    两条凑不到一起：锚点是规则的属性，既不在 specifier 里也不在工具参数里，
    三参签名没有它的出口。实现取的是加第 4 个参数 `ctx: MatchContext(anchor, cwd, home)`。
    否掉的两条：① 权限层把 anchor 拼进 specifier 再传——要求权限层判断
    「这个 specifier 是不是路径」，正好违反拍板问 2；② 再加一个 `normalize_specifier`
    钩子——多一层机制解决同一件事。
    代价：`Tool.matches()` 的 `ctx` 有默认值，所以只有自定义 matcher 受影响（5 处）。

50. ~~hook 自身崩溃或超时一律按「非阻断」处理~~（2026-08-10，feature 07 task 6）。
    ⚠️ 已于 2026-08-11 被 D#54 复议修正（feature 09，用户拍板）。下文保留原始记录。
    备选：挂了就拦（fail-closed）。`guards/design_gate.py` 结尾那个
    `except: sys.exit(0)` 是同一条铁律的先例。
    如实记安全代价：这意味着杀掉 hook 进程就能绕过它。
    仍这么选，是因为 fail-closed 的代价更大——一个写错的钩子会让整个 agent 罢工，
    而人在那种情况下通常直接把钩子全关掉，等于一道门禁都不剩。
    配套的一条实现约束：`run_pre_tool_use` 返回 `None` 表示「没意见」而非「放行」，
    两者混同的话，一个崩掉的 hook 就等于一次静默放行。


## 阶段 4 补课 · 工作目录边界与权限模式（2026-08-11，feature 09）

51. 默认兜底从常量改为「工作目录边界函数」（2026-08-11，feature 09 拍板问 1，
    用户选 A）。这条推翻 D#47。备选：抄 pi 的诚实（保持 allow + 明写免责声明）、
    只对写生效。
    起因是用户实测质疑：「我在当前目录下运行 pai，照理来说上级目录下应该是不能看的」——
    当时 `read_file(~/.ssh/id_rsa)`、`write_file(../别人的项目/x.py)`、
    `bash(rm -rf ~/Documents)` 全部 allow。
    根因不是参数没调对，是结构性差异：CC 的 `checkReadPermissionForTool` 里
    根本没有「默认决策常量」这个东西，兜底是 `in_working_dir ? allow : ask`
    （`filesystem.ts` 第 6 步与第 12 步），写路径兜底则一律 ask、没有目录放行那一步。
    pai 照抄了 CC 的引擎（三态、求值顺序、匹配下放）却把兜底抄成常量——
    D#47 当初的类比「与压缩/事件/记忆三次接线一致，不配置 = 行为不变」不成立：
    那三次不配置的代价是少一个优化，这次是权限层完全不存在。
    明确接受的代价：破坏性变更，once 模式被限制在启动 cwd 内只读
    （越界 ask 按 D#48 降级 deny）。显式配 `"defaultDecision": "allow"` 可退回旧行为，
    有测试钉住。

52. `bash` 不参与目录边界，兜底 `ask`（2026-08-11，feature 09 拍板问 2，
    用户先选「不做边界」、后改选「兜底 ask」）。备选：朴素路径提取（正则找 `../`）、
    bash 也做边界。
    CC 靠 `bashClassifier`（分类器模型）判断 bash 命令碰了哪些路径，pai 明确不做分类器。
    做朴素路径提取会误判（`echo "../"`、`grep -r /etc` 全中）且防不住 `$(...)` 与变量拼接
    ——给出「看起来防住了」的错觉，正是 pi 警告的那种半吊子。
    与 CC 的明确差异：CC 对没有 `getPath` 的工具返回 ask 后由分类器兜底，
    pai 没有分类器，选择「不参与边界判定 + 兜底 ask」。
    实现上这是结构性的：bash 不声明 `get_path`/`access`，边界判定碰不到它，
    而不是权限层里一句 `if tool_name == "bash"`（后者会在加第五个工具时被照抄成新分支）。
    洞的准确形状（交付后复盘修正）：洞不在默认路径上（bash 默认 ask 已是最保守），
    而在用户为了可用性必然要走的那条路上——配了 `allow=["Bash(cat *)"]` 之后
    `cat ../../etc/passwd` 畅通无阻。已登记 TODO：应在 `/permissions` 与首启明确提示。

53. 权限模式四态：`default` / `acceptEdits` / `dontAsk` / `bypassPermissions`
    （2026-08-11，feature 09 追加拍板）。不做 `plan`（价值主要在「产出计划→用户批准→
    自动转模式」那套交互，留 TUI 阶段）；不做 `auto`（CC 源码写死 ant-only，
    `isExternalPermissionMode` 排除 `auto`/`bubble`，外部用户拿不到，且需分类器 + 熔断器）。
    核实纠正用户两处认知：CC 界面没有 `manual`（是 `Default`）；
    用户感觉的「auto 不弹 ask」很可能是 `Accept edits`——四个模式共用 `⏵⏵` 符号。
    模式不是全局开关，是插在求值链特定位置的放行条件：`acceptEdits` 是
    `mode == acceptEdits && 是写 && 在界内`（不免边界，照 CC 的 `&& isInWorkingDir`）；
    `bypassPermissions` 有三条免疫（deny 规则、用户显式配的 ask 规则、危险路径）。
    最容易实现错的一条：第 3 步（显式 ask）与第 7 步（兜底 ask）都产出 `kind=="ask"`，
    但前者 bypass 也要问、后者 bypass 放行；混同的后果是二选一——bypass 等于没有，
    或 bypass 变成万能开关无视用户写的规则。
    `dontAsk` 与「无真人」合流：D#48 那个「once 无真人时 ask→deny」的特例，
    其实就是 CC 的 `dontAsk` 模式。合流后 once 的默认模式即 `dontAsk`，
    同一段代码从「特例」变成「模式」只差一个名字。
    ⚠️ 交付后自我质疑：合流的副作用是 once 下用户显式配 `defaultMode: "default"`
    被静默忽略（没真人，照样降级）。行为对但不该静默，已登记 TODO。

54. hook 改 fail-closed，但只覆盖「pai 侧没拿到判定」（2026-08-11，
    feature 09 拍板问 3，用户选「分场景改」）。这条复议修正 D#50。
    D#50 当初的理由是「`design_gate.py` 已有先例」，那是场景错配：
    `design_gate.py` 挡的是「AI 改自己源码时没走流程」，失败代价是流程没走到；
    运行期权限 hook 挡的是「agent 动用户的机器」，失败代价是安全事故。
    调研佐证：pi（`emitToolCall` 不捕获异常，上层转拦截）与 CC（分类器解析失败即 block）
    两个独立实现都选了 fail-closed。
    但实现时收敛了范围：子进程语境下「崩溃」有歧义——脚本 `raise` 与主动 `exit 1`
    退出码都是 1，分不出来；而 CC 协议明确把「其他退出码」定义为脚本*能够表达*的状态
    （我跑完了、有问题、别拦）。一并改成 deny 就是改协议本身。
    最终：超时 / 起不来（126、127、OSError）→ deny；其他退出码维持非阻断。
    与 pi 的差异如实记成测试：pi 的钩子是进程内函数，区分得出「没跑完」，
    pai 的是子进程，只有退出码可看。
    `guards/design_gate.py` 保持 fail-open，并加测试钉住不被「统一一下」误改。

55. 记忆索引 `MEMORY.md` 是投影，不是账本（2026-08-11，feature 10 拍板问 2，
    用户选「投影」并认下代价）。
    CC 怎么做：模型自己写记忆文件的 frontmatter，也自己往 `MEMORY.md` 加一行；
    两份文案（frontmatter 的 `description` 给召回器读、索引行的钩子给主模型读）
    互相独立，框架不做一致性检查——本机实测样本证实两串文字确实不同。
    pai 怎么做：`remember` 落盘后重新渲染整个 `MEMORY.md`
    （`render_index(scan_memories(dir))`），并且读侧根本不读盘上那份，
    每次现扫现渲染进上下文。
    为什么：召回层本来就要写扫描代码（每文件前 30 行取 frontmatter），
    索引重建只是同一个扫描结果的第二个消费者，零新增机制；
    而账本方案要写四类补丁（新增/描述变更/文件被删/去重），其中「文件被删」
    只有全量扫描才知道——账本迟早也要扫描。旧实现的去重还是子串匹配
    （`if f"{name}.md" in existing`），文件多起来后 `a.md` 会在 `xa.md` 那行误命中。
    代价（用户明确认下）：手编 `MEMORY.md` 会在下次 `remember` 时被覆盖，
    所以文件头写明它是生成物。CC 没有这个代价，因为它的索引本来就是模型手写的。
    连带的一条：相对时间（「47 天前」）只渲染进上下文、不写进文件——
    它是渲染时刻的函数，落盘就会腐坏，而「三个月前的记忆在文件里写着『今天』」
    正是新鲜度这个特性要防的东西。

56. 召回照 CC 做框架侧查询，但补三处 pai 特有的成本约束（2026-08-11，
    feature 10 拍板问 1，用户原话「按cc的来」）。
    候选：甲不做（只把索引做厚，靠模型自己 `read_file`）／乙做成 `recall_memory` 工具
    （不额外打模型，但「模型压根没想起来」时和 `read_file` 一样叫不动）／
    丙照 CC 每轮打一次便宜模型选文件。选丙——甲乙都在绕开走读里唯一识别出的机制落差
    （06 复盘悬案：pai 少的是一整层机制，不是实现质量）。
    连带锁死两条：粒度必须是一事一文件（否则 description 与 mtime 都只是半真半假）；
    召回块入 messages 跨轮留存（正因留存才需要 `alreadySurfaced` 去重）。
    比 CC 多的三处，都是 pai 的预算文化逼出来的：
    ① 记忆目录为空 / 全部已注入 → 不发请求；
    ② 侧查询的 usage 计进 `max_total_tokens` 熔断账（同压缩那次，`loop.py`）；
    ③ 连续 3 次失败 → 本会话停用。CC 是「失败返回 `[]` 不阻断」，
    在 pai 那等于每轮白打一次请求（同 D#14 压缩熔断的理由）。
    少的一处：`recentTools` 去噪（CC 会区分「正在用的工具，用法文档不选、
    但坑与警告要选」）没做，记忆量还没到需要它的规模，已登记 TODO。
    不押在 provider 上的一处：CC 用 JSON schema 强制输出，
    DeepSeek 兼容层的严格 `json_schema` 未必支持，所以只用 `json_object`，
    正确性靠防御式解析 + 文件名白名单兜底。
    ⚠️ 交付当天真跑校正（用户授权花钱）：`json_object` 被接受，但抄 CC 的另外两个
    前提在 DeepSeek 上不成立，当时召回真实环境 100% 失效且完全静默——
    ① `max_tokens=256` 是给不推理的 Sonnet 档定的，而 `deepseek-v4-flash` 的
    `reasoning_tokens` 计进该上限（实测同 query 思考量 218/112/1941，差 17 倍），
    预算被吃光后 `content` 变空串 → 改 4096；
    ② 白名单要求逐字相等，而模型把 manifest 行的 `[type]` 装饰一起抄了回来 →
    改成「在回复里找已知文件名、取最长匹配」，白名单仍然说了算。
    连带把「解析不出来」与「明确选了空列表」在解析层分开（前者才是故障），并加
    `RecallFailed` 事件。教训：抄来的常数带着它原本的模型假设，前提不会自己跟过来。
    见 [K model-api/reasoning-models-max-tokens.md](../../knowledge/model-api/reasoning-models-max-tokens.md)。

57. 一次流式响应装配成一条 assistant 消息（2026-08-11，feature 11 Task 1）。

    CC 怎么做：走 Anthropic 协议，流式并行工具调用时每个 content block 变成一条
    独立的 assistant 记录，它们共享同一个 `message.id`。代价是必须再写一个
    `getAssistantMessageId`：从后往前找「最后一次真实 usage」当锚点时，会锚在同一响应的
    最后一个分片上，而该分片的 usage 其实覆盖了前面几个分片 → 前面那些被重复计入。
    于是找到锚之后还要继续往前挪，直到同一响应的第一个分片。

    pai 怎么做：`streaming.assemble` 把整个 chunk 序列装成一条消息，
    形状与非流式的 `response.choices[0].message` 兼容，loop 那一侧一个字都不用改。

    理由：那个补丁存在的唯一原因是 CC 的建模选择，不是流式的固有代价。
    保持一对一，补丁就永远不需要。这条推翻了 TODO 里挂了很久的「接流式前必修：
    并行工具调用会让 usage 重复累加」——它的前提在 OpenAI 兼容协议下不成立
    （实测：2 个并行 tool_calls、1 份 usage，流式与非流式一致）。

    反过来仍要警惕：若将来为了「边流边显示」把一次响应拆成多条记录，
    就是亲手复制这个 bug。判据写在 [K streaming/streaming-tool-calls.md](../../knowledge/streaming/streaming-tool-calls.md) 第四节：
    问「一次 API 响应在我的数据结构里变成了几条记录」。

58. usage 的取法是「每块都看，最后一个非空的赢」，不照文档认 `include_usage`
    （2026-08-11，feature 11 Task 1，实测证据见
    [features/11 evidence](features/11-20260811-streaming/evidence/20260811-流式探针/说明.md)）。

    文档怎么说（DeepSeek 官方，`refs/deepseek-api/api/create-completion.md`）：
    设 `stream_options={"include_usage": true}` 时，在 `[DONE]` 之前多传一个额外的块，
    该块 `usage` 有值而 `choices` 始终是空数组。

    实测是什么（三方对照：不传 / `False` / `True`）：`include_usage` 是空操作，
    usage 一律挂在带 `finish_reason` 的末块上，该块 `choices` 从来不为空，
    那个「额外块」从未出现。

    pai 怎么做：不管 `choices` 空不空，每块都看一眼 `chunk.usage`，最后一个非空的赢。

    理由：OpenAI 生态最常见的写法是 `if not chunk.choices: usage = chunk.usage`——
    在 DeepSeek 上那个分支永不触发，usage 恒为 None，而 usage 是预算熔断与上下文锚点的
    唯一输入，两者会一起静默失效。反过来假设「usage 一定在末块」也不安全（标准 OpenAI
    会给独立块）。「每块都看」是唯一同时吃得下两种形状的写法。

59. 权限判定按批前置，不在执行时判（2026-08-11，feature 11 Task 5）。

    CC 怎么做：权限在 `runToolUse` 内部判，与工具执行交织。

    pai 怎么做：每批开始前串行判完该批所有工具的权限，只把 allow 的派发给调度器。

    理由两条：① CC 的做法下，同批两个并行工具可能同时要求问真人——正好撞上
    TODO 里「asker 与 REPL 抢同一个输入流」那条已知缺陷；按批前置让它结构上不存在。
    ② 语义变化被限制在批内：并发批里全是只读工具，不改变彼此的判定前提；
    批与批之间仍保持「先执行前一批、再判定后一批」，所以「工具 A 建了目录、B 才写得进去」
    这类依赖不受影响。

    前提被钉进代码：调度器要求 `read_only` 且 `concurrency_safe` 都为真才并发
    （`scheduler._parallelizable`）。只看 `concurrency_safe` 的话，将来出现一个
    「并发安全但会写」的工具，理由②会静默失效——所以前提放在代码里，不放在文档里。


60. TUI 走「底部活动区」，pai 不持有整份文档（2026-08-11，feature 12 拍板问 1）。

    pi 怎么做：main-screen 每帧渲染整份文档并做行数组 diff；宽度一变就
    `\x1b[2J\x1b[H\x1b[3J` 全量重绘——连 scrollback 一起清掉。

    CC 怎么做：主形态其实同 pai——已提交的消息进 scrollback 就不再重渲染
    （`utils/staticRender.tsx` 的注释：渲染成字符串再 print），只有可选的 fullscreen
    模式才是全帧。

    pai 怎么做：只接管屏幕底部的 dock（活动区/队列区/输入行/状态行），
    上面的历史打出去就归终端所有。`DockRenderer` 绝不发 `2J`/`3J`。

    理由：pi 敢清 scrollback，是因为它持有整份文档、清完能重画回来；
    pai 不持有，清掉就画不回来。这条是方案 B 被否的全部理由——
    不是「B 更贵」，是「B 的前提 pai 不满足，除非连带把持有整份文档也做了」。

    代价（拍板时已知并接受）：transcript 内不能滚动/搜索、工具结果不能原地展开、
    不能点击。用户 2026-08-11 真跑后提出这三条需求，追下去正是同一个约束，
    已另立档案 [features/13-alt-screen](features/13-20260811-alt-screen/README.md) 复议。

61. 对话框不抢焦点：用户在打字就压住它（2026-08-11，feature 12 拍板问 3）。

    pai 原先的判断：TODO 里写着「真正的解法是模态输入——问题框接管输入焦点，
    CC 的 AskUserQuestion 就是这么做的」。那是从官方文档推的。

    源码里 CC 实际怎么做：`REPL.tsx` 的 `getFocusedInputDialog()` 第三行就是
    `if (isPromptInputActive) return undefined`——输入框非空即压住所有对话框，
    停手 1500ms 才放行，被压期间输入框下方显式显示 `Waiting for permission…`。
    仲裁偏袒正在打字的人，方向与 pai 原先的判断相反。

    pai 怎么做：照抄。`InputArbiter` 一处仲裁、每个消费者一个 `is_active`。

    理由：这条修正的价值不在语义本身，在它是怎么被发现的——
    原判断来自文档推理，被源码走读推翻。与 D#58（`include_usage` 实测与文档不符）
    是同一类：凡是「官方大概是这么做的」，都要落到源码或实测才算数。

62. 会变的依赖一律传可变持有者，不传值（2026-08-11，feature 12 T5 + 交付后修复）。

    原先怎么写：`make_before_tool_call(..., mode="default", asker=fn)`——
    装配期把值烤进闭包。

    撞了两次：① 权限模式：`/mode` 与 shift+tab 运行时改不动（T5 动工前发现）；
    ② 问答通道：TUI 起来后权限框仍走 REPL 的老 asker 去调 `input()`，
    而 stdin 已在 raw mode，整个程序死住，Ctrl+C/D 都退不出去（用户真跑发现）。

    pai 怎么做：`PermissionModeState` 与 `AskerRef` 都可调用/可取，
    gate 每次判定现取；同时保留「也能传值」以免破坏 once 的调用路径。

    理由与更值钱的那条：第二次撞坑时，代码里那个模式我一天前刚修过一遍。
    修第一个时想的是「模式要能切」，而不是「装配期捕获这个模式还有几处」。
    → 沉淀为 [K engineering/injection-seams.md](../../knowledge/engineering/injection-seams.md)：
    修掉一个装配期捕获的 bug 之后，立刻把同一个装配函数的其余参数逐个过一遍。

63. TUI 的字形不用 emoji，且用测试把物理约束卡死（2026-08-11，feature 12 T9）。

    起因：答案前缀用了 `🤖`，用户终端上渲染成方块（字体缺字）。

    pai 怎么做：界面自己的字形一律用文本呈现的符号（`●` `✳` `└` `─` `❯` `⧗`），
    并加一条测试遍历所有字形，断言「码位 < U+1F000」且「不是宽字符」且「显示宽度为 1」。

    理由：这看着像审美问题，其实是物理问题——emoji 的宽度在各终端不一致，
    只要终端与应用差一列，整行光标定位就错，症状与「终端替你折行」同源。
    审美判断不好测，物理约束好测，那就把能测的那部分测住。


## 阶段 2 复议 · 备用屏（2026-08-11，feature 13）

64. 备用屏常驻，但本轮完全不接管鼠标（2026-08-11，feature 13 拍板问 1/3）。
    备选（brainstorm 把候选重排成 2×2 之后才看得清）：甲=常驻+鼠标（CC 的 fullscreen 全开档）、
    乙=常驻+键盘、丙=只在 `^O` 时进 alt、丁=都不做。

    pi 怎么做：alt-screen 是另一个渲染器（`TuiAltScreen`），全套接管鼠标，
    并为此自己实现了选区（锚点/焦点、双击选词、拖到边缘自动滚、滚出视口的行要另存、
    软折行要拼回逻辑行、OSC 52 写剪贴板）。
    CC 怎么做：同样全套接管，但对外部用户默认关（`USER_TYPE === 'ant'` 才默认开），
    且留了三个逃生口，其中 `CLAUDE_CODE_DISABLE_MOUSE` 的注释直说动机是
    「让 tmux/kitty/终端原生的 copy-on-select 继续能用」；选区实现 917 行。
    pai 怎么做：进备用屏拿下整屏，滚动只给键盘（PgUp/PgDn/Ctrl+Home/Ctrl+End），
    一个鼠标序列都不发。

    理由：三条需求里「像新开一个窗口」只有常驻满足，而「能点」需要鼠标——
    但鼠标的价签不是「解析 SGR 1006」（那很便宜），是终端原生的拖选复制会失效，
    且失效方式是静默的（用户拖一下，什么也没发生）。
    对照之下命中测试只要 130 行（CC `hit-test.ts`）——贵的从来不是能点，是拿走鼠标。
    所以本轮把地基（每帧知道每个条目画在哪几行）建起来，鼠标单独立项，
    届时必须同时给关掉的开关。

65. 退出备用屏不回吐完整文档，只打一行会话提示（2026-08-11，feature 13 拍板问 2，
    用户质疑推翻了我的推荐）。

    pi 怎么做：退出 alt 时把整份文档以无界高度重渲染一遍打到主屏上
    （`tui-plan.md` 的 "Final document on stop"，且明写不能拿最后一帧顶替——那是裁剪过的视口）。
    CC 怎么做：不回吐。`gracefulShutdown.ts:144` 的 `printResumeHint()` 只打一行
    「怎么 resume」，且刻意先退 alt 再打，好让提示落在主屏而不是跟着备用屏一起消失。
    pai 怎么做：照 CC——打一行「会话已存 `<sessions/*.jsonl>`」。

    过程如实记：我最初推荐「重渲染完整文档」，并把它说成两家的共同做法；
    用户反问「为什么不和 cc 一样 resume 可以回到之前的会话（session 不是已经按照项目
    来进行管理了吗）」，查证后确认CC 不回吐，我把 pi 的做法当成了两家的做法。
    pi 之所以必须回吐，是因为它没有会话持久化那一层；CC 有 resume 所以不必。

    明确接受的代价：pai 两样都没有——`cli.py` 里根本没有 `--resume`。
    于是从本轮交付到 resume 落地之间，退出那一刻整段对话只剩一个 JSONL 文件，
    而 JSONL 不是给人读的。这是本轮引入的缺口（不是本轮未做的功能），
    复盘据此建议它的优先级高于「搜索」与「点击」。已登记 TODO。

66. 绝不重发 `?1049h`、绝不发 `2J`（2026-08-11，feature 13，实测裁决）。

    CC 怎么做：自相矛盾。`ink.tsx` 的 `handleResize` 注释说
    「Do NOT write ENTER_ALT_SCREEN: iTerm2 treats ?1049h as a buffer clear even when
    already in alt — that's the blank flicker」；同一文件 `reenterAltScreen()` 的
    docstring 却说「a terminal-side no-op if already in alt」。
    pai 实测（iTerm2 3.6.11 + Terminal.app 470.2，动工前反向对照）：
    重发之后光标回到 (1,1)、备用屏内容消失——前一句对，且不是 iTerm2 独有的怪癖：
    「清空」本来就是 DECSET 1049 定义的一部分。

    pai 怎么做：备用屏渲染器一个 `?1049` 都不发（进出归 `terminal.py`）；
    resize 后的「全量重绘」是逐行重写而不是先清屏——CC 的注释解释了为什么不能先擦：
    render 可能要 ~80ms，先擦的话屏幕在这段时间里是全黑的。
    两条各有一条测试钉住，e2e 另断言「整个会话里 `?1049h` 只出现一次」。

    衍生的一条更一般的：备用屏是个需要自愈的状态（vim 的 rmcup 会把你踢回主屏、
    tmux 重连/睡眠唤醒会重置模式），而自愈的两条路都被实测堵死了——
    重进会清屏、`DECRQM` 在 Terminal.app 完全不可用（问不出自己在不在 alt）。
    所以 pai 本轮不做自愈，如实登记为遗留，而不是写一个「看起来在自愈」的东西。


## 阶段 2 补 · 鼠标档位（2026-08-11，feature 16）

67. 鼠标上报只发 `1002` + `1006`，不照抄 CC 的四条（2026-08-11，
    复议了本 feature 拍板问 2，理由是交付前真跑撞出来的证据）。

    CC 怎么做：`termio/dec.ts` 的 `ENABLE_MOUSE_TRACKING` 一口气发
    `1000 + 1002 + 1003 + 1006`，注释写着「Combined: wheel + click/drag for selection + hover」。
    实测纠正它两处：① `1000/1002/1003` 是互斥单选、后设的覆盖先设的
    （features/13 evidence 第 3 条），所以 CC 实际拿到的是 1003；
    ② CC 的意图（要 hover）因此确实达成了，但机制不是「组合」。

    pai 怎么做：只发 `1002`（按下/松开 + 拖动 + 滚轮）+ `1006`（SGR 编码）。

    为什么复议：拍板时选 1003 的理由是「照抄 CC + 给将来的 hover 留路」，
    而交付前真跑给出了两条当时没有的信息——
    ① 1003 确实上报无按键移动（鼠标划过窗口就有字节流进 stdin），
    且它直接带出一个 bug：`button=35`（32|3，低两位 3 = 没有按键）被当成拖动，
    于是用户松手之后高亮还跟着鼠标走；
    ② hover 高亮本轮是非目标，多付的这份成本买不到任何东西。

    一般化的那条：照抄一个实现时，要把「它为什么这么做」一并抄过来核对——
    CC 发 1003 是因为它要 hover。目标不同，抄来的参数就不该照搬。

68. 排队消息：单队列取自 CC、第二出口取自 pi（2026-08-13，feature 18 七问拍板）。

    「用户在 agent 干活时打的字，什么时候发出去」这个问题，两家答得都不完整，
    pai 各取一半——关键是拒掉的那一半也要写下来，否则读者会以为这是照抄 CC。

    | 来源 | pai 抄的 | pai 拒的 |
    |---|---|---|
    | CC | 单队列 + 用户输入默认中途注入。`messageQueueManager.ts:122-129` 的 `enqueue()` 默认 `next`，任务通知走 `enqueuePendingNotification()` 默认 `later`，注释写明动机：*so user input is never starved by system messages*。即「人说话默认优先，机器说话默认等着」，且这个默认值有真实用户量验证过 | `next` 的退化行为。`query.ts:558` 的 `needsFollowUp` 注释是 *"the sole loop-exit signal"*，只在 `:834` 有 tool_use 时置真；模型这轮纯答话 → `:1062` `if (!needsFollowUp)` 直接 `return {reason:'completed'}`，根本走不到 `:1570` 的 mid-turn drain。那条 `next` 只能等 turn 结束由 `useQueueProcessor` 开一个新 query——CC 的 `next` 在纯答话轮次上事实上退化成 `later` |
    | pi | 第二出口：`loop.py:283` 那条「模型不发 tool_calls」的分支也查一次队列，非空就注入 + `continue`，在同一次 run 内解决。形状取自 pi 内层 while 的 `\|\| pendingMessages.length > 0`（`agent-loop.ts:174`）——队列非空就不许退出 | 双队列结构（`steeringQueue` / `followUpQueue`）。两个对象把「什么时候发」这个问题推给集成方（两条队列的模式都可配、默认都是 `one-at-a-time`），而那正是 pai 要自己答的问题 |

    pai 的形状：一条 `PendingMessageQueue` + 两个注入出口（工具结果回填后 / 模型不调工具时）。
    队列里混装两种东西——要发给模型的话，与 `/`、`!` 这类给客户端执行的命令；
    `drain(where=...)` 的谓词把后者滤掉且留在队列里，本轮结束后逐条交给 `_dispatch_command`
    （对应 CC 的 `dequeueAllMatching(predicate)` 与 `useQueueProcessor`，
    「slash 不能当文本发给模型」也是 CC 的明文规矩）。

    为什么删掉 followUp 而不是留一条显式路径（拍板问 2）：CC 的交互式用户
    根本没有「降级到 later」的手势——`later` 只给系统消息用，因为 CC 用户还有 Esc
    这条独立出口。pai 没有 Esc 那条路（中断是进程级标志 D#40，一按就是整轮结束），
    但既然默认已经是「本轮就注入」，再造一个前缀/修饰键去表达「等你干完」属于凭空发明
    ——没有参照实现，也没有证据说用户需要它。代价如实记：
    「不要打断你、干完再看」这个意图在 pai 里现在无法表达（复盘已就此立疑）。

    一般化的那条：两家做法不同时，「抄哪家」往往是伪问题——
    真正的问题是「这两家各自的做法里，哪一半是被它自己的其他约束逼出来的」。
    CC 的退化不是设计，是它单层循环 + `needsFollowUp` 唯一退出信号的副产品；
    pi 的双队列不是设计，是它把决定权推给集成方的结果。剥掉这两处约束之后，
    剩下的才是可以拿的东西。

    ---

    ⚠️ 2026-08-13 追记：上面「代价如实记」那段的论据被第三家证伪了一半，本条待复议。

    原话是「再造一个前缀/修饰键去表达『等你干完』属于凭空发明——没有参照实现，
    也没有证据说用户需要它」。加进 dsh 之后（D#69），「没有参照实现」这句不成立：
    见 K [loop/dsh-loop.md](../../knowledge/loop/dsh-loop.md) 第 7 节 ——

    | 层 | dsh 的事实 | 出处（commit `47f9438`） |
    |---|---|---|
    | 协议 | `mode: 'queue' \| 'steer'` 必填、无默认，harness 不替调用方选 | `api/sessions.schema.ts:290` |
    | UI | 忙碌时回车 = queue（等你干完），Cmd/Ctrl+Enter = steer（插话） | `submission-policy.ts:48-57` |
    | 默认 | `DEFAULT_BUSY_ENTER_BEHAVIOR = 'queue'`，且是用户可配设置项 | `submission-settings.ts:18` |

    即 dsh 不但把这个意图做成了手势，还把它设成了默认，方向与 CC/pai 相反。

    但注意别把证伪扩大：被推翻的只是「没有参照实现」这一条论据，不是本条的结论。
    CC 与 dsh 给相反默认值，各自都有前提：CC 的「人说话默认优先」立在它还有 Esc
    这条独立打断路径上；dsh 的「默认排队」立在它把两种意图都做成了手势且允许改默认上。
    pai 两者都没有。该不该改默认是一个新问题，得单独答——已登记 TODO，不在此处拍。

## 体系 · 第三参照源 deepseek-harness（2026-08-13）

69. 参照源从两家加到三家，平级；但「平级」只是准入平级，证据等级仍分三档
    （2026-08-13，用户指令：「作为和 cc 和 pi 的同级的对比学习项目」）。

    克隆位置与 pin：`~/improve/coding/agent/projects/deepseek-harness`，
    commit `47f943859bef60e4160492346772ded9b24f765a`（2026-08-13），MIT。
    7412 个入库文件，其中 2355 个 `.md`——这个比例本身就是它与另外两家最大的差别。

    为什么加：三条，缺一条我都不会主动提。
    ① 同模型厂——pai 从第一天起就打 DeepSeek 的 API，`reasoning_content` 该不该回传
    （D#33）、`include_usage` 是不是空操作（D#58）这类实测与文档不符的坑，
    dsh 是唯一一个也必须踩同一批坑的第一方实现；
    ② 唯一有第一方设计文档的一家——pi 只有源码，CC 的官方文档与反编译源码分属两处且
    互相打脸（D#61、D#66 都是源码推翻文档或反过来）。dsh 的 `docs/architecture.zh.md`、
    `agent-lifecycle`、`event-producer-consumer`、`tool-execution-pipeline`、`capability-seams`
    是作者自己写的意图，这一档 pai 此前完全没有；
    ③ 它把 pai 尚未动工的几块都成文了——`tool-catalog` / `capability-seams` /
    `defensive-patterns` / `testing` 正对 roadmap 剩下的 skills、mcp_client、evals 三阶段。

    为什么不是「照它重构」：dsh 是 Cordis 插件架构（「一切皆插件」，
    背后有篇时空可组合性的论文），pai 是单体 Python、且 D#24「core 与 modes 提前分开」
    是按学习阶段切的边界。可拿的是它对问题的切分与命名，不是它的装配方式——
    这与 D#67「照抄一个实现时要把它为什么这么做一并抄过来核对」是同一条规矩。

    三档证据等级（写进 AGENTS.md 与 roadmap，引用时必须标明是哪一档）：

    | 源 | 档 | 引用时的写法 |
    |---|---|---|
    | pi | 可读源码 | `pi packages/agent/src/...:行号` |
    | CC | 反编译源码 | 检索符号名，不记行号（行号会漂，roadmap 阶段 5 已明文） |
    | dsh | 第一方源码 + 第一方文档 | 「dsh 文档说」与「dsh 源码是」分开写，且带 commit hash |

    拒掉的三个方案：
    - 只当读物、不进 roadmap「参照」栏——那它两周后就沉底了，pai 的规矩是
      「写不出锚点的不进仓库」，反过来说进了仓库就该有锚点；
    - 给 knowledge 拆 `dsh-docs-` / `dsh-src-` 两个前缀（照 CC 的 `claude-` vs `cc-`）——
      CC 拆是因为两者出处不同且常互相打脸，dsh 的文档与源码在同一 commit 里，
      拆开只制造一个每次都要问「这算哪个」的边界；
    - 立 feature 档案——本次不动一行 `src/`，没有测试可红可绿，
      立档案会让「档案 = 一次交付」这个定义松掉。走 `docs/` 分支 + 本条 decisions。

    代价如实记：① 参照源从 2 涨到 3，每阶段前置精读的成本涨了——
    对策是 dsh 只读该阶段点名的文档，不通读（knowledge 规约 1「禁止囤积式通读」照旧）；
    ② dsh 自称开发者预览、破坏性变更在即，今天记下的结论会过期，
    所以每处引用带 commit hash；③ 它有中文第一方文档这件事最危险——
    读起来太顺，会诱人跳过「反向对照」那条固定项。feature 09 的教训是
    「精读覆盖了文档每一节，却漏掉一整层机制」，文档更好不等于可以不跑。

## 70. SIGWINCH 处理器只置标志，重画交给主循环（复议 feature 12 的「同步处理」）

feature 12 拍的是「resize 同步处理、同尺寸事件丢弃」，对齐 CC 的 `handleResize`
刻意不去抖。本轮（feature 19 拍板问 3）改掉其中「同步」那一半，**去抖那一半不动**——
两者是两件事，当时被写在同一条里。

改的理由不是风格：`handle_resize` 跑在信号处理器里，而信号会打在主线程任意
一条指令之间。`DockRenderer` 没有 `AltScreenRenderer` 那样的重入门，一帧写到
一半被插入另一帧会让字节交错、`_height`/`_cursor_offset` 被重入改写，dock 永久漂移。
更硬的一刀是主线程正处于 `sys.stdout.write` 内部时处理器再写同一 stream，
Python 的 buffered IO 会抛 `RuntimeError: reentrant call`——**它在我们自己加的
任何重入门之外**，所以「只补 DockRenderer 一个 `_drawing` 标志」这个方案结构上
只能治一半。pi 与 CC 的信号处理器同样不直接画。

代价：重画晚一个 poll 周期（≤100ms）。换掉的是一整类不可复现的崩溃。

诚实边界：`RuntimeError: reentrant call` 这条是**按源码结构推出来的，本轮没有
真的触发过它**，修完也没有真跑验证。按 pai 的证据等级，它属「推」不属「实测」。

出处：[features/19](features/19-20260819-tui-input-and-signals/README.md) 拍板问 3。

## 71. skills 的加载动作走专用 skill 工具，不走「模型自己 read」（2026-08-22，feature 25）

pi：索引给 SKILL.md 路径，模型用 read 工具自己加载——零新增工具，但 pi 文档自认
*models don't always do this*。CC：Skill 工具把正文展开进对话（inline）或丢进
fork 子 agent。dsh：专用 `skill({name})` 工具把正文作为 tool result 返回。
R4#A4 的评审定向写的是「照 pi 最小形态（零新增工具）」——动工前反向对照
（features/25 evidence）证实那只是三家之一的形态，不是共识。

pai：照 dsh 缩水——新增 `skill(name)` 工具返回 `<skill_content>` 包装的正文；
目录只给 name + description 不给路径（路径与 read 形态绑定：给了路径没有工具，
或有工具还给路径诱导绕过，都是拆开抄的错）。

理由（用户拍板，问 1 候选 B）：加载动作显式可观测——ToolStart/ToolEnd 事件、
状态行、viz、「已加载哪些」的追踪全部白拿；对服从性没有保证的模型（pai 打
DeepSeek），工具 schema 的强制力也高于 system prompt 里的一句指导语。
代价如实记：工具集混入一个框架私有动作（此前 5 个全是通用原语），且偏离
R4#A4 的字面定向——本条即为那次偏离的落点。

出处：[features/25](features/25-20260822-skills/README.md) 拍板问 1。

## 72. skills 同名冲突：项目级赢用户级（2026-08-22，feature 25）

三家三种语义：dsh 项目赢用户（rank 100 < 400）、CC 个人赢项目（理由：个人配置
是用户主动装的、更可信）、pi 先到先得（按扫描顺序）。

pai：取 dsh——`<项目>/.pai/skills/` 覆盖 `~/.pai/skills/` 的同名者。
理由（用户拍板，问 3 候选 A）：越具体越优先，与 pai 记忆分层「cwd 在后、
后来居上」的既有直觉一致；项目里检入的 skill 是给这个项目定制的，
被用户的通用版盖掉才是意外。CC 的「个人更可信」前提在 pai 不成立：
pai 的项目 skills 同样过不了别人塞进仓库就静默生效那关——它没有 CC 的
工作区信任对话框，这个洞与「配了 Bash allow 即可越界」同属一类，
登记在 TODO 遗留里，不靠冲突语义兜。

出处：[features/25](features/25-20260822-skills/README.md) 拍板问 3。

## 73. 工具级边界豁免位：skill 工具退出路径边界（2026-08-23，feature 27）

25 把「加载 skill」建模成「读 SKILL.md 这个路径」（`@path_access_for(skill, READ)`
+ 未知名回 cwd 的绕法），25 复核实证了它的结构性后果：扫描按 git 根、边界按启动
cwd，从仓库子目录启动时目录照常宣传、工具调用却被边界拦（once/dontAsk 直接拒绝
且带权限话术——正是 R4#10 要避开的）；软链 skill 同样撞死。

三家对照（CC 反编译 2.1.88 符号级走读 + dsh 第一方文档）：没有一家这么建模。
CC 的 SkillTool 无 `getPath`、不进路径边界，门是 skill 名维度的 allow/deny/ask，
正文在发现期由 harness 裸读进内存；CC 边界根就是启动 cwd（`getOriginalCwd`），
`getProjectRoot()` 注释明文「Use for project identity (history, skills, sessions)
not file operations」——身份根与文件操作根刻意分工，CC 内部同样两根不一致但不成
bug，因为 Skill 工具不过路径层。dsh 的门是 `isModelInvocable` 策略位（加载前 +
返回前各查一次），全程不提文件权限层。

pai：`Tool.boundary_exempt` 显式豁免位（默认 False，`boundary_exempt_for(tool)`
声明），只作用于 decide 求值链第 7 步兜底——deny 规则、危险写检查、用户显式
ask 规则照常在前（测试钉优先级）。skill 删掉 path 声明与「未知名回 cwd」绕法。
声明条件收紧为两条同时成立：入参表达不了路径（模型没法用它指定读哪个文件），
且实际路径来自 pai 自算的受信来源。目前唯一豁免者是 skill。

刻意不抄的：CC 的 skill 名维度 allow/deny/ask 规则（pai 已有 `model_invocable`
这一半，规则那一半等真实需要）；附属文件的 read_file 仍走既有边界，用户级根
仍在 `WorkingDirs.additional`（25 遗留 6 的声明不变）。

出处：[features/27](features/27-20260823-skill-boundary-exempt/README.md)
拍板问 1（候选 B「两根进 additional」与 C「边界根改 git 根」的取舍见档案）。

## 74. MCP 工具的 schema 来自外部：「schema 与代码同源」的显式破例（2026-08-23，feature 29）

AGENTS 架构约束「工具 schema 一律由 @tool 装饰器从函数签名生成，禁止手写
schema 字典」的前提是工具是 pai 自己写的。MCP 工具的 schema 来自外部 server
的 tools/list——同源约束在这里结构性不可能成立。

三家的做法：CC 原样透传（annotations 另行映射能力位），dsh 原样透传且连子集
校验都不过并自认「垃圾进垃圾出是 server 作者的责任」，pi 无此问题（不做 MCP）。

pai：破例但不裸奔——外部 schema 与 description 一律过 Unicode 清洗
（NFKC + 剥 Cf/Co/Cn；CC 防 HackerOne #3086545 的真实攻击面：Tag 字符往
description 藏模型可读、人不可见的指令）+ description 截 2048 字符，然后
作为 `Tool.parameters` 透传。输入参数校验刻意留给 server（dsh 同款：兜底
`{}` 让 server 报「缺参数」这种模型能学的错）。破例范围只此一处：
`core/mcp.py` 的 `bridge_tools`，其它任何地方手写 schema 字典仍然违规。

出处：[features/29](features/29-20260823-mcp-client/README.md)；
K mcp/cc-mcp.md、mcp/dsh-mcp.md。
