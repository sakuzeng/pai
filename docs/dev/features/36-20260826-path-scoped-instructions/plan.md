# 36-path-scoped-instructions · 实施计划

六个 task，逐个 TDD（先红后绿，红的输出贴进 devlog）。
前四个是纯函数与核心，离线可测；后两个是接线。

## Task 1：规则发现与 `paths:` 解析（`core/rules.py`）

测试先行：`.pai/rules/` 与 `~/.pai/rules/` 递归发现 `*.md`；
`paths: a, b` 与 YAML 列表块两种写法都解析成同一个元组；
不带 `paths:` 的跳过并 warn 一次（warn 文案含出路 `PAI.md`）；
坏 frontmatter / 读不了的文件跳过不炸。

实现：`Rule(name, path, patterns, base)` + `scan_rules(warn, cwd, home)`。

验收：新测试全绿。

## Task 2：glob 匹配（`core/rules.py`）

测试先行：`src/**/*.py` 匹配 `src/a/b.py` 不匹配 `src/a.txt`；
`*.md` 不跨 `/`；`docs/` 前缀匹配其下一切；
绝对路径与项目外路径不参与；Windows 分隔符不管（目标平台 macOS/Linux）。

实现：`matches(rel_path, patterns)`，把 glob 翻成正则（`**` → `.*`，
`*` → `[^/]*`，`?` → `[^/]`），其余字符转义。

验收：新测试全绿，含一条注入反证（把 `**` 的翻译改成 `[^/]*` 即红）。

## Task 3：选择与渲染（`core/rules.py`）

测试先行：碰到匹配路径 → 返回带 `<system-reminder>` 的块且含「不是用户指令」；
同一条不重复注入（`RuleState.injected`）；不匹配的永远不出现；
单篇超 `MAX_RULE_CHARS` 截断并说明；一步超过 `MAX_RULES_PER_STEP` 只注前 N
且说明还有几篇没注（不许静默丢——与 25 遗留 3 那条追记同一条规矩）。

实现：`RuleState` + `select_and_render(paths, rules, state, project_root)`。

验收：新测试全绿。

## Task 4：loop 挂点（`core/loop.py`）

测试先行：一步里 `read_file` 之后，下一轮请求的 messages 里有规则正文；
被权限拒绝的调用不触发；中断的批不触发；`bash("cat x")` 不触发；
回调返回空串时不插消息（不许插空 user 消息）。

实现：工具结果回填之后收集本步真执行过的调用的路径
（`tools[name].get_path(args)`，脏参数与异常一律跳过），去重后调
`on_paths_touched(paths) -> str`，非空则 `_extend`。

验收：新测试全绿 + 既有 loop 测试不动。

## Task 5：装配接线（`modes/assembly.py` / `once.py` / `interactive.py`）

测试先行：`assemble` 产出的 `on_paths_touched` 真能从磁盘选中规则；
`on_context_rewritten` 一并清 `RuleState.injected`（压缩后能重新注入）；
once 与 REPL 两条路都把回调传给了 `run_agent`。

实现：`assemble` 里 `scan_rules` 一次（装配期）、`RuleState()` 跨轮持有、
闭包接 `select_and_render`；`Assembly` 多一个字段。

验收：新测试全绿。

## Task 6：`/memory` 看得见（`modes/interactive.py`）

测试先行：`/memory` 输出里列出规则文件名与它的 `paths`，并标出已注入的。

实现：`_show_memory` 加一节。

验收：新测试全绿；`./test.sh` 全量绿，STATUS 数字同步。
