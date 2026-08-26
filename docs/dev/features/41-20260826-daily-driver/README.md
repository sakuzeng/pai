# 41-daily-driver

状态：已交付
分支：`feat/41-daily-driver`
流程：中等改动直做（无 spec/plan）。理由：两条改动各自形状明确，且三处形状选择
      在动工前已由用户用 AskUserQuestion 拍板（记在下面「候选方案与确认」节），
      没有需要先设计的整体方案。搜索工具虽是新工具，但它的每一处接线
      （matcher / path_access / capabilities）都有 fs 三件套的现成同款可照抄。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

用户 2026-08-26：把 pai 推到「能拿来做日常开发」这一格，这是能力补齐不是批清 TODO。
目标是能用 pai 在一个真实仓库里做「查一处实现 / 改一个函数 / 加一条测试」这种粒度的活，
而不需要每读一个文件就分段拼、每找一次代码就被问一次权限。

用户已经查清、明确说不要重查的证据：

- `read_file` 截断在 4000 字符且没有 offset。本仓库 160 个 `.py` 里 92 个超过这条线，
  `test_loop.py` 要分 21 次读。现在的做法是提示语教模型用 `sed -n` 分段，
  那是把成本转嫁给模型，TODO 里也写着「真正的解法是 offset 参数」。
- 没有搜索工具。找代码只能走 bash，而 bash 默认 ask，会被问到烦；
  一旦配 allow 白名单绕开询问，bash 就绕过了工作目录边界（D#52 的已知洞）。
  安全与顺手在这里是真冲突，不要假装能两全。
- 没有网（WebFetch / WebSearch），本轮不做。

范围：只做前两条（`read_file` 的 offset、一个搜索工具）。其余想到的一律登记 TODO。

上游 TODO 条目（两条都在本轮销账）：

- 「`read_file` 的截断提示没有真模型验证（34 复盘质疑三）」，原文里已经写着
  *"倾向于 offset 参数才是正解（那是可测的），零成本做法只是把成本转移给了模型"*。
- 「`read_file` 截断后无分页/offset（R#17）」那条的注记：*"真正的分页/offset 参数仍没做"*。

验收标准：

1. offset 是「解析后的值逐字相等」级别的验收，不是「测试还绿」——同一个文件全文读
   与分段读拼起来，内容要逐字相同。
2. 搜索工具在工作目录内调用一次都不被问（走 `_boundary_fallback` 的「读 → 界内 allow」），
   界外 ask；这条要有测试钉，不能靠推理。
3. 新工具带正常路径 + 至少一个错误路径的单测（AGENTS「测试」一节）。
4. 每条改动做一次注入反证：把实现改坏，证明测试会红。
5. `./test.sh` 全量绿，STATUS 数字同步。

## 候选方案与确认

三处形状由用户 2026-08-26 用 AskUserQuestion 一次拍板，三问全选推荐项。
以下是问题原文、每个候选及其取舍、用户的选择。

### 问 1：`read_file` 的 offset 参数取什么形状？

约束背景：`@tool` 的 schema 生成器只认 str/int/float/bool（`PY_TO_JSON`），
`Optional[int]` 会被它当场 `raise ValueError`；`shell.py` 的 `clamp_timeout` 为此
用了 `0` 哨兵，那段注释写着「改装饰器是动『schema 与代码同源』那块基石，
为一个参数不值当」。

- 候选 A·行号 `offset` + `limit`，`0` 哨兵（用户选中）。坐标系是「行」：
  `offset=1` 从第一行起，`limit=0` 用默认上限。与现有截断文案教的 `sed -n` 同一套坐标，
  模型不用换算；也与 CC 的 Read 一致。
  代价：截断上限仍按字符算，行读进来后还要按 `MAX_OUTPUT_CHARS` 再截一次，
  两个坐标系并存——文案里必须同时报「读到第几行」与「全文共几行」。
- 候选 B·字符 `offset` + `limit`，`0` 哨兵。好处是与现在的文案「全文共 N 字符」
  一个坐标系到底，不并存两套。代价：offset 会切在行中间，模型拿到半行；
  而且定位一个函数时模型手里只有行号，得先换算出字符位置。
- 候选 C·只加 `offset` 不加 `limit`，每屏固定 `MAX_OUTPUT_CHARS`。参数最少。
  代价：模型想精确取某个函数的 20 行做不到，还得回去走 bash——本轮的目标正是
  把这种活从 bash 手里收回来，少了 `limit` 收得不彻底。
- 候选 D·单个 `range: str = ""` 传 `"120,180"`。绕开 int 哨兵问题，一个参数表达一段。
  代价：等于自己发明一套要解析的迷你语法，错误路径（空串/倒序/非数字/单边）全要写，
  与「schema 与代码同源」的精神相悖——schema 里它只是个 string，约束全在 docstring 里
  靠模型自觉。

用户选 A。

### 问 2：搜索能力走哪条路？

- 候选 A·新立一个搜索工具（用户选中）。纯 Python 实现（`os.walk` + `re`，
  不依赖 `rg`——本机的 `rg` 在 `/Applications/ChatGPT.app/Contents/Resources/rg`，
  是那个 app 自带的，系统没装）。权限后果：它有自己的名字，于是能挂
  `path_access_for(READ)`，走 `_boundary_fallback` 的「读 → 界内 allow / 界外 ask」——
  界内搜索一次都不问，用户不需要配任何白名单，且不经过 bash 那条洞。
  代价：搜索得自己写，gitignore 语义、二进制文件跳过、大仓性能都要自己处理，
  且不会有 rg 那么快。
- 候选 B·给 bash 配只读白名单（`allow=["Bash(rg *)", "Bash(grep *)"]`）。零实现成本。
  权限后果正是 D#52 那个洞在这条路上被放大：bash 结构上不参与目录边界
  （不声明 `get_path`/`access`），白名单一配，`rg foo ../../..` 与 `grep -r password /etc`
  全部畅通，pai 没有任何机制把它拉回界内。allow 的「每个子命令都要匹配」拦得住
  `rg foo && rm -rf x`，拦不住越界的搜索根。外加 rg 不一定装了。
- 候选 C·两条都做。覆盖最广，代价是把 B 的洞照样引进来，而 A 本可以让它不必存在；
  且本轮范围用户划的是两条，这会变成三条。

用户选 A。

### 问 3：新搜索工具要不要参与目录边界与并发调度？

漏声明的后果是静默的：边界那边退回 ask（每次搜索都弹），调度那边静默退回串行。

- 候选 A·边界 + 并发都声明（用户选中）。`path_access_for(READ)` 取搜索根路径 +
  `matcher_for` 复用 fs 的 `path_matcher`（软链双路径）+
  `capabilities_for(read_only=True, concurrency_safe=True)`。
  后果：界内搜索直接 allow 不问，界外 ask；可与 `read_file` 并发。
  必须写明的诚实边界：边界判的是「搜索根」这一个路径，而遍历会读到根下每个文件——
  根在界内、树里有指向界外的软链时判定管不到。实现里显式跳过指向界外的软链，
  并把这条限制写进档案与模块注释，不假装没有。
- 候选 B·只声明边界，不声明并发。边界照样界内 allow 不问，但调度静默退回串行。
  搜索是纯读，理论上并发安全，这条是刻意保守。代价：与读文件排队，模型一轮发多个搜索时慢；
  而且「不声明」与「声明了 False」在代码里长得一样，下一个人分不清是想过了还是忘了
  （`fs.py` 那段注释批评的正是这个）。
- 候选 C·两个都不声明（照 bash 的样子）。结构上不参与边界判定，落进兜底
  「未声明路径语义 → ask」。后果是每次搜索都问一次——直接违背本轮目标。
  只有在「搜索根本无法表达成一个路径」时才该这么选，而它能表达。

用户选 A。

## 结果与总结

两条都做了，全量 `1534 passed`（此前 1503）。开发过程见
[devlog.md](devlog.md)，取舍升格成 [D#76](../../decisions.md)。

一、`read_file(path, offset, limit)`：按行分段，`0` 哨兵。截断切在整行边界，
文案给出的续读 `offset` 逐字接得上；文案改指自家 offset，不再教模型走 `sed -n`。
验收按用户点名的判据做成「分段读拼回全文、逐字相等」，不是「测试还绿」。

二、`search_files(pattern, path, glob, max_results)`：内容正则 + 文件名 glob，
`pattern` 传空串则只按文件名找。纯 Python，不依赖 ripgrep（本机那个 `rg` 是某个 app
自带的，系统没装；外部二进制在不在会变成「同一段代码在别人机器上结果不同」）。
三件声明齐全，于是界内搜索走 `_boundary_fallback` 的「读 → 界内 allow」，
一次都不问，且不需要用户配任何 allow 白名单去换——那条路会绕开目录边界（D#52）。

验收标准五条的对账：

1. 逐字相等 —— `test_segmented_reads_reassemble_the_file_verbatim` 钉住。
2. 界内不问 / 界外 ask —— `test_searching_inside_the_working_dir_is_allowed_without_asking`
   与 `test_searching_outside_the_working_dir_still_asks`，走真的 `permissions.decide`，
   不是断言声明字段。
3. 正常路径 + 错误路径 —— 搜索工具 3 条错误路径（坏正则 / 根不存在或不是目录 /
   负 max_results），`read_file` 2 条（负参数 / offset 越界）。
4. 注入反证 —— Task 1 五条、Task 2 八条，全部变红；其中两条头一轮没红，
   查下来是测试漏了两格（不是实现错），补测试后即红，过程记在 devlog。
5. `./test.sh` 全量绿、STATUS 数字同步 —— 都做了。

## 遗留问题

每条已同步登记 TODO（「feature 41 遗留与发现」节）。

- `read_file` 的行坐标系够不着「单行超上限」那一格：续读点落在行内，
  offset 表达不了。现在如实说明并把出路指回 bash，刻意不给一个假的 offset。
- `search_files` 不解析 `.gitignore`：噪音目录是一张硬编码名单。
- `search_files` 的性能一个数字都没有；`MAX_FILES_SCANNED = 20000` 是未实测的经验值。
- 边界只管搜索根，不管遍历到的每个文件（拍板问 3 认下的诚实边界）：
  遍历自己跳过指向根外的软链，那是工具的自觉，不是边界判定。
- 找内容与找文件合在一个工具里（CC 是 `Grep` + `Glob` 两个），
  代价是 schema 表达不出两个参数互斥。
- decisions 的索引表从 69 之后就没再维护，而校验它的那条测试看不见 70+ 的形式。
- `loop.SYSTEM_PROMPT` 常量仍谎报工具集（只在老路径上生效，且「逐字不变」是刻意的）。

## 用到的知识

- `knowledge/engineering/mutation-testing-pitfalls.md`（注入反证第五条：反证不红时先怀疑实现）
