# 27-skill-boundary-exempt（skill 工具退出路径边界：修子目录启动被拦）
状态：已交付
分支：fix/27-skill-boundary-exempt（本档案全部工作；自 test/26-reattach-fake-green
分出——26 尚未合并，25 复核的 TODO 登记在那条分支上，27 要在其上销账）
流程：中等改动直做（无 spec/plan）——改动面三个文件 + 测试；验收项写进「需求」节
（features/README 规矩 9）。

## 需求

25 复核（2026-08-23）发现：项目级 skills 扫描按 git 根向上找
（`paths.project_skills_dir`），权限边界 `WorkingDirs.startup_cwd` 按启动 cwd——
从仓库子目录启动 pai 时，skill 目录照常注入 system prompt，但 skill 工具调用被
边界拦（once/dontAsk 直接拒绝且带权限话术，正是 R4#10 要避开的；interactive 弹
意外权限框）。离线冒烟实证：/tmp git 项目子目录启动，工具回填是「权限被拒绝」
而非正文。出处：TODO「25 复核发现」高级第 2 条；链回
[25 档案](../25-20260822-skills/README.md)与
[26 档案](../26-20260823-reattach-test-fix/README.md)（同一次复核的另一条高级）。

CC 反编译源码研究（2026-08-23，证据等级：CC 反编译 2.1.88，符号名检索）证实
脱节的根源是建模而非边界根选错：

- CC 的 SkillTool 没有 `getPath`，不进路径边界；有自己的 `checkPermissions`，
  按 skill 名做 allow/deny/ask（`src/tools/SkillTool/SkillTool.ts`）；正文在
  发现期由 harness 用裸 `fs.readFile` 读进内存（memoize），调用时不碰盘
  （`src/skills/loadSkillsDir.ts`）。
- CC 的边界根是启动 cwd（`allWorkingDirectories` = `getOriginalCwd()` +
  additionalDirectories）；`getProjectRoot()` 源码注释明文「Use for project
  identity (history, skills, sessions) not file operations」——身份根与文件
  操作根刻意分工，CC 内部同样两根不一致，但因 Skill 工具不过路径层而不成 bug。
- dsh 同构（第一方文档 `docs/subsystems/skills.zh.md`）：`skill({name})` 的门
  是 `isModelInvocable` 策略位（加载前 + 返回前各查一次），不提文件权限层。

即：三家参照里没有一家把「加载 skill」建模成「读 SKILL.md 这个路径」；
pai 25 的 `@path_access_for(skill, READ)` 是孤例，「未知名回 cwd」绕法正是
这个建模不合身的症状。

验收标准（怎么算做完）：

1. 子目录启动修复：/tmp git 项目从仓库子目录启动（once/dontAsk），skill 工具
   回填正文而非权限话术——25 复核的冒烟场景变成回归测试；
2. skill 工具不再声明 `path_access_for`，「未知名回 cwd」的 `_skill_path`
   连带删除；未知名仍报「未知或不可用」（既有测试不动语义）；
3. 豁免是显式声明不是默认：权限层新增工具级豁免位，只有声明了的工具在兜底
   步 allow；deny 规则、危险写检查、用户显式 ask 规则的优先级不变
   （decide 求值链前三步不动，豁免只作用于第 7 步兜底）；
4. 用户级 skills 根仍留在 `WorkingDirs.additional`（附属文件走 read_file 仍
   需要它，25 遗留 6 的声明不变）；
5. 注入反证：临时去掉豁免声明 → 子目录场景测试必红（红的输出进 devlog）；
6. `./test.sh` 全绿。

## 候选方案与确认

### 方案 A · 退出路径边界 + 显式豁免位（拍板选定）

删 `@path_access_for(skill, READ)` 与 `_skill_path`；`tools/__init__.py` 新增
显式豁免声明（形如 `boundary_exempt_for(tool)`）；`permissions._boundary_fallback`
对声明了豁免的工具 allow（在「不参与边界 → ask」之前查）。门回到 skill 名维度
（工具内已有 `model_invocable` 判定），与 CC/dsh 同构。

- 好处：结构性根除脱节（不靠把目录塞进边界）；删掉「未知名回 cwd」绕法；
  与参照系对齐。
- 代价：权限层新增一个 seam（豁免位），须升格 decisions；豁免位用错等于
  在权限层开洞，声明必须显式、逐工具、有测试钉住优先级。

### 方案 B · 两根都进 additional（一行补丁）

装配时 `project_skills_dir()` 也进 `WorkingDirs.additional`。

- 好处：改动最小。
- 代价：路径建模不合身继续存在（绕法留着）；CC 从不为 skills 动
  additionalDirectories；附带 `<git根>/.pai/skills/` 整目录读免问面。

### 方案 C · 边界根统一取 git 根

- 已证伪：CC 源码注释明文身份根不管文件操作；这是用全局语义变更修局部脱节，
  等于复议 feature 09，不该搭 fix 的车。

### 确认

2026-08-23 用户拍板（AskUserQuestion，与 26 的拍板同链条、CC 研究结论呈报后）：

问 1：27（子目录启动时 skill 工具被边界拦）：怎么修？研究结论：CC/dsh 都没让
skill 加载过路径权限层，门开在 skill 名/策略维度。
- 候选 A·退出路径边界+显式豁免位（AI 推荐）：删 @path_access_for(skill, READ)
  （连带删掉「未知名回 cwd」绕法），权限层加一个显式的工具级豁免声明（兜底
  allow，deny/ask 规则照常优先）。对齐 CC/dsh：门在 skill 名（model_invocable
  工具内已有）。代价：权限层新增一个 seam，须升格 decisions；附属文件的
  read_file 仍按既有边界走。
- 候选 B·两根进 additional（一行补丁）：改动最小能修 bug，但路径建模不合身
  继续存在（绕法留着），CC 从不为 skills 动 additional；附带 <git根>/.pai/skills/
  整目录读免问面。
- 候选 C·边界根改 git 根：研究已证伪：CC 源码注释明文「getProjectRoot 管身份
  不管文件操作」，改边界根是用全局语义变更修局部脱节，等于复议 feature 09。
选择：A。（理由栏用户未附文字，只记选择本身。已升格
[D#73](../../decisions.md)：工具级边界豁免位。）

问 2：研究顺带挖出的正交改进：CC 的发现其实是 cwd→git 根沿途多根链（子目录里
的 .pai/skills 也生效，顺带解掉 25 evidence 里「skill 放子目录不生效」的静默
失效），pai 现在是 git 根单根。这笔怎么处置？
- 候选 A·登记 TODO，不进 27（AI 推荐）：独立一笔、别和边界修复混一个档案
  （研究 agent 也这么建议）。先登记，等真实需要再立案。
- 候选 B·并进 27 一起做：发现与边界一次性对齐 CC，代价是 27 范围变大、
  扫描层也要动。
- 候选 C·不记不做：pai 保持单根最小形态。
选择：A·登记 TODO，不进 27。（已登记 TODO「25 复核发现」节。）

## 结果与总结

三处 src 改动 + 测试重写（详细红→绿见 [devlog.md](devlog.md)）：

- `core/tools/__init__.py`：`Tool.boundary_exempt` 字段（默认 False）+
  `boundary_exempt_for()` 显式声明器（没注册就抛）；声明条件写死在 docstring
  （入参表达不了路径 + 路径来自 pai 自算的受信来源，缺一不可）。
- `core/permissions.py`：`_boundary_fallback` 开头认豁免位（在「未声明路径
  语义 → ask」之前）；deny / 危险写 / 用户 ask 规则在求值链前面不受影响，
  优先级有守卫测试钉住。
- `core/tools/skill.py`：删 `_skill_path` 整段与 `path_access_for` 声明
  （「未知名回 cwd」绕法随建模一起消失），换 `boundary_exempt_for(skill)`。
- 测试：红 `3 failed, 48 passed` → 绿 `51 passed`（删 2 旧增 4 新）；
  注入反证去掉豁免声明 → `2 failed`（豁免放行红在 allow≠ask、子目录场景
  红回权限话术）后复原。25 复核冒烟三场景复验：子目录与软链正文均由
  「权限被拒绝」变为正文回填。全量 `./test.sh` → 1294 passed, 3 deselected
  （交付前 1292；中间 STATUS 数字对账红一次，护栏起效）。
- 验收标准 1-6 全兑现；升格 [D#73](../../decisions.md)；TODO 销账
  25 复核高 2，软链中级条范围收窄为附属文件（正文半边顺带修掉）。

## 遗留问题

无新增（豁免位粒度、skill 名维度规则缺席两条记录性质疑见
[复盘.md](复盘.md)，前者等第二个豁免工具出现再议，后者并入 D#73
「刻意不抄」清单等真实需要，均不立 TODO）。

## 用到的知识

- CC 反编译源码研究（本档案「需求」节转录关键证据；原始检索 2026-08-23 会话）
- [knowledge/skills/cc-skills.md](../../../../knowledge/skills/cc-skills.md) /
  [dsh-skills.md](../../../../knowledge/skills/dsh-skills.md)（25 前置精读）
- [26 档案](../26-20260823-reattach-test-fix/README.md)（同批复核的另一条高级）
