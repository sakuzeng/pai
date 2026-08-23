# 20-e2e-for-seams
状态：已交付（2026-08-22，三条全部完成；全量 1181 passed + 1 skipped（R4#26 已登记的 Pillow 缺失）+ 3 deselected，collected 1182 与 STATUS 对账一致）
分支：`test/20-e2e-for-seams`
流程：中等改动直做（无 spec/plan）——理由：只补测试不动被测代码（`test` 类型），
      三条的改法都由既有发现决定，没有需要拍板的取舍；用户 2026-08-19 认可方向。

## 需求

补上离线测试覆盖不到的接缝，三条都已登记在案：

1. 拖动节流没有 e2e（feature 16 复盘质疑三）。节流正在 `feed` 与 `needs_tick`
   的接缝上，收尾帧靠 driver 的空闲 poll 推动——某次 poll 因有输入而不走超时
   分支时收尾会晚一拍，离线测不出来。
2. R4#T2：`test_e2e_tui.py` 的阶梯断言析取项形同虚设——
   `row.lstrip() == row.strip() or row.startswith((marker, " "))`
   里第二项只要行首有一个空格就为真，1~11 格的阶梯不红。
3. R4#T3：6 个测试文件用 `inspect.getsource` 断言接线存在。这类只防误删、
   不防改坏，且对重构极脆（`"trace=" in source` 连 `trace=None` 都命中）。

## 验收标准

1. 拖动节流有一条 e2e，且数的是真实的终端写次数（录制里每条记录就是一次写）；
2. 阶梯断言不再有恒真析取项，且改后仍能挡住真实的阶梯（注入反证验证）；
3. `getsource` 断言逐条处理：能换成行为断言的换掉，换不掉的写明为什么
   （诚实边界优于假装覆盖）；
4. 全绿，数字进 STATUS；不动任何被测代码——本轮是 `test` 类型。

## 候选方案与确认

无需拍板的取舍。唯一有选择余地的是「e2e 里怎么观测帧数」，而既有基建已经给出
答案：`PAI_TUI_RECORD` 录的每条记录就是一次终端写（`load(s.record)`），
数记录条数即帧数，不需要新增任何观测点。另一条路（在 app 里加计数器再从
录制里读）要动被测代码，与本轮 `test` 类型冲突，直接排除。

## 结果与总结（进行中）

第 1 条（拖动 e2e）已做，并在做的过程中推翻了 feature 16 的交付结论：

真 pty、40 条拖动事件对照（一帧 = 一条写记录，已实测）：

| 事件间隔 | 有节流 | 无节流 |
|---|---|---|
| 0ms | 6 | 7 |
| 10ms | 71 | 67 |
| 30ms | 75 | 70 |

两列没有差别。逐层注入反证确认这条 e2e 到底钉住什么：拆掉节流 → 不红；
拆掉 driver 的「读干净再处理」→ 不红（60 条事件约 720 字节，一次
`os.read(4096)` 全拿到）；只让每个鼠标事件都 refresh → 不红；
**只有把 `_merge_mouse_runs` 一起拆掉才红**。

所以：真机上帧数低是「鼠标事件按批合并 + 每批只 refresh 一次」挡下来的，
`DRAG_FRAME_INTERVAL` 没起作用；feature 16 发布的 206→14ms 是基准脚本的产物
（紧循环调 `app.feed()` + 假时钟，造出真路径上不存在的到达形态）。
已纠正 16 的 devlog 与复盘，并在 TODO 重开「拖选卡顿成因未确诊」。

第 2 条（阶梯断言，2026-08-22）：期望缩进改为锚到源头文本——答案续行对
`answer` 变量、`/help` 行对 `interactive.HELP` 文案，断言「屏幕缩进 == 源头缩进」
严格相等，析取项整个删掉。先真跑摸清形态（答案续行顶格、`/help` 行自带 2 格），
再注入反证两连：
- 深破坏（`theme.wrap` 不拆 `\n`，即 12 阶梯的原病）→ 红（整块被打散，标记行找不到）；
- 浅阶梯（`_answer_lines` 给续行加 1~n 格缩进，正是旧断言放过的形态：
  行首一个空格满足 `startswith((marker, " "))`、不足 12 格躲过第二条）→
  新断言精确红在 `' - file0.txt'` 缩进 1 ≠ 源头 0。

第 3 条（`getsource` 断言，2026-08-22）：原报告说 8 处，现存 6 处（R4#T1/T5
清理时已顺带消掉 2 处——口径漂移如实记）。逐条裁决：3 换 3 留。

换成行为断言的（每条注入反证验过）：
- `test_trace_wiring.py` trace 接线：`_run_tui` 换成间谍真跑装配，断言递到手里的
  是 `EventTrace` 实例。注入 R4#T3 点名的那个突变（`trace=None`）→ 红——
  而旧断言 `"trace=" in source` 对这个突变恰恰是绿的，这条是 3 处里唯一能
  当场演示「旧的防不住」的。
- `test_interactive_steering.py` 队列模式：构造器换间谍、reader 立刻 EOF 真跑一次
  `run_interactive`，断言 `built == ["all"]`。注入 `"all"→"single"` → 红。
- `test_viz_server.py` 路由存在性：对真 server 逐个打页面引用的 `/api/*`，
  只认 404 为失联（参数不齐的 400/500 说明路由在）；另加「提取正则至少抓到一个」
  的护栏防空转。注入路由改名 `/api/flow → /api/floww` → 红。

保留源码断言的（各自写明为什么换不掉，写在测试 docstring 里）：
- `test_tui_mouse_wheel.py` WHEEL_LINES 注释纪律——钉的是注释本身，行为测不出注释；
- `test_interactive_steering.py` follow_up 符号缺席——行为只能证明「有」，
  证明「不存在残留引用」只有扫源码一条路；
- `test_modes.py` TUI 文案无 emoji——lint 型测试，行为版要枚举全部渲染路径，枚举不完。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md -->

## 用到的知识

- 既有 e2e 基建：`tests/test_e2e_tui.py` 的 `Session`（真 pty 跑 pai）、
  `tests/fake_provider.py`（真 HTTP 说 OpenAI 兼容协议）、`tui/record.py` 录制。
