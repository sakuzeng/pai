# 34-todo-backlog-batch · 开发日志

一步一条。全局 devlog 只记里程碑一行 + 指到这里。

## 2026-08-25 · 挑条目与两处拍板

目标：从 TODO 的 180 条开放项里挑出「不等外部输入、修法已有形状」的那一批。

用户给的挑选标准是硬的：写着「等真实使用数据 / 等复现 / 等真实需要 / 记录性 /
观察期」的一律不碰，也不许凭空造数据去满足它们；遇到需要拍板的当场问。

通读全文后分成三类：可直接做的（修法在条目里已写明）、需要拍板的（两条）、
明确等条件的（跳过，清单见本文件末尾）。两条需要拍板的当场问了用户，
问答原样存进 [README](README.md) 的「候选方案与确认」节，结论都是推荐项：
AnchorBook 换 NamedTuple、未知 role 按 content 估算。

改动：新建本档案，`.active` 指向它，开分支 `fix/34-todo-backlog-batch`。

测试：无（尚未动代码）。

## 2026-08-25 · 压缩与配置的四条小账

目标：清 02 终审延后项与 R#5 —— context_window 报错、Anchor 具名、
tripped 单向性、未知 role 估算。

改动：`src/pai/config.py`、`src/pai/core/compaction.py`、`src/pai/core/loop.py`、
`src/pai/modes/interactive.py`（三处 `latest()` 调用点）、
`tests/test_config.py`、`tests/test_compaction.py`。

一处动工时才发现的坑：`latest()` 换成 `Anchor(index, tokens)` 之后，
「无锚」这条退化路径的判据从「第一个字段是 None」变成了 `index is None`——
如果照着新字段名顺手写成 `anchor=latest.tokens`，空锚簿会给出 0，
而 `context_tokens` 把 0 当成「真有个 0 token 的锚」走锚定分支，
工具 schema 那几百 token 就此从账上消失。补了
`test_no_anchor_is_index_none_not_tokens_zero` 把这个差别本身钉住。

测试（红 → 绿）：

- `context_window` 非法值：`2 failed, 9 passed` → `11 passed`
- Anchor 具名：`3 failed, 2 passed`（TestAnchorBook 子集）→ 全类 `6 passed`
- 未知 role 估算：`2 failed, 1 passed`（`-k unknown_role`）→ `tests/test_compaction.py 47 passed`
- tripped 单向性：本来就对，属补测试。做了注入反证——把
  `tripped=state.tripped or failures >= MAX` 改成 `tripped=failures >= MAX`
  即 `1 failed`，装回即 `1 passed`。

遗留：无。

## 2026-08-25 · 事件通道与队列长度

目标：TUI 下 MemoryWritten / RecallFailed 打进 stdout（feature 12/13 起就有），
以及 `_queue_size` 读 `PendingMessageQueue` 私有表（12 复盘质疑一）。

改动：`src/pai/modes/interactive.py`（新增 `EventSink`，装配处传 sink、
`_run_tui` 一处 `set`）、`src/pai/core/queue.py`（`__len__`）、
`tests/test_assembly.py`、`tests/test_trace_wiring.py`、`tests/test_queue.py`。

事件通道这条的根因与 2026-08-11 那次 asker 卡死同构：装配层把 `on_event`
烤进闭包，而 TUI 是装配之后才建起来的。所以修法也照 `AskerRef` 的样子来，
两个可变持有者并排住着，下次再有「装配期烤进去、运行期要换」的东西有现成的形。

覆盖分两头：一头证明 sink 换完之后事件不再流回旧通道（`test_assembly.py`），
另一头证明 `_run_tui` 真的换了它——把 `TerminalSession.start` 换成引爆点，
让真 `_run_tui` 跑到那一行为止（它之前全是纯构造），不去断言源码文本
（R4#T3 的教训：`"trace=" in getsource(...)` 连 `trace=None` 都命中）。

测试（红 → 绿）：

- 事件通道：`1 failed, 4 passed` → `tests/test_assembly.py 5 passed`；
  `tests/test_trace_wiring.py + test_assembly.py 15 passed`。
  注入反证：拿掉 `event_sink.set(on_event)` 那一句即 `1 failed`。
- 队列长度：`2 failed, 15 passed` → `tests/test_queue.py + test_interactive.py 62 passed`

遗留：无。

## 2026-08-25 · resume 挑选、截断提示、类型注解、风格杂项

目标：24 复盘质疑四（同秒 mtime tie）、R#17（截断提示给出路）、
R#14 + R3#8（client / response 与两个文件的类型注解）、R3#16 + R3#11 + R3#12（风格五条）。

改动：`src/pai/core/session.py`、`src/pai/core/tools/fs.py`、
新增 `src/pai/core/protocols.py`、`src/pai/core/loop.py`、
`src/pai/core/compaction.py`、`src/pai/core/recall.py`、`src/pai/modes/once.py`、
`src/pai/modes/assembly.py`、`guards/design_gate.py`、`src/pai/viz/server.py`、
`src/pai/viz/collect.py`、`tests/test_session_format.py`、`tests/test_tools.py`、
`tests/test_loop.py`、`tests/test_compaction.py`。

`ChatClient` 刻意只描述 `client.chat.completions.create` 这一条路径：
Protocol 写得越宽，能通过的实现越少，而 pai 并不想约束 provider SDK 的其余部分。
`response` 如实写 `Any` 并在 docstring 说明为什么——非流式是 SDK 的响应对象、
流式装配后是 pai 自己的结构，写死任何一个都是在说谎。

FROZEN_TOOL_SCHEMAS 拉平缩进时出过一次事故：脚本找「顶层收尾 `]`」时
撞上了 `"required": [ … ]` 的内层 `]`，把括号改到了错的地方——而它仍是合法
Python，48 条测试照样全绿。发现后从 HEAD 取回原块重做，并用
`ast.literal_eval` 比对新旧字面值确认逐字未变。冻结夹具改缩进也得证明没改内容。

测试（红 → 绿）：

- 同秒 tie：`1 failed, 18 deselected` → `tests/test_session_format.py 19 passed`
- 截断提示：`1 failed, 62 deselected` → `tests/test_tools.py 63 passed`
- ChatClient：两条契约测试 `2 passed`（协议模块与测试同批写，无红；
  反向那条钉的是「Protocol 不能宽到什么都通过」）
- 类型注解与风格：`tests/test_loop.py 95 passed`、`tests/test_compaction.py 48 passed`、
  `tests/test_design_gate.py 13 passed`、viz 三套 `63 passed`

遗留：无。

## 2026-08-25 · 文档对账与销账

目标：把本轮修掉的逐条在 TODO 原条目上销账；顺带把复核中发现「其实早已修过、
只是漏勾」的条目也核销掉；两对重复登记合并。

改动：`docs/dev/TODO.md`（17 条销账 + 2 条修毕销账 + 2 对去重）、
`docs/dev/decisions.md`（D#7 引用链回收、D#8 推翻记录、D#9 理由更正，
原文一律划掉保留不删）、`docs/dev/STATUS.md`、全局 `docs/dev/devlog.md` 一行。

对账核销（本轮复核发现早已关闭、只是漏勾的五条）：

- 02 终审 Minor#8（压缩后审计流不含摘要）——feature 24 会话格式 v1 已关
- 02 终审 Minor#9（awaiting_verify 永挂）——注释早在 loop.py 验证块上（R4#23）
- R3#5（SYSTEM_PROMPT 硬编码工具名）——feature 22 的 `build_system_prompt` 已关
- R#11（单轮多 tool_calls 无测试）——2026-08-09 就有两条测试，与 P0 节那条同一件事
- R#15（session 文件名精确到秒）——文件名早已带 `session_id[:8]`，撞不到一起
- （另加）`@tool` 注册表进程级全局——2026-08-19 的 `isolate_tool_registry` 已根治

测试：`./test.sh` 全量（数字见 README 结果节与 STATUS）。

## 本轮刻意没做的（跳过的条目与理由）

按用户给的标准跳过，不是漏了：

- 等真实数据 / 等复现：reserve_tokens 与 keep_recent_tokens 实测校准、
  reasoning 400 监控、pty e2e 父子退出竞态根因、ESC_SETTLE_SECONDS 慢链路验证、
  拖选卡顿成因、四个 skills 预算常量校准、pytest-xdist 观察期。
- 记录性条目（写下来就是它的全部作用）：启动侧无肉、「哪些工具不该加超时」、
  25 遗留 6、viz 时间线不显示金额。
- 明确等条件才动的：截断逻辑抽 `truncate_output()`（第三个产出文本的工具出现时）、
  抽共享测试夹具层（测试文件到 10 个左右）、`compaction.py` 拆目录（等 +300 行）、
  microcompact 评估、封 Session 会话对象（到第四件平行状态时）。
- spec 明确非目标 / 需求未出现：MCP 的 HTTP+OAuth 与 resources/prompts、
  skills 的 frontmatter 扩展、plan 模式、树操作、只读命令免提示集合。
- 需要用户定的（不是我能拍的）：gates.md 的本地备份放哪。
- 需要独立设计而非清账的：子目录指令懒加载与路径作用域规则（已在需求池待评估）、
  可扩展性改造 R4#E1~E5、跨项目吸收 R4#A2~A10、召回单调衰减、按钱算预算。
