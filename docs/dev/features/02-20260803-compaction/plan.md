# 02-compaction 压缩闭环 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 find_cut_point / summarize / compact 接进 loop，压缩闭环在真实轨迹上跑通（spec.md 已批）。

**Architecture:** 全部判定逻辑做成 compaction.py 的纯函数/纯数据类（AnchorBook、find_cut_point、CompactionState），loop 只做接线；摘要喂料双模式（flat/raw）由实测裁决默认值；压缩成败只认压缩后首次真实 usage（D#34），连续失败 3 次熔断。

**Tech Stack:** Python 3.9.6（`from __future__ import annotations` 必配）、pytest、tests/fake_llm.py 假 provider。

## Global Constraints

- TDD 铁律：每个 task 先红后绿，红绿的真实 pytest 数字进 `devlog.md`（本目录）。
- 离线铁律：除 Task 4 的 `@pytest.mark.llm` 实测外，一切测试不打真实 API。
- 工具错误不 throw；loop 不因单步失败而崩（AGENTS.md 架构约束）。
- 切点铁律：保留段绝不以 `role=="tool"` 开头（孤儿 tool_result 会 400）。
- 类型注解必写；3.9 下 `int | None` 语法需 future import（两个目标文件已有）。
- commit 格式 `{feat,fix,test}(compaction): ...`，分支 `feat/compaction`。
- 每个 task 的实现里禁止出现「TODO/以后再说」——遗留必须落全局 TODO.md。

---

### Task 1: AnchorBook——锚点列表化（D#32 实现要求）

**Files:**
- Modify: `src/pai/core/compaction.py`（追加 AnchorBook）
- Modify: `src/pai/core/loop.py:62-64,109-111`（单锚变量 → AnchorBook）
- Test: `tests/test_compaction.py`、`tests/test_loop.py`

**Interfaces:**
- Produces: `AnchorBook`——`record(message_index: int, real_tokens: int)`、`latest() -> "tuple[int | None, int]"`（返回 `(anchor, anchor_index)`，无锚时 `(None, 0)`）、`entries: list[tuple[int, int]]`（升序，供 Task 3 消费）、`reset()`（压缩后清空，D#18/32）。
- 语义：`entries[i] = (该锚覆盖到的 message 下标, 到此为止的累计真实 token)`；相邻差值即该轮真实成本。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_compaction.py` 末尾）

```python
class TestAnchorBook:
    def test_records_and_latest(self):
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        assert book.latest() == (None, 0)      # 无锚时 context_tokens 走纯估算
        book.record(3, 1000)                   # 第 1 轮后：messages 前 3 条 = 1000 真实 token
        book.record(5, 1075)
        assert book.latest() == (1075, 5)
        assert book.entries == [(3, 1000), (5, 1075)]

    def test_turn_cost_is_adjacent_difference(self):
        """D#32：第 N 轮新增消息的真实成本 = 相邻锚差值——实测 42/33/43 的那套语义。"""
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        book.record(3, 100)
        book.record(5, 142)
        book.record(7, 175)
        costs = [b - a for (_, a), (_, b) in zip(book.entries, book.entries[1:])]
        assert costs == [42, 33]

    def test_reset_clears_everything(self):
        """压缩改写历史后旧锚全部作废（D#18/D#32 前提：append-only）。"""
        from pai.core.compaction import AnchorBook

        book = AnchorBook()
        book.record(3, 1000)
        book.reset()
        assert book.latest() == (None, 0)
        assert book.entries == []
```

- [ ] **Step 2: 跑测试确认红**

Run: `python3 -m pytest tests/test_compaction.py::TestAnchorBook -v`
Expected: FAIL, `ImportError: cannot import name 'AnchorBook'`

- [ ] **Step 3: 最小实现**（追加到 `src/pai/core/compaction.py`，放在 `context_tokens` 之前）

```python
@dataclass
class AnchorBook:
    """真实 usage 锚点簿（D#32）：单锚只够判「该不该压」，切点计算需要完整列表。

    entries[i] = (锚覆盖到的 message 下标, 累计真实 token)；相邻差值 = 该轮真实成本。
    压缩会改写历史，必须 reset()——锚定法假设 append-only。
    """

    entries: list[tuple[int, int]] = field(default_factory=list)

    def record(self, message_index: int, real_tokens: int) -> None:
        self.entries.append((message_index, real_tokens))

    def latest(self) -> tuple[int | None, int]:
        if not self.entries:
            return None, 0
        index, tokens = self.entries[-1]
        return tokens, index

    def reset(self) -> None:
        self.entries.clear()
```

同文件顶部 import 行 `from dataclasses import dataclass` 改为
`from dataclasses import dataclass, field`。

- [ ] **Step 4: loop 换用 AnchorBook**（`src/pai/core/loop.py`）

把 66 行前的
```python
    anchor: int | None = None
    anchor_index = 0
```
改为
```python
    anchors = AnchorBook()
```
`context_tokens(...)` 调用处改为
```python
        anchor, anchor_index = anchors.latest()
        estimated = context_tokens(
            messages, tool_schemas, anchor=anchor, anchor_index=anchor_index
        )
```
109-111 行的锚顺延改为
```python
        if usage and usage.get("prompt_tokens") is not None:
            anchors.record(
                len(messages), usage["prompt_tokens"] + (usage.get("completion_tokens") or 0)
            )
```
import 行加 `AnchorBook`：`from pai.core.compaction import AnchorBook, context_tokens`。

- [ ] **Step 5: 跑全量确认既有锚簿记测试仍绿**

Run: `./test.sh`
Expected: 全绿（`test_anchor_bookkeeping_is_exact` 等 2 条既有精确断言不许动——它们钉的语义没变）。

- [ ] **Step 6: Commit**

```bash
git add src/pai/core/compaction.py src/pai/core/loop.py tests/test_compaction.py
git commit -m "feat(compaction): AnchorBook 锚点列表化，loop 换用（D#32 前置）"
```

---

### Task 2: 并行 tool_calls 配对不变量（R#11，有真实 400 复现）

**Files:**
- Test: `tests/test_loop.py`（只加测试；loop 逻辑上已处理，红了才改 src）

**Interfaces:** 无新接口。钉住的不变量供 Task 6 的 e2e 依赖：一轮 N 个 tool_calls 必须回填 N 条 role=tool 消息、id 一一配对、顺序一致。

- [ ] **Step 1: 写测试**（追加到 `tests/test_loop.py` 末尾；FakeClient 的 turn 格式见 `tests/fake_llm.py` 头注释）

```python
def test_parallel_tool_calls_each_get_a_reply(tmp_path, monkeypatch):
    """DeepSeek 实测一次回 3 个并行 tool_calls；漏回任何一条下轮即 400（R#11）。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [
            ("bash", json.dumps({"command": "true"})),
            ("bash", json.dumps({"command": "echo a"})),
            ("bash", json.dumps({"command": "echo b"})),
        ]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None)
    sent = client.requests[1]["messages"]           # 第二次请求 = 回填后的完整历史
    assistant = next(m for m in sent if m["role"] == "assistant" and m.get("tool_calls"))
    call_ids = [tc["id"] for tc in assistant["tool_calls"]]
    tool_msgs = [m for m in sent if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == call_ids   # N 条、同序、一一配对


def test_parallel_tool_calls_mixed_known_and_unknown(tmp_path, monkeypatch):
    """合法工具与未知工具同轮混发：未知的也必须回填错误消息，不许漏配对。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [
            ("bash", json.dumps({"command": "true"})),
            ("no_such_tool", json.dumps({})),
        ]},
        {"content": "done"},
    ]
    client = FakeClient(script)
    run_agent("x", client=client, model="fake", tools=get_tools(),
              on_event=lambda _: None)
    tool_msgs = [m for m in client.requests[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert "未知工具" in tool_msgs[1]["content"]
```

- [ ] **Step 2: 跑测试**

Run: `python3 -m pytest tests/test_loop.py -k parallel -v`
Expected: PASS（这是钉不变量的 characterization 测试——loop 现有实现逻辑正确但零覆盖；若意外红，修 loop 而不是改测试）。

- [ ] **Step 3: Commit**

```bash
git add tests/test_loop.py
git commit -m "test(loop): 钉死并行 tool_calls 配对不变量（R#11，真实 400 场景）"
```

---

### Task 3: find_cut_point——真实 usage 差值定切点

**Files:**
- Modify: `src/pai/core/compaction.py`（追加 find_cut_point；CompactionSettings 加 keep_recent_tokens）
- Test: `tests/test_compaction.py`

**Interfaces:**
- Consumes: Task 1 的 `AnchorBook.entries`。
- Produces: `find_cut_point(messages: Sequence[Mapping[str, object]], anchors: Sequence[tuple[int, int]], *, keep_recent_tokens: int = 20000) -> int`——返回保留段起点下标 `cut`；`messages[cut:]` 保留、`messages[1:cut]` 待摘要（下标 0 的 system 永远保留）。**返回 `1` 表示无可压**（超长单轮/锚不足），调用方走「不压+警告」（spec 非目标裁决）。
- `CompactionSettings` 新增字段 `keep_recent_tokens: int = 20000`（照 pi 的 keepRecentTokens；与 reserve 一样待实测校准，注释写明）。

- [ ] **Step 1: 写失败测试**

```python
class TestFindCutPoint:
    def _msgs(self, n):
        out = [{"role": "system", "content": "s"}]
        for i in range((n - 1) // 2):
            out.append({"role": "assistant", "content": None,
                        "tool_calls": [{"id": f"c{i}", "type": "function",
                                        "function": {"name": "bash", "arguments": "{}"}}]})
            out.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"})
        return out

    def test_cuts_at_anchor_keeping_recent_budget(self):
        from pai.core.compaction import find_cut_point

        msgs = self._msgs(9)                       # system + 4 轮 (assistant, tool)
        anchors = [(3, 100), (5, 300), (7, 600), (9, 1000)]
        # 从最新往回累计真实差值：9←7 是 400，>=350 即停 → 切在下标 7
        assert find_cut_point(msgs, anchors, keep_recent_tokens=350) == 7

    def test_never_starts_kept_segment_with_tool_result(self):
        """切点铁律：落在 role=tool 上就前移到该轮 assistant——绝不产生孤儿 tool_result。"""
        from pai.core.compaction import find_cut_point

        msgs = self._msgs(9)
        anchors = [(4, 100), (6, 300), (8, 600)]   # 锚故意落在 tool 消息下标上
        cut = find_cut_point(msgs, anchors, keep_recent_tokens=250)
        assert msgs[cut]["role"] != "tool"

    def test_returns_1_when_nothing_can_be_cut(self):
        """锚不足两个 / 预算大到全保留 → 返回 1（无可压），调用方走不压+警告。"""
        from pai.core.compaction import find_cut_point

        msgs = self._msgs(9)
        assert find_cut_point(msgs, [], keep_recent_tokens=100) == 1
        assert find_cut_point(msgs, [(9, 50)], keep_recent_tokens=100) == 1
        anchors = [(3, 100), (9, 200)]
        assert find_cut_point(msgs, anchors, keep_recent_tokens=99999) == 1
```

- [ ] **Step 2: 跑测试确认红**

Run: `python3 -m pytest tests/test_compaction.py::TestFindCutPoint -v`
Expected: FAIL, `ImportError: cannot import name 'find_cut_point'`

- [ ] **Step 3: 最小实现**（追加到 compaction.py；CompactionSettings 加字段）

```python
def find_cut_point(
    messages: Sequence[Mapping[str, object]],
    anchors: Sequence[tuple[int, int]],
    *,
    keep_recent_tokens: int = 20000,
) -> int:
    """在哪下刀（D#32）：从最新锚往回累计真实差值，够 keep_recent_tokens 即停。

    只在锚点边界下刀——真实成本只能按轮次反推，粒度天然对齐。返回保留段起点；
    1 = 无可压（锚不足 / 预算吞下全部历史），调用方按 spec 裁决走「不压 + 警告」。
    落点若是 tool 消息则前移，绝不让保留段以孤儿 tool_result 开头。
    """
    if len(anchors) < 2:
        return 1
    _, latest_total = anchors[-1]
    cut = 1
    for index, total in reversed(anchors[:-1]):
        if latest_total - total >= keep_recent_tokens:
            cut = index
            break
    while 0 < cut < len(messages) and messages[cut].get("role") == "tool":
        cut -= 1                       # 前移方向 = 多保留，宁多勿孤儿
    return max(cut, 1)
```

`CompactionSettings` 增加一行字段（docstring 补一句「keep_recent_tokens 照 pi，
与 reserve 同样待实测校准」）：

```python
    keep_recent_tokens: int = 20000
```

- [ ] **Step 4: 跑测试确认绿，随后全量**

Run: `python3 -m pytest tests/test_compaction.py::TestFindCutPoint -v && ./test.sh`
Expected: PASS / 全绿

- [ ] **Step 5: Commit**

```bash
git add src/pai/core/compaction.py tests/test_compaction.py
git commit -m "feat(compaction): find_cut_point 用真实 usage 差值定切点（D#32）"
```

---

### Task 4: summarize 双模式 + 花钱实测脚手架

**Files:**
- Modify: `src/pai/core/compaction.py`（SUMMARY_INSTRUCTIONS、summarize）
- Create: `tests/test_llm_summarize_experiment.py`（`@pytest.mark.llm`，唯一花钱步骤，已获用户授权 ≤1 元）
- Test: `tests/test_compaction.py`（离线部分）

**Interfaces:**
- Produces: `summarize(messages: Sequence[Mapping[str, object]], *, client, model: str, style: str = "flat", instructions: str | None = None) -> tuple[str, dict]`——返回 `(摘要文本, usage_dict)`；`style="flat"` 拍平喂料（serialize_conversation，跳过 system——R#16），`style="raw"` 原样发消息数组；`instructions` 覆盖默认保留清单（官方 compact 自定义指令同款能力）。usage 用 `loop._usage_fields` 同款提取逻辑——为避免跨模块 import 私有函数，把 `_usage_fields` **从 loop.py 移到 compaction.py 并改名 `usage_fields`**，loop 改为 `from pai.core.compaction import usage_fields`（函数体一字不动，既有 loop 测试守护此迁移）。
- `SUMMARY_INSTRUCTIONS`：模块常量，官方六项保留清单（context-management.md 笔记）。

- [ ] **Step 1: 写失败测试（离线）**

```python
class TestSummarize:
    def _msgs(self):
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "建个文件"},
            {"role": "assistant", "content": "好的，done"},
        ]

    def test_flat_style_feeds_serialized_text_without_system(self):
        from fake_llm import FakeClient
        from pai.core.compaction import summarize

        client = FakeClient([{"content": "摘要文本", "usage": {"prompt_tokens": 10,
                             "completion_tokens": 5, "total_tokens": 15}}])
        text, usage = summarize(self._msgs(), client=client, model="fake", style="flat")
        assert text == "摘要文本"
        assert usage["total_tokens"] == 15
        sent = client.requests[0]["messages"]
        assert len(sent) == 2                       # system(指令) + user(拍平文本)
        assert "sys" not in sent[1]["content"]      # R#16：原 system 不进拍平文本
        assert "建个文件" in sent[1]["content"]
        assert "tools" not in client.requests[0]    # 摘要请求不带工具

    def test_raw_style_sends_original_messages(self):
        from fake_llm import FakeClient
        from pai.core.compaction import summarize

        client = FakeClient([{"content": "s", "usage": {"total_tokens": 1}}])
        summarize(self._msgs(), client=client, model="fake", style="raw")
        sent = client.requests[0]["messages"]
        assert {"role": "user", "content": "建个文件"} in sent   # 原消息原样在场
        assert sent[-1]["role"] == "user" and "摘要" in sent[-1]["content"]  # 末尾追加摘要指令

    def test_instructions_override_default(self):
        from fake_llm import FakeClient
        from pai.core.compaction import SUMMARY_INSTRUCTIONS, summarize

        client = FakeClient([{"content": "s", "usage": {}}])
        summarize(self._msgs(), client=client, model="fake", instructions="只保留文件名")
        joined = "".join(m["content"] for m in client.requests[0]["messages"])
        assert "只保留文件名" in joined and SUMMARY_INSTRUCTIONS[:8] not in joined
```

- [ ] **Step 2: 跑测试确认红**

Run: `python3 -m pytest tests/test_compaction.py::TestSummarize -v`
Expected: FAIL, `ImportError: cannot import name 'summarize'`

- [ ] **Step 3: 实现**（追加到 compaction.py；`usage_fields` 自 loop.py 原样迁入并去下划线，loop.py 改 import——迁移函数体禁止改动一个字符）

```python
SUMMARY_INSTRUCTIONS = (
    "你在为一段编码 agent 的对话历史写交接摘要，续任者只靠它接着干活。必须保留：\n"
    "1) 用户的请求与意图 2) 关键技术概念 3) 检查/修改过的文件与重要代码片段\n"
    "4) 出过的错误与修法 5) 未完成的待办 6) 当前正在做的事。\n"
    "只输出摘要正文，不要评论任务本身，更不要继续执行任务。"
)


def summarize(
    messages: Sequence[Mapping[str, object]],
    *,
    client,
    model: str,
    style: str = "flat",
    instructions: str | None = None,
) -> tuple[str, dict]:
    """调模型生成摘要。style 由实测裁决默认值（spec 问 1）：flat=拍平，raw=原样发。

    不带 tools——摘要请求绝不该触发工具调用；这也是「继续干活」误解的第一道防线。
    """
    prompt = instructions or SUMMARY_INSTRUCTIONS
    if style == "flat":
        body = serialize_conversation(m for m in messages if m.get("role") != "system")
        request: list[dict] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"待摘要的对话记录：\n{body}"},
        ]
    elif style == "raw":
        request = [dict(m) for m in messages if m.get("role") != "system"]
        request.append({"role": "user", "content": f"停下手头任务。{prompt}\n现在输出上面全部对话的摘要。"})
    else:
        raise ValueError(f"未知 style: {style!r}（只认 flat / raw）")

    response = client.chat.completions.create(model=model, messages=request)
    text = response.choices[0].message.content or ""
    return text, usage_fields(response)
```

- [ ] **Step 4: 跑离线测试确认绿，随后全量**

Run: `python3 -m pytest tests/test_compaction.py::TestSummarize -v && ./test.sh`
Expected: PASS / 全绿（loop 的 usage 相关测试守护 `usage_fields` 迁移无损）。

- [ ] **Step 5: 写实测脚手架**（新文件 `tests/test_llm_summarize_experiment.py`；跑法沿用 test_llm_smoke 的双开关门）

```python
"""拍平 vs 原样发实测（spec 问 1/问 3，用户已授权 ≤1 元）。

跑法：./test.sh --llm（需 DEEPSEEK_API_KEY + PAI_RUN_LLM_TESTS=1）。
原始请求/响应/usage 归档进功能目录 evidence/，裁决进 decisions——数据可查证原件。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from pai.config import make_client, model_name
from pai.core.compaction import summarize
from test_compaction import REAL_TRAJECTORY

EVIDENCE = (Path(__file__).resolve().parent.parent / "docs" / "dev" / "features"
            / "02-20260803-compaction" / "evidence")

pytestmark = pytest.mark.llm


@pytest.mark.parametrize("style", ["flat", "raw"])
def test_summarize_experiment(style):
    client, model = make_client(), model_name()
    out_dir = EVIDENCE / f"{time.strftime('%Y%m%d')}-拍平vs原样发实测"
    out_dir.mkdir(parents=True, exist_ok=True)
    for run in range(3):
        text, usage = summarize(REAL_TRAJECTORY, client=client, model=model, style=style)
        (out_dir / f"{style}-run{run}.json").write_text(
            json.dumps({"style": style, "run": run, "summary": text, "usage": usage},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        assert text.strip(), f"{style} run{run} 摘要为空"
```

- [ ] **Step 6: 跑实测并把数据落 decisions**

Run: `./test.sh --llm`（此步之外全程禁打真实 API）
Expected: 6 个 JSON 落 evidence/。随后**人工判读**：逐份看 summary 是「摘要」还是「继续干活」（不听话率）、比 usage 的含缓存成本与摘要长度 → decisions 追加一条（裁决 flat 还是 raw 为默认、顺带用真实摘要长度评 reserve_tokens=16384）→ **若裁决为 raw，把 summarize 的 `style: str = "flat"` 默认值改为 `"raw"` 并让本 task 测试同步**。判读结论若两可，交用户仲裁（工作流的计划冲突仲裁点）。

- [ ] **Step 7: Commit**

```bash
git add src/pai/core/compaction.py src/pai/core/loop.py tests/test_compaction.py tests/test_llm_summarize_experiment.py docs/dev/features/02-20260803-compaction/evidence docs/dev/decisions.md
git commit -m "feat(compaction): summarize 双模式 + 实测脚手架，evidence 归档实测数据"
```

---

### Task 5: compact + 熔断状态机（D#34）

**Files:**
- Modify: `src/pai/core/compaction.py`（CompactionState、verify_compaction、compact、MAX_COMPACT_FAILURES）
- Test: `tests/test_compaction.py`

**Interfaces:**
- Produces:
  - `MAX_COMPACT_FAILURES = 3`（对齐 CC，D#14）。
  - `@dataclass CompactionState: failures: int = 0; awaiting_verify: bool = False; tripped: bool = False`——loop 每次 run 持有一份。
  - `compact(messages, *, cut: int, client, model, style: str = "flat", instructions: str | None = None) -> tuple[list[dict], str]`——返回 `(新消息列表, 摘要文本)`；新列表 = `[原 system, 摘要消息] + messages[cut:]`，摘要消息为 `{"role": "user", "content": "[早前对话的摘要，供延续任务用]\n" + summary}`（用 user 而非 system：OpenAI 兼容协议下多条 system 的支持度参差，user 前缀最稳）。调用方负责 `anchors.reset()` 与 `state.awaiting_verify = True`。
  - `verify_compaction(prompt_tokens: int, window: int, settings: CompactionSettings, state: CompactionState) -> CompactionState`——D#34：压缩后**首次真实 prompt_tokens** 仍超线 → `failures + 1`，达 `MAX_COMPACT_FAILURES` 置 `tripped=True`；降回线内 → `failures = 0`。任何情况都清 `awaiting_verify`。返回新 state（frozen 语义，纯函数可测）。

- [ ] **Step 1: 写失败测试**

```python
class TestCompactAndBreaker:
    def _msgs(self):
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "recent"},
        ]

    def test_compact_rebuilds_with_summary_as_user(self):
        from fake_llm import FakeClient
        from pai.core.compaction import compact

        client = FakeClient([{"content": "这是摘要", "usage": {}}])
        new, summary = compact(self._msgs(), cut=3, client=client, model="fake")
        assert summary == "这是摘要"
        assert new[0] == {"role": "system", "content": "sys"}       # system 原样保留
        assert new[1]["role"] == "user" and "这是摘要" in new[1]["content"]
        assert new[2:] == self._msgs()[3:]                           # 保留尾原样
        assert all(m["role"] != "tool" for m in new[:3])

    def test_verify_counts_failure_only_on_real_usage_still_over(self):
        """D#34：成败只认压缩后首次真实 usage；降回线内清零计数。"""
        from pai.core.compaction import (CompactionSettings, CompactionState,
                                         verify_compaction)

        settings = CompactionSettings(reserve_tokens=200)
        state = CompactionState(awaiting_verify=True)
        state = verify_compaction(950, 1000, settings, state)        # 仍超线（>800）
        assert state.failures == 1 and not state.awaiting_verify
        state.awaiting_verify = True
        state = verify_compaction(500, 1000, settings, state)        # 降回线内
        assert state.failures == 0

    def test_breaker_trips_after_three_consecutive_failures(self):
        from pai.core.compaction import (CompactionSettings, CompactionState,
                                         verify_compaction)

        settings = CompactionSettings(reserve_tokens=200)
        state = CompactionState()
        for _ in range(3):
            state.awaiting_verify = True
            state = verify_compaction(999, 1000, settings, state)
        assert state.tripped                                          # 第 3 次即熔断
```

- [ ] **Step 2: 跑测试确认红**

Run: `python3 -m pytest tests/test_compaction.py::TestCompactAndBreaker -v`
Expected: FAIL, `ImportError: cannot import name 'compact'`

- [ ] **Step 3: 实现**（追加到 compaction.py）

```python
MAX_COMPACT_FAILURES = 3   # 对齐 CC（D#14）：没有熔断时真实事故是数千次连续失败


@dataclass
class CompactionState:
    """熔断状态机（D#34）：压缩后不立即判成败，等首次真实 usage 回传。"""

    failures: int = 0
    awaiting_verify: bool = False
    tripped: bool = False


def verify_compaction(
    prompt_tokens: int,
    window: int,
    settings: CompactionSettings,
    state: CompactionState,
) -> CompactionState:
    """压缩后首次真实 prompt_tokens 才是裁决依据——估算在此刻低估 33%，信它必炸（D#34）。"""
    still_over = prompt_tokens > window - settings.reserve_tokens
    failures = state.failures + 1 if still_over else 0
    return CompactionState(
        failures=failures,
        awaiting_verify=False,
        tripped=state.tripped or failures >= MAX_COMPACT_FAILURES,
    )


def compact(
    messages: Sequence[Mapping[str, object]],
    *,
    cut: int,
    client,
    model: str,
    style: str = "flat",
    instructions: str | None = None,
) -> tuple[list[dict], str]:
    """切 + 摘 + 重建。调用方随后必须 anchors.reset() 并置 state.awaiting_verify。

    摘要消息用 user role：OpenAI 兼容协议下多条 system 支持度参差，user 前缀最稳。
    """
    summary, _usage = summarize(
        messages[:cut], client=client, model=model, style=style, instructions=instructions
    )
    rebuilt: list[dict] = [dict(messages[0])]
    rebuilt.append({"role": "user", "content": f"[早前对话的摘要，供延续任务用]\n{summary}"})
    rebuilt.extend(dict(m) for m in messages[cut:])
    return rebuilt, summary
```

- [ ] **Step 4: 跑测试确认绿，随后全量**

Run: `python3 -m pytest tests/test_compaction.py::TestCompactAndBreaker -v && ./test.sh`
Expected: PASS / 全绿

- [ ] **Step 5: Commit**

```bash
git add src/pai/core/compaction.py tests/test_compaction.py
git commit -m "feat(compaction): compact 重建 + 熔断状态机，成败只认真实 usage（D#34）"
```

---

### Task 6: 接线进 loop + 端到端（含超长单轮警告）

**Files:**
- Modify: `src/pai/core/loop.py`（run_agent 加参 + 触发块 + verify 块）
- Modify: `src/pai/config.py`、`src/pai/modes/once.py`（window 接线）
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: Task 1/3/4/5 的全部产物（签名见各 task Produces）。
- Produces:
  - `run_agent(..., context_window: int | None = None, compaction: CompactionSettings | None = None)`——两者都给才启用压缩；默认 None = 行为与现状完全一致（既有全部测试零改动的保证）。
  - `config.context_window() -> int`：`PAI_CONTEXT_WINDOW` env，默认 `1_000_000`（v4-flash）。
  - `once.run_once` 透传：`context_window=context_window(), compaction=CompactionSettings()`。
  - session 落盘新记录 `{"type": "compaction", "step": N, "cut": i, "summary": ..., "estimated_before": ..., "estimated_after": ...}`。

- [ ] **Step 1: 写失败测试**

```python
def _usage(prompt, completion=10):
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion}


def test_loop_compacts_when_over_threshold(tmp_path, monkeypatch):
    """e2e：超线 → 切 → 摘（fake 扮演摘要模型）→ 重建 → 锚重置 → 继续任务。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(100)},
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(700)},
        {"content": "这是摘要"},                                   # ← 压缩触发的摘要请求
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(300)},
        {"content": "done"},
    ]
    client = FakeClient(script)
    settings = CompactionSettings(reserve_tokens=200, keep_recent_tokens=500)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       context_window=1000, compaction=settings, on_event=lambda _: None)
    assert answer == "done"
    summary_req = client.requests[2]                    # 第 3 次 create = 摘要请求
    assert "tools" not in summary_req
    after = client.requests[3]["messages"]              # 压缩后的下一次任务请求
    assert any("[早前对话的摘要" in (m.get("content") or "") for m in after)
    assert after[0]["role"] == "system"
    assert all(after[i]["role"] != "tool" or             # 无孤儿 tool_result
               after[i - 1].get("tool_calls") or after[i - 1]["role"] == "tool"
               for i in range(1, len(after)))


def test_loop_warns_not_compacts_when_no_cut_available(tmp_path, monkeypatch):
    """超长单轮裁决（spec 问 2）：无可压 → 不压 + 警告事件，靠预算熔断兜底。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    events: list[str] = []
    script = [
        {"tool_calls": [("bash", json.dumps({"command": "true"}))], "usage": _usage(900)},
        {"content": "done"},
    ]
    run_agent("x", client=FakeClient(script), model="fake", tools=get_tools(),
              context_window=1000, compaction=CompactionSettings(reserve_tokens=200),
              on_event=events.append)
    assert any("无可压" in e for e in events)            # 只有 1 个锚,find_cut_point 返回 1
    assert len(events) == len([e for e in events if e]) # 没发生摘要请求（脚本只有 2 turn 且未爆）


def test_breaker_stops_auto_compaction(tmp_path, monkeypatch):
    """连续 3 次压缩后仍超线 → tripped，不再发起第 4 次摘要请求。"""
    monkeypatch.chdir(tmp_path)
    from pai.core.compaction import CompactionSettings
    from pai.core.loop import run_agent
    from pai.core.tools import get_tools

    tool_turn = {"tool_calls": [("bash", json.dumps({"command": "true"}))]}
    script = []
    script.append({**tool_turn, "usage": _usage(100)})
    for _ in range(3):                                   # 3 轮：超线→压→真实 usage 仍超线
        script.append({**tool_turn, "usage": _usage(950)})
        script.append({"content": "摘"})
    script.append({**tool_turn, "usage": _usage(950)})   # tripped 后：不再压
    script.append({"content": "done"})
    client = FakeClient(script)
    answer = run_agent("x", client=client, model="fake", tools=get_tools(),
                       context_window=1000, max_steps=10,
                       compaction=CompactionSettings(reserve_tokens=200, keep_recent_tokens=1),
                       on_event=lambda _: None)
    assert answer == "done"
    summary_reqs = [r for r in client.requests if "tools" not in r]
    assert len(summary_reqs) == 3                        # 熔断后没有第 4 次
```

- [ ] **Step 2: 跑测试确认红**

Run: `python3 -m pytest tests/test_loop.py -k "compacts or warns or breaker" -v`
Expected: FAIL, `TypeError: run_agent() got an unexpected keyword argument 'context_window'`

- [ ] **Step 3: loop 接线实现**（`src/pai/core/loop.py`；import 行扩为
`from pai.core.compaction import AnchorBook, CompactionSettings, CompactionState, compact, context_tokens, find_cut_point, should_compact, usage_fields, verify_compaction`）

签名加参：
```python
    context_window: int | None = None,
    compaction: CompactionSettings | None = None,
```
`anchors = AnchorBook()` 之后加 `state = CompactionState()`。
在 `estimated = context_tokens(...)` 之后、`client.chat.completions.create` 之前插入触发块：

```python
        compaction_on = compaction is not None and context_window is not None
        if compaction_on and not state.tripped and not state.awaiting_verify \
                and should_compact(estimated, context_window, compaction):
            cut = find_cut_point(messages, anchors.entries,
                                 keep_recent_tokens=compaction.keep_recent_tokens)
            if cut <= 1:
                on_event(f"⚠️ 上下文超线（估算 {estimated}）但无可压（超长单轮或锚不足），"
                         "不压，靠预算熔断兜底")
            else:
                messages, summary = compact(messages, cut=cut, client=client, model=model)
                anchors.reset()                      # 历史被改写，旧锚全部作废（D#18/32）
                state.awaiting_verify = True         # 成败等首次真实 usage（D#34）
                after = context_tokens(messages, tool_schemas)
                on_event(f"🗜️ 压缩：切于 {cut}，估算 {estimated} → {after}")
                if session:
                    session.append({"type": "compaction", "step": step, "cut": cut,
                                    "summary": summary, "estimated_before": estimated,
                                    "estimated_after": after})
                estimated = after
```
在 `usage = usage_fields(response)` 之后插入 verify 块：

```python
        if compaction_on and state.awaiting_verify and usage.get("prompt_tokens") is not None:
            state = verify_compaction(usage["prompt_tokens"], context_window, compaction, state)
            if state.tripped:
                on_event(f"⚠️ 压缩连续失败 {MAX_COMPACT_FAILURES} 次，自动压缩已熔断")
```
（`MAX_COMPACT_FAILURES` 加进 import。）

- [ ] **Step 4: config/once 接线**

`src/pai/config.py` 追加：
```python
def context_window() -> int:
    load_dotenv()
    return int(os.environ.get("PAI_CONTEXT_WINDOW", 1_000_000))
```
`src/pai/modes/once.py` 的 run_agent 调用处透传（import 对应补齐）：
```python
        context_window=context_window(),
        compaction=CompactionSettings(),
```

- [ ] **Step 5: 跑测试确认绿，随后全量**

Run: `python3 -m pytest tests/test_loop.py -k "compacts or warns or breaker" -v && ./test.sh`
Expected: PASS / 全绿（既有测试不传新参，行为不变是硬承诺）。

- [ ] **Step 6: 留痕与收尾**

- 本目录 `devlog.md` 各 task 红→绿数字补齐；档案 README「结果与测试」更新。
- STATUS：模块表 compaction 行改「可用」、compaction.py 函数表更新、缺陷 1/4/5 按实况改写、下一步指向实测裁决/microcompact 评估。
- TODO：划掉 P0/P1 已完成项（注明出处），reserve_tokens 校准结论登记。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(compaction): 压缩闭环接进 loop——触发/切/摘/重建/熔断 + e2e（阶段 1 主线完成）"
```

---

## Self-Review（已执行）

1. **Spec 覆盖**：目标 1→Task 1+3；目标 2→Task 4；目标 3→Task 5；目标 4→Task 6；目标 5→Task 2；实测设计→Task 4 Step 5-6；非目标（超长单轮不压+警告）→Task 6 警告路径。无缺口。
2. **占位符扫描**：无 TBD/TODO/「适当处理」；每个代码步骤有完整代码。
3. **类型一致性**：`AnchorBook.entries: list[tuple[int,int]]` 贯穿 1→3→6；`summarize -> tuple[str, dict]` 贯穿 4→5；`CompactionState` 字段 5→6 一致；`usage_fields` 迁移在 4 声明、6 的 import 使用。
```
