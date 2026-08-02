# 开发日志

「做了什么」的时间线，一步一条。为什么这么选见 [decisions.md](decisions.md)，
下一件该做什么见 [TODO.md](TODO.md)。

注：2026-08-03 起本文件从 `docs/` 移到 `docs/dev/`。此前条目正文里的 `docs/xxx.md` 路径
保持当时原样未改写——那是记录，不是导航。

格式：目标 → 动了哪些文件 → 测试（红→绿的真实数字）→ 已知缺陷/待办。

---

## 2026-08-02 · 阶段 1 第 1-2 步：token 秤 + 警戒线 + 对话拍平机

**目标**：压缩系统的第一个问题是"现在上下文多大、该不该压"。先造三个纯函数当地基，
为后续 find_cut_point（在哪下刀）和 compact（自动压缩）铺路。

**动了的文件**
- 新增 `src/pai/compaction.py` — `estimate_tokens` / `should_compact` / `serialize_conversation` /
  `CompactionSettings`（frozen dataclass，`threshold=0.8`、`enabled=True`），
  外加一个 `estimate_conversation_tokens` 便利函数。
- 新增 `tests/test_compaction.py` — 18 个测试，含 `REAL_TRAJECTORY` 常量：
  取自 `pai_playground/sessions/20260802-224352.jsonl`（tri.txt 那次，9 条消息，
  含一条真实的 `sed` 失败），抄进测试时剥掉了 SessionLog 加的 `ts` 字段。
- 追加 `docs/decisions.md` 第 6-11 条。

**测试**
- 红：`ModuleNotFoundError: No module named 'pai.compaction'`（先写测试，模块还不存在）。
- 绿：`tests/test_compaction.py` **18 passed**；全量 `pytest -q` **28 passed in 4.22s**。
- 真实轨迹实测：估算 161 token / 拍平后 956 字符 / 原始 JSON 1505 字符。

**覆盖到的验收标准**
- 400 字符的 user 消息 = 100 token；不足 4 字符向上取整。
- 带 tool_calls 的 assistant 严格大于同 content 的纯文本消息。
- `content=None`（模型只发 tool_calls 不说话）不炸。
- 未知 role → 0，且拍平时整条跳过。
- `should_compact` 严格 `>`：800/1000@0.8 不压，801 才压；`enabled=False` 短路。
- 拍平截断：8000 字符 → 保留 5000 + `[... 3000 more characters truncated]`；
  content 和 tool_calls.arguments 两条路径都截；`max_chars` 可配。
- 真实轨迹：9 条消息无一被算成 0；拍平后仍含任务、三次命令、那条 `sed` 报错、最终结论。

**已知缺陷 / 待办**
1. **中文严重低估**：4 字符/token 是英文/代码经验值，汉字真实约 1-1.5 token/字，
   当前实现对中文对话可能低估 3-4 倍 → 压缩会来得太晚。修法：接 provider 的 `usage`
   回传做校准（后续阶段），当前仅用于阈值判断，量级够用。
2. 不计 `id` / `tool_call_id` 的 token（见 decisions 第 7 条），整体略偏低估。
3. 环境实跑 Python 3.9.6，而 AGENTS.md 原写 `>=3.10`——本次已把 AGENTS.md 改为
   与实际一致（要求配 `from __future__ import annotations`）。是否统一升到 3.10 待用户定。

**刻意没做**：`find_cut_point`（在哪下刀）、`summarize`（调模型摘要）、`compact`（把两者接起来）——
下一步。`loop.py` 也还没接压缩，本次改动对现有运行路径零影响。

---

## 2026-08-02 · 修订 AGENTS.md：放开 AI 实现权限 + 强制留痕

**目标**：项目改为 AI coding 驱动，AI 可直接实现阶段模块；代价是每步必须留痕，
否则"代码写完了人没学到"。

**动了的文件**
- `AGENTS.md`：
  - 项目定位约束——删掉"阶段模块是用户作业、不要替用户实现"，改为可由 AI 实现，
    但一律走 TDD（红的输出、绿的数字都要贴）。
  - 新增「留痕」一节：devlog 记"做了什么"、decisions 记"为什么"；一步一条不攒着补；
    数字要真实；已知缺陷必须落文件而不是只活在对话里。
  - 测试一节——新增阶段模块必须带单测，且至少一条用真实会话轨迹当输入。
  - 代码一节——把 `Python >= 3.10` 改为与实际 venv（3.9.6）一致的说明。
- 新增本文件 `docs/devlog.md`（含上一条的补录）。

**测试**：仅文档改动，`pytest -q` 仍 **28 passed**。

**待办**：`pyproject.toml` 的 `requires-python` 与实际 venv、与原 AGENTS.md 三处曾不一致，
现已统一到 3.9 的表述；若决定升 3.10，需同时改 pyproject 并重建 venv。

**2026-08-02 追记（待办关闭）**：用户拍板锁定 **Python 3.9.6**，不升 3.10。
三处表述现已一致（pyproject `>=3.9` / venv 3.9.6 / AGENTS.md），无需改代码。
后果：所有模块的现代类型注解（`int | None`、`list[str]`）都必须配
`from __future__ import annotations`，这是长期约束，不是临时妥协。

---

## 2026-08-02 · 阶段 1 修正：压缩阈值从「百分比」改为「减固定预留量」

**目标**：读 pi 与 CC 源码后发现 pai 的 `should_compact` 算法与两家都不同，且在大窗口上
会过早触发。趁 find_cut_point 还没依赖它，先改掉。

**改了什么**
- `src/pai/compaction.py`：
  - `CompactionSettings.threshold: float = 0.8` → `reserve_tokens: int = 16384`。
  - `should_compact`：`tokens > window * threshold` → `tokens > window - reserve_tokens`。
  - 两处 docstring 补上 16384 的构成（摘要输出约 8k + 下一轮工作空间约 8k）
    与退化情形说明。
- `tests/test_compaction.py`：改 3 条、新增 2 条。
- `docs/decisions.md`：第 12-14 条（pi/CC 拍平之争、阈值算法、熔断器）。

**测试**
- 红：`TypeError: __init__() got an unexpected keyword argument 'reserve_tokens'`，
  **5 failed, 15 passed**。
- 绿：`tests/test_compaction.py` **20 passed**；全量 `pytest -q` **30 passed in 4.39s**。

**新增的两条测试**
- `test_reserve_is_absolute_not_proportional` — 直接钉死这次修的 bug：
  200k 窗口下 170k **不该**压（旧的 `*0.8` 会误判为 True），183616 是压线点。
  同时验证同一个 reserve 在 64k 窗口下相当于更大比例（48k 就压），这正是期望行为。
- `test_window_smaller_than_reserve_always_triggers` — 把已知缺口钉在明面上（见下）。

**依据（读的是本机真源码，非记忆）**
- pi `compaction.ts:225`：`contextTokens > contextWindow - settings.reserveTokens`，
  `reserveTokens: 16384`、`keepRecentTokens: 20000`。
- CC `autoCompact.ts:30,62,72`：`窗口 - min(模型最大输出, 约两万) - 一万三千`。
  其中的输出预留量有统计依据：注释说明它取自压缩摘要输出长度的极高分位数。

**已知缺陷 / 待办**
1. **退化情形**：`window <= reserve_tokens` 时 `should_compact` 恒为 True，压缩救不了场，
   会变成无限压缩循环。已用测试钉住行为，但**未防护**——防循环属于上层熔断器职责，
   随自动压缩一起做（CC 把连续失败上限设为 3，其注释记录了起因：
   没有熔断时个别会话出现过数千次连续失败，全局每天浪费大量 API 调用）。
2. 16384 是照搬 pi 并按 DeepSeek 情况反推的，**没有实测依据**。CC 的 20000 来自
   p99.99 摘要长度统计——我们没有这个数据。拿到 usage 落盘后应该用真实摘要长度校准。
3. 前一条 devlog 记的「中文低估 3-4 倍」仍未验证，同样等 usage 落盘。

**刻意没做**：没有为退化情形加保护性 return（那会让 should_compact 撒谎），
没有把 `reserve_tokens` 拆成「摘要输出 + 工作空间」两个字段（CC 那样拆是因为它要按模型
动态取 maxOutputTokens，pai 目前单一模型，拆了是过度设计）。

---

## 2026-08-02 · 补录：DeepSeek 模型事实核对（含一处注释纠错）

**触发**：用户提供官网截图 + Responses API 文档链接，核对了此前几处凭印象的说法。

**确认的事实**（来自官网，非记忆）
- `deepseek-v4-flash`：**上下文 1M，输出上限 384K**，思考模式默认开启。
  → 关闭了上一条 devlog "窗口多大得查官网"的悬案。
- 另有 `deepseek-v4-pro`，同为 1M/384K，但**不支持 Responses API**。
- **Anthropic 格式 base url**：`https://api.deepseek.com/anthropic`
  → 意味着可用 Anthropic SDK 直连 DeepSeek，将来复刻 CC 的实现时能省大量改造。
- **Responses API 在 DeepSeek 是无状态的**：`previous_response_id` 不支持、
  `conversation` 不支持、`store` 恒为 false。它只是为兼容 Codex 这类客户端提供的
  **请求格式**，不提供 OpenAI 自家那种服务端会话状态。→ pai 无理由切换。
  唯一差异点：缓存字段名不同，Chat Completions 是 `usage.prompt_cache_hit_tokens`，
  Responses API 是 `usage.input_tokens_details.cached_tokens`。

**实测缓存数据**（用户 2026-08-02 全天用量截图）
- 总 30,048 = 命中缓存 23,424 + 未命中 4,216 + 输出 2,408。
- **输入缓存命中率 84.7%**（23424/27640）。
- 结论：pai 当前虽是「单次任务执行完即退出」，但 loop 每步重发递增前缀，
  第 2 步起即命中缓存。**不需要 REPL 就已经在吃缓存**。
  → 直接冲击 decisions 第 12 条（选拍平的理由是"没有缓存前提"），该前提已被推翻一半。

**纠错**
- `src/pai/compaction.py` 的 `CompactionSettings` docstring 原写
  "摘要输出（DeepSeek 单次上限约 8k）"——**错误**，实际输出上限 384K，差 48 倍。
  该数字是凭印象写的，未经核对。已改为不按输出上限推算，并注明 16384 目前无实测依据。
  教训：注释里的外部事实必须标注来源或标注"待核"，否则会变成后续决策的伪依据。

**测试**：仅 docstring 改动，`pytest -q` 仍 **30 passed**。

**待办（更新）**
1. usage 落盘仍是解锁项：能同时给出每步缓存命中率、真实 token 数（验证"中文低估"猜测）、
   真实摘要长度（校准 reserve_tokens）。
2. decisions 第 12 条（拍平 vs 原样发）需在 usage 落盘后重算——现在改等于拿一个
   未验证假设换另一个。
3. **1M 窗口下压缩几乎不会触发**（阈值 983,616，而用户全天才 30k）。
   压缩对 pai 更多是学习性实现而非运行必需，这不影响要做，但影响优先级判断。

---

## 2026-08-02 · 建立本地文档知识库 + 用官方系数重写 estimate_tokens

**目标**：此前多处注释凭印象写（已犯过一次 384K 写成 8k 的错），需要本地权威依据。
顺带用官方 token 系数替换通用经验值。

### 一、知识库

- 新增 `refs/deepseek-api/` —— DeepSeek API 中文文档本地快照，**61 页 / 532 KB / ≈82k token**，
  保留原站点路径结构，每文件头部标 `<!-- 来源: URL -->`，另有 `INDEX.md` 索引。
- 抓取方式：站点是 Docusaurus，`llms.txt` 是 SPA 回落（假的），GitHub 源仓库 404，
  故走 sitemap（62 页）→ `curl -L` → 抽 `<article>` → `pandoc -f html -t gfm`
  → 清洗（面包屑 / 移动端 TOC / base64 内联图标 / 上下页导航）。
- 失败 1 页：`prompt-library`（无 `<article>`，特殊布局页，与 API 无关），已记入 INDEX 末尾。
- 只抓了中文版；英文版可按同法再跑一遍。
- 意外收获：官方为 **pi**（`agent_integrations/pi_mono.md`）与 **Claude Code**
  （`agent_integrations/claude_code.md`）都写了接入文档，另有 `guides/anthropic_api.md`
  ——`https://api.deepseek.com/anthropic` 可用 Anthropic SDK 直连。

### 二、estimate_tokens 改用官方系数

**改了什么**
- `src/pai/compaction.py`：`CHARS_PER_TOKEN = 4` → `TOKENS_PER_CJK_CHAR = 0.6` /
  `TOKENS_PER_ASCII_CHAR = 0.3` + `CJK_RANGES`；新增 `_is_cjk` / `_estimate_text_tokens`。
- `tests/test_compaction.py`：改 3 条、新增 5 条。

**测试**
- 红：**7 failed, 17 passed**（`assert 100 == 120`、`assert 161 > 209.3` 等）。
- 绿：`tests/test_compaction.py` **24 passed**；全量 `pytest -q` **34 passed in 3.56s**。
- 实测 REAL_TRAJECTORY：629 字符，旧算法 161 token → 新算法 **243 token（1.51x）**，
  落在纯英文下界 189 与纯中文上界 377 之间。

**推翻了一条最初的验收标准**：`400 字符 = 100 token`（chars/4）改为 **120**（400×0.3）。
这是用户最早钉下的标准，经确认后推翻——理由写在测试 docstring 里：通用经验值让位于官方系数。

**纠正了一个此前记错的数**：devlog 首条写「中文低估 3-4 倍」，官方系数下**实际是 2.4 倍**
（0.6 vs 0.25）。原数是猜的，现有依据。

**新增测试的取舍**：真实轨迹那条从「写死区间 100~400」改为
`0.3*chars < total < 0.6*chars`——上下界是算法本身的数学边界，只要系数对、字符没漏算就必然落在
里面，比拍脑袋的数字更能抓真问题（漏算 arguments 会跌破下界）。

### 三、缓存机制（decisions 第 16-17 条）

读 `guides/kv_cache.md` + `quick_start/pricing.md` 后，**第 12 条的账反转了**：
缓存命中 0.02 元/M vs 未命中 1 元/M = **50 倍**差距（此前估的是 10 倍），
CC 的「原样发」在 DeepSeek 上比 pi 的「拍平」便宜约 **32 倍**。
未改实现——CC 自陈原样发有百分之几的不听话率（其在较新模型上的实测），DeepSeek 上未知。
详见 decisions 第 16 条。

**已知缺陷 / 待办**
1. `reserve_tokens=16384` 仍无实测依据（1M 窗口下触发点 983,616，实际几乎不会到）。
2. usage 落盘仍未做——它现在能解锁：真实 token 对比（验证 0.3/0.6 系数准不准）、
   每步缓存命中率、摘要真实长度。
3. 官方离线 tokenizer（`deepseek_v3_tokenizer.zip`）未下载。它能给精确值，
   但会引入依赖且是 v3 版本（当前用 v4），暂缓。
4. `refs/` 是否纳入版本管理待定，当前未 commit。

---

## 2026-08-02 · usage 落盘 + refs/ 纳入版本管理

**目标**：把 provider 回传的 usage 落进 session JSONL，用真实数字校准估算、量化缓存命中率。

### 一、改了什么

- `src/pai/compaction.py`：新增 `estimate_request_tokens(messages, tool_schemas)`。
  真实 `prompt_tokens` 算的是**整个请求**，工具 schema 也在里面；只估 messages 会系统性
  低估一个近似恒定的量（pai 四个工具约 389 token）。要与 window 比、与 usage 对账，
  比的都该是这个数。
- `src/pai/loop.py`：每次模型调用后把 usage 落一条 session 记录，含本地估算值并排放。
  新增 `_usage_record()`：`model_dump()` 优先（SDK 是 pydantic），退化路径覆盖 dict 与
  SimpleNamespace；provider 不回 usage 时返回 None，不落空记录。
- `tests/fake_llm.py`：turn 支持可选 `usage` 字段。
- `tests/test_loop.py` +4 条、`tests/test_compaction.py` +3 条。
- 新增 `refs/README.md` 与 `refs/fetch_deepseek_docs.py`（知识库可重复更新）。

**两个刻意的设计**
1. 记录挂 `type: "usage"` 而**不是** `role`，且绝不挂到 message 上。多一个字段就改变请求前缀，
   而 DeepSeek 硬盘缓存要求完整匹配缓存前缀单元——污染消息等于把命中率打到 0。
   专门有测试 `test_usage_never_leaks_into_messages_sent_to_api` 钉住。
   附带好处：`estimate_tokens` 对无 role 记录返回 0、`serialize_conversation` 直接跳过，
   usage 记录天然不会被当成消息。
2. usage 字段**只透传不归一化**。归一化会丢掉 DeepSeek 专有的
   `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`，而那正是我们要的。

### 二、测试

- 红：**5 failed, 36 passed**（3 个 `ImportError: estimate_request_tokens`，
  2 个 usage 记录缺失 `IndexError`）。
- 绿：全量 `pytest -q` **41 passed in 3.92s**。

### 三、真实运行实测（session 20260802-235657，3 步任务）

| 步 | 消息数 | 消息估算 | +schema | 真实 prompt_tokens | 差额 | 比值 |
|---|---|---|---|---|---|---|
| 1 | 2 | 102 | 491 | 732 | 241 | 1.49 |
| 2 | 4 | 134 | 523 | 821 | 298 | 1.57 |
| 3 | 6 | 151 | 540 | 885 | 345 | 1.64 |

**缓存命中率 89.3%**（2176 / 2438），印证了此前 84.7% 的全天统计。
`prompt_tokens_details.cached_tokens` 与 `prompt_cache_hit_tokens` 一致，两个字段都在回传。

**结论：改用官方 0.3/0.6 系数后，估算仍系统性低估约 1.5-1.6 倍。** 拆解：
- 差额随消息数增长：每多 2 条消息，差额涨约 50 → **每条消息约 25 token 的框架开销**
  （role 标记、分隔符等 chat template 结构，我们完全没算）。
- 扣掉框架开销后仍有约 190 的固定差额 → **工具 schema 被低估约 1.5 倍**
  （我们按 `json.dumps` 估 389，服务端实际格式化后更贵）。

这不是系数错了，是**估算对象不完整**：我们只数了内容的字符，没数协议的结构。

### 四、refs/ 纳入版本管理

`git add refs/` —— **64 个文件 / 540 KB** 已进暂存区（未 commit，按 AGENTS.md 规矩）。
新增 `refs/README.md` 说明用途与更新方式，并列出常查页；
`refs/fetch_deepseek_docs.py` 是抓取脚本，日后可重跑更新快照。

### 已知缺陷 / 待办

1. **估算仍低估 1.5-1.6 倍**（上面的诊断）。正确修法不是继续调系数，而是学 pi
   （`compaction.ts:189`）：**以最近一次 usage 回传的真实值为基准，只估它之后新增的消息**。
   这样系统性误差被真实值锚住，估算只作用于很短的尾部。→ 下一步。
2. 上述诊断基于**单次 3 步会话**，样本太小。多跑几次不同任务再定结论。
3. `pai_playground/sessions/` 被 .gitignore 排除（规则 `sessions/`），
   而 REAL_TRAJECTORY 的原始出处正在那里。测试里已内联该数据故不受影响，
   但**溯源链断了**——若要可追溯，需把用作测试夹具的轨迹单独存一份到版本库内。

---

## 2026-08-03 · 上下文大小改为「真实 usage 锚定 + 增量估算」

**目标**：上一条 devlog 实测出估算系统性低估 1.5-1.6 倍。不继续调系数，改用 pi 的思路——
以真实值为锚，把估算限制在很短的尾部。

**改了什么**
- `src/pai/compaction.py`：新增 `context_tokens(messages, tool_schemas, *, anchor, anchor_index)`。
  三行实现：无锚则退化为 `estimate_request_tokens`；有锚则 `anchor + 估算(messages[anchor_index:])`。
- `src/pai/loop.py`：维护两个变量 `anchor` / `anchor_index`。收到响应并追加 assistant 消息后：
  `anchor = prompt_tokens + completion_tokens`、`anchor_index = len(messages)`。
  `_usage_record()` 简化为 `_usage_fields()`（只取字段，记录组装挪到调用处）。
- `tests/test_compaction.py` +4 条，含新夹具 `REAL_USAGE_TRAJECTORY` / `REAL_USAGE_STEPS`
  （取自真实会话 20260802-235657 的 3 步运行）。

**测试**
- 红：**4 failed, 27 passed**（`ImportError: context_tokens`）。
- 绿：`tests/test_compaction.py` **31 passed**；全量 `pytest -q` **45 passed in 4.32s**。

**验收标准写进了测试**：`test_anchored_estimate_beats_pure_estimate_on_real_usage`
用真实的三步 usage 断言——锚定法误差须 < 5%，且纯估算在同一批数据上必须错 > 30%。
双向断言是故意的：只断言"锚定法准"，改回纯估算时测试可能仍侥幸通过。

**真实运行验证**（新会话，4 步任务）

| 步 | 预测 | 真实 | 误差 |
|---|---|---|---|
| 1 | 495 | 736 | **-32.7%**（无锚，纯估算） |
| 2 | 833 | 845 | **-1.4%** |
| 3 | 912 | 924 | **-1.3%** |
| 4 | 975 | 988 | **-1.3%** |

锚定后误差绝对值均值 **1.3%**（此前 -36%）。本次缓存命中率 **91.6%**。

**顺带的性能收益**（当时没想到）：纯估算每步都要扫描整段对话的全部字符，
一次会话下来是 O(n²)；锚定法只扫新增部分，是 O(新增字符)。1M 窗口下这个差别不是小事。

**已知缺陷 / 待办**
1. 锚假设「上一步之后新增的消息都在 anchor_index 之后」，这在当前 append-only 的 loop 里成立。
   将来压缩会**改写**历史（老消息被摘要替换），届时必须让锚失效重来——
   实现 compact() 时要把 anchor 重置为 None，否则会拿旧锚算新对话，错得离谱。**这是个坑，别忘。**
2. 首次请求仍纯估算（-33%）。可接受：那时上下文几百 token，离 983,616 的阈值差三个数量级。
3. `estimate_tokens` 的 1.5 倍系统偏差保留不修（decisions 第 19 条给了理由）。
   若将来 find_cut_point 表现出切点偏移，再回来看这条。
4. 至今仍未接 `should_compact` 到 loop——`context_tokens` 算出来只落盘、不决策。
   接上是自动压缩那一步的事，需同时带熔断器（decisions 第 14 条）。

---

## 2026-08-03 · 公开仓库前的清理 + 状态快照

**目标**：仓库将改为公开，先处理第三方内容与引用问题；并补一份给接手者看的状态快照。

**动了的文件**
- 新增 `docs/STATUS.md` —— 一页的当前状态快照：模块状态表、compaction 各函数是否已接进 loop、
  实测数据、6 条已知缺陷、下一步。`AGENTS.md` 留痕一节加了它（阶段性节点更新，不必每步动）。
- `docs/decisions.md` / `docs/devlog.md` / `docs/STATUS.md`：把 Claude Code 源码的**逐字引用**
  与其中的内部遥测数字改为**转述 + 量级描述**。设计洞察全部保留（熔断上限、预留量的统计依据、
  原样发的不听话率），去掉的是逐字注释文本与精确内部统计值。
  pi 的引用保留——它是 MIT（Copyright (c) 2025 Mario Zechner），带出处引用没有问题。
- `README.md`：「Claude Code 反编译源码」改为「对 Claude Code 的实现分析」，
  并给 pi 标注 MIT。
- `.gitignore`：新增 `refs/deepseek-api/`（第三方文档，版权归 DeepSeek，改为用脚本自行生成）
  与 `pai_playground/`（agent 跑测试留下的产物）。
- `git rm -r --cached refs/deepseek-api` —— 从暂存区移除 61 个文件；
  `refs/` 现在只跟踪 `README.md` 与 `fetch_deepseek_docs.py`。
- `refs/README.md`：改写为"不入库，需自行生成"，附 pandoc 安装与生成命令。

**安全检查（公开前）**
- `.env` 从未进入 git 历史（只有 `.env.example`，内容是占位符）。
- 已跟踪文件中无任何形如 `sk-...` 的密钥。
- 远程：`https://github.com/sakuzeng/pai.git`。

**测试**：仅文档与 .gitignore 改动，`pytest -q` 仍 **45 passed**。

**待办**：知识库不入库后，`refs/README.md` 里列的"常查页"清单只有生成过的人能用；
若将来发现协作者频繁需要，再考虑改为链接到官网对应页。

---

## 2026-08-03 · 外部评审第一批修复（立即修 4 条）

**来源**：`docs/reviews/2026-08-03-冷眼评审.md`，全新上下文的 AI 评审会话，20 条发现。
本条只处理其中「小刀」四条，其余按优先级排期（见文末）。

### #1（严重）loop 被「合法 JSON 但非对象」的 arguments 崩掉

`src/pai/loop.py:102`。`json.loads` 只挡 `JSONDecodeError`；模型返回 `null`、`[1,2]`、
`"hello"` 时都是合法 JSON，但 `t.run(**args)` 在**进入 Tool.run 的 try 之前**就抛
`TypeError: argument after ** must be a mapping`，loop 整个崩。

同时打穿两条自家决策：第 2 条「任何分支都必须回填 tool 消息」、第 1 条「Tool.run 保证
任何调用路径不漏」。**教训：错误吸收边界修在了函数内部，而这一击落在函数门口。**

修法：`json.loads` 后加 `isinstance(args, dict)` 判断，非 dict 走同款错误回填。
新增两条测试：五种非对象输入全覆盖；错误消息仍与 tool_call_id 严格配对。

### #2（严重）STATUS.md 的测试数字与事实不符

`docs/STATUS.md` 原写「45 passed，全部离线」。实际 45 = 44 离线 + 1 条打真实 API 的冒烟测试。
违反 AGENTS.md「数字要真实」铁律，实际后果是**任何有 key 的人跑全量测试就静默花钱**
（评审者本人就中招了）。已改为分列两行并加粗警告，建议日常用 `-m "not llm"`。

### #10 无 docstring 的工具在装饰时崩 IndexError

`src/pai/tools/__init__.py:64` 的 `splitlines()[0]` 对空 docstring 崩。
改为显式 `raise ValueError("工具 X 缺少 docstring：首行会作为工具描述发给模型")`——
报错要指向真因，而不是索引越界。新增一条测试。

### #13 AGENTS.md 的 3.9 表述不准确

原写「`int | None`、`dict[str, X]` 都必须配 future import」。**`dict[str, X]` 是 PEP 585，
3.9 运行期就合法**（已实测；`tests/fake_llm.py:31` 无 future import 用 `list[dict]` 跑通即证据）。
真正需要 future import 的只有 PEP 604 的 `int | None`。已改。

**测试**
- 红：**3 failed, 44 passed, 1 deselected**（2 个 TypeError 崩溃 + 1 个 IndexError）。
- 绿：`pytest -q -m "not llm"` **47 passed, 1 deselected**。

### 剩余 16 条的排期

- **find_cut_point 动工前必须清掉**：#3（thinking mode 断言矛盾，需探针核实）、
  #4（重审 decisions 第 19 条——「均匀偏差不影响切点」只对按比例切成立，
  而 pi 按绝对预算切，这动摇了 find_cut_point 的设计前提）、
  #7（锚重置后的读数盲区，补进 STATUS 缺陷 1）、#8/#9（测试加固）。
- **留到 summarize 时一起算**：#12（32 倍的两个输入项偏虚）、#16（system 是否进拍平）。
- **文档类**：#5、#6、#20（decisions 内部矛盾与过时论证）。
  #6 按用户要求**保留原理由作为划掉的记录**而非删除——决策文档里「曾经这么想、
  后来被指出为什么错」的痕迹，是「我的决策可被挑战」最有说服力的证据。
- 其余（#11、#14、#15、#17、#18、#19）按可选处理。

---

## 2026-08-03 · 烧钱防线：用量预算熔断 + 真实 API 测试改为显式选择

**目标**：担心真实 key 跑出错时烧掉大量费用。先查平台侧能力，再补代码侧防线。

**查证结论（refs/deepseek-api）**
- `quick_start/rate_limit.md`：DeepSeek **只有并发限速**（v4-flash 2500 / v4-pro 500，
  按账号计、与 API Key 无关，超限返回 HTTP 429），**没有消费限额/配额功能**。
- `api/get-user-balance.md`：有 `GET /user/balance` 可查余额（总额/赠金/充值分列），只读。
- 结论：平台指望不上，防线得自己建。

**改了什么**
- `src/pai/loop.py`：`run_agent` 新增 `max_total_tokens` 参数；累加每步 usage 的
  `total_tokens`，在**循环开头、发请求之前**检查，超了就带数字返回。
  同时给 `run_agent` 补了 docstring（此前没有）。
- `src/pai/cli.py`：新增 `--max-tokens`，**默认 200000**（v4-flash 最坏约 0.4 元），
  `0` 表示不限。默认给防线，而不是默认裸奔。
- `tests/conftest.py`：llm 标记的测试从「有 key 就跑」改为「有 key **且**
  `PAI_RUN_LLM_TESTS=1` 才跑」，跳过原因里直接写出启用方法。
- `tests/test_loop.py` +5 条测试。

**测试**
- 红：**5 failed, 47 passed**（`TypeError: run_agent() got an unexpected keyword
  argument 'max_total_tokens'`）。
- 绿：`pytest -q -m "not llm"` **52 passed, 1 deselected**；
  默认 `pytest -q`（有 key 但未选择加入）**52 passed, 1 skipped**。

**真实运行验证**
```
$ pai --max-tokens 1500 "创建 budget_check.txt ...（4 步任务）"
🤖 已达用量预算：累计 1695 token 超过上限 1500，在第 3 步发出请求前停止。任务可能未完成。
```
实际停在 1695 而非 1500——因为检查点在发请求之前，最后一次请求必然略微超出。
这是刻意的取舍（decisions 第 22 条）。

**已知缺陷 / 待办**
1. 预算只按 token 计，不按钱计。命中缓存的输入比未命中便宜 50 倍，同样 token 数
   花的钱可差两个数量级。要精确控费需按 `prompt_cache_hit/miss/completion` 三档
   分别乘单价——但单价会变（官网已预告峰谷定价），硬编码进代码是维护债。
   当前取舍：token 预算作为量级护栏够用，精确成本留给离线分析 session JSONL。
2. 没有跨会话的累计预算。每次 `pai` 调用各自计数，连着跑 100 次仍会花 100 份钱。
   真正的总闸是「账户只充小额」。
3. `GET /user/balance` 未接入。可做 `pai --balance` 或启动时低余额告警，暂未做。

---

## 2026-08-03 · 框架对齐 pi：core/ + modes/ 分离，docs 分层，统一测试入口

**目标**：趁代码只有 587 行、32 个 import 点，把结构对齐 pi，避免后续加模块时反复搬家。

### 第 1 步：合并待办 → `docs/dev/TODO.md`

此前待办散在 8 条 devlog + STATUS + 评审报告，共 13 处「已知缺陷/待办」——记是记了，
但没法一眼看出下一件该做什么。合并为单一清单，四档优先级（P0 阻塞主线 / P1 主线 /
P2 值得改 / P3 可选），每条注明出处（`R#n` 评审 / `D#n` 决策 / 日期），外加已完成区 12 条。
`AGENTS.md` 补规矩：新写的待办必须同步登记到 TODO.md，否则等于没记。

### 第 2 步：docs 分层

`docs/{decisions,devlog,STATUS}.md` 与 `reviews/` 移入 `docs/dev/`；
`docs/` 根目录留给面向用户的文档（学 pi）。导航性引用改了 12 处，残留 0。
历史 devlog 条目正文里的旧路径未改写——那是记录不是导航，已在 devlog 开头说明。

### 第 3 步：core/ + modes/ 重构

```
src/pai/
  cli.py  config.py
  core/    loop.py  session.py  compaction.py  tools/
  modes/   once.py
```
- `cli.py` 从 37 行瘦到只做 argparse + 分发；跑任务的接线抽进 `modes/once.py`。
- `run_once` 的 client/model 可注入 → 接线层也能离线测，新增 `tests/test_modes.py` 4 条。
- 32 个 import 点机械改写，残留 0。

### 第 4 步：`test.sh` 统一入口

默认 `-m "not llm"`；`./test.sh --llm` 才打真实 API 并先打印警告。README 同步更新。

**测试**
- 搬完立刻绿：**52 passed, 1 skipped**（未新增测试时）。
- 补接线层测试后：`./test.sh -q` **56 passed, 1 deselected**。
- 真实任务端到端验证通过（`pai --max-tokens 50000 "创建 refactor_check.txt…"`）。

**没做的一件事**：`compaction.py` 没拆成目录。现在 189 行，pi 的对应文件到 893 行才拆；
现在拆会在还不知道 find_cut_point/summarize 形状时就把边界钉死。
已设触发条件（summarize 落地后）并登记进 TODO.md P2。

**待办**：本条涉及的新待办已同步进 TODO.md（compaction 拆分触发条件）。
