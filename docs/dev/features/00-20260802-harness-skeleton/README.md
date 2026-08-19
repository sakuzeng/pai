# 00-20260802-harness-skeleton —— 最小可用 harness 基座
状态：已验收（2026-08-02 初版，2026-08-03 经冷眼评审修复后持续演化）
分支：早于本字段的规矩（2026-08-10 立），未回填——分支线性叠，事后用 git 推不出「在哪条上做的」

追认档案（基座先于档案机制完成），指针为准。

## 需求

从零手写最小可用 coding agent harness：`pai "任务"` 能真跑——agent loop、
工具系统（schema 与代码同源）、会话落盘、单次执行模式、CLI/配置。
零框架，参照 pi/CC 设计思想但零代码复用。

## 候选方案与确认

奠基取舍见 decisions D#1-D#28（核心：@tool 装饰器自动 schema 禁手写字典、
工具错误不 throw、core/modes 分离学 pi、依赖注入保离线可测、
usage 真实锚定 D#18、预算熔断 D#21-23）。

## 结果与总结

`src/pai/`：loop.py（预算熔断、usage 锚定落盘）、core/tools/（4 工具）、
session.py（append-only JSONL）、modes/once.py、cli.py/config.py。
基座测试 17（loop）+ 6（tools）+ 4（modes）条；
2026-08-03 冷眼评审 20 条 finding，严重项（R#1/R#2 等）当日修复。
时间线见 ../../archive/devlog-2026-08.md 起始各条（早于档案机制，无目录内 devlog）。

## 遗留问题

评审残余均在 TODO（P2/P3）：session 同秒撞文件名 R#15、loop 无类型注解 R#14、
read_file 截断无分页 R#17、usage 归一化/可信度过滤/按钱计费等。

## 用到的知识

早于 knowledge/ 机制；参照关系散记在 D#1-D#28。
