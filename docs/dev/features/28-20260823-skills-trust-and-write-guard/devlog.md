# 28 · devlog

## 2026-08-23 · 拍板与 TDD

- 一轮拍板三问（存 README「确认」）：写面 A（用户级+项目级都进危险写名单）、
  信任 B（CC 式门禁——AI 推荐的是更便宜的提示一行，用户选了彻底的）、
  软链附属 A（只解用户级真身）。
- 红：新增 9 条测试先行（写面 2 / 信任 5 / 软链 2）。首跑红在 collection
  （`ImportError: cannot import name 'apply_project_trust'`）；实现 skills.py
  三件套（信任标记读写 + `apply_project_trust` + `user_skill_link_roots`）后
  精确剩 4 条集成红：
  `test_dangerous_write_guards_skills_dirs` /
  `test_accept_edits_does_not_silently_write_skills`（危险写名单未加）、
  `test_once_untrusted_project_skill_stays_out_of_prompt`（once 未接门禁）、
  `test_once_reads_attachment_of_symlinked_user_skill`（真身根未进边界）。
- 绿：`boundary.py` 的 `_DANGEROUS_ANYWHERE` 加 `.pai/skills` 段（与
  `.git/hooks` 同款「写进去拿到后续执行/指挥权」，一个模式覆盖用户级与
  项目级）；once/interactive 装配接 `apply_project_trust`（once 无人 →
  未信任丢弃+warn 指路；interactive 用装配期的 reader 版 asker 问一次，
  精确选中信任项才持久化标记）；additional 拼上 `user_skill_link_roots`。
  `tests/test_skills.py` → `63 passed`。
- 连带更新两处测试（意图不变，如实记）：27 的子目录回归测试预置信任标记
  （它测边界不测门禁）；25 的 skill e2e 同样预置标记，另新增
  `test_project_skills_trust_dialog_gates_then_persists`——真 pty 里启动即弹
  信任问题（TUI 未起、问题只在裸字节里）、答 1 后 TUI 起、目录进 system
  prompt、标记落盘。两条 e2e `2 passed in 14.07s`。
- 注入反证两处，各红各的后复原：危险写名单去掉 `.pai/skills` → `2 failed`
  （acceptEdits 写回 allow）；`apply_project_trust` 开头直接 `return skills`
  → `3 failed`（未信任项目 skill 混进 prompt、信任对话消失）。
- 全量：`./test.sh` → `1307 passed, 3 deselected in 165.80s (0:02:45)`
  （交付前 1297）。

## 已知边界（如实声明）

- 信任是项目级一次性的：信任之后新增的 skill 不再触发确认（CC 工作区信任
  同款弱点）。
- 危险写名单按 `.pai/skills` 路径段匹配：软链用户级 skill 的真身目录
  （dotfiles 形态）不含该段，模型经 bash 自行 readlink 后直写真身可绕——
  bash 本就不参与边界（feature 09 拍板），与 `.git/hooks` 的既有豁口同类。
