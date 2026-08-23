# 19-tui-input-and-signals
状态：已交付
分支：`fix/19-tui-input-and-signals`（三条一并做——同属输入/信号层，
      且问 1 与问 2 共用同一份「时间」机制，拆开反而要写两遍）
流程：superpowers 全链路（spec + plan）——理由：三条都在输入/信号这一层的接缝上，
      改法各有真实取舍（尤其信号那条要动 SIGWINCH 的同步语义，那是 feature 12
      拍过板的东西），且本轮之前连着十次走 `!小修` 通道，这次回到完整流程。

## 需求

修掉 R4 评审里 TUI 输入与信号三条用户可直接撞到的缺陷（出处：
[reviews/2026-08-17](../../reviews/2026-08-17-功能测试与分析评审.md) R4#12/13/14）。
三条已全部实测复现，见下。

### R4#13 干活期间按方向键，输入框里多出 `[A`

`flush()` 的设计前提是「100ms 超时后仍只有一个悬着的 ESC，那就是 Esc 键」。
但 TUI 干活期间每个事件都顺手 `driver.poll(timeout=0)`，于是转义序列被拆成
两包到达时（feature 12 的 pty 实测明确说会拆），第一包 `\x1b` 进缓冲后，
下一次 `poll(0)` 见无新数据即刻 flush，判成 Esc；随后到达的 `[`、`A`
被当普通字符插进输入框。

实测：
```
第一包 b'\x1b'  → []
此刻 flush()    → ['esc']          ← 提前裁决
第二包 b'[A' 才到 → [('char','['), ('char','A')]
```
流式期间 `MessageDelta` 逐 token 触发 poll，撞上窗口的概率不低；
那个假 Esc 若恰逢对话框弹出，还会把框取消掉。

### R4#14 `PASTE_END` 丢失后键盘全死

`flush()` 只处理 `buf == b"\x1b"`，不复位 `_pasting`。一旦 `201~` 丢失
（终端异常、断连、粘贴流被截），此后所有字节都进 `_paste` 缓冲：

```
丢掉 201~ 后喂 Ctrl+C (0x03) → []
再 flush()                   → []
再喂普通字符                  → []
```
raw mode 下 ISIG 已关，Ctrl+C 只是普通字节，所以连退出都做不到，只能 kill。

同文件另一个边角：`\x1b` 与后续字节同批到达时被并吞成 `unknown`——
连按两次 Esc 实测得到 `unknown '\x1b\x1b'`，一个 esc 都不产生，
于是对话框的 Esc 取消在快速操作下不可靠。

### R4#12 SIGWINCH 同步重入可能掀掉整个 TUI

`handle_resize` 在信号处理器里同步调 `_on_resize` → `app.refresh()` → 写 stdout。
`AltScreenRenderer` 有 `_drawing` 重入门（altscreen.py:71-81），
`DockRenderer` 完全没有——`tui.altScreen: false` 路径下，信号打在一帧写到
一半的位置，两帧字节交错、`_height`/`_cursor_offset` 被重入改写，dock 永久漂移。
更硬的一刀：主线程正处于 `sys.stdout.write` 内部时处理器再写同一 stream，
Python 的 buffered IO 会抛 `RuntimeError: reentrant call`，而 TUI 的大 try
只有 finally 没有 except，异常直接掀掉整个 TUI。

## 验收标准

1. 拆包到达的方向键不再被裁决成 Esc，且原键（up）照常送达；
2. `PASTE_END` 丢失后键盘能自行恢复，不需要 kill 进程；
3. 连按两次 Esc 产生两个 esc 键，不是一个 unknown；
4. 上述三条各有一条注入反证（改回旧实现必须变红）；
5. SIGWINCH 那条：按拍板结果定（见候选方案），至少 DockRenderer 不再被
   重入写坏，且不引入「resize 后不重画」的回退；
6. `./test.sh` 全绿，数字进 STATUS。

## 候选方案与确认

候选与取舍见 [spec.md](spec.md)。三条各自独立拍板，2026-08-19 用户一次性裁决。

问 1：`flush()` 提前把拆包的方向键裁决成 Esc（R4#13）。`flush()` 被设计成
「超时后才裁决」，而 busy 期的 `poll(timeout=0)` 让「无新数据」这个条件在
拆包间隙就成立。
- 候选 A·让 flush 认时间：`KeyDecoder` 记下缓冲区最后一次进字节的时刻，
  `flush()` 只在距今 ≥ 50ms 时才真裁决。修的是判据本身，调用方不用知道差别；
  代价是引入时间依赖，测试要注入假时钟。
- 候选 B·busy 期不调 flush：`poll()` 加参数，timeout=0 时跳过。改动最小、
  decoder 保持纯状态机；代价是把「什么时候可以裁决」放进调用方，
  第三个调用点出现时还得记得传对参数。
选择：A。理由：用户选「让 flush 认时间（推荐）」。50ms 有物理依据——
真人按 Esc 与终端发转义序列的时间差是一个数量级（人 >100ms、序列 <1ms），
不是拍脑袋的常数；且 B 那种隐性契约与 R4#1「取第一个值」是同一类债。

问 2：`PASTE_END` 丢失后 pasting 态无出口，键盘全死只能 kill（R4#14）。
- 候选 A·挂超时自愈：距最后一次进字节超过阈值仍等不到 `201~`，
  把已攒内容按 paste 吐出并复位。与问 1 共用同一份时间机制；
  代价是慢速分片的大段粘贴可能被切成两段，阈值要比问 1 大得多。
- 候选 B·只给一条逃生键：让 `Ctrl+C` 在 pasting 态强制复位。
  不引入时间判断、不可能误切；但用户得先知道「按 Ctrl+C 能救」，
  而症状是键盘全死、第一反应是 kill。
选择：A。理由：用户选「挂超时自愈（推荐）」。B 是逃生口不是修复——
它要求用户在最慌的时刻知道一个没人告诉过他的手势。

问 3：SIGWINCH 处理器同步写 stdout（R4#12）。注意这会改动 feature 12
拍过板的「同步处理」。
- 候选 A·处理器只置标志、主循环重画：从结构上消灭重入，pi 与 CC 都这么做；
  代价是多一个 poll 周期的延迟（≤100ms），且要在 decisions 记一条对
  feature 12 的复议（仍不去抖——去抖与同步是两件事）。
- 候选 B·只补 DockRenderer 重入门：改动最小、不动已拍板语义；
  但只挡住一半——防得了两帧交错，防不了 `RuntimeError: reentrant call`
  （它在 Python 的 buffered IO 层抛出，在我们的标志之外），会给人已修好的错觉。
- 候选 C·两者都做：根因治了，另加一道冗余防御；改动面最大。
选择：A。理由：用户选「处理器只置标志（推荐）」。B 明确只治一半而且制造
「已经修过了」的错觉——这正是本仓库反复吃亏的那类。

## 结果与总结

四个 task 全部交付，`./test.sh` → 1176 passed, 1 skipped, 3 deselected。
详细日志见 [devlog.md](devlog.md)，复盘见 [复盘.md](复盘.md)。

- T1 `flush()` 认时间（`ESC_SETTLE_SECONDS = 0.05`）：拆包到达的方向键不再被
  裁决成 Esc；真按 Esc 照常（`driver.POLL_SECONDS = 0.1` 是阈值的两倍）。
- T2 pasting 态自愈（`PASTE_SETTLE_SECONDS = 1.0`）：`201~` 丢失后键盘自行恢复，
  不再需要 kill 进程。
- T3 `\x1b\x1b` 同批到达时拆成两个 esc：连按两次 Esc 不再产生一个 `unknown`。
- T4 SIGWINCH 处理器只置标志、主循环重画：升格 [D#70](../../decisions.md)，
  是对 feature 12「同步处理」那半边的复议（不去抖照旧）。

四条注入反证各红各的。三处既有测试因语义变更被改写，每处都先确认生产路径
未坏再动测试，理由写进各自 docstring。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md -->

## 用到的知识

- K [tui/terminal-raw-mode.md](../../../../knowledge/tui/terminal-raw-mode.md)
- K [tui/cc-input-ownership-and-modes.md](../../../../knowledge/tui/cc-input-ownership-and-modes.md)
- 前置精读核对：本轮属既有阶段（阶段 2 后半程 TUI）的缺陷修复，不新开路线图阶段，
  故无新增「前置精读」清单项；三条缺陷均已实测复现，证据在本文件「需求」节。
