# 测试夹具

**真跑产生的轨迹一旦被当作测试夹具，须复制进版本库**（AGENTS.md 测试规约）——
否则溯源链断在一个 gitignore 掉的目录里（这正是 STATUS 缺陷 6 记的那件事）。

| 文件 | 出处 | 用在哪 |
|---|---|---|
| `real_turn.jsonl` | `pai_playground/sessions/20260803-000946.jsonl`（真跑，2026-08-03），已剥掉 `SessionLog` 加的 `ts` 字段 | `tests/test_tui_dock.py` 的真实轨迹驱动测试 |
| `real_session.jsonl` | `~/.pai/projects/<本仓库>/sessions/20260811-024816-110ae765.jsonl`（真跑，2026-08-11），**原样保留 `ts`** | `tests/test_viz_flow.py`（feature 17）的 turn 分组与配对 |

`real_session.jsonl` 是唯一一份**带 `ts`** 的夹具，与上面那条「抄进来要剥 ts」的规约不冲突：
剥 ts 是因为那些测试不关心时间、留着只是噪音；而这一份里 `ts` **正是被测对象**
（turn 排序、两个流按时间合并、工具耗时全靠它）。剥掉就等于测不到。

它的价值在于三处编不出来的真实形状：一条 assistant 里**两个并发 `read_file` 调用**
（feature 11 的保序分批跑出来的）、真实的 `call_00_eYpVDzjffTKaD6HqyCUX7545` id 格式、
`usage` 里 `prompt_cache_hit_tokens` / `prompt_tokens_details.cached_tokens`
**两套缓存字段并存**（provider 同时给了两种口径）。
