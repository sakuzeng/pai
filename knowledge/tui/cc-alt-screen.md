# CC 的 alt-screen：一个默认对外**关着**的功能，和它为此付的代价

- 来源：CC 反编译源码 v2.1.88（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `src/ink/components/AlternateScreen.tsx`(79)、`src/ink/ink.tsx`(1722，看 `handleResize` /
  `enterAlternateScreen` / `reassertTerminalModes` / `reenterAltScreen` / `setAltScreenActive`)、
  `src/ink/hit-test.ts`(130)、`src/ink/selection.ts`(917)、`src/utils/fullscreen.ts`(203)、
  `src/components/FullscreenLayout.tsx`、`src/screens/REPL.tsx`
  （反编译源码行号会漂，**按符号名检索**）
- 精读日期：2026-08-11
- pai 锚点：`src/pai/tui/terminal.py`、`src/pai/tui/renderer.py`、
  docs/dev/features/13-20260811-alt-screen、roadmap 阶段 2 原则 2 的复议

**为什么读这篇**：pai 要做「像新开了一个窗口」，而 CC 是唯一一个**在同一个产品里
同时保留 main-screen 与 alt-screen 两种形态**的参照物——它怎么切、切完付什么，
比「alt-screen 怎么写」更有信息量。

---

## 一、进出 alt 只有 4 行代码，坑全在**时序**上

`AlternateScreen.tsx` 整个组件就是：进入时写 `1049h` + `2J` + `H`（+ 鼠标），
卸载时写（关鼠标 +）`1049l`。真正值钱的是它用 **`useInsertionEffect` 而不是
`useLayoutEffect`** 那一大段注释（原文在 sourcemap 里）：

> react-reconciler 在 mutation 与 layout 提交阶段之间调 `resetAfterCommit`，
> 而 Ink 的 `resetAfterCommit` 会触发 `onRender`。用 `useLayoutEffect` 的话，
> **第一次 onRender 会先于这个 effect 触发**——于是一整帧被画在**主屏**上，
> 然后我们才进 alt；这一帧被保存下来，**退出 alt 时作为一个坏掉的视图重新出现**。

> **可迁移的教训**：「进 alt」与「画第一帧」的先后顺序错了，症状不在进入时，
> **在退出之后**（主屏上多出一帧脏东西）。pai 没有 React，但同样有
> 「装配 → 首次渲染 → 进入终端模式」三步，顺序错了同样会在退出时才暴露。
> 与 [K injection-seams](../engineering/injection-seams.md) 的「装配期」是同一类账。

组件的 docstring 还点了一句 pai 直接能用的：
「Safe for use in **ctrl-o transcript overlays** and similar temporary fullscreen
views — the main screen is preserved.」——**CC 官方认可「只在转录视图时进 alt」
是这个组件的正当用法**（即 pai 候选方案 B 的形态）。

## 二、**默认关**：`isFullscreenEnvEnabled()` 是一票否决的三层判据

`src/utils/fullscreen.ts` 是本篇最该记的一节。CC 的 alt-screen 形态（内部叫
fullscreen / no-flicker）**对外部用户默认关闭**：

```ts
if (isEnvDefinedFalsy(CLAUDE_CODE_NO_FLICKER)) return false   // 显式关，最高优先
if (isEnvTruthy(CLAUDE_CODE_NO_FLICKER))       return true    // 显式开
if (isTmuxControlMode())                       return false   // tmux -CC 自动禁用
return process.env.USER_TYPE === 'ant'                        // 只有内部员工默认开
```

配套还有两个**更细的**逃生口：

- `CLAUDE_CODE_DISABLE_MOUSE`：保留 alt 屏与虚拟滚动，但**不开鼠标捕获**——
  注释写明动机：「so tmux/kitty/terminal-native **copy-on-select keeps working**」。
- `CLAUDE_CODE_DISABLE_MOUSE_CLICKS`：滚轮留着，点击/拖动丢掉，
  防止误点触发光标定位/选区/消息展开。

`isTmuxControlMode()` 那段更能说明代价：为了判断自己是不是在 `tmux -CC` 里，
CC **同步 spawn 一个 tmux 子进程**去问 `#{client_control_mode}`。注释解释为什么必须同步：
异步探测输给了 React 渲染——「by the time the async probe resolved we'd already
entered alt-screen with mouse tracking enabled. Mouse wheel is dead in iTerm2's -CC
integration, so **users couldn't scroll at all**.」

还有 `maybeGetTmuxMouseHint()`：tmux 里 `mouse off` 时提示用户
「scroll with PgUp/PgDn · or add 'set -g mouse on'」——注释记着一段被推翻的历史：
它们曾经在进 alt 时替用户 `tmux set mouse on`，结果**改掉了同一 session 里所有其他
pane 的行为**，还会在 kill-pane 或多实例竞争时泄漏；现在改成「不碰用户状态，只告诉他」。

> **pai 视角，这一节是三个候选方案的定价单**：
> alt-screen 不是「写完就能用」，它带来一串**环境判定与逃生口**。
> CC 有整个团队，仍然选择**默认不给外部用户开**。
> 这不构成「pai 不能做」，但构成「pai 做的话，默认值要慎重、逃生口要有」。

## 三、`handleResize`：一段几乎每句都在讲代价的注释

`ink.tsx` 的 `handleResize`（符号名检索）：

- **刻意不去抖**。注释：去抖会开一个窗口，期间 `stdout.columns` 是新的、
  内部记的列数与 Yoga 布局是旧的——任何 spinner/时钟触发的渲染都会让 log-update
  发现宽度变了而清屏，然后去抖再触发一次，**双重「空白→重画」闪烁**。
- **同尺寸事件直接 return**：「Terminals often emit 2+ resize events for one user
  action (window settling)」。
- alt 屏下：重置前后帧缓冲（下一帧每个格子都重写）、**重新发一次鼠标使能**
  （有些模拟器 resize 时会把它复位）。
- 两条「**不要做什么**」，都点名了具体后果：
  - **不要写 `ENTER_ALT_SCREEN`**：「iTerm2 treats ?1049h as a buffer clear even when
    already in alt — that's the blank flicker.」
  - **不要写 `ERASE_SCREEN`**：render 可能要 ~80ms，先擦的话这段时间屏幕是全黑的。

> ⚠️ **同一份文件里 `reenterAltScreen()` 的 docstring 却写着
> 「ENTER_ALT_SCREEN is a terminal-side no-op if already in alt」——两句互相矛盾。**
> pai 实测（iTerm2 3.6.11 与 Terminal.app 470.2）：**重发 `?1049h` 会清屏并把光标
> 打回原点**，即前一句对、后一句错，且不是 iTerm2 独有。
> 证据见 [features/13 evidence](../../docs/dev/features/13-20260811-alt-screen/evidence/20260811-alt-screen反向对照/说明.md)
> 第 1 条；机制见 [K alt-screen-and-mouse](../tui/alt-screen-and-mouse.md)。

## 四、命中测试便宜，选区昂贵

**命中测试**（`hit-test.ts`，130 行）几乎是白送的：

```
hitTest(node, col, row)：矩形不含就返回 null；子节点**倒序**遍历（后画的在上）；
返回最深的命中节点。矩形来自 nodeCache——由 renderNodeToOutput 填，
**坐标已经是屏幕坐标，滚动偏移已经算进去了**。
```

`dispatchClick` 从命中点沿 `parentNode` 冒泡，谁挂了 `onClick` 谁触发，
支持 `stopImmediatePropagation`；顺带做「点击即聚焦」（往上找第一个有 `tabIndex` 的祖先）。
`dispatchHover` 做 enter/leave 的集合差分（**不冒泡**，与 DOM 一致）。

> **这一节直接回答 pai 那个需求**：「工具结果能点」的技术门槛**不是命中测试**——
> 命中测试是「每帧记下每个组件画在哪个矩形里，然后按坐标反查」，一百多行。
> 门槛是**「每帧知道每个组件画在哪个矩形里」**这件事本身，
> 而这正是 pai 现在没有的（打出去就归终端了）。

**选区**（`selection.ts`，917 行）是另一个极端。开了鼠标捕获，终端原生的选中复制就没了，
得自己实现，而它的字段列表就是一张坑清单：

- `anchor` / `focus` / `isDragging`：锚点与当前点，渲染时才归一化成 start≤end。
- `anchorSpan`：双击选词/三击选行之后再拖，要从**整个词/行**开始扩展。
- `scrolledOffAbove` / `scrolledOffBelow` **+ 两个平行的 softWrap 位图**：
  屏幕缓冲只有当前视口，拖到边缘自动滚动时**滚出去的那些行的文本要另存**，
  否则复制出来缺一截；而「这一行是不是上一行的软折行续行」得同时存，
  才能在复制时把折行拼回逻辑行。
- `virtualAnchorRow` / `virtualFocusRow`：PgDn 把锚点钳位之后再 PgUp，
  不记住钳位前的真实位置就会**高亮与复制内容对不上**。
- `lastPressHadAlt`：靠 SGR 的 alt 修饰位反推「VS Code 的
  macOptionClickForcesSelection 是不是关着」，好在 footer 上显示正确的提示。

> **pai 视角**：这 917 行是**「拿走鼠标」的真实标价**。
> pai 若开鼠标而不实现选区，用户会失去「选中复制」——这是每天都在用的功能，
> 且失去的方式是静默的（拖一下没反应）。CC 给了 `CLAUDE_CODE_DISABLE_MOUSE`
> 正是因为这条真的会咬人。

## 五、alt 屏是个**需要自愈**的状态，而自愈没法靠问终端

`reassertTerminalModes()` 的 docstring 列了四种会把 CC 踢出 alt 屏或清掉终端模式的情况：
**tmux detach→attach、ssh 重连、笔记本睡眠唤醒、事件循环停顿**——
「none of which send SIGCONT」。于是 CC 有一套探测（>5s stdin 静默 + 事件循环停顿检测）
在事后把模式补回去。

补的时候还分轻重：鼠标使能是**幂等**的，随便补；
Kitty 键盘协议是**栈**（`CSI >1u` 是 push），所以每次都先 pop 再 push，
否则每次空闲都涨一层，退出时那一次 pop 排不干净，**shell 会留在 CSI u 模式里、
Ctrl+C 变成转义序列漏出来**；
而 alt 屏重进是**破坏性的**（会擦屏），所以只在「有强信号确认终端真的掉出了 1049」
时才做，用 `includeAltScreen` 参数区分。

另有 `enterAlternateScreen()` / `exitAlternateScreen()`（把终端交给 vim/nano 这类外部
编辑器再收回来），注释里那句最值得记：终端编辑器自己会写 smcup/rmcup（`?1049h/l`），
**即使 CC 本来就在 alt 屏里，编辑器退出时的 rmcup 也会把它掉回主屏**；
不重新进 alt 的话，随后的 `2J` 会**擦掉用户主屏的 scrollback**。

> **pai 视角**：这是 alt-screen 独有的**一整类失败模式**——
> 「我以为我在 alt 屏，其实不在」。main-screen 下不存在这个状态，
> 因为没有「我在哪个屏」这个状态。
> 而实测发现**没法问终端**：Terminal.app 完全不回 DECRQM（见 evidence 第 2 条），
> 所以 CC 全靠环境变量与启发式**不是偷懒，是没得问**。

## 六、CC 在 alt 屏里的布局：`FullscreenLayout` 与 pi 的形状一模一样

`FullscreenLayout.tsx` 的 docstring：「In fullscreen mode, puts scrollable content in a
sticky-scroll box and pins bottom content via flexbox. Outside fullscreen mode,
renders content sequentially so the existing main-screen scrollback rendering works
unchanged.」——**同一棵组件树，两种组合方式**，与 `tui-plan.md:13` 的
「two different compositions, sharing the same component instances」是同一条设计。

`REPL.tsx` 里 `<AlternateScreen>` 出现在**根**（注释：「so nothing can accidentally
render outside it」），高度被钉成 `rows`，于是溢出**必须**由 `overflow: scroll` 处理——
alt 屏没有原生 scrollback 兜底。

fullscreen 打开后连**内容折叠策略都跟着变**：`collapseReadSearch.ts` 里多处
`if (isFullscreenEnvEnabled())` 分支（Bash 结果折叠、搜索工具折叠的口径都不同）。

> **pai 视角**：这条是「两条渲染路径」代价的实证——
> CC 的 fullscreen 开关不只影响渲染器，**渗透到了工具结果怎么折叠**这一层。
> pai 现在已经有「tty 走 TUI / 非 tty 走 REPL」两条路（12 复盘质疑四），
> 再加一条 alt/main 分叉，就是 2×2。

## 七、pai 可以照抄 / 必须重想 / 直接不要

| CC 的做法 | pai | 理由 |
|---|---|---|
| `hitTest` 倒序遍历 + 矩形缓存 + 沿父链冒泡 | **照抄** | 一百多行，是「能点」的全部机制 |
| 「进 alt」必须早于「第一帧」 | **照抄** | 顺序错了在**退出后**才暴露，极难反推 |
| resize 不去抖 + 同尺寸丢弃 | **已有**（feature 12 T8），alt 下**改成全量重绘** | 实测 alt 屏 resize 后屏幕是脏的 |
| resize 时**不**补发 `1049h`、**不**先擦屏 | **照抄，且这是硬约束** | 实测两个终端重发都会清屏 |
| 一整套逃生口（关 fullscreen / 关鼠标 / 关点击） | **照抄「要有逃生口」这件事** | 但 pai 不该学它用三个环境变量——权限层已有两层 `settings.json` |
| tmux -CC 同步探测 | **不要**（先记着） | 真撞上再说；但要知道「有些终端组合下 alt+鼠标是不可用的」 |
| 917 行自研选区 + OSC 52 | **不要**，且**必须把「失去终端原生选中复制」写进取舍** | 这是用户每天用的功能，静默失去最伤 |
| 睡眠唤醒/重连后的模式自愈 | **重想** | 值得做，但「重进 alt」会清屏，只能配合全量重绘 |
| fullscreen 开关渗透进工具折叠策略 | **明确不要** | 那是 2×2 路径爆炸的开始 |
