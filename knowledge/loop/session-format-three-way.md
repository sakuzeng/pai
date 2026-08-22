# 会话格式三家对照：header 首行、统一信封、压缩即条目

- 来源：pi `packages/coding-agent/src/core/session-manager.ts`（1712，可读源码）；
  CC 反编译源码 `src/utils/sessionStorage.ts`（`recordTranscript` /
  `buildConversationChain`）、`src/utils/conversationRecovery.ts`、
  `src/utils/messages.ts`（`filterUnresolvedToolUses` 等三道过滤，符号名检索）；
  dsh `docs/subsystems/persistence.zh.md`（第一方文档，pin `47f9438`）
- 精读日期：2026-08-22
- pai 锚点：`src/pai/core/session.py`、
  `docs/dev/features/24-20260822-session-format-and-resume`
- 相关：[cc-prompt-and-transcript.md](cc-prompt-and-transcript.md)
  （recordTranscript 的收口与幂等，本篇不重复）

一句话：三家在「首行 header + 每条统一信封 + 消息嵌套在 payload 里 +
压缩是一条带指针的条目」上完全收敛——这是比「120s/600s 超时」更强的三票信号。

---

## 一、格式：三家收敛的四件事

1. 首行 header。pi：`{type:"session", version, id, timestamp, cwd, parentSession?}`；
   dsh：header 带 `version`，JSONL 后端**先于任何事件行解码**就从原始 header 拒绝
   外来版本，且报错说明方向（比自己新→「请升级 harness」；比自己旧→「本构建无
   升级路径」）——「版本不对」与「数据损坏」是两种错误，不许混。
2. 统一信封 + 嵌套 payload。pi：`{type, id, parentId, timestamp}` 外壳，消息是
   `type:"message"` 且正文嵌在 `message` 字段；CC 同构（`{type:'user'|'assistant',
   uuid, parentUuid, message}`）。顶层判别字段只有一个 `type`——pai 现状
   「消息用 role、旁账用 type」的双轨正是三家都没有的东西。
3. id 链。pi 用 uuidv7（时间有序），`parentId` 指上一条；CC 用 uuid4 + `parentUuid`。
   线性会话里链就是文件顺序，树（回退/分支）才真正用到它——pi 的
   `buildSessionPath` 从 leaf 沿 parentId 走到根再反转。
4. 压缩是一条**条目**不是改写。pi `CompactionEntry`：`summary + firstKeptEntryId
   + tokensBefore`；重建（`buildContextEntries`）= 取路径上最后一条 compaction，
   输出 [compaction 摘要, 自 firstKeptEntryId 起的保留段, compaction 之后的全部]。
   历史一个字不删，回放天然可行——pai 的 `replay_messages` 之所以必须拒收压缩
   会话，正因为 pai 的压缩是就地改写内存、落盘只有一条孤立的 type 记录。

## 二、恢复：卫生过滤与「配平不改盘」

- CC resume 三道过滤（`messages.ts`）：`filterUnresolvedToolUses`（assistant 声明的
  tool_use 没有对应 result 就整块删——半截回合是 400 之源）、
  `filterOrphanedThinkingOnlyMessages`、`filterWhitespaceOnlyAssistantMessages`。
  过滤注释里有条反教材：早期实现在过滤时调 `normalizeMessages` 生成了新 uuid，
  落盘去重认不出，**每次 resume 转录都指数增长**——resume 路径上不许造新身份。
- CC 删除消息后的 relink：幸存消息的 parentUuid 指进被删区间时，
  `buildConversationChain` 会 `get(undefined)` 停在断链处、把之前的历史全孤儿掉——
  沿被删区自己的 parent 链回走到第一个幸存祖先重新挂上。链式格式的税，收着。
- dsh：崩溃恢复「在内存中配平中断的轮次，物理尾部保持撕裂原样」——修复发生在
  读取侧，磁盘上的半行/半轮不动。与 CC 的过滤是同一思想的两种表述。
- dsh：词汇表外的事件类型**拒绝**而非静默跳过（除非信封带 `ignorable: true`）——
  「静默跳过一个不认识的必需事件可能改变日志其余部分的解读方式」。

## 三、pai 视角的取舍清单

- 可直抄：header 首行（带 version + 拒绝语义分方向）、统一信封 `{type,id,parentId,ts}`
  + 消息嵌套、compaction 条目带 firstKeptEntryId、resume 读取侧配平（不改盘）。
- 要挑的：uuidv7 自实现（时间有序）vs 标准库 uuid4（文件顺序已给序）——pai 无
  跨文件合并需求，uuid4 够；树操作（回退/分支）字段先留、功能后置（pi 的
  buildSessionPath 证明留了 parentId 之后树是纯读取侧算法）。
- 不抄：dsh 的「事件日志即真源」（E3 已裁决 event-sourcing 属过度设计）、
  Zstandard 压缩帧、SQLite 后端、CC 的远程持久化与 sidechain。
