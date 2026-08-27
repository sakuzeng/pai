# 46-tool-steering 开发日志

## Task 1 · `search_files` 吃单个文件（2026-08-27）

feature 45 实测发现 A2 的后一半：模型已经知道文件在哪、只想在里面找一行，
而 `search_files` 报「搜索根不是目录」，于是「找代码用 search_files」这条引导
在最该生效的时候失效，模型退回 bash 并弹一次窗。

红：3 failed。绿：`tests/test_search_tool.py` 26 passed。

顺带改掉一条既有断言：`test_a_missing_search_root_is_reported` 原本还断言
「path 是文件也算错」——那一半被**刻意放开**了，测试改成如实描述。

## Task 2 · `list_dir` 工具（2026-08-27）

新增 `core/tools/listing.py`。接线照 feature 43 的 `roots.py`（`path_semantics`），
没写第四份「默认根解析 + matcher 包装」。

红：模块不存在。绿：`tests/test_listing.py` 15 passed。

噪音目录判断**复用 `search_files` 的同一份对象**而不是抄一份，
并顺带把它从 `SKIP_DIRS` 集合升级成 `is_noise_dir()`（多认一类后缀式噪音：
`*.egg-info` 是每次 `pip install -e` 都会重建的构建产物，与 `__pycache__` 同类，
只是名字带包名所以列不进那张表）。测试里有一条断言两边是同一个对象。

## Task 3 · 提示引导 + 结构注入（2026-08-27）

`build_system_prompt` 加 `project_root` 参数与五句条件化引导
（read_file / search_files / run_tests / git_read / list_dir），
`bash` 的工具描述收紧成「先确认没有更合适的专用工具再用它」。
四个调用点（once / interactive ×2 / commands）都传 cwd。

红：6 failed。绿：`tests/test_tool_steering.py` 7 passed + 1 skipped。

一处自己踩的坑：`bash` 的 docstring 首行我第一版写成
「先确认没有更合适的专用工具（feature 46）」——**首行是发给模型的**，
把内部档案号写进去等于让模型读我的提交记录。当场改掉。

## 造 `render_tree` 时撞出的两个问题（2026-08-27）

都是生成出来一看就不对，离线测试全绿。

**一、`tests/` 的 60 个文件把预算吃光。** 第一版是「深度 2 + 全局 120 项上限」，
在本仓库上生成出来：`tests/` 列了 60 个测试文件，而 `src/` 只显示到 `pai/`
——摘要里没有一点源码结构，等于没写。加了 `MAX_FILES_PER_DIR = 8`
（骨架比枚举重要，每个目录只给几个样本）。

**二、深度优先 + 全局上限，会让最重要的目录整个消失。** 改成深度 3 之后，
`src/` **根本没出现**——字母序在前的 `docs/` `evals/` `knowledge/`
`pai_playground/` 把 120 项吃光了，而提示语只说「还有 N 项未列出」。
也就是说最要紧的那个目录可以完全不见，且看不出来。
改成**预算按层分配（广度优先）**：第一层永远完整，深的层次才去抢剩下的。
最终定在深度 2（试过 3，在本仓库上更差：深层把预算吃光，`src/pai/` 反而
一个子目录都列不出来），往下挖交给 `list_dir`。

第三个小问题：每个目录省略的文件数原本不计进总的截断说明，
于是「每个目录都省了 50 个文件」会显示成「0 项未列出」。

## Task 4 · `--llm` 验收（2026-08-27）

`tests/test_llm_steering.py` 三条，默认跳过（要 `PAI_RUN_LLM_TESTS=1`）：
模型会选 `run_tests` 而不是 bash 跑 pytest、会选 `search_files` 而不是 grep、
第一步不再拿 bash 探路。断言写成能容忍随机性的形状——不要求「只用了那一个」，
只要求「用了它」且「没拿 bash 去干它的活」。

真跑三遍：`3 passed in 8.11s / 7.06s / 6.92s`。稳定。

这是本轮**唯一能证明它有用的测试**。feature 45 的全部教训就是离线断言
「提示语里有那几个字」证明不了「模型看了会听」。

## 端到端真跑：数字很吵，如实记（2026-08-27）

拿 feature 45 那个原始问题（「read_file 的输出截断上限是多少」）在真仓库上跑：

| | 工具调用 | 其中 bash | 权限弹窗 | 用时 |
|---|---|---|---|---|
| feature 45（改动前） | 8 | 4 | 4 | 15s |
| feature 46 第一次 | 7 | 2 | 2 | 13s |
| feature 46 第二次 | 12 | 3 | 5 | 35s |

第二次明显更差，而看弹窗内容，模型跑到**父目录**去搜了
（`search_files(path=/Users/…/agent)`）——那是模型自己走岔了，不是改动的锅，
但也说明**单次运行不是测量**。

所以本轮不拿这三个数字声称改进。可靠的证据是上面那三条 `--llm` 测试
（针对性强、跑三遍稳定）。端到端的数字如实贴在这里，包括更差的那一次。

第一次那跑里有一处直接验证：模型真的用上了
`search_files(path='src/pai/core/tools/fs.py')`——Task 1 加的单文件搜索根。

## 交付（2026-08-27）

`./test.sh` 全量：`1683 passed`（此前 1656；新增 27 条 = search 4 + listing 15 +
steering 8；另有 3 条 `--llm` 默认跳过）。
注入反证 8 条全部变红。

收尾时改掉一条自己写的坏测试：接线那条第一版写成「`assemble` 返回里有没有
`system_prompt`，没有就 `pytest.skip`」——它**永远在 skip**，也就是一条永不执行的
接线测试，而它守的恰恰是 feature 33 H9 那个「配了/写了却没接进装配」的教训。
改成 monkeypatch `once.build_system_prompt` 钉住真正传进去的那个 kwarg，
注入「once 不传 project_root」当场变红。
