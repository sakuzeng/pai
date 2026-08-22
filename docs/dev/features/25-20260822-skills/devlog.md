# feature 25 · skills — 开发日志

一步一条，红→绿贴真实数字。全程在 `feat/25-skills` 分支；测试用
`~/.virtualenvs/pai/bin/python` 跑（教训见 T4 那条：系统 python3 跑
`test_hang_becomes_red.py` 会因子进程没有 pytest 而假红）。

## T1 · 路径与扫描（2026-08-22）

- 目标：`core/paths.py` 加 `user_skills_dir` / `project_skills_dir`（项目取 git 根，
  与 `project_slug` 的项目定义一致）；`core/skills.py` 的 `Skill` + `scan_skills`。
- 红：`tests/test_skills.py` 12 条全部收集失败——
  `ModuleNotFoundError: No module named 'pai.core.skills'`。
- 绿：`pytest tests/test_skills.py tests/test_paths.py tests/test_memory.py` →
  `49 passed`（新 12 条 + 两个邻居模块回归）。
- 说明：frontmatter 解析直接复用 `memory.parse_frontmatter`（用户约束 3），
  连「只读前 30 行」的成本约束一起继承。

## T2 · 目录渲染与 prompt 装配（2026-08-22）

- 目标：`render_catalog`（过滤/排序/转义/双上限截断）+
  `build_system_prompt(tools, skills_catalog=None)`。
- 红：4 条 prompt 侧失败（`TypeError: unexpected keyword argument 'skills_catalog'`）。
  如实记：渲染侧 7 条测试绿于到达——T1 写模块时 `render_catalog` 一并成形了，
  这 7 条只起钉死作用、没有经历红。
- 绿：`tests/test_skills.py tests/test_loop.py` → `115 passed`；
  「不传参数逐字节不变」有专测（feature 22 缓存前缀不变量的延伸）。

## T3 · skill 工具（2026-08-22）

- 目标：`core/tools/skill.py`——现读磁盘、剥 frontmatter、`<skill_content>` 包装、
  未知与被隐藏同一句话、追踪器记录、READ + get_path 声明、能力标志。
- 红：收集错误（`pai.core.tools.skill` 不存在），8 条测不了。
- 绿：`31 passed`。注入点照 memory_tool 模式（`set_catalog` / `set_tracker`）。
- 取舍落点：get_path 对未知名返回 cwd——让边界放行、由工具报「未知 skill」，
  幻觉名不撞权限话术（R4#10 同款教训），有测试钉死。

## T4 · 边界与 once 接线（2026-08-22）

- 目标：once 装配全套（扫描/目录进 prompt/工具注入/空目录藏工具/
  用户级根进 WorkingDirs.additional）。
- 红：3 条 once 级测试失败（工具结果是权限拒绝、system 无目录、空目录仍摆工具）。
  decide 级 2 条绿于到达（机制已就位，钉语义用）。
- 绿：`tests/test_skills.py tests/test_modes.py` → `73 passed`。
- 全量波及 5 条红，定性各不同：
  - `test_tools.py` 内置集合断言：预期内，`skill` 加进集合（真实变更）；
  - `test_loop.py::test_loop_warns_not_compacts_when_no_cut_available`：
    skill 的 schema 让 `estimate_request_tokens` 变大、卡窗口数字的场景多触发
    一次——测试与 skills 无关，把它的工具集钉成固定四件套（对将来加工具鲁棒），
    理由写进测试注释；
  - `test_hang_becomes_red.py` 2 条：假红——子进程用 `sys.executable -m pytest`
    而我的 shell 没激活 venv；venv 下 `3 passed` 复核通过；
  - STATUS 数字对账：留到交付时统一改。

## T5 · 压缩后重挂（2026-08-22）

- 目标：`LoadedSkills` + `render_loaded_skills` + `make_instructions`（组合 loader
  搭 D#42 的车，零 loop 改动）；loop 级压缩重挂测试拿 `REAL_TRAJECTORY`
  真实轨迹夹具做底（AGENTS「至少一条真实轨迹输入」规约）。
- 红：收集错误（`make_instructions` 不存在）；实现后仍 2 条红，修出两个真 bug：
  - `LoadedSkills.record` 用 `time.time()`——同一毫秒内两次 record 时间戳并列，
    「最近优先」退化成插入序运气。改单调计数器；
  - 截断提示语不计入单篇预算——截过的正文（50 上限 + 30 字提示 = 80）照样
    超总预算被整条丢弃，最近一篇永远装不进。改成提示语算进单篇上限。
- 绿：`41 passed`。压缩重挂 loop 级测试自证场景真实：先断言摘要请求真的发生
  （否则在测空气），再断言重建后的 messages 里有 `ALPHA-REATTACH-TOKEN`。

## T6 · /skill 命令与 interactive 装配（2026-08-22）

- 目标：REPL 空闲态 `/skill <名> [参数]` 展开跑轮次、裸 `/skill` 列表、
  TUI 空闲态转 SUBMIT 复用轮次机器、忙碌/对话框期展开进 steering 队列、
  HELP 更新；interactive 全套装配（目录/工具/追踪器/组合 loader/working_dirs）。
- 红：7 条（`/skill` 当未知命令、system 无目录、空目录仍摆工具、追踪器没记录…）。
- 绿：`tests/test_skills.py` → `48 passed`。
- 细节：历史记原命令不记展开块（TUI 用 from_skill 旗子跳过 SUBMIT 分支的
  `_append_history`）；`/skill` 加载同样计入重挂追踪器（用户显式加载的正文
  没理由比模型加载的低一等，有测试钉死）。

## T7 · e2e 与文档（2026-08-22）

- e2e：真 pai 进程（pty + 假 provider）项目级 skill 全链——目录进 system prompt、
  模型调 skill 工具、不弹权限框、正文进第二次请求。一次绿（组件皆经 TDD，
  集成测绿于到达属预期），按惯例做注入反证：掐断装配的 `render_catalog` →
  该测试红；复原 → `test_e2e_tui.py` 13 条全绿。反证有效。
- 全量：`./test.sh` → `1290 passed, 3 deselected`（venv），仅剩 STATUS 数字对账；
  更新 STATUS（模块表 + 一句话 + 数字 1291——含对账测试自身转绿）后复跑确认。
- 文档：decisions D#71（工具形态，偏离 R4#A4 定向的落点）与 D#72（项目赢），
  STATUS、TODO 遗留登记、roadmap 交付标记待反向对照后补。
