# dsh 的 DeepSeek 适配层：拿同厂第一方交叉验证 pai 的两条实测坑

- 来源：deepseek-harness（github.com/deepseek-ai/deepseek-harness，MIT），
  commit `47f9438`。`packages/llm/llm-deepseek/src/{serialize,translate,types}.ts`。
  证据等级（D#69）：dsh 源码 + 源码内注释引用的官方文档路径（`guides/
  thinking_mode.mdx`、`api/create-chat-completion`）——注释是源码的一部分，
  但它转述的官方原文本篇未另行核对。
- 精读日期：2026-08-24（TODO「拿 dsh 反查两条实测坑」销账；D#69 理由①——
  三家里唯一能做同厂交叉验证的一家，别浪费）
- pai 锚点：`docs/dev/decisions.md` #33、#58、`src/pai/core/streaming.py`、
  `src/pai/core/compaction.py`（usage 口径）
- 相关：[../loop/dsh-loop.md](../loop/dsh-loop.md)（同 commit）、
  [reasoning-models-max-tokens.md](reasoning-models-max-tokens.md)

## 1. reasoning_content 回传（对 D#33）

dsh `serialize.ts:96-99` 真的回传，但只在 tool-call 轮：

- 注释原话：*Official passback rule (guides/thinking_mode.mdx):
  reasoning_content must return on tool-call turns; it is ignored on plain
  turns, so we drop it there to save tokens.*
- 即同厂第一方把文档的回传要求当真了，且给出了比文档更细的省 token 取舍
  （平轮丢弃）。

对 pai 的意义：D#33 的实测（不回传未触发文档说的 400）与 dsh 的顺从并不
矛盾——dsh 顺从不能证明 400 会发生，pai 的探针也只测了 3 次。维持 D#33 的
监控姿态不变，但监控条目的「一旦出现该 400」修法现在有了精确形状与文档
出处：只在 tool-call 轮回传（dsh 同款），不要平轮也带（白花 token）。

## 2. include_usage 与 usage 块形状（对 D#58）

- 发送侧：dsh 无条件带 `stream_options: {include_usage: true}`
  （`types.ts:17` 进请求默认）。pai 的 D#58 实测该参数在 DeepSeek 上是
  空操作——dsh 照发不误，保险带成本为零。
- 读取侧是真正的交叉验证点：`translate.ts` 模块注释写明 *Finish reason and
  the latest usage are deferred until `[DONE]`, covering both
  finish-attached and trailing usage-only shapes*——dsh 也观察到了 pai
  实测的那两种形状（usage 挂在带 finish_reason 的末块上 vs 独立
  usage-only 尾块），并写了形状无关的读取器（推迟到 DONE、取最新）。
  pai 的「每块都看、最后一个非空的赢」（`streaming._as_dict` 调用处注释）
  是同一结论的另一种实现。两家独立收敛，D#58 的置信度升级。

## 3. 顺手捡到：prompt_tokens 含缓存命中

`translate.ts:46-49` 注释（引 `api/create-chat-completion`）：DeepSeek 的
`prompt_tokens` **包含**缓存命中（`prompt_tokens = prompt_cache_hit_tokens
+ prompt_cache_miss_tokens`）；dsh 的 TokenUsage 约定是不相交计数，所以
减掉 cacheRead 才当 inputTokens。

对 pai 的意义：pai 的锚点簿与压缩触发都直接用 `prompt_tokens`——对「上下文
总量」这个用途，含缓存的口径恰好是对的（缓存命中的 token 也占窗口），
不需要改；但将来做成本核算（R4#A 待办：pi 费率结构 + 台账只存 token）时，
命中/未命中价差 50 倍，必须按 dsh 这样拆开算，不能拿 `prompt_tokens` 直乘
单价。另：`completion_tokens_details.reasoning_tokens` 字段存在，
成本核算与 reasoning 观测可用。
