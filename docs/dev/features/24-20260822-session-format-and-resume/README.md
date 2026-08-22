# 24-session-format-and-resume
状态：已交付（2026-08-22）
分支：`feat/24-session-format-and-resume`
流程：大改动走候选拍板 + plan 直做（前置走读已完成并沉淀
      K [loop/session-format-three-way.md](../../../../knowledge/loop/session-format-three-way.md)；
      不另写 spec——候选节即共识落盘，任务拆分写 plan.md）

## 需求

出处：R4#A1（高）+ TODO 三条既有登记（08 遗留「会话记录的完整字段改造」、
13 遗留「`--resume` 不存在」、23 遗留「uuid 幂等增量归 A1」）。

现状的洞：feature 13 之后退出即历史只剩 JSONL（alt 屏无 scrollback、
退出不回吐、退出提示不敢提 `--resume` 这个不存在的命令）；会话格式顶层
判别字段双轨（消息用 `role`、旁账用 `type`）、无消息身份（uuid）、
压缩落盘只有一条孤立记录导致 `replay_messages` 只能拒收压缩会话；
evals（阶段 7）明确依赖本项先行。

三家走读结论（K session-format-three-way）：首行 header、统一信封
`{type,id,parentId,ts}`、消息嵌套 payload、压缩记成带 `firstKeptEntryId`
的条目——四件事三家完全收敛。

验收标准：
1. 新会话文件：首行 header（type/version/id/timestamp/cwd），每条记录统一
   信封（type 单一判别字段 + id/parentId/ts），消息嵌 `message` 字段；
2. 压缩落盘为带 `firstKeptEntryId` 的 compaction 条目（历史不删），
   `replay_messages` 升级为按条目重建（压缩会话不再拒收）；
3. `pai --resume` 恢复最近一次会话接着聊，`pai --resume <id或路径>` 指定；
   恢复侧做半截回合配平（CC 三道过滤的 pai 版：未回填的 tool_calls 整块删），
   锚点簿与压缩熔断状态从零（否则 resume 后首步就可能误触发压缩死循环——
   CC 同款告警）；恢复路径不生成新 id（CC 反教材：resume 造新身份 →
   转录每次恢复指数增长）；
4. 退出提示升级为真话（「pai --resume 可继续」）；
5. 每条测试含至少一条真实轨迹夹具；全绿，数字进 STATUS。

## 候选方案与确认

### 问 1 · 格式形状

- A · 三家收敛形（信封 + 嵌套 + header）：如验收 1。代价是「换格式」——
  读写两侧都动，`replay_messages`/viz 时间线读者同步改。id 用标准库 uuid4
  （pi 的 uuidv7 为跨文件合并保时间有序，pai 无此需求，文件顺序已给序；
  此为实现细节不再另问）。parentId 先写字段、树操作（回退/分支）后置——
  pi 证明留了 parentId 之后树是纯读取侧算法。
- B · 最小增量：顶层 role 消息保持，只加 uuid/parentUuid 与首行 header。
  改动最小，但「判别字段双轨」的病留着（分类永远要写
  `r.get('type', r.get('role'))`），且与三家全都不同——每次对照参照实现
  都要先做一层心智翻译。
- C · 事件溯源单一真源（dsh Session 形）：E3 已裁决不抄，列出仅为完整。

### 问 2 · 旧格式（现存 v0 文件）怎么办

- A · 只读兼容：loader 认无 header 的旧文件为 v0（顶层 role → 包成信封，
  现场生成 id 仅存在于内存不写回），旧会话也能 `--resume`；恢复后写入的是
  **新文件**（header 的 `parentSession` 指旧会话 id，三家里 pi/dsh 都有这个
  字段）。旧文件永不改写。
- B · 不兼容：旧文件如实提示「旧格式不可恢复」。省一个 loader 分支，
  代价是现存所有会话作废——08 复盘那条「涉及删除/迁移的拍板要附执行时
  你能否分辨」适用：作废的是用户真实的历史。

### 问 3 · resume 范围

- A · 全量：`--resume`（最近一次）+ `--resume <id或路径>` + 压缩会话按
  firstKeptEntryId 重建 + 配平过滤 + 状态从零。一次把 13/23 两处遗留全关。
- B · 最小：只做「最近一次」，压缩会话拒收（沿用 replay_messages 现状）。
  更小，但压缩条目是本次格式改造的一半动机，拒收等于新格式只用了一半。

### 确认

（2026-08-22，AskUserQuestion，三问一轮）
问 1 格式形状：选 A·三家收敛形。
问 2 旧文件：选 B·不兼容——旧格式如实提示「不可恢复」，不做 v0 读兼容。
  执行时能否分辨（08 复盘那条）：旧文件原样留在磁盘上不动、不删不改，
  只是 `--resume` 拒绝它们并说明原因；作废的是「可恢复性」不是数据本身。
问 3 resume 范围：选 A·全量（含压缩会话重建 + 配平 + 状态从零）。
连带定下的实现细节（不再另问）：id 用标准库 uuid4；resume 开新会话文件、
header 带 parentSession 指旧会话、把重建后的历史按**原 id** 重录进新文件
（自包含，单文件永远够用；CC 反教材钉死「resume 不许造新身份」）。

## 结果与总结

七个 task 全部交付（详见 devlog）：v1 格式（header 首行 / 统一信封 / 消息嵌套 /
压缩即条目带 firstKeptEntryId）、loop 与 REPL/TUI 全链 id 台账、
`/compact` 补落盘、`pai --resume`（latest / id 前缀 / 路径）带配平与状态从零、
按原 id 重录的自包含新文件（parentSession 指旧会话）、退出提示改真话、
viz 读边归一化、两进程接力 e2e。「重放 == 内存对话」不变量从无压缩会话
扩到全部。注入反证三连各红各的。全量 1241 passed, 3 deselected。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md -->

- `--resume` 只进交互模式：`pai --resume "任务"`（CC 的 `-c -p` 组合）被拒绝，
  once 模式续跑未做。
- resume 只恢复对话，不恢复设置：权限模式/模型/system prompt 都取当前环境
  （dsh 明确警告「恢复不同构图的组合是错误」——pai 现在如实不管，连警告都没有）。
- 会话选择器没有：`--resume` 无参取 mtime 最新，同秒 tie 时取哪个未定义。
- 观测流（`.events.jsonl`）仍是旧平铺格式：一对文件两种形状，viz 靠归一化
  弥合；events 侧要不要同步换信封，等 evals 立项时定。
- 树操作（回退/分支重开）只有字段没有功能：parentId 已在，`buildSessionPath`
  类的 leaf 游走没做——pi 证明那是纯读取侧算法，需求出现再开。

## 用到的知识

- K [loop/session-format-three-way.md](../../../../knowledge/loop/session-format-three-way.md)（本轮走读沉淀：三家收敛形 + CC 反教材 + dsh 拒绝语义）。
- K [loop/cc-prompt-and-transcript.md](../../../../knowledge/loop/cc-prompt-and-transcript.md)（recordTranscript 的 uuid 幂等——本轮兑现其「归 A1」的那半）。
