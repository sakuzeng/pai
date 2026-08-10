# 2026-08-11 · 召回真跑冒烟（原件）

D#56 的实测校正、[K concepts/reasoning-models-max-tokens.md](../../../../../knowledge/concepts/reasoning-models-max-tokens.md)
里引用的数字都来自这里。脚本原本在 `pai_playground/smoke/`（gitignore），
按 features/README 规矩 9 复制进版本库——否则 decisions 引用的数字没有可查证的原件。

| 文件 | 内容 |
|---|---|
| `recall_max_tokens.py` | max_tokens 阶梯量测脚本 |
| `recall_json_object.py` | 端到端召回冒烟（含 `response_format` 探针） |
| `max_tokens-阶梯输出.txt` | 阶梯量测的第二次运行输出 |
| `端到端输出-修复后.txt` | 修复后的端到端输出 |

**两次阶梯量测的结果不一样，这本身就是结论**（`deepseek-v4-flash`，同一 prompt 同一 query）：

| max_tokens | 第一次 reasoning / content | 第二次 reasoning / content |
|---|---|---|
| 256 | 218 / 有 | 51 / 有 |
| 512 | 112 / 有 | **512 / 空**（全烧在思考上） |
| 1024 | 79 / 有 | 55 / 有 |
| 2048 | 1941 / 有 | 38 / 有 |

**思考长度是抽签，而且不单调**——第二次跑里 512 失败而 256 成功。
所以「把上限调到刚好够」这个思路根本不成立：**没有一个小上限是安全的**，
唯一的防御是给足余量（计费按真实用量走，调高不额外花钱）。

跑法（会花钱，约 500 token/次）：`python3 recall_max_tokens.py`
