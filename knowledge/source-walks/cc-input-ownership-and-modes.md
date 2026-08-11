# CC 的输入归属与模式切换：对话框不抢焦点，它等你停手

- 来源：CC 反编译源码（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）——
  `src/screens/REPL.tsx`（`getFocusedInputDialog` / `isPromptInputActive`）、
  `src/components/PromptInput/PromptInput.tsx`、`src/utils/permissions/getNextPermissionMode.ts`、
  `src/keybindings/defaultBindings.ts`、`src/ink/ink.tsx`（`handleResize`）、
  `src/ink/hooks/use-input.ts`、`src/main.tsx`（符号名检索，反编译行号会漂）
- 精读日期：2026-08-11
- pai 锚点：`src/pai/modes/interactive.py`、`src/pai/core/tools/ask.py`、
  `src/pai/core/permissions.py`、roadmap 阶段 2 后半程、features/12-20260811-tui
- 相关：[pi-tui-main-screen.md](pi-tui-main-screen.md)（绘制侧）、
  [../claude-docs/interactive-mode.md](../claude-docs/interactive-mode.md)（官方交互契约）

**为什么读这篇**：pai 有两条「留 TUI 阶段」的欠账都在这里落地——
**模态输入**（asker 与 REPL 抢同一个输入流）与 **`/mode` + shift+tab 模式切换**。

---

## 一、决定性发现：CC 的对话框**不抢焦点**，它在用户打字时把自己藏起来

pai 的 TODO 里写着（feature 08 遗留，根因记录）：

> 真正的解法在 TUI 阶段：模态输入——**问题框接管输入焦点**、Esc 取消
> （CC 的 AskUserQuestion 就是这么做的）

**源码里的机制与这句话方向相反。** `REPL.tsx` 的 `getFocusedInputDialog()`
决定「此刻哪个对话框拥有输入」，第三条判断就是：

```ts
// High priority dialogs (always show regardless of typing)
if (isMessageSelectorVisible) return 'message-selector';

// Suppress interrupt dialogs while user is actively typing
if (isPromptInputActive) return undefined;          // ← 用户在打字 → 谁都别弹
if (sandboxPermissionRequestQueue[0]) return 'sandbox-permission';
const allowDialogsWithAnimation = !toolJSX || toolJSX.shouldContinueAnimation;
if (allowDialogsWithAnimation && toolUseConfirmQueue[0]) return 'tool-permission';
...
```

`isPromptInputActive` 的定义极其朴素（`REPL.tsx`）：

```ts
setIsPromptInputActive(value.trim().length > 0);       // 输入框非空 = 正在打字
// 停手 1500ms 后解除
const timer = setTimeout(setIsPromptInputActive, PROMPT_SUPPRESSION_MS /* 1500 */, false);
```

所以完整语义是：

| 状态 | 谁拥有输入 |
|---|---|
| 输入框有内容（且距最后一次按键 < 1500ms） | **用户**。权限框、AskUserQuestion、成本框、各类 callout **全部不弹** |
| 输入框空 / 停手满 1500ms | 队首对话框接管 |
| 用户主动打开的选择器（message-selector） | 永远优先，连「正在打字」都压不住 |

**而且不静默**：被压住时 `hasSuppressedDialogs` 为真，输入框下方直接显示一行
`Waiting for permission…`（`PromptInput.tsx`）——用户知道有东西在排队，
只是没打断自己。

> **对 pai 的意义**：pai 现在的病是「asker 与主循环共用一个阻塞 reader，谁先
> `read()` 谁拿到」，实际发生过 `!echo 我是命令` 被当成对问题的回答。
> CC 的答案不是「问题框把输入抢过去」，而是**输入的归属由一个显式的、
> 单一的仲裁函数算出来**（`getFocusedInputDialog`），且仲裁**偏袒正在打字的人**。
> 这条修正了 TODO 里凭官方文档推出的判断——**升格价值高，值得进 decisions 复议**。

## 二、模式轮转：`plan` 在环里，`dontAsk` 不在

`getNextPermissionMode.ts` 是纯函数，一个 switch：

```
default  → acceptEdits
acceptEdits → plan
plan → bypassPermissions（可用时）→ 否则 default
bypassPermissions → default
dontAsk → default        // 注释：Not exposed in UI cycle yet
```

三条对 pai 直接有用：

1. **`bypassPermissions` 只在「可用」时进环**（`isBypassPermissionsModeAvailable`），
   不可用就跳过。危险档不是白给的。
2. **`dontAsk` 存在但不在轮转里**，注释明写「尚未暴露在 UI 环里」。
   pai 的四态是 `default`/`acceptEdits`/`dontAsk`/`bypassPermissions`（D#53），
   其中 `dontAsk` 与「无真人」合流——**它天然就不该出现在给真人按的快捷键环里**，
   CC 的取舍与 pai 的语义正好对上。于是 pai 的环最短可以是
   `default → acceptEdits → bypassPermissions(可用时) → default`。
3. 切换不是改一个字段，而是走 `transitionPermissionMode(from, to, ctx)`——
   有些目标模式需要**清理上下文**（例如进 auto 前剥掉危险权限）。
   pai 现在没有这类清理需求，但接口该留出位置。

## 三、`shift+tab` 本身不是可靠按键

`defaultBindings.ts`：

```ts
// Modifier-only chords (like shift+tab) may fail on Windows Terminal without VT mode
const MODE_CYCLE_KEY = SUPPORTS_TERMINAL_VT_MODE ? 'shift+tab' : 'meta+m';
```

`SUPPORTS_TERMINAL_VT_MODE` 判的是平台与 Node/Bun 版本（Node 24.2+/22.17+ 才在
Windows 开 VT mode）。pai 目标平台是 macOS/Linux，这条**不影响实现**，
但它说明一件事：**模式切换必须同时有一条不依赖组合键的路径**——CC 的那条就是
`/permissions` 与命令，pai 对应的是待做的 `/mode`。
所以 `/mode` 命令与 shift+tab **不是二选一，是必须都有**。

另外 `ctrl+c` / `ctrl+d` 在 CC 里走**基于时间的双击**处理，且写死在
`reservedShortcuts.ts` 里**不允许用户重绑**。pai 的两级 Ctrl+C 语义与之同源。

## 四、焦点的实现原语：`useInput(handler, { isActive })`

`src/ink/hooks/use-input.ts` 的 `isActive` 为 false 时**既不注册监听也不进 raw mode**。
CC 的所有对话框、滚动处理器、快捷键处理器都靠传 `isActive={...}` 来开关自己
（`REPL.tsx` 里满屏的 `isActive={screen === 'transcript' && ...}`）。

> **对 pai 的意义**：这是「一个输入源、多个消费者」的通用解法——
> **不是让消费者去抢，而是给每个消费者一个开关，由一处仲裁统一置位**。
> pai 用不着 React，但「仲裁函数 + 每个消费者带 `is_active`」这个形状可以照搬。

## 五、resize：不去抖，同尺寸事件直接丢

`ink.tsx` 的 `handleResize` 顶着一段很长的注释，结论有两条：

- **刻意不做 debounce**。去抖会开一个窗口：`stdout.columns` 已是新值而内部
  记录还是旧值，这期间任何一次渲染（spinner、时钟）都会被判成宽度变化 → 清屏，
  然后去抖到期再清一次 → **两次「空白→重画」的闪烁**。
- **终端一次用户操作常发 2 次以上 resize 事件**（窗口沉降），
  所以新旧尺寸相等就直接 `return`，避免冗余重置与渲染。

同一件事在 pi 那边的表现是「宽度一变就全量重绘」（见
[pi-tui-main-screen.md](pi-tui-main-screen.md) 第四节）。两家都把 resize
当成**必须立刻同步处理的强事件**，而不是可以攒一攒的通知。

## 六、非交互判定：`-p` 或 **stdout 不是 tty**

`main.tsx`：

```ts
const isNonInteractive = hasPrintFlag || hasInitOnlyFlag || hasSdkUrl || !process.stdout.isTTY;
```

判的是 **stdout**（能不能画），不是 stdin。stdin 另有一条：非 tty 时
把整个 stdin 读成 prompt（带 3 秒无数据的超时告警）。
另外 Ink 在**非 TTY 输出下会打完整帧而不是 diff**——CC 反过来利用了这一点，
`utils/staticRender.tsx` 把组件渲染进一个 `PassThrough` 流再抠出第一帧，
用来把内容「打印」进 scrollback（因为 Ink 不支持同一棵树里有多个 `<Static>`）。

> **对 pai 的意义**：pai 现在 `StatusLinePrinter` 判的是 `stream.isatty()`（对），
> 而 `_is_real_terminal_input` 判的是 `sys.stdin.isatty()`（也对，它管的是 readline）。
> TUI 化后要多一条**总开关**：**stdout 不是 tty 就整个不进 TUI**，
> 与 CC 同口径。实测 pai 现在在管道下仍会打欢迎语与 `› ` 提示符
> （见 features/12 evidence），那是给脚本用时的噪音。

## 七、pai 能直接拿走的四条

1. **一个仲裁函数决定输入归属**，消费者只有 `is_active` 开关——替掉「两个 reader 抢 read()」。
2. **偏袒正在打字的人**：有未处理的提问/权限请求时，若用户正在输入就先压住，
   并**显式提示**「有 N 个请求在等」，停手一小会儿再弹。
3. **`/mode` 与快捷键都要有**，且 `dontAsk` 不进快捷键轮转环。
4. **resize 同步处理、同尺寸事件丢弃**，不要去抖。

## 外部参照

见 [knowledge/README.md 的「外部参照」节](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)。
