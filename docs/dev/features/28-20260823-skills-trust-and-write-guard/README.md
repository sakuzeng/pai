# 28-skills-trust-and-write-guard（skills 持久化位点与信任门槛）
状态：已交付
分支：fix/28-skills-trust-and-write-guard（本档案全部工作）
流程：中等改动直做（无 spec/plan）——三个内聚小项一次交付；验收项写进「需求」节
（features/README 规矩 9）。

## 需求

25 复核与 25 遗留里「skills 是持久化指挥权位点」这一族的三条，一次交付收掉：

1. acceptEdits 下 `~/.pai/skills/` 可免问写入（25 复核中 4）：用户级根进
   `WorkingDirs.additional` 后，`decide` 第 5 步对「界内写」直接 allow，且
   `is_dangerous_write` 名单不含 skills 目录——模型可静默写入/篡改用户级
   skill，写进去的内容在之后所有项目的会话里自动进目录。项目级 `.pai/skills/`
   在 acceptEdits 下同样免问（它在 cwd 界内）。
2. 项目级 skill 无信任门槛（25 遗留 1，D#72 顺带点名）：别人塞进仓库的
   `.pai/skills/` 静默生效并能指挥模型干活。CC 靠工作区信任对话框挡，pai 没有。
3. 软链 skill 的附属文件半条（25 复核中 3 残余）：feature 27 修好了正文加载，
   软链 skill 目录下的参考文件走 read_file 时 realpath 在界外仍 ask/deny。

验收标准（怎么算做完）：

- 写面：acceptEdits 模式下 write_file/edit_file 到 skills 目录（按拍板范围）
  不再静默放行——离线 decide 测试钉住，且既有危险写的 bypass 免疫语义一致；
- 信任/可见性：项目级 skill 被加载时按拍板形态可感知（测试钉提示或门禁行为）；
- 软链附属文件：按拍板方案处理，行为有测试钉住（或如实记录不做的代价）；
- 注入反证至少一条（去掉危险写名单新增项 → acceptEdits 写测试必红）；
- `./test.sh` 全绿；遗留与刻意不做的逐条登记。

## 候选方案与确认

### 问 1 · acceptEdits 写面：skills 目录进不进危险写名单？

- 候选 A·用户级 + 项目级都进（推荐）：`is_dangerous_write` 认 `~/.pai/skills/`
  （对齐 `_DANGEROUS_HOME_DIRS` 的 `.ssh` 模式）与任意路径中的 `.pai/skills`
  段（对齐 `_DANGEROUS_ANYWHERE` 的 `.git/hooks` 模式——项目 skill 与 git hook
  同为「写进去就拿到后续执行/指挥权」）。写 skills 永远 ask，bypass 免疫
  （危险写现有语义）。代价：让 agent 帮忙写 skill 时每次要确认——持久化位点
  该有的待遇，与 settings.json 同款。
- 候选 B·只进用户级根：跨项目持久面（最大的洞）堵上；项目级写入仍免问，
  理由是「项目内容本来就归 acceptEdits 管」。代价：别人 review 不到的
  自动生效面还留着一半。
- 候选 C·不进名单：维持现状，只在文档里记代价。

### 问 2 · 项目级 skill 的信任/可见性形态？

- 候选 A·装配期提示一行（推荐）：扫到项目级 skill 时 warn 一行
  「加载了 N 个项目级 skills：<names>（来自 <目录>）」，REPL/once 都打。
  「静默生效」的静默二字被去掉；配合问 1 的写面，塞进仓库的 skill
  既躲不过眼睛、也写不回去。成本一行，无状态。
- 候选 B·CC 式信任门禁：首次遇到未信任的项目级 skills 时 ask 确认，
  决定持久化（存 `~/.pai/projects/<slug>/` 标记）；once 无人可问 → 未信任
  默认不加载 + warn。最彻底，但要新增信任存储与首扫交互，once/CI 场景
  会静默少 skill，量级接近独立 feature。
- 候选 C·不做：等真实事故。

### 问 3 · 软链 skill 的附属文件？

- 候选 A·用户级软链解析真身进边界（推荐）：装配时对用户级 skill 的
  base_dir 取 realpath，软链真身根加进 additional——用户自己建的软链
  （dotfiles 形态）视为受信，附属文件在 once 下也可读。项目级刻意不解析：
  仓库里可被塞入指向 `~/.ssh` 之类的恶意软链，自动放行真身等于开
  任意读洞（与问 1 同族的反向面）。
- 候选 B·全部解析（含项目级）：行为一致，但引入上述任意读面，不推荐。
- 候选 C·不做，记录代价：软链 skill 的附属文件在 once 下不可读，
  interactive 下弹框放行。范围小（附属文件 + 软链 + once 三条件叠加）。

### 确认

2026-08-23 用户一轮拍板三问（AskUserQuestion，问题与候选原文见上三节；
理由栏用户未附文字，只记选择本身）：

问 1（acceptEdits 写面）：选择 A·用户级+项目级都进危险写名单。
问 2（项目级信任/可见性）：选择 B·CC 式信任门禁——AI 推荐的是 A（提示一行，
成本低），用户选了更彻底的 B：首遇未信任项目 skills 时 ask 确认并持久化决定；
once 无人可问 → 未信任默认不加载 + warn。实现取舍记在「结果与总结」。
问 3（软链附属文件）：选择 A·只解用户级真身进边界（项目级刻意不解——
仓库可被塞入指向 `~/.ssh` 的恶意软链，自动放行真身等于开任意读洞）。

## 结果与总结

改动四处 src + 测试 11 条（9 新 + 2 处既有场景预置信任标记；详细红→绿见
[devlog.md](devlog.md)）：

- 写面（问 1·A）：`boundary.py` 的 `_DANGEROUS_ANYWHERE` 加 `.pai/skills`
  路径段——用户级与项目级一个模式全覆盖，写 skills 永远 ask、bypass 免疫、
  acceptEdits 翻不过（求值链第 2 步在第 5 步之前）。
- 信任门禁（问 2·B）：`core/skills.py` 新增信任标记（存项目身份目录
  `~/.pai/projects/<slug>/skills_trusted`——不进仓库，塞 skill 的人塞不了
  标记）+ `apply_project_trust`。interactive 首遇未信任项目 skills 用装配期
  asker 问一次，精确选中「信任」才持久化；once 无人可问 → 不加载 + warn
  指路。pty e2e 钉全链（对话在 TUI 前、只在裸字节里，答 1 → TUI 起 →
  目录进 prompt → 标记落盘）。
- 软链附属（问 3·A）：`user_skill_link_roots` 只解用户级真身进
  `WorkingDirs.additional`；项目级刻意不解（恶意软链任意读洞，理由在
  函数 docstring 与拍板记录）。
- 注入反证两处各红各的（名单去项 → acceptEdits 写回 allow；门禁旁路 →
  未信任 skill 混进 prompt），复原后全绿。
- 全量 `./test.sh` → 1307 passed, 3 deselected（交付前 1297）。
- TODO 销账三条：25 复核中 3（软链，全部收掉）、中 4（acceptEdits 写面）、
  25 遗留 1（信任门槛）；遗留 6 追记读面扩展。

## 遗留问题

无新增待办。三条记录性边界（信任项目级一次性、路径段匹配理论误伤、
once 无非交互信任通道）见 [devlog.md](devlog.md)「已知边界」与
[复盘.md](复盘.md)「我现在质疑什么」——均为「撞上再收紧」类，不立 TODO。

## 用到的知识

- [25 档案](../25-20260822-skills/README.md)遗留 1/6 与
  [27 档案](../27-20260823-skill-boundary-exempt/README.md)（豁免位落地后
  additional 的收益面变化，27 复盘质疑三）
- `core/boundary.py` 危险写名单的既有模式（feature 09）
