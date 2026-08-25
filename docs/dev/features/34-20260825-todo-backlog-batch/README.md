# 34-todo-backlog-batch
状态：已交付
分支：`fix/34-todo-backlog-batch`（全部改动与文档对账都在这一条上）
流程：中等改动直做（无 spec/plan）。理由：本轮不是一个新功能，是把 TODO 里
      「修法已有形状、不等外部输入」的存量条目批量清掉——每条各自独立、
      各自 TDD，没有需要先设计的整体方案；两处真有分歧的当场问了用户（见下）。

<!-- 状态取值：讨论中 → 已拍板 → 实现中 → 已交付 → 已验收；只在此处维护一份 -->

## 需求

用户 2026-08-25 指示：清一批 TODO 里还开着的待办。挑选标准由用户给定——
只做「不等外部输入、修法已有形状」的；明确写着「等真实使用数据 / 等复现 /
等真实需要 / 记录性 / 观察期」的一律不碰，也不凭空造数据去满足；
遇到需要拍板的当场问，不代替用户拍板也不因此跳过整条。

验收标准（怎么算做完）：

1. 每条 TDD：先写测试跑红（贴真实输出），再写实现跑绿（贴真实数字）。
2. 每修一条，在 TODO.md 原条目上销账（划掉 + 已修说明 + 出处）。
3. 纯对账条目（实际早已修过、只是漏勾）同样销账，并写明是哪次改动关掉的。
4. `./test.sh` 全量绿，且 STATUS.md 的 passed 数字同步（机器对账）。

本轮的条目清单（含跳过的与为什么跳过）见 [devlog.md](devlog.md)。

## 候选方案与确认

批量清账本身没有「整体方案」可选，需要拍板的是其中两条条目各自的修法。
两问都在开工前问了用户，原样存档：

问 1：TODO「AnchorBook.latest() 返回序与 entries 存储序相反（02 终审 Minor#6）」
怎么修？entries 存 `(index, tokens)`，latest() 返回 `(tokens, index)`。

- 候选 A·换 NamedTuple 具名字段：latest() 返回 `NamedTuple(index, tokens)`，
  调用方按名取，序无关；entries 也顺带具名。改动比统一序小，且以后再调序
  不会静默坏掉调用方。
- 候选 B·统一成 `(index, tokens)`：latest() 改成与 entries 同序，逐个改调用方
  解包。序统一了，但解包点仍是位置相关，将来再改仍会静默坏。
- 候选 C·不改，只补注释：在 latest() docstring 写明「返回序与 entries 相反，
  是刻意的」。改动最小，但坑还在。

选择：A（换 NamedTuple 具名字段）。理由：用户选了推荐项——按名取值，
序不再是调用方要记住的隐式契约。

问 2：TODO「decisions 第 8 条与第 6 条自相矛盾（R#5）」：未知 role 的消息
`estimate_tokens` 记 0，而 D#6 说低估是唯一会炸窗口的方向。怎么裁？

- 候选 A·按 content 估算，宁可高估：未知 role 也按 content + tool_calls 估算，
  与已知 role 同算法。消除低估方向，与 D#6 一致；代价是 D#8「来路不明的数
  不进阈值」被推翻，需在 decisions 里记推翻理由。
- 候选 B·记 0 但走告警路径：保留 D#8 的语义，但撞到未知 role 时发一次告警，
  不再静默。改动更小，D#8 不被推翻，但低估方向仍在。
- 候选 C·两条都做：按 content 估算 + 撞到未知 role 时告警。改动最大。

选择：A（按 content 估算，宁可高估）。理由：用户选了推荐项。落点写明
`serialize` 那条 `role not in KNOWN_ROLES` 的跳过保持不变——拍平的语义
（不认识的消息不塞进摘要请求）与秤的语义（不认识也得称重）是两回事。
→ 升格进 [decisions.md](../../decisions.md)（D#8 推翻记录）。

## 结果与总结

11 条真修 + 6 条对账核销 + 2 对重复登记合并，TODO 开放项从 180 条降到 161 条。
全量 `./test.sh`：1411 passed, 3 deselected（此前 1395）。

真修的十一条，按落点分组：

压缩与配置（02 终审延后项 + R#5）

1. `PAI_CONTEXT_WINDOW` 非法值不再裸抛 `ValueError`（Minor#7）。非整数与非正数
   都在门口 `sys.exit` 说清是哪个 env、当前值是什么、该怎么配。顺带挡住 0 与负数：
   语法合法但会让 `window - reserve` 算出负预算，于是每轮都判"该压缩"。
2. 锚点换具名 `Anchor(index, tokens)`（Minor#6，用户拍板 A）。`entries` 与
   `latest()` 从此是同一种东西，序不再是调用方要背下来的隐式契约。
3. 熔断 `tripped` 单向性补测试（Minor 延后项）。实现本来就对，所以做了注入反证。
4. 未知 role 照常称重（R#5，用户拍板 A）。推翻 [D#8](../../decisions.md) 的秤那一半。

事件通道与接口（12/17 遗留）

5. TUI 下 `MemoryWritten` / `RecallFailed` / `RecallInjected` 不再打进 stdout：
   新增 `EventSink` 可变持有者，`_run_tui` 一处 `set`。
6. `PendingMessageQueue.__len__`：modes 层不再读私有表（12 复盘质疑一）。

会话与工具

7. `resolve_resume_target` 同秒 mtime tie 排序稳定（24 复盘质疑四）。
8. `read_file` 截断提示给出路：说清"前 N / 全文 M"、点名 `sed -n` 分段读、
   并明说别拿残缺内容去 edit_file（R#17，取零成本做法，真正的 offset 参数仍没做）。

类型与风格（R#14 / R3#8 / R3#16 / R3#11 / R3#12）

9. 新增 `core/protocols.py` 的 `ChatClient`，接进六处 client 参数。
10. `guards/design_gate.py` 与 `once.py` 补类型注解。
11. R3 风格五条清零。

对账核销六条（复核发现早已修过、只是漏勾）：02 终审 Minor#8 / Minor#9、R3#5、
R#11、R#15、`@tool` 注册表隔离。逐条写明是哪次改动关掉的，见
[TODO](../../TODO.md) 与 [devlog](devlog.md)。

跳过的条目与理由（按用户给的标准，不是漏了）见 [devlog 末节](devlog.md)。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md 并注明出处 -->

实现层无新增遗留：11 条都是收口，没有留下半成品。
[复盘](复盘.md)引出四条，已逐条登记 [TODO](../../TODO.md)「feature 34 复盘引出」节：

- 第三个可变持有者出现时抽泛型 `Ref[T]`（质疑一）
- 装配为什么必须在 TUI 之前——两个持有者可能是同一个更深问题的症状（质疑二）
- `read_file` 截断提示没有真模型验证，倾向于 offset 参数才是正解（质疑三）
- 给「漏勾」建一条可执行检查（「下次怎么做更好」）

## 用到的知识

本轮无新增精读：清的是存量条目，各自的出处（R#n / R3#n / 02 终审 Minor#n /
24 复盘 / 12 复盘）已在 TODO 原条目里写明，逐条链接见 devlog。
