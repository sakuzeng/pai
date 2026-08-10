# OpenAI 兼容协议的流式：工具调用逐字符到达，usage 只在末块

- 来源：无单一外部原文。DeepSeek 官方 API 文档（本仓库镜像
  `refs/deepseek-api/api/create-completion.md` 的 `stream` / `stream_options`）
  + OpenAI chat completions 的 delta 协议 + **2026-08-11 对 `deepseek-v4-flash` 的实测**
  （6 个探针，原始 chunk 与脚本见
  [features/11 evidence](../../docs/dev/features/11-20260811-streaming/evidence/20260811-流式探针/说明.md)）
- 精读日期：2026-08-11
- pai 锚点：`src/pai/core/loop.py`（`usage_fields` / `AnchorBook` / `spent_tokens`）、
  docs/dev/features/11-20260811-streaming（阶段 5）

任何把非流式的 `create()` 改成 `stream=True` 的程序都要重写两处：**怎么把碎片拼回一条消息**，
以及**用量数据从哪拿**。第二处是静默失效的重灾区。

## 一、tool_calls 是按 `index` 分片的，而且碎到逐字符

一次并行调用两个工具，实测 76 个 chunk 里工具部分的形状：

```
chunk#55  index=0  id=call_00_…  name=get_weather        ← id 与 name 只出现一次，在首块
chunk#56  index=0  arguments='{'                          ← 从这里开始逐字符
chunk#57  index=0  arguments='"'
chunk#58  index=0  arguments='city'
…
chunk#64  index=0  arguments='}'                          ← index=0 完整发完
chunk#65  index=1  id=call_01_…  name=get_population      ← 才轮到 index=1
…
chunk#75  finish_reason=tool_calls  + usage               ← 收尾
```

四条可依赖的事实：

1. **`index` 是唯一的归并键**，不是 `id`——`id` 只在首块出现，后续分片只有 `index`；
2. **`arguments` 必须字符串拼接后再解析**。`{"city": "北京"}` 这 16 个字符分成了 9 块。
   拿到 delta 就 `json.loads` 必炸，而且炸得毫无规律（取决于分块位置）；
3. **并行调用是串行分片的**（index=0 全部发完才开始 index=1），但**不要依赖这一点**——
   协议允许交错，归并逻辑按 index 写就天然兼容两种；
4. **`finish_reason` 是解析时机的信号**：`tool_calls` 表示这轮要调工具，`stop` 表示纯文本回答。

## 二、usage 在哪：文档说的和实际发生的不是一回事

DeepSeek 文档写的是 OpenAI 的标准语义：设 `stream_options={"include_usage": true}` 时，
在 `data: [DONE]` 之前多传**一个额外的块**，该块 `usage` 有值而 **`choices` 始终是空数组**；
其余块的 `usage` 为 `null`。

**实测（`deepseek-v4-flash`，三方对照）**：

| 请求 | usage 在哪 | 那一块的 `choices` |
|---|---|---|
| 不传 `stream_options` | **末块**（第 43/43 块） | **非空**，带 `finish_reason=stop` |
| `include_usage: False` | **末块**（第 92/92 块） | **非空** |
| `include_usage: True` | **末块**（第 87/87 块） | **非空**，带 `finish_reason` |

即：**`include_usage` 是空操作，usage 永远白送在末块上，而且从来没有那个「choices 为空」的额外块。**

**这就是那个坑**。OpenAI 生态里最常见的组装写法是：

```python
for chunk in stream:
    if not chunk.choices:          # ← 惯用法：没有 choices 的就是 usage 块
        usage = chunk.usage
        continue
    delta = chunk.choices[0].delta
```

这段代码在 DeepSeek 上**那个分支永不触发**，`usage` 恒为 `None`。而 usage 通常喂给
预算/成本统计与上下文估算，两者失效都不报错——只是钱白花、上下文读数回到瞎猜。

**稳妥写法：不管 choices 空不空，每块都看一眼 `chunk.usage`，最后一个非空的就是它。**
两种协议形状都能吃下。

（对称的警告：反过来假设「usage 一定在末块」也不安全——那是 DeepSeek 的实测行为，
标准 OpenAI 会给独立块。「每块都看」是唯一同时正确的写法。）

## 三、中断掉的流，没有 usage

客户端中途 `break` 出迭代（用户按 Ctrl+C 的等价物），**拿不到任何 usage**——
它在末块，而我们没读到末块。

后果：**被中断的那次请求的消耗不会进任何账**。服务端照样按已生成的部分计费，
本地的累计用量却少算一笔。会话里中断得越多，账偏得越多，且方向恒定（**总是少算**）。

想不漏账只有两条路：请求前用估算预扣，或接受这个偏差并写明白。
（同类问题的另一面：有些实现会给「中断」造一条合成的 assistant 消息，
那条消息带的是**假 usage**，混进统计里是反方向的错——所以「哪些 usage 可信」
本身需要一条过滤规则，不能见到就加。）

## 四、并行工具调用**不会**让 usage 重复

一次流式响应 = 一份 usage，与这轮调了几个工具无关（实测：2 个并行 tool_calls，
1 份 usage；同一请求非流式跑一遍，tool_calls 数与 usage 形状完全一致）。

值得单独写一条，是因为**反直觉的说法在流传**：Anthropic 协议下，流式并行工具调用会让
每个 content block 成为一条独立的 assistant 记录、共享同一个 `message.id`，
天真地按记录累加就会重复计费。那是**那个协议的形状带来的**，不是流式的固有属性。

**判据**：问「一次 API 响应在我的数据结构里变成了几条记录」。
一条 → 没有这个问题；多条 → 需要一个「同源识别」字段（响应 id）把它们认回去。
**这是自己的建模选择决定的，不是协议强加的**——为了边流边显示而把一次响应拆成多条记录，
就是在给自己造这个 bug。

## 五、缓存字段在流式下没变

`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` / `reasoning_tokens`
在流式的末块 usage 里全在，口径与非流式一致（实测：同 prompt 的第二次请求命中缓存 384 token，
流式与非流式读数对得上）。**换成流式不需要重做成本核算的口径。**
