# 24-session-format-and-resume · 开发日志

## 2026-08-22 · 三家走读 → 拍板 A/B/A → 七个 task TDD 交付

目标：会话格式 v1（header + 统一信封 + 压缩即条目）+ 全量 `--resume`。

改动：
- T1-T3 `core/session.py` 重写：`SESSION_VERSION=1`、header 首行、信封包装
  （消息嵌 `message`）、`append` 返 id 且支持 `record_id`（resume 不造新身份）、
  `load_session`（v0/更新版本拒绝语义分方向、词汇表外类型拒收）、
  `build_messages`（pi buildContextEntries 同款压缩重建 + 指令归位）、
  `replay_messages` 升级（压缩会话不再拒收）、`_summary_message` 成为摘要
  包装唯一出处（compact() 改调它）。
- T4 loop：`entry_ledger`（与 messages 平行的 id 台账，REPL 跨轮持有）穿过
  `_record`/`_extend`/`_inject_instructions`；自动压缩落 `firstKeptEntryId`
  且压缩条目**先于**指令重注入落盘（顺序反了重建会把新指令归进被摘掉的旧段）。
- T4b interactive：ledger 穿 REPL/TUI 全部 dispatch 路径；`/compact` 此前
  **根本不落盘**——补成与自动压缩同款；`/clear` 同步裁台账；`_run_shell`
  改走 `loop._record`（feature 23 的 REPL 侧遗留就此关闭）。
- T5 resume：`resolve_resume_target`（latest/id 前缀/路径）、`trim_unfinished`
  （CC 三道过滤的 pai 版）、`run_interactive(resume=)` 重建 + 按原 id 重录进
  新文件（header.parentSession 指旧会话）+ 锚点簿/熔断从零；cli `--resume`
  （与任务参数互斥、两类可预期错误变人话）。
- T6 退出提示改真话（13 号那笔债）；viz `flow._normalize_v1` 读边归一化。
- T7 e2e：两个真进程接力（第一个聊完退出、第二个 `--resume` 起来，断言发给
  假 provider 的请求带着第一段对话）。

测试：新文件 `test_session_format.py` 17 条 + loop/modes/viz/e2e 增补；
换格式的既有破坏 4 条逐一改写（形状断言 3 + 「拒收压缩」按拍板改写）。
注入反证三连（各红各的、复原全绿）：resume 造新身份 → 保留 id 断言红；
压缩丢 firstKeptEntryId → 跨压缩重放不变量红；跳过配平 → 半截回合断言红。
全量 1241 passed, 3 deselected。

过程小事故（如实记）：用 python 三引号字符串往 e2e 文件写替换时，`\r` 被
解释成真回车写进源码把字符串字面量劈断（SyntaxError），第一次修复又把
提交键吃掉造成 e2e 假红。教训：跨语言写文件时转义层数要在写之前数清，
写完 `ast.parse` 一遍再跑。

遗留：见 README「遗留问题」，逐条已登记 TODO。

## 2026-08-22 · 用户问「正确了吗」→ 交付后自查 + 真模型反向对照

自查（对照 pi 原版逐行重审 build_messages）撞出一个真洞并当场红→绿：
第二次压缩的切点落在第一次的摘要消息上时，firstKeptEntryId 指向的是
compaction 条目——只扫 message 条目的保留段扫描会把保留段**静默丢光**。
pi 的 buildContextEntries 扫全部条目、压缩条目在保留段里化身摘要消息，
抄的时候漏了这层。修法照 pi；`test_second_compaction_can_keep_the_first_summary`
钉死。

真模型反向对照（roadmap 固定末项「交付前跑完整真实回合，哪怕花钱」）：
pai_playground/resume-smoke 里三段真回合（真 DeepSeek、真 pty、真 TUI）——
约定暗号 → 退出（提示带 `pai --resume 可继续`）→ `--resume` 起新进程答出暗号
→ 再 resume 一次（链式：恢复「恢复产生的文件」）仍答出。撞出两条真实观察：
1. 「请记住」这句话会诱发模型调 `remember` 工具弹权限框——预期行为，
   但冒烟脚本第一版没接框，Ctrl+D 落在框上退出提示就不完整；
2. Ctrl+D 落在回合收尾的 busy 窗口会被静默忽略（R4#25 拍板「EOF 不放行」的
   真实代价：用户要再按一次；当时拍板已预见，此处是第一次真机撞见）。
