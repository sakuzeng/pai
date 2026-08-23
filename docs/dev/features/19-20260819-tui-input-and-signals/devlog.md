# 19 开发日志

## 2026-08-19 T1+T3 · KeyDecoder 认时间 + 同批到达的 ESC

三条缺陷动工前全部实测复现（证据在 README「需求」节）。

红：`4 failed, 17 passed`（拆包不裁决 / 真 Esc 仍裁决 / 连按两次 Esc 出两个 esc /
整包方向键不受影响，全部 AssertionError）。

绿：`21 passed`。实现两处——`KeyDecoder` 收可注入的 `now` 并记 `_last_byte_at`，
`flush()` 加「静默 ≥ `ESC_SETTLE_SECONDS`(0.05)」判据；`_step_escape` 里
`\x1b` 后面又是 `\x1b` 时只消费前一个（此前整包被吞成一个 `unknown`）。

撞红一条既有测试 `test_lone_escape_only_becomes_esc_on_flush`——它编码的是旧语义。
没有逐条改测试，而是让 `keys()` helper 默认注入一个「flush 前先跳过阈值」的时钟：
既有测试断言的仍是它们本来的语义（flush 时才裁决），不必被迫关心毫秒。

## 2026-08-19 T2 · pasting 态自愈

红：`1 failed, 2 passed`——另两条是防过头的守卫（慢速分片不许被切、空缓冲不吐空事件），
本来就该绿，只有「丢失 201~ 后键盘恢复」是红的。

绿：`24 passed`。`flush()` 加第二条分支，`PASTE_SETTLE_SECONDS = 1.0`
（比 ESC 那条大一个量级，理由写在常量旁：粘贴分片间隔可达数百毫秒，
而真实的「201~ 永远不来」是分钟级干等；切早了劈开一次粘贴，切晚一点只是多等一秒）。

## 2026-08-19 T4 · SIGWINCH 只置标志

红：`3 failed, 12 passed`（处理器不许画 / 标志取走即清 / 同尺寸仍丢弃）。

绿：`15 passed`（terminal）+ `20 passed`（含 driver）。`handle_resize` 只更新尺寸
并置 `resize_pending`；新增 `take_resize_pending()` 与 `redraw_after_resize()`；
`TuiDriver` 收可选 `terminal`，`poll()` 开头取标志并重画；`interactive` 接线。

撞红既有的 `test_changed_size_triggers_a_redraw_synchronously`——那正是 feature 12
拍板的「同步处理」，本轮拍板改的就是它。测试改名为
`test_changed_size_defers_the_redraw_to_the_main_loop` 并在 docstring 里写明
「改的只是同步这一半，不去抖与同尺寸丢弃照旧」。

## 2026-08-19 收尾

四条注入反证各红各的：flush 不认时间 → 只红拆包那条；pasting 不自愈 → 只红键盘恢复；
ESC+ESC 不拆 → 只红连按两次；处理器又画回去 → 只红「处理器不许画」。

全量首跑撞红两条 `test_tui_dialog.py`（`test_esc_cancels`、
`test_permission_dialog_cancel_means_deny`）——同样是编码旧时序语义的测试：
它们 `feed(b"\x1b")` 之后立刻 `flush()`。先确认真实路径不受影响再改测试：
`driver.POLL_SECONDS = 0.1`，恰是新阈值 0.05 的两倍，真按 Esc 时 select 超时
那一下必然已静默够久。随后给这两条注入同款时钟。

最终：`1175 passed, 1 skipped, 3 deselected`。
