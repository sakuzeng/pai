# 13-alt-screen · 开发日志

<!-- 一步一条，不攒着最后补。全局 devlog 只记里程碑一行 + 指到这里。 -->

## 2026-08-11 立项（未动工）

**目标**：把「工具结果能点」「transcript 能滚」「像新开一个窗口」三件事单独立项。

**为什么现在立**：用户在真跑 feature 12 时连问三条，追下去发现它们**底下是同一个约束**——
谁拥有屏幕。方案 A（12 交付的）只接管底部 dock，进 scrollback 的内容 pai 再也够不着，
所以「点击」不是没做而是**做不到**。要做就得进 alt-screen，那会推翻 roadmap 阶段 2
已拍板的设计原则 2，属「改变那次交付的结果」→ 按 features/README 规矩 7 新建档案。

**用户拍板（三选一）**：甲=键盘展开 / 乙=转 alt-screen / 丙=先甲再单独立项 → **选丙**。
甲已在 feature 12 交付（`^O` 展开被折叠的工具输出）。

**动了哪些文件**：本档案（README 含需求与三个候选）、features/README 交付总览、
TODO、roadmap 阶段 2 就地注记。

**测试**：未动 src，`./test.sh` 不受影响。

**遗留**：三个候选未拍板；前置精读全部未做（`tui-plan.md` 的主体、
`tui-alt-screen.ts`、CC 的 hit-test/selection、SGR 1006 与 DECSET 1049 的实测）。

## 2026-08-11 前置精读 + 反向对照（动工前）

**目标**：把上一条的「前置精读全部未做」清掉。roadmap 阶段 2 原有的四篇笔记
**全是给 main-screen 的**，alt-screen 一篇都没有。

**读了什么**（三篇笔记，均已登记 knowledge/README 并勾进 roadmap 阶段 2「第三批」）：

- [K source-walks/pi-alt-screen.md](../../../../knowledge/source-walks/pi-alt-screen.md)
  —— pi-mono `tui-plan.md`(1001) 的**主体**（feature 12 跳过的那 90%）、
  `tui-alt-screen.ts`(845)、`scroll-view.ts`(195)。
- [K source-walks/cc-alt-screen.md](../../../../knowledge/source-walks/cc-alt-screen.md)
  —— CC `AlternateScreen.tsx`(79) / `hit-test.ts`(130) / `selection.ts`(917) /
  `fullscreen.ts`(203) / `ink.tsx` 的 handleResize 与模式自愈 / `FullscreenLayout.tsx`。
- [K concepts/alt-screen-and-mouse.md](../../../../knowledge/concepts/alt-screen-and-mouse.md)
  —— 可迁移那层（DECSET 1049 / 鼠标三档 / SGR 1006 / DECRQM）。

**读出来的三条会改变候选方案讨论的**：

1. **原则 2 的原文被 pai 转述错了**。pi 的原句是「do not pretend the same constrained
   viewport semantics exist in `TuiMainScreen`」——**「别在 main-screen 里假装」**，
   而 pai 的 roadmap 写成「只做 main-screen 模式，不给 main-screen 假装 sticky 语义」，
   把「不做 alt-screen」这个**范围选择**和 pi 的**论断**捆成了一条。
   要复议的只有 pai 自己加的那半句，pi 那半句照旧成立。
2. **CC 的 alt-screen 对外部用户默认关**（`isFullscreenEnvEnabled()` 里
   `USER_TYPE === 'ant'` 才默认开），且配了三个逃生口 + tmux -CC 同步子进程探测。
   而 `AlternateScreen.tsx` 的 docstring 把「ctrl-o transcript overlay 这类**临时**
   全屏视图」写成它的正当用法——**候选方案 B 不是折中，是 CC 自己写在文档里的用法**。
3. **命中测试便宜（130 行），选区昂贵（917 行）**。「工具结果能点」的门槛不在
   hitTest，在「每帧知道每个组件画在哪个矩形里」；而一旦接管鼠标，
   **终端原生的选中复制就没了**，这是取舍不是遗漏。

**反向对照（动工前）**：写了两个探针（`probe_alt.py` / `probe_resize.py`）+ 一个
AppleScript 驱动，在**新开的**终端窗口里跑（不碰当前会话），抓屏时机由探针自己写的
检查点驱动而不是 sleep 猜。iTerm2 3.6.11 + Terminal.app 470.2，六条结论见
[evidence/说明.md](evidence/20260811-alt-screen反向对照/说明.md)，最要紧的两条：

- **重发 `?1049h` 会清屏 + 光标回原点，不是 no-op**——两个终端一致。
  这**推翻了 CC 源码里的一句注释**（`ink.tsx` 的 `reenterAltScreen()` docstring 说是
  no-op，而同一文件 `handleResize` 的注释说 iTerm2 会当成清屏；前者错）。
  直接后果：**任何「自愈式重进 alt」都会闪白屏**。
- **DECRQM 在 Terminal.app 完全不可用**（12 条查询全超时，同窗口 CPR 正常），
  于是「问终端支不支持某个能力」这条路是堵的——CC 全靠环境变量判断**不是偷懒**。
  且**不被识别的查询会漏成可见字符**：本次差点因此误判「Terminal.app 退出 alt 后
  光标没还原」，把查询顺序换一下结论就反了。**测量手段污染了被测对象。**

另两条对候选方案定价有用的：退出 alt 后**主屏与光标原样还回**（「像新开一个窗口」的
技术前提成立，pai 不必自己保存主屏）；**alt 屏里 resize 之后不全量重绘屏幕就是脏的**
（实测混进了主屏残留文本）。

**跑不到的**：一切需要真实鼠标事件的（点击/滚轮/拖选/1002 vs 1003 的实际吵闹程度）——
osascript 缺辅助功能授权、本机无 cliclick 与 pyobjc，Terminal.app 的自动化权限也没授。
**没测就是没测**，全部进[手工清单](evidence/20260811-alt-screen反向对照/手工清单.md)，
按 roadmap 那句规矩不拿「按源码推」冒充观测。

**动了哪些文件**：新增三篇 knowledge 笔记 + evidence 目录（说明/手工清单/原始数据 11 份/
探针 3 个）；改 knowledge/README 登记表、roadmap 阶段 2 前置精读（第三批 + 动工前反向对照
勾选、交付前留空）、本档案 README「用到的知识」节、本文件。**未动 src。**

**测试**：`./test.sh` → **771 passed, 3 deselected**（与动工前一致，本步纯文档）。

**遗留**：三个候选仍未拍板（下一步 brainstorm）；鼠标那块手工清单待真人跑一次。

## 2026-08-11 brainstorm → spec 定稿

**目标**：拍板三个候选。**结果是把候选重排了**——前置精读之后发现原来的 A/B/C
把两个正交的决定（**什么时候进 alt** × **要不要接管鼠标**）捆成了一条线，
重排成 2×2 之后，中间冒出两格原本不在选项里的形态。

**六问拍板**（原文存档在 [README「确认」节](README.md)）：乙（常驻 alt + 键盘滚动）/
退出不回吐只打提示 / 本轮完全不接管鼠标 / 默认进 + settings 开关 / 搜索不进本轮 /
resume 不顺手做。

**两件我说错、被查证纠正的**：

1. 「alt-screen 会推翻原则 2」——**没有整条推翻，是被拆开了**。pi 的原句是
   「别在 main-screen 里*假装*」，这半句照旧成立；作废的是 pai 自己加的
   「只做 main-screen 模式」，而它本来就是范围选择不是论证结论。
2. 「退出时重渲染完整文档打回主屏」——**我把 pi 与 CC 的做法混成一条推荐了**。
   用户质疑「为什么不和 cc 一样 resume 可以回到之前的会话」，查证属实：
   **CC 退出时不回吐，只打 `printResumeHint()`**（`gracefulShutdown.ts:144`，
   且刻意先退 alt 再打，好让提示落在主屏上）。pi 之所以回吐，是因为它没有会话持久化那一层。
   顺带查清 **pai 的 `--resume` 根本不存在**（`cli.py` 只有 task/--max-steps/--no-session），
   于是这条拍板带出一笔明确的债，已登记 TODO。

**spec 里两个不在原始候选里的设计决定**：

- **transcript 不能存行，要存能按宽度重渲染的条目**。今天 `commit(lines)` 收的是
  按当时宽度排好的行，alt 屏下窗口一变它们就是错的。做法是把 `_answer_lines` /
  `_tool_lines` / `theme.band` 从「commit 时调用」推迟到「渲染帧时调用」+ 按
  `(内容,宽度)` 缓存（照 pi：叶子自己持缓存，框架层不许加第二层）。
- **第一个 task 是扩 `screen.py` 而不是写渲染器**。它现在把私有 CSI 当无操作、
  不认 `H`/`J`，alt 一上线录制回放就是错的、5 条 e2e 全失效——
  feature 14/15 刚建起来的「让 AI 自己看得见界面」会退回到让用户截图。

**动了哪些文件**：新增 [spec.md](spec.md)；README（状态→已拍板、流程→superpowers 全链路、
候选重排成 2×2、六问存档、两处订正）；TODO 新增「feature 13 拍板时已知的债」三条；本文件。
**未动 src。**

**测试**：`./test.sh` → **771 passed, 3 deselected**（本步纯文档）。

**遗留**：spec 待批；批了写 plan（按 task 切，测试数字写下限）。

## 2026-08-11 plan 定稿

**目标**：把 spec 切成可 TDD 的 task。**7 个 task，测试下限合计 ≥51 条**（spec 要求 ≥45）。

**两个决定 task 顺序的结构问题**（读代码撞见的，写进 plan 头部）：

1. **T1 是终端模拟器不是渲染器**。`screen.py` 私有 CSI 一律当无操作、`_csi` 里没有
   `H`(CUP) 也没有 `J`(ED)，strict 下撞上就抛。alt 一上线，回放出图是错的、
   5 条 e2e 当场失效——先把自测闭环补住再动渲染器。
2. **`commit()` 要有两种落点，但只能有一个 Transcript**。接缝定在
   `renderer.keeps_transcript`：alt 留文档（每帧切视口），main 当场渲染成行打进
   scrollback。12 交付的 main-screen 路径**逐字节不变**，拿现有 e2e 钉死。

**task 划分**：T1 模拟器 / T2 Transcript 条目与按宽度缓存 / T3 滚动状态机 /
T4 整屏帧渲染器 / T5 进出 alt 与开关 / T6 接线 / T7 e2e。

**注入反证一共 7 条**，其中一条特意写了断言口径（T4）：
「把行 diff 改成全量写」要断言**写出的字节数变多**而不是「屏幕内容不同」——
屏幕内容本来就一样，照后者写就是 feature 15 那三条假绿的病根。

**动了哪些文件**：新增 [plan.md](plan.md)；README 的流程字段转成正常形态；本文件。**未动 src。**

**测试**：`./test.sh` → **771 passed, 3 deselected**（本步纯文档）。

**遗留**：plan 待批；批了开 T1。

## 2026-08-11 T1-T7 实现（严格 TDD）

七个 task 逐条红→绿，注入反证一并跑。总数从 **771 → 860 passed**（+89 条，plan 的下限是 ≥51）。

| task | 红 | 绿 | 注入反证 |
|---|---|---|---|
| T1 模拟器认备用屏 | `11 failed, 10 passed` | `21 passed` | ①重发 1049h 当 no-op → 1 红；②alt 与主屏共用格子 → 3 红 |
| T2 Transcript 条目 | 收集错误（模块不存在） | `13 passed` | 缓存 key 去掉宽度 → 3 红 |
| T3 滚动状态机 | 收集错误（模块不存在） | `14 passed` | 上滚不关跟随 → 5 红 |
| T4 整屏帧渲染器 | 收集错误（模块不存在） | `16 passed` | 行 diff 改成全量写 → 2 红 |
| T5 进出 alt + 开关 | 收集错误（模块不存在） | `13 passed` | （见 T7 的②） |
| T6 接线 | `13 failed, 1 passed` | `14 passed` | 见 T7 的③ |
| T7 e2e | 2 failed（我自己的测试写错） | `5 passed` | ①补发 1049h 自愈 → 红；②退出不发 1049l → 红；③新内容拽回底部 → **第一轮没红** |

**T7 那条没红的反证，按 feature 15 的规矩查清了**：属于「场景不对」——
e2e 里 PgUp 之后再没有新内容到达，注入点根本没被走到。补上「滚上去之后再问一个问题」
这一步，反证立刻变红（连带打红了两条离线测试）。**不红的测试等于没有**，这次没放过。

**实现过程中撞出来的三条**（都在接缝上，离线单测结构上看不见）：

1. **录制器漏了一整条写入路径**。`TerminalSession` 的写走的是 `sys.stdout`，
   而录制器只包了渲染器的 write——于是录制文件里**没有 `?1049h`**。
   修法是给终端也套上同一个 write（`RecordedStream`）。
   教训是通用的：**号称「记录写给 X 的全部字节」的东西，只要 X 有第二个写入者，
   它记的就是一部分。**
2. **回放按「数换行」估屏幕高度**——alt 屏一个换行都不写，于是估出 24 行，
   而 pai 写的是 30 行的绝对坐标，末尾几行全被钳到最后一行叠成一团。
   症状是「dock 少了几行」，看起来像渲染器画错了，**其实是回放放错了**
   （feature 14 复盘「验证工具自己也要被验证」的第二次实例）。
3. **两遍组帧**：视口高度依赖 dock 高度，而 dock 的状态行又依赖滚动状态——
   第一遍量高度、更新滚动，第二遍才是真的画。第一版拿第一遍的长度去截第二遍的结果，
   在「dock 高度两遍不一样」时把权限框的问题行切掉了（e2e 当场变红）。

**交付前反向对照**（roadmap 固定末项第二条，见
[evidence 第 7-9 条](evidence/20260811-alt-screen反向对照/说明.md)）：
真 iTerm2 里跑完整回合、resize、退出，三样都对。**并且推翻了动工前的一个存疑观察**——
「resize 之后顶部残留主屏内容」是 AppleScript `contents` 的假象，
用 `screencapture` 截真窗口证明屏幕上是干净的。
由它引出的两处代码（渲染器重入保护、resize 强制全量重画）**保留**，因为各自独立成立。

**动了哪些文件**：新增 `tui/transcript.py` `tui/scroll.py` `tui/altscreen.py`
`core/settings.py`；改 `tui/screen.py`（两块缓冲区 + CUP + ED + `?7`）、
`tui/record.py`（`RecordedStream`）、`tui/replay.py`（alt 录制按真实高度回放）、
`tui/keys.py`（PgUp/PgDn/Ctrl+Home/End）、`tui/app.py`（commit 落点分流 + 滚动键）、
`tui/dock.py`（滚动指示）、`tui/renderer.py`（commit 收条目）、`tui/component.py`
（`extract_cursor` 挪进来共用）、`tui/terminal.py`（进出 alt）、`modes/interactive.py`（装配）。
测试新增 5 个文件、改 2 个。

**测试**：`./test.sh` → **860 passed, 3 deselected**。
