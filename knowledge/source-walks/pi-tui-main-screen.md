# pi 的 TUI 走读：main-screen 模式下「差量重绘」到底在差量什么

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `packages/tui/src/tui.ts`(1223)、`packages/tui/src/tui-main-screen.ts`(552)、
  根目录 `tui-plan.md`(1001)、`packages/coding-agent/src/core/settings-manager.ts`、
  `packages/coding-agent/src/modes/interactive/interactive-mode.ts`
- 精读日期：2026-08-11
- pai 锚点：`src/pai/modes/interactive.py`、`src/pai/modes/statusline.py`、
  roadmap 阶段 2 后半程、docs/dev/features/12-20260811-tui

**为什么读这篇**：roadmap 阶段 2 把四条 TUI 设计原则「现在拍板，实现时不再议」，
其中三条点名引用了这两个文件。动工前要确认的不是「原则对不对」，
而是**原则背后的机制到底是什么、pai 抄哪部分**。

---

## 〇、先纠一个范围错误：`tui-plan.md` 讲的是 pai 明确不做的那一半

roadmap 写着「pi-mono 根目录 `tui-plan.md`（36KB 设计文档，动工前通读）」，
读完发现它的标题是 **`Alternate-Screen Layout System Plan`**——
1001 行里约 90% 在设计 alt-screen 的**约束式布局系统**（VStack/HStack/ScrollView、
布局树、命中测试、滚轮路由、Kitty 图像、选区与超链接）。
而 pai 的设计原则 2 明写「只做 main-screen 模式，不做 alt-screen」。

对 pai 真正有用的只有三处，加起来不到 60 行：

1. **第 26-36 行「Why main-screen and alternate-screen layouts differ」**——
   这正是原则 2 的出处，值得逐字看（下节抄结论）。
2. **第 423 行**：裁剪叶子组件时，若其行内含 `CURSOR_MARKER`，
   要**挑一个包含该标记的可见行窗口**——即「焦点光标不能因为裁剪而消失」。
3. **第 839-941 行的测试计划**：可迁移的是测试项清单的**形状**
   （resize 重算、光标行在何处、终端过小时先保谁），不是 alt-screen 的具体断言。

**这条本身就是教训**：roadmap 的「动工前通读」把一份 36KB 文档整体记成了前置，
没人核对过它覆盖的是哪一半。**前置精读清单该记到「哪一节」而不是「哪个文件」。**

## 一、原则 2 的原文理由：终端拥有滚动权，所以有五件事应用程序做不到

`tui-plan.md:28-36` 列的是能力清单而非偏好：main-screen 模式下终端拥有滚动，
应用**无法可靠提供**——

- sticky（固定不动）行
- 可独立滚动的嵌套区域
- 满高的左右分栏
- 对已滚进 scrollback 的内容做可靠的鼠标命中测试
- 不重放、不清屏就重绘屏幕外区域

结论句是命令式的：**「Therefore, do not pretend the same constrained viewport
semantics exist in `TuiMainScreen`.」** main-screen 交互模式就是一份
**垂直排下来的文档**（header / 资源 / 对话 / 待发消息 / 状态 / 组件 / 编辑器 / footer），
谁在上谁在下由 `addChild` 顺序决定，没有「贴底」这回事。

> pai 锚点：这条直接支撑 roadmap 原则 2。**但要注意 pi 的 main-screen 仍然每帧
> 渲染整份文档**（见第三节），与 pai 现在的 print-and-forget 不是一回事——
> 原则 2 说的是「不假装 sticky」，不是「可以只管最后一行」。

## 二、`Component` 契约是四件事，不是一件

roadmap 原则 1 只写了 `render(width) -> list[str]`。源码里（`tui.ts:23-47`）接口有四个成员：

```ts
export interface Component {
    render(width: number): string[];        // 必需
    handleInput?(data: string): void;       // 可选：拿到焦点时收键盘输入
    wantsKeyRelease?: boolean;              // 可选：是否要 Kitty 协议的抬键事件
    invalidate(): void;                     // 必需：作废缓存的渲染状态
}
```

两条对 pai 重要的补充：

- **`invalidate()` 是必需成员**。`Container.invalidate()` 递归调用子组件的
  （`tui.ts:229-233`）。它的存在是因为组件**自己持有渲染缓存**——
  pi 明确拒绝在框架层再加一层缓存（`tui-plan.md:376`：第二层缓存会因为
  「组件自己拥有失效语义」而变陈旧）。
- **输入是「焦点组件收 `handleInput`」**，不是全局读 stdin。
  焦点由 `TUI.setFocus(component)` 指定；`Focusable` 接口只有一个字段
  `focused: boolean`，组件据此决定要不要吐 `CURSOR_MARKER`（`tui.ts:63-66`）。

> pai 锚点：pai 若照抄，`render(width)` 之外至少还要有 `invalidate()`；
> 而「一个输入流两个消费者」（asker vs REPL）在这套契约里的答案是
> **setFocus 换人**，不是两个 reader 抢 `read()`。

## 三、main-screen 的差量重绘：diff 的是**整份文档的行数组**

`tui-main-screen.ts:146-513` 的 `doRender()` 是这样一条流水线：

```
render(width) 得到 newLines（整份文档，不是增量）
  → 合成 overlay
  → extractCursorPosition(newLines, height)   ← 必须在 applyLineResets 之前
  → applyLineResets
  → 与 this.previousLines 逐行比，求 firstChanged / lastChanged
  → 用相对光标移动（CSI nA / nB）+ CSI 2K 清行，只重写 [firstChanged, lastChanged]
  → 记下 previousLines / previousWidth / previousHeight / hardwareCursorRow
```

要点：

1. **它持有整份文档**。`render(width)` 每帧把所有组件（含全部历史消息）重渲染一遍，
   差量只体现在**写出去多少字节**，不体现在算了多少东西。
   贵的部分靠组件自己的缓存扛（Markdown/Text/Image/Box 都按 `(内容, 宽度)` 缓存）。
2. **差量只能碰「上次还在视口里」的行**。`tui-main-screen.ts:348`：
   `firstChanged < prevViewportTop` 就直接全量重绘——
   已滚进 scrollback 的行，**任何转义序列都够不着**。
3. **写入包在同步输出里**：每个 buffer 首尾是 `\x1b[?2026h` / `\x1b[?2026l`
   （DEC synchronized output），终端在此期间不刷新，避免撕裂/闪烁。
4. 光标位置**先提取再重置样式**——注释明写「marker must be found first」。

## 四、宽度变化 = 全量重绘 + **清掉 scrollback**

`tui-main-screen.ts:236-249`：

```ts
if (widthChanged) { fullRender(true); return; }              // 宽度变了必然重绘
if (heightChanged && !isTermuxSession()) { fullRender(true); return; }
```

而 `fullRender(clear=true)` 写的是 `\x1b[2J\x1b[H\x1b[3J`——
清屏、回原点、**清 scrollback**（`3J`）。理由是宽度一变换行位置全变，
旧的行数组与屏幕内容不再对应。Termux 是唯一豁免：软键盘弹出/收起会改高度，
每次全量重绘等于把整段历史重放一遍。

**代价必须说清楚**：main-screen 模式号称「滚动交给终端」，
但只要用户拖一次窗口宽度，**终端 scrollback 里的历史就被 `3J` 清掉了**，
换成由应用重新画出来的当前文档。这不是 bug，是「持有整份文档」的必然配套——
应用能重画出全部内容，所以敢清。

> pai 锚点：**pai 若做不到「持有整份文档」，就绝不能抄这个 `3J`**——
> 清掉的历史 pai 画不回来。这是 TUI 方案选型里第一个硬约束。

另有两条：终端一次用户操作常发 **2 次以上** resize 事件（窗口沉降），
pi 靠比较新旧尺寸相等就直接 return 来去重；
`clearOnShrink`（内容变短时清空多余行）是可开关的，默认开。

## 五、行宽超出终端宽度 → **抛异常并写 crash log**

`tui-main-screen.ts:413-439`：差量重写每一行前检查
`visibleWidth(line) > width`，命中就把所有行 dump 进 `pi-crash.log`、
调 `this.stop()` 复原终端，然后 `throw`。错误信息直接指认凶手：
「likely caused by a custom TUI component not truncating its output.
Use `visibleWidth()` to measure and `truncateToWidth()` to truncate.」

这是**刻意选的 fail-loud**：一行超宽会被终端自动折行，之后所有基于
「一行 = 一个屏幕行」的相对光标移动全部错位，症状是满屏乱跳而非某处显示不全。
与其让它错得莫名其妙，不如当场炸掉。

> pai 锚点：pai 的 `render_tool_line` 已经自己截断（`concepts/terminal-width.md`），
> 本次实测 1..120 列 × 中文/emoji/ASCII 混合**零越界**（见 features/12 evidence）。
> 但 pai 目前**没有任何断言挡住「将来某个组件忘了截断」**——pi 这条 fail-loud
> 是便宜且高价值的仿制品。

## 六、`CURSOR_MARKER` 与 IME：位置永远要摆，可见性才是选项

```ts
export const CURSOR_MARKER = "\x1b_pi:c\x07";   // tui.ts:79
```

是 APC（Application Program Command）序列，终端会忽略它、**不占列宽**。
机制三步：

1. 拿到焦点的组件在自己的输出里、光标该在的位置吐一个 `CURSOR_MARKER`；
2. `extractCursorPosition`（`tui.ts:1149-1167`）从**最终合成后的行**里倒着找它，
   `visibleWidth(标记之前的文本)` 就是列号，然后把标记从行里剥掉；
3. `positionHardwareCursor`（`tui-main-screen.ts:520-551`）用相对行移动
   + `\x1b[{col+1}G` 把**硬件光标**摆过去。

两条容易读漏的：

- **`showHardwareCursor` 只决定光标可不可见，不决定摆不摆。**
  `positionHardwareCursor` 无条件先移动，最后才按设置决定 `showCursor()`
  还是 `hideCursor()`。`settings-manager.ts:125` 的注释说得最清楚：
  「Show terminal cursor **while still positioning it for IME**」。
  默认值是 `process.env.PI_HARDWARE_CURSOR === "1"`，即**默认不可见但照样摆位**。
- 找不到标记时 `hideCursor()`，且**只扫最底部 height 行**（视口内）。

> pai 锚点：这就是原则 3「CURSOR_MARKER 零宽标记定位硬件光标（中文 IME 候选框
> 位置正确的关键）」的完整机制。**当前 pai 不需要它**——`input()` 让光标天然
> 待在输入位置；一旦 pai 自己接管绘制并把输入框画在别处，IME 候选框就会跑到
> 上一次写字节的位置去。

## 七、渲染节流：16ms

`TuiBase.MIN_RENDER_INTERVAL_MS = 16`（`tui.ts:332`）。
`requestRender()` 只置标志位并合并到下一帧，没有独立的渲染循环——
`tui-plan.md:388` 明写「No render means no layout」。

## 八、pai 可以照抄 / 必须重想 / 直接不要

| pi 的做法 | pai | 理由 |
|---|---|---|
| `Component` 四成员契约 + `Container` 递归 | **照抄**（render + invalidate 起步） | 纯函数、离线可测，与 pai 现有 `render_tool_line` 同构 |
| `CURSOR_MARKER` + 提取 + 摆硬件光标 | **照抄**（原则 3 已拍板） | 中文 IME 的唯一正确解法 |
| 同步输出 `\x1b[?2026h/l` 包住每次写 | **照抄** | 几行，防撕裂 |
| 超宽即抛 + dump | **照抄**（改成 pai 风格的断言） | 便宜，且错位症状极难反推 |
| 每帧渲染整份文档 + 行数组 diff | **必须重想** | pai 现在是 print-and-forget；持有整份文档要连带解决内存、渲染成本、以及下一行 |
| 宽度变化 `\x1b[3J` 清 scrollback 后重画 | **必须重想** | 只有「持有整份文档」才敢清；否则清掉的历史画不回来 |
| 16ms 节流 | 视方案定 | 只在有连续动画（spinner/流式）时才有意义 |
| alt-screen 布局系统（VStack/ScrollView/命中测试/滚轮） | **不要** | 原则 2 已拍板不做 alt-screen |
| Kitty 图像、鼠标选区、超链接 | **不要** | 阶段 2 范围明确排除 |

## 外部参照

见 [knowledge/README.md 的「外部参照」节](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)。
