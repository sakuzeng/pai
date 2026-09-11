# 49-resume-same-file-and-slash-resume
状态：已交付
分支：`feat/49-resume-same-file-and-slash-resume`（2026-09-11 从 `main` 切出，此前先把 `feat/48-resume-transcript-replay` 以 no-ff 方式合回 `main` 并推送；本档案全部改动在这一条）
流程：中等改动直做（无 spec/plan）：不新开路线图模块，改的是 24 与 48 已交付结果的两处形状（落盘位置、进程内切换）；涉及 SessionLog / EventTrace / events 三处小接口，任务清单与验收项写在「需求」节。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

出处：[需求池 2026-09-11](../../需求池.md)，用户原话「我想追加同一文件呢。并且在命令/resume 下能够恢复对话呢」
（feature 48 交付回复之后——那份回复刚把「CC 沿用原 session id 往同一文件追加，pai 保持 24 的新文件」
列为刻意没做）。改的是 [features/24](../24-20260822-session-format-and-resume/README.md)
拍板的落盘形状与 [features/48](../48-20260910-resume-transcript-replay/README.md) 的启动回放，
两个旧档案冻结，本档案链回。

两件事：

1. 同一文件追加：`--resume` 不再新建文件、不再按原 id 重录历史，而是沿用被恢复会话的 id，
   往同一个文件追加（照 CC：`switchSession(sid)` + `useLogMessages(messages, ignore)`——
   恢复后一条新消息都没有就什么都不写）。
2. 会话内 `/resume`：不退出 pai 就切到另一个会话接着聊（照 CC 的 `/resume` 命令：无参弹
   选择器、带参直达）。切换 = 换消息 + 换落盘目标 + 重置跨轮状态 + 屏幕换成那段对话。

验收标准（怎么算做完）：

- e2e：两个真进程接力（现有 `test_resume_carries_the_conversation_into_a_new_process`）改断言——
  第二个进程退出后 sessions 目录只有一个会话 `.jsonl`（不含 `.events.jsonl`），header 的 id 不变，
  新消息追加在末尾，原消息一条不重复；退出提示「会话已存 …」指的是同一个文件。
- 单测：`SessionLog` 能接管既有文件——取 header 的 id / cwd、不再写 header、`_last_id` 是物理尾部
  最后一条（dsh：「内存配平中断轮次，物理尾部保持撕裂原样」）；v0 / 更新版本按既有语义报错。
- 单测：恢复后一个字没敲就退出 → 文件字节不变（CC `useLogMessages` 的 ignore 语义；也是用户
  2026-09-10 13:39 那次的真实场景）。
- 单测：resume 后重装配的 system 不落盘（CC 转录里不存 system prompt，下次 resume 反正重算）；
  指令消息内容与磁盘最新一条相同则不重录，变了才追加。
- 单测（REPL 路径，注入 reader）：`/resume <id前缀>` 切换后，下一次请求带的是目标会话的历史、
  不带切换前的对话；锚点簿与熔断状态归零；发出 `events.CONTEXT_REWRITING` 里的新事件——
  纵切写法同 feature 37：切换前召回过的记忆，切换后必须能再次被选中。
- 单测：`/resume` 无参 → 经 asker 弹出候选（最近 N 个、不含当前文件），选中即切换；取消不切换；
  没有可选会话时一句提示。
- e2e（TUI）：`/resume <id>` 之后屏幕上是目标会话的对话、原对话不在屏上；后续事件落在目标会话
  同名的 `.events.jsonl`。
- 注入反证：拿掉 `transcript.clear()` → TUI e2e 红；拿掉新事件的发出 → 召回纵切红；
  拿掉「一条没敲不写」→ 字节不变那条红。
- `./test.sh` 全绿，数字贴 devlog。

非目标：

- `--fork`（CC `--fork-session`：resume 时造新 id 走新文件）——问 1 定。
- 会话树 / 回退 / 分支重开（24 遗留）、跨项目选择器（CC `showAllProjects`）、会话搜索
  （CC `agenticSessionSearch`）、自定义标题。
- 不改格式 v1：`parentSession` 字段保留可读、不再写入。
- 不动 viz：它按同名配对读会话与事件流；`parentSession` 在 src 里没有消费者（2026-09-11 grep 核实，
  只有 interactive.py 的写入处）。

## 候选方案与确认

### 一、同一文件追加

方案 A · 接管原文件（照 CC）。`SessionLog.open_existing(path)`：读 header 取 id / cwd，
`_header_written = True`，`_last_id` = 物理尾部最后一条 id——半截回合留在盘上、内存里由
`trim_unfinished` 配平（dsh 形）。`--resume` 启动不再 `SessionLog(parent_session=…)`、不再重录，
ledger 直接用 `build_messages` 给的原 id。system：48 的 `_refresh_assembly` 换出的新 system
只在内存（ledger None、不落盘）——CC 转录不存 system prompt，下次 resume 反正重算；
指令消息：与磁盘最新一条内容相同就保留原条目，不同才由 `_inject_instructions` 追加一条。
events：`EventTrace` 在 session 接管之后构造，同名文件天然接上。按路径跨项目 resume：就地
追加到那个文件（CC `switchSession(sid, dirname(fullPath))` 同款）。
取舍：文件数不再翻倍，24 复盘质疑三「文件数 × 全量」的账直接销掉；代价是 24 的「自包含新文件」
不再成立——但它当时防的是 CC 反教材里「resume 造新身份 → 指数增长」，接管原文件连一次复制
都没有，比按原 id 重录更彻底。

方案 B · 维持新文件重录（现状），只做 `/resume`。
取舍：不动 24；但用户点名要追加，且 `/resume` 在进程内反复切换时每切一次复制一份全量历史，
滚雪球比 CLI resume 快得多。

方案 C · 追加到原文件，另留 `--fork` 走新文件 + parentSession（CC `--fork-session` 同款）。
取舍：两条路都留，代码与测试两份；pai 目前没有 fork 的动机（CC fork 是为了隔离 plan 文件与
worktree，pai 两样都没有）。需求出现再加，重录代码在 git 历史里。

### 二、会话内 `/resume`

方案 A · 照 CC 形态。`/resume` 无参 → 经 asker 弹选择框（最近 8 个、不含当前文件，每行
「MM-DD HH:MM · N 条 · 首句前 30 字」，Esc 取消）；`/resume <id前缀|路径>` 直达（复用
`resolve_resume_target`，找不到一句提示，同 CLI）。切换例程与启动 `--resume` 共用一份
`_switch_conversation(target)`：load → build → trim → refresh assembly → 就地换 `messages[:]` /
`ledger[:]`（闭包持有的是列表对象）→ `anchors.reset()`、熔断状态清零 → `session.switch_to(path)`
就地换（同一个 SessionLog 对象）→ `EventTrace` 改按 session 当前路径写（不再构造期缓存）→
`memory_tool.set_origin_session(新 id)` → 发新事件 `ConversationResumed` 并加进
`events.CONTEXT_REWRITING`（events.py 那条注释点名的「resume 重建」第三种改写；召回去重表与
规则注入表靠它作废，忘了加就是静默漏）→ TUI：`transcript.clear()` + `app.replay(...)` + 恢复
提示；REPL：print 提示。当前对话不需确认（已全部在盘上，CC 同）。干活期间敲的 `/resume`
照既有规则排队、轮末执行。
方案 B · 只做带参形式 `/resume <id前缀|路径>`，不做选择框。
取舍：少一个 Dialog 复用点；但用户手里没有 id 可抄（id 只在退出提示里出现过一次），
选择框才是真正可用的入口。

### 三、状态怎么换（结构）

方案 A · 就地变更（仓库既有的 mutable-holder 套路：asker_ref / event_sink / mode_state）：
`messages[:]`、`ledger[:]`、`anchors.reset()`、`SessionLog.switch_to`、`EventTrace` 按 session
现路径写。改动面小，闭包一处不动。
方案 B · 封 `Conversation` 对象（messages / ledger / anchors / state / session / transcript 一个壳，
pi SessionManager 的角色）：24 复盘质疑一登记的债「到第四件该封」——`/resume` 一次要换六件，
正是那个触发点。改动面：`run_agent` 八个调用点 + 装配 + 全部相关测试。
取舍：A 这一轮能交付；B 是对的方向但是另一次交付的体量——先 A，B 立独立档案。

### 确认

拍板（2026-09-11）：用户原话「照cc的吧，先合48」。逐问对到 CC 2.1.88 的做法：

问 1：同一文件追加怎么做？
- 候选 A·接管原文件、不留 fork。
- 候选 C·接管原文件 + `--fork-session` 保留新文件路径。
- 候选 B·不改落盘，只做 `/resume`。
选择：C。理由：「照 CC」——CC 默认 `switchSession(sid)` 沿用原 id 往同一文件追加，
另有 `--fork-session` 造新 id 走新文件；pai 的 fork 路径就是 24 的现行为（新文件 + parentSession +
按原 id 重录），放到 `--fork-session` 后面即可，既有测试改指向它而不是删掉。
问 2：`/resume` 的形态？
- 候选 A·无参选择框 + 带参直达。
- 候选 B·只带参。
选择：A（CC：无参 `LogSelector`，带参先当 id 匹配）。pai 没有自定义标题，带参就是 id 前缀 / 路径，
与 CLI 同一套 `resolve_resume_target`。
问 3：状态切换的结构？
- 候选 A·就地变更。
- 候选 B·先封 Conversation 对象。
选择：A。CC 的 `switchSession` 也是就地改 `STATE.sessionId`、REPL 里 `setMessages` 换状态，
不为此造新对象；B 的债仍在 TODO（24 复盘质疑一）。
问 5（交付后补漏，2026-09-11 用户截图）：用户原话「现在resume应该只会显示当前项目下的历史，
别的目录下的应该不显示的」——截图里无参 `--resume` 挑中了 `20260822-235906-8cf20ae1`，
它录制于 `pai_playground/skills-smoke`（同一 git 仓库的子目录，slug 按 git 根算，文件与根目录
同一个 sessions 文件夹）。
- 候选 A·按 header.cwd 过滤：无参 `--resume` 与 `/resume` 选择框只认录制 cwd = 当前目录；
  显式 id / 路径仍可跨目录（CC：项目目录按启动 cwd 归档，`--continue` 与 LogSelector 只看
  当前目录，跨目录 `checkCrossProjectResume` 拒绝并给 cd 命令；CLI 明确 id 可跨）。
- 候选 B·按 git 根过滤：现状，子目录会话照列——正是用户不要的。
选择：A（用户原话即拍板；同一轮交付的补漏，留在本档案）。代价：在 `src/` 里启动看不到
根目录录制的会话，与 CC 一致，README 写明。

问 4（流程）：先合 48 还是从 48 分支切？
选择：先合 48。已执行：`feat/48` 以 `--no-ff` 合回 `main`（merge cfed4e0），推送 main 与 48 分支，
再从 main 切出本分支。

## 结果与总结

交付（2026-09-11）：`pai --resume` 默认接管被恢复的会话文件追加（一个字没敲就退出，文件字节不变）；
`--fork-session` 保留 24 的新文件路径；会话内 `/resume` 无参弹最近 8 个会话、带参 id 前缀 / 路径直达，
切换后 TUI 清屏用 48 的回放画目标会话、REPL 打提示；切换发 `ConversationResumed`，召回去重表随之作废。

- 新增 `SessionLog.open_existing` / `switch_to`、`EventTrace.path` 跟 session 走、`ConversationResumed`、
  `modes/resume.py` 的切换六件（`load_conversation` / `refresh_assembly` / `resume_note` / `recent_sessions` /
  `switch_conversation` / `resume_command`）、`/resume` 命令、`TuiApp.clear_transcript`、`--fork-session`。
- 测试：`tests/test_resume_switch.py` 15 条 + e2e 1 条新增、1 条加固；三处注入反证各红。
- 数字：相关单测 `182 passed`，e2e `2 passed in 13.97s`，全量 `1720 passed`
  （STATUS 更新前一跑 `1 failed, 1719 passed, 8 deselected in 190.00s`，红的是测试数校验）；
  补漏后全量 `1723 passed`（更新 STATUS 前一跑 `1 failed, 1722 passed, 8 deselected in 195.13s`）。

顺带推翻一条旧登记：TODO 里「没有 /resume，要做得先有会话树」——CC 的 /resume 是线性切换，不需要树。

补漏（同日，用户截图）：无参 `--resume` 与选择框只认录制 cwd = 当前目录（`session_cwd` 只读首行），
显式 id / 路径仍可跨目录；+3 测试，数字见 devlog。

详细日志见 [devlog.md](devlog.md)，复盘见 [复盘.md](复盘.md)，取舍升格为 [D#80](../../decisions.md)。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处，否则等于没记 -->

- 对话框提示语「数字直选」与行为（序号 + 回车）不符。
- 重装配的 system 不落盘，文件里的 system 永远是首次录制版（evals 回放拿到旧 system）。
- 指令消息「变了才追加」会在长期文件里积累多条，体积账没算。
- `recent_sessions` 整文件解析每个候选；CC 有 lite log 两级。
- `--fork-session` 无 TUI e2e；选择框无搜索 / 跨项目开关。
- 跨轮状态就地变更到了第六件，封 `Conversation` 对象的债触发点已到（24 复盘质疑一，追记）。

## 用到的知识

- K [tui/cc-resume-rendering.md](../../../../knowledge/tui/cc-resume-rendering.md)（第五节：CC 不重录、`switchSession` 沿用 id；第一节：同一个渲染器——`/resume` 切换后屏幕换成那段对话的依据）。
- K [loop/session-format-three-way.md](../../../../knowledge/loop/session-format-three-way.md)（dsh「物理尾部保持撕裂原样」——接管原文件时 `_last_id` 取物理尾部的依据；CC 反教材「resume 不造新身份」——接管原文件比重录更彻底地满足它）。
