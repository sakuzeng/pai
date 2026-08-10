"""流式探针第二轮：探针 A 的结果与 DeepSeek 官方文档不符，追证。

文档（refs/deepseek-api/api/create-completion.md）说：include_usage=true 时
「在最后的 data: [DONE] 之前传输一个**额外的块**，此块 choices **始终是空数组**」。
实测 A（不传 stream_options）却在**末块**（choices 非空、带 finish_reason）上就有 usage。

两种解释，必须分开：
  D. openai python SDK 偷偷替我加了 include_usage → 显式传 False 应当让 usage 消失
  E. DeepSeek 无论如何都在末块给 usage → 显式传 False 也还在

外加一问，直接关系到流式下的中断语义：
  F. 客户端中途 break（模拟 Ctrl+C 掐流）——拿不拿得到 usage？
     拿不到就意味着「中断掉的那次请求不计进预算」，spent_tokens 系统性少算。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pai.config import make_client, model_name  # noqa: E402

OUT = Path(__file__).resolve().parent / "streaming_probe_out"
PROMPT = "用两句话说说什么是 server-sent events。"


def run(client, model, label: str, **extra) -> None:
    print(f"\n=== {label} ===")
    print(f"额外参数：{extra}")
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        stream=True,
        max_tokens=2048,
        **extra,
    )
    rows, usage_at = [], []
    for i, chunk in enumerate(stream):
        d = chunk.model_dump()
        rows.append(d)
        if d.get("usage") is not None:
            usage_at.append((i, d["usage"], d.get("choices")))
    OUT.mkdir(exist_ok=True)
    (OUT / f"{label}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"chunk 总数：{len(rows)}；带 usage 的块：{[i for i, _, _ in usage_at]}")
    for i, u, choices in usage_at:
        empty = choices == [] or choices is None
        print(f"  chunk#{i}（末块={i == len(rows) - 1}，choices 为空={empty}）total_tokens={u['total_tokens']}")


def probe_f(client, model) -> None:
    print("\n=== F · 中途 break 掐流（模拟 Ctrl+C）===")
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "从 1 数到 200，每个数字单独一行。"}],
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=2048,
    )
    seen_usage, n = None, 0
    for chunk in stream:
        n += 1
        d = chunk.model_dump()
        if d.get("usage") is not None:
            seen_usage = d["usage"]
        if n >= 10:                      # 只读 10 块就走人
            break
    stream.close()
    print(f"读了 {n} 块就 break")
    print(f"break 之前见到 usage 了吗：{'见到 ' + str(seen_usage['total_tokens']) if seen_usage else '没有'}")
    print("→ 中断掉的请求拿不到 usage 的话，这次消耗就不会进 spent_tokens")


def main() -> None:
    client, model = make_client(), model_name()
    print(f"模型：{model}")
    run(client, model, "D_include_usage_false", stream_options={"include_usage": False})
    run(client, model, "E_include_usage_true", stream_options={"include_usage": True})
    probe_f(client, model)


if __name__ == "__main__":
    main()
