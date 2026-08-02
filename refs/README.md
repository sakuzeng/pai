# refs/ — 外部参考资料（本地快照）

给 AI 与人类协作者查证用。**注释里引用外部事实时，链接到这里的文件，不要凭记忆写**
（曾把 384K 的输出上限写成 8k，见 docs/dev/devlog.md）。

## deepseek-api/（不入库，需自行生成）

DeepSeek API 中文文档的本地快照，61 页。**版权归 DeepSeek**，因此不纳入版本管理
（已在 .gitignore 中排除），只保留生成脚本。

生成/更新：

```bash
brew install pandoc          # 仅首次
python3 refs/fetch_deepseek_docs.py
```

生成后索引见 `deepseek-api/INDEX.md`，每个文件头部标注来源 URL。以官网为准。

常查的几页：
- `quick_start/token_usage.md` — 官方 token 换算系数（中文 0.6 / 英文 0.3 每字符）
- `quick_start/pricing.md` — 价格与模型规格（v4-flash：1M 上下文 / 384K 输出）
- `guides/kv_cache.md` — 硬盘缓存的落盘与命中规则
- `guides/tool_calls.md` / `api/create-chat-completion.md` — 协议细节
- `quick_start/agent_integrations/pi_mono.md`、`claude_code.md` — 官方给这两个 harness 写的接入文档
