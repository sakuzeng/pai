# 35-todo-backlog-batch-2 · 开发日志

一步一条。全局 devlog 只记里程碑一行 + 指到这里。

## 2026-08-26 · 挑条目、复核代码、两处拍板

目标：从 TODO 的 165 条开放项里挑出「不等外部输入、修法已有形状」的一批。

挑选标准与 feature 34 同一套（用户给定，硬的）：写着「等真实使用数据 / 等复现 /
等真实需要 / 记录性 / 观察期 / spec 非目标」的一律不碰，也不许凭空造数据去满足；
条目里写着修法/出路的优先；遇到需要拍板的当场问。

通读全文之后没有直接开做，先拿代码复核了约二十条候选——用户这次点名了
「先看代码现状再看条目描述，别照着条目想当然」。这一步捞出三类东西：

- 三条其实早就修过、只是漏勾（核销清单见下）；
- 一条条目里写着的修法不能照做（pgid 那条，见「跳过的条目」）；
- 一条同族洞条目里没写（`/clear` 也没清召回去重表）——是复核压缩那条时撞见的。

两处真有分歧的当场问了用户，问答原样存进 [README](README.md)：
召回去重表选「上下文被改写就全清」，D#43 选「改成也读 AGENTS.md」。

改动：新建本档案，`.active` 指向它，开分支 `fix/35-todo-backlog-batch-2`。

测试：无（尚未动代码）。

## 2026-08-26 · 压缩链路第一次能在真实使用里跑到

目标：TODO「压缩链路的可验证性」那一节的前两条（2026-08-10 用户实测暴露的）。

第一条是 `PAI_KEEP_RECENT_TOKENS`。这个口子存在的理由不是调优：触发一次压缩要
同时满足两个条件，`PAI_CONTEXT_WINDOW` 能让第一个永远成立，第二个（相邻两锚的
真实差值累计 ≥ keep_recent_tokens）却没有任何环境变量能改——小对话里差值只有几百，
于是真跑一次压缩得先攒够 2 万 token 的对话。离线测试看不见这道坎，正是因为它们
直接传 `CompactionSettings(keep_recent_tokens=1)` 把坎绕过去了。

第二条是 `/compact` 的「无可压」。它分不清「坏了」与「还没到量」，而差额是算得出来的。

改动：`src/pai/config.py`（`keep_recent_tokens()`，报错形状对齐
`context_window()`）、`src/pai/core/compaction.py`（纯函数
`keep_recent_shortfall`）、`src/pai/modes/once.py` 与
`src/pai/modes/interactive.py`（装配接线 + `/compact` 文案）、
`tests/test_config.py`、`tests/test_modes.py`、`tests/test_interactive.py`、
`tests/test_compaction.py`。

红：`3 failed`（`ImportError: cannot import name 'keep_recent_tokens'`）→
接线两条 `2 failed`（`assert 20000 == 888`）→ shortfall 两条 `2 failed`
（ImportError）→ 文案一条 `1 failed`（`assert '19200' in '⚠️ 无可压：保留预算已吞下全部历史…'`）。
绿：`tests/test_config.py -k keep_recent` `3 passed`、
`test_modes.py + test_interactive.py -k keep_recent` `2 passed`、
`test_compaction.py -k shortfall` `2 passed`、`test_interactive.py -k compact` `5 passed`。

诚实边界：这两条只是把「跑得到」变成可能，`reserve_tokens` / `keep_recent_tokens`
本身仍是借来的经验值（那条待办照旧开着，它等的是真实数据不是代码）。

## 2026-08-26 · 上下文被改写，召回去重表就该作废

目标：10 遗留 6（「召回块被压缩摘掉后不会重来，召回在长会话里单调衰减到零」，
条目自评「比一般遗留严重」）。

复核时发现条目只写了一半：`/clear` 把整段对话删掉，同样没清 `surfaced`——
而它比压缩更彻底。这一半此前没人登记过。

用户拍板「上下文被改写就全清」。落点是一条注入回调而不是 import：
`run_agent` 新增 `on_context_rewritten`，压缩真压成了之后调（暂缓与失败都不调），
装配层把它接成 `recall_state.surfaced.clear()`；`/compact` 与 `/clear` 走同一条通道。
loop 因此仍然完全不认识召回（与 `instructions` / `recall` 同款做法）。

改动：`src/pai/core/loop.py`、`src/pai/modes/assembly.py`（`Assembly` 多一个字段）、
`src/pai/modes/interactive.py`（`_run_turn` / `_handle_command` / `_manual_compact`
与 REPL、TUI 两条路的六个调用点）、`src/pai/modes/once.py`、
`tests/test_assembly.py`、`tests/test_loop.py`、`tests/test_interactive.py`。

红：装配层那条 `AttributeError: 'Assembly' object has no attribute
'on_context_rewritten'`——注意它前两个断言是通过的（注入过一次、再问就空），
也就是说这条测试先把 bug 本身钉住了才失败在缺口上；
loop 两条 `TypeError: run_agent() got an unexpected keyword argument`；
命令层三条同款 TypeError。
绿：`test_interactive + test_assembly + test_loop + test_modes` `195 passed`。

反向守卫三条（都会因为「顺手多清一次」而红）：没压成时一个字不通知、
`/status` 不通知、失败的 `/compact` 不通知。

## 2026-08-26 · 记忆三条：单篇上限、/memory reload、AGENTS.md

目标：召回单篇字符上限（2026-08-19 走读发现）、06 task 4（REPL 中途改 PAI.md
不生效）、D#43 复议（06 复盘质疑三）。

召回上限：`MAX_RECALL_FILES = 5` 只限篇数，正文整篇读进来——写一篇特别长的记忆，
召回一次就把它整个顶进上下文，而预算估算的尾部没算它。取 4000（`read_file` 的
`MAX_OUTPUT_CHARS`），理由写在常量旁：「一段进上下文的外部文本」两条路上该同价，
不是因为量过。

`/memory reload`：`_inject_instructions` 认出已有指令消息就直接返回，连 loader 都不调。
修法是丢掉那条消息（`loop.drop_instructions`，台账同步删），让下一轮的注入点重新读盘——
不在命令里立即重注入，注入点本来就在每轮开头，多一条路径就多一处要对齐的语义。
落盘侧天然自洽：`session.build_messages` 只留最后一条指令消息。

AGENTS.md：用户拍板改成读。`discover()` 的候选加一个名字，排在 `PAI.md` 之前
（后读到的更靠近对话）。这一条改完当场炸出两条测试的隔离缺口——
`test_conversation_persists_across_turns` 与 `test_slash_clear_keeps_system_and_drops_history`
不 chdir，此前捡不到仓库根的指令文件纯属侥幸（仓库没有 PAI.md），
现在会捡到 26KB 的 AGENTS.md。两条各加一行 `monkeypatch.chdir(tmp_path)`。

顺带清掉「分层记忆逐条对照」的第一条（注释准确度）：`discover` 的 docstring
写着「cwd 之下不收集——官方同款语义」，而官方那边是框架懒加载（发现了但
延迟到读该目录的文件时才注入），pai 是彻底不收集，比官方弱一档。改成说真话，
测试里抄了同一句错话的 docstring 一并订正。

改动：`src/pai/core/recall.py`、`src/pai/core/loop.py`、`src/pai/core/memory.py`、
`src/pai/modes/interactive.py`、`README.md`、`docs/dev/decisions.md`（D#43 追记）、
`tests/test_recall.py`、`tests/test_loop.py`、`tests/test_interactive.py`、
`tests/test_memory.py`。

红：召回上限 `ImportError: cannot import name 'MAX_RECALL_CHARS'`；
`drop_instructions` 两条 ImportError；`/memory reload` 两条（`assert 2 == 1`）；
AGENTS.md 三条（`assert [] == ['AGENTS.md']` 等）。
绿：`test_recall.py` `35 passed`、`test_interactive + test_memory + test_loop`
`181 passed`。

## 2026-08-26 · 三条各自独立的小账

目标：能力判定退化路径留痕（11 task 3）、`derive_replay` 误取指令当任务（32 遗留 1）、
`--resume` 不说「设置不跟着回来」（24 遗留）。

能力判定：三条退化路径此前完全同形。只给第三条留痕——未声明与参数脏是常态，
判定器自己炸了才是 bug；按 (工具, 判定器) 去重，往 stderr 喊一次
（形状照 `EventTrace` 落盘失败那条）。行为一字不变仍返回 False。

`derive_replay`：任务文本取「首条非空 user 消息」，而框架注入的指令消息与召回块
也是 user 角色且排在真任务前面。跳过这两种（认头部字符串，脆弱点照旧记在代码旁）；
全是框架消息时报错，不硬凑一个任务出来。

`--resume`：header 里存着录制时的 cwd（feature 24 的格式给了这个事实），
所以警告能说得具体——目录不同时点名它，目录相同时一个字不提。

改动：`src/pai/core/tools/__init__.py`、`src/pai/evals/replay.py`、
`src/pai/modes/interactive.py`、`tests/test_tools.py`、`tests/test_evals_replay.py`、
`tests/test_interactive.py`。

红：能力判定两条 `AttributeError: module 'pai.core.tools' has no attribute
'_CAP_WARNED'`；replay 两条（`Failed: DID NOT RAISE` / 取到了指令消息）；
resume 两条（`assert '设置' in …`、`assert False`）。
绿：`test_tools.py` `65 passed`、`test_evals_replay + test_evals_artifacts`
`9 passed`、`test_interactive.py` `58 passed`。

一处自证：resume 那条第一版实现没把「设置」二字写进文案，测试当场红了——
断言钉的是说了什么，不是「有没有多打几行字」。

## 2026-08-26 · 测试分层与宽度原语搬家

目标：15 遗留（e2e 把主套件拖慢，没有快循环）、12 T1（`display_width` 的家不对）。

分层：`./test.sh --fast` 跑 `-m "not llm and not e2e"`。标记由 conftest 按文件名
自动挂（`test_e2e_*.py`），不靠每个文件自己写 `pytestmark`——自觉的那种漏一个不会红，
而漏掉的后果正是快循环里混进一条起真 pty 的测试。
实测：全量 `1447 passed / 163.16s`，`--fast` `1416 passed, 1 skipped / 36.23s`，
4.5×（那 1 skipped 是 STATUS 数字对账，它本来就只在标准入口下跑）。

搬家：新增 `src/pai/tui/width.py`，十个 tui 模块改从它 import，`statusline`
反过来从 tui 拿并 re-export（不动九处调用点与十处测试 import——搬家是结构修正，
不是接口变更）。方向由一条 AST 守卫钉住：`pai/tui/*.py` 不许 import `pai.modes`。

这条的验收标准是用户单独给的：只该影响表示层的改动，验收是「解析后的值逐字相等」，
不是「测试还绿」。所以另跑了一次差分——拿 `git show HEAD:` 的旧实现与新模块
对同一批 4090 条样本（中英/全角/组合记号/ZWJ emoji/CSI/OSC/APC/制表符/随机串）
做 36810 次比对：

```
样本 4090 条 × display_width 1 次 + _truncate 8 档 = 36810 次比对
display_width 不一致 0 处；_truncate 不一致 0 处；_ESCAPES 正则逐字相等：True
```

改动：`test.sh`、`pyproject.toml`（markers）、`tests/conftest.py`、
`src/pai/tui/width.py`（新）、`src/pai/modes/statusline.py`、
`src/pai/tui/` 十个模块的 import、`knowledge/tui/terminal-width.md`（锚点）、
`tests/test_docs_consistency.py`。

红：守卫测试列出 16 处反向依赖（`altscreen.py: pai.modes.statusline →
['_ESCAPES', 'display_width']` 等）；e2e 标记两条 ImportError。
绿：`test_docs_consistency.py` `15 passed, 1 skipped`；
`test_statusline + 六个 tui 测试文件 + docs` `157 passed, 1 skipped`。

残留一处如实登记：`_preview`（工具参数预览）仍住在 `modes/statusline.py`，
被 statusline 与 `tui/dock.py` 共用。它不是宽度原语，塞进 `width.py` 是错的家；
守卫测试把它写成显式豁免（多一个名字就红），并单独登记进 TODO。

## 2026-08-26 · 交付：全量与销账

`./test.sh`（venv `~/.virtualenvs/pai`，Python 3.9.6）：

```
1447 passed, 3 deselected in 163.16s (0:02:43)
```

12 条真修 + 3 条对账核销全部在 [TODO](../../TODO.md) 原条目上销账（划掉 + 已修
说明 + 出处），STATUS 数字同步。

### 对账核销三条（早已修过、只是漏勾）

- `tui/driver.py` 一条测试都没有（12 复盘质疑五）→ feature 16 收尾
  （2026-08-19）已补 118 行，那次的条目里就写着「顺带给 driver.py 补了测试」，
  只是没回来划掉这条。
- `statusline._preview` 只取第一个参数值（05 task 8）→ 2026-08-18
  `fix/bash-timeout` 改成按主参数名取（`_PREVIEW_KEYS`），当时是被 bash 的
  `timeout` 参数当场引爆的。剩下的「多参数只显示一个字段」是刻意取舍。
- 注入进 messages 的消息不发事件 + `dock.set_queued` 显示旧数字 → 两半都由
  feature 18（2026-08-13）做掉：`_extend` 发 `SteeringInjected`（e2e 钉屏幕可见）、
  `_steering_source(after_drain=...)` 取完当场报剩余量。

### 跳过的条目与理由（按用户给的标准，不是漏了）

- 「等真实使用数据 / 等复现 / 等真实需要」：`reserve_tokens` 校准、
  25 遗留 3 的四个预算常量、pty e2e 挂死根因、feature 19 遗留 1/3、
  `remember` 端到端真实验证、E5 after_tool_call、MCP 重连/HTTP 传输、
  xdist 观察期。
- 「记录性 / spec 非目标」：环境运行器的洞、只读命令免提示集合、
  `decisionReason` 结构化审计、25 遗留 4/5/6、29 遗留 2、Windows 形态、
  哪些工具不该加超时。
- 「perf 要先有数字」：`realpath` 未缓存、`_highlight` 逐字符扫描、
  `session=None` 时的多余估算。
- `estimate_tokens` 收分段 content（R#19）：条目自己写着「接多模态前要处理」，
  pai 现在没有任何路径会产出分段 content——修了也没有真实红可构造，属造需求。
- 收割进程组的 pgid 重用（06 补漏三）：条目里写着的修法不能照做，
  这是本轮唯一一条「先看代码才发现条目错了」的。`reap_spawned` 的 docstring
  自己写着它存在的理由是 `sleep 300 &`——父 shell 立刻退、后台孙子还活着；
  而 `proc.poll() is not None` 恰恰在这时为真，照修法收紧就会跳过 killpg，
  把主用例漏掉。等于拿一个几乎不会发生的误杀，换一个每次都发生的泄漏。
  已把这段追记写进 TODO 原条目，条目维持开着但修法一栏作废。
