# feature 25 · skills — plan

分支 `feat/25-skills`，7 个 task，每个先红后绿（红的输出与绿的数字都贴进
本目录 devlog.md）。测试数字写下限不写精确值（feature 09 复盘教训）。

- T1 扫描层：`core/paths.py` 加 skills 两级路径；`core/skills.py` 的
  `Skill` + `scan_skills`（目录包/扁平/项目赢/缺 description 跳过并 warn/
  disable-model-invocation/坏 frontmatter 即跳过）。测试 ≥8 条。
- T2 索引层：`render_catalog`（过滤/排序/转义/每条 500/总 8000 截断留提示/空串）
  + `build_system_prompt(tools, skills_catalog=None)`（不传逐字节不变——
  拿现测试的输出对拍；传了且有 skill 工具才加段）。测试 ≥6 条。
- T3 工具层：`core/tools/skill.py`（正文包装/剥 frontmatter/重读磁盘/未知名
  不泄露不撞权限话术/追踪器记录）+ 能力与边界声明 + 注入点。测试 ≥7 条。
- T4 边界接线：once 与 interactive 传 `working_dirs`（additional 含用户级
  skills 根）；decide 级测试钉「once 下读 ~/.pai/skills 内 SKILL.md → allow、
  界外别处仍 ask、幻觉名 → 工具级未知错误」。测试 ≥4 条。
- T5 压缩重挂：`LoadedSkills` + `render_loaded_skills`（预算三条：截头保留/
  整条丢弃/磁盘重读与缺文件跳过）+ 装配组合 loader；一条拿
  `REAL_TRAJECTORY`（真实轨迹夹具）做底的压缩重建测试：压缩后指令消息含
  `<skill_content>`（满足「至少一条真实轨迹输入」）。测试 ≥6 条。
- T6 /skill 命令：REPL `_handle_command` + TUI `_dispatch_command` 两路、
  裸 /skill 列表、未知名提示、/help 文案、展开后走一轮 fake client。测试 ≥5 条。
- T7 装配收口 + e2e：once/interactive 全接线（scan → catalog → prompt →
  工具注入 → 追踪器 → 组合 instructions）；一条 pty e2e（fake provider 脚本
  让真 pai 进程调 skill 工具并按正文答）。文档：STATUS、decisions
  D#71（工具形态，复议 R4#A4 的「零新增工具」半句）与 D#72（同名冲突
  项目赢，三家三分中取 dsh）、roadmap 勾选、TODO 登记遗留。

交付前：反向对照（真实回合，真 API：项目里放一个真 skill，让模型自主匹配
并加载，产物进 evidence）→ 复盘.md（四问）→ 合并 main。
