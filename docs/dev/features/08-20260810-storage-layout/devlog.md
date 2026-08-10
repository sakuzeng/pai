# 08-20260810-storage-layout · 开发日志

基线：`259 passed, 3 deselected`（`feat/08-storage-layout` 自 `main` 开出）。

## 2026-08-10 · Task 1：`core/paths.py` 路径唯一事实源

**目标**：把「`~/.pai` 在哪、项目目录怎么算」从三处（`memory.py` / `config.py` /
`interactive.py`）收敛到一处，slug 换成可读的全路径连字符。

**改动**：新建 `src/pai/core/paths.py`、`tests/test_paths.py`。

**测试**：红 `ModuleNotFoundError: No module named 'pai.core.paths'` → 绿 `6 passed`。

**实测 slug**：`-Users-sakuzeng-improve-coding-agent-projects-pai`——与 CC 同形。

**设计要点**：`test_known_slug_collision_is_documented` **把已知缺陷钉成了测试**，
断言 `/a-b/c` 与 `/a/b-c` 确实撞成同一 slug。它不测正确性，测的是「将来有人想顺手修好时，
先撞见这条测试并读到理由」——CC 就是这么拼的，加转义就不再与 CC 同形，
而那正是本需求的诉求。

## 2026-08-10 · Task 2：`memory.py` 转调 paths

**改动**：`memory.memory_dir` 转调 `paths.memory_dir`，删掉重复的 `_git_root` 与 hashlib 依赖；
对外签名不变，`build_context` / `memory_tool` 的调用点一行没改。

**测试**：`test_memory_dir_now_lives_under_the_readable_slug` 断言目录名含连字符且长于
16 位哈希；既有的「git 根归并」「非 git 回退」全绿。

## 2026-08-10 · Task 3：`SessionLog` 落用户目录 + sessionId/cwd + 去碰撞

**目标**：**本轮最要紧的一条**——不再往当前工作目录写 `sessions/`。

**改动**：`src/pai/core/session.py` 重写（默认目录取 `sessions_dir()`、每条记录带
`sessionId` 与 `cwd`、文件名加短 id）。

**测试**：红 5 条 → 全套绿。四条关键断言：当前目录不出现 `sessions/`、
每条记录带 `sessionId`+`cwd`、同秒两个 SessionLog 得到两个文件（**关掉 R#15 旧账**）、
文件名保留时间戳前缀。

**一处刻意的写法**：默认参数写 `None` 再在函数体里取 `sessions_dir()`，
**不能**写成 `directory=sessions_dir()`——默认参数在函数定义时求值，
测试隔离 `$HOME` 之后就追不回来（feature 05 补漏五刚在 `history_path_for` 上栽过同款，
这次是照着教训写的，没再红一次）。

## 2026-08-10 · Task 4：装配层与可见性

**改动**：`once.py` / `interactive.py` 的 `SessionLog()` 无参调用自动吃到新默认值（零改动）；
`_show_memory` 增加「💾 会话记录目录」一行。

**测试**：`272 passed, 3 deselected`（259 → 272，+13）。

## 2026-08-10 · 端到端实测（真跑，非测试）

在 `/tmp/othersproject`（模拟别人的项目）里跑一轮再退出：

```
$ ls -a /tmp/othersproject
.  ..                     ← 只有这两个，没被拉屎（整个需求的初衷）

$ ls ~/.pai/projects/-private-tmp-othersproject/sessions/
20260810-221805-36c2fc1a.jsonl

记录字段: ['content', 'cwd', 'role', 'sessionId', 'ts']
cwd : /private/tmp/othersproject      ← 集中存放后仍分得清在哪跑的
```

`/memory` 同时显示两个目录，slug 可读。
