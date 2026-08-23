# 27 · devlog

## 2026-08-23 · 拍板前研究（CC 反编译走读）

- 用户在 27 首轮拍板时未选、要求先查 CC 的做法。走读 CC 反编译源码 2.1.88
  （符号级检索）+ dsh 第一方文档，三条结论转录进 README「需求」节：
  SkillTool 无 getPath 不进路径边界（门在 skill 名维度）；正文发现期裸读进
  内存、调用时不碰盘；边界根就是启动 cwd 且 `getProjectRoot()` 注释明文
  身份根不管文件操作。dsh 的门是 `isModelInvocable` 策略位。
  即：脱节根源是 25 的路径建模（三家孤例），不是边界根选错。
- 二轮拍板：A·退出路径边界 + 显式豁免位；顺带挖出的「多根发现链」
  用户裁决登记 TODO 不进 27。研究还纠正了候选集：一轮时的推荐是
  「两根进 additional」，研究后降为候选 B。

## 2026-08-23 · TDD 红→绿→注入反证

- 红：改/新 5 条测试先行——`test_skill_tool_capabilities_and_boundary_declarations`
  改断言（get_path 为 None + boundary_exempt 为 True）、新增
  `test_decide_allows_skill_tool_via_boundary_exemption`、
  `test_decide_skill_exemption_yields_to_deny_and_ask_rules`（优先级守卫）、
  `test_decide_skill_attachments_still_walk_the_boundary`（豁免不外溢到
  read_file，替代原「skills 根不在边界就 ask」两条旧测试）、
  `test_once_loads_project_skill_from_repo_subdir`（25 复核冒烟场景转回归）。
  实跑 `3 failed, 48 passed in 0.58s`——红的正是三处新行为（声明、豁免放行、
  子目录全链），子目录那条红在
  `assert 'SUBDIR-BODY-TOKEN' in '权限被拒绝，该工具调用未执行。…'`，
  与 25 复核冒烟的失效形态逐字同款。优先级守卫与附属文件两条绿于到达
  （钉的是既有求值链语义，如实标注）。
- 绿：三处改动——`tools/__init__.py` 加 `Tool.boundary_exempt` 字段 +
  `boundary_exempt_for()` 声明器（没注册就抛，同 capabilities_for）；
  `permissions._boundary_fallback` 开头查豁免位（在「未声明路径语义 → ask」
  之前）；`tools/skill.py` 删 `_skill_path` 整段与 `path_access_for` 导入，
  换 `boundary_exempt_for(skill)`。实跑 `51 passed in 2.16s`（此前 49 条，
  删 2 旧增 4 新）。
- 注入反证（验收 5）：注释掉 `boundary_exempt_for(skill)` →
  `2 failed`（豁免测试红在 `allow != ask`，子目录测试红回权限话术），复原后全绿。
- 冒烟复验：25 复核的三场景脚本重跑，场景 2（子目录）与场景 3（软链正文）
  由「权限被拒绝」变为正文回填——软链的正文半边被顺带修掉，TODO 中级那条
  范围收窄为附属文件（已改写登记）。
- 全量：`./test.sh` → `1294 passed, 3 deselected in 151.50s (0:02:31)`
  （交付前 1292；中间 STATUS 数字对账红一次 `1 failed, 1293 passed`，
  护栏起效，改 1294 后全绿）。
- 升格 [D#73](../../decisions.md)（工具级边界豁免位）。
