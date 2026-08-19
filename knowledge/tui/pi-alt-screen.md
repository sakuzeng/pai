# pi 的 alt-screen：一套约束式布局系统，以及它到底要多少东西

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  根目录 `tui-plan.md`(1001)、`packages/tui/src/tui-alt-screen.ts`(845)、
  `packages/tui/src/components/scroll-view.ts`(195)、`packages/tui/src/layout.ts`(402)、
  `packages/tui/src/layout-node.ts`(51)
- 精读日期：2026-08-11
- pai 锚点：`src/pai/tui/`、roadmap 阶段 2 原则 2（本篇是复议它的输入）、
  docs/dev/features/13-20260811-alt-screen

为什么读这篇：feature 12 读 `tui-plan.md` 时发现它 90% 在讲 alt-screen，
而当时明确不做，只用了三处（见 [pi-tui-main-screen 第〇节](pi-tui-main-screen.md)）。
现在那 90% 是主线——因为用户提的三件事（工具结果可点、transcript 可滚、像新开一个窗口）
底下是同一个约束：谁拥有屏幕。

---

## 〇、一句话结论

pi 把 alt-screen 当成另一个渲染器（`TuiAltScreen` 与 `TuiMainScreen` 并存），
不是给 main-screen 打补丁；为它引入了一整套 VStack / HStack / ScrollView + 内部布局树。
`tui-plan.md` 的第一句核心决策就是：「The constrained layout system is an
alternate-screen feature.」——能力清单不同，所以是两套东西。

## 一、原则 2 的原文，与它没说的那半句

`tui-plan.md:28-36`（feature 12 已引过，这次要看反面）：main-screen 模式下终端拥有滚动，
应用无法可靠提供——sticky 行、可独立滚动的嵌套区、满高左右分栏、
对已滚进 scrollback 的内容做可靠的鼠标命中测试、不重放不清屏就重绘屏外区域。

结论句：「Therefore, do not pretend the same constrained viewport semantics exist in
`TuiMainScreen`.」

关键：这句话是「不要在 main-screen 里假装」，不是「不要做 alt-screen」。
pai 的 roadmap 原则 2 写的是「只做 main-screen 模式，不给 main-screen 假装 sticky
语义——理由见 tui-plan.md」，把两件事捆成了一条。前半句是 pai 的范围选择，
后半句才是 pi 的论断。 复议时该被推翻的只有前半句，后半句照旧成立。

对照 pi 自己给出的两种形态（`tui-plan.md:38-70`）：

```
main-screen：一份垂直排下来的文档            alt-screen：滚动区 + 固定 dock
header / 资源 / 对话 / 待发 / 状态 /          ┌──────────────┐
组件 / 编辑器 / footer                        │ 可滚动的 transcript │
（谁在上谁在下由 addChild 顺序决定，           ├──────────────┤
  没有「贴底」这回事）                        │ 待发 / 状态 / 编辑器 / footer │
                                             └──────────────┘
```

`tui-plan.md:72` 有一条产品判断值得记：待发消息与状态必须在固定区——
「Hiding active queue/working state while the user reads older output would be surprising.」
（用户往回翻历史时，把「正在跑什么、排了几条」藏起来是反直觉的。
pai 的 dock 现在正是这两样东西。）

## 二、要做 alt-screen，最小得引入什么

`tui-plan.md` 的公开 API 只有三个组件，但每个都不小：

| 东西 | 干什么 | pai 要付的 |
|---|---|---|
| `VStack` / `HStack` | 主轴尺寸分配：`basis`/`grow`/`shrink`/`minSize`/`maxSize`/`visible` | 一个 flex 子集分配器。整数取整必须确定（`tui-plan.md:412`：leftover 按子序分配，否则布局逐帧抖） |
| `ScrollView` | 视口 + `scrollTop` + follow-end + 溢出链 | 见下节，状态机比想象的多 |
| 内部布局树 `LayoutBox` | rect / clip / 父子 / 叶子行数组 / 滚动祖先 / 层级 | 每帧重建（`tui-plan.md:343`），组件树长命、布局树是一帧的快照 |

另外三条是「不做也得想」的：

- 叶子渲染缓存不许再加一层（`tui-plan.md:376`）：Markdown/Text/Image/Box 自己按
  `(内容, 宽度)` 缓存，框架层再加 `WeakMap<Component, Cache>` 会陈旧——
  因为失效语义归组件自己所有。（pai 的 `Component.invalidate()` 已经是这个模型。）
- 裁剪时保住光标（`tui-plan.md:423`）：叶子被竖向裁掉时，若它的行里含 `CURSOR_MARKER`，
  要挑一个包含该标记的可见行窗口。否则输入框被挤出视口 = 光标消失 = IME 跑飞。
- 终端太小时的优先级（`tui-plan.md:448`）：保 1 行 transcript > 保编辑器光标 >
  保 1 行 footer > 先裁 widget 与状态。这条是产品决策，不是布局算法，
  pi 明说宁可让调用方用 `minSize`/`shrink` 表达，也不把领域优先级写进通用 TUI。

## 三、`ScrollView` 的状态比「一个 scrollTop」多得多

`scroll-view.ts` 195 行里，真正的滚动逻辑不到 40 行，其余是跟随与钳位的状态机：

- `follow: "end"`：起始跟随；内容长高时自动贴底；手动往上滚关掉跟随；
  滚回底部或显式 `scrollToEnd()` 重新打开跟随（`scroll-view.ts:114-160`）。
- `scrollBy()` 返回没用掉的 delta，嵌套滚动靠它链式冒泡（`tui-plan.md:223-234`）：
  请求 +3 只动得了 1 就返回 +2，父级 ScrollView 接着消费；`overscroll: "contain"`
  则到此为止。
- `updateLayout(contentHeight, viewportHeight, …)`：视口高度变了要保住 scrollTop
  （除非在跟随态）——resize 时用户不该被弹走。
- 滚动条是瞬态的：`auto` 模式下滚动时出现、1 秒后消失（`scrollbarHideDelayMs`），
  还要区分「鼠标悬在滚动条上」（`setScrollbarActive`）。

pai 视角：「流式输出时用户正在往回翻」这个场景，follow-end 状态机是唯一的答案。
pai 现在没有这个问题——因为内容一打出去就归终端了，用户滚不滚 pai 都不知道。
一旦持有屏幕，「新内容来了要不要跟着走」就变成 pai 必须回答的问题。

## 四、`TuiAltScreen` 的实现里，真正扎手的是终端级细节

`tui-alt-screen.ts` 845 行，布局只占一小块。逐项看代价：

进出（`beforeTerminalStart` / `afterTerminalStop`，:170-228）

```ts
ENTER_ALT_SCREEN = "\x1b[?1049h"      DISABLE_AUTOWRAP = "\x1b[?7l"
ENABLE_MOUSE = "\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1004h\x1b[?1006h"
```

进：`1049h` + 关自动折行 + 鼠标 + `2J` + `H` + 藏光标，一次写完。
出：反序关掉，然后把整份文档以无界高度重渲染一遍打到主屏上（:213-223）——
即 `tui-plan.md:679` 的「Final document on stop」：
不能拿最后一帧当退出文档（那是被裁剪过的视口），要重新渲染完整的逻辑文档，
`ScrollView` 此时吐出完整子内容而不是视口。

这条对 pai 很关键：alt 屏退出后，会话历史要不要留在终端里？
pi 的答案是「留，而且是重新渲染一份完整的」。不做这一步的话，用户退出 pai 之后
终端里什么都没有——这与今天 pai 的行为（历史都在 scrollback 里）是可见的倒退。

鼠标（:362-534）：SGR 与老式 X10 两种编码各解析一遍（`\x1b[<b;x;yM` 与
`\x1b[M` + 3 字节）；滚轮要判 `button & 64`、方向取 `button & 3`；
拖动是 `button & 32`；释放是结尾 `m` 还是 `M`。
路由是「命中测试 → 从最深的框往根走 → 每个 ScrollView 试着吃 delta → 剩下的给
primary」（:389-401）。

选区（:490-761，约 270 行）：一旦接管鼠标，终端自己的选中复制就没了，
得自己实现：锚点/焦点、跨行、按 grapheme 边界吸附、拖到边缘自动滚（50ms 定时器）、
`\x1b]52` OSC 52 写系统剪贴板、还要处理「选区起点在滚动区里」时的坐标换算。

超链接：`getOsc8LinkAtColumn` 从合成后的屏幕行取 OSC 8 元数据；
点了不拖才算点击、拖过就当选区。

图片：Kitty 协议要跟踪已上传的 image id、滚动出视口要删占位、iTerm2 协议在 alt 下
直接退回文本（:180-184）。（pai 不做图片，但这解释了为什么 `doRender` 里到处是
`isImageLine(line)` 的分支。）

差量重绘（`doRender`,:781-844）：与 main-screen 同构——逐行比 `previousScreen`，
只重写变了的行，整块包在 `\x1b[?2026h/l` 同步输出里。
但多了两条 alt 特有的：尺寸一变就 `fullRedraw`（:799），
以及画完之后把光标摆回 `cursorPos` 或藏起来。

## 五、pai 可以照抄 / 必须重想 / 直接不要

| pi 的做法 | pai | 理由 |
|---|---|---|
| alt 与 main 两个渲染器并存，能力用 `isViewportTUI()` 判 | 照抄形状 | pai 已经有「非 tty 走老 REPL」的双路径，再加一条要想清楚（12 复盘质疑四那笔账会加重） |
| `ScrollView` 的 follow-end 状态机 | 照抄 | 「流式输出时用户在往回翻」没有第二种解法 |
| `scrollBy` 返回剩余 delta 做滚动链 | 不要（先） | pai 只有一个滚动区，链式冒泡是为侧边栏准备的 |
| `VStack/HStack` 全套 flex 分配 | 裁到最小 | pai 的布局是「上面滚动区 + 下面 dock」，一个 `grow=1` + 一个 `basis=auto` 就够，不需要 HStack |
| 每帧重建布局树、组件树长命 | 照抄 | 与 pai 现有的 `render(width)->list[str]` 纯函数契约相容 |
| 裁剪时保住 `CURSOR_MARKER` 所在行 | 照抄 | pai 已有 CURSOR_MARKER，IME 靠它 |
| 退出时重渲染完整文档打回主屏 | 必须做 | 否则退出后终端里空空如也，是相对今天的可见倒退 |
| 自己实现选区 + OSC 52 复制 | 重想 | 270 行且全是边界情况；不做的话用户失去终端原生选中复制——这是取舍不是遗漏，要摆到台面上 |
| 老式 X10 鼠标编码兼容 | 不要 | 只支持 SGR 1006，不认就不开鼠标 |
| Kitty 图像 / 超链接 / 滚动条瞬态显示 | 不要 | 阶段范围外 |

## 六、一条范围提醒

`tui-plan.md` 是实现交接文档，不是已实现的描述——但 pi 仓库里
`layout.ts` / `scroll-view.ts` / `layout-node.ts` 都已存在，说明它落地了。
本篇引用的行为以源码为准，引用 `tui-plan.md` 的地方都是它作为「设计意图」的部分。
