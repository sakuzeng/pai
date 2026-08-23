# 23-model-visible-is-recorded · 开发日志

## 2026-08-22 · 用户指定「参照 CC」→ 走读 recordTranscript → 拍板 A → TDD 交付

目标：「模型可见即已落盘」从习惯升格为可测不变量（R4#E3），为 evals 铺地基。

改动：`core/session.py`（`replay_messages` + `_META_KEYS`）、
`core/loop.py`（`_record` 收口，替换 5 处成对 append + `_extend`）；
`tests/test_loop.py` 3 条（真实轨迹重放 / 压缩拒收 / 不变量本体）。

测试：红 `3 failed`（replay_messages 不存在）→ 实现后 3 passed——
注意不变量在收口之前就绿（现有 5 处配对是对的），它的价值在防将来漏；
收口重构后受影响文件 `180 passed` 一条没改。注入反证：`_record` 对
`role=="tool"` 漏记 session → 不变量精确红，复原全绿（加/删用脚本，
不碰 git checkout——feature 21 的教训）。

遗留：REPL 侧（`_run_shell`/`_handle_command`）仍有自己的成对 append，
不变量照不到，登记 TODO。
