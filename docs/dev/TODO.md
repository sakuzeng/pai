# 待办清单

单一优先级清单。此前待办散在 8 条 devlog + STATUS + 评审报告里，记是记了但不可用——
本文件是唯一入口，每条注明出处，改完在对应出处补记再从这里划掉。

出处记法：`R#n` = docs/dev/reviews/2026-08-03-冷眼评审.md 第 n 条；
`R2#n` = docs/dev/reviews/2026-08-09-体系评审.md 第 n 条；
`R3#n` = docs/dev/reviews/2026-08-09-代码梳理.md 第 n 条；
`D#n` = decisions.md 第 n 条；`K <路径>` = knowledge/ 笔记；`日期` = devlog 里程碑或 archive/devlog-2026-08.md 对应条目。

---

## P0 · find_cut_point 动工前必须清掉

这些都会影响 find_cut_point 的设计前提，带着它们动工等于在流沙上盖楼。

- [x] ~~核实 thinking mode 到底默认开不开（R#3，严重）~~ 已完成 2026-08-03，见 D#33。
      裁决：思考确实默认开（devlog 断言正确，占输出 12.5%）；不回传 `reasoning_content`
      未触发文档所说的 400（测 3 次，含 181 token 重推理）；锚不受影响
      （「增长 − completion」恒为 +13~+22，与 reasoning 量无关）。
      我此前说的「reasoning_tokens 全为 0」是错的——只看了单个 session 的单条记录就推广。
- [ ] 监控：reasoning 相关的 400（D#33 衍生）
      文档白纸黑字说带 tools 不回传 `reasoning_content` 会 400，实测未复现——
      这是未解释的偏差，可能随模型/版本变化。一旦出现该 400，立即改为在
      `assistant_entry` 里带上 `reasoning_content`。
      注：机制未查明（为何丢弃后下轮 prompt 仍按含 reasoning 的量增长），
      只有实测事实没有解释，别编。
      追记 2026-08-24（dsh 交叉验证，K model-api/dsh-deepseek-wire.md）：
      dsh 真的回传且只在 tool-call 轮（官方 guides/thinking_mode.mdx 规则，
      平轮丢弃省 token）——一旦 400 出现，修法照这个形状，别平轮也带。
- [x] ~~并行工具调用已确认是真实场景（R#11 升级）
      探针中 DeepSeek 一次返回了 3 个并行 tool_calls；只回 1 条 tool 消息即触发 400
      （`insufficient tool messages following tool_calls message`）。
      pai 的 loop 逻辑上处理了（遍历所有 tc 各回一条），但无测试覆盖。
      这条从「值得改」升级：它有真实 400 复现路径。~~
      早在 2026-08-09 已完成，本条漏勾，2026-08-24 对账核销（同 R#8/R#9 两条
      的处理）：`tests/test_loop.py` 的 `test_parallel_tool_calls_each_get_a_reply`
      （N 条、同序、一一配对）与 `test_parallel_tool_calls_mixed_known_and_unknown`
      （未知工具混发也回填）当天就随 commit 8a0ccd7 进库了。
- [x] ~~重审 decisions 第 19 条（R#4）~~ 已完成 2026-08-03，结论见 D#19（推翻，原文保留）
      与 D#32（新的做法）。复核发现原论证错在两处，评审只指出了一处：
      ① 绝对预算切法下比例抵消不成立；② 偏差根本不均匀——实测短 tool 结果低估 4-5 倍
      （固定的每条约 25-30 token 框架开销占比暴涨），长消息只低估约 2%。
      → 衍生出下面这条实现要求。
- [x] ~~find_cut_point 用真实 usage 差值，不用字符估算（D#32）~~ 已完成
      2026-08-09（compaction 阶段 1 task 3）：`AnchorBook.entries` 保留锚点列表，
      `find_cut_point` 按相邻真实差值反推切点，绝不切在孤儿 tool_result 上；
      单锚（锚不足两个）如实返回 1（无可压），任务 6 的 e2e 撞出这条约束的实际影响
      （见 STATUS 缺陷 1）。
- [x] ~~锚重置后的读数盲区补进 STATUS 缺陷 1（R#7）~~ 已完成 2026-08-03：
      STATUS 缺陷 1 已改写（含"低估会让压缩后上下文看起来更小 → 误判成功 → 下轮爆窗口"
      这条具体后果），裁决见 D#34。
- [x] ~~实现熔断器时：失败计数只认压缩后首次真实 usage（D#34）~~ 已完成
      2026-08-09（compaction 阶段 1 task 5+6）：`CompactionState`/`verify_compaction`
      标记 `awaiting_verify`，等压缩后首次真实 `prompt_tokens` 才判成败；
      `MAX_COMPACT_FAILURES=3` 接进 loop 触发块，连续 3 次仍超线即 tripped，
      `test_breaker_stops_auto_compaction` 覆盖。
- [x] ~~给 loop 层锚簿记补测试（R#8）~~ 早在 2026-08-03 已完成，本条漏勾，
      2026-08-09 对账核销。tests/test_loop.py:238 `test_anchor_bookkeeping_is_exact`
      与 :272 反向钉死双计入；注入 off-by-one（`len(messages)-1`）实测会红。
      顺带修了 FakeClient 存引用的测试基建硬伤（deepcopy），见 archive/devlog-2026-08.md 2026-08-03 条目。
- [x] ~~冻结测试夹具里的工具 schema（R#9）~~ 早在 2026-08-03 已完成，本条漏勾，
      2026-08-09 对账核销。`FROZEN_TOOL_SCHEMAS`（test_compaction.py:450），
      改工具 docstring 实测不再假失败。

## P1 · 主线（阶段 1 压缩）—— 已全部完成 2026-08-09（compaction task 1-6，feat/compaction 分支）

- [x] ~~`find_cut_point`（在哪下刀）~~。约束落实：绝不在 tool 结果上切
      （`test_never_starts_kept_segment_with_tool_result`）。
- [x] ~~`summarize`（调模型摘要）~~。届时决定的三件事均已定：
      - 拍平 vs 原样发（D#12/D#16，R#12）——已实测裁决 D#37，默认 `style="flat"`，
        loop 调 `compact` 不传 style 用默认值；数据存 evidence/20260809-拍平vs原样发实测/
      - `serialize_conversation` 跳过 system 消息（R#16）——已实现，见函数调用处
      - 用真实摘要长度校准 `reserve_tokens=16384`——仍未做，见 STATUS 缺陷 3，
        单独登记在下面
- [x] ~~`compact`（把两者接起来），必须同时带熔断器（D#14）~~：
      `CompactionState`/`verify_compaction`/`MAX_COMPACT_FAILURES=3` 已实现并接进 loop。
- [x] ~~把 `should_compact` 真正接进 loop~~：`run_agent` 新增 `context_window`/`compaction`
      两个 keyword-only 参数（都给才启用；默认 `None` 时行为与接线前完全一致），
      触发块在 `estimated` 计算之后、`create` 调用之前；`once.run_once` 透传
      `context_window()`（读 `PAI_CONTEXT_WINDOW`，默认 1_000_000）与 `CompactionSettings()`。
- [x] ~~压缩会改写历史，必须让 anchor 失效~~：`compact()` 后调用方立即
      `anchors.reset()`（`AnchorBook.reset()`），不是把单个 `anchor` 置 `None`——
      阶段 1 的最终设计是保留锚点列表（D#32），reset 清空整个列表。
- [ ] reserve_tokens=16384 / keep_recent_tokens=20000 实测校准（登记自 STATUS 缺陷 3）：
      两个数字仍是从 pi 借来的经验值，接线阶段的 e2e 测试只验证了阈值公式本身
      （`tokens > window - reserve`）与切点算法的正确性，没有真实摘要长度/真实触发频率
      数据。需要 `--llm` 冒烟测试或生产使用积累后再回来定。

## P2 · 值得改

### R4 评审（2026-08-18 功能测试与分析）—— 新缺陷登记

出处统一是 [reviews/2026-08-17-功能测试与分析评审.md](reviews/2026-08-17-功能测试与分析评审.md)，
条目编号 `R4#n` 与该文件一致。逐条登记见评审文件本身（那边带 file:line、
触发路径与修法），本节只登记「已修」与「下一批要修的」，避免同一份清单抄两遍。

- [x] ~~R4#1 权限匹配器取错参数，deny 可被 JSON 键序绕过~~ 已修 2026-08-18
      （`fix/target-path-key-order`，小修通道）：`target_path` 改为按声明的参数名取，
      与同文件 `path_access_for` 对齐；两条反证测试钉死（content-first / path-last），
      1114 passed。
- [x] ~~R4#2 + R4#3 打字抑制期权限框被自动弃答 + 僵尸对话框错配答案（高，同根）：
      `ask_human` 的完成判据 `arbiter.current() is None` 分不清「答完了」与
      「被抑制暂藏」；INTERRUPT/EOF 退出不 `resolve()`，僵尸框接管键盘且答案
      进共享 FIFO 被下一个问题错配消费。feature 18 之后属交付即坏。~~
      已修 2026-08-18（`fix/dialog-suppression-abandon`，小修通道，方案 A）：
      结论跟着框走不进共享 FIFO（`Dialog.resolved`/`settle`、`arbiter.resolve`
      按身份移除、`app.cancel_dialog`）；等待逻辑抽成模块级
      `await_dialog_answer()` 才测得了；11 条测试 + 两轮精准注入反证，1122 passed。
- [x] ~~R4#4 + R4#5 配对不变量在异常路径上无保障（高，建议按专项一次补齐）：
      `{"self": …}` 参数击穿 `Tool.run` 的异常吸收边界（`t.run(**args)` 调用点本身
      能抛）；更一般地，assistant 落盘与 tool 回填之间任何异常都会留下结构非法
      的对话，而 REPL「对话留着」的兜底恰好把它固化成永久 400。~~
      已修 2026-08-18（`fix/tool-call-pairing-invariant`，小修通道）：
      门口挡 `self` 键 + 回填顺序改成「先进 messages 再发事件」（真实结果因此
      不再被渲染器异常连累）+ 工具段套 `try/finally` 兜底网（跑起来之前就炸的
      场景补占位结果，补完让异常继续往上走）。两条实测复现见 devlog。
- [x] ~~R4#6 工具输出未消毒直写终端 + `\t` 全链按 1 列（含 screen.py 模拟器）（高）：
      `grep --color`/`cat Makefile` 即触发；模拟器与真终端在此系统性分叉，
      是下一批「测试绿真机坏」的总闸。~~ 已修 2026-08-19
      （`fix/terminal-output-sanitize`）：新增 `tui/sanitize.py`，在入口消毒
      （工具结果四处 + `!命令` 输出）。没有去教每一层认识 tab——tab 宽度取决于
      当前列，而 `display_width(片段)` 拿不到列号，结构上算不对；入口展开之后
      下游全部自洽，模拟器与真终端也不再分叉。取舍：连 SGR 一起剥
      （pai 自己给工具输出上色，外来颜色会打架且未闭合会漏），代价是
      `grep --color=always` 不着色。边界钉了测试：只消毒给终端看的那一份，
      模型拿到的仍是原文。
- [x] ~~`display_width` 对 `\t` 仍返回 1（R4#6 的残余，低）：入口消毒之后
      正常路径上已经没有 tab 了，但这个函数单独拿出来用仍然是错的。
      要么让它对 `\t` 显式报错（fail loud，pi 在超宽行上就是这么选的），
      要么在文档里写明「调用方必须先消毒」。现在是第二种但没写。~~
      已写 2026-08-22（R4 低批）：docstring 明确「调用方必须先消毒」的契约、
      为什么结构上算不对（tab 宽度取决于当前列而片段拿不到列号）、
      并顺带点名 R4#19（组合字符）仍待修。
- [x] ~~R4#T6 e2e 至今无任何测试级超时（性价比最高的一条）：本次实修期间
      又复现一次挂死（pytest 跑满 7 分钟无输出无子进程，`pkill` 后重跑正常），
      与 2026-08-13 那条是同一个。挂死必须变红。~~ 已做 2026-08-18
      （`test/e2e-timeout`）：`tests/pai_test_timeout.py` 用 SIGALRM 给每条测试
      装 60s 兜底（不止 e2e），`@pytest.mark.timeout_seconds(n)` 可单独加预算；
      不引 pytest-timeout（一个依赖换十几行不划算）。诚实边界写在模块头：
      信号只送得进主线程，且卡在不可中断系统调用（STAT=`U`）时送不进去——
      实测那两次挂死父进程处于 `S`，兜得住。
      注意这治的是症状不是病：pty 父子退出竞态的根因仍未查（下条）。
- [ ] pty e2e 父子退出竞态的根因仍未查（从上条独立出来）。
      2026-08-18 追记：查过一轮，推断被自己的反证推翻，如实记下来。
      当时的推断是「子进程卡在往 pty 写（缓冲区满、父进程不读了），父进程卡在
      `waitpid`，两边互等」，三个观测看着能对上（父进程持有 `/dev/ptmx`、
      fake_provider 端口仍 LISTEN 而 teardown 顺序里 close 排在 `provider.stop()`
      前面、装上超时后那条被报成 ERROR 即抛在 teardown 里）。
      但实测站不住：构造「子进程猛写 pty 到缓冲区满」后，裸 `waitpid` 照样
      收得掉——`SIGKILL` 本就能杀掉阻塞在 pty 写上的进程。这条纠正是注入反证
      抓出来的（换回旧实现，我新写的「回归测试」不红）。
      顺手留下的是防御性硬化（`reap_pty_child` 有界等待 + 收割期间继续读），
      不是修复，注释与测试头部都已如实声明。
      下次复现时按 SIGALRM 抛出的堆栈查——那才是第一手证据。
- [x] ~~R4#26 Pillow 缺失时 `test_tui_record.py:87` 静默 skip：回放出图是所有
      e2e 的测量仪器，仪器缺席不该只是一条 skip。注意：原报告说「STATUS 数字
      漂了」是错的——对账口径是 `testscollected`（含 skip），1112 本就正确。~~
      已修 2026-08-22（R4 低批）：`importorskip` 换成显式 `pytest.fail`（带修法
      提示），Pillow 列进 pyproject `[dev]` 并已装进本机 venv——此前那条常驻的
      `1 skipped` 就是它，现在归零。
- [x] ~~R4#7 `expand_imports` 把正文任意 `@词` 当导入（中）：`@tool`、`@dataclass`、
      邮箱被替换成「(@xxx 未找到)」，每轮注入的指令消息被静默改写。~~
      已修 2026-08-19（`fix/import-syntax-scope`，小修通道）：加两条约束，各由一条
      注入反证钉住——`@` 必须在行首或空白之后（治邮箱），且目标要含 `/`、`.`
      或以 `~` 开头（治 `@tool` / `@property` / `@dataclass(frozen=True)`，
      后者此前连括号都被吃进「未找到」里）。判据取「含分隔符」而不是「文件存在」：
      后者会让写错路径的人连诊断都拿不到。
- [x] ~~R4#8 自动压缩的摘要请求是全链路唯一不设防的网络调用（中）：注释自认
      「全系统最贵的单次请求」却无 try，once 下整个进程崩；且失败不计入熔断，
      API 抖动时每轮重发最贵请求、熔断器永不跳。~~
      已修 2026-08-19（`fix/network-paths-guarded`）：触发块包 try，失败发
      `CompactionSkipped(reason="summarize_failed")` 并计入 `state.failures`，
      撞到 `MAX_COMPACT_FAILURES` 照常发 `BreakerTripped`；事件 reason 新增第三档。
- [x] ~~R4#9 全链路假设 tool_call id 非空唯一，无守卫（中）：id 空串时同批调用
      共享 `decisions[""]` 键互相覆盖，后判的权限决定套在所有调用头上。
      pai 经 `PAI_BASE_URL` 明确支持任意 OpenAI 兼容端点，而漏发流式 id 的实现真实存在。~~
      已修 2026-08-22（R4 低批）：守卫定在 `streaming.assemble` 出口——空 id 与
      同批重复 id 改写成 `call_synth_{index}`，正常 id 一个字符不碰（有测试钉死）；
      发回 provider 的历史两侧用的都是装配后的 id，配对自洽。
- [x] ~~R4#10 幻觉工具名走进权限链（中）：`before_tool_call` 排在存在性检查之前，
      调不存在的工具收到的是权限拒绝理由而非「未知工具」；交互模式下会弹框
      让真人给不存在的工具授权。动态探针实测。~~
      已修 2026-08-19（`fix/unknown-tool-before-gate`，小修通道）：存在性检查
      前移到权限判定之前，回填仍交给 `_run_tool`（配对不变量不受影响）。
      真跑探针复验：回填从一大段权限拒绝理由变成「错误：未知工具 no_such_tool」。
- [x] ~~R4#11 `/compact` 不在任何兜底之内（中）：已登记的「两条主循环都兜了」
      只包住 `_run_turn`，而 `_manual_compact` 是唯一碰网络的命令路径。~~
      已修 2026-08-19（同上分支）：兜底点定在 `_manual_compact` 内部，一处覆盖
      REPL 与 TUI 两个调用方；失败告诉用户原因并明说「历史未改动」。
- [x] ~~R4#12/13/14 TUI 输入与信号三条（中）：~~ 已修 2026-08-19，走完整流程，
      档案 [features/19](features/19-20260819-tui-input-and-signals/README.md)，
      拍板三问均选 A，升格 [D#70](decisions.md)。原文：
- [ ] feature 19 遗留 1：`ESC_SETTLE_SECONDS = 0.05` 在慢速 ssh / 串口上未验证
      （出处：19 复盘质疑一）。两包间隔超过 50ms 就退回原病（方向键变 `[A`），
      离线测不出，需手工清单。
- [x] ~~feature 19 遗留 2：粘贴自愈把可能只有半截的内容按成功吐出且无提示
      （出处：19 复盘质疑三），与「静默失败是 bug」相冲，考虑带一行提示~~
      已修 2026-08-24（feature 33）：自愈时解码器多吐一个 `paste_recovered`
      信号，app 收到给 dock 一行提示「粘贴结束符丢失…请检查是否完整」；
      editor 不认识该名字原样忽略，纯 REPL 路径不受影响。修前红。
- [ ] feature 19 遗留 3：`RuntimeError: reentrant call` 是按源码结构推的，
      从未真的触发、修完也没真跑验证（出处：19 复盘质疑四、D#70 诚实边界）。
- [ ] feature 19 遗留 4：列候选方案时带了倾向性措辞（把「只治一半」写成
      「制造已修好的错觉」），下次只写做到什么、做不到什么（出处：19 复盘质疑二）。
      原 R4#12/13/14 条目内容：DockRenderer 无 `_drawing` 重入门
      且信号处理器里写 stdout 可能抛 `RuntimeError: reentrant call`；
      busy 期 `poll(timeout=0)` 让 `flush()` 提前把拆包的方向键裁决成 Esc；
      KeyDecoder 的 pasting 态无出口（`PASTE_END` 丢失即键盘全死）。
- [x] ~~R4#T1/T2/T3 假绿与弱断言：4 处字面永真断言（两处 `assert … or True`、
      两处裸 `assert True`）、e2e 阶梯断言的析取项形同虚设、8 处
      `inspect.getsource` 断言只防误删不防改坏。~~
      T1 已修 2026-08-19（`test/kill-vacuous-assertions`，见对应里程碑）；
      T2+T3 已修 2026-08-22（feature 20 第 2/3 条）：阶梯断言改「屏幕缩进 ==
      源头文本缩进」严格相等（期望锚到 `answer` 与 `interactive.HELP`，
      浅阶梯注入反证钉死）；`getsource` 现存 6 处（T1/T5 清理时已消 2 处）
      裁决 3 换 3 留——trace 接线/队列 all 模式/viz 路由换行为断言
      （`trace=None` 突变旧绿新红），钉注释/证缺席/emoji lint 三处保留并在
      docstring 写明为什么换不掉。详见
      [features/20](features/20-20260819-e2e-for-seams/README.md)。
- [x] ~~R4#T5 `@tool` REGISTRY 泄漏的具体机制（补已登记条目）：
      `test_tools.py:617/636/652` 三个探针注册后不清理，目前靠字母序苟活。~~
      已修 2026-08-19（`test/kill-vacuous-assertions`）：conftest 加 autouse 的
      快照/复原 fixture，配一对测试钉住（前一条故意注册不清理、后一条断言
      看不见它）。第一版把快照拍在内置工具惰性注册之前，teardown 连内置一起
      清掉（症状是后续 `KeyError: 'bash'`），改成先 `get_tools()` 再拍快照。
- [ ] R4#15~R4#28 其余 14 条（低）：2026-08-22 R4 低批清掉 10 条——
      #15 dialog `/exit`（`await_dialog_answer` 认 quit 返回值撤框）、
      #17 TUI `!命令` 进历史（对齐 REPL：`!` 记 `/` 不记）、
      #18 退出先清 dock 再 print（e2e 拿 `s.raw` 喂虚拟屏钉「shell 拿回的屏幕」）、
      #20 resize 清选区（挪进 `app.handle_resize` 可离线测，头注已订正）、
      #21 `Interrupted(where="stream")` 文案改说真话（已计费、无 usage 不进账）、
      #22 loop 层 recall 兜底不再静默（发 `RecallFailed(reason="crashed")`）、
      #24 空闲 Ctrl+C 真清输入（e2e 钉屏幕）、#28 `atomic_write` 承诺收窄到
      进程死亡（掉电如实声明不保）、#23 已在 `awaiting_verify` 旁记档、
      #26 见上一条。剩 4 条 2026-08-22 由用户一轮拍板（问答存
      [features/21 README](features/21-20260822-input-line-overflow/README.md)
      「确认」节与本条）后同日修完，R4#15~28 全部清零：
      - [x] #16 数字直选 → 拍板「按框分流」：权限框保留首键直选（无自由文本
        语义），提问框改判整串（回车才裁决，越界数字当自由文本），与 REPL 一致；
      - [x] #19 组合字符宽度 → 拍板「最小修」：Mn/Me/Cf 计 0 列（纯标准库）。
        诚实边界：ZWJ emoji 序列仍算错（要 UAX#29 才对），有一条测试钉住这个
        已知错误，做完整 grapheme 分段时它该红然后改写；
      - [x] #25 busy 期按键 → 拍板「放行安全三键」：CYCLE_MODE/EXPAND/REDRAW
        在 busy 与对话框期都放行（抽 `cycle_mode()` 三处共用），EOF 刻意仍忽略
        （误触即退代价太大）；e2e 钉对话框期与 busy 期各切一次模式；
      - [x] #27 输入行超宽 → 拍板 A·折行，立档案交付，见
        [features/21](features/21-20260822-input-line-overflow/README.md)。
- [ ] R4#E1~E5 可扩展性改造（对照 dsh，用户 2026-08-17 提出「想像 dsh 一样可扩展」）。
      2026-08-22 清掉前三条（E2/E3 用户拍板「参照 CC」，走读沉淀
      K loop/cc-prompt-and-transcript.md）：
      - [x] E1「要加 X 去哪里」映射表 → docs/dev/扩展点.md（末节「现在还
        说不清的」即 E2~E5 的证据）；顺带把「新模块只依赖 events 与注入回调、
        绝不 import loop 内部」采纳进 AGENTS「架构约束」。
      - [x] E2 system prompt 从常量变装配 → 交付见
        [features/22](features/22-20260822-system-prompt-assembly/README.md)。
        追记：CC 的 env 段（cwd/日期/模型进 prompt）刻意未抄，skills 阶段
        加段时一并评估。
      - [x] E3「模型可见即已记录」不变量 → 交付见
        [features/23](features/23-20260822-model-visible-is-recorded/README.md)。
      - [x] E4 ToolSource seam → 最小形态兑现 2026-08-23（feature 29）：
        工具第二来源经 `core/mcp.bridge_tools` 在装配层 setdefault 并表，
        「schema 与代码同源」的改述由 D#74 完成。正式 ToolSource 协议刻意
        未立——第二来源只此一家，协议等第三来源出现再抽（不预防性拆分，
        dsh 同款戒律）。
      仍开着的一条：E5 after_tool_call 对称缝
      （等 microcompact 这类真实需求出现再开）。
      点名不抄：Cordis 全插件化 / profile 分层 / waterfall 事件总线。
- [x] ~~feature 23 遗留：收口只覆盖 loop——`_run_shell` 与 `/clear` 重建仍有
      自己的成对 append。~~ 已关闭 2026-08-22（feature 24 T4b）：`_run_shell`
      改走 `loop._record`，`/clear` 同步裁台账，REPL 侧不再有裸成对 append。
- [ ] R4#A1~A10 跨项目吸收 10 条（A1 已于 2026-08-22 交付，见
      [features/24](features/24-20260822-session-format-and-resume/README.md)）：
      ~~会话格式一次到位改造 → 线性 `--resume`（高）~~、
      成本核算（pi 费率结构 + waku「台账只存 token、金额读时算」，高）、
      记忆双时间轴 `valid_at`/`invalid_at`（graphiti，成本近零，高）、
      skills 照 pi 最小形态（高，阶段 6）等，完整表见评审文件第四节。
      注：hermes/waku/graphiti/zep 不在 D#69 参照制度内，第一次被 feature
      引用时须在 decisions 补一条「参照源定级」。


### feature 32（evals）遗留 —— 2026-08-24

- [x] ~~任务文本启发式取「首条非空 user 消息」（32 遗留 1）：录制会话若带
      指令消息（PAI.md 注入），`derive_replay` 会误取指令当任务。修法是识别
      指令消息头部（与 26 复盘「指令消息识别靠头部字符串」同一处脆弱点）。~~
      已修 2026-08-26（feature 35，修法即条目既定）：跳过框架注入的两种 user
      消息——指令消息（`INSTRUCTION_HEADER` 前缀）与召回块（`<system-reminder>`
      前缀），两者都排在真任务前面，所以「首条非空」必然取到它们。
      全是框架消息时报错而不是硬凑一个任务出来。脆弱点照旧记在代码旁：
      消息没有身份字段，只能看内容开头，改哪个都该顺手改另一个。
- [ ] 回放判分无声明式「期望产物」描述（32 遗留 2）：逐夹具手写断言，
      夹具多了会重复。等第二三份夹具看形状再抽，别预防性设计。
- [ ] 评测单场景（32 遗留 3）：回放 1 夹具 + 真模型 1 任务。扩任务集与
      成功率统计（evals/README 旧计划）等真实使用压力；下一份夹具应录
      「带 allow 规则非 bypass」的回合（32 复盘质疑二：当前评测姿态绕开了
      权限层）。
- [ ] roadmap 阶段 7「反向对照 N 场景」勾选项仍空（32 遗留 4）：本轮两次
      真跑（铸造 + 真模型评测）不构成体系化对照，如实留空；扩任务集时一并。

### feature 33（usability-hardening）遗留 —— 2026-08-24

- [ ] 「首启提示 bash 边界洞」半边刻意未做（33 遗留 1）：/permissions +
      README 双通道已覆盖，一次性 banner 读过即丢——但该判断无用户数据
      支撑，dogfooding 或有第二个用户后重看（出处：33 复盘质疑一）。
- [ ] 配置键接线对账测试待评估（33 遗留 2）：settings「被声称的键」与
      装配层「实际消费的键」机器对账，`additionalDirectories` 那类
      「文档声称、实际没接」的静默失效就会自己红——难点是「声称」的
      机器可判口径（出处：33 复盘「下次怎么做更好」；与 TurnStart 死事件
      同族：登记表校验不了「真有人消费」）。

### 功能测试 20260824（独立功能测试，只查不改；全部低级）

- [x] ~~低·MCP timeout 非法值静默回默认（出处：功能测试 20260824）~~
      已修 2026-08-24（!小修，`fix/mcp-timeout-warn-and-cjk-tool-name`）：
      `_parse_servers_section` 比照同函数其余坏配置加 warn（回默认语义不变，
      CC 同款「防秒毫秒手滑」保留）；`test_load_mcp_servers_skips_bad_entries_with_warn`
      改为断言该 warn（修前红）。原发现：`"timeout": 5` 无任何提示按 60s 跑，
      与「静默失败是 bug」相冲。
- [x] ~~低·纯非 ASCII 的 MCP 工具名归一化后信息量归零且必撞名（出处：功能测试
      20260824）~~ 已修 2026-08-24（同上分支）：`public_tool_name` 在
      「raw 归一化后全为 `_`」时同样挂 hash 后缀（原来只兜超长）；ASCII 名
      与撞名 fail loud 路径不受影响（既有测试钉着）。修前实测 `中文工具` 与
      `另个名字` 都归一成 `mcp__srv______`、第二个被跳过；
      `test_public_name_all_non_ascii_gets_hash_not_collision` 钉住（修前红）。
- [x] ~~低·feature 07 档案状态行漂移（出处：功能测试 20260824）~~
      已修 2026-08-24（同上分支，纯文档）：状态行翻到「已交付」并注明
      漂移始末。原发现：README:3 停在「已拍板」而结果节已记录 7 task 交付，
      抽查 7 份档案里唯一没翻的。

### 优化检查 —— 2026-08-24（出处：优化检查 + feature 30 拍板问 3）

- [ ] pytest-xdist 观察期（30 问 3·A）：已进 dev 依赖，`./test.sh -n auto`
      可用、默认仍串行。试点数字：串行 171.57s → 并行 127.56s 全绿
      （10 核仅 1.35×，扩展性差的成因未查明——只记实测不编解释）。观察期
      两件事：跑一段确认 pty e2e 挂死旧账不被并行放大；查扩展性瓶颈
      （分发不均 / 夹具串行化 / 启动开销），查明后复议默认值。
      观察记录 2026-08-24：`-n auto` 1377 passed in 129.05s 全绿无挂死
      （同日串行 162.59s，1.26×；测试数从试点的 1350 涨到 1377，扩展比
      与试点的 1.35× 同量级）。观察点 +1，挂死零复现。
- [ ] 启动侧无肉（记录性结论，防将来想当然去「优化启动」）：2026-08-23 实测
      装配全环节 <1ms（scan_skills 20 包 0.7ms）、MCP 连接+发现 16ms/server、
      冷 import 0.47s（大头是解释器）。启动性能不立优化项，除非实测数字变了。
- [x] ~~interactive.py 装配巨石（1254 行，次大文件近两倍）：抽独立 assembly
      模块的候选已评估未做（改动面大风险中）；做时顺带把 MCP 关闭从 atexit
      改单出口 finally（29 遗留 7 联动）。等下次要在装配段加第三样东西时一起。~~
      已做 2026-08-24（[feature 31](features/31-20260824-assembly-convergence/README.md)，
      用户拍板 A 提前兑现时机）：共用序列抽进 `modes/assembly.py` 的
      `assemble`，once/interactive 只注入差异点；29 遗留 7 联动（见该条）。
      行为逐字不变：既有测试零改动全绿 + 功能测试 28 冒烟场景复跑全过。

### 29 复核发现 —— 2026-08-23（出处：29 复核；全部低级，无高中级）

- [x] ~~低·reader 线程对 unhashable id 会死（29 复核）~~ 已修 2026-08-23
      （!小修）：id 非 (int,str) 丢弃该行；`test_reader_survives_unhashable_id`
      钉住（bad-id-noise 夹具模式，修前红在超时）。
- [x] ~~低·`_send` 写管道不在锁内（29 复核，结构性伏笔）~~ 已修 2026-08-23
      （!小修）：独立 `_write_lock`（与配对查表的 `_lock` 分开防阻塞 reader），
      结构保险无行为变化、无红可构造（调度现串行），如实注明。
- [x] ~~低·spec 与实现不符——连接超时粒度（29 复核）~~ 已修 2026-08-23
      （!小修）：按实现改 spec 措辞（每请求各计）并留追记标注。
- [x] ~~低·connect_configured_servers 无兜底 finally（29 复核）~~ 已修
      2026-08-23（!小修）：BaseException 时先 close_all 再照样抛；
      `test_connect_helper_closes_sessions_on_unexpected_error` 钉住（修前红）。
- [x] ~~低·装配级测试覆盖缺口三处（29 复核）~~ 已补 2026-08-23（!小修）：
      repl 信任问答持久化 / once 坏 server 不崩 / 配置 timeout 全链，三条
      绿于到达（钉的是冒烟实证过的既有正确行为，如实标注）。
- [x] ~~低·非对象 inputSchema 原样透传（29 复核，记录性）：server 给
      `{"type":"string"}` 这类根级非对象 schema 会直达 API，可能被拒——
      CC 2.1.88 同样透传（拍平是 2.1.195 才加的）。等真撞到再挡~~
      已挡 2026-08-24（feature 33，「健全既有功能」指示提前解除「等真撞到」）：
      桥接层 warn + 跳过该工具（缺 schema 仍走兜底空对象；CC 的拍平不学，
      取更小动作）；400 从「调用时、离配错的 server 十万八千里」提前到装配期
      可见。测试钉四形态（string 根/非 dict/正常/缺失），修前红。

### feature 29（MCP client）遗留 —— 2026-08-23

- [ ] HTTP/SSE/ws 传输与 OAuth 未做（29 遗留 1，拍板问 1 范围）：v1 只有
      stdio。远程 server 需求出现时先做 streamable-http + 静态 header
      （dsh 形态），OAuth 等真实需要。
- [ ] resources/prompts/sampling/roots/elicitation/progress/list_changed
      未做（29 遗留 2，spec 非目标）：裁剪判据记档（「协议能力在自家架构里
      没有归属者时不到动工时候」）。prompts 的归属者是 / 命令表、resources
      是 @ 引用——那两个机制先出现，这条才解锁。list_changed 与「REPL 中途
      改 skill 不生效」（25 遗留 2）同族，做时一起。
- [ ] 重连未做（29 遗留 3）：server 死了摘除、调用回错误串（pi 式）。
      真需要时抄 dsh 的三件套（uptime 重置预算 / 等关闭再退避否则彻底停 /
      故障期不注销工具），设计已存 K mcp/dsh-mcp.md。
- [ ] 大输出落盘与非文本内容未做（29 遗留 4）：超 100k 字符截断留提示、
      image/audio 占位符——CC 的落盘+类型签名形态等真实撞到再做。
      输出预算的字符换算对中文偏大（复盘质疑三），校准与 25 遗留 3 同批。
- [ ] `${VAR}` 环境变量展开与 `.mcp.json` 生态兼容未做（29 遗留 5）：
      检入仓库的项目级配置想引 secret 时需要前者；想直接挂 CC 生态配置时
      需要后者（settings 加一个「外部 mcp 配置文件路径」项即可）。
- [x] ~~连接失败不告知模型（29 遗留 6）：v1 只 warn 给用户——模型可能反复试
      不存在的工具名。反向对照 P3 证明 CC 文档的「经 ToolSearch 告知」实测
      未复现，无可抄的已验证行为，pai 要自己定形态（最小：装配期把失败
      server 列进 system prompt 一行）。~~ 已修 2026-08-24
      （`fix/error-surfaces-batch`，!小修）：`connect_configured_servers` 第三
      返回值带失败名单，assembly 折进 instructions 指令消息一段（形态偏离原
      设想的 system prompt 一行，理由：零管线新增 + 压缩重建后重注入告知不丢；
      未信任被跳过的刻意不算失败——策略拦截不是故障）。三条测试钉住
      （含「无失败一个字不提」的反向守卫），修前红。
- [x] ~~interactive 的 MCP 关闭挂 atexit 是取舍（29 遗留 7，记录性）：
      REPL/TUI 多出口不做大缩进；close 幂等 + 进程生命周期 = 会话生命周期。
      若 run_interactive 重构出单一出口，顺手改确定性关闭（复盘质疑一）。~~
      已改 2026-08-24（[feature 31](features/31-20260824-assembly-convergence/README.md)）：
      装配收敛后 run_interactive 有了单出口，TUI/REPL/异常三条路统一走
      finally 的 `mcp.close_all_mcp`；atexit 注册删除。
      `tests/test_assembly.py` 两条钉住（修前红：atexit 在函数返回时不触发）。
- [x] ~~dirty-stdout 丢弃不可见（29 遗留 8）：非 JSON 行静默丢、无计数——
      丢弃行数超阈值该 warn 一次（复盘质疑四）。~~ 已修 2026-08-24
      （!小修，可见性批清）：reader 计数、到阈值（10，未实测经验值）warn
      恰好一次并指路「日志改走 stderr」；warn 在 reader 线程发的取舍记在
      代码旁。`test_dirty_stdout_flood_warns_once` 钉住（修前红）。

### feature 25（skills）遗留 —— 2026-08-22

- [x] ~~项目级 skill 无信任门槛（25 遗留 1，D#72 顺带点名）~~ 已修 2026-08-23
      （[feature 28](features/28-20260823-skills-trust-and-write-guard/README.md)
      问 2·B，CC 式门禁）：首遇未信任项目 skills 交互模式真人确认（精确选中
      「信任」才持久化到项目身份目录，拒绝/跳过不持久化下次再问）；once 无人
      可问 → 不加载 + warn 指路。pty e2e 钉对话框全链。已知边界：信任是项目级
      一次性的，信任后新增 skill 不再触发确认（CC 同款弱点，记 28 devlog）。
- [ ] 会话中途增删改 skill 不生效（25 遗留 2）：扫描只在装配期跑一次（pi 同款），
      CC 的实时变更检测 / dsh 的 Chokidar watcher 都没抄。最小修法是
      `/skill reload` 或按轮重扫；注意重扫会动 system prompt 前缀（缓存代价）。
- [ ] 四个预算常量全部未实测校准（25 遗留 3）：目录每条 500 字符（取 dsh 默认）/
      总 8000 字节（取 CC 兜底值）、重挂单篇 2 万字符 / 总 10 万字符
      （CC 5k/25k token × 4 换算）。与 reserve_tokens 同类「借来的经验值」，
      来源已写在 `core/skills.py` 常量旁，等真实使用数据回来定。
      追记（25 复盘质疑二）：重挂总预算装不下时「整条丢弃」抄了 CC 连静默一起抄——
      与「静默失败是 bug」相冲，校准时顺带加一行「另有 N 个未重挂」提示。
- [ ] frontmatter 扩展字段与参数替换未做（25 遗留 4，spec 非目标）：
      `allowed-tools` / `model` / `context: fork` / `hooks` / `paths` /
      `$ARGUMENTS`。`paths` 条件加载与 memory 那条「`.claude/rules/` 式
      paths 条件加载」（06 遗留）是同一机制，做时一起。
- [ ] 嵌套递归发现与外部目录兼容未做（25 遗留 5，spec 非目标）：pi 递归找
      `**/SKILL.md`、pi/CC 都能挂 `~/.claude/skills` 这类外部目录（settings
      配置项）。pai 只扫两级根的直接子项。等真实需要。
- [ ] `~/.pai/skills/` 整目录读免问是刻意代价（25 遗留 6，记录非待办）：
      用户级 skills 根进了 WorkingDirs.additional，read_file 读该目录下任何
      文件不再询问。不加就是 once 下用户级 skill 结构性不可用（spec 第 3 节）。
      追记 2026-08-23（feature 28 问 3·A）：用户级软链 skill 的真身根同样进
      additional（dotfiles 受信），免问读面随之扩到这些真身目录；写面已由
      危险写名单收口（28 问 1）。

### 25 复核发现 —— 2026-08-23（出处：25 复核）

- [x] ~~高·验收标准 4 的锚测试是假绿（25 复核）~~ 已修 2026-08-23
      （[feature 26](features/26-20260823-reattach-test-fix/README.md)）：
      场景改三锚让切点真摘掉 skill 的 tool_result + 双向断言（token 不在
      tool 消息、在指令消息），注入反证掐断重挂必红（红的输出在 26 devlog）。
- [x] ~~高·子目录启动时项目级 skill 目录与边界脱节（25 复核）~~ 已修
      2026-08-23（[feature 27](features/27-20260823-skill-boundary-exempt/README.md)，
      D#73）：skill 工具退出路径边界，`Tool.boundary_exempt` 显式豁免位兜底
      放行（deny/危险写/用户 ask 规则照常在前，测试钉优先级），「未知名回
      cwd」绕法连带删除。子目录场景进回归测试，注入反证去掉豁免即红。
- [ ] skills 发现升级为 cwd→git 根沿途多根链（27 拍板顺带，出处：25 复核
      的 CC 源码研究）：CC 的 `getProjectDirsUpToHome` 收集沿途每层
      `.claude/skills`，子目录里的 skills 也生效——顺带解掉 25 evidence
      「skill 放子目录不生效」的静默失效。pai 现在是 git 根单根（dsh 同款）。
      用户裁决：登记不并进 27，等真实需要再立案。
- [x] ~~中·软链 skill 结构性不可用（25 复核）~~ 全部收掉：正文半边
      feature 27 顺带修（豁免位）；附属文件半边 feature 28 问 3·A 修——
      用户级软链真身根进 additional（dotfiles 受信），项目级刻意不解析
      （仓库可塞指向 `~/.ssh` 的恶意软链，理由记 28 档案），后者是刻意代价
      非待办。
- [x] ~~中·acceptEdits 模式下 `~/.pai/skills/` 可免问写入（25 复核）~~ 已修
      2026-08-23（[feature 28](features/28-20260823-skills-trust-and-write-guard/README.md)
      问 1·A）：`.pai/skills` 路径段进 `_DANGEROUS_ANYWHERE`（用户级与项目级
      一个模式全覆盖），写 skills 永远 ask、bypass 免疫；注入反证去掉名单项
      即红。已知豁口如实记 28 devlog：bash readlink 真身直写可绕（bash 不参与
      边界的既有拍板，与 `.git/hooks` 同类）。
- [x] ~~低·「disable-model-invocation 的 skill /skill 可调」无测试（25 复核）~~
      已补 2026-08-23（feature 26 顺带）：
      `test_repl_skill_can_invoke_disable_model_invocation`，含注入反证。
- [x] ~~低·skill.py 模块注释「装配期写、执行期只读」对追踪器不成立（25 复核）~~
      已修 2026-08-23（!小修）：`LoadedSkills.record` 加锁 + 注释改说真话；
      竞争红可确定性构造（`setswitchinterval(1e-6)` 下 8 线程无锁 5/5 丢增量
      约 35%），测试 `test_loaded_skills_record_is_thread_safe` 钉住。
- [x] ~~低·全部 skill 均 disable-model-invocation 时 once 仍摆 skill 工具
      （25 复核）~~ 已修 2026-08-23（!小修）：once/interactive 收工具的条件从
      「skills 全空」改为「无 model_invocable」；/skill 用户通道不受影响
      （测试钉住通道仍可跑轮次）。

### feature 21（输入行折行）遗留 —— 2026-08-22

- [x] ~~折行续排行上的鼠标点击定位不对（21 遗留 1）：`app._input_click` 按
      「显示行=逻辑行」换算字符下标，折行后点第二段会定位到错误字符。
      修法：把 `_wrap_spans` 的区间暴露给 `point_at`。键盘选字不受影响~~
      已修 2026-08-24（feature 33）：按预记修法——`_display_rows` 与 render
      共用一套折行几何，新 `point_at_display(row, col, width)` 按显示行换算；
      顺带修掉第二处病：旧调用点统一按 prompt 宽减列，续行前缀不等宽时也错，
      前缀宽现在按目标行所属逻辑行取。中文宽字符/续行前缀各有测试，修前红。
- [x] ~~↑↓ 在折行长行上仍翻历史，不进显示行（21 遗留 2）：CC 是移动光标、
      光标在首行才翻历史。现状与单行时代一致（非回归），但长行编辑体验受限，
      且「想上移光标却换出历史」可能比遗留 1 更早被撞到~~
      已修 2026-08-24（feature 33，CC 同款语义）：↑/↓ 先在显示行间移动光标
      （目标列取当前视觉列；非末段行尾收在段末前一字符——那个位置视觉上属于
      下一行），到首/末显示行才翻历史；没渲染过（纯 REPL 注入路径）不知宽度，
      退回旧行为。不做跨多次移动的 goal-column 记忆（体验优化非正确性）。
- [x] ~~dock 高于终端行数（粘几千字符的输入）时 `_repaint` 行为未测（21 遗留 3）：
      pi 对超宽 fail-loud，pai 对超高什么都没有。真实使用罕见，但没测过要说出来~~
      已修 2026-08-24（feature 33）：实况是 `\r\n` 逐行写超过屏高会让终端
      滚动、随后相对上移指到 scrollback 里——整块漂移且擦不掉。DockRenderer
      收 rows 提供者，钳到「终端高度 - 1」保尾部（输入行与状态行在底部）；
      不传不钳（组件测试与 alt 屏不需要）。两条测试钉住，修前红。

### 第三参照源 deepseek-harness 接进流程 —— 2026-08-13（D#69 衍生）

- [x] roadmap 剩余阶段的「参照」栏与「前置精读」清单补 dsh 条目（出处：D#69）。
      全部补齐：skills 半段 2026-08-22（见下）；mcp_client 半段 2026-08-23
      （feature 29 动工日，「dsh api-gateway」线索实测是空的、已按实况改正）；
      evals 半段 2026-08-24（阶段 7 动工日：参照栏补 dsh testing + llm-replay，
      前置精读两篇落 K evals/，原文如下）。
      至少三处对得上：~~阶段 6 skills → dsh `docs/capability-seams.zh.md` 与 `tool-catalog.zh.md`~~
      已补 2026-08-22（feature 25 动工日：参照栏三家全补，笔记
      K skills/dsh-skills.md，另发现 R4#A4 引的 "skills.zh.md" 实际路径是
      `docs/subsystems/skills.zh.md`）；剩两处照旧动工那天再补：
      mcp_client 子阶段 → dsh `docs/api-gateway.zh.md`、`subsystems/`
      （roadmap 阶段 6 已留了指针行）；evals 阶段 → dsh `docs/testing.zh.md`。
- [x] ~~第一篇 `dsh-` 笔记写哪块，动工前定（出处：D#69）~~ 已完成 2026-08-13：
      写了 K [loop/dsh-loop.md](../../knowledge/loop/dsh-loop.md)（loop 与队列，
      补齐 `pi-loop.md` / `cc-loop.md` 的第三家）。顺带更正了 `pi-loop.md` 一处量词错误
      （「loop 内部问队列是 pi 独有的」→ dsh 也是，真正独有的是 CC）。
- [x] ~~★ pai 该不该给「干完再看」一个手势 —— D#68 追记衍生的新问题（出处：D#68 追记、
      K [loop/dsh-loop.md](../../knowledge/loop/dsh-loop.md) 第 7 节）。
      D#68 拒绝造这个手势的论据之一是「没有参照实现」，dsh 证伪了这一条
      （回车默认 queue、Cmd/Ctrl+Enter 才插话、默认值还可配）。
      但别直接抄：CC 与 dsh 给的是相反的默认值，各自的前提 pai 都不具备
      （CC 有 Esc 独立打断路径、dsh 有两个手势 + 可配默认）。
      要答的是三问：pai 要不要第二个手势 / 默认值放哪一档 / 要不要做成设置项。
      结论无论哪一边，都得回来改 D#68 而不是新起一条。~~
      已裁决 2026-08-24（用户拍板「不做，等真实使用」，结论按规矩回写
      D#68 追记而非新起一条）：「无参照」论据确被 dsh 推翻，但「无使用
      证据」仍立——dogfooding 真撞到「想排队却被注入」再升格立案，届时
      三问拿着使用证据一起答。
- [x] ~~拿 dsh 反查 pai 的两条实测坑（出处：D#69 理由①，本条从下面那条 P2 独立出来）。
      `dsh-loop.md` 只读了 loop 与队列，没碰 DeepSeek 侧协议处理。~~
      已做 2026-08-24，与下面那条一并（同一件事的两条登记），结论见
      K [model-api/dsh-deepseek-wire.md](../../knowledge/model-api/dsh-deepseek-wire.md)。
- [x] ~~修 `knowledge/README.md` 缺失的「外部参照」小节（出处：2026-08-13 写 dsh-loop 时发现）。
      笔记模板（README:87-88）要求「本机绝对路径收进本页『外部参照』一节」，
      `loop/pi-loop.md` 等多篇的来源行也确实按此锚了过去——
      但 README 里根本没有这一节，那些锚点全是死链。
      两条出路：补上这一节，或改模板 + 改各篇来源行。
      注：`dsh-loop.md` 不受影响（dsh 是公开仓库，直接用 URL + commit hash，不需要本机路径）。~~
      已修 2026-08-24（走出路一·补小节）：编号以既有引用（2/4/5/6）反推回填
      不重排，1/3 从未被引用、原始清单未曾入库，如实标空缺保留编号。
- [x] ~~dsh 的 DeepSeek 侧实测坑值不值得反查（出处：D#69 理由①）。
      pai 有两条与文档不符的实测结论（D#33 `reasoning_content`、D#58 `include_usage` 空操作），
      dsh 作为同厂第一方实现必然也要处理——去它源码里检索这两个符号，
      看它怎么处理的。这是三家里唯一能做这种交叉验证的一家，别浪费。~~
      已反查 2026-08-24，值得：K [model-api/dsh-deepseek-wire.md](../../knowledge/model-api/dsh-deepseek-wire.md)——
      reasoning_content dsh 真回传但只在 tool-call 轮（官方 thinking_mode
      规则，D#33 监控条目的修法形状有出处了）；usage 两种块形状 dsh 也观察到
      并写了形状无关读取器，与 pai「每块都看」独立收敛（D#58 置信度升级）；
      顺手捡到 prompt_tokens 含缓存命中（上下文口径恰好对，将来成本核算必须拆开）。

### 工具调用超时 —— 2026-08-18（用户提问引出，三家参照对照）

pai 现状：`shell.py` 的 `TIMEOUT_SECONDS = 60` 硬编码、模型不能传、不可配；
`_wait` 轮询同时看中断标志与 deadline（与 dsh 的 `AbortSignal.any` 同构，
这一点 pai 做对了，CC 反而是两套通道）；超时回填部分输出（R3#3 已钉）；
杀整个进程组。loop / scheduler 层无任何 deadline，除 bash 外的工具无超时。

- [x] ~~超时文案要给模型出路（P0，纯 prompt 改动零风险）。现在只说
      「(命令超时 60s，命令与其整个进程组已被终止)」，没告诉模型下一步该干什么，
      模型大概率原样重试再撞一次。三家都在这个语境里给出路（dsh 写进工具描述、
      CC ripgrep 超时说「换更具体的路径或 pattern」）。pai 没有后台机制，
      可教穷人版：加长超时 / 拆分段 / `nohup … &> /tmp/x.log &` 后分次读。~~
      已做 2026-08-18（`fix/bash-timeout`）：文案给出可照着敲的一条 nohup 命令 +
      read_file 分次看日志。只挂在超时上，不挂在中断上——中断是用户主动喊停，
      给它出路等于劝模型绕过用户，有守卫测试钉死。
- [x] ~~60s 没有依据且明显偏短（P0）。CC 与 dsh 独立收敛到同一对数字
      120s / 600s——难得的强信号。60s 连一次完整 `pytest`（本仓库自己就要 106s）
      或 `npm install` 都扛不住。建议默认改 120s。这条是「给照抄来的常数建一条
      检查习惯」的又一个实例：60 是拍脑袋定的，从没被质疑过。~~
      已做 2026-08-18：默认改 120s，理由（两家独立收敛）写在常量旁边，
      并有一条测试守着「改它之前先读一遍理由」。
- [x] ~~让模型能传 `timeout`，并且真钳制（P1）。抄 dsh 的
      `clampTimeout(requested, default, max) = min(requested ?? def, max)`。
      明确不要抄 CC：它 schema 里写了 `max 600000` 却没有运行期钳制
      （`BashTool.tsx:860` 只有 `timeout || default`），而同仓库的 PowerShellTool
      有 `Math.min`——是疏漏不是设计，是个货真价实的洞。~~ 已做 2026-08-18
      （`fix/bash-timeout`）：`clamp_timeout` + `MAX_TIMEOUT_SECONDS=600`，负数显式报错
      不静默退默认值。用 `int` + `0` 哨兵而非 `Optional[int]`——`@tool` 的 schema
      生成器只认 str/int/float/bool，改它是动「schema 与代码同源」那块基石。
      连带修掉 R4#1 的两个潜伏点：加这个参数当场引爆 `statusline._preview` /
      `dock._preview` 的「取第一个值」（模型把 timeout 排前面时状态行显示光秃秃的
      `300` 而非命令）；改成按主参数名取，两份重复也顺手收成一处。
- [x] ~~超时可配置（P1）：CC 走 env var，dsh 走 settings section。
      pai 已有 `core/settings.py`，走 settings 与现有架构更一致。~~
      已做 2026-08-24（!小修，`feat/bash-timeout-setting`，方向即条目既定）：
      settings `bash.timeoutSeconds`（1..600，非法值 warn 回默认、bool 单独挡），
      assembly 装配期经 `shell.set_default_timeout` 注入、未配置显式清空；
      模型自传 timeout 的钳制语义不变。诚实边界记代码旁：工具 schema 描述
      文案生成于 import 期，配置后「默认 120s」字样不跟着变（只影响提示）。
      8 条新测试（解析 6 + 装配接线含清空 1 + 既有守卫不动），修前红在 import。
- [ ] ★ MCP 阶段必须回来处理统一超时（P2，阶段 7 前置）。
      「只有 bash 有超时」目前不是硬伤（CC 与 pi 也这样，2:1），
      但网络调用会让它变成硬伤：接了 MCP 的两家都给 MCP 单独设了超时
      （CC `MCP_TOOL_TIMEOUT`、dsh `toolCallTimeoutMs=60_000`）。
      pai 的 loop 一旦挂住就回不来——已实测：`read_file` 读一个无写端的 FIFO
      永久阻塞，置中断标志也没用（工具内部没人查它），只能 kill 进程。
      真要做统一层就抄 dsh 的形状，两条必须一起抄：① 声明式 + 协作式
      （工具声明预算、执行器只置位取消信号、`await` 到底不 race，
      避免「结果返回了但活还在跑」）；② 超时元数据绝不给模型看
      （dsh 在 `ToolDefinition.timeoutMs` 注释里钉死 `NEVER sent to the model`）。
- [ ] 哪些工具不该加超时，判据是「这个超时能不能真的终止工作」（记录，非待办）。
      dsh 明确不给 read/write/edit 设超时（`docs/subsystems/filesystem.zh.md:274`）：
      本地系统调用至多尽力中止，超时无法迫使进行中的 `fsync`/`rename` 停下，
      加了就是「一条强制不了的截止时间」。这条判据直接适用于 pai。
- [x] ~~超时路径丢了 exit code（小，dsh「正交事实独立上报」只踩到一半）：
      一个命令可能 trap 了 SIGTERM 后以 0 退出、同时确实超了时。
      dsh 为此把 `timedOut`/`aborted`/`signal`/`exitCode` 做成四个独立字段。
      pai 的改动很小：超时文案里带上 `proc.returncode`。~~ 已修 2026-08-24
      （!小修，可见性批清）：超时文案末尾追加「(进程退出码：N)」——
      returncode 在 kill 后的 communicate 才有值，只能在收集后拼接。
      `test_timeout_message_reports_exit_code` 钉住（修前红）。

### pty e2e 偶发挂死（不报错、不超时、就是不回来）—— 2026-08-13

- [ ] `./test.sh` 偶发永久挂起，进程留在那儿不退（出处：2026-08-13 写 dsh 笔记时连撞两次）。
      现象：同一天同一份代码，四次 `./test.sh` 里两次正常（~107s，1112 passed）、
      两次永不返回（一次挂了 1 小时，一次 10 分钟，都是人工 `kill -9` 才停）。
      两次的进程签名完全一致：父 pytest 阻塞着持有 `/dev/ptmx`，
      子进程已是僵尸（`ps` STAT = `?Es`），另外还占着一个 LISTEN 的本地端口
      （fake_provider 的 HTTP server）。两次端口不同，所以不是端口冲突。
      判据：docs-only 改动也能复现 → 与被测代码无关，是 pty e2e 自身的竞态
      （父进程等 pty 上的东西，子进程已经先走了）。
      危害不是慢，是它不红也不超时 —— CI 里会表现成「一直在跑」，
      本地会表现成「我的改动把测试跑挂了」，两种都会把人引到错误的方向。
      下一步：给 pty e2e 加测试级超时（挂死必须变成红，不能变成等待），
      再查父子退出顺序。注：`timeout` 命令 macOS 默认没有，别在 test.sh 里直接用。

### 观测流的两个术语/死事件问题 —— 2026-08-13（feature 18 期间旁生）

- [x] ~~`TurnStart` 是个死事件：定义了、登记了、画了节点，但 `src/` 里没有一处发它
      （出处：features/18 T5 探针实测，事件序列只有 `AgentStart → AssistantMessage → AgentEnd`）。
      `events.py:26` 有 dataclass，`viz/collect.py:150` 声称它住在 `core/loop.py`，
      `viz/index.html:302` 配了节点映射——而 `loop.py` 从不发。
      于是 viz 时间线上那一格永远不会亮，页面上「这个环节住哪」还指着一个不存在的发射点。
      `EVENT_SRC` 的防漂移测试挡不住这类：它只校验「键集合 == 事件类名集合」，
      校验不了「这个事件真有人发」。两条出路二选一：loop 每步真发一条（那就得先想清
      它与 `step` 的关系），或者删掉它并同步清 viz 映射。~~
      已按出路二删除 2026-08-24（!小修）：定义以来从未有人发、从未有人缺它，
      「每步真发」是没有消费方的预防性建设（真需要 per-step 分组时 viz 时间线
      已靠配对做到了）；类/Union/EVENT_SRC/index.html 映射同步清，六处借它当
      样本的测试换用真实事件。真发红过一次：Union 残留引用 import 即炸。
- [x] ~~术语两套并存：事件叫 `TurnStart`，字段却是 `step`（同上出处）。
      按 K [loop/cc-loop.md](../../knowledge/loop/cc-loop.md) 第二节的对照表，
      pai 的内部一步就叫 step（pi/CC 才叫 turn）。名字与字段各说一套，
      读事件流的人要先猜一次。与上一条一起处理。~~
      随上条删除一并消失 2026-08-24（矛盾的载体没了）。

### feature 18（steering 输入源）交付遗留 —— 2026-08-13

- [x] ~~「不要打断你，干完再看」这个意图现在无法表达（18 复盘质疑一）：
      问 2 拍板删掉了 followUp 队列，理由之一是「CC 的交互式用户也没有降级手势」——
      但那条理由对 pai 不成立：CC 用户不需要它是因为有 Esc（abort 当前工具、不杀整轮），
      而 pai 的 Ctrl+C 是进程级标志（D#40），一按就是整轮结束。
      pai 恰恰是更需要「排队」选项的那个实现。 暂不改（现在改就是凭空发明手势，
      无证据无参照）；真跑撞到就升格成 D#68 的复议。~~
      已随 D#68 复议收账 2026-08-24：用户拍板「不做，等真实使用」（结论在
      D#68 追记）。「现在无法表达」的事实不变，升格条件从「真跑撞到」明确为
      dogfooding 里撞到即立案。
- [ ] 轮末残余是「一条消息一轮」，代价没量过（18 复盘质疑二）：
      连打三句就是三次完整模型往返，CC 是一次。若发现常见，修法不是拼字符串，
      而是让 `run_agent` 收 `tasks: list[str]`（`AgentStart` 取第一条、`recall` 取拼接）。
- [x] ~~撞上 `MAX_QUEUE_ROUNDS`（8）时用户没有任何提示（18 复盘质疑三）：
      剩下的会留到下一轮结束再处理（不丢），但用户不知道自己有几条话被推迟了。
      数字 8 本身也是拍脑袋的——选错代价小，但静默是真问题。~~
      静默半边已修 2026-08-24（!小修，可见性批清）：撞上限且队列非空时
      经 commit 通道提示剩余条数与「下一轮结束时继续」；没撞上限一个字不提
      （反向守卫钉住）。数字 8 本身仍是拍脑袋的，维持原判（选错代价小）。
- [ ] `test_typing_while_busy_lands_in_the_queue` 是一条「不会失败的测试」
      （18 复盘「下次怎么做更好」）：它只断言两个答案都出现，
      在「排队等轮末」与「本轮就注入」两种语义下都绿，feature 18 改了语义它也没红。
      本次只改了它的 docstring。下次动到它时补反证或删掉。

### feature 18（steering 输入源）前置缺陷 —— 2026-08-13

- [x] ~~steering 队列在「模型这轮不调工具」时永久卡死~~ 2026-08-13 随 features/18 修复（取 (a) 两个出口；`test_steering_is_polled_when_model_gives_final_answer` + 两条 e2e 钉死，注入反证验过：拆掉出口②恰好这两条 e2e 变红）。原文（出处：
      [features/18 spec](features/18-20260813-steering-input/spec.md)「前置缺陷」节，
      由 K [loop/cc-message-queue.md](../../knowledge/loop/cc-message-queue.md)
      第六节撞出）：pai 把 pi 的双层 while 压成单层 `for` + `continue`
      （`loop.py:167`/`:284-288`），于是 `:283-289` 的「不发 tool_calls 就 return」
      在 `:352-355` 的 steering poll 之前。模型收尾那轮通常就不调工具，
      于是队列里的 steering 既不会被注入、也不会退化成 followUp，卡在那儿。
      pi 靠内层 while 的 `|| pendingMessages.length > 0` 挡住（agent-loop.ts:174），
      CC 靠 `next`/`later` 两档各有各的出口。
      这条必须在给 steering 接输入源之前修，随 feature 18 一并交付；
      方案 (a) 加分支检查 / (b) 改回双层循环（会动 `max_steps` 语义）见该 spec。

### loop 的健壮性缺口 —— 2026-08-13（读 pi/CC 真源码撞出来）

- [x] ~~被 token 上限截断的 assistant 消息，它的 tool_call 应当全部判失败~~
      已修 2026-08-24（`fix/error-surfaces-batch`，!小修）：动工第一步按 ⚠️
      先实测——DeepSeek 流式截断确实回 `finish_reason == "length"`（探针
      max_tokens=8，OpenAI 兼容口径）；`assemble` 本就保留该字段（feature 11
      就有，loop 一直没读），loop 在派发前检查，"length" 轮次一个不执行、
      每个 tool_call 回填 `TRUNCATED_RESULT`（配对不变量照常，文案给出路——
      与 bash 超时同一条规矩）。两条测试钉住（单调用不执行 + 并行批配对同序），
      修前红：截断轮次的 `touch` 真的落盘了。原文（出处：
      K [loop/pi-loop.md](../../knowledge/loop/pi-loop.md) 第五节，pi `agent-loop.ts:207-216`）：
      pi 在执行工具前先看 `message.stopReason`，为 `"length"` 时这条消息里的每个
      tool_call 直接判失败，一个都不执行。注释理由：*截断意味着每个 tool call 的
      arguments 都可能是残的，与其执行可能已损坏的调用，不如全部失败掉*。
      pai 没有这条：`core/streaming.py` 的 `assemble` 把 `arguments` 拼完就解析，
      解析失败才报错——一个恰好截在合法 JSON 边界上的残参数会被照常执行
      （例：本该是 `{"path": "src/pai/core/loop.py"}`，截在 `{"path": "src/pai/core"}`
      仍是合法 JSON）。失效方式是静默的：没有异常、没有日志，只有一次参数不对的工具调用。
      修法：`assemble` 保留 provider 的 finish_reason，loop 在派发前检查；
      每个被判失败的 tool_call 同样要回填一条结果（对齐 `loop.py:326-331` 那条
      「被拒绝的调用也必须回结果」不变量），否则下一轮 400。
      ⚠️ 动工第一步是实测：确认 DeepSeek 在 OpenAI 兼容协议下回的是
      `finish_reason == "length"`（未实测，别照 Anthropic 的字段名写）。

- [x] ~~注入进 messages 的消息不发事件，界面看不见（出处：
      K [loop/cc-loop.md](../../knowledge/loop/cc-loop.md) 第四节）：`_extend` 只
      append 进 `messages` 与 `session`，TUI 完全不知道有东西被注入；连带
      `dock.set_queued` 在 `run_agent` 内部 drain 之后没人更新，队列区一直显示旧数字。~~
      2026-08-26 对账核销（feature 35 复核）：两半都已由 feature 18 做掉
      （2026-08-13），本条漏勾——`_extend` 收 `on_event` 并在追加完成后发
      `SteeringInjected`（三个 steering 注入点都传了；`_inject_instructions` 那类
      系统注入刻意不发，它不是用户插话），e2e `test_the_injection_is_visible_on_screen`
      钉屏幕可见；剩余量由 `_steering_source(after_drain=...)` 在取完当场报给
      `dock.set_queued`（那段注释里连「为什么不挂在事件上」都写着）。

### feature 09（工作目录边界）遗留（2026-08-11 交付）

- [x] ~~配了 Bash allow 规则 = 该命令可越界，但没有任何提示（复盘质疑一，D#52）。
      洞不在默认路径上（bash 默认 ask），而在用户为了可用性必然要走的那条路上：
      once 下 bash 全被 deny，用户只能配白名单或开 bypass；一配
      `allow=["Bash(cat *)"]`，`cat ../../etc/passwd` 就畅通无阻。
      应在 `/permissions` 与首启明确提示这条。这是本功能的主要失效模式。~~
      提示已做 2026-08-24（feature 33）：`/permissions` 两个分支（有/无规则）
      都打出 bash 边界洞与危险写清单，README「权限与安全」节同款两句真话。
      「首启」原意的一次性 banner 刻意不做：一次性提示读过即丢，
      /permissions + 文档双通道随时可查，比 banner 更可复核（判断记档案 33）。
      洞本身是 D#52 既有拍板，不动。
- [x] ~~once 下用户配的 `defaultMode` 被静默忽略（复盘质疑二，D#53）。
      `dontAsk` 与「无真人」合流后，once 里配 `defaultMode: "default"` 与配 `dontAsk`
      毫无区别，且无提示。行为对但不该静默——应在检测到「配置的模式需要真人、
      而当前没有真人」时告警一次。~~
      已修 2026-08-24（feature 33）：RuleSet 记下 defaultMode 的来源文件，
      once 未显式传模式且 settings 配了非 dontAsk 模式时告警一次（含来源路径
      与出路：进交互模式或显式 --permission-mode）。行为不变只加声音——
      配置的 bypass 在 once 刻意仍不生效（旧 settings 静默提权比静默降权更糟）。
- [x] ~~危险路径清单硬编码且完全不可见（复盘质疑三）。用户看不到清单内容、不能增删，
      直到撞上为止。至少 `/permissions` 该列出来。~~
      可见半边已修 2026-08-24（feature 33）：`boundary.dangerous_writes_description()`
      人话版清单进 `/permissions`（与 is_dangerous_write 同源，测试互钉）+
      README「权限与安全」列全。「能不能增删」维持不可配（清单是安全底线，
      可配等于可绕，与 bypass 免疫同一逻辑）。
- [x] ~~`/permissions` 不显示当前权限模式~~ 已做 2026-08-11（feature 12 T5）。
- [x] ~~`/mode` 命令与 shift+tab 切换未做（拍板：留 TUI 阶段）~~ 已做 2026-08-11
      （feature 12 T5）：`PermissionModeState` 可变持有者（gate 每次判定现取，
      此前是装配期常量、运行时改不动）+ `MODE_CYCLE` 数据表。
      `dontAsk` 不在轮转环里（D#53：它与「无真人」是同一件事）。
- [ ] `realpath` 未缓存：每次判定都对路径与全部工作目录做双路径展开。
      CC 用 `memoize` 缓存工作目录的解析结果（注释说不缓存是每次检查 30 次 syscall）。
      工作目录集合是会话级不变量，值得缓存。（perf，需先有数字）
- [ ] 危险路径清单的 Windows 形态完全没考虑：`.bashrc` 这类写法在 Windows 上
      静默失效。pai 目标平台是 macOS/Linux，但「静默失效」本身该被记下来。
- [ ] `decisionReason` 结构化审计未做（spec 非目标）。pai 的 `Decision.reason`
      是人话字符串，机器读不了；CC 的 decisionReason 带 type（rule/mode/workingDir/
      safetyCheck），是审计与「为什么被拦」排查的最小单元。
- [ ] plan 模式未做（09 拍板：留 TUI 阶段连交互一起做）。
      2026-08-11 改判（feature 12 brainstorm 问 2，用户拍板）：不进 TUI 本轮，单独立项。
      理由与 09 当时的假设不同——读完 CC 源码后确认 plan 的实质是
      工具白名单 + ExitPlanMode 确认流，是权限层与工具层的活，不是交互层的活；
      TUI 只提供「模式能切」+「能弹对话框」两个能力。
      约束：feature 12 的模式轮转表必须写成数据而非 if 链，给 plan 留位，
      单独立项时加一行即可。见 [features/12 spec G5](features/12-20260811-tui/spec.md)。
- [ ] plan 的测试数字应写成下限而非精确值（复盘「下次怎么做更好」）。
      本次 7 个 task 有 4 个实际数与 plan 不符，每次都要回头改 STATUS 并被机器对账
      打红一次——把「计划的估算」当成「应该达到的事实」，制造了必然失败的对账。


### feature 07（权限）遗留（2026-08-10 交付，档案「遗留问题」逐条同步）

- [x] ~~首启无规则时应明确告知「一律放行」~~ —— 2026-08-11 由 feature 09 关闭：
      默认不再是全放行（D#51 把兜底改成工作目录边界函数），这条的前提已不成立。
- [x] ~~matcher 签名 3 参 → 4 参偏离了已拍板 spec，请用户复议（D#49）。仍未复议。
      spec 第 2 节钉的是 `(specifier, args, require_all)`，而 spec 第 4 节的路径锚点
      需要「规则来自哪个设置文件」这个信息，三参没有它的出口。已实现为
      `ctx: MatchContext`。要么认可并订正 spec，要么换实现。~~
      已复议 2026-08-24（用户拍板追认 4 参，问答存 D#49 追记）：spec 第 2 节
      加追记（原文不改），零代码变化。
- [x] ~~符号链接双路径检查未做~~ —— 2026-08-11 由 feature 09 Task 4 关闭，
      `test_symlink_double_check_is_not_implemented` 已按设计变红并改写为
      `test_symlink_cannot_bypass_deny`。
- [ ] 环境运行器的洞（feature 07 task 3）：`Bash(devbox run *)` 会放行
      `devbox run rm -rf .`。官方承认的同款取舍，已写成测试摆在明面上。
      剥离它们更糟（等于承认借壳能跑任意命令），所以这条更像「记录」而非「待修」。
- [ ] bash 命令拆分是正则不是真 shell 解析：引号里的分隔符（`echo "a && b"`）会被误拆。
      实测方向是更保守（allow 更难通过、deny 更容易命中），所以不是安全洞，
      但会误伤正常命令。要真解决得引入 shell 词法分析。
- [ ] 只读命令内置免提示集合未做（spec 明确不做）。它是 D#47 那条「默认 ask 会烦到
      没法用」的直接原因——有了它，白名单模式才具备可用性。
- [ ] 按参数语义挂匹配器可能比按工具挂更对（复盘质疑二）。`path_matcher` 真正依赖的是
      「这个参数是一条路径」，不是「这个工具叫 read_file」。加第五个碰路径的工具时忘了
      `matcher_for` 就静默退回朴素 fnmatch。加第五个 fs 类工具时重估，现在不动。
- [ ] `strip_wrappers` 的「带标志就不剥」是推的不是抄的（复盘质疑三）。
      `timeout -s KILL 30 npm test` 会判不匹配（偏保守，安全方向对），
      但用户会遇到「规则明明写了却不放行」的困惑。需要官方语义佐证或补文档。


### 压缩链路的可验证性（2026-08-10 用户实测暴露）

用户按测试清单跑 `PAI_CONTEXT_WINDOW=3000 pai "读一下 PAI.md，再说说你是谁"`，
输出里只有两次「🗜️ 锚点不足（<2）…暂缓压缩」，从未出现 `🗜️ 压缩：切于 N`——
即压缩链路（含 D#42 的压缩后重注入）在真实使用中一次都没被走到过。

- [x] ~~没有可负担的办法在真实使用中触发一次压缩：`PAI_CONTEXT_WINDOW` 能让
      ①（should_compact）永远成立，但 `keep_recent_tokens`（默认 20000）没有任何
      环境变量能改——小对话里相邻锚差值只有几百，②（find_cut_point）永远不成立。
      修法：暴露 `PAI_KEEP_RECENT_TOKENS`（几行，与 `context_window()` 同款）。~~
      已做 2026-08-26（feature 35，`fix/35-todo-backlog-batch-2`，方向即条目既定）：
      `config.keep_recent_tokens()` 与 `context_window()` 同款——不配回
      `CompactionSettings` 的默认值，非整数与非正数在门口 `sys.exit` 说清是哪个 env
      （0 会让切点落在最新锚上，把整段历史一次压光）。once 与 REPL 两处装配
      各有一条接线测试（捕获传给 `run_agent` 的 `compaction`），漏传不再是静默的。
- [x] ~~REPL 的 `/compact` 在真实会话里几乎永远不可用（同一道坎）：手动敲
      `/compact` 大概率只得到「锚点不足」或「无可压」，让人以为坏了。
      至少该让提示语可操作（告诉用户还差多少 token 才切得动）。~~
      已做 2026-08-26（feature 35）：新增纯函数
      `compaction.keep_recent_shortfall(anchors, keep_recent)`（最新锚减最早锚的
      真实差值 vs 门槛；锚不足两个时如实返回整个门槛，返回 0 会被读成「够了」），
      `/compact` 的「无可压」分支改说「还差约 N token（门槛 M）」并点名
      `PAI_KEEP_RECENT_TOKENS` 这条出路。反向守卫钉住：锚不足两个时一个「还差」
      都不许说——算不出来就别装作算得出。
- [x] ~~这是「测试全绿但真实不可用」的又一例，值得记进方法论：离线测试之所以全绿，
      是因为测试里直接传了 `CompactionSettings(keep_recent_tokens=1)` 把这道坎绕过去了。
      够格升格成 knowledge/concepts 的一条方法论笔记。~~
      已回流 2026-08-26（feature 38），但落点与原设想不同：写进
      [K engineering/instruments-lie.md](../../knowledge/engineering/instruments-lie.md)
      的第五种骗法——「仪器让被测路径结构上走不到」。
      本轮撞到的是比「绕过去」更狠的一档：不是测试绕开了那道坎，是假 provider 的
      固定 usage 让那道坎在这套仪器下不可能被跨过，而没有任何测试会因此变红。
      注：`knowledge/concepts/` 这个目录早就并进 `knowledge/engineering/` 了，
      另外几条「够格升格 concepts」的登记都指着一个不存在的目录，写的时候按新路径走。

### feature 08（落盘布局）遗留 —— 2026-08-10

- [ ] asker 与 REPL 抢同一个输入流——现在的修法是逃生口，不是根治（2026-08-10，
      08 devlog「越界修复」，根因记录）。
      现象：模型调 `ask_user_question` 时，asker 去读下一行 stdin，
      而用户此刻敲的可能是给 REPL 的命令。实际发生过：`!echo 我是命令` 被当成了对问题的回答
      （铁证是它没进输入历史——那一行根本没被主循环读到）。
      根因：`_make_asker` 与主循环共用同一个阻塞 `reader`，本质是
      同一个输入流被两个消费者抢，谁先 `read()` 谁拿到。
      已做的只是缓解：空行跳过、`/exit` 退出、其他 `/命令` 提示后重读。
      仍然坏的：① `!命令` 仍被当成答案（没一并拦是因为真实答案以 `!` 开头的可能性
      不为零，硬拦会误伤）；② 提问期间用户无法执行任何命令，只能答或退。
      真正的解法在 TUI 阶段：模态输入——问题框接管输入焦点、Esc 取消
      （CC 的 AskUserQuestion 就是这么做的，见 K tui/claude-interactive-mode.md 的
      「Esc 关闭对话框而不是中断 Claude」）。纯 REPL 里做不出模态，
      所以这条不该在 REPL 阶段继续打补丁，等 TUI 一并解决。

- [ ] slug 碰撞（08 复盘一，D#44）：`/a-b/c` 与 `/a/b-c` 撞成同一个 slug。
      已钉成测试（`test_known_slug_collision_is_documented`），改之前先读那条 docstring。
- [ ] 输入历史仍用哈希文件名，这条判断可能是错的（08 复盘三）：当时理由是
      「可读性的价值在目录树里，不在同级文件名里」。但用户正是翻着
      `~/.pai/history/e4887ef95b86e3ee` 问「这是什么」才发现测试污染的——
      文件名可读的话也许更早发现。倾向于承认判断错了，重新评估。
- [x] ~~会话记录的完整字段改造（需求池，08 只并进了 sessionId + cwd）：
      `uuid`/`parentUuid` 父子链、ISO 时间戳、统一顶层判别字段。~~
      已交付 2026-08-22（[features/24](features/24-20260822-session-format-and-resume/README.md)
      格式 v1）：header 首行 + `{type,id,parentId,ts}` 信封 + 消息嵌套。
      刻意偏离一处：信封 ts 保持 epoch float（viz 时间算术），header 才用 ISO。
- [ ] 「顺手并入」的判据要收紧（08 复盘一）：本轮把 `sessionId` 搭车并入，
      理由「本来就要动 SessionLog」——那是 scope creep 最常见的措辞。
      规矩 7 应加一句：「顺手」只在『不做它本轮交付就是有缺陷的』时成立
      （`cwd` 满足，`sessionId` 不满足）。
- [ ] 涉及删除/迁移的拍板要附「执行时你能否分辨」（08 复盘四）：
      「老数据直接删」执行起来是 `rm -rf ~/.pai/projects`，而旧目录名是哈希、
      用户根本认不出哪个对应哪个项目——只能全删。这个代价拍板时没说。

### knowledge 缺口（2026-08-10 用户问「有没有归纳」时自查出来的）

- [ ] `loop/pi-agentloop.md` 该从「指针」升「精读」：阶段 2 实际深读了
      `agent.ts:123`（PendingMessageQueue 的 all/single 两种 drain 语义）与
      `types.ts:422`（AgentEvent 扁平联合共 9 种事件），这些结论现在只活在
      features/05 的档案里，没回流笔记。登记规约写明「指针升精读的时机：
      动工时发现指针的结论粒度不够用」——正是这个情形。
- [x] ~~CC `src/memdir/` 源码走读没做~~ 已补 2026-08-10，见
      [K memory/cc-memdir.md](../../knowledge/memory/cc-memdir.md)。
      悬案裁决：属实——CC 的召回是框架主动做的（便宜模型按 header manifest
      选 ≤5 篇塞进上下文），不是「模型自己想起来 read_file」。pai 少的是一整层机制。
      衍生出下面三条。
- [x] ~~`remember` 写入时带 `description` frontmatter~~ 已做 2026-08-11，
      见 [10-memory-recall](features/10-20260811-memory-recall/README.md)。
      连带把粒度改成一事一文件（`remember(name, description, fact, type)`）。
- [x] ~~记忆的新鲜度提示~~ 已做 2026-08-11（同上档案）：`memory_age` 相对时间 +
      `freshness_note`（≥2 天才提示，点名 `file:line` 引用会显得更权威）。原条目留档：
      （K cc-memdir 第四节，零成本，写入日期 pai 已经有了）：
      CC 用「47 days ago」而非 ISO 时间戳，注释直说模型不擅长日期算术，
      原始时间戳不会触发陈旧性推理；>1 天的记忆附一句「记忆是时间点观察不是实时状态，
      file:line 引用可能已过期」。动机是真实事故：带 file:line 的引用会让过期声明
      听起来更权威而不是更不权威。pai 迟早会踩，CC 已替我们踩过。
- [x] ~~记忆召回层做不做~~ 已拍板并交付 2026-08-11（用户原话「按cc的来」）：
      照 CC 做框架侧查询，另加空目录短路 / usage 计进熔断 / 连续 3 次失败停用（D#56）。
      见 [10-memory-recall](features/10-20260811-memory-recall/README.md)。
- [x] ~~建档案时不要删模板的 `复盘.md`~~ 已升级为硬规矩 2026-08-10（用户裁决）：
      「交付即复盘」写进 features/README 规矩 7 与 AGENTS.md，
      `tests/test_docs_consistency.py::test_delivered_features_have_a_retrospective` 强制
      （状态到「已交付」必须有复盘、不能是模板占位、必须有「我现在质疑什么」节）。
      立项日早于 2026-08-10 的既有档案不追溯。

- [x] ~~05 复盘质疑二：状态行不该默认改变已交付功能的输出形态（05 复盘）~~
      2026-08-11 由 feature 12 关闭：方案 A 天然解决——transcript 输出形态一个字没变，
      状态行进了 dock。原文留档：
      Task 8 把 `run_interactive` 的默认 `on_event` 换成了状态行处理器，
      开着就不再滚动打 `🔧`——这个行为改变从没被拍过板。考虑默认关、显式打开。
- [x] ~~06 复盘质疑三：「不读 AGENTS.md」的理由可能只在自家成立（06 复盘，
      D#43 复议候选）：论据「那是给开发 pai 的 AI 的规矩」在本仓库成立，但 pai 的
      立意是在别人的项目里跑，那里的 `AGENTS.md` 恰恰是该项目写给 agent 的规矩。~~
      已复议 2026-08-26（feature 35，用户当场拍板「改成也读」）：`discover()` 的
      候选加 `AGENTS.md`，用户级与项目级都读，同目录内排在 `PAI.md` 之前
      （后读到的更靠近对话）。`CLAUDE.md` 等别家入口照旧不读。
      [D#43](decisions.md) 已记推翻半边（原文划掉保留），代价如实写在那里：
      本仓库自己跑 pai 时这份 26KB 规约会进每轮上下文。
      连带修掉两条测试的隔离缺口：`test_conversation_persists_across_turns` 与
      `test_slash_clear_keeps_system_and_drops_history` 不 chdir，此前捡不到
      仓库根的指令文件纯属侥幸（仓库没有 PAI.md），现在会捡到 AGENTS.md。
- [ ] 06 复盘质疑四：`MEMORY.md` 的 200 行 / 25KB 是照抄官方，没有 pai 依据：
      官方数字是给英文 + Claude 调的；pai 跑中文、token 密度差一倍以上。
      与 `reserve_tokens=16384`「从 pi 借来的经验值」同一类债。
- [x] ~~两块硬拿的工程知识没沉淀~~ 已补 2026-08-10：
      [engineering/process-groups-and-interrupts.md](../../knowledge/engineering/process-groups-and-interrupts.md)、
      [tui/terminal-width.md](../../knowledge/tui/terminal-width.md)。
      顺带把 knowledge/ 的分类标准从「按主题」改成「按来源」（原先 concepts/ 是
      否定式定义「不专属某家源码的」，边界靠猜，当天就误放了一篇双源走读进去），
      并在 README 与 AGENTS.md 里写明：开发知识里「只关于 pai 的」进 docs/dev/，
      「换个项目仍成立的」才进 concepts/。

### API key 解析（2026-08-10，K model-api/pi-cc-api-keys.md）

- [ ] provider → env 变量名映射表（学 pi `env-api-keys.ts`）：现在 `DEEPSEEK_API_KEY`
      硬编码在 config.py，换 provider 要改代码。一张表 + `find_env_keys(provider)`。
- [ ] key 带来源（学 CC `getAnthropicApiKeyWithSource`）：返回 `(key, source)`，
      `/status` 显示「这次用的是哪来的 key」。2026-08-10 那次误诊断就栽在不知道 .env 从哪加载的。
- [ ] key 解析可注入（学 pi 的 `getApiKey` 钩子）：`make_client` 收可选回调，core 不碰 env。
- [ ] apiKeyHelper（key 来自一条命令）：价值在密钥轮转/企业网关，pai 暂无此场景；
      带 TTL 缓存 + stale-while-revalidate + 并发去重一整套复杂度，等真需要再做。

### feature 11（流式）遗留 —— 2026-08-11

- [ ] 中断丢弃半条 assistant 消息，与屏幕上看到的不一致（11 复盘质疑四）：
      打出来的半截答案不进上下文，下一轮问「你刚说的那个」它不知道。
      当时的理由是实现视角的（没有 usage、token 数无从得知）；用户视角看，
      「看得见的东西不算数」才是那个奇怪的地方。可考虑追加时按估算记 token
      （锚点本来就允许估算段），值得复议。
- [x] ~~并发在界面上完全不可见（11 复盘质疑二）~~ 2026-08-11 由 feature 12 T6 关闭：
      dock 活动区按动作聚合计数（照 CC 实物），同一批并发工具同时在列。
      未改线程模型。原文留档：为了不给 modes 层强加「事件处理器
      必须线程安全」，所有事件都在主线程发、`ToolEnd` 按原顺序交付——于是看不出谁先跑完，
      甚至看不出并发有没有真的发生。做了并发却看不见并发，对学习驱动的项目是损失。
      也许加个事件时间戳就够，不必改线程模型。
- [ ] `MAX_TOOL_WORKERS = 8` 是个不会生效的常量（11 复盘质疑一）：唯一的并发安全工具是
      `read_file`，模型一轮最多发过 3 个。连带质疑「给照抄常数写来源注释」这条习惯——
      给一个不会生效的常量写严肃注释，可能把「留痕」做成了仪式。
      下次遇到倾向于直接写「暂不限并发，真撞上再加」。
- [ ] `once` 的输出形态变了（11 复盘质疑三）：多了 `🤖 ` 前缀与空行，stdout 被多次写入。
      拍板时当作「预期内的代价」轻轻放过了，但 once 是给脚本用的模式，
      `pai "..." > out.txt` 这类用法迟早要回来处理。
- [x] ~~能力判定的三条退化路径不可分辨（11 task 3）：未声明 / 参数不是 dict /
      判定器抛异常，全部返回 False 且不留痕——「判定器写错了」与「工具确实不安全」
      在外部完全一样。工具多了会变成静默的性能损失。~~
      已修 2026-08-26（feature 35）：只给第三条留痕——前两条是常态（没声明就是
      没声明、模型发来的 arguments 本就可能是 `null`/`[1,2]`），判定器自己炸了
      才是 bug。`Tool._ask` 捕获异常时按 (工具, 判定器) 去重、往 stderr 喊一次
      （形状照 `EventTrace` 落盘失败那条：每次判定刷一行会淹掉真正要看的输出），
      行为一字不变仍返回 False。反向守卫钉住前两条保持沉默。
- [ ] `assemble` 不认 `finish_reason` 提前收尾（11 task 1）：读到迭代器结束为止。
      真实 SDK 在 `[DONE]` 后就停，暂不影响；provider 若在 finish 之后还发东西会继续消费。
- [ ] 流式中断的粒度是「块与块之间」（11 task 1）：巨大 chunk 传输中按 Ctrl+C
      要等它收完。实测 chunk 都很小（逐字符），暂不处理。
- [x] ~~把「反向对照」写成 roadmap 的固定勾选项（11 复盘「下次怎么做更好」）~~
      已做 2026-08-11（feature 12 顺手）：roadmap 头部新增「前置精读清单的固定末项：
      反向对照」一节写明规矩与理由，阶段 6/7 各补一行未勾选项，阶段 2 后半程与阶段 5
      补上已勾选项并链到各自 evidence。立规前交付的阶段（1/3/4）不追溯。
      规矩里另加一句诚实边界：跑不到的部分要留手工清单，不许拿「按源码推」冒充观测。

### feature 12（TUI）交付遗留 —— 2026-08-11

档案：[features/12](features/12-20260811-tui/README.md)、[复盘](features/12-20260811-tui/复盘.md)

- [x] ~~干活期间的按键只在「有事件到来时」被读取（12 复盘质疑二，比一般遗留严重）：
      一个跑 30 秒且不发事件的 bash 命令，期间用户打的字在 dock 上完全看不见——
      用户会以为键盘死了。解法要么独立输入线程（明确不做），要么工具执行期也定时 poll。~~
      已修 2026-08-26（[feature 39](features/39-20260826-busy-heartbeat/README.md)，
      用户从四处体验候选里点名这一处）：走「工具执行期也定时 poll」那条。
      新增 `core/heartbeat.py`（进程级心跳，形状照 `core/interrupt.py`——理由一字不差：
      `@tool` 从签名生成 schema，运行期上下文只能从旁路进），`shell._wait` 的轮询循环
      每轮一跳，TUI 把读键盘那段抽成 `pump_keys()` 给事件路径与心跳共用。
      顺带修掉一个谁也没登记过的真 bug：TUI 里 `!命令` 期间 Ctrl+C 停不下来
      （raw mode 关了 ISIG，而那时没人读键盘，字节要等命令跑完才被看见）。
      两条 e2e 先红后绿 + 三处注入反证。
- [x] ~~`_queue_size` 读了 `PendingMessageQueue` 的私有表（12 复盘质疑一）：
      当时的理由「不给 05 交付的类加公开面」站不住——`len(queue._messages)` 比加个
      `__len__` 更耦合，它把「内部用 list 存」泄漏进了 modes 层。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：`PendingMessageQueue.__len__` 加上，
      `_queue_size` 改成 `len(queue)`；两条测试覆盖（含"被谓词留在队列里的命令
      要照样计数"——dock 上那个数字说的就是它们）。
- [x] ~~`tui/driver.py` 一条测试都没有（12 复盘质疑五）：唯一碰真 tty/select 的
      文件，靠不在 `./test.sh` 里的冒烟脚本顶着，改坏它不会有任何东西变红。~~
      2026-08-26 对账核销（feature 35 复核）：已由 feature 16 收尾（2026-08-19，
      `fix/16-drag-render-throttle`）补上，本条漏勾——`tests/test_tui_driver.py`
      118 行，注入假 fd 测 `poll()`（含「真终端是很多批各一条、离线测试是一批很多条」
      这个被检验的假设本身）。那次的条目里写着「顺带给 driver.py 补了它此前一条都
      没有的测试」，只是没回来划掉这条。
- [ ] `run_interactive` 现在有两条主循环（12 复盘质疑四）：tty 走 TUI、非 tty 走老 REPL。
      与被否掉的方案 C 是「同一种东西的两个剂量」。代价是交互语义改动要改两处，
      而只改了一处不会让任何测试变红。
- [ ] `Ctrl+R` 的回退在拍板时被说得太轻（12 复盘质疑三）：readline 白送的不止 `Ctrl+R`，
      还有词跳边界、libedit 与 GNU readline 的差异、各终端方向键序列长尾。
      本轮只支持「一组主流序列」。用户拍板时看到的成本比真实成本小。
- [ ] 中文 IME 候选框位置仍未经真人验证（12 spec 验收标准第 11 条）：
      离线测不出，基准线见
      [evidence 手工清单](features/12-20260811-tui/evidence/20260811-终端反向对照/手工清单.md)。
- [x] ~~「交付前也该做一次反向对照」~~ 已做 2026-08-11：roadmap 那条固定项
      拆成「动工前」+「交付前：跑一个完整的真实回合，哪怕花钱」，并写明代价是用户替我踩的。
- [ ] 交付前的冒烟脚本为了省钱绕开了真实模型回合（12 复盘追记质疑六）：
      三条被用户打回的 bug 里有两条只要跑过一个完整回合就会撞到。
      与「测试为了让被测路径跑起来而注入的参数，正是真实路径上会卡住的地方」同源。
      建议把「一个完整回合」做成 `--llm` 冒烟的固定项。
- [ ] spec 应有「视觉层」一节（12 复盘追记「下次怎么做更好」第 6 条）：
      本轮 spec 只写功能不写视觉，交付后用户第一眼说「没有 TUI 呀」，
      随后四轮视觉修正全是靠截图往返。哪怕只写三行：什么在哪、什么颜色、层级是什么。

### feature 16（鼠标与选区）遗留 —— 2026-08-11

档案：[features/16](features/16-20260811-mouse-and-selection/README.md)。
本 feature 未标「已交付」：下面第一条是用户真跑撞到的、用户可感知的坏路径。

- [x] ~~真终端里「从后往前拖选」松手后不复制~~ 已修 2026-08-11（用户第三次报时
      给了决定性线索：高亮还在——而复制成功会清掉选区，所以是释放事件没送到，
      不是方向逻辑的问题）。修法不去猜它为什么丢，而是不依赖它一定会来。
      第一版兜底被用户当场推翻（「我还在按就结束了」）：把「停手」当成「松开」，
      慢拖被误判成结束。两者在输入流上完全一样，拿超时猜必然误伤一种——
      改成停手只做不破坏性的那一半（把选中的放进剪贴板 + 提示，
      不结束拖动、不清高亮），释放到了或下一次按下时才真正收尾。
      顺带给 `driver.py` 补了它此前一条都没有的测试（12 复盘质疑五）。
- [x] ~~拖动时的卡顿还没解决（同一次报告里的另一半）。已做的「driver 读干净再处理」
      只在事件已经排队时有用；真正的原因是每条拖动事件都触发一次整屏重绘
      （离线量到每帧约 1ms + 一次终端写，一次手势上百条）。
      正解是渲染节流：pi 的 `TuiBase.MIN_RENDER_INTERVAL_MS = 16`——
      置个标志位、合并到下一帧，而不是每个事件画一次。
      注意配套：节流必须有收尾的那一帧（否则最后一次移动画不出来），
      而 `needs_tick()` 已经在拖动期间为真，正好可以推它。
      归下一轮「优化」，且按 AGENTS 的 `perf` 判据：先量出数字再改。~~
      已修 2026-08-19（feature 16 收尾，`fix/16-drag-render-throttle`）。
      量出来的诊断与本条原文不同：`app.feed()` 末尾本来就只 refresh 一次、
      鼠标事件也合并过，真实分布是「事件一条一批到达时帧数太多」
      （一批到达 12.5ms/1 次写，一条一批 206~263ms/121 次写；单帧只要
      1.1~1.7ms 且不随 transcript 增大）。修法 `DRAG_FRAME_INTERVAL = 0.016`，
      修复后 14.4~16.4ms / 2 次写。16 号档案随此交付（停在「实现中」八天）。
- [ ] ★ 拖选卡顿的真实成因至今未确诊，feature 16 的节流没解决它
      （出处：16 devlog 2026-08-19 追记、20 交付时的真机对照）。
      真 pty、40 条拖动事件，有节流 6/71/75 次写、无节流 7/67/70 次写
      （事件间隔 0/10/30ms）——两列没有差别。逐层注入反证确认：真机上帧数低
      是 `_merge_mouse_runs` 与「每批只 refresh 一次」挡下来的，节流没起作用。
      原先发布的 206→14ms 是基准脚本的产物（紧循环调 `app.feed()` + 假时钟，
      造出了真路径上不存在的到达形态）。
      节流代码保留（无回退、有 4 条离线测试钉自身语义），但不再声称它修了卡顿。
      下一步：先在真终端复现卡顿并定位，而不是再猜一个原因。
- [x] ~~「基准测出来的收益在真实路径上不存在」值得记进方法论
      （出处：同上）。与既有那条「测试为了让被测路径跑起来而注入的参数，
      正是真实路径上会卡住的地方」是同一种病的镜像：这次是**基准为了让被测
      代码生效而注入的到达形态，恰是真实路径上不会出现的**。够格升格
      knowledge/concepts 的一条方法论笔记。~~
      已回流 2026-08-26（feature 40）：[K engineering/green-but-which-path.md]
      (../../knowledge/engineering/green-but-which-path.md) 第二节
      「基准为了让被测代码生效而注入的到达形态，恰是真实路径上不会出现的」。
      与它同族的另三种巧合（测试注入的参数绕过真实的坎、两个坐标系恰好相等、
      仪器把会变的量常量化）写在同一篇里——它们的共同点是「绿只证明了
      这套测试环境里被执行的那条路是对的」。
- [ ] feature 16 收尾遗留：节流没有 e2e（出处：16 复盘质疑三）。它正在
      `feed` 与 `needs_tick` 的接缝上，而收尾帧靠 driver 的空闲 poll 推动——
      某次 poll 因有输入而不走超时分支时收尾会晚一拍，离线测不出。
- [ ] 「功能停在实现中」应比普通待办更显眼（出处：16 复盘质疑四）。
      16 号从「实现完」到「交付」隔了八天，档案状态一直是「实现中」而无人提醒；
      TODO 里有那条卡顿记录，但 TODO 有 171 条。建议 STATUS「下一步」单列一行。
- [ ] `perf` 类待办登记时要写明「该量什么」（出处：16 复盘「下次怎么做更好」）。
      本条原文只写「先量出数字再改」，没说量什么，八天后得重新想一遍。
- [ ] 复制提示的口径与 CC 不同：pai 说「已复制 N 行」，CC 说「copied 18 chars」。
      按行还是按字符没讨论过，留待复议。
- [ ] 输入框的选区不参与 `resize` 与历史翻页：换宽度后选区仍按旧的字符下标，
      视觉上会错位（transcript 那边锚在逻辑行所以没有这个问题）。
- [ ] `_highlight` 逐字符扫描每一行：选区存在时每帧对视口内每行做一次字符级遍历。
      现在看不出（视口几十行），长视口 + 宽终端下值得量一量再说（`perf` 要先有数字）。
- [ ] `kill -9` 之后鼠标模式留在终端里：与 feature 13 那条「留在备用屏」同源，
      且更烦——shell 里鼠标会失灵。同样兜不住。

### feature 13（alt-screen）交付遗留 —— 2026-08-11

档案：[features/13](features/13-20260811-alt-screen/README.md)、[复盘](features/13-20260811-alt-screen/复盘.md)

- [ ] 崩溃/`kill -9` 会把用户留在空的备用屏里（13 复盘质疑二，比一般遗留严重）：
      `try/finally` 兜住了异常与正常退出，但 `kill -9` 兜不住也测不到。
      main-screen 下最坏是留个乱 dock（`clear` 一下就好），alt 屏下用户看到的是
      空屏 + 打字没回显，第一反应是「终端坏了」。
      拍板时我给的理由「自用项目没有外部用户风险」只覆盖了「影响多少人」，
      没覆盖「一次失败有多难恢复」。建议补：启动时若检测到上次异常退出，打一行怎么恢复。
- [ ] `vim`/`less` 这类程序退出时的 rmcup 会把 pai 也踢回主屏（CC 注释点名）：
      pai 的 `bash` 工具就可能跑到它们。本轮不做自愈——两条实测结论把路堵死了：
      重进 alt 会清屏（evidence 第 1 条）、没法问终端自己在不在 alt（evidence 第 2 条）。
- [ ] 「已上滚」的指示位置可能选错了（13 复盘质疑三）：它藏在状态行里，
      而屏幕上最显眼的 transcript 区域什么都没说。CC 用的是悬浮的「跳到底部 / N 条新消息」
      药丸。指示位置选错了可能比没做还糟——它制造了「已经提示过用户」的错觉。
- [ ] `_fit()` 的静默截断与「等真撞上再说」自相矛盾（13 复盘质疑四）：
      超宽行在 alt 屏里的症状是悄悄吃掉右边的内容，用户不会报告一个他看不见的 bug，
      所以「真撞上」这个触发条件结构上永远不会到来。pi 在同一位置选的是 fail-loud
      （超宽即 dump + throw）。值得复议。
- [ ] transcript 无上限：长会话里条目只增不减（每条还带一份行缓存）。
      与 feature 10 那条「一事一文件让索引膨胀」是同一类账，但这次没有任何收缩机制。
- [x] ~~两处读同一个 `settings.json`（等第三个读者出现时再合）~~ 已合
      2026-08-24（[feature 30](features/30-20260824-config-and-trust-dedup/README.md)）：
      读取者到第四个（mcp）时触发条件翻倍命中，`settings.read_settings_layers`
      成为唯一读盘实现，permissions/hooks/mcp/settings 全部消费它；顺带把
      skills 与 mcp 的信任门禁三胞胎合成 `project_trust_gate` 一份（文案参数化
      逐字不变）。
- [ ] 内容不满一屏时顶部对齐，transcript 与 dock 之间留一大片空白。
      与 pi/CC 的形态一致，但没问过用户觉得好不好看。

### feature 13（alt-screen）拍板时已知的债 —— 2026-08-11

档案：[features/13](features/13-20260811-alt-screen/README.md)、[spec](features/13-20260811-alt-screen/spec.md)。
三条都是拍板时就知道的，不是事后发现。

- [x] ~~`--resume` 不存在，而 13 交付后历史只剩 JSONL（13 brainstorm 问 2，用户提出）。~~
      已交付 2026-08-22，见 [features/24](features/24-20260822-session-format-and-resume/README.md)：
      `pai --resume`（latest / id 前缀 / 路径）+ 配平 + 状态从零 + 按原 id 重录；
      退出提示已改真话。原条目余文照留：
      今天退出 pai，整段对话还在终端 scrollback 里能翻能复制；alt 屏没有 scrollback，
      13 又拍板不回吐完整文档（对齐 CC 的 `printResumeHint()`）。
      于是从 13 交付到 resume 落地这段时间，退出那一刻历史就只在
      `~/.pai/projects/<slug>/sessions/*.jsonl` 里，而 JSONL 不是给人读的。
      紧接着 13 单独立项；最小形态（读回最后一次会话的线性消息接着聊）不需要
      `uuid`/`parentUuid` 父子链，那是「回退/分支重开」才要的（见上面 08 那条）。
      2026-08-11 交付后追记优先级理由（13 复盘质疑一）：它应当排在「搜索」与
      「点击」之前——那两项是本轮未做的，而这一条是本轮引入的缺口。
- [ ] 「工具结果能点」是 13 的地基而不是 13 本身（13 brainstorm 问 1/3）。
      13 拍板不接管鼠标（保住终端原生的拖选复制与 `Cmd+F`——一旦上报鼠标终端就不管了，
      且失败是静默的）。13 建的是「每帧知道每个条目画在哪几行」这个前提；
      加鼠标是 SGR 1006 解析 + 命中测试（CC 实测只要 130 行，便宜），单独立项。
      动工前先看 [K tui/alt-screen-and-mouse.md](../../knowledge/tui/alt-screen-and-mouse.md)
      第 3 节：`1000/1002/1003` 互斥单选，照抄 pi/CC 那串四条序列会选中最费的 1003。
- [ ] transcript 内搜索没做（13 brainstorm 问 5）：需求第 2 条「滚动与搜索」
      只做了滚动那一半。搜索要额外的输入模式，与已有的输入归属仲裁、对话框、
      `!`/`/` 模式都要对得上。注意不接管鼠标的代价在这里露头：
      终端自己的 `Cmd+F` 在备用屏里只搜得到当前一屏。

### 流程 —— 2026-08-11

- [x] ~~档案分不清「中等改动通道」与「漏了 plan」~~ 已做 2026-08-11
      （用户问「15 这个没有 plan 吗」引出）：档案头部新增「流程：」字段，
      `_template` 与 features/README 规矩 9 同步，两条机器校验
      （字段必须有；声明走全链路的必须拿得出 spec 与 plan）。
      立项日早于 2026-08-11 的不追溯；10/11/12 补了真实字段（都确实走了全链路）。
- [ ] 中等改动通道没有承载「验收项」的地方（同上引出的真问题）：
      feature 15 的「每条 e2e 必须配一条注入反证」只活在脑子里，结果 2/3 假绿。
      规矩 9 已要求「走中等改动时把验收项写进档案的需求节」，
      但机器判不了「验收项写得够不够」——这条是提示词层约束，如实声明。

### feature 15（假 provider + e2e）遗留 —— 2026-08-11

- [x] ~~「跑一次真 pai 然后出图」这条链路没有自动化~~ 已做（14 遗留由 15 关闭）：
      `tests/test_e2e_tui.py` 5 条进了 `./test.sh`。
- [x] ~~e2e 把主套件从 12s 拖到 34s：没做分层（没有 `-m "not e2e"` 的快循环）。
      再多几条就该分了。~~ 已做 2026-08-26（feature 35，触发条件到了：e2e 现在
      占掉大半墙钟）：`./test.sh --fast` 跑 `-m "not llm and not e2e"`。
      标记由 conftest 按文件名自动挂（`test_e2e_*.py`），不靠每个文件自己写
      `pytestmark`——自觉的那种漏一个不会红，而漏掉的后果正是快循环里混进一条起
      真 pty 的测试。实测（2026-08-26 本机，串行）：全量 1447 passed / 163.16s，
      `--fast` 1416 passed + 1 skipped / 36.23s（4.5×，31 条 e2e 占掉 78% 墙钟）。
      交付前仍必须跑全量，快循环只用于改一行看一眼。
- [ ] e2e 依赖 pty 与 select 的时序，理论上仍可能偶发；已用「等到出现为止」
      压到最小，但没做重试。
- [x] ~~没有测「中断」与「压缩」：Ctrl+C 掐在流中途、自动压缩触发——
      这两条 e2e 都能测但还没写。~~
      已补 2026-08-26（[feature 38](features/38-20260826-offline-real-gap/README.md)）。
      「都能测」这句当年说早了：压缩那条此前结构上跑不到——假 provider 对每轮回
      固定 usage，相邻锚差值恒为 0，切点永远算成「无可压」。先把假 provider 的
      `prompt_tokens` 改成随对话增长（可按轮钉死），压缩才第一次在真进程 + 真 pty
      里跑到，屏幕上有「压缩：切于 2」、摘要请求真的发出去了。
      中断那条第一版假绿（拿屏幕当同步点，而流式增量要等收尾才进 scrollback，
      于是等到整轮结束、Ctrl+C 落成空闲态那一档），改成死等固定秒数 + 断言
      「整段答案不许完整出现」。两条各有注入反证。
- [ ] 假 provider 只实现了 `POST /chat/completions`，接别的端点要补。

### feature 14（录制与回放）遗留 —— 2026-08-11

- [ ] 录制不含用户按键（14 复盘质疑一）：看得见结果，看不见导致结果的操作。
      用户报「我按了 X 然后坏了」时录制帮不上忙。完整形态是双向录制（输入 + 输出带时序）。
- [ ] 「跑一次真 pai 然后出图」这条链路没有自动化（14 复盘质疑二）：
      录制/回放有 8 条单测，但端到端活在 gitignore 掉的探针脚本里——
      改坏 `DockRenderer` 的 write 注入点不会有任何东西变红。
      建议做成一条 e2e：起 pai → 录 → 回放 → 断言屏幕上有欢迎语。
- [ ] 出图字体路径写死 macOS，Linux 上要另找；彩色 emoji 画不出（已由缺字告警兜住）。
- [ ] `pai-replay` 对用户同样有用而档案没写（14 复盘质疑三）：
      可以让用户录下问题发给别人复现、也可以给 pai 自己做文档配图。需求当时定窄了。
- [ ] `render_text` 与 `/help` 里的 emoji 未清：05/06 交付的 scrollback 内容，
      D#63 只约束了 TUI 自己的字形。要不要一并换成非 emoji，待定。

### feature 12（TUI）用户真跑打回来的 —— 2026-08-11

三条都是离线 171 条测试全绿却坏掉的，值得单列出来看规律：
它们全在「组件之间的接缝」上，而我的测试是逐个组件测的。

- [x] ~~模型的回答完全没上屏~~ 已修：`render_text(AssistantMessage)` 返回 None
      （echo 模式的前提是「流式已逐字打过」），而 TUI 的 `on_event` 又跳过 `MessageDelta`——
      两边都以为对方会打。没抓到是因为没有一条测试走完 delta→AssistantMessage 全链路。
- [x] ~~权限框走老 asker，raw mode 下整个程序死住~~ 已修：`gate` 装配期捕获了
      REPL 的 asker，TUI 只换了 `ask.set_asker`。老 asker 调 `input()`，
      而 raw mode 下 Enter 发 `\r` 不是 `\n` → 永远等不到行尾；Ctrl+C 因 ISIG 关了
      只是普通字节 → 退都退不出去。改成 `AskerRef` 可变持有者，一处换两处生效。
      与 T5 那条「模式是装配期常量」是同一个病，我修了一个没想到另一个。
- [x] ~~排版满屏阶梯~~ 已修：`app.commit()` 不拆换行也不折行。
      工具结果是一整个带 `\n` 的字符串，被当成「一行」交出去，终端自己折了，
      而 dock 的相对光标移动按「我写了几行」算 → 差几行整块就漂。
- [x] ~~工具结果的展开机制没做~~ 已做 2026-08-11（用户拍板「丙」）：
      `^O` 把最近一条被折叠的工具输出整段再打一遍，连按往回走，历史有界（32 条）。
      不是原地展开、不能点——那要 alt-screen，已单独立项
      [features/13](features/13-20260811-alt-screen/README.md)。
- [ ] 权限询问里 `write_file` 的 content 仍只截 160 字（12 收尾）：
      够用但看不到要写什么。真要批得明白得有 diff 预览，属另一件事。

### feature 12（TUI）实现中冒出来的 —— 2026-08-11

- [x] ~~`display_width` 的家不对了（12 T1）：它住在 `modes/statusline.py`，
      而 `pai/tui/` 要用它，形成 tui → modes 的依赖。应把这个宽度原语一并挪进
      tui 包，并同步 K tui/terminal-width.md 的锚点。~~
      已挪 2026-08-26（feature 35）：新增 `src/pai/tui/width.py`
      （`display_width` / `_truncate` / `_ESCAPES` / `ELLIPSIS`），十个 tui 模块
      改从它 import，`statusline` 反过来从 tui 拿并 re-export（不动九处调用点与
      十处测试 import——搬家是结构修正不是接口变更）；K tui/terminal-width.md
      锚点同步。方向由一条 AST 守卫测试钉住（`pai/tui/*.py` 不许 import
      `pai.modes`，唯一豁免见下条）。
      验收不是「测试还绿」：拿 HEAD 的旧实现与新模块对同一批 4090 条样本
      （中英/全角/组合记号/ZWJ/CSI/OSC/APC/制表符）做 36810 次比对，
      `display_width` 与 `_truncate`（8 档宽度）零处不一致，`_ESCAPES` 正则逐字相等。
- [ ] `_preview` 仍住在 `modes/statusline.py`，是 tui → modes 的唯一残余
      （出处：feature 35 搬 `display_width` 时顺带发现）：它被 statusline 与
      `tui/dock.py` 共用，但它不是宽度原语，塞进 `tui/width.py` 是错的家。
      守卫测试已把它写成显式豁免（多一个名字就红）。等第三个消费者出现，
      或 dock 与状态行的渲染再有共用件时，一起找个合适的家。

### feature 12（TUI）拍板后已知的功能回退 —— 2026-08-11

- [ ] `Ctrl+R` 增量历史搜索会消失（12 spec 非目标）：方案 A 全程 raw mode、
      自写行编辑器，readline 白送的 `Ctrl+R` 没有了。这是一处明确的功能回退，
      拍板时就知道，不是事后发现。真需要时单独做（本质是个模糊匹配 + 覆盖层组件）。
- [x] ~~steering 队列仍不通电（12 spec G6）~~ 2026-08-13 由
      [features/18](features/18-20260813-steering-input/README.md) 关闭：默认值反过来了——
      干活时打的字本轮就注入（问 1 照 CC），followUp 队列删掉（问 2），
      pai 只剩一条消息队列 + 两个注入出口。

### feature 12（TUI）前置发现 —— 2026-08-11

这三条是已交付代码的现存缺口，由 feature 12 的反向对照撞出（不是 12 自己的遗留）。
出处统一是 [features/12 evidence](features/12-20260811-tui/evidence/20260811-终端反向对照/说明.md)。

- [x] ~~pai 对窗口 resize 完全无反应（evidence 第 1 条）~~ 已做 2026-08-11
      （feature 12 T8）：`SIGWINCH` 同步处理、同尺寸事件丢弃、只重画 dock、不清 scrollback。
      原文留档：没装 `SIGWINCH`，
      readline 也不重绘，实测 80→30→100 列 pai 一个字节都不发。
      后果：窗口变窄时已输入的半行中文与光标位置错位。
      对照 pi（宽度一变即全量重绘）与 CC（`handleResize` 刻意不去抖、同尺寸事件丢弃），
      pai 是三家里唯一完全不处理的。归 TUI 阶段一并解决。
- [ ] 状态行按事件重算宽度，而不是按 resize 重算（evidence 第 4 条）：
      `StatusLinePrinter.handle()` 每次重取列数是对的，但 resize 之后、
      下一个工具事件之前，屏幕上还留着按旧宽度渲染的那一行；缩窄后它被终端折成两行，
      而后续 `\r\x1b[K` 只清得掉最后一个视觉行。视觉残留待人工确认
      （evidence 的[手工清单](features/12-20260811-tui/evidence/20260811-终端反向对照/手工清单.md)第 2 项）。
- [ ] 没有任何断言挡住「将来某个组件忘了截断」（evidence 第 5 条）：
      实测 1..120 列 × 中文/emoji/ASCII 混合零越界，守卫目前是结实的，
      但靠的是每个渲染函数自觉。pi 为此准备了 fail-loud（超宽即 dump + throw，
      理由：折行会让所有相对光标移动错位，症状是满屏乱跳而非某处显示不全）。
      便宜的仿制品，值得做。
- [ ] 非 tty 下仍打欢迎语与 `› ` 提示符（evidence 第 6 条）：退化本身是对的
      （无 `\r`、无 ANSI），但提示符进了管道是噪音。CC 的口径是
      stdout 不是 tty 就整个走非交互路径。与 feature 11 遗留
      「`once` 的输出形态变了，而 once 是给脚本用的模式」是同一类账，可一起处理。
- [ ] 空闲态的第一次 Ctrl+C 也计入两级（evidence 第 3 条）：输入框为空、
      没有正在跑的任务时按 Ctrl+C，pai 也提示「再按一次退出」，第二次即退出。
      CC 的第一级语义是「中断当前操作」。是否要让空闲态的 Ctrl+C 不计数是个可议取舍，
      记录待定，不一定要改。

### feature 10（记忆召回）遗留 —— 2026-08-11

- [x] ~~召回的 `json_object` 一次都没真验过~~ 已验证并修复 2026-08-11（用户授权花钱）。
      真跑抓到两个离线测不出的 bug（`max_tokens=256` 被推理 token 吃光、模型抄回
      `[type]` 装饰被白名单全丢），召回当时在真实环境 100% 失效且完全静默。
      已加 `RecallFailed` 事件、解析层区分「没说话/明确选空」、
      沉淀 [K model-api/reasoning-models-max-tokens.md](../../knowledge/model-api/reasoning-models-max-tokens.md)。
- [ ] 给「照抄来的常数」建一条检查习惯（10 冒烟教训，与 06 复盘质疑四同类）：
      `max_tokens=256`（CC 的 Sonnet 档）、`MEMORY.md` 200 行/25KB（英文调的）、
      `reserve_tokens=16384`（从 pi 借的）——三条都是抄来的数字带着它原本的模型/语言假设。
      至少在常量旁强制写「这个数从哪来、依赖什么前提」，让下一个人看得见前提。
- [x] ~~召回块被压缩摘掉后不会重来，召回在长会话里单调衰减到零（10 遗留 6，
      复盘质疑四）：`RecallState.surfaced` 还记着「已经注入过」，于是那几篇再也
      不会被选中。`surfaced` 的语义（「已经在上下文里」）被压缩证伪了。~~
      已修 2026-08-26（feature 35，用户拍板「上下文被改写就全清」）：
      `run_agent` 新增注入回调 `on_context_rewritten`（loop 仍不认识召回；
      追记：该回调已于 2026-08-26 由 feature 37 升格成事件，机制换了、结论没变），
      装配层接成 `recall_state.surfaced.clear()`；自动压缩、`/compact`、`/clear`
      三处共用同一条通道。复核时发现的第二半边一并修掉：`/clear` 同样没清
      ——它比压缩更彻底（整段删），而那几篇记忆此后永不再被选中且完全静默。
      测试两头钉：装配层「注入过→再选就空→改写后又能选中」，loop 层
      「压成了才通知、暂缓与失败一个字不说」，命令层 `/clear` 报、`/status` 不报。
      代价如实记：压缩后那几篇可能被再召回一次，多花一次注入的 token。
- [ ] 一事一文件让索引膨胀变快，而本次没引入任何收缩机制（10 遗留 4，复盘质疑二）：
      索引行数从「主题数」变成「记忆条数」，200 行上限撞得早得多。CC 靠写入侧提示词
      让模型查重/删除，pai 抄了「更新而不是新建」（做进工具了）但没抄「删」——
      `remember` 结构上只能增和改。与 06 遗留的「MEMORY.md 无自动剪枝」是同一条账，
      但触发条件已经从「等它长起来」提前了。
- [ ] `recentTools` 去噪未做（10 遗留 2，K cc-memdir 第三节）：CC 区分得很细——
      正在用的工具，其用法/API 文档不选，但关于它的警告与坑仍要选
      （「active use is exactly when those matter」）。要给 loop 加一条
      「最近用了哪些工具」的管线，记忆量还没到需要它的规模。
- [ ] 召回没有开关（10 遗留 3）：唯一的「关」是记忆目录为空。真要开关应落在
      `.pai/settings.json`（feature 07 的两层配置），不该再加一个 env。
- [ ] `description` 一个字段兼任 CC 的两份文案，代价未知（10 复盘质疑三）：
      CC 的 frontmatter `description`（给召回器）与索引行钩子（给主模型）是两个不同字符串，
      本机样本实测确实不同。pai 合并成一份省了字段，但两处读者与用途不同。
      建议等有数据再复议，别忘了这是个*选择*而不是自然结果。

### feature 24（会话格式 + resume）遗留 —— 2026-08-22

- [ ] `--resume` 只进交互模式：与任务参数组合（CC 的 `-c -p`）被拒绝，
      once 续跑未做（出处：24 README 遗留）。
- [x] ~~resume 只恢复对话不恢复设置：权限模式/模型/system prompt 取当前环境，
      dsh 明确警告「恢复不同构图的组合是错误」而 pai 连警告都没有（同上）。~~
      警告已加 2026-08-26（feature 35）：`--resume` 的提示多两行——「恢复的只有
      对话，设置不跟着回来：权限模式、模型、system prompt 都按当前环境重新装配」，
      以及（仅当 header 里的 `cwd` 与当前目录不同时）「该会话录制于 X，
      当前目录不同——工作目录边界与项目指令都会不一样」。目录没变一个字不提
      （反向守卫钉住）。真正「恢复设置」仍未做：那要把模式/模型写进 header，
      是格式的事，等真实需要。
- [x] ~~`resolve_resume_target` 同秒 mtime tie 时 latest 未定义：排序键补
      st_mtime_ns 或文件名即可，一行的事（出处：24 复盘质疑四）。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：排序键改 `(st_mtime_ns, f.name)`，
      两件事一起做——秒改纳秒（本来就该分得出先后），真同秒时再按文件名
      （前缀是 `%Y%m%d-%H%M%S-<id8>`）给一个稳定且可解释的答案。
      测试把 glob 顺序钉成最坏情况正反各跑一次，断言答案不随列出顺序变。
- [ ] 观测流 `.events.jsonl` 仍是旧平铺格式：一对文件两种形状，viz 靠读边
      归一化弥合；events 侧换不换信封等 evals 立项时定（出处：24 README 遗留）。
- [ ] resume 重录全量历史进新文件：自包含的代价是每 resume 复制一份历史，
      反复 resume 长会话会滚雪球，「文件数 × 全量」的账没算过（24 复盘质疑三）。
- [ ] 跨轮平行状态已三件（messages/anchors/ledger），到第四件该封 Session
      会话对象（pi SessionManager 的角色）（出处：24 复盘质疑一）。
- [ ] 树操作（回退/分支重开）只有 parentId 字段没有功能——pi 证明是纯读取侧
      算法，需求出现再开（出处：24 README 遗留）。

### 分层记忆：与 CC 官方文档逐条对照 —— 2026-08-19（用户提问引出）

起因：用户问「CLAUDE.md 是默认加载当前目录的吗」，去读官方 memory 文档逐条核了一遍。
好消息是抄得挺准：注入成 system 之后的一条 user 消息、@import 四跳上限、
`MEMORY.md` 200 行 / 25KB、不读 `AGENTS.md` 而建议显式导入、压缩后从磁盘重读重注入——
这几条与官方一致。下面是对不上的。

- [x] ~~`memory.py:57` 的注释「官方同款语义，模型要用时自己 read_file」不成立
      （准确度，先改）：官方对 cwd 之下子目录的 `CLAUDE.md` 是框架懒加载，
      不是「靠模型自己 read_file」；pai 彻底不收集，比官方弱一档。~~
      已改 2026-08-26（feature 35，纯文档）：`discover` 的 docstring 写明这不是
      同款语义、官方那边仍是「框架主动」（只是延迟到需要时）、pai 弱一档是刻意的
      能力差（懒加载要一条读文件时检查的管线，且注入时机不确定，与压缩锚点簿有
      交互）。`test_subdirectory_files_are_not_loaded` 的 docstring 同步订正——
      它此前抄的是同一句错话。
- [ ] 子目录指令的懒加载未实现（能力缺口）——管线已由 feature 36 铺好，
      本条只差一种规则来源：「读到 `sub/x.py` → 看 `sub/PAI.md` 有没有、
      没加载过就注入」。挂点、注入形态、去重与压缩后的失效全部复用
      `core/rules.py` 那一套（`on_paths_touched` → `select_and_render` →
      `RuleState`），不再是「不是加个函数就完事」——现在真的差不多就是加个函数。
      收益仍存疑（pai 典型用法是单仓单目录），所以 36 拍板问 3 把它留在了外面。
- [x] ~~没有路径作用域规则（对应官方的 `.claude/rules/` + `paths:` frontmatter）：
      官方用它解决「CLAUDE.md 越写越长」，是降低常驻成本的机制，而常驻那一层
      正是 pai 四家对照里最薄的（PAI-04 卡片的诚实边界）。~~
      已交付 2026-08-26（[feature 36](features/36-20260826-path-scoped-instructions/README.md)，
      用户在「阶段 1-7 全交付后接哪件」里点名）：`.pai/rules/*.md` 与
      `~/.pai/rules/*.md` 里带 `paths:` 的规则，只在模型这一步真的碰到匹配文件时
      才进上下文。挂点在 loop 的工具结果回填处（路径怎么取仍下放给 `Tool.get_path`），
      注入形态与召回块同款，压缩后作废重来（当时走 `on_context_rewritten` 回调，
      2026-08-26 由 feature 37 升格成事件 `events.CONTEXT_REWRITING`）。
      与官方不同的四处见 [D#75](decisions.md) 与档案 spec。
- [ ] 项目级指令只认 `PAI.md`，官方还认 `./.claude/CLAUDE.md`（小，可不做）：
      记下来是为了别在对照时说漏。真要加就是 `discover()` 里多一个候选路径。
- [ ] `remember` 在真实会话里从未被调用过（2026-08-19 实测）：
      `~/.pai/projects/` 下 5 个项目目录**全部只有 `sessions/`，没有 `memory/`**——
      该目录是 `remember` 首次调用时才 mkdir 的，所以事实记忆一篇都没写过。
      召回层因此每轮都走第二个短路（候选为空）直接返回，请求根本不发。
      后果不是坏，是看不出来：「它没在工作」和「它工作得很好」外部表现一模一样，
      这正是这一层反复讲的「失效方式是沉默」本身。
      要做的是一次端到端真实验证：让 pai 自己 remember 三五条，再问一个能命中的问题，
      确认召回块真的注入了。与「json_object 一次都没真验过」那条不同——
      那条验的是侧查询本身（已完成 2026-08-11），这条验的是从写入到召回的整条链。
- [x] ~~召回注入没有单篇字符上限（2026-08-19 走读时发现，PAI-04 诚实边界已记）：
      `MAX_RECALL_FILES = 5` 只限篇数，记忆文件是整篇读进来的；工具输出在源头
      截到 4000 字符，召回这条路不走那个截断。写一篇特别长的记忆，召回一次就顶上来。~~
      已修 2026-08-26（feature 35）：`MAX_RECALL_CHARS = 4000`（取 `read_file` 的
      `MAX_OUTPUT_CHARS`，理由是「一段进上下文的外部文本」两条路上该同价，
      不是因为量过——常量旁写明来路），超了截断并说出来（前 N / 全文 M /
      需要全文就 read_file 读哪个路径）。反向守卫：没超的一个字不许动。
      中文按字符截偏严，与 25 遗留 3 的换算校准同批再定。

### feature 06（记忆）遗留 —— 2026-08-10

- [ ] 收割后台进程组存在 pgid 重用的误杀窗口（2026-08-10 补漏三）：
      `_SPAWNED_GROUPS` 登记的是 pgid，若某个组早已结束、pgid 被系统重用，
      退出时的 `killpg` 会误杀无关进程。真实风险低（macOS pid 空间大、回绕慢）
      但不为零。可行的收紧：登记时一并记 `proc`，收割前用 `proc.poll()` 确认
      我们那个子进程还在（组仍属于我们）。
      追记 2026-08-26（feature 35 挑条目时先看代码，结论是这个修法不能照做）：
      `reap_spawned` 的 docstring 自己写着它存在的理由是 `sleep 300 &`——
      父 shell 立刻就退了、后台孙子还活着。而 `proc.poll() is not None` 恰恰在
      这种情况下为真，照这个修法收紧就会跳过 killpg，把主用例的后台进程漏掉。
      换句话说：拿一个几乎不会发生的误杀，换一个每次都发生的泄漏。
      真要修得换判据（组里是否还有属于我们的进程，POSIX 层面查不了），
      或接受现状。本条维持开着，但修法一栏作废——下次动它先读这条追记。

- [x] ~~REPL 主循环应兜一层「任何异常都回提示符」（2026-08-10，同类问题第三次）~~
      已做 2026-08-11（feature 12 T8）：纯 REPL 与 TUI 两条主循环都兜了，
      `EOFError`/`KeyboardInterrupt` 显式重抛不吞，两条测试钉死。原文留档：
      401 炸会话、Ctrl+C 打断 `!命令` 炸会话，两次都是「某条路径漏了保护」，
      两次都靠「发现一处补一处」修。REPL 这一层的价值就是对话留着，
      任何逃逸的异常都在毁掉这个价值。应在主循环上兜底，让「哪条路径漏了」
      不再需要逐条排查——注意别把 EOFError（Ctrl+D 正常退出）也吞掉。

- [x] ~~API key 只能放项目 .env，无用户级配置~~ 已修 2026-08-10（用户提出）。
      过程中我先给了一个错误诊断，如实留痕：最初说「`.env` 只在仓库目录找得到，
      `cd /tmp && pai` 起不来」——那是用 `python3 -c` 测出来的假象（python-dotenv 对
      `-c`/交互走「按 cwd 找」分支，真实 `pai` 走「按调用方文件找」分支，正好摸到仓库 .env）。
      真正的问题比这个更隐蔽：`find_dotenv()` 默认从调用方所在文件（`src/pai/config.py`）
      向上找，所以「项目级 .env」实际解析成 pai 仓库自己那份——在别的项目里跑读的是错的那个，
      装成 wheel 之后直接找不到；它现在能工作纯粹是 editable 安装的巧合。
      修法：`load_dotenv(find_dotenv(usecwd=True))`（项目级真按当前目录找）+
      `~/.pai/.env` 用户级兜底，优先级 真实环境变量 > 项目 > 用户。测试 4 条钉死。

- [x] ~~REPL 中途改 `PAI.md` 不生效（06 task 4）：`_inject_instructions` 认出已有
      指令消息就直接返回，连 loader 都不调——多轮 REPL 只在第一轮读盘，改了文件
      要等一次压缩或重启。可加 `/memory reload`，几行的事。~~
      已做 2026-08-26（feature 35，方向即条目既定）：`loop.drop_instructions`
      丢掉当前指令消息（台账同步删，否则下次压缩 `ledger[cut]` 指错条目），
      下一轮的注入点重新调 loader = 从磁盘重读。不在命令里立即重注入：注入点
      本来就在每轮开头，多一条路径就多一处要对齐的语义。落盘侧天然自洽——
      `session.build_messages` 只留最后一条指令消息，重注入的那条自然赢。
      测试跑的是真实症状：第一轮之后改盘上的 PAI.md、`/memory reload`、
      第二轮的请求里必须是新内容且旧的不并存。
- [ ] `MEMORY.md` 无自动剪枝（06 spec 非目标）：写多了会撞 200 行上限被截断
      （有提示，不静默）。等它真长起来再设计「谁来剪、剪掉的进哪个主题文件」。
- [ ] `memory_dir` 的 key 是 hash，不可读（06 task 3）：调试时得靠 `/memory` 才知道
      记忆写到哪去了。可考虑 `<仓库名>-<hash 前 8 位>` 兼顾可读与唯一。
- [x] ~~`.claude/rules/` 式的 `paths` 条件加载未做（06 spec 非目标，
      K memory.md 第六节）：本质是按需加载，与阶段 6 skills 同一机制。~~
      已交付 2026-08-26（[feature 36](features/36-20260826-path-scoped-instructions/README.md)）。
      与本文件「分层记忆」节那条是同一件事的两处登记，一并销账。
      注：最终没有与 skills 共用机制——skills 是「模型自己挑」，规则是「框架按
      路径塞」，两者的触发方式不同，共用的只有 frontmatter 解析这一小块。
- [ ] 指令消息作为普通 user 消息参与压缩切点计算（06 task 5）：它可能被切掉——
      现在靠重注入兜住了，但切点算法并不知道这条消息「特殊」。若将来指令很长，
      值得让 `find_cut_point` 显式跳过它。
- [x] ~~`set_memory_dir` / `set_notifier` / `set_origin_session` 是进程级全局
      （06 task 6 + feature 10 又加了第三个，同 D#40 的老问题）：
      测试靠 contextmanager 复位；一旦有并发（阶段 5）就要重新考虑。~~
      2026-08-11 并发真的来了，核实后这条担忧不成立（feature 11 Task 5）：
      三个注入点都是装配期写、执行期只读，线程并发下不构成竞争。
      真正需要加锁的是 `SessionLog.append`（多个工具同时回填结果会把 JSONL 写成半行），
      已加 `threading.Lock`。原条目保留：它记录的是「担心过、查过、结论是不用改」，
      比直接删掉有用。

### feature 05（REPL）遗留 —— 2026-08-10

- [ ] `Tool.run` 的返回契约分不出错误（05 task 1）：`ToolEnd.is_error` 只标得出
      loop 自己造的错（参数非法 / 未知工具），工具内部异常被 `Tool.run` 吸收成
      「错误：...」字符串，状态行因此标不出红叉。要真区分得改 `Tool.run` 返回
      `(text, is_error)` 或抛受控异常——影响面到每个工具，单独立项。
- [ ] steering 队列在 REPL 阶段无真实输入源（05 拍板问 2，诚实边界）：
      结构与注入点已在 loop 里备好、有假回调测试钉死位置，但阻塞的 `input()` 拿不到
      「agent 干活时打字」。TUI/流式阶段接真实输入源时才通电。
      2026-08-11 实测修正本条的定性（feature 12 反向对照）：那些字根本没丢——
      内核 tty 行规程替我们缓冲着，`!sleep 3` 期间打的字在命令结束后原样出现在
      下一个提示符上。所以缺的不是「独立输入线程」这么重的东西，在干活期间对
      stdin 做非阻塞读/`select` 就取得到。证据见
      [features/12 evidence](features/12-20260811-tui/evidence/20260811-终端反向对照/说明.md) 第 2 条。
      2026-08-13 由 [features/18](features/18-20260813-steering-input/README.md) 关闭：
      非阻塞读在 12 已做到（`driver.poll(timeout=0)` 挂在 loop 的每个事件上），
      18 补上的是「那些字进哪条队列、什么时候发出去」。
- [ ] `AgentStart.task` 在多轮 REPL 里语义歧义（05 task 5）：字段是「本轮的任务」
      而非「整个会话的任务」，多轮时名字容易误读。改名或拆事件，小事。
- [x] ~~`statusline._preview` 只取第一个参数值（05 task 8）：`bash` 只有 command
      正好，`edit_file` 这类多参数工具的预览只显示 path，够用但不精确。~~
      2026-08-26 对账核销（feature 35 复核）：「取第一个值」这个机制已在
      2026-08-18 的 `fix/bash-timeout` 里改掉，本条漏勾——现在按声明的主参数名取
      （`_PREVIEW_KEYS = ("command", "path", "name")`，认不出才退回第一个值）。
      当时是被 bash 的 `timeout` 参数当场引爆的：模型把它排在前面，状态行就显示
      光秃秃的「300」。剩下的「多参数工具只显示一个字段」是刻意取舍（一行状态行
      放不下第二个），代码注释里写着，不再当待办。
- [ ] REPL 无会话恢复（05 spec 非目标）：`messages` 只活在进程内，
      落盘仍是 append-only JSONL，没有 `/resume`。要做得先有会话树。
- [x] ~~`_install_sigint` 在非主线程装不上（05 task 7）~~ 2026-08-11 由 feature 12 关闭：
      结论是不把 REPL 挪到子线程（主线程持有 stdin/信号/loop，并发工具留线程池）。
      `TerminalSession.start()` 在非主线程时明确告警而不是静默退化，测试钉死。


- [x] ~~verify_compaction 的 tripped 单向性补测试（02 终审延后项）：置位后降线不回落，
      实现已双重审查确认正确（表达式 + 熔断后触发块整体跳过），3 行测试即可。~~
      已补 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：`test_tripped_is_one_way`
      （tripped=True 时喂一个降回线内的 prompt_tokens，failures 清零而 tripped 不落）。
      实现本来就对，所以做了注入反证：拿掉 `state.tripped or` 这一半即变红，
      装回即绿——这条测试不是走过场。
- [x] ~~AnchorBook.latest() 返回序与 entries 存储序相反（02 终审 Minor#6）：
      (tokens, index) vs (index, tokens)，未来调用者的坑；namedtuple 或统一序。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`），用户拍板选 NamedTuple：
      新增 `Anchor(index, tokens)`，entries 与 latest() 是同一种东西，调用方按名取。
      三处调用点（loop 触发块、`/status`、dock 的 refresh_context）一并改。
      顺带钉住一条此前无人保护的退化路径：无锚时判据必须是 `index is None`，
      拿 `tokens == 0` 当锚传下去会让工具 schema 那几百 token 从账上消失
      （`test_no_anchor_is_index_none_not_tokens_zero`）。
- [x] ~~context_window() 对非法 PAI_CONTEXT_WINDOW 裸抛 ValueError（02 终审 Minor#7）：
      make_client 有清晰报错先例，对齐。~~ 已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：
      非整数与非正数都在门口 `sys.exit` 说清是哪个 env、当前值是什么、该怎么配。
      顺带挡住 0 与负数——语法合法但会让 `window - reserve` 算出负预算，
      于是每轮都判"该压缩"，比当场崩溃难查得多。
- [x] ~~压缩后 session 审计流不含重建摘要消息（02 终审 Minor#8）：可由 cut+summary
      重建，但「每条消息落盘」字面已不成立，补一行注释说明重建规则。~~
      2026-08-25 对账核销（feature 34 复核）：已由 feature 24 会话格式 v1 关掉，
      本条漏勾。压缩落的是一条 typed `compaction` 条目（含 `summary` 与
      `firstKeptEntryId`），重建规则写在 `session.build_messages` 的 docstring
      里并有测试；摘要消息的 entry id 就取该条目自己的 id（pi 同款）。
- [x] ~~压缩后首个响应无 usage 时 awaiting_verify 永挂（02 终审 Minor#9）：与预算
      退化取舍一致属预期，补注释说明这是设计而非事故。~~
      2026-08-25 对账核销（feature 34 复核）：注释早已在 `loop.py` 的验证块上
      （"已知洞（R4#23，记档备参照）…DeepSeek 恒回 usage 故不触发；换 provider 时再兜"），
      本条漏勾。

- [x] ~~SYSTEM_PROMPT 硬编码四个工具名，与依赖注入矛盾（R3#5）：get_tools() 子集
      被真用到的第一天，提示词就在向模型撒谎。改为从 tools 注册表生成清单行。~~
      2026-08-25 对账核销（feature 34 复核）：已由 feature 22 的 `build_system_prompt`
      关掉（按实际工具集生成，指导语按"有没有这个工具"条件化），本条漏勾。
      三条生产路径（once、REPL、TUI）全部传 `system_prompt=build_system_prompt(...)`；
      常量只剩"不传 system_prompt 直调 run_agent"的兜底，且刻意逐字不变（护缓存前缀）。
- [ ] 截断逻辑 fs/shell 两处重复（R3#6）：第三个产出文本的工具出现时抽
      `truncate_output()` 进 tools/__init__.py，现在抽是过度设计。
- [x] ~~design_gate.py 与 once.py 补类型注解（R3#8）：修 R#14 时顺手一并带上。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：design_gate 的 `decide` / `main` / 内层
      `read` 都带上（`Optional[str]` 那两个参数正是"文件不存在"的语义所在）；
      once.py 的 `client=None` 随 R#14 的 `ChatClient` 一起补。
- [ ] loop 预算 fallback（R3#15，未核实）：provider 不回 total_tokens 时预算静默
      失效，可 fallback prompt+completion。DeepSeek 会回，仅记档。
- [x] ~~风格杂项（R3#16）：FROZEN_TOOL_SCHEMAS 缩进、test_loop 混用
      TemporaryDirectory、collect.py 裸 list 注解、loop 重复注释（R3#11）、
      server.py 冗余字符串注解（R3#12）。顺手为之，不单独立项。~~
      五条全清 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：缩进整段拉平（改完用
      `ast.literal_eval` 比对 HEAD，值逐字未变——冻结夹具改缩进也得证明没改内容）；
      `test_anchor_does_not_double_count_the_assistant_message` 换 `tmp_path`；
      collect.py 五处裸 `list` 补成 `list[dict]` / `list[str]`；
      loop 的 usage 透传理由改成指向 `usage_fields` 的 docstring，不再抄第二遍；
      server.py 四处字符串注解拆掉（文件本就有 `from __future__ import annotations`）。

- [x] ~~decisions 第 8 条与第 6 条自相矛盾（R#5）
      第 6 条说「低估是唯一会炸窗口的方向」，第 8 条却让未知 role 静默记 0——
      0 是最极端的低估。改为按 content 估算（宁可高估）或留告警路径。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`），用户拍板选"按 content 估算"：
      `estimate_tokens` 一概不看 role，未知 role 与已知 role 同算法（含 tool_calls）。
      拍平那一半原样保留（`serialize_conversation` 仍跳过未知 role）——秤问
      "占不占窗口"、拍平问"要不要塞进摘要请求"，是两个问题。
      [D#8](decisions.md) 已记推翻，原理由划掉保留。
- [x] ~~decisions 第 9 条理由不成立（R#6）
      「严格大于防阈值横跳」防不了——边界上 `>` 与 `>=` 只差 1 token。真防横跳的是
      压缩后落点远离警戒线。结论无害但理由错。
      改法：保留原理由作为划掉的记录，不要删除——决策文档里「曾经这么想、后来被指出
      为什么错」的痕迹，是「我的决策可被挑战」最有说服力的证据。~~
      已改 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：[D#9](decisions.md) 原理由划掉保留，
      下面补上为什么它不成立、以及保留严格大于的真实（且更小的）理由。代码未动。
- [x] ~~decisions 第 7 条引用链未回收（R#20）
      其理由引用的「400 字符=100 token 心智模型」已被第 15 条废弃（结论仍成立）。~~
      已改 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：[D#7](decisions.md) 补记引用链回收，
      写明结论仍成立但不该再用作废的心智模型去论证它。原论证保留。
- [x] ~~单轮多 tool_calls 无测试覆盖（R#11）
      所有测试脚本每轮只有一个 tool_call；「N 条 tool 消息按序配对」「合法+未知工具混同轮」
      两个配对不变量无测试。DeepSeek 会发并行工具调用，非假想场景。~~
      2026-08-25 对账核销（feature 34 复核）：与本文件 P0 节那条同一件事，那边
      2026-08-24 已核销、这边漏勾。测试 2026-08-09 随 commit 8a0ccd7 进库：
      `test_parallel_tool_calls_each_get_a_reply` 与
      `test_parallel_tool_calls_mixed_known_and_unknown`。
- [x] ~~`session.py` 文件名精确到秒（R#15）：同秒创建两个 SessionLog 会写同一文件。~~
      2026-08-25 对账核销（feature 34 复核）：文件名早已是
      `{%Y%m%d-%H%M%S}-{session_id[:8]}.jsonl`，同秒的两个 SessionLog 各带自己的
      随机 id 短码，撞不到一起（要撞得 uuid4 前 8 位相同）。本条漏勾。
      同秒真正还剩的问题是 `--resume` 挑"最近一次"时并列，已单独修（见 24 遗留那条）。
- [x] ~~抽出共享测试夹具层（对照 pi 的 `test/harness/session-test-utils.ts`、`test/utils/`）：
      夹具各自为战，改一处可能让多处假失败。触发条件：测试文件到 10 个左右。~~
      已做 2026-08-26（[feature 40](features/40-20260826-old-debts/README.md)）。
      触发条件早就过了——发现时 80 个测试文件、1503 条用例。
      比行数更实的证据是跨测试文件的 import 已有 5 处（`from tests.test_skills import _repl`、
      `from tests.test_recall import reply`、`from tests.test_memory_scan import write_memory`、
      `from tests.test_compaction import REAL_TRAJECTORY / REAL_USAGE_TRAJECTORY`）——
      测试文件 A import 测试文件 B，意味着 B 的任何改动都可能让 A 假失败而 A 的作者不知道。
      落点两个：`tests/helpers.py`（`OPEN_RULES`、`scripted_reader`、`write_memory`、
      `recall_reply`、`run_repl`）与 `tests/trajectories.py`（真实轨迹夹具 + 出处 + 诚实边界）。
      跨测试文件的 import 归零（剩下的 `fake_llm` / `tui_screen` 本就是 helper 模块不是测试）；
      `_OPEN` 从 5 份变 1 份、脚本化 reader 从 5 个变体变 1 个。
      搬家验收不是「测试还绿」：拿 HEAD 的旧实现与新 helper 对同一批输入比值
      （`write_memory` 3 组含 mtime、`recall_reply` 3 组），逐字相等；
      全量测试数 1503 不变——纯搬家最好的证明就是数字一个不动。
- [x] ~~`compaction.py` 拆成目录的触发条件：现在 189 行……等 `summarize` 落地
      （预计 +300 行）再拆，拆法照 pi。~~
      2026-08-26 重估：不拆（[feature 40](features/40-20260826-old-debts/README.md)）。
      触发条件的字面（summarize 落地）满足了，但它自带的两个参照都不支持动手：
      条目自己写着「pi 的 compaction.ts 到 893 行才拆」，而这边落地后是 392 行
      （summarize 只有 34 行，不是预估的 +300）；更硬的一条是 AGENTS 架构约束
      「模块边界按学习阶段切：一个阶段一个模块」——compaction 就是阶段 1，
      拆成 5 个文件与那条约束直接相抵。
      重估的判据留给下次：`compaction.py` 超过 800 行，或它开始装第二个阶段的逻辑。

### feature 34（TODO 存量批清）复盘引出 —— 2026-08-25

档案：[features/34](features/34-20260825-todo-backlog-batch/README.md)、
[复盘](features/34-20260825-todo-backlog-batch/复盘.md)

- [ ] 第三个可变持有者出现时抽成泛型 `Ref[T]`（34 复盘质疑一）：`AskerRef` 与
      `EventSink` 现在是两个几乎一模一样的 `get/set/__call__`。两份还不构成模式，
      第三份就该抽——形状已经想好，触发条件是「又一个装配期烤进闭包、运行期要换的东西」。
- [ ] 装配为什么必须在 TUI 之前（34 复盘质疑二）：两个可变持有者可能都是同一个
      更深问题的症状——装配期就要用真人通道（skills/MCP 信任门禁要问人），
      于是 UI 还没建好。顺序若能反过来，两个持有者都不需要。
      目前只是怀疑，没有证据支撑到能提方案，先记着。
- [x] ~~`read_file` 的截断提示没有真模型验证（34 复盘质疑三）：本轮按 R#17 的
      「零成本做法」写了提示语，但「模型会不会真按提示去 `sed -n` 分段读」完全没验过——
      离线测试只能断言提示语里有那几个字。倾向于 offset 参数才是正解（那是可测的），
      零成本做法只是把成本转移给了模型。验收要么一次 `--llm` 冒烟，要么老实做 offset。~~
      已做 2026-08-26（feature 41，`feat/41-daily-driver`）（取「老实做 offset」那条）：
      `read_file(path, offset, limit)` 按行分段，0 哨兵（`Optional[int]` 会被
      `PY_TO_JSON` 当场拒，同 `clamp_timeout`）。验收按用户点名的判据做成
      「解析后的值逐字相等」——分段读拼回全文，不是「测试还绿」。
      截断改切在整行边界，文案给出的续读 offset 逐字接得上（切在行中间的话那半行
      要么丢要么重复，而两种错都不会让别的断言变红，专门钉了一条）。
- [ ] 给「漏勾」建一条可执行检查（34 复盘「下次怎么做更好」）：三次交付里都出现过
      「其实早就修了、只是没回来划掉」（2026-08-09 / 2026-08-24 / 2026-08-25 各一批）。
      不是记性问题是流程缺口——修的时候在别的档案里，销账要回全局 TODO，而那是纯自觉动作。
      做法：写复盘前拿 `git diff --name-only` 的文件名/函数名去 grep TODO 的开放条目，
      逐条问「这次是不是顺手把它关掉了」。五分钟的事，且正对着漏勾发生的机制。

### feature 40（还旧账）遗留与发现 —— 2026-08-26

档案：[features/40](features/40-20260826-old-debts/README.md)、
[复盘](features/40-20260826-old-debts/复盘.md)

- [ ] 方法论欠账还剩 6 条（40 遗留）：本轮清掉 6 条（2 篇新笔记 + 2 处追记 +
      instruments-lie 骗法五），剩下的要么已并进这几篇、要么是「工程习惯小条」
      不够独立一篇（如「替换文件内容前先断言 start < end」）。
      下次写笔记时顺带把够格的并进去。
- [ ] 登记「够格升格」时要写对落点（40 发现）：6 条欠账里 5 条指着
      `knowledge/concepts/`，而那个目录早就并进 `knowledge/engineering/` 了。
      「登记时写错落点」比「忘了写」更常见，而错落点让人以为那篇要新开一个分类。
      改法：登记时写具体文件名（哪怕还不存在），不写目录。
- [ ] `tests/helpers.py` 有变成杂物间的苗头（40 复盘质疑一）：它装了 4 样东西，
      各自与不同子系统有关，今天的共同点只有「被两个以上的测试文件用」——
      这个共同点撑不起一个模块的语义。第三次往里加东西时按主题拆
      （`helpers/memory.py`、`helpers/repl.py`），不要继续往一个文件里堆。
- [ ] 命令簇的函数签名普遍很长（40 复盘质疑二）：`_handle_command` 收 14 个
      keyword。根因不是搬家，是没有「会话对象」把跨轮状态装起来——
      与 24 复盘那条「跨轮平行状态已三件，到第四件该封 Session」是同一件事。
      聚到一处之后这个缺口更显眼了：14 个参数并排放比散在两处更难看。
- [ ] 触发条件要写清「谁在什么时候来查」（40 复盘「学到了什么」）：本轮两件事的
      触发条件早就满足却一直挂着，不是判据写得不好，是判据没有查的人。
      改法：写触发条件时同写「它会在哪个动作里被顺带检查到」（下次动这个文件时 /
      每次批清时），不要让它悬空等着。

### feature 39（干活期间的心跳）遗留 —— 2026-08-26

档案：[features/39](features/39-20260826-busy-heartbeat/README.md)、
[复盘](features/39-20260826-busy-heartbeat/复盘.md)

- [x] ~~MCP 工具调用期间没有心跳（39 遗留，与刚修好的是同一个病）：
      `core/mcp.py` 的 `_request` 是一次 `event.wait(总时长)`，没有轮询循环——
      一个慢的 MCP 工具（默认超时 60s）期间键盘照样像死了。~~
      已修 2026-08-26（!小修，`fix/mcp-heartbeat-and-interrupt`，用户当天指示
      「MCP 那条也修了吧」）：`_wait_for` 小步等（`WAIT_STEP_SECONDS = 0.1`，与
      shell 的 `POLL_SECONDS` 同值同理由），每步 `heartbeat.current().beat()`。
      顺带把中断也接上（用户当场拍板「中断 + 把代价说出来」）：等待期看中断标志，
      置位就不再等，而回填的话里明说 server 没收到取消信号、可能仍在执行、
      已产生的副作用不会回滚——这与 bash 那条不同（那边我们真能杀进程组），
      不说的话「已中断」就是半真话。MCP 协议的 `notifications/cancelled` 仍不发
      （spec 非目标，取消语义要连 progress 一起做，见 29 遗留 2）。
      三条测试 + 四处注入反证（不跳心跳 / 不看标志 / 文案不提 server / 退回一次性等待，
      各自会红）。
- [ ] `POLL_SECONDS = 0.1` 现在承担两个职责（39 复盘质疑一）：中断响应粒度
      （原本的）与界面刷新粒度（feature 39 新加的）。两者对「多快算够」的要求不同
      ——中断 100ms 绰绰有余，打字回显 100ms 已在人能感觉到的边缘。
      真要分开得给 `_wait` 两个节奏，本轮判为不值当；这个耦合是 39 制造的。
- [ ] `!命令` 期间打字现在会进 steering 队列（39 复盘质疑三）：此前那些字留在
      输入行里、命令结束后才可见。改成共用 `pump_keys()` 之后语义跟着变了，
      理由是「与模型调 bash 时保持一致」——但那是顺口的说法不是证据。
      真实使用里可能有人就想在命令跑着时先把下一句敲好、看完输出再回车。撞到再议。
- [x] ~~「操作系统本来替我做了什么」应列成清单（39 复盘「学到了什么」）：
      一段代码把输入通道的语义从「操作系统替你处理」换成「我自己处理」时
      （raw mode / 非阻塞 IO / 自己解析协议），要逐条接管——ISIG 就是被漏掉的那条，
      漏了十五天没人发现，因为它的症状（Ctrl+C 按不停）不像 bug 像「命令就是慢」。
      够格进 knowledge/engineering，与既有那几篇同族。~~
      已回流 2026-08-26（feature 40）：写进
      [K engineering/process-groups-and-interrupts.md]
      (../../knowledge/engineering/process-groups-and-interrupts.md) 第六节
      （raw mode 关掉的不只是行缓冲，还有 ISIG/ICRNL；漏掉的共同症状是
      「某个键没反应」，而它太容易被解释成「程序在忙」）。

### feature 38（离线与真实的差距）遗留 —— 2026-08-26

档案：[features/38](features/38-20260826-offline-real-gap/README.md)、
[复盘](features/38-20260826-offline-real-gap/复盘.md)

- [ ] 手工清单尚未被人跑过（38 遗留）：`features/38/evidence/手工清单.md` 六节
      （IME 候选框、resize 视觉残留、颜色与 NO_COLOR、鼠标拖选、退出与 --resume
      提示、规则与记忆的真跑佐证）。第三类差距本轮只做到了「有清单」，
      没做到「验过」——清单末尾已如实写明。
- [ ] 两条 `--llm` 冒烟尚未被跑过（38 遗留）：`remember` → 召回全链、
      路径作用域规则模型听不听。写不花钱、跑才花钱（`./test.sh --llm`），
      等你决定花那几分钱。
- [ ] `--llm` 冒烟自己也是「写了没验」（38 复盘质疑一）：它们默认跳过，
      写错了要等到有人花钱才发现——正是本轮要治的那类病的小号。
      更好的做法是把管线与行为断言拆开（管线对着假 provider 跑，行为断言只在真
      模型下跑），本轮没做是因为要把测试拆成两半、结构变复杂。
- [ ] 压缩 e2e 用的配置处在已知退化区（38 复盘质疑二）：
      `PAI_CONTEXT_WINDOW=20000` 配默认 `reserve_tokens=16384`，实际阈值只剩 3616。
      这条 e2e 验的是「压缩链路能跑通」，不是「压缩在正常配置下会被恰当触发」。
      后者要么等真实长会话，要么把 `reserve_tokens` 也做成可配——倾向于后者。
- [ ] `.pai/rules/tests.md` 没验过（38 复盘质疑三）：仓库自己那条规则写完就交付了，
      它现在的状态和它要治的病一模一样。与手工清单第六节一起验。
- [ ] 把 `AGENTS.md` 按路径拆薄，要先解决 Claude Code 那半边（38 交付时的修正）：
      `CLAUDE.md` 只 `@AGENTS.md`，内容搬进 `.pai/rules/` 之后 pai 省了常驻、
      Claude Code 那边就看不见了。两个消费者的加载机制不同，同一份内容不能同时满足。
      可能的出路：规则文件里放指针而非正文，或让 AGENTS.md 自己按 `@` 导入拆分的片段。
- [x] ~~「离线结论与真实观察相反时要当最高优先级线索」值得进流程
      （38 复盘「下次怎么做更好」）：本轮那条缺口能拖十几天，就是因为用户
      2026-08-10 报告「压缩一次都没触发」与离线全绿两边各记各的，谁也没被逼着
      回答「那绿的是什么」。做法：真实使用报告的现象若与离线结论相反，
      登记时必须同写一句「离线那边绿的是什么」。~~
      已回流 2026-08-26（feature 40）：写进
      [K engineering/todo-drift.md](../../knowledge/engineering/todo-drift.md)
      的「两条配套纪律」，并在 green-but-which-path.md 的操作纪律里互指。

### feature 37（改写事件）复盘引出 —— 2026-08-26

档案：[features/37](features/37-20260826-context-rewritten-event/README.md)、
[复盘](features/37-20260826-context-rewritten-event/复盘.md)

- [ ] 跨轮状态的作废挂在观测通道上是一次耦合升级（37 复盘质疑一）：
      谁把 `on_event` 换成会吞异常或过滤事件的实现（给 viz 做事件采样、
      headless 模式关掉观测），召回与规则的去重表就会静默不失效。
      观测流按定义是可丢的（`EventTrace` 写失败只 warn 一次），而正确性不该建在
      可丢的东西上。触发条件：观测流真的开始被采样/过滤时，第一个查它。
- [ ] `CONTEXT_REWRITING` 加新成员靠人记得（37 复盘质疑二）：防漂移测试只校验得了
      「集合里每个都是真事件」，校验不了「每个会改写上下文的事件都在集合里」——
      与 TurnStart 那次同族（登记表校验不了「真有人发」）。真能防住的写法是把
      「我会改写上下文」变成事件自己的属性（标记 mixin / dataclass 字段），
      代价是动 events.py 的扁平 dataclass 联合这个既有设计，本轮判为不划算。
- [ ] 「用两个锚点之间替换文件内容前先断言 start < end」值得进工程习惯清单
      （37 复盘「哪里走了弯路」）：区间取反不会报错，只会静默把一段内容抄两遍，
      而复制出来的测试照样全绿。本轮靠 `grep -c` 数函数定义才发现。

### feature 36（路径作用域规则）遗留 —— 2026-08-26

档案：[features/36](features/36-20260826-path-scoped-instructions/README.md)、
[复盘](features/36-20260826-path-scoped-instructions/复盘.md)

- [ ] `bash` 里的 `cat`/`sed` 不触发规则加载（36 已知豁口）：bash 不声明路径
      语义（同 D#52「bash 不参与目录边界判定」），`core/rules.py` 的模块注释与
      一条测试把它写在明面上。要堵得先给 bash 一套路径提取，那是 D#52 的复议，
      不是本功能的事。
- [ ] `MAX_RULE_CHARS = 4000` 与 `MAX_RULES_PER_STEP = 3` 未实测（36 遗留）：
      与 `reserve_tokens`、skills 四常量同类账，来路已写在常量旁。
      追记（36 复盘质疑一）：`MAX_RULES_PER_STEP` 按条数截可能就是错的形状——
      三条各 3000 字符比五条各 200 字符贵得多，而现在前者放行后者被截；
      正确的大概是按累计字符截（单篇已由 `MAX_RULE_CHARS` 管住）。
      改它要先想清「超了先丢谁」，等真实数据。
- [ ] 规则的效果没有真模型验证（36 遗留）：离线测试只能断言「正文进了 messages」，
      「模型会不会真按规则做事」没验过。与 34 复盘质疑三（read_file 截断提示
      没有真模型验证）同族，验收要么一次 `--llm` 冒烟，要么等 dogfooding。
- [ ] 「触发面含写/编辑」这条偏离官方的选择没有证据（36 复盘质疑三）：
      理由是「一条 `src/**/*.py` 的规则在改这个文件时同样该生效」，听起来合理，
      但官方只在读时触发可能有它的道理（写之前通常先读过，重复触发是浪费）。
      真跑起来若发现规则总被 write_file 触发而那时模型已经读过一遍，这条该收回。
- [x] ~~`on_context_rewritten` 该升格成事件的证据更足了（36 复盘质疑二，
      与 35 复盘质疑二同一条）：两个消费者（召回去重表 + 规则注入表），
      而 loop 已经在同一位置发 `Compacted`；拖着的成本是每加一个消费者就要多穿
      一遍参数——feature 36 穿了六个调用点。~~
      已升格 2026-08-26（[feature 37](features/37-20260826-context-rewritten-event/README.md)，
      用户指示「把 on_context_rewritten 升格成事件」，形状拍板选 A·事件集合常量）：
      `events.CONTEXT_REWRITING = (Compacted, ConversationCleared)` 是「哪些事件
      意味着上下文被改写」唯一的家；装配层给出一个事件监听器并联进 on_event，
      `run_agent` 的参数与八个调用点的穿参数全部消失（src 里 28 处引用 → 0）。
      行为逐字不变，纵切钉住（`/clear` 之后召回能重来）。
- [x] ~~「两个坐标系恰好相等的测试证明不了任何东西」值得记进方法论
      （36 复盘「学到了什么」）：本轮那个真 bug（相对路径按项目根解析，而模型
      给的是相对 cwd 的）之所以七条测试全绿，是因为测试都在项目根下跑，
      cwd 与项目根重合。与既有那两条方法论同族（都是「测试环境的巧合掩盖了
      真实路径上的分歧」），写的时候一起收。~~
      已回流 2026-08-26（feature 40）：同上那篇的第三节，判据写成可执行的一句——
      只要代码在两个坐标系之间搬运（cwd/项目根、本地时间/UTC、字节/字符/列宽），
      就必须有一条测试让这两个坐标系不相等。

### feature 35（TODO 存量批清第二轮）复盘引出 —— 2026-08-26

档案：[features/35](features/35-20260826-todo-backlog-batch-2/README.md)、
[复盘](features/35-20260826-todo-backlog-batch-2/复盘.md)

- [ ] AGENTS.md 该「读多少」值得复议（35 复盘质疑一）：本轮拍板解决的是
      「读不读」，代价面比问的时候说的更宽——任何用 pai 的仓库，它的
      `AGENTS.md` 都会每轮常驻，而那份文件通常是写给「开发这个仓库的人/AI」的
      （构建命令、测试规约、提交格式），与当轮任务的相关性未必高。
      CC 至今仍不直接读它、让用户显式 `@` 导入，不见得只是保守。
      真正该议的是常驻整篇 vs 相关时才加载——与「没有路径作用域规则」
      （`.claude/rules/` + `paths:`）是同一件事，做时一起。
- [x] ~~`on_context_rewritten` 可能该是一条事件而不是回调（35 复盘质疑二）：
      装配层要回调、观测流要事件，各修各的。合并的前提是先想清 `/clear` 那条路
      的关系（它发的是 `ConversationCleared`）。~~
      已升格 2026-08-26（feature 37）：与 36 复盘质疑二是同一条，一并销账。
      `/clear` 那条路的关系答案是「两条事件都算改写，判据进一个具名常量」——
      不新增第三条事件（那会让一件事有两个名字）。
- [ ] 「参数不是 dict 属于常态」这个判断没有数据（35 复盘质疑三）：
      能力判定的三条退化路径本轮只给「判定器崩溃」留了痕，另两条判为常态是
      推理不是实测。真跑起来若发现并发频繁退化成串行，第一个该查的就是它。
- [x] ~~给「够格升格 knowledge/concepts」建一个触发点（35 复盘「下次怎么做更好」）：
      TODO 里现在躺着四条「够格升格成方法论笔记」（2026-08-10 一条、
      2026-08-19 两条、35 复盘一条），全停在「够格」上没人动——不像遗留问题
      有「必须同步登记 TODO」的硬规矩。做法：交付前扫一遍本轮 devlog 与复盘里
      的「够格升格」字样，有就当场写；写不出 pai 锚点就降级成 TODO 一行说明
      为什么写不出，不留「以后再说」。~~
      2026-08-26 部分兑现（feature 40）：这一批 12 条欠账清掉 6 条（2 篇新笔记 +
      2 处追记 + instruments-lie 骗法五），剩下的要么已并进这几篇、要么是
      「工程习惯小条」不够一篇。触发点本身没做成机器检查——`knowledge/concepts/`
      这个目录早就并进了 `knowledge/engineering/`，而 6 条欠账里有 5 条还指着它，
      说明「登记时写错落点」比「忘了写」更常见。改法登记在下面一条。
- [x] ~~本轮那条方法论本身还没写（35 复盘「学到了什么」第一段）：
      「待办清单会随代码漂移而失真，且失真不止过期一种——还有『修法当初想对了、
      后来前提变了』与『当初只看见半个问题』；所以复核要问三问：它还在吗、
      修法还成立吗、是不是只写了一半」。本轮 15 条里有 5 条属于这三类。
      与既有那条「测试为了让被测路径跑起来而注入的参数，正是真实路径上会卡住的
      地方」同族（都是记录与现实的漂移），写的时候一起收。

## P3 · 可选~~
      已回流 2026-08-26（feature 40）：写成独立一篇
      [K engineering/todo-drift.md](../../knowledge/engineering/todo-drift.md)——
      四种失真（已修没划掉 / 修法前提变了 / 只看见半个问题 / 触发条件早已满足
      但没人回来查）、复核三问、两条登记纪律。四种失真里有三种是这三轮批清
      逐条复核时实测到的，不是推理出来的。
- [x] ~~`loop` 的 `client` / `response` 无类型注解，违反自家规矩（R#14）。
      可给最小 Protocol（`chat.completions.create`），顺带静态约束 FakeClient 同构性。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：新增 `core/protocols.py` 的
      `ChatClient`（runtime_checkable Protocol，只描述 `chat.completions.create`
      这一条路径），接进 `run_agent` / `summarize` / `compact` / `make_recall` /
      `assemble` / `run_once` 六处；两条测试钉住 FakeClient 合规、以及
      Protocol 没宽到什么都通过。`response` 如实写 `Any` 并说明为什么
      （流式装配后是 pai 自己的结构、各家 SDK 类型不通用，写死任何一个都是撒谎）。
- [x] ~~`read_file` 截断后无分页/offset，模型可能基于残缺视图去 edit（R#17）。
      零成本做法：在截断提示语里建议模型用 bash 分段读。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）（取零成本做法）：提示语改成说清
      "以上是前 N 字符 / 全文共 M 字符"、点名 `sed -n '起始,结束p'` 分段读、
      并明说别拿这份残缺内容直接去 edit_file。真正的分页/offset 参数仍没做。
      追记 2026-08-26（feature 41）：offset/limit 已做，提示语改指自家 offset，
      不再教模型走 `sed -n`。唯一仍指回 bash 的是「整个文件就一行、而这一行超上限」
      那一格——续读点在行内，行坐标系表达不了，见下面新登记的那条。
- [ ] `session=None` 时也每步计算 `estimated`，纯浪费（R#18，量极小）。
- [ ] `estimate_tokens` 假设 content 是 str/None；OpenAI 协议 content 可为分段列表，
      接多模态前要处理（R#19）。
- [ ] 预算改按钱算（2026-08-03，措辞已修正）。命中缓存比未命中便宜 50 倍，
      同样 token 数花的钱可差两个数量级。此前记为"单价会变所以是维护债"——这个判断下早了：
      pi 有现成答案（`ai/src/models.ts:639` `calculateCost`），把费率放进 model registry 而非代码，
      四档分别乘单价（input / output / cacheRead / cacheWrite），
      且支持分层价格 `tiers`（按 `inputTokensAbove` 切档）——DeepSeek 的峰谷定价可用同一机制表达。
      所以不是"不该做"，是需要先有一个费率表结构。
- [ ] usage 归一化：算出"真正新计算的 input"（2026-08-03）。
      现在原样透传 provider 字段（保住 `prompt_cache_hit_tokens` 是对的），但缺一步减法。
      pi 的语义（`api/openai-completions.ts:1337`）：`prompt_tokens` 是含缓存的总数，
      `input = prompt_tokens - cacheRead - cacheWrite`，`totalTokens = input+output+cacheRead+cacheWrite`。
      按钱算预算的前提就是这个减法。注：pi 明确兼容了 DeepSeek 的 `prompt_cache_hit_tokens` 字段。
- [x] ~~接流式前必修：并行工具调用会让 usage 重复累加（2026-08-03）~~ ——
      2026-08-11 前提被实测推翻，本条降级为「不适用」（feature 11 前置精读的反向对照）。
      原文保留：CC 注释（`utils/tokens.ts:28`）说并行工具调用流式返回时，每个 content block
      会成为一条独立的 assistant 记录，但共享同一个 `message.id`，天真累加就是重复计费，
      CC 为此有 `getAssistantMessageId` 识别同源记录；当时判断「pai 接流式后必然撞上」。
      错在哪：那是 Anthropic 协议的形状带来的，不是流式的固有属性。pai 走 OpenAI
      兼容协议，实测一次流式响应只有一份 usage（2 个并行 tool_calls、1 份 usage，
      流式与非流式一致），证据见
      [features/11 evidence](features/11-20260811-streaming/evidence/20260811-流式探针/说明.md)。
      仍需警惕的是自己造出来：若 pai 为了边流边显示把一次响应拆成多条 assistant 记录，
      就会亲手复制这个 bug。判据写进
      [K streaming/streaming-tool-calls.md](../../knowledge/streaming/streaming-tool-calls.md) 第四节。
      与「单轮多 tool_calls 无测试覆盖」（R#11）仍是同一场景的两面，R#11 那条不受影响，照做。
- [ ] 接流式后真正会咬人的是这两条（2026-08-11 探针替换上面那条，归 feature 11）：
      ① usage 的取法——`stream_options.include_usage` 在 DeepSeek 上是空操作，
      usage 永远在末块且 `choices` 非空；OpenAI 生态惯用的
      `if not chunk.choices: usage = chunk.usage` 分支永不触发 → 预算熔断与锚点一起静默哑掉。
      稳妥写法是「每块都看一眼 `chunk.usage`，最后一个非空的就是它」。
      ② 中断掉的流拿不到 usage（它在末块，而我们没读到末块）→ 被中断请求的消耗
      不进 `spent_tokens`，且偏差方向恒定（总是少算）。与下面「usage 可信度过滤」同源。
- [ ] usage 可信度过滤（2026-08-03）。两家都不直接信原始返回：
      pi 排除 `aborted` / `error` / 全 0；CC 排除合成消息（`SYNTHETIC_MESSAGES`，
      中断等场景注入的假 assistant 消息带假 usage）。
      pai 现在只判 `usage is None`，够用但不完整——接中断/重试后要补。
- [ ] 无跨会话累计预算（2026-08-03）。每次 `pai` 调用各自计数。真正的总闸是账户只充小额。
- [ ] `GET /user/balance` 未接入。可做 `pai --balance` 或启动时低余额告警。
- [ ] 官方离线 tokenizer（`deepseek_v3_tokenizer.zip`）未下载。能给精确值，
      但引入依赖且是 v3 版（当前用 v4），暂缓。
- [x] ~~`pai_playground/sessions/` 已被 .gitignore 排除，而测试夹具的原始出处在那里——
      溯源链断了~~ 2026-08-11 由 feature 12 T6 关闭：新增 `tests/fixtures/`，
      `real_turn.jsonl` 从 `pai_playground/sessions/20260803-000946.jsonl` 抄入（剥 `ts`），
      出处写进 `tests/fixtures/README.md`。既有内联夹具未追溯。
- [ ] `refs/README.md` 列的「常查页」清单，在知识库不入库后只有生成过的人能用。
      若协作者频繁需要，改为链接官网对应页。
- [ ] pai-viz 子进程 30s 超时值无实测依据（2026-08-03）：照拍脑袋定的，随功能变大
      （collect.py 干的事变多）再看是否够用。
- [ ] pai-viz 不做自动刷新（2026-08-03，YAGNI）：现状是点按钮手动刷新；
      若用起来发现手动刷新烦，再加。
      2026-08-13 由 feature 17 关闭：结构图照旧手动刷新；时间线是 2s 游标轮询
      （对象不同：当时不做刷新针对的是静态结构图，流转本身是时间性的，不刷新等于没做）。
- [ ] pai-viz 的会话回放、用量仪表盘未立项（2026-08-03）：以后有需要再单独立项设计，
      不是本轮 viz 范围。
      2026-08-13 更新：会话回放已由 feature 17 交付（跨项目会话下拉 + 逐步展开 +
      未完成回合标红）；用量聚合仪表盘仍未立项（17 只做单会话内的每步用量）。
- [x] ~~TUI 下 `MemoryWritten` / `RecallFailed` 直接打进 stdout，可能弄花 dock
      （2026-08-13，P2，出处：17 的 T3.5 顺带发现）：`memory_tool.set_notifier` 与 recall 的
      `on_failure` 闭包用的是外层 `on_event`（默认渲染器），而 TUI 自建了走
      `app.on_event` 的本地版本。feature 12/13 就存在的老问题，非 17 引入；
      修它要动 TUI 的事件路由，超出 17 范围。~~
      已修 2026-08-25（feature 34，`fix/34-todo-backlog-batch`）：事件通道改走可变持有者
      `EventSink`（与 2026-08-11 那次 asker 卡死同一个形状，所以照 `AskerRef` 的样子做），
      装配层收 sink，`_run_tui` 建好 app 之后一处 `set`，装配期烤进闭包的
      记忆通知 / 召回失败 / 召回命中三条一起跟着走。
      两头各钉一条测试：sink 换完之后事件不再流回旧通道；以及 `_run_tui` 真的换了它
      （在 `term.start()` 上引爆跑到那一行，不断言源码文本）。
      注入反证：拿掉那句 `event_sink.set(on_event)` 即变红。
      本条与下面第二处是同一件事重复登记，那一处已合并删除。
- [ ] 事件流文件（`*.events.jsonl`）无上限增长、无清理策略（2026-08-13，P2，
      出处：17 的 T1-T3）：`<session>.events.jsonl` 与会话同寿，长会话会一直长；
      也没有「删旧会话」的入口。观测流是可再生数据，删了不损失历史，
      所以清理策略是纯运维问题，17 不做。
      （2026-08-25 去重：本文件下方原有第二条同内容登记，已合并到这里。）
- [x] ~~`viz/collect.py` 的 `_stage_key` 剥反引号只剥两端（2026-08-12，P1，出处：17 立项
      时对真实 STATUS.md 实跑发现）：`` `core/tools/` 的 matcher `` 这行解析出
      `key="\` 的 matcher"` 垃圾键；`strip("\`")` 碰不到中间的反引号。现有一致性测试只查
      pipeline→stages 方向，反向畸形不变红。修法：先剥别的再剥反引号，或对 key 加
      「合法标识符形状」断言。~~ 2026-08-13 由 feature 17 T6 关闭：
      改为先剥全部反引号再拆路径，散文式单元格取最后一个标识符样的词当 key
      （`matcher`），整句留给 label；新增反向断言测试
      `test_stage_keys_are_clean_identifiers`。
- [x] ~~`@tool` 注册表是进程级全局，测试注册的工具会漏进后续测试
      （2026-08-13，P2，出处：feature 17 T6）：`tests/test_tools.py` 的探针工具
      （如 `_cap_bool_probe`）会出现在别的测试文件看到的 `get_tools()` 里，
      于是「单跑绿、全跑红」。本轮绕开（断言只针对四个内置工具），
      根治要给注册表加测试级隔离 fixture。~~
      2026-08-25 对账核销（feature 34 复核）：根治已于 2026-08-19 做完（R4#T5），
      本条漏勾——`tests/conftest.py` 的 autouse fixture `isolate_tool_registry`
      按测试隔离 REGISTRY，注释里连"此前靠字母序苟活"都写着。
- [ ] viz 时间线不显示金额、也无会话级合计（2026-08-13，P3，出处：feature 17 T8 用户裁决）：
      刻意不建价格表（定价会变，token 才是 ground truth）；会话级合计用户明确说不加。
      若日后要看成本趋势，先立「用量聚合」独立档案。
- [ ] scheduler 并发批与 queue 进出无事件源，页面上看不见（2026-08-13，P2，
      出处：feature 17 spec「刻意不做」）：并发做了却看不见并发（同 STATUS 已知缺陷）。
      补事件源要动 `core/scheduler.py` 与 `core/queue.py`，是下一轮的事。
- [ ] 面试准备仓库加反向链接指向 pai knowledge/（2026-08-09，D#35）：
      在其 04_Harness 专题 README 加一行即可。属另一仓库的独立小改动，在这里备忘。
- [ ] microcompact 评估（2026-08-09，K context/cc-compaction.md）：
      触发条件已满足（阶段 1 压缩闭环 2026-08-09 已跑通接进 loop）——pai 的 4 个工具
      全部可重放，按 tool_call_id 清旧结果
      不用调模型，可能是性价比最高的第二级压缩。
- [x] ~~R2#1 残余：anna 披露边界的最终确认~~ 已裁决 2026-08-09：不入库，本地保留。
      `knowledge/anna/` 与 `reviews/2026-08-09-体系评审.md` 进 .gitignore；
      一致性测试对 gitignored 目标放行（新克隆不算断链）。
      代价如实记（gates.md 头部同步声明）：gates.md 从此无版本控制无备份，
      「给 anna 方法论留带版本控制的沉淀」的初衷未达成，防丢靠本地。
- [ ] gates.md 与体系评审文件的本地备份（R2#1 裁决的衍生）：两文件不入库后无任何
      备份，anna 原目录也非 git——是否给它们做个私有备份（私有 gist / 本机第二位置），
      用户定。
- [ ] design_gate 真实会话验收（2026-08-09，features/03-20260809-design-gate）：hook 配置
      快照机制下本会话注册可能不生效——下次会话故意在未拍板状态改一次 src/，
      实测被拦后把档案状态转「已验收」。
- [ ] 超长单轮的复杂兜底（2026-08-09，features/02-20260803-compaction spec 非目标节）：
      本轮裁决「不压 + 警告，靠预算熔断兜底」；若窗口变小或警告日志真实出现，
      再设计轮内清工具结果 / 劈轮方案（后者需重开 D#32）。
- [ ] read_log/read_gate 防幻觉读取（2026-08-09，用户经验回流，K anna 篇本地）：
      「模型自报读过不可信 → PostToolUse 记内容哈希 + 收尾判定」。当前评审流程用
      逐字核验顶着，等评审常态化或出现「引用落空」事故再上——记录器先行（成本低）、
      判定器后置。
- [x] ~~model-config 页的 auto-compact 阈值未查~~（R2 未核实节）已查证 2026-08-10：
      官方给数字——Sonnet 5 的 1M 窗口默认 ~967K 触发（预留 ~33K，
      `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 可调）。pai 的 16384 约其一半、同数量级；
      已录 K context/claude-context-management.md，作为 reserve 校准参照之一。

---

## 已完成（保留记录，便于回看节奏）

- [x] token 秤 / 警戒线 / 拍平机三件套（2026-08-02）
- [x] 官方系数替换 chars/4，中英文分开算（2026-08-02，D#15）
- [x] 阈值从百分比改为减固定预留量（2026-08-02，D#13）
- [x] usage 落盘（2026-08-02）
- [x] 上下文大小改为真实 usage 锚定 + 增量估算，误差 -33% → -1.3%（2026-08-03，D#18）
- [x] 本地文档知识库 refs/deepseek-api（2026-08-02）
- [x] 公开前清理：CC 逐字引用转述、第三方文档与 playground 入 .gitignore（2026-08-03）
- [x] R#1 loop 被非对象 arguments 崩掉（2026-08-03，严重）
- [x] R#2 STATUS 测试数字与事实不符（2026-08-03，严重）
- [x] R#10 无 docstring 的工具崩 IndexError（2026-08-03）
- [x] R#13 AGENTS.md 的 3.9 类型注解表述不准（2026-08-03）
- [x] 用量预算熔断 + 真实 API 测试改为显式选择加入（2026-08-03，D#21-23）

### feature 41（推到能做日常开发）遗留与发现 —— 2026-08-26

档案：[features/41](features/41-20260826-daily-driver/README.md)

- [ ] `read_file` 的行坐标系够不着「单行超上限」那一格（41 遗留）：整个文件就一行、
      而这一行超过 `MAX_OUTPUT_CHARS` 时，续读点落在行内，offset 表达不了。
      现在的做法是如实说「这一行没法用 offset 续读」并把出路指回 bash，
      刻意不给一个假的 offset（那才会真骗到模型）。压缩过的 js/json 会撞上。
      修法若要做：再加一个行内字符 offset，或对超长行按字符切并报「行内第几字符」。
- [ ] `search_files` 不解析 `.gitignore`（41 遗留）：噪音目录是一张硬编码名单
      （`SKIP_DIRS`），`.gitignore` 里写的别的东西照样会被搜到。做真解析要一整套
      pattern 语义（否定规则、目录 vs 文件、多级 `.gitignore` 叠加）。
      触发条件：真在一个 `.gitignore` 很厚的仓库里被噪音淹掉时再做。
- [ ] `search_files` 的性能没有数字（41 遗留）：纯 Python `os.walk` + `re`，
      不依赖 ripgrep（D#76）。本仓库这个量级没感觉，但「多大的仓库开始难用」
      一个数都没有。`MAX_FILES_SCANNED = 20000` 同样是**未实测的经验值**——
      按「给照抄来的常数建一条检查习惯」那条，改它之前先拿数字。
- [ ] `search_files` 的边界只管搜索根，不管遍历到的每个文件（41 拍板问 3 认下的诚实边界）：
      权限层判的是根这一个路径，遍历自己跳过指向根外的软链（`_escapes_root`），
      但那是工具的自觉，不是边界判定。第二个碰这种「一个入参代表一片文件」的工具
      出现时，该考虑给边界层一个「路径集合」的表达，而不是每个工具各自跳一遍。
- [ ] 找内容与找文件合在一个工具里（41 发现）：`search_files` 用「pattern 传空串」
      切到只按文件名找。CC 是 `Grep` 与 `Glob` 两个工具。一个工具两种模式的代价是
      schema 里表达不出「这两个参数是互斥的」，模型只能靠 docstring 那句话。
      触发条件：真观察到模型混用两种模式时拆。
- [ ] decisions 的索引表从 69 之后就没再维护（41 发现）：70-76 用的是
      `## NN. 标题` 形式，而 `test_decisions_index_matches_entries` 的正文正则是
      `^(\d+)\. `，看不见它们——于是「索引与正文一一对应」这条被机器钉住的规矩，
      对最近七条实际上是失效的。本轮补录索引反而把测试弄红了，说明这不是顺手能改的：
      要么改正则认两种形式并补齐 7 行索引，要么把 70+ 改回旧形式。刻意没在本轮做
      （用户划的范围是两条）。
- [ ] `loop.SYSTEM_PROMPT` 常量仍谎报工具集（41 发现）：那句「你有这些工具：
      bash、read_file、write_file、edit_file」不随新工具更新。它只在不经装配层
      直调 `run_agent` 的老路径上生效（feature 22 起装配层走 `build_system_prompt`），
      且「逐字不变」是刻意的（护缓存前缀）——所以不是随手改一下的事。
      至少该在常量旁边写明它描述的是老路径的工具集，不是今天的。（本轮已在
      `docs/dev/扩展点.md` 里改了说法，代码注释还没动。）

### feature 42（跑测试与 git 摘出 bash）遗留与发现 —— 2026-08-26

档案：[features/42](features/42-20260826-tests-and-git-tools/README.md)

- [ ] 「跑什么不由模型决定」没有机器检查（42 遗留，比一般遗留严重）：
      `run_tests` / `git_read` 能自动放行（`EXEC` + 界内 allow）的**唯一根据**
      就是这一条，而它今天只写在模块注释与 D#77 里。哪天有人给 `run_tests`
      加一个「传任意参数」的口子，或往 `git_read` 的白名单里放进一个能 exec 的
      flag，放行的根据就没了，而不会有任何东西变红。
      修法方向：一条测试遍历所有 `access == EXEC` 的工具，断言它们的 schema 里
      没有能表达「任意命令」的参数——判据怎么写还没想清楚，所以先记着。
- [ ] `run_tests` 的 `filter` 写死了 pytest 的 `-k`（42 遗留）：`tests.command`
      配成 `npm test` / `cargo test` 时这个 flag 那边不认。刻意不在代码里假装通用
      （猜错的代价是跑了个不该跑的东西）。修法若要做：settings 加一个
      `tests.filterFlag`，或按解析出的命令挑写法。触发条件：真在非 Python 项目里用起来。
- [ ] `run_tests` 的探测表只认五种项目（42 遗留）：test.sh / Python / Node /
      Rust / Go。认不出就报错并指路 `tests.command`，不瞎猜。加第六种时顺手加一行。
- [ ] `run_tests` 的 `MAX_TIMEOUT_SECONDS = 3600` 未实测（42 遗留）：默认 600s
      有来源（本仓库 183s 的三倍余量 + bash 那条两家收敛的上限），但天花板 3600
      纯属拍脑袋。同 `search_files` 的 `MAX_FILES_SCANNED`——按「给照抄来的常数
      建一条检查习惯」，改它之前先拿数字。
- [ ] `git_read` 的 flag 白名单不全（42 遗留）：漏写的合法 flag 会被拒。
      失效方向是安全的那一侧（模型收到「允许的是这些」一句话就能改），
      所以不急；被拒多了再按实际用到的补。
- [ ] `git_read` 没有 path 参数（42 遗留）：`-C` / `--git-dir` / `--work-tree`
      都在拒绝名单里，所以它只能在 cwd 跑。多仓库场景（`additionalDirectories`
      配了别的根）下看不了那些仓库。要做的话得先想清楚「path 参数」与
      「拒绝 -C」之间怎么不自相矛盾。
- [ ] `output.py` 只收编了两处拷贝（42 遗留）：`fs.py` 与 `shell.py` 改成从它
      导入了，`search.py` 仍自己做头部截断。它那里头部截断是对的（搜索结果从上
      往下读），但「哪种截断用在哪」这个判断现在散在三个模块里。
      触发条件：第三个需要保头保尾的工具出现时，把选择也收进 output.py。
- [ ] `EXEC` 档只有兜底那一支认得它（42 发现）：`acceptEdits` 与危险写检查都
      刻意不管 EXEC，这是对的；但 `visible_tools`、`/permissions` 的展示、
      README 的权限表都还只讲 READ/WRITE 两档。文档层面 EXEC 目前是隐形的。

### feature 41 交付后新发现 —— 2026-08-26

- [x] ~~`search_files` 与 `run_tests` / `git_read` 的「默认根解析」已经三份
      （`search_root` / `test_root` / `repo_root`，形状一模一样）（42 发现）：
      三个都是「取 args 里的 path，空则回落 cwd，绝对化」，且三个都配一个
      同形的 matcher 包装。第三份出现意味着该抽了——按 40 复盘学到的那条，
      触发条件写清楚：下一个碰路径的工具立工具时就抽，别等第四份。~~
      已抽 2026-08-26（feature 43 Task 1，`feat/43-edit-by-line-and-diff`）：
      `core/tools/roots.py` 的 `root_getter` / `root_matcher` / `path_semantics`。
      验收按「解析后的值逐字相等」——把抽取前的三份实现抄进测试当对照组，
      10 组输入 × 三个工具逐个比对，而不是靠「测试还绿」。
      顺带把「没有路径参数的工具要无视 args」从「碰巧不读」变成显式的 `param=None`。

### feature 43（行号编辑与 diff 呈现）遗留与发现 —— 2026-08-26

档案：[features/43](features/43-20260826-edit-and-diff/README.md)

- [ ] REPL / once 那条路的 diff 是残的（43 遗留）：`events.render_text` 的契约是
      「返回一行」（`modes/echo.py` 的注释明写着它依赖这条），且 `_preview` 会
      `" ".join(text.split())` 把换行压掉再截到 200 字符。于是那两条路上
      diff 显示为一行乱码。拍板时的候选 D（给 render_text 加多行分支）被否，
      因为要动的是三个消费者共用的契约。要做的话是一个独立需求。
- [ ] `MAX_DIFF_LINES = 80` 未实测（43 遗留）：凭手感定的「一屏多一点」。
      **注意这已经是连续第三轮做同一个动作**（`MAX_FILES_SCANNED` 20000、
      `MAX_TIMEOUT_SECONDS` 3600、`MAX_DIFF_LINES` 80），三次都是「如实写成
      未实测 + 登记 TODO」。诚实记录一个拍脑袋的数，三次之后就不再是诚实，
      是习惯性免责。下一轮该给这三个数里至少一个拿到真实分布。
- [ ] `near_line` 没解决「old 本身要写多长」（43 复盘质疑一）：它让**短的 old
      变得可用**，但一个 20 行的函数体照样要原样贴 20 行。拍板时我把这两件事
      混在一句「解决了贴长上下文」里递给了用户，如实登记。
      真要解决得换形状（按行号取一段、模型只给新内容），那是另一个需求。
- [ ] diff 无条件跟在每次编辑后（43 复盘质疑二）：80 行以内全贴，而模型多数
      时候是在读自己五秒钟前写的内容。这笔 token 值不值没有数据，只有直觉。
      可能的改法：只在 `edit_file` 给（那里模型确实不知道结果），
      `write_file` 只报统计（内容是它自己写的）。
- [ ] `write_file` 为 diff 多读一次盘（43 遗留）：没量过开销。pai 写的是代码
      文件，直觉上可忽略，但同样没有数字。
- [ ] 给「组织文本给人看」的函数补一条逐字比对整体输出的测试（43 复盘「下次怎么做更好」）：
      本轮的空文件头噪音（`difflib` 不给文件名时照吐 `--- ` / `+++ `）与 42 的
      嵌套括号是同一类——输出里有噪音，而所有断言都在看别处。
      片段断言查「有没有」，逐字断言查的才是「是不是只有」。
      落点：`diffs.render_change`、`tests_tool.run_tests`、`git_tool.git_read` 各一条。
