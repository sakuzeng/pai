# 待办清单

单一优先级清单。此前待办散在 8 条 devlog + STATUS + 评审报告里，记是记了但不可用——
本文件是唯一入口，每条注明出处，改完在对应出处补记再从这里划掉。

出处记法：`R#n` = docs/dev/reviews/2026-08-03-冷眼评审.md 第 n 条；
`D#n` = decisions.md 第 n 条；`日期` = devlog 对应条目。

---

## P0 · find_cut_point 动工前必须清掉

这些都会影响 find_cut_point 的设计前提，带着它们动工等于在流沙上盖楼。

- [ ] **核实 thinking mode 到底默认开不开**（R#3，严重）
      devlog 断言 v4-flash「思考默认开启」，而 loop 丢弃 `reasoning_content`；
      官方文档写明带 tools 时未回传 reasoning_content 会返回 400。
      实测 session 里 `reasoning_tokens` 全为 0（即实际没开），与 devlog 矛盾。
      两个断言必有一假。做法：一次探针请求核实 → 开则 loop 必须回传 reasoning_content
      且重审 anchor 的 completion_tokens 口径，不开则纠正 devlog。
- [ ] **重审 decisions 第 19 条**（R#4）
      「均匀偏差不影响切点」只在切点按**比例**定义时成立；pi 按**绝对预算**切
      （keepRecentTokens=20000）。1.5 倍低估意味着想保 2 万实际保约 3 万，挤占 reserve 余量。
      这是评审最值钱的一击——攻的是我们最自信的推理。
- [ ] **锚重置后的读数盲区补进 STATUS 缺陷 1**（R#7）
      `compact()` 重置 `anchor=None` 后，紧接着的 `context_tokens` 退化为纯估算（-33%），
      而那恰是最需要准确回答「压缩救回来了没有」的时刻（熔断器依赖它）。
      方向：熔断器判断改用压缩后**首次真实 usage 回传**。
- [ ] **给 loop 层锚簿记补测试**（R#8）
      `loop.py` 的 `anchor_index = len(messages)` 是 off-by-one 高危点；
      评审实测改成 `len(messages)-1` 后全部测试照样绿（现有断言只有 `estimated > 0`，过弱）。
      做法：两步带 usage 的脚本，精确断言第二条 usage 的 `estimated == anchor + 尾部估算`。
- [ ] **冻结测试夹具里的工具 schema**（R#9）
      `REAL_USAGE_STEPS` 的真实值录制于当时的 schema，测试却用 `get_tools()` 取活 schema——
      将来改一句工具描述就可能假失败，且报错不指向真因。

## P1 · 主线（阶段 1 压缩）

- [ ] `find_cut_point`（在哪下刀）。约束：绝不在 tool 结果上切，否则产生孤儿 tool_result。
- [ ] `summarize`（调模型摘要）。届时一并决定：
      - 拍平 vs 原样发（D#12/D#16，R#12）——需实测 DeepSeek 上的「不听话率」，
        并把「0.64 系数来自单条小轨迹」「原样发要求 tools 逐字节一致」两个虚项补进实验设计
      - `serialize_conversation` 是否跳过 system 消息（R#16）——不跳则 system 会同时出现在
        拍平文本与新上下文里，浪费摘要预算
      - 用真实摘要长度校准 `reserve_tokens=16384`（目前照搬 pi，无实测依据）
- [ ] `compact`（把两者接起来），必须同时带**熔断器**（D#14）：连续压缩失败达上限即停。
- [ ] 把 `should_compact` 真正接进 loop——目前 `context_tokens` 算出来只落盘、不决策。
- [ ] **压缩会改写历史，必须让 anchor 失效**：`compact()` 里把 `anchor` 重置为 `None`，
      否则拿旧锚算新对话。锚定法假设 append-only，与压缩天然冲突。

## P2 · 值得改

- [ ] **decisions 第 8 条与第 6 条自相矛盾**（R#5）
      第 6 条说「低估是唯一会炸窗口的方向」，第 8 条却让未知 role 静默记 0——
      0 是最极端的低估。改为按 content 估算（宁可高估）或留告警路径。
- [ ] **decisions 第 9 条理由不成立**（R#6）
      「严格大于防阈值横跳」防不了——边界上 `>` 与 `>=` 只差 1 token。真防横跳的是
      压缩后落点远离警戒线。结论无害但理由错。
      **改法：保留原理由作为划掉的记录，不要删除**——决策文档里「曾经这么想、后来被指出
      为什么错」的痕迹，是「我的决策可被挑战」最有说服力的证据。
- [ ] **decisions 第 7 条引用链未回收**（R#20）
      其理由引用的「400 字符=100 token 心智模型」已被第 15 条废弃（结论仍成立）。
- [ ] **单轮多 tool_calls 无测试覆盖**（R#11）
      所有测试脚本每轮只有一个 tool_call；「N 条 tool 消息按序配对」「合法+未知工具混同轮」
      两个配对不变量无测试。DeepSeek 会发并行工具调用，非假想场景。
- [ ] **`session.py` 文件名精确到秒**（R#15）：同秒创建两个 SessionLog 会写同一文件。
- [ ] **抽出共享测试夹具层**（对照 pi 的 `test/harness/session-test-utils.ts`、`test/utils/`）
      现状：5 个测试文件平铺，夹具各自为战——`REAL_TRAJECTORY` / `REAL_USAGE_TRAJECTORY` /
      `REAL_USAGE_STEPS` 在 test_compaction.py，`USAGE` / `_budget_script` 在 test_loop.py，
      改一处工具描述可能让多处假失败（R#9 只覆盖了"冻结 schema"这一角）。
      **触发条件**：测试文件到 10 个左右，或 find_cut_point/summarize 的夹具开始重复时再抽。
      现在抽是过度设计——57 个用例还不知道该抽什么。
      注：pi 的 `test/harness/` 是"给 harness 模块写的测试"（镜像源码结构），不是测试框架；
      pai 真正缺的是共享夹具与目录分层，不是"缺一个 harness"。
- [ ] **`compaction.py` 拆成目录的触发条件**：现在 189 行，单文件合适；
      pi 的 compaction.ts 到 893 行才拆。等 `summarize` 落地（预计 +300 行）再拆，
      拆法照 pi：`estimate` / `serialize` / `cut_point` / `summarize` + `__init__.py` 统一导出。

## P3 · 可选

- [ ] `loop` 的 `client` / `response` 无类型注解，违反自家规矩（R#14）。
      可给最小 Protocol（`chat.completions.create`），顺带静态约束 FakeClient 同构性。
- [ ] `read_file` 截断后无分页/offset，模型可能基于残缺视图去 edit（R#17）。
      零成本做法：在截断提示语里建议模型用 bash 分段读。
- [ ] `session=None` 时也每步计算 `estimated`，纯浪费（R#18，量极小）。
- [ ] `estimate_tokens` 假设 content 是 str/None；OpenAI 协议 content 可为分段列表，
      接多模态前要处理（R#19）。
- [ ] **预算改按钱算**（2026-08-03，措辞已修正）。命中缓存比未命中便宜 50 倍，
      同样 token 数花的钱可差两个数量级。此前记为"单价会变所以是维护债"——**这个判断下早了**：
      pi 有现成答案（`ai/src/models.ts:639` `calculateCost`），把费率放进 model registry 而非代码，
      四档分别乘单价（input / output / cacheRead / cacheWrite），
      且支持分层价格 `tiers`（按 `inputTokensAbove` 切档）——DeepSeek 的峰谷定价可用同一机制表达。
      所以不是"不该做"，是**需要先有一个费率表结构**。
- [ ] **usage 归一化：算出"真正新计算的 input"**（2026-08-03）。
      现在原样透传 provider 字段（保住 `prompt_cache_hit_tokens` 是对的），但缺一步减法。
      pi 的语义（`api/openai-completions.ts:1337`）：`prompt_tokens` 是**含缓存的总数**，
      `input = prompt_tokens - cacheRead - cacheWrite`，`totalTokens = input+output+cacheRead+cacheWrite`。
      按钱算预算的前提就是这个减法。注：pi 明确兼容了 DeepSeek 的 `prompt_cache_hit_tokens` 字段。
- [ ] **接流式前必修：并行工具调用会让 usage 重复累加**（2026-08-03）。
      CC 注释（`utils/tokens.ts:28`）：并行工具调用流式返回时，**每个 content block 会成为一条独立的
      assistant 记录，但共享同一个 `message.id`**——天真累加就是重复计费，CC 为此专门有
      `getAssistantMessageId` 识别同源记录。
      pai 当前安全（不流式，一次 `create()` 累加一次），但接流式后必然撞上。
      与「单轮多 tool_calls 无测试覆盖」（R#11）是同一场景的两面。
- [ ] **usage 可信度过滤**（2026-08-03）。两家都不直接信原始返回：
      pi 排除 `aborted` / `error` / 全 0；CC 排除**合成消息**（`SYNTHETIC_MESSAGES`，
      中断等场景注入的假 assistant 消息带假 usage）。
      pai 现在只判 `usage is None`，够用但不完整——接中断/重试后要补。
- [ ] 无跨会话累计预算（2026-08-03）。每次 `pai` 调用各自计数。真正的总闸是账户只充小额。
- [ ] `GET /user/balance` 未接入。可做 `pai --balance` 或启动时低余额告警。
- [ ] 官方离线 tokenizer（`deepseek_v3_tokenizer.zip`）未下载。能给精确值，
      但引入依赖且是 v3 版（当前用 v4），暂缓。
- [ ] `pai_playground/sessions/` 已被 .gitignore 排除，而测试夹具的原始出处在那里——
      溯源链断了。若要可追溯，需把用作夹具的轨迹单独存一份到版本库内。
- [ ] `refs/README.md` 列的「常查页」清单，在知识库不入库后只有生成过的人能用。
      若协作者频繁需要，改为链接官网对应页。
- [ ] **pai-viz 子进程 30s 超时值无实测依据**（2026-08-03）：照拍脑袋定的，随功能变大
      （collect.py 干的事变多）再看是否够用。
- [ ] **pai-viz 不做自动刷新**（2026-08-03，YAGNI）：现状是点按钮手动刷新；
      若用起来发现手动刷新烦，再加。
- [ ] **pai-viz 的会话回放、用量仪表盘未立项**（2026-08-03）：以后有需要再单独立项设计，
      不是本轮 viz 范围。

---

## 已完成（保留记录，便于回看节奏）

- [x] token 秤 / 警戒线 / 拍平机三件套（2026-08-02）
- [x] 官方系数替换 chars/4，中英文分开算（2026-08-02，D#15）
- [x] 阈值从百分比改为减固定预留量（2026-08-02，D#13）
- [x] usage 落盘（2026-08-02）
- [x] 上下文大小改为真实 usage 锚定 + 增量估算，误差 -33% → -1.3%（2026-08-03，D#18）
- [x] 本地文档知识库 refs/deepseek-api（2026-08-02）
- [x] 公开前清理：CC 逐字引用转述、第三方文档与 playground 入 .gitignore（2026-08-03）
- [x] R#1 loop 被非对象 arguments 崩掉（2026-08-03，严重）
- [x] R#2 STATUS 测试数字与事实不符（2026-08-03，严重）
- [x] R#10 无 docstring 的工具崩 IndexError（2026-08-03）
- [x] R#13 AGENTS.md 的 3.9 类型注解表述不准（2026-08-03）
- [x] 用量预算熔断 + 真实 API 测试改为显式选择加入（2026-08-03，D#21-23）
