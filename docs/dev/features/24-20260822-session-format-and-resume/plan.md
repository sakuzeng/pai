# 24-session-format-and-resume · 实施计划

按拍板（A/B/A）拆七个 task，每个先红后绿。走读结论与反教材见
K loop/session-format-three-way.md。

- T1 写侧（core/session.py）：`SESSION_VERSION = 1`；文件首次落盘先写 header
  行 `{type:"session", version, id, timestamp, cwd, parentSession?}`；
  `append(record)` 包统一信封 `{type, id, parentId, ts}`——带 `role` 的记录
  自动包成 `{type:"message", message:{...}}`，带 `type` 的保留其 type；
  `parentId` 由 SessionLog 内部链（上一条 id）；`append` 返回 id；
  支持 `record_id=` 显式传 id（resume 重录用，不许造新身份）。
  旧的每条 ts/sessionId/cwd 冗余元数据取消（header 一次说清）。
- T2 读侧（core/session.py）：`load_session(path)` → (header, entries)。
  首行不是合法 header：报「旧格式（v0）不可恢复」（拍板问 2 = B）；
  version 比 SESSION_VERSION 新：报「由更新的 pai 写入，请升级」；
  比它旧（将来出现时）：报「本版本无升级路径」——方向分清（dsh 语义）。
  词汇表外的 entry type 拒绝而非静默跳过（dsh 教训）。
- T3 重建（core/session.py）：`build_messages(entries)` → (messages, ledger)。
  压缩条目按 pi `buildContextEntries`：取最后一条 compaction，输出
  [首条 system, 摘要 user（compaction.summary 按 compact() 同款包装）,
  自 firstKeptEntryId 起的保留段, compaction 之后的全部]；
  指令注入消息（INSTRUCTION_HEADER 前缀识别）重建时插回 system 之后
  （与 `_inject_instructions` 同位）。`replay_messages` 改走同一条路
  （压缩会话不再拒收——feature 23 那条 ValueError 的历史使命结束）。
- T4 loop 台账：`_record` 收 `ledger`（与 messages 平行的 entry id 表，
  跨轮由 REPL 持有，同 anchors）；compaction 落盘记录加
  `firstKeptEntryId = ledger[cut]`（保留 cut 供观察）；compact 重建后
  ledger 同步重建；`_inject_instructions` / `_extend` 同步维护。
- T5 resume 装配：`pai --resume [id或路径]`（无参 = 本项目 sessions 目录
  mtime 最新）；配平（CC 三道过滤的 pai 版：尾部未回填 tool_calls 的
  assistant 整块删）；锚点簿与熔断状态从零（CC 告警）；开新 SessionLog
  （parentSession 指旧会话），历史按原 id 重录；`run_interactive` 收
  预加载的 messages/ledger/session。
- T6 出口与提示：退出提示改真话（`pai --resume 可继续`，13 那条
  printResumeHint 对齐终于能说全）；viz 读者（viz/flow.py）适配 v1 信封。
- T7 e2e：真 pty 跑一段对话退出，`pai --resume` 再起，断言第二个进程发给
  假 provider 的 messages 含第一段历史；压缩会话的重建至少一条离线测试
  拿真实轨迹夹具。

已知风险：既有测试与 viz 里所有直读会话 JSONL 的地方都会红——这正是换格式
的代价预算内（评审 A1「一次到位」的含义）。
