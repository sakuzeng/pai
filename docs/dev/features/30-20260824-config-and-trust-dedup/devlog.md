# 30 · devlog

## 2026-08-24 · 拍板与 TDD

- 三问全 A（README「确认」；问 3 预拍的是计划第 3 步 xdist 杂务）。
- 红：`tests/test_settings.py` 6 条先行（分层读取 3 + marker/门禁 3）→
  collection 红（原语不存在）。
- 绿：`core/settings.py` 增 `read_settings_layers`（返回 ((路径, dict), (路径,
  dict))，读盘 + 坏 JSON 告警唯一实现）与 `project_trusted` /
  `mark_project_trusted` / `project_trust_gate`（机制一份，文案全参数化）→
  `6 passed`。
- 迁移四个消费方（行为零变化）：
  - permissions.load_rules 换 IO 入口，锚点与 RuleSet 组装一行不动；
    `_read_settings` 删除（坏 JSON 告警文案随之从「权限设置…本层规则按空处理」
    统一为 settings 的「设置文件…本层按空处理」——无测试钉旧文案，
    warn 措辞微变如实记录）；
  - hooks.load_hooks 从「借 permissions 的私有函数」改为消费统一原语，
    顺带删掉自算两层路径的重复；
  - mcp：`_read_servers_layer` 砍成纯 section 解析 `_parse_servers_section`
    （mcpServers 坏 JSON 告警文案同上统一）；trust 三件套变薄适配
    （文案逐字不变）；
  - skills：trust 三件套同样变薄适配（文案逐字不变）；清掉不再使用的
    `project_dir` 导入；
  - settings.load_settings 自身也消费统一原语。
- 受影响面回归：settings/skills/mcp/hooks/permissions/modes 六个测试文件
  `208 passed`（既有断言零改动——refactor 判据成立）。
- 全量：首跑 `1 failed, 1349 passed`（STATUS 数字对账竞态红——更新落在该测试执行之后，复盘有记），复跑 `1350 passed, 3 deselected in 171.57s (0:02:51)`。
