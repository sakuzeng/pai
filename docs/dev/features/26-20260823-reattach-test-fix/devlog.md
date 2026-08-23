# 26 · devlog

## 2026-08-23 · 拍板与场景分析

- 拍板（两问）：测试形态选 B（场景真摘掉正文 + 双向断言）；范围顺带补
  /skill 通道对 disable-model-invocation 的覆盖缺口。存档见 README「确认」。
- 场景分析：读 `compaction.py::find_cut_point`——刀只落在锚点边界，
  从最新锚往回累计差值够 keep_recent 即停。原两锚场景（110/860）里
  `anchors[:-1]` 只剩 skill 轮的锚，刀落在它上面 = skill 轮整个保留，
  这就是 25 复核撞见的假绿成因。三锚（110/400/850）时刀落在第二锚，
  skill 轮被摘掉——场景改法由此确定，不用猜 usage 数字。

## 2026-08-23 · 改测试（红→绿→注入反证）

- 动了哪些文件：仅 `tests/test_skills.py`（不动 src，分支类型 `test` 的判据）。
  1. `test_compaction_reinjects_loaded_skill_body`：场景从两锚改三锚
     （skill 轮后加一轮 bash 填充），断言从「token 在整份 messages」改成双向：
     token 不在任何 tool 消息（自证正文真被摘掉，防场景漂移回假绿）+
     token 在指令消息（只可能来自重挂）。
  2. 新增 `test_repl_skill_can_invoke_disable_model_invocation`：
     disable 的 skill 走 /skill 照常展开跑轮次 + 同 skill 不在模型可见目录
     （对照断言）。
- 绿（当前实现）：`2 passed in 0.45s`（两条目标测试单跑）。
- 注入反证 1（重挂）：`make_instructions` 临时改 `load()` 只回 `base()` →

  ```
  E  AssertionError: 正文被摘掉后，token 只可能经重挂回到指令消息——不在就是重挂没生效
  E  assert 'ALPHA-REATTACH-TOKEN' in '# 项目指令与记忆（来自 PAI.md 与自动记忆）\n\n# 项目指令与记忆（来自 PAI.md 与自动记忆）\n基础'
  1 failed in 0.57s
  ```

  红落在重挂断言上，且「正文真被摘掉」的自证断言先通过了——刀的位置对了。
  修改前的旧断言在同一注入下是绿的（25 复核实测），对比即本次修复的价值。
- 注入反证 2（/skill 通道）：`_expand_skill_line` 临时对 `model_invocable=False`
  拦截 → `client.requests == []` 断言红（`1 failed in 0.45s`）。
- 两处注入均已复原。
- 全量：`./test.sh` → 首跑 `1 failed, 1291 passed, 3 deselected`——失败的是
  `test_status_reports_the_current_test_count`（新增 1 条测试后 STATUS 的
  1291 过期），机器对账按设计发挥作用；更新 STATUS 为 1292 后复跑
  `1292 passed, 3 deselected in 152.61s (0:02:32)`。
- 已知缺陷/待办：无新增。销账两条见 TODO「25 复核发现」（高 1、低 1 划掉）。
