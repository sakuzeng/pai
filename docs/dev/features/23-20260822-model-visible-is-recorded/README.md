# 23-model-visible-is-recorded
状态：已交付（2026-08-22）
分支：`feat/r4-e2-e3-extensibility`（与 feature 22 同批）
流程：中等改动（候选拍板后直做 + TDD——评审已明确否掉大重构，
      剩余取舍只有「收口 + 不变量」的做法边界）

## 需求

出处：R4#E3（P1）。「模型可见的都已落盘」目前只是习惯不是不变量：
loop 里 messages.append 与 session.append 是散在 5 处的成对手工操作
（`_extend` 只是雏形），漏一半不会有任何测试变红——R4#5 那类
「落盘与回填之间的异常留下结构非法对话」正是这个缺口的产物。
这也是阶段 7 evals 的地基：回放会话 JSONL 必须能重建发给模型的 messages。

验收标准：
1. loop 内所有「模型可见消息」的追加收口到一个函数（含 system/user/
   assistant/tool 四类与注入路径）；
2. 一条不变量测试：取会话 JSONL 重放，重建出的 messages 与真发给
   provider 的最后一次请求逐字段相等；至少一条用真实轨迹夹具；
3. 压缩会改写历史——含 compaction 记录的会话如实声明本轮不变量不覆盖
   （完整回放语义归 R4#A1 会话格式立项），测试遇到即明确跳过而非假绿；
4. 行为零变化（纯收口 + 测试），全绿。

## 候选方案与确认

### 方案 A · 最小做法（评审建议）：收口 + 回放不变量

`_extend` 一般化成 `_record(messages, entry, session)`（或等价收口），
5 处成对操作全部改走它；新增回放不变量测试（FakeClient 捕获请求对照）。
- 优点：行为零变化；evals 地基直接可用；顺手钉住 R4#5 的同族回归。
- 代价：无实质代价——这正是它是「最小做法」的原因。

### 方案 B · event-sourcing 重构（单一事实源，messages 从记录推导）

- 评审点名不抄：那是 fork / 多前端的规模需求，pai 现阶段属过度设计。

### 方案 C · 只加不变量测试，不收口

- 代价：不变量红了只知道「漏了」不知道哪处；修的时候还是要收口——
  等于把 A 拆成两半各付一次成本。

### 确认

问 1（2026-08-22，AskUserQuestion）：怎么做（候选 A/B/C 如上）？
用户答（原话）：「cc是怎样做的呢，参照一下」。
CC 实证（反编译源码，检索符号名）：`src/utils/sessionStorage.ts` 的
`recordTranscript(messages)` 是唯一收口点——QueryEngine 约 8 处全调它，
传当前 messages；函数幂等：按消息 uuid 对已落盘集合
（`getSessionMessages`）去重，只追加增量，顺手串 parentUuid 链；
压缩后 messagesToKeep 出现在新 summary 之后的情况有专门的前缀跳过逻辑。
即 CC 的不变量靠「单一收口 + 按身份幂等增量」维持。
选择：A（收口 + 回放不变量），带一条 CC 对照说明——「按 uuid 幂等增量」
那半依赖消息带 uuid，pai 的消息还没有身份字段，这半归 R4#A1 会话格式
立项一并做；本轮收口的是「成对 append 只有一个出口」这半，
回放不变量测试同时为 A1 与 evals 铺地基。

## 结果与总结

已交付：`_record(messages, entry, session)` 成为「模型可见」的唯一入账口
（loop 内 5 处成对 append + `_extend` 全部改走它；`type` 旁账与
`_inject_instructions` 的 insert 是仅有的两类例外，理由写在 `_record` docstring）。
`core/session.py` 新增 `replay_messages(path)`：滤 `type` 记录、剥
ts/sessionId/cwd 元数据；含 compaction 记录直接 ValueError（压缩改写历史，
硬拼是错序对话，完整回放归 R4#A1）。三条测试：真实轨迹重放（REAL_TRAJECTORY）、
压缩会话拒收、不变量本体（真实回合后 重放 == messages == 最后请求 + 收尾
assistant）。注入反证：让 `_record` 对 tool 消息漏记 session → 不变量精确红。
行为零变化（180 passed 的既有测试一条没改）。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md -->

- 收口只覆盖 loop：`modes/interactive.py` 的 `_run_shell` 与 `_handle_command`
  仍有自己的成对 append（`!命令` 转述、/clear 后重建），不变量测试照不到
  REPL 侧路径（已登记 TODO）。

## 用到的知识

- K [loop/cc-prompt-and-transcript.md](../../../../knowledge/loop/cc-prompt-and-transcript.md)（本轮走读沉淀）。
