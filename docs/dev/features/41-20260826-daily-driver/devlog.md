# 41-daily-driver 开发日志

## Task 1 · `read_file` 的 offset / limit（2026-08-26）

目标：把「每读一个文件就分段拼」从模型手里收回来。此前 `read_file` 只有 `path`，
超过 4000 字符就截断并教模型走 `sed -n`——本仓库 160 个 `.py` 里 92 个超过这条线，
`test_loop.py` 要分 21 次读。

形状按拍板问 1·A：按行的 `offset` / `limit`，`0` 哨兵。
`Optional[int]` 走不通不是猜的——`@tool` 的 `PY_TO_JSON` 只认 str/int/float/bool，
非法类型当场 `raise ValueError`；`shell.clamp_timeout` 为同一条约束用了同一个哨兵。

动的文件：

- `src/pai/core/tools/fs.py`：`read_file` 加两个参数；新增 `_take_whole_lines`
  （按字符预算取整行、至少取一行）；截断文案改指自家 `offset=N`。
- `tests/test_tools.py`：新增 9 条；改写 1 条（见下）。

红：`8 failed, 1 passed`（第 9 条 `test_whole_file_read_is_byte_for_byte_unchanged`
是行为不变的回归守卫，本来就该绿）。
绿：`tests/test_tools.py` `74 passed`。

三处值得记的：

一、截断必须切在整行边界。切在行中间的话，文案报的「继续读用 `offset=N`」就是假话：
那半行要么丢、要么在下一段里重复一遍。而这两种错都不会让任何别的断言变红——
`test_truncation_cuts_at_a_line_boundary_so_the_next_offset_is_exact` 是专门为它写的。

二、验收判据按用户点名的来：不是「测试还绿」，是解析后的值逐字相等。
`test_segmented_reads_reassemble_the_file_verbatim` 把 500 行的文件分段读回来拼接，
与原文 `==`。

三、旧的 `test_read_file_truncation_tells_the_model_how_to_get_the_rest`
（feature 34 按 R#17 的零成本做法写的）改动后**照样绿**，但是因为错的理由：
它的内容是 `"x" * N` 没有换行，落进了新的「单行超预算」分支，而那个分支的文案里
恰好也有 `sed` 与 `bash`。与其留一条名字与实际覆盖对不上的测试，改写成
`test_a_single_over_budget_line_says_offset_cannot_help`，如实钉住那一格：
续读点在行内、offset 表达不了，此时必须说清这一点并把出路指回 bash，
且**不许给一个假的 offset**（断言 `not re.search(r"offset=\d", out)`）。

注入反证五条，全部变红：offset 改 0-based（3 红）、续读点差一（1 红）、
改回按字符切（3 红）、负数参数静默吞掉（1 红）、越界 offset 回空串（1 红）。

## Task 2 · `search_files` 工具（2026-08-26）

目标：找代码不再只能走 bash。路线按拍板问 2·A（新立工具），接线按问 3·A
（边界与并发都声明）。取舍升格成 [D#76](../../decisions.md)。

动的文件：

- `src/pai/core/tools/search.py`（新）：内容正则搜索 + 文件名 glob 过滤；
  `pattern` 传空串则只按文件名找。纯 Python，不依赖 ripgrep。
- `src/pai/core/tools/__init__.py`：`get_tools()` 与 `all_tools()` 两处 import 都加
  `search`（只加一处的后果是权限层认不得它——`all_tools()` 是判定用的那份）。
- `src/pai/tui/dock.py`：动作表加一行「搜代码」。
- `src/pai/core/scheduler.py`：并发上限那段注释里「pai 目前唯一的并发安全工具是
  read_file」已经过期，改成两个。
- `tests/test_search_tool.py`（新，22 条）、`tests/test_tools.py`（内置工具集断言 +1）。

红：`19 failed, 1 passed`（那 1 条是「界外仍要问」，未知工具时也 ask，先绿后要
在实现后为对的理由继续绿）。
绿：`tests/test_search_tool.py` `22 passed`。

三处值得记的：

一、`search_root()` 是权限层与工具本体的共用函数，空 `path` 回落到 cwd。
这里最容易埋的静默 bug 是 `get_path` 回空串：边界判定拿不到路径就退回 ask，
于是「不传 path 的搜索每次都被问」——而那正是模型最常见的调用形态，
且不会让任何别的测试变红。`test_the_declared_path_resolves_the_default_root` 钉它。

二、matcher 不能直接把 `fs.path_matcher` 挂上去：它按 `args["path"]` 取路径，
而空串在那边被判成「取不到路径」直接返回 `False`——权限规则对最常见的调用形态
静默失效。所以包一层 `search_matcher`，先把默认根解出来再交给它。
漏挂 matcher 的话吃的是 `default_matcher`（对**第一个参数值**做通配符匹配），
而这个工具的第一个参数是 `pattern`：规则会拿正则去比对路径 pattern，静默永不命中。

三、测试自己先有一个「因为错的理由变绿」的坑：`os.walk(followlinks=False)`
本来就不跟进目录软链，所以只用目录软链测「跳过越界软链」的话，删掉实现里的
`_escapes_root` 也不会红。补了一条**文件软链**——那种 `os.walk` 是会列出来的，
才是真正需要显式跳过的那一格。

## 注入反证（Task 2，2026-08-26）

八条，最终全部变红。头两轮里有两条没红：

- 删掉 NUL 检查：上一条二进制测试照样绿，因为那个文件里的 `\xff\xfe` 让
  `UnicodeDecodeError` 先接管了，NUL 那一格根本没被走到。
- 删掉文件内命中的 `break`：上限测试照样绿，因为那 30 个文件每个只有一处命中，
  外层的 break 就够了。

按 `knowledge/engineering/mutation-testing-pitfalls.md` 第五条先查实现——查下来
两处实现都是对的（NUL 是合法 UTF-8 码点，含 NUL 的文本文件确实解得开；
一个文件里多处命中确实会冲破上限），是测试漏了两格。补了两条测试，
再注入即红：`test_a_file_that_decodes_but_holds_nul_bytes_is_also_skipped`、
`test_many_matches_inside_one_file_still_respect_max_results`。

八条清单：漏声明 `path_access_for`（3 红）、漏声明 `capabilities_for`（2 红）、
漏挂 matcher（1 红）、`search_root` 回空串（1 红）、不跳越界文件软链（1 红）、
不跳噪音目录（1 红）、不跳含 NUL 的文本（1 红，补测试后）、
文件内命中不受上限约束（1 红，补测试后）。

## 交付（2026-08-26）

`./test.sh` 全量：`1534 passed`（此前 1503；新增 31 条 = read_file 9 + 改写 1 不计
+ search 22）。

刻意没做、已登记 TODO 的：`.gitignore` 解析、搜索性能数字、
单行超上限那一格的行内续读、找内容与找文件是否该拆成两个工具、
decisions 索引从 69 之后的漂移、`SYSTEM_PROMPT` 常量谎报工具集。
WebFetch / WebSearch 按用户指示本轮不做。
