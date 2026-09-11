# CC 的 resume：没有「回放」这条路——一份消息数组，一个渲染器

- 来源：CC 反编译源码 v2.1.88（[外部参照 6](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)），
  文件清单见下方「读了哪些文件」（反编译源码行号会漂，按符号名检索）
- 精读日期：2026-09-11
- pai 锚点：`src/pai/modes/resume.py`、`src/pai/tui/history.py`、`TuiApp.replay`，
  docs/dev/features/48-20260910-resume-transcript-replay、docs/dev/decisions.md #79

读了哪些文件：`src/screens/ResumeConversation.tsx`、`src/screens/REPL.tsx`（看 `initialMessages` /
`useLogMessages`）、`src/utils/conversationRecovery.ts`（`loadConversationForResume` /
`deserializeMessagesWithInterruptDetection`）、`src/utils/sessionRestore.ts`、
`src/utils/messages.ts`（`shouldShowUserMessage` / `getMessagesAfterCompactBoundary` /
`isNotEmptyMessage`）、`src/components/Messages.tsx`、`src/components/Message.tsx`、
`src/components/CompactSummary.tsx`、`src/components/messages/CompactBoundaryMessage.tsx`、
`src/components/messages/UserBashInputMessage.tsx`、`src/cli/print.ts`。

为什么读这篇：用户报「`--resume` 并不能恢复对话状态」，排查发现 pai 只恢复了模型侧、
屏幕侧从没画过；用户拍板「按 CC 的来」，于是要弄清 CC 恢复一个会话时到底画什么、
不画什么、从哪里拿 system prompt。

## 一、恢复的形状：把数组交给同一个渲染器

`ResumeConversation.tsx` 选中一条日志后调 `loadConversationForResume(log)`，拿到
`messages` 就渲染 `<REPL initialMessages={resumeData.messages} …>`。`REPL.tsx` 里
`useState<MessageType[]>(initialMessages ?? [])` 把它们直接当成 `messages` 状态，
之后与活轮次追加的消息一起交给同一个 `<Messages messages={displayedMessages} …>`。

也就是说 CC 没有「回放历史」这个动作。恢复之后屏幕上有什么，完全由「这份数组
经过 `<Messages>` 会画成什么」决定——与活轮次逐条一致，因为就是同一段代码。
加载期间只有一个转圈的「Resuming conversation…」，没有常驻横幅；
终端标题也不为恢复的会话重新生成（`haikuTitleAttemptedRef` 在有 initialMessages 时直接置真）。

pai 视角：pai 的 transcript 是 append-only 的条目表（`tui/transcript.py`），不是从 messages
派生的视图，所以「同一个渲染器」在 pai 里必须写成一个显式的 `TuiApp.replay(items)`，
逐项复用 `_submitted` / `_flush_answer` / `on_event(ToolEnd)` 用的那几个函数。
形状抄到了，机制抄不了——这是 React 派生式 UI 与日志式 UI 的结构差别。

## 二、什么不画

`utils/messages.ts::shouldShowUserMessage(message, isTranscriptMode)`：
非 user 消息一律画；`isMeta` 的 user 消息不画（唯一例外是 channel 来源，feature flag 后面）；
`isVisibleInTranscriptOnly` 的只在 transcript 模式画。system-reminder、注入的上下文、
恢复时合成的「Continue from where you left off.」都是 isMeta。

`Messages.tsx` 再过三道：`normalizeMessages(...).filter(isNotEmptyMessage)`（空文本、
`NO_CONTENT_MESSAGE`、`INTERRUPT_MESSAGE_FOR_TOOL_USE` 不画）、滤掉 `progress` 类型、
滤掉 `isNullRenderingAttachment` 的 attachment。`Message.tsx` 里 thinking / redacted_thinking
只在 verbose 或 transcript 模式画。

压缩：主屏（非 verbose、非全屏）只画最后一个压缩边界之后的消息
（`getMessagesAfterCompactBoundary`），边界本身是 `CompactBoundaryMessage` 一行
「✻ Conversation compacted (ctrl+o for history)」；摘要那条 user 消息由 `CompactSummary`
画成「● Summarized conversation / Summarized N messages up to this point / (ctrl+o to expand
history)」，摘要正文只在 transcript 模式（ctrl+o）出现。

`!` 命令：用户消息带 `<bash-input>` / `<bash-stdout>` 标签，`UserBashInputMessage` 画
`! <input>`，`UserBashOutputMessage` 走 `BashToolResultMessage`，非 verbose 时折叠。

pai 视角：pai 的消息没有 isMeta 字段，注入消息只能靠各自的固定头认（指令头、
`<system-reminder>`、摘要头、`!` 回显）。这四个头都是 pai 自己造的，所以分类函数
`history_items` 住 modes 层。pai 没有 transcript 模式，摘要正文于是无处可看（TODO）。

## 三、system prompt 不在转录里

`utils/sessionStorage.ts` 里没有 systemPrompt 字样；`REPL.tsx` 每次 query 现算：
`getSystemPrompt(tools, model, additionalWorkingDirectories, mcpClients)` +
`getUserContext()`（CLAUDE.md 那些）+ `getSystemContext()`，经 `buildEffectiveSystemPrompt`
合成。恢复的只有消息数组。`sessionRestore.ts` 恢复的是 cost state、文件历史快照、
agent 设置、worktree、会话元数据（名字 / PR 关联）；没有 permissionMode，没有 model。

pai 视角：pai 的 system 消息落在 JSONL 里（feature 24），所以 resume 之后要显式换掉
`messages[0]` 并丢掉旧指令消息（`_refresh_assembly`）。24 遗留写的「权限模式 / 模型 /
system prompt 都取当前环境」与 CC 同向——但其中 system prompt 那半句此前只是提示语，
代码没做，13 天没人发现：断言文案存在的测试证明不了文案是真的。

## 四、恢复侧的配平与哨兵

`deserializeMessagesWithInterruptDetection`：迁移旧 attachment 类型 → 清掉非法的
`permissionMode` 字段 → `filterUnresolvedToolUses`（半截工具回合）→
`filterOrphanedThinkingOnlyMessages` → `filterWhitespaceOnlyAssistantMessages`（模型在
thinking 前吐的 "\n\n" 被用户取消留下的）→ `detectTurnInterruption`。
轮次中途被打断：追加一条 isMeta 的 user「Continue from where you left off.」。
过滤后最后一条是 user：在它后面插一条合成 assistant（`NO_RESPONSE_REQUESTED`），
让对话在用户什么都不做时也是 API 合法的。最后跑 `processSessionStartHooks('resume')`
把 hook 消息追加进去。

pai 视角：`trim_unfinished` 对应第一道过滤（feature 24 已抄）；空白 assistant 不画这条
在 pai 回放层做了；两种哨兵没抄（OpenAI 兼容协议连续两条 user 合法），登记 TODO。

## 五、不重录，沿用 session id

`useLogMessages(messages, ignore = messages.length === initialMessages?.length)`：
恢复后一条新消息都没有就什么都不写（注释原文：用户恢复后直接退出的情形）。
`switchSession(sid)` 沿用被恢复会话的 id，`adoptResumedSessionFile` 把文件指针指回原转录；
只有 `--fork-session` 才造新 id、由 `recordTranscript` 把源消息复制进新文件。

pai 视角：feature 24 选的是新文件 + parentSession + 按原 id 重录（当时的理由是自包含、
单文件永远够用）。与 CC 的差异保留，「文件数 × 全量」的账仍在 TODO。

## 六、print 模式

`cli/print.ts` 给 `-p -c` / `-p -r` 加载 `initialMessages` 后无头运行，没有任何渲染。
pai 的纯 REPL（非 tty）路径照此只打恢复提示、不回放。
