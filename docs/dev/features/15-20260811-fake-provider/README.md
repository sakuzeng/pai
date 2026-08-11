# 15-fake-provider
状态：已交付
分支：`feat/15-fake-provider`

## 需求

**让「需要模型开口」的那一半功能也能被自动测试**，从而把闭环补完：

```
脚本化的假模型 → pai 在真 pty 里跑 → 录制 → 回放出图 → AI 自己看
```

### 为什么必须做

feature 12 交付时 171 条离线测试全绿，用户第一次真跑**当场打回三条**——
而那三条**全部需要一个真实的模型回合**才会暴露：

| bug | 为什么离线测试碰不到 |
|---|---|
| 模型的回答完全不上屏 | 要有 `MessageDelta` → `AssistantMessage` 的完整链路 |
| 权限框卡死（raw mode 下 `input()` 死锁） | 要有 tool_call 触发权限询问 |
| 排版满屏阶梯 | 要有多行的工具结果 |

feature 14 的复盘写过：**「为了省钱而绕开的路径，正是唯一没被验过的路径」**。
冒烟脚本刻意不跑真实回合（花钱、慢、不可复现），于是这条路径从未被验过。

假 provider 把这三条约束全部解掉：**免费、确定、离线**，且能进 `./test.sh`。

### 前提已经具备

`config.py:47` 已支持 `PAI_BASE_URL` —— **pai 一行代码都不用改**。

### 验收标准

1. 一个本地 HTTP 服务，说 OpenAI 兼容协议，按脚本回放（流式 SSE + 非流式两种）。
2. 脚本能表达：纯文本回答、tool_calls、多轮。
3. `PAI_BASE_URL=<假服务> pai` 走完整个 loop：流式上屏、工具执行、权限询问。
4. 一条 e2e：真 pty 起 pai + 假 provider + 录制 → 回放 → **断言屏幕上有什么**。
5. 不花钱、不联网、可重复。

## 候选方案与确认

### 方案 A · 本地 HTTP 假 provider（选它）

起 `http.server`，实现 `POST /chat/completions`，按脚本回放 SSE。

- **对**：走**真实的整条路**——真 HTTP、真 SSE 解析、真 `streaming.assemble`、
  真 gate、真 TUI。pai 零改动。
- **缺**：要自己拼 SSE 的字节形状（但那正是 D#58 实测出来的形状，写一次就固化了）。

### 方案 B · 注入 FakeClient（现有 `tests/fake_llm.py`）

已经有了，747 条测试用的就是它。

- **对**：零成本。
- **缺**：**它是注入的**，走不到 `make_client`、走不到真实 HTTP 与 SSE 解析，
  更走不到 pty 里的真 pai 进程——而今天要测的正是「真 pai 进程跑起来长什么样」。
  两者不冲突：A 补的是 B 够不着的那一段。

### 确认

**问**：怎么让「需要模型开口」的功能也能自动测？
**选择**：**方案 A**，与既有的 `fake_llm.py`（方案 B）并存，分工是
「B 测装配与逻辑，A 测真进程跑起来的样子」。理由见上：
今天要抓的三类 bug 全在 B 够不着的那一段。

## 结果与总结

**闭环补完了**：

```
脚本化的假模型 → pai 在真 pty 里跑 → 录制 → 回放出图 → AI 自己看
```

`tests/test_e2e_tui.py` 的 5 条走的是真实的整条路：真进程 → 真 tty/raw mode →
真 HTTP → 真 SSE 解析 → 真 `streaming.assemble` → 真 gate → 真 TUI → 录制回放，
**断言的是屏幕上有什么**。feature 12 被用户打回的三条各钉一条。

`./test.sh` **769 passed, 3 deselected**，约 34s，仍然不花钱、不联网、可重复。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md -->

1. **e2e 把主套件从 12s 拖到 34s**。目前没做分层（没有 `-m "not e2e"` 的快循环）。
   再多几条就该分了。
2. **e2e 依赖 pty 与 `select` 的时序**，理论上仍可能偶发。已用「等到出现为止」
   而不是死等把窗口压到最小，但没有做重试。
3. **假 provider 只实现了 `POST /chat/completions`**。将来接别的端点（如
   `GET /user/balance`）要补。
4. **没有测「中断」与「压缩」**：Ctrl+C 掐在流中途、自动压缩触发，
   这两条 e2e 都能测但还没写。

## 用到的知识

- [K concepts/streaming-tool-calls.md](../../../../knowledge/concepts/streaming-tool-calls.md)
  （SSE 的真实形状：tool_calls 按 index 归并、`arguments` 逐字符分片、usage 在末块）
- [K concepts/injection-seams.md](../../../../knowledge/concepts/injection-seams.md)
  （接缝上的 bug 离线测试结构上看不见——本档案就是它的对策）
