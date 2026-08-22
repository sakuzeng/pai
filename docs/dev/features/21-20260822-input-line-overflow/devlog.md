# 21-input-line-overflow · 开发日志

## 2026-08-22 · 拍板 A·折行，TDD 实现

目标：`LineEditor.render(width)` 真正用上 width——超宽逻辑行按显示列折成多个
显示行，CURSOR_MARKER 与选区反显跨行存活。

改动：`src/pai/tui/editor.py`（新增 `_wrap_spans` + 重写 `render`，
折行按字符边界不做词级）；`tests/test_tui_editor.py`（5 条新测试）、
`tests/test_e2e_tui.py`（2 条：alt 下行尾 TAIL 可见、main-screen 下 dock
结构完好）。三条不变量各有测试：不丢字符、光标落在正确显示行、
反显对每显示行内配平（alt 按行 diff 重绘，跨行悬空 SGR 会漏）。

测试：红 `3 failed`（折行/光标行/宽字符）→ 绿；e2e main-screen 那条第一版
断言写错（footer 是状态行、含 cwd 路径，`"y" not in footer` 误伤），修断言后绿。
注入反证：`_wrap_spans` 恒回单段 → `3 failed`（两条 e2e + 单测折行），
去注入 → 全绿。收尾扩面 `136 passed`（editor/app/mouse/e2e 全文件）。

事故（如实记）：第一轮注入反证的复原用了 `git checkout src/pai/tui/editor.py`，
而折行实现当时**未提交**——checkout 把实现连注入一起冲回 HEAD，
且复原后的「确认」跑出 `3 failed` 被我误读成绿。发现后重新落实现，
第二轮注入改用 python 脚本加/删注入行，不再碰 git checkout。
教训升格到复盘：**未提交的修复，注入反证的复原手段不能是 git checkout**；
且复原后的确认跑必须真的读数字，不能只看「跑完了」。

遗留（同步 TODO）：
1. 折行续排行上的鼠标点击定位不对：`app._input_click` 按「显示行=逻辑行」
   换算字符下标，折行后点第二段会定位到错误字符。选字仍可用键盘；修法是
   把 `_wrap_spans` 的区间暴露给 point_at。
2. ↑↓ 在折行的长行上仍是翻历史，不是在显示行间移动光标（CC 是后者）。
   现状与单行时代一致，算行为保持不算回归，但长行编辑体验受限。
