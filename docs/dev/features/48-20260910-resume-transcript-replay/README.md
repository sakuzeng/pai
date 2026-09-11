# 48-resume-transcript-replay
状态：已交付
分支：`feat/48-resume-transcript-replay`（从 `main` 切出；两个新模块、四处小改、测试与文档全部在这一条）
流程：中等改动直做（无 spec/plan）：单功能增强，改动面是 TUI 装配一处 + 一个纯函数模块，取舍点已列成四问在本档案拍板，返工成本低。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

出处：[需求池 2026-09-10](../../需求池.md)，用户原话「我使用resume并不能恢复对话状态」，
随后问「怎么来解决这个需求呢」。改的是 feature 24 交付的结果（`--resume` 只恢复了模型侧），
按规矩 7 新建档案并链回 [features/24](../24-20260822-session-format-and-resume/README.md)，24 冻结。

一句话：`pai --resume` 起来之后，人要看得出对话被恢复了。具体三件事：

1. 旧对话上屏：TUI 的 transcript 里能看到恢复的用户话、模型回答与工具调用，形态与活轮次一致。
2. 恢复提示可见：「↩️ 已恢复会话 …」在 TUI 里上屏，不再被备用屏盖掉。
3. 提示语说真话：「system prompt 都按当前环境重新装配」目前不属实（`run_agent` 只在
   `messages` 为空时造 system 条目，`_inject_instructions` 见旧指令消息就跳过），
   要么真的重装配，要么改口。

排查结论（2026-09-10，只查不改）见需求池同日条目；要点：模型侧是通的（e2e
`test_resume_carries_the_conversation_into_a_new_process` 断言 provider 收到历史），
屏幕侧 `_run_tui` 的 `Transcript()` 从空建起、无人遍历 `messages` 上屏，
提示走 `print` 在 `ENTER_ALT_SCREEN`（自带 `2J`）之前打出即被盖掉。
用户机器上 13:39 那次恢复后一个字没敲就退了，像是看到空屏以为没恢复。

验收标准（怎么算做完；中等改动通道没有 plan，验收项按 features/README 规矩 9 的教训写在这里）：

- e2e：`test_resume_carries_the_conversation_into_a_new_process` 加 `screen_text()` 断言——
  第二个进程起来后，屏幕上有第一段的用户话与模型回答、有「已恢复会话」；不再只查 `s2.raw`。
- 注入反证：把回放调用去掉，上面那条 e2e 必须红（features/README 规矩 9 附带教训：15 的 2/3 假绿）。
- 单测：回放渲染是纯函数，至少一条测试拿真实会话轨迹当输入（AGENTS「测试」节）——
  复制 `~/.pai/projects/…/sessions/20260910-133120-becd50cd.jsonl`（37 条，含并发工具批、
  规则注入、指令消息）进版本库、剥 `ts`；断言：用户行数、答案条目数、工具行折叠形态、
  注入消息不当用户话上屏、system 不上屏。
- 单测：问 3 选 A 则断言 resume 后 `messages[0]` 是当前 `build_system_prompt` 的产物且指令
  消息重读了磁盘；选 B 则断言提示语的新措辞。
- `./test.sh` 全绿，数字贴 devlog。

非目标：

- 纯 REPL 路径（管道 / CI / `pai | cat`）不回放历史，只打提示（问 4 若选 A）。
- `--resume` 与任务参数组合（once 续跑）、会话选择器、树操作——全是 24 遗留，与本需求无关。
- 不改会话格式 v1；不动 `build_messages` / `trim_unfinished`。

## 候选方案与确认

### 方案 A · 回放上屏（复用活轮次的渲染）

- 新增 `src/pai/tui/history.py`：纯函数 `entries_from_messages(messages, *, color, markdown)
  -> List[TranscriptEntry]`，逐条映射：
  - `user`（非注入）→ 用户色带条目。把 `TuiApp._submitted` 里那段渲染抽成模块级
    `user_entry(text, color)`，两处共用——回放的用户行与活轮次长得一样。
  - `assistant` 有 `content` → `_answer_entry` 提成模块级 `answer_entry(text, color, markdown)`。
  - `assistant` 有 `tool_calls` → 每条 tool_call 找配对的 `tool` 消息，合成
    `ToolEnd(tool_call_id, name, args=json.loads(arguments), result)` 喂现有 `_tool_entry`
    （折叠一行 + 可展开）。`is_error` 只能给 False：`tool` 消息里分不出 loop 造的错，
    诚实边界同 `events.ToolEnd` 注释。`arguments` 解析失败退化为 `{"raw": …}`。
  - `system` 不上屏；注入消息按问 2 处理。
- `TuiApp.replay(entries)`：只 `transcript.append`，不过 `dock.handle`（dock 是本进程的活动
  计数，回放不该动它）；工具条目同时登记进 `_collapsed`，`^O` 能展开到它们。
- `_run_tui` 收 `resumed_messages` 与 `resume_note`：app 建好后先回放，再 `commit` 恢复提示。
  `run_interactive` 里那句 `out(resume_note)` 移到 TUI / REPL 分叉之后：TUI 走 `commit`，
  REPL 照旧 `out`。
- 若问 3 选 A：`run_interactive` 里把「按原 id 重录进新文件」那段移到装配之后，先换
  `messages[0]` 为当前 `build_system_prompt(...)`、`drop_instructions` 掉旧指令消息，再重录。
  换掉的两条按新 id 重录（内容变了就是新条目；只多两条，不是 CC 反教材里的指数增长）。
- 改动面估算：`tui/history.py` 约 80 行、`tui/app.py` 抽两个函数 + 一个方法、
  `modes/interactive.py` 约 20 行、测试约 120 行。

取舍：完整满足「打开就能看到之前聊了什么」，pi/CC 都是这个形态；代价是 `app.py`
的两段渲染要提成共享函数（小重构），且历史长时 transcript 一上来就满——备用屏可滚且跟随末尾，
用户落在最新处，可接受。

### 方案 B · 只搬提示，不回放

- 恢复提示走 `commit` 上屏，措辞改为「历史已加载给模型，屏幕不回放；`/status` 看条数」。
- 改动约 10 行，零新模块。

取舍：最小改动，但用户的直观诉求没满足——屏幕仍是空的，只是多了一行解释。
等于把「看起来没恢复」改成「告诉你其实恢复了」。

### 方案 C · 回放但折叠成一条

- 整段历史做成一个可展开条目「↩️ 已恢复 N 条消息（^O 展开）」，展开后才铺开。

取舍：屏幕干净；但可展开条目是「一个渲染函数两个态」，几十条消息塞进一个条目就失去
逐条点击展开工具输出的能力，且 pi/CC 都不这么做——为省屏发明一个别处没有的形态，不值。

### 确认

拍板（2026-09-11）：用户原话「cc是怎么做的呢，按cc的来吧」。于是四问都按 CC 2.1.88
反编译源码（证据等级：反编译，行号会漂，下面全按符号名引用；本机 checkout 见
knowledge/README「外部参照 6」）的做法定，逐条如下。走读笔记
[knowledge/tui/cc-resume-rendering.md](../../../../knowledge/tui/cc-resume-rendering.md)。

问 1：上屏形态选哪个？
- 候选 A·回放上屏：复用活轮次渲染，形态一致，改动面中等。
- 候选 B·只搬提示：约 10 行，屏幕仍空。
- 候选 C·折叠成一条：屏幕干净，失去逐条展开，三家孤例。
选择：A。理由（CC 源码）：`screens/ResumeConversation.tsx` 调 `loadConversationForResume()`
后渲染 `<REPL initialMessages={resumeData.messages}>`；`screens/REPL.tsx` 用
`useState(initialMessages ?? [])` 把它们直接当成 `messages` 状态，活轮次与恢复的消息走
同一个 `<Messages>` 组件——CC 根本没有「回放」这条独立路径，恢复 = 把数组喂给同一个渲染器。
加载期间只有一个转圈的「Resuming conversation…」（`ResumeConversation.tsx`），没有常驻横幅。

问 2（A/C 才需答）：注入消息回放时怎么处理？
- 候选 A·全部不上屏，两处例外各显示一行标记。
- 候选 B·一律做成可展开条目。
选择：A，细节按 CC 修订。理由（CC 源码）：`utils/messages.ts::shouldShowUserMessage` 对
`isMeta` 的 user 消息返回 false——system-reminder、注入上下文、恢复时合成的
「Continue from where you left off.」全是 isMeta，一律不画；`components/Messages.tsx`
再滤掉 `progress` 与 null 渲染的 attachment。`!命令`：`UserBashInputMessage` 画
`! <input>` 一行，`UserBashOutputMessage` 走 `BashToolResultMessage`，非 verbose 时折叠
——所以 pai 这里与候选 A 原文「只显示命令行」不同：命令行 + 输出折叠一行可展开。
压缩：主屏只显示最后一个压缩边界之后的消息（`getMessagesAfterCompactBoundary`），边界画成
`CompactBoundaryMessage` 一行「✻ Conversation compacted (ctrl+o for history)」，摘要正文只在
transcript 模式（ctrl+o）才出现。pai 的 `build_messages` 输出恰好就是「边界之后」那段
（摘要 + 保留段 + 其后全部），照 CC 主屏形态：摘要位置画一行标记，正文不回放。

问 3：system prompt 与项目指令在 resume 时怎么办？
- 候选 A·真的重装配。
- 候选 B·改口。
选择：A。理由（CC 源码）：CC 的转录里根本不存 system prompt（`utils/sessionStorage.ts`
无 systemPrompt 字样），`screens/REPL.tsx` 每次 query 都现算：`getSystemPrompt(tools, model,
additionalWorkingDirectories, mcpClients)` + `getUserContext()`（CLAUDE.md）+
`getSystemContext()` → `buildEffectiveSystemPrompt`。恢复的只有消息数组；权限模式与模型也
不恢复（`utils/sessionRestore.ts` 恢复的是 cost state / 文件历史快照 / agent 设置 / worktree /
会话元数据，没有 permissionMode 与 model）——与 pai 24 的「设置取当前环境」同向，
system prompt 归到同一类才自洽。pai 的差别是 system 消息落在 JSONL 里，所以要在 resume 后
把 `messages[0]` 换成当前装配结果、丢掉旧指令消息让 `_inject_instructions` 重读磁盘。

问 4：纯 REPL 路径（非 tty / 管道）要不要也回放？
- 候选 A·不回放，只打提示。
- 候选 B·纯文本逐条打。
选择：A。理由（CC 源码）：`cli/print.ts` 给 `-p -c` 加载 `initialMessages` 后无头运行，
没有任何渲染。写进非目标。

保留的 pai 差异（照 CC 之后仍与它不同的三处，如实记）：
- 「↩️ 已恢复会话 …」提示保留（feature 35 拍板的设置警告有用），只是改成回放完历史后
  `commit` 进 transcript；CC 没有这条常驻提示。
- pai 把历史按原 id 重录进新文件（feature 24，parentSession 指旧会话）；CC 沿用原 session id
  往同一个文件追加（`useLogMessages(messages, ignore = messages.length === initialMessages?.length)`
  + `switchSession`）。本轮不动，24 遗留那条「文件数 × 全量」的账仍在 TODO。
- CC 恢复时若转录以 user 消息结尾，会补一条合成的 assistant 哨兵（`NO_RESPONSE_REQUESTED`）；
  轮次中途被打断则补一条 isMeta 的「Continue from where you left off.」。pai 的 `trim_unfinished`
  只删半截工具回合，不补哨兵——OpenAI 兼容协议连续两条 user 合法，不是 bug，登记 TODO 待议。

## 结果与总结

交付（2026-09-11）：`pai --resume` 起来后，logo 与提示行之后铺开旧对话（用户行 / 答案 /
工具折叠行，可 ^O 展开），末尾一行恢复提示；system prompt 与项目指令按当前环境重装配。

- 新增 `src/pai/modes/resume.py`（`history_items`，消息 → 回放项）、`src/pai/tui/history.py`
  （回放项类型 + `user_entry` / `compacted_entry`）；`TuiApp.replay`；`interactive._refresh_assembly`；
  `commands.shell_echo` / `split_shell_echo`；`session.SUMMARY_HEADER`；`theme.COMPACTED`。
- 测试：`tests/test_resume_replay.py` 9 条（真实轨迹 `tests/fixtures/resume_session.jsonl`——
  就是用户那次「看起来没恢复」的原始会话）；e2e 改查 `screen_text()`；两处注入反证各红。
- 数字：新增/相关 `48 passed`，e2e `1 passed in 6.58s`，全量 `1704 passed`
  （STATUS 更新前一跑 `1 failed, 1703 passed, 8 deselected in 184.52s`，红的是测试数校验）。

意外收获：真实会话里零最终回答——整段是一次 run，第二问是 steering 注入，run 被用量预算掐断。
用户当时看到的空屏后面，模型侧其实也没答完过。

详细日志见 [devlog.md](devlog.md)，复盘见 [复盘.md](复盘.md)，取舍升格为 [D#79](../../decisions.md)。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处，否则等于没记 -->

- `!命令` 活轮次全量上屏、回放折叠一行，两条路形态不一致——活轮次也该折叠（照 CC）。
- resume 尾部哨兵没抄（CC：以 user 结尾补合成 assistant；中途打断补「Continue from where you left off.」）。
- 压缩摘要正文在 pai 里无处可看（CC 有 transcript 模式，pai 无对应物）。
- 回放历史与本次对话之间没有开头分隔，只有末尾的恢复提示。
- 真实轨迹夹具 131KB，是仓库里最大的测试文件。

## 用到的知识

- K [loop/session-format-three-way.md](../../../../knowledge/loop/session-format-three-way.md)（resume 配平与「不造新身份」的出处；问 3 选 A 时「换掉的条目按新 id 重录」要对着它的第二节核一遍）。
- K [loop/cc-prompt-and-transcript.md](../../../../knowledge/loop/cc-prompt-and-transcript.md)（CC 的 transcript 回放形态）。
- K [tui/alt-screen-and-mouse.md](../../../../knowledge/tui/alt-screen-and-mouse.md)（备用屏 `2J` 会盖掉进屏前的输出，本需求症状二的机制）。
