"""流式探针（feature 11 前置精读的「反向对照」，2026-08-11 用户授权花钱）。

三问，每问一次真实请求：
  A. stream=True 但**不传** stream_options —— usage 到底有没有？
     （pai 的预算熔断与锚点全押在 usage 上，没有就是静默失效）
  B. stream=True + include_usage + 两个工具诱发并行 tool_calls ——
     chunk 序列长什么样：tool_calls[].index 怎么分片、id/name 在哪块、
     末块 usage 有没有 prompt_cache_hit_tokens、reasoning_content 怎么来
  C. 同样的请求**不流式** —— 与 B 的 usage 对齐，验证
     「一次响应恰好一份 usage」在 OpenAI 协议下是否成立
     （TODO 那条「并行工具调用 usage 重复累加」抄自 CC，CC 走的是 Anthropic 协议）

原始 chunk 全量落 JSONL，供 features/11/evidence/ 归档。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pai.config import make_client, model_name  # noqa: E402

OUT = Path(__file__).resolve().parent / "streaming_probe_out"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市的当前天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_population",
            "description": "查询某个城市的人口",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名"}},
                "required": ["city"],
            },
        },
    },
]

PARALLEL_PROMPT = "帮我查北京的天气和上海的人口。两件事互不依赖，请在同一轮里一次性把需要的工具都调了。"


def dump(name: str, rows: list) -> Path:
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def probe_a(client, model) -> None:
    print("\n=== A · stream=True，不传 stream_options ===")
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "用一句话说说什么是流式输出。"}],
        stream=True,
        max_tokens=2048,
    )
    rows, usage_seen, n = [], [], 0
    for chunk in stream:
        d = chunk.model_dump()
        rows.append(d)
        n += 1
        if d.get("usage") is not None:
            usage_seen.append(d["usage"])
    path = dump("A_no_stream_options", rows)
    print(f"chunk 总数：{n}")
    print(f"带 usage 的 chunk 数：{len(usage_seen)}")
    print(f"末块 choices：{rows[-1].get('choices')}")
    if usage_seen:
        print(f"最后一个 usage：{json.dumps(usage_seen[-1], ensure_ascii=False)}")
    else:
        print("!!! 全程没有任何 usage —— 不传 stream_options 就等于没有用量数据")
    print(f"原始落盘：{path}")


def probe_b(client, model) -> None:
    print("\n=== B · stream=True + include_usage + 并行 tool_calls ===")
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PARALLEL_PROMPT}],
        tools=TOOLS,
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=4096,
    )
    rows = []
    # 按 index 归并 tool_calls 分片，顺便记下「哪些字段在第几块出现」
    frag_log: list[str] = []
    assembled: dict[int, dict] = {}
    reasoning_chunks = content_chunks = 0
    usage_blocks = []
    for i, chunk in enumerate(stream):
        d = chunk.model_dump()
        rows.append(d)
        if d.get("usage") is not None:
            usage_blocks.append((i, d["usage"], d.get("choices")))
        for ch in d.get("choices") or []:
            delta = ch.get("delta") or {}
            if delta.get("reasoning_content"):
                reasoning_chunks += 1
            if delta.get("content"):
                content_chunks += 1
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index")
                slot = assembled.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                bits = []
                if tc.get("id"):
                    slot["id"] = tc["id"]
                    bits.append(f"id={tc['id']}")
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                    bits.append(f"name={fn['name']}")
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
                    bits.append(f"arguments={fn['arguments']!r}")
                frag_log.append(f"  chunk#{i} index={idx} " + " ".join(bits))
            if ch.get("finish_reason"):
                frag_log.append(f"  chunk#{i} finish_reason={ch['finish_reason']}")
    path = dump("B_parallel_tool_calls", rows)
    print(f"chunk 总数：{len(rows)}；reasoning delta 块 {reasoning_chunks}，content delta 块 {content_chunks}")
    print(f"并行 tool_calls 数（按 index 去重）：{len(assembled)}")
    for idx in sorted(assembled):
        print(f"  index={idx} → {json.dumps(assembled[idx], ensure_ascii=False)}")
    print("分片时序（前 40 条）：")
    for line in frag_log[:40]:
        print(line)
    print(f"带 usage 的 chunk 数：{len(usage_blocks)}")
    for i, u, choices in usage_blocks:
        print(f"  chunk#{i} choices={choices} usage={json.dumps(u, ensure_ascii=False)}")
    print(f"原始落盘：{path}")


def probe_c(client, model) -> None:
    print("\n=== C · 同一请求不流式（对照组）===")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PARALLEL_PROMPT}],
        tools=TOOLS,
        max_tokens=4096,
    )
    d = resp.model_dump()
    dump("C_non_streaming", [d])
    tcs = d["choices"][0]["message"].get("tool_calls") or []
    print(f"tool_calls 数：{len(tcs)}")
    for tc in tcs:
        print(f"  {tc['id']} {tc['function']['name']} {tc['function']['arguments']}")
    print(f"usage：{json.dumps(d.get('usage'), ensure_ascii=False)}")
    print(f"finish_reason：{d['choices'][0].get('finish_reason')}")


def main() -> None:
    client, model = make_client(), model_name()
    print(f"模型：{model}")
    probe_a(client, model)
    probe_b(client, model)
    probe_c(client, model)


if __name__ == "__main__":
    main()
