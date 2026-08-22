# 20-e2e-for-seams · 开发日志

## 2026-08-19 · 第 1 条：拖动节流 e2e（补记）

本条是 2026-08-22 的补记——当时只写了 README 的「结果与总结」与提交
（`e06af1e`），漏了 devlog 这边的一步一条。内容以 README 与提交为准，
这里只补账目：

目标：给拖动节流补一条数真实终端写次数的 e2e。

改动：`tests/test_e2e_tui.py`（拖动 e2e）；顺带纠正 features/16 的 devlog 与复盘、
TODO 重开「拖选卡顿成因未确诊」。

测试：e2e 实测有节流/无节流两列帧数没有差别（0ms:6/7、10ms:71/67、30ms:75/70），
据此推翻 feature 16 的交付结论；逐层注入反证定位到真正挡事件洪水的是
`_merge_mouse_runs`，不是 `DRAG_FRAME_INTERVAL`。

遗留：拖选卡顿成因未确诊（已登记 TODO）。

## 2026-08-22 · 第 2 条：阶梯断言的恒真析取项（R4#T2）

目标：`test_multiline_content_does_not_stair_step` 的
`row.startswith((marker, " "))` 行首一个空格就恒真，1~11 格的阶梯不红；
第二条 `"    " * 3` 只挡 ≥12 格。换成挡得住浅阶梯的断言。

改动：`tests/test_e2e_tui.py`（只动断言段，被测代码零改动）。
先真跑摸形态：答案续行顶格（0 列）、`/help` 行自带 2 格缩进且缩进来自
`interactive.HELP` 文案本身。据此把断言改成「屏幕行缩进 == 源头文本该行缩进」
严格相等——期望值锚到 `answer` 变量与 `HELP` 常量，不留魔法数字。

测试：改后 `1 passed`。注入反证两连、各自复原：
- `theme.wrap` 不拆 `\n`（12 号阶梯的原病）→ `1 failed`（标记行整块被打散）；
- `_answer_lines` 给续行加 1~n 格浅阶梯（旧断言两个检查都放过的形态）→
  `1 failed`，精确红在 `indent_of(' - file0.txt') == 1` ≠ 源头 0。

遗留：无。

## 2026-08-22 · 第 3 条：6 处 `getsource` 断言逐条裁决（R4#T3）

目标：原报告「8 处 `inspect.getsource` 只防误删不防改坏」。现存 6 处
（R4#T1/T5 清理时顺带消掉 2 处，口径漂移如实记）。逐条处理：
能换行为断言的换，换不掉的写明为什么。

改动：3 换 3 留。
- 换：`tests/test_trace_wiring.py`（`_run_tui` 换间谍真跑装配，断言递到手的是
  `EventTrace`）、`tests/test_interactive_steering.py`（队列构造器换间谍 +
  EOF reader 真跑 `run_interactive`，断言 `built == ["all"]`）、
  `tests/test_viz_server.py`（对真 server 逐个打页面引用的 `/api/*`，
  只认 404 为失联，加「正则至少抓到一个」护栏；删掉 `inspect_source_of_do_get`）。
- 留：`tests/test_tui_mouse_wheel.py`（钉注释本身，行为测不出注释）、
  `tests/test_interactive_steering.py` follow_up 缺席（证「无」只有扫源码）、
  `tests/test_modes.py` 无 emoji（lint 型，渲染路径枚举不完）。
  三条的理由都写进了各自 docstring。

测试：五个被改文件 `95 passed`。注入反证三连、各自复原：
- `trace=trace → trace=None`（R4#T3 点名的突变）→ `1 failed`。
  这个突变旧断言 `"trace=" in source` 恰好是绿的——本条是唯一能当场演示
  「旧的防不住、新的防得住」的。
- `PendingMessageQueue("all") → ("single")` → `1 failed`；
- 路由 `/api/flow → /api/floww` → `1 failed`。

遗留：无新增。保留的 3 处不算遗留，算裁决记录（理由在 docstring）。
