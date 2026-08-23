# 30-config-and-trust-dedup（settings 统一读取层 + 信任门禁通用化）
状态：已交付
分支：refactor/30-config-and-trust-dedup（本档案全部工作）
流程：中等改动直做（无 spec/plan）——refactor 类，行为与指标都不变；
验收项写进「需求」节（features/README 规矩 9）。

## 需求

优化检查（2026-08-23/24）发现两处结构性重复，触发条件均已命中，合一次交付：

1. settings.json 有四个独立读取者：`permissions._read_settings`、
   `core/settings._read`、`hooks` 自读两层、`core/mcp._read_servers_layer`——
   settings.py docstring 自记的合并阈值是「等第三个读者出现时再合并」
   （feature 13 plan 的遗留），feature 29 让它翻倍越过。四套「读文件 + 坏 JSON
   告警 + 两层分层」的重复实现，改告警文案或分层语义要改四处。
2. 信任门禁三胞胎：`skills.apply_project_trust`（30 行）与
   `mcp.apply_mcp_trust`（27 行）逐条同构，外加 `project_skills_trusted` /
   `mark_project_skills_trusted` 与 `project_mcp_trusted` /
   `mark_project_mcp_trusted` 两对 marker 函数——feature 28/29 连着长出来的
   同一模式，第二个实例已出现，抽通用正当时。

验收标准（怎么算做完）：

- refactor 判据：外部行为零变化——全量测试不改断言全绿（信任门禁的文案是
  模型/用户可见输出，保持逐字不变或同步既有测试断言，改了要在 devlog 说明）；
- settings 读取只此一处：四个消费方（permissions/hooks/mcp/settings 自身的
  section 取值）都走统一读取原语；坏 JSON 告警语义统一且有测试钉住；
- 信任门禁只此一份通用实现：skills 与 mcp 各自是薄适配（标记名 + 文案参数）；
  两侧既有门禁测试（apply 级 + 装配级 + e2e）全绿；
- 新原语带单测（正常 + 坏文件路径，AGENTS 测试规矩）；
- `./test.sh` 全绿，数字与交付前一致（1344 passed, 3 deselected——refactor
  不加行为测试，只加原语单测，数字允许因新增单测而增加并如实记录）。

## 候选方案与确认

### 问 1 · settings 统一读取的形态

- 候选 A·分层读取原语（推荐）：`core/settings.py` 提供
  `read_settings_layers(cwd, home, warn) -> (user_dict, project_dict)`
  （读文件 + 坏 JSON 告警一份实现），permissions/hooks/mcp 改为消费原始两层
  dict，各自的 section 解析（RuleSet 组装、hooks 解析、mcpServers 校验）
  留在各自模块不动。改动面最小：权限层 100+ 测试只换 IO 入口，求值链一行不碰。
- 候选 B·大一统 Settings 对象：一次读取解析全部 section，各模块收成品。
  更彻底，但把权限解析搬进 settings 层——权限层是被测试盯得最death的模块，
  为「不重复」去动它的解析路径违背 feature 13 当年不动它的同一理由。

### 问 2 · 信任门禁通用化的落点

- 候选 A·通用门禁进 core/settings.py（推荐）：`project_trust_gate(marker,
  items, describe, *, cwd, home, ask, warn)` 与 marker 读写对——信任的对象
  就是「项目级配置」，与 settings 分层同属一层；skills/mcp 各留一行适配
  （标记名与文案作参数），公开函数名与签名不变（调用方零改动）。
- 候选 B·独立 core/trust.py 新模块：边界更清晰，但为两个消费者立一个
  单函数模块，与「不预防性拆分」相抵。

### 问 3 · pytest-xdist 接入方式（第 3 步杂务的预拍板，避免二次往返）

- 候选 A·可选旗标 + 观察期（推荐）：xdist 进 dev 依赖，`./test.sh -n auto`
  可用但默认仍串行；「pty e2e 偶发挂死」旧账未确诊前不把并行设为默认，
  试点数字与稳定性记录进 TODO，跑稳一段再复议默认值。
- 候选 B·直接默认并行：省时立竿见影（预计 2:46 → <1 分钟），代价是挂死
  旧账若被并行放大，全量红会变成常态噪音。

### 确认

2026-08-24 用户一轮拍板三问（AskUserQuestion，问题与候选原文见上三节；三问均选
A 即推荐项；理由栏用户未附文字，只记选择本身）：

问 1：A·分层读取原语（`read_settings_layers` 返回两层原始 dict，section 解析
留在各消费方——权限求值链一行不碰）。
问 2：A·通用门禁进 core/settings.py（信任的对象就是项目级配置；skills/mcp
公开函数名与签名不变，文案作参数保持逐字不变）。
问 3：A·xdist 可选旗标 + 观察期（挂死旧账未确诊前不改默认；试点数字记录在案）
——此问预拍的是本计划第 3 步杂务，不在本档案改动面内。

## 结果与总结

两处重复各收敛为一份实现，行为零变化（详细见 [devlog.md](devlog.md)）：

- `core/settings.py`：`read_settings_layers`（唯一读盘 + 坏 JSON 告警）+
  `project_trusted` / `mark_project_trusted` / `project_trust_gate`（通用门禁，
  文案全参数化）。原语单测 6 条先红后绿。
- 四个消费方迁移：permissions（删 `_read_settings`，求值链一行不动）、
  hooks（不再借 permissions 私有函数）、mcp（`_parse_servers_section` 纯解析 +
  trust 薄适配）、skills（trust 薄适配）。两侧门禁文案逐字不变，
  受影响六个测试文件 208 条既有断言零改动全绿。
- 唯一的行为微变如实记：坏 JSON 告警文案统一为 settings 的中性版
  （「设置文件…本层按空处理」），无测试或文档依赖旧文案。
- 全量 `./test.sh` → 1350 passed, 3 deselected（交付前 1344，+6 为原语单测；
  中间一轮数字对账竞态红，复盘有记）。
- TODO 销账 feature 13 时代的「两处读 settings」旧账（触发条件命中）。

## 遗留问题

无新增。两条记录性质疑见 [复盘.md](复盘.md)（告警文案统一的边界、
门禁参数宽度到第三个消费者再收），均不立 TODO。

## 用到的知识

- 优化检查实测数字（2026-08-23 会话）：装配全环节 <1ms、MCP 16ms/server、
  冷 import 0.47s（启动侧无肉的依据）；套件 166s、top-18 慢测约 86s。
