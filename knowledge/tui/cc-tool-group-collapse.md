# CC 的工具组：连续的读搜跑折成一行，模型开口或写改文件就断组

- 来源：CC 反编译源码 v2.1.88（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)），
  `src/utils/collapseReadSearch.ts`（`collapseReadSearchGroups` / `isTextBreaker` / `isNonCollapsibleToolUse` /
  `getSearchReadSummaryText`）、`src/components/messages/CollapsedReadSearchContent.tsx`、
  `src/components/CtrlOToExpand.tsx`、`src/components/messageActions.tsx::useSelectedMessageBg`
  （反编译源码行号会漂，按符号名检索）
- 精读日期：2026-09-12
- pai 锚点：`src/pai/tui/groups.py`、`TuiApp.on_event` / `replay` / `expand_last`，
  docs/dev/features/50-20260912-tool-group-collapse、docs/dev/decisions.md #81

为什么读这篇：用户截图里一轮十几条灰色工具行铺满屏，「(^O 展开)」淡得看不出是入口，
点名要 CC 那种「执行结束之后收起、显示执行了几条命令」。

## 一、分组：对消息列表做后处理

`collapseReadSearchGroups(messages, tools)` 走一遍渲染用的消息列表，把连续的「可折叠」工具
调用累进一个 `GroupAccumulator`，遇到断点就 `flushGroup()` 吐出一条 `collapsed_read_search` 消息。

可折叠（`getToolSearchOrReadInfo`）：read / search / list（ls、tree、du 这类 bash）/ 全屏模式下的
任意 bash / MCP 的读搜（计成 "Queried <server> N times"）/ 记忆文件的读写搜。
断点两种：`isTextBreaker`——assistant 的第一个内容块是非空文本；`isNonCollapsibleToolUse`——
edit / write 这类不可折叠工具（各自单独渲染，Edit 的结果本来就默认画 diff）。
没有最小组大小：单个 read 也是一组「Read 1 file」。

pai 视角：pai 没有「渲染用消息列表」这一层——transcript 是 commit 出来的条目表。所以分组
不能是后处理，只能是状态机：`TuiApp` 持有当前组，ToolStart / ToolEnd 往里加，
AssistantMessage（非空）/ 写改文件 / AgentEnd / 用户再说话把它定格。判据一一对应，形状不同。

## 二、画法：跑着一行现在时，跑完一行过去时

`CollapsedReadSearchContent`：组还在跑（`isActiveGroup` = 最后一组且 isLoading）时，
左边转圈、现在时「Reading 3 files…」+ 下面一行 `  ⎿  <当前文件 / 模式 / 命令>`（每条提示至少
停 700ms，`MIN_HINT_DISPLAY_MS`，不然快工具一帧就闪过去）；跑完是 2 列空 gutter +
`<Text dimColor>`「Read 3 files, searched 2 patterns, ran 4 bash commands (ctrl+o to expand)」。
动词顺序固定（git 操作、search、read、list、REPL、MCP、bash、memory），不按出现顺序。
`(ctrl+o to expand)` 两态都带（`{isActiveGroup && …} <CtrlOToExpand />`）。

`backgroundColor={bg}` 里的 `bg` 来自 `useSelectedMessageBg()`——只有该行被 message actions
的光标选中时才是 `messageActionsBackground`（深色主题 `ansi:blackBright`），平时 undefined。
也就是说 CC 的工具块没有常驻底色，靠 dim + 缩进 + 一行摘要区分；用户截图里的「加深背景」
是选中态。

pai 视角：pai 没有光标选中行，「点开」就是它的选中，所以底色给展开态的内容块
（`theme.TOOL_BG`，比用户行的 `USER_BG` 再暗一档）。摘要词表按动作（读 / 搜 / 看 / 跑 / 记），
顺序同样固定。

## 三、verbose：ctrl+o 之后组内每条各自一行 + 完整结果

`VerboseToolUse` 逐条渲染组里的工具调用（用各工具自己的结果渲染器，`verbose=true`），
没有第二级折叠。pai 照做：展开一级铺全部输出；每条工具结果在工具层已截到 `MAX_OUTPUT_CHARS`，
所以一次铺开有界。

## 四、边界

- CC 主屏对 bash 折叠只在全屏模式（`isFullscreenEnvEnabled()`）开；pai 一律折。
- CC 的摘要能认出 git commit / push / PR（`scanBashResultForGitOps`）并放在最前面；pai 没做。
- CC 有 `groupMessages`（同名工具连续调用的另一层归并，`grouped_tool_use`）；pai 只有工具组一层。
