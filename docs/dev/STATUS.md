# 当前状态快照

最后更新：2026-08-09（体系补全：knowledge / features / roadmap 就位）。给接手者（人或 AI）一页看清现状。
「做了什么」的时间线见 [devlog.md](devlog.md)，「为什么这么选」见 [decisions.md](decisions.md)，
功能级故事线见 [features/](features/README.md)，阶段地图见 [roadmap.md](roadmap.md)。

## 一句话

agent loop + 工具系统 + 会话落盘已跑通；阶段 1 压缩做完了**地基**（token 秤、警戒线、
拍平机、上下文大小锚定），但**压缩本身还没接进 loop**——目前只测量、不决策、不压。
动工前清障（P0 五条 R#3/4/7/8/9）**已全部清完**，`find_cut_point` 可动工；
该功能全貌见 [features/02-20260803-compaction/](features/02-20260803-compaction/README.md)。

## 模块现状

| 模块 | 状态 | 说明 |
|---|---|---|
| `core/loop.py` | 可用 | agent loop：依赖注入、max_steps 兜底、每条消息落盘、usage 落盘、用量预算熔断 |
| `core/tools/` | 可用 | `@tool` 从签名生成 schema；bash / read_file / write_file / edit_file |
| `core/session.py` | 可用 | append-only JSONL |
| `core/compaction.py` | **部分** | 见下 |
| `modes/once.py` | 可用 | 单次任务，跑完即退出（对应 pi 的 print-mode）。client/model 可注入故可离线测 |
| `viz/` | 可用 | `pai-viz` 本地架构可视化：工具自省自动上图，阶段状态解析本表 |
| `cli.py` / `config.py` | 可用 | cli 只做参数解析与分发；OpenAI 兼容协议打 DeepSeek |
| `modes/interactive.py` | 未开始 | REPL。结构已预留，加一个文件即可，core 不动 |
| memory / permissions / streaming / skills / mcp_client / evals | 未开始 | 路线图后续阶段，见 [roadmap.md](roadmap.md) |

## compaction.py 里有什么

| 函数 | 干什么 | 接进 loop 了吗 |
|---|---|---|
| `estimate_tokens` | 单条消息 token 估算，中英文分别按官方系数（0.6 / 0.3） | 间接 |
| `estimate_conversation_tokens` | 整段消息求和 | 间接 |
| `estimate_request_tokens` | 加上工具 schema，对齐 provider 的 prompt_tokens 口径 | 间接 |
| `context_tokens` | **以真实 usage 为锚 + 增量估算**，误差 1.3% | ✅ 每步算，落盘 |
| `should_compact` | 阈值判断（`tokens > window - reserve_tokens`） | ❌ **没接** |
| `serialize_conversation` | 拍平成文本喂摘要模型 | ❌ 无调用方 |
| `CompactionSettings` | `reserve_tokens=16384`、`enabled=True` | ❌ 没接 |

**还没写**：`find_cut_point`（在哪下刀）、`summarize`（调模型摘要）、`compact`（把两者接起来）。

## 实测数据（真实跑出来的，非推测）

- 上下文估算误差：无锚 **-33%** → 锚定后 **-1.3%**
- 缓存命中率：单次会话 **91.6%**，全天统计 **84.7%**
- `deepseek-v4-flash`：上下文 **1M**、输出上限 **384K**；缓存命中 0.02 元/M vs 未命中 1 元/M（**50 倍**）
- 按 `reserve_tokens=16384`，压缩触发点是 **983,616** token——以当前用量（全天 3 万）几乎不会触发

## 测试

共收集 **93 项**（2026-08-09 新增：3 条文档一致性、10 条方案门禁、7 条评审修复钉子，
见 features/03、04 档案）：

- `./test.sh` → **92 passed, 1 deselected**，全部离线（`tests/fake_llm.py` 假 provider）。**这是默认路径。**
- `./test.sh --llm` → 额外跑 1 条打真实 API 的冒烟测试，**会产生费用**。
  需同时满足有 `DEEPSEEK_API_KEY` 且 `PAI_RUN_LLM_TESTS=1`——花钱的副作用不能是默认行为。

两份真实轨迹夹具内联在 `tests/test_compaction.py`：
`REAL_TRAJECTORY`（含一条真实的 sed 失败）、`REAL_USAGE_TRAJECTORY` + `REAL_USAGE_STEPS`。

## 已知缺陷（详细条目在 [archive/devlog-2026-08.md](archive/devlog-2026-08.md)）

1. **锚与压缩天然冲突，且重置后有读数盲区**（评审 R#7，比原自评更严重）。
   锚假设历史 append-only，而压缩会改写历史——`compact()` 必须把 `anchor` 重置为 `None`。
   但**重置之后到下一次真实 usage 回来之前，读数退化为纯估算（-33%）**，
   而那恰是最需要准确回答「压缩救回来了没有」的时刻（熔断器靠它决定要不要继续压）。
   低估方向尤其危险：会让压缩后的上下文**看起来比实际小**，
   于是误判「压成功了」而放行，下一轮直接爆窗口。
   → 裁决见 decisions 第 34 条：**熔断器不看估算值，等下一次真实 usage 回传再判。**
2. `estimate_tokens` 系统性低估约 **1.5 倍**（chat template 框架开销 + 工具 schema）。
   **仍不修**，但**理由已换**——原理由（「均匀偏差不影响切点」）已被推翻，
   见 decisions 第 19 条（划掉保留）与第 32 条（改用真实 usage 差值定切点）。
   补充实测：偏差**不均匀**——短 tool 结果低估 4-5 倍，长消息只低估约 2%。
3. `reserve_tokens=16384` 无实测依据，照搬 pi 并按 DeepSeek 反推。
4. `should_compact` 有退化情形：`window <= reserve_tokens` 时恒为 True，
   需上层熔断器兜底（decisions 第 14 条），尚未实现。
5. 拍平 vs 原样发（decisions 第 12/16 条）：缓存价差 50 倍使 CC 的「原样发」在成本上
   反超 pi 的「拍平」约 32 倍，但 CC 自陈有百分之几的不听话率，DeepSeek 上未知。
   **待实现 summarize 时实测再定**。
6. `pai_playground/sessions/` 被 .gitignore 排除，而测试夹具的原始出处在那里——溯源链断了。

## 下一步

`find_cut_point`（在哪下刀）→ `summarize`（调模型摘要）→ `compact`（接起来，带熔断器）。
走 superpowers 全链路，spec/plan/devlog 落 [features/02-20260803-compaction/](features/02-20260803-compaction/README.md)；
动工前先过 roadmap 阶段 1「前置精读」（已 ✓）。
