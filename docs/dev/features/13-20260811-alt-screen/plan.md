# plan：13-alt-screen —— 7 个 task，严格 TDD

档案：[README.md](README.md) ／ 需求与验收：[spec.md](spec.md) ／ 分支：`feat/13-alt-screen`

规矩（AGENTS.md）：每个 task 先写测试跑红（贴红的输出），再写实现跑绿（贴绿的数字）。
不允许「先写实现，再补测试」。测试条数一律写下限——09 复盘的教训：
把计划的估算当成「应该达到的事实」，会制造一场必然失败的对账。

---

## 动工前先摆平的两个结构问题

读代码时撞见的，它们决定 task 顺序。

### ① 自测闭环会先瞎 —— 所以 T1 是模拟器不是渲染器

`src/pai/tui/screen.py`（终端模拟器，回放出图与测试断言共用同一份）现在：
私有 CSI 一律当无操作（`?1049h` 被吞）、`_csi` 的分支里没有 `H`（CUP）也没有 `J`（ED），
strict 模式下撞上就 `_unsupported` 抛异常。

于是 alt-screen 一上线：`PAI_TUI_RECORD` 回放出来的图是错的、`tests/test_e2e_tui.py`
的 5 条当场失效。feature 14/15 刚建起来的「让 AI 自己看得见界面」会退回到让用户截图。
所以第一笔预算花在模拟器上。

### ② `commit()` 的落点要有两种，但只能有一个 `Transcript`

今天 `TuiApp.commit(lines)` 收已经按当时宽度排好的行，直接交给 `DockRenderer` 打进
scrollback。alt 下这两件事都得变：收的要是条目（宽度变了要能重排），落点是文档不是终端。

两种模式共存的最小接缝——渲染器自己说要不要留：

```python
def commit(self, entry: TranscriptEntry) -> None:
    if self.renderer.keeps_transcript:        # alt：文档留着，每帧从里面切视口
        self.transcript.append(entry)
    self.renderer.commit(entry, root=self.root)   # main：当场渲染成行、打进 scrollback
```

`DockRenderer.keeps_transcript = False`、`AltScreenRenderer.keeps_transcript = True`。
12 交付的 main-screen 路径行为一个字节不变（T6 用现有 e2e 钉死）。

## 目录布局

```
src/pai/tui/screen.py       ← 改：两块缓冲区 + CUP + ED + 自动折行开关（T1）
src/pai/tui/transcript.py   ← 新：TranscriptEntry（按宽度渲染 + 缓存）/ Transcript（T2）
src/pai/tui/scroll.py       ← 新：滚动状态机（follow-end / clamp / 视口）（T3）
src/pai/tui/altscreen.py    ← 新：AltScreenRenderer 整屏帧 + 行 diff + 绝对定位（T4）
src/pai/tui/terminal.py     ← 改：进出 alt、autowrap、异常复原（T5）
src/pai/core/settings.py    ← 新：两层 settings.json 的通用读取（T5）
src/pai/tui/keys.py         ← 改：补 PgUp/PgDn/Ctrl+Home/Ctrl+End（T6）
src/pai/tui/app.py          ← 改：commit 落点、滚动键、滚动指示（T6）
src/pai/modes/interactive.py← 改：按开关装配两种渲染器之一（T6）
```

不动：`component.py` / `dock.py` / `editor.py` / `arbiter.py` / `dialog.py` /
`theme.py` / `logo.py` / `record.py` / `replay.py` / `driver.py`（纯函数契约救了这一轮）。

---

## T1 · 终端模拟器认得备用屏（第一个做，否则后面全是瞎的）

目标：`screen.py` 能正确回放 alt-screen 的字节流，于是录制回放与 e2e 继续可信。

红（≥10 条）
- `?1049h`：切到第二块缓冲区，内容为空；主屏那块的格子原封不动。
- `?1049l`：切回主屏，逐格还原（拿 `all_cells()` 比对进 alt 前的快照）。
- 已在备用屏时再发 `?1049h` → 备用屏被清空、光标回 (0,0)
  （照实测，不是 no-op；[evidence 第 1 条](evidence/20260811-alt-screen反向对照/说明.md)）。
- `?1049h` 存光标、`?1049l` 复光标（进 alt 前在 (5,3)，出来还在 (5,3)）。
- `H` / `CSI r;cH`：1-indexed，缺参数默认 (1,1)，超界钳位。
- `J`：`2`=整屏清空、`0`=清到屏尾、`1`=清到屏首。
- `?7l` 之后写超宽内容：在右边界截断，不折到下一行；`?7h` 恢复折行。
- 无关的私有模式（`?2026`、`?25`）继续当无操作，不得因此报 unsupported。
- 注入反证：把「重发 1049h 也清屏」改成 no-op，对应测试必须变红。
- 注入反证：把备用屏做成与主屏共用一块格子，「出来后逐格还原」必须变红。

绿：`screen.py` 里加 `_alt: Optional[Grid]` 与 `_saved_cursor`，`_csi` 补 `H`/`J`，
私有模式分支从「一律忽略」改成「认得 1049/7，其余忽略」。

风险：`replay.py` 出图走的是 `visible()`——切缓冲区之后它必须读当前那块。
这条要单独钉一个测试，否则回放图对了、`lines()` 却读的是主屏。

---

## T2 · Transcript：能按宽度重排的文档

目标：把「渲染成行」的时机从 commit 推迟到画帧，于是 resize 之后历史能重排。

红（≥8 条）
- `TranscriptEntry.render(width)` 与 `Component` 同构（纯函数、返回行数组）。
- 同一条目在 80 列与 40 列下行数不同；中文按 `display_width` 折。
- 缓存按 `(内容, 宽度)`：同宽度第二次调用不重算（注入计数器断言）；
  换宽度必须重算——这条是本 task 的核心（缓存把旧宽度的行发出来 = resize 后满屏错位）。
- `Transcript.append` / `total_lines(width)` / `slice(width, top, height)`。
- `slice` 越界（top 超过总行数、height 大于剩余）钳位不抛。
- 空文档 `slice` 返回空表。
- 条目种类覆盖今天 `app.py` 里全部 commit 调用点：logo 定格、用户输入色带、
  模型答案、工具行（折叠态）、事件摘要、`^O` 展开的整段、错误行。
  渲染函数一行不改（`_answer_lines` / `_tool_lines` / `theme.band` 原样搬进条目里调用）。
- 注入反证：把缓存的 key 从 `(内容, 宽度)` 改成只有 `内容`，「换宽度必须重算」变红。

绿：`transcript.py`。框架层不许再加第二层缓存（照 pi `tui-plan.md:376`：
第二层会因为「失效语义归组件自己所有」而陈旧）。

---

## T3 · 滚动状态机

目标：把 pi 的 `ScrollView` 语义抄成一个不碰终端的纯状态机。

红（≥10 条）
- 初始跟随末尾；`append` 之后自动贴底。
- 手动上滚就关掉跟随；此后 `append` 不移动视口（这是「流式输出时用户在往回翻」
  的全部意义）。
- 滚回底部重新打开跟随；`Ctrl+End` 显式回底也打开。
- `scroll_by` 在两端钳位；返回没用掉的 delta（暂无第二个滚动区，但语义先立住）。
- `Ctrl+Home` 到顶。
- `PgUp`/`PgDn` 翻一屏留 4 行重叠（照 pi 的 `PAGE_SCROLL_OVERLAP`）。
- 视口高度变化（resize / dock 变高变矮）时：跟随态贴底、非跟随态 `scroll_top` 不变。
- 内容比视口短时：`scroll_top` 恒 0，且不进入「已上滚」状态。
- `has_unseen()`：非跟随态下有新内容到达 → True（T6 的状态行要显示它）。
- 注入反证：把「手动上滚关掉跟随」删掉，对应测试必须变红。

绿：`scroll.py`，纯状态机、零 IO。

---

## T4 · 整屏帧渲染器

目标：每帧算出 `rows` 行，只把变了的行写给终端。

红（≥8 条）
- 帧 = transcript 视口切片 + dock；总行数正好等于 `rows`（不足补空、超出裁掉）；
  transcript 视口至少 1 行（dock 再高也要留）。
- 第二帧只重写变了的行（用 `screen.py` 断言屏幕内容 + 断言写出的字节里
  只出现变了那几行的 `CSI n;1H`）。
- 输出里不含 `2J`、不含第二个 `?1049h`（两条各一个测试，这是 evidence 钉的硬约束）。
- 整帧包在 `?2026h` / `?2026l` 里。
- `CURSOR_MARKER` → 硬件光标绝对定位（沿用 12 的提取逻辑，行列都按屏幕坐标算）；
  没有标记时藏光标。
- 每行按 `display_width` 截到 `width`（配合 T1 的 `?7l` 双保险）。
- resize：每一行都被重写，且没有 `2J`。
- 注入反证：把行 diff 改成「每帧全量写」，`test_only_changed_rows_are_written` 变红
  （注意：断言要挑「写出的字节数变多」而不是「屏幕内容不同」——屏幕内容是一样的，
  这正是 feature 15 那三条假绿的病根）。

绿：`altscreen.py`。与 `DockRenderer` 共用 `_extract_cursor`（提到 `component.py`）。

---

## T5 · 进出备用屏、异常复原、开关

目标：把终端交出去、拿回来，任何路径都不留残局。

红（≥6 条）
- 进：`?1049h` + `?7l` + `2J` + `H` + 藏光标，且这串序列早于第一帧内容
  （CC 的教训：顺序反了，那一帧留在主屏上、退出后才作为脏东西暴露）。
- 出：显示光标 + `?7h` + `?1049l`；正常退出 / 异常抛出 / `Ctrl+D` 三条路径都复原
  （异常那条用 `pytest.raises` 包住并断言写出的字节）。
- 退出后在主屏打一行会话提示（含 sessions 文件路径），不提示 `--resume`
  （它还不存在，提示不存在的命令比不提示更糟）。
- `settings.json` 的 `tui.altScreen`：用户级 + 项目级两层合并，默认 `true`；
  非法值（非布尔）告警并退回默认，不炸。
- 开关为 `false` 时：输出里没有任何 `?1049`。
- 非 tty：`use_tui()` 闸门之前就返回，一个字节都不发。

绿：`terminal.py` 扩 + 新建 `core/settings.py`（两层读取的通用函数）。
不动 `permissions.py` 自己的读取——它工作正常，动它是无谓风险；
两处读同一个文件这件事登记为遗留，不在本轮解决。

---

## T6 · 接线

目标：把 T2-T5 接进主循环，两种渲染器按开关二选一。

红（≥6 条）
- `interactive` 按 `tui.altScreen` 装配 `AltScreenRenderer` 或 `DockRenderer`；
  main-screen 那条路径的行为逐字节不变（拿现有 e2e 兜住）。
- `commit` 落点：alt 下进 transcript、main 下进 scrollback（`keeps_transcript` 分流）。
- 键位：`keys.py` 补 `\x1b[5~`(PgUp) / `\x1b[6~`(PgDn) / `Ctrl+Home` / `Ctrl+End`；
  `Home`/`End` 仍归编辑器（行首/行尾），滚到顶/底走 Ctrl 组合（照 CC）。
- 滚动指示：非跟随态状态行右侧出现 `已上滚 N 行`；期间有新内容追加 `· 有新内容`。
- resize：`SIGWINCH` → 重算视口 → 全量重绘（沿用 12 的同尺寸事件丢弃）。
- 注入反证：把「手动上滚后 append 不移动视口」的接线删掉（每次 append 都 `to_end()`），
  对应测试必须变红。

绿：`app.py` / `interactive.py` / `keys.py`。

---

## T7 · e2e：真 pty + 假 provider

目标：把「真 pai 进程在真 pty 里跑完整一回合」这条线拉到 alt-screen 上。

红（≥3 条 e2e，各配一条注入反证）
- 起 pai（alt 开）→ 跑完一回合 → 录制回放 → 断言：屏幕上有模型的回答、
  dock 在最底部那几行、进 alt 的序列出现且只出现一次。
- 按 PgUp 之后：dock 仍在原位（逐行比对），transcript 区域内容变了。
- 退出：输出里有 `?1049l`，且主屏上有那行会话提示。
- 每条 e2e 配一条能还原原 bug 的注入反证——feature 15 的教训：
  三条注入反证第一轮只红了 1 条，另两条假绿。不红的测试等于没有；
  不红时先分清「注入不对 / 断言不对 / 原 bug 的入口已不存在」
  （[K engineering/mutation-testing-pitfalls.md](../../../../knowledge/engineering/mutation-testing-pitfalls.md)）。

绿：`tests/test_e2e_alt_screen.py`（新文件，与 `test_e2e_tui.py` 并列）。

---

## 验收（对齐 [spec 的验收标准](spec.md)）

| spec | 由谁兑现 |
|---|---|
| 1 全绿、新增 ≥45 条 | T1-T7 合计下限 ≥51 |
| 2 模拟器认 1049/H/J/?7 | T1 |
| 3 按宽度重渲染 | T2 |
| 4 滚动状态机 | T3 |
| 5 只重写变了的行、无 `2J`、无第二个 `1049h` | T4 |
| 6 进出顺序与异常复原 | T5 |
| 7 resize 全量重绘 | T4（渲染）+ T6（接线） |
| 8 开关 | T5 |
| 9 非 tty 逐字节不变 | T5 + T6（现有 e2e 兜底） |
| 10 e2e + 注入反证 | T7 |
| 11 交付前反向对照 | 交付前单独一步，含 evidence 手工清单 |

## 刻意不做（与 [spec 非目标](spec.md) 一致，写在这里防实现时手滑）

- 不发任何鼠标序列（`?1000/1002/1003/1006`），于是终端原生拖选复制照旧能用。
- 不做点击/命中测试、不做搜索、不做 `--resume`、不做滚动条与选区。
- 不做虚拟滚动等性能优化（`perf` 得先有数字）。
- 不顺手把 `display_width` 从 `modes/statusline.py` 挪进 `tui/` 包
  （TODO 里挂着的那条）——不做它本轮交付也不缺陷，按 08 复盘收紧后的「顺手」判据，不并。
- 不动 `once`、不动非 tty 路径、不动 `permissions.py` 的 settings 读取。
