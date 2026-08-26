# 36-path-scoped-instructions · 开发日志

一步一条。全局 devlog 只记里程碑一行 + 指到这里。

## 2026-08-26 · 立项与拍板

目标：把需求池 2026-08-19 那条（用户表态要做的「子目录懒加载 + 路径作用域规则」）
升格立项。

用户在「阶段 1-7 全交付之后接哪一件」里选了这条，于是按流程立档案、
把需求池那条登记里写死的三个必答问题变成拍板问，一轮问完，三问全选 A：
挂点在 loop 的工具结果回填处、注入形态当第二个召回块、本轮只做路径作用域规则。
问答原样存进 [README](README.md)。

写 spec 时另定了一处偏离官方并升格 [D#75](../../decisions.md)：规则目录里
不带 `paths:` 的文件不加载（官方那边它们是常驻的）。理由是目标一致性——
这个功能的收益命题就是降低常驻成本，在同一个功能里再开一条常驻通道与它相反。

改动：新建档案（README/spec/plan），`.active` 指过来，开分支
`feat/36-path-scoped-instructions`。

测试：无（尚未动代码）。

## 2026-08-26 · Task 1+2：规则发现与 glob 匹配

目标：`.pai/rules/` 与 `~/.pai/rules/` 递归发现、`paths:` 两种写法解析、
glob 匹配（`**` 跨目录、`*`/`?` 不跨 `/`）。

两处值得记的取舍：

`paths:` 认两种写法（行内逗号与 YAML 列表块）。行内是 pai 自家 frontmatter 子集的
形状，列表块是官方文档里的形状——用户从 CC 抄一份过来必然写后者。只认前者的话
失效方式是沉默的：`paths:` 值为空 → 当成没写 paths → 整条规则被跳过。
解析放在 `rules.py` 自己做而不是扩 `memory.parse_frontmatter`：后者是拍平的
str→str，表达不了列表，而为此引 PyYAML 不划算（那条「不引 PyYAML」的理由仍成立）。

匹配不用 `fnmatch`：它的 `*` 会跨 `/`（`*.md` 能匹配 `docs/a.md`），对路径规则
来说是错的语义，且这个错很难在测试里被注意到。自己把 glob 翻成正则。

改动：`src/pai/core/paths.py`（`user_rules_dir` / `project_rules_dir` /
`project_root`）、`src/pai/core/rules.py`（新）、`tests/test_rules.py`（新）。

红：`ImportError: cannot import name 'rules' from 'pai.core'`（整个文件收集失败）。
中途红一次：`test_broken_files_do_not_explode` 里那个「围栏没收尾」的坏文件被
当成了半个合法规则（`patterns=('[未闭合',)`）——改成先确认收尾围栏再解析，
与 `memory.parse_frontmatter` 同一条约定。
绿：`tests/test_rules.py` `11 passed`。

## 2026-08-26 · Task 3：选择与渲染（以及一次自证）

目标：碰到的路径 → 该注入哪几条规则的正文，带去重、单篇截断、每步条数上限。

这一步没做到严格的先红后绿：`select_and_render` 与 Task 1/2 在同一个模块里
一次写完，于是它的测试是绿于到达的。按仓库规矩这不算 TDD，所以补了注入反证——
把实现改坏五次，逐次确认对应的测试真的会红：

```
去掉去重（already injected 照样注）       → 1 failed, 18 passed
一步注入不设上限                         → 1 failed, 18 passed
单篇不截断                            → 1 failed, 18 passed
项目外路径也参与匹配                       → 1 failed, 18 passed
去掉「不是用户指令」声明                     → 1 failed, 18 passed
```

改动：`src/pai/core/rules.py`、`tests/test_rules.py`。
绿：`19 passed`。

## 2026-08-26 · Task 4：loop 挂点

目标：loop 在一步的工具结果全部回填之后，把「这一步碰了哪些文件」交给注入回调。

路径怎么从 args 里取下放给工具自己声明（`Tool.get_path`）——loop 只负责问一句、
收集、交给回调，它不认识规则也不认识记忆。只算真跑过的调用：被权限拒绝的连跑
都没跑，中断的批同理。`bash` 在这里恒为 None（它不声明路径语义，同 D#52），
所以 `cat 文件` 对这条管线不可见——已知豁口，写进 `rules.py` 的模块注释与一条测试，
不假装堵住了。

注入点与 steering 同一处（所有结果回填之后）：插在中间会劈开 tool_calls 与它的
结果，配对当场断裂。回调返回空串不插消息（塞一条空 user 消息是白烧 token）。

改动：`src/pai/core/loop.py`、`tests/test_loop.py`。

红：五条全是 `TypeError: run_agent() got an unexpected keyword argument
'on_paths_touched'`。绿：`tests/test_loop.py` `104 passed`。

## 2026-08-26 · Task 5+6：装配接线与 /memory

目标：装配期扫一次规则、跨轮持有注入表、接进 once 与 REPL/TUI 两条路；
`/memory` 能看见规则。

`on_context_rewritten`（feature 35 建的那条通道）在这里有了第二个消费者：
压缩/`/clear` 之后 `RuleState.injected` 与 `RecallState.surfaced` 一起清。
35 复盘质疑二说的「它可能该是一条事件而不是回调」因此更值得复议了——
但本轮不改，第二个消费者只是让判断的证据更足，还不构成非改不可。

`/memory` 加一节：列规则文件、它的 `paths`、以及本会话是否已注入。这层的失效
方式天然是沉默的（规则没进上下文，模型照样给一个像样的回答），所以它必须能被看见。
没有规则目录时一节都不打（反向守卫钉住）。

改动：`src/pai/modes/assembly.py`、`src/pai/modes/once.py`、
`src/pai/modes/interactive.py`、`tests/test_assembly.py`、`tests/test_interactive.py`。

红：装配五条 `AttributeError: 'Assembly' object has no attribute
'on_paths_touched'` / `TypeError`；`/memory` 两条。
绿：`test_interactive + test_assembly + test_modes + test_rules + test_loop`
`235 passed`。

## 2026-08-26 · 纵切与一个真 bug

单元接线全绿而纵切坏掉，是这个仓库反复踩的形状（feature 12 被用户打回的三条
bug 全在接缝上）。所以补了一条纵切：真跑一轮 REPL（假 client + 真工具 + 真装配），
模型 `read_file` 一个匹配文件之后，第二次请求里必须带着规则正文、而第一次不许有。

注入反证：把 loop 里那句 `_extend` 拆掉，`2 failed`（纵切与 loop 单测各一条），
装回即 `116 passed`。

随后自己查出一个真 bug 并补测试修掉：`_relative` 拿项目根去拼相对路径，
而模型给的相对路径是相对 cwd 的（工具就是这么打开文件的）。在子目录里启动
pai 时这两个基准不是同一个——`web/a.css` 会被算成 `<根>/web/a.css`，
而模型指的是 `<根>/子目录/web/a.css`。子目录启动是 pai 撞过的场景（feature 27
就是它），所以这不是假想。修完连带发现七条测试此前是靠「基准恰好一致」蒙对的
（它们没 chdir 到 tmp_path），一并改成真实姿态。

红：`test_relative_paths_resolve_against_cwd_not_the_project_root`；
修完中途 `5 failed`（就是那七条里靠蒙的部分）→ 全部改成 chdir 之后 `20 passed`。

## 2026-08-26 · 交付：全量与文档

`./test.sh`（venv `~/.virtualenvs/pai`，Python 3.9.6）：

```
1481 passed, 3 deselected in 163.84s (0:02:43)
```

`./test.sh --fast`（本轮之前 feature 35 刚加的快循环）：`1449 passed / 36.59s`。

新增 33 条测试（`tests/test_rules.py` 20 条 + loop 5 条 + 装配 6 条 + `/memory` 3 条，
其中一条是纵切）。
