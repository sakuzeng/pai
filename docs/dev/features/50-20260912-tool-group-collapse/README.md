# 50-tool-group-collapse
状态：已交付
分支：`feat/50-tool-group-collapse`（2026-09-12 从 `main` 切出，全部改动在这一条）
流程：中等改动直做（无 spec/plan）：改的是 TUI 里工具结果的呈现形态（transcript 条目层 + 轮末折叠），不新开路线图模块；取舍点列成四问在本档案拍板，验收项写在「需求」节。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

出处：[需求池 2026-09-12](../../需求池.md)，用户原话「优化一下这个界面，感觉当前的展开，收起有点不明显，
不像claudecode这样的加深背景（同时在执行结束之后会收起，显示执行了几条命令）」，附两张截图：
一轮里十几条 `└ read_file(...) → … +99 行 (^O 展开)` 灰线铺满整屏，末尾的「(^O 展开)」淡得看不出是个入口。
改的是 feature 12/13/16 交付的工具行形态与 48 的回放形态，旧档案冻结，本档案链回
[12](../12-20260811-tui/README.md)、[16](../16-20260811-mouse-and-selection/README.md)、
[48](../48-20260910-resume-transcript-replay/README.md)。

一句话：一轮跑完之后，工具调用折成一行摘要（「读了 5 个文件，搜了 2 次，跑了 3 条命令」），
展开/收起的入口与边界一眼可见；活轮次里逐条上屏的行为不变。

CC 2.1.88 的做法（反编译，按符号名；走读笔记见「用到的知识」）：

- `utils/collapseReadSearch.ts::collapseReadSearchGroups` 对消息列表做后处理：连续的可折叠工具
  （read / search / list / bash / MCP 的读搜 / 记忆读写）合成一个 `collapsed_read_search` 组；
  遇到模型的非空文本（`isTextBreaker`）或不可折叠工具（edit / write，`isNonCollapsibleToolUse`）
  就断组。没有最小组大小：单个 read 也是「Read 1 file」。
- `components/messages/CollapsedReadSearchContent.tsx` 把组画成一行：跑完是 2 列空白 gutter +
  dim 文本「Read 3 files, searched 2 patterns, ran 4 bash commands (ctrl+o to expand)」
  （`<Text dimColor={!isActiveGroup}>` + `CtrlOToExpand`）；跑着时是转圈 + 现在时
  「Reading 3 files…」+ 一行 `⎿` 提示当前文件/模式/命令（每条至少停 700ms，`MIN_HINT_DISPLAY_MS`）。
- `backgroundColor={bg}` 只在该行被光标选中时才有（`useSelectedMessageBg` →
  `messageActionsBackground`，深色主题下是 `ansi:blackBright`）——用户截图里的「加深背景」
  就是这个选中态，不是工具块的常驻底色。CC 靠 dim + 缩进 + 一行摘要区分工具块。
- verbose（ctrl+o）下组展开成每条工具各自一行 + `⎿` 结果。

验收标准（怎么算做完）：

- 单测（纯函数）：给一轮的工具事件序列 → 分组：连续读/搜/看目录/跑命令/看 git/跑测试合成一组，
  遇到答案文本或写/改文件断组；摘要文案按 dock 的 `_ACTIONS` 词表（「读了 5 个文件，搜了 2 次，
  跑了 3 条命令」），单数不加「了 1 个」的怪话；拿真实轨迹（`tests/fixtures/resume_session.jsonl`，
  10 个并发工具批）当输入。
- 单测（TuiApp）：`AgentEnd` 之后 transcript 里那一轮的 N 条工具行被一条组条目替换；组条目可展开
  （点击 / ^O）；写/改文件的行不进组、且按问 1 决定是否默认展开 diff。
- 单测：48 的回放走同一条折叠逻辑（同一个渲染器），回放出来的旧对话也是折叠形态。
- 单测：背景带按问 2 的选择渲染；`NO_COLOR` 下一个转义符都不吐（theme 第二条硬约束）。
- e2e：真进程里一轮多工具任务跑完，屏幕上只剩一行摘要 + 答案；^O 之后工具行出现。
- 注入反证：拿掉轮末替换 → e2e 红；拿掉断组判据 → 分组单测红。
- `./test.sh` 全绿，数字贴 devlog。

非目标：

- 活轮次的显示改成 CC 那种「正在读 3 个文件… + ⎿ 当前文件」——pai 的 dock 活动区已经是这个角色
  （按动作聚合计数 + 明细行），不重复做（问 4 若选 A）。
- CC 的光标选中行（message actions）整套；git 操作识别（commit / push / PR 出现在摘要里）。
- REPL / once 路径（`render_text` 一行契约，43/44 遗留同一条线）。

## 候选方案与确认

### 方案 A · 轮末折叠成组（照 CC）

- 新增 `tui/groups.py`（纯函数）：`group_tool_events(items) -> List[Group|Single]`，判据照
  `collapseReadSearch`：可折叠 = 读文件 / 搜代码 / 看目录 / 跑命令 / 跑测试 / 看 git / 记笔记，
  断组 = 答案文本、写文件、改文件、ask_user_question。文案照 dock 的 `_ACTIONS` 词表。
- `TuiApp`：一轮里 commit 的工具条目记在 `_turn_entries`；`AgentEnd` 时按分组把它们从 transcript
  里换成组条目（`Transcript.entries` 就地替换，位置不变）；组条目 `expandable_entry`：折叠态一行
  摘要「读了 5 个文件，搜了 2 次，跑了 3 条命令 (^O 展开)」，展开态列出每条工具行（保留各自的
  「→ 首行 … +N 行」）。`_collapsed` 表照旧登记每条工具事件，^O 逐条看完整输出不变。
- 48 的 `replay` 走同一条分组，回放与活轮次一个形态。
- 改动面：`tui/groups.py` 约 100 行、`tui/app.py` 约 60 行、测试约 150 行。

### 方案 B · 整轮折成一条

- 不区分断组，`AgentEnd` 时该轮全部工具行折成一条「本轮 12 次工具调用」。
- 更简单，但 CC 的断组是有理由的：模型中途说的话与写/改文件是用户要看的节点，
  全折进去就找不到「它在哪一步改了文件」。

### 方案 C · 只改视觉不折叠

- 工具行加底色带、「(^O 展开)」加亮；不做轮末折叠。
- 用户点名的「执行结束之后会收起，显示执行了几条命令」没兑现。

### 确认

拍板（2026-09-12）：用户原话「都可以照cc的来呢」。四问逐条对到 CC 2.1.88：

问 1：折叠范围与断组？选择：A。CC `collapseReadSearchGroups`：连续可折叠工具合组，
`isTextBreaker`（模型非空文本）与 `isNonCollapsibleToolUse`（edit / write）断组；edit / write 各自
一行，CC 的 FileEditTool 结果默认就画 diff——pai 顺带兑现 45-B2。

问 2：背景加深？选择：A。CC 工具组折叠态是 `dimColor`、无常驻底色；`backgroundColor` 只在
`useSelectedMessageBg`（光标选中行）时出现。pai 没有光标选中行，点击展开就是它的「选中」，
所以底色给展开态的内容块。

问 3：展开层级？选择：B（CC 形态）。CC 的 ctrl+o 进 verbose：组内每条工具各自一行 +
`⎿` 完整结果，没有第二级。pai 每条工具结果在工具层已截到 `MAX_OUTPUT_CHARS`，一次铺开有界。
候选 A 那句「一条 ls 占半屏」的担心由工具层截断兜着，不另设层级。

问 4：活轮次显示？选择：B（CC 形态）。CC 跑着时组是「Reading 3 files…」现在时 + 一行 `⎿`
当前文件 / 模式 / 命令提示（`MIN_HINT_DISPLAY_MS = 700`），工具不逐条上屏；跑完换成过去时 +
「(ctrl+o to expand)」。pai 照做：组条目在第一条可折叠工具到来时创建、随事件就地更新，
`AgentEnd` 或断组时定格。dock 活动区原样保留（它是状态行，CC 底部也有转圈行；跑着的工具
与计时是它的信息，组的 `⎿` 提示是最近一个工具）——两处信息有重叠，登记遗留看真用再定。

## 结果与总结

交付（2026-09-13）：一轮里连续的读/搜/看/跑折成一条会更新的条目——跑着「正在读 3 个文件… (^O 展开)」
+ `⎿ 当前文件`，跑完「读了 3 个文件，跑了 4 条命令 (^O 展开)」dim 灰；模型开口 / 写改文件 / 轮末 /
用户再说话断组；写改文件单独一行且默认展开 diff；^O 或点击展开一级铺全部输出、整块暗底；
48 的回放走同一状态机。只在备用屏分组，main-screen 照旧。

- 新增 `src/pai/tui/groups.py`；`TranscriptEntry.invalidate`；`theme.TOOL_BG`；`TuiApp` 的组状态机。
- 测试：`tests/test_tui_groups.py` 10 条 + e2e 1 条；四条真跑点击测试改到组的契约（其中一条契约反转，
  理由写在测试里）。两处注入反证各红。
- 数字：相关 `208 passed`，e2e `3 passed in 17.94s`，全量 `1734 passed`
  （更新 STATUS 前一跑 `1 failed, 1733 passed, 8 deselected in 195.76s`，红的是测试数校验）。

详细日志见 [devlog.md](devlog.md)，复盘见 [复盘.md](复盘.md)，取舍升格为 [D#81](../../decisions.md)，
走读笔记 [K tui/cc-tool-group-collapse.md](../../../../knowledge/tui/cc-tool-group-collapse.md)。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处，否则等于没记 -->

- 活轮次的 `!命令` 仍全量上屏，回放侧已进组（接 48 遗留）。
- 展开长组后摘要行被顶出视口，不知道怎么收。
- `⎿` 提示没有 CC 的 700ms 最短停留。
- CC 摘要能认 git commit / push / PR，pai 没做。
- dock 活动区明细与组的 `⎿` 提示信息重叠。

## 用到的知识

- K [tui/cc-alt-screen.md](../../../../knowledge/tui/cc-alt-screen.md)（备用屏下 transcript 条目可重画——就地替换条目的前提）。
- K [tui/cc-tool-group-collapse.md](../../../../knowledge/tui/cc-tool-group-collapse.md)（本轮走读：
  `collapseReadSearchGroups` 的判据、`CollapsedReadSearchContent` 的两态画法、暗底只在选中行）。
