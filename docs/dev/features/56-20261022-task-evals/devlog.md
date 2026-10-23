# 56-task-evals · 开发日志

## 2026-10-22 · 前置核对与立项草案

目标：承接用户选择的任务级评测，先确定范围、预算和判分方式。

- 从 main `9937c02` 建立 `feat/56-task-evals`，未改 src/tests。
- 核对阶段 7 前置精读，重读 pi/dsh 笔记并按固定版本反查；证据见 [preflight](evidence/preflight.md)。
- 用户确认三个任务的最小范围及 3×3 真实模型预算；完整问答落 README，spec 仍待整体拍板。
- 新建 README/spec/plan 草案，登记需求池、TODO 与索引，更新当前工作指针。
- 现有评测基础离线测试：`9 passed in 0.57s`。这是既有实现基线，不是新功能的 TDD 绿，也不是模型效果证据。
- 本步为文档与只读核对，没有实现测试的红阶段；进入实现后各步独立记录实际红→绿输出。

已知边界/待办：once 无真人弹窗；AgentEnd 必须单独采集；工具内部字符串错误不能靠 ToolEnd.is_error 统计。
spec 拍板、TDD、真实基线和复盘尚待完成，统一入口见 [TODO](../../TODO.md#本轮任务feature-56)。

## 2026-10-22 · 草案文档校验修正

目标：确保新档案可被既有索引/分支/状态校验读取。

首次检查实际输出：`1 failed, 27 passed, 1 skipped in 0.74s`。失败原因是 README 的「分支」行同时用反引号标记提交 hash，被既有校验视为第二条分支；将基点移到单独一行，不修改校验规则。
本次为文档校验修正，不是阶段模块的实现 TDD。复跑实际输出：`28 passed, 1 skipped in 0.64s`。跳过项只在标准 ./test.sh 全量入口对账收集数字，本次单文件检查不适用。`git diff --check` 无输出。

另以模拟 Write 事件调用原 design_gate（不实际写文件），确认当前「讨论中」状态对 src/pai/evals/probe.py 返回 deny，未解除设计门禁。

## 2026-10-22 · 恢复逐项方案讨论

目标：回应用户对「先给候选、用户选择、原样落盘」流程的追问。

核对 feature 53 的候选/确认记录和当前 56 草案。此前范围与费用已确认，但执行者直接提出整份 spec 确认，没有充分展开其余设计取舍。
README 保留此前整体确认问与用户追问原文，标明尚无选择；增加任务代码来源 A/B 及取舍，后续讨论权限配置和成功口径。
spec 头部澄清建议稿性质，需求池登记用户原话。没有把状态改为已拍板，没有修改 src/tests 或调用真实 API。

本步为文档讨论修正，无实现 TDD 红/绿；文档检查实际输出：`28 passed, 1 skipped in 0.65s`。跳过项为标准全量入口专用的收集数字检查，本次单文件检查不适用。
遗留仍为同一交付待办，见 TODO 的 feature 56 条目，没有新增独立任务。

## 2026-10-22 · 任务来源选择 A

用户选择原文：「A：小型固定仓库（推荐）」。README 记录原始问答与选择，spec 标明任务来源已确认。
继续提供权限策略及成功口径两问，各列候选与取舍；答案待记录，不代选。
没有修改 src/tests，没有真实模型调用。此步为讨论记录，无实现 TDD 红/绿。

## 2026-10-22 · 方案逐项拍板

两次异步单选收到明确回传：权限选 A acceptEdits，成功口径选 A 产物正确且正常结束。
README 原样保存最后两题及答案，spec 据此定稿，状态改为已拍板；索引和 STATUS 同步。已确认的范围/费用不再另行询问。
当前尚未执行新实现测试或真实 API；下一步按 plan 先写失败测试，再实现。

## 2026-10-22 · T1 固定案例与外部评分器

目标：冻结三类小题与评分契约，证明空测试、删测试、跳过断言和越界改文件不能假通过。
改动：evals/tasks/ 三题输入/参考解/评分器，src/pai/evals/task_grading.py，tests/test_task_grading.py。

实际测试过程：初次缺模块 `1 error in 0.07s`；实现初版 `1 failed, 7 passed in 10.01s`；加跳过断言反证后 `2 failed, 7 passed in 10.72s`；修复后 `9 passed in 10.31s`。
失败揭示 pytest JUnit 不保证 type 属性，以及全跳过可退出 0；分别依据实际末行失败种类与 skipped 计数修正。
原始输出见 [TDD 输出](evidence/tdd-output.md)。T2 已先跑红：缺 task_metrics 模块，`1 error in 0.07s`。

已知边界：夹具是构造小题，不能外推实际 pai 仓库开发成功率；评分器执行提交测试代码，只是目录/配置隔离，不是系统沙箱。
还需完成指标、进程/超时、入口、真跑和复盘，沿用 TODO 的同一 feature 56 条目。

## 2026-10-22 · T2 真实会话指标

目标：分开工具尝试/执行/拒绝、未知/零、完整成功/产物通过。
新增 tests/test_task_metrics.py 先红：`1 error in 0.07s`（模块不存在）。实现 src/pai/evals/task_metrics.py 后实际输出：`9 passed in 0.63s`。
使用已入库真实中文轨迹 evals/fixtures/20260824-greeting-file.jsonl；实测读取三条 usage 合计 3338 token、两次工具调用，不是合成轨迹冒充真数据。
覆盖缺 usage、缺事件、多调用权限拒绝、损坏输入、侧请求覆盖不完整、预算及未启动仍在分母。
边界：主 usage 不等于 provider 全部计费，覆盖不完整单列；仍待进程生命周期/入口/真实基线及复盘。

## 2026-10-22 · T3 真实 once 与进程期限

新增 tests/test_task_runner.py 先红：`1 error in 0.10s`（runner 未实现）。新增 task_worker.py / task_runner.py 后首轮 `5 failed, 2 passed in 1.98s`：三处是误解 EventTrace 的源文件名→.events.jsonl 命名约定，两处为沙箱禁止监听 localhost（PermissionError errno 1）。
调整评测输入契约为 trace 源文件，明确使用现有 EventTrace 命名，不改其实现。申请在沙箱外执行同一组离线测试，实际输出 `7 passed in 8.05s`。

worker 复用公开 run_once，client 显式禁用 SDK 自动重试；key 构造 client 后从子进程环境移除，run_tests 不继承 key。评分环境也不含 key。
超时实际跑进独立 pytest 进程组（running.pid 为证）后验证 PID 消失；不能只杀 worker 冒称回收工具进程。
另核对到 memory.discover 会读全部祖先而不以 Git 根截断，因此运行 worker 使用仓库外临时 cwd，完整工作区与会话快照保存在调用者的 pai_playground 运行目录。该实现细节已补到 spec，没有修改 pai 指令发现或 loop 行为。

边界：此处真实的是 HTTP/进程/工具，模型仍为 FakeProvider；真模型预算尚未使用。批次总预算、入口与归档仍待 T4/5。

## 2026-10-22 · T4 显式入口与固定批次

新增 tests/test_task_entry.py 先红：`1 error in 0.08s`（require_llm/run_batch 未实现）；实现后 `9 passed in 3.21s`。
改动：runner 增加批次/manifest/报告，eval.sh 增加 --tasks / --tasks --llm，evals/task_suite.py 显式收集，conftest 忽略题目自己的测试。
计划 9 次逐次落盘，不自动补跑；总期限用单调时钟限制下一次启动，未启动保持在分母；runs.jsonl v1 三态不变，任务详表另存。
边界：pytest 的通过只表示设施完成，模型不必九次全胜；实际成功数在报告中分列。

## 2026-10-22 · 评分器祖先 conftest 隔离反证

复核 pytest 已安装源码确认 confcutdir 并非所有无关目录的加载白名单。新增反证：题目源目录上级放一个立即失败的 conftest，参考解应仍通过；实际 `1 failed, 9 deselected in 0.96s`。
修正：把外部评分测试也复制到独立评分副本中，pytest 只执行该副本，不再以源码目录中的文件作为 target。
没有修改 pai 运行时循环、权限或工具；复跑组合检查实际输出：`35 passed in 20.32s`。此问题先暴露再修复，不拿之前 9 passed 掩盖评分隔离缺陷。

## 2026-10-22 · 首轮全量与进程兜底补强

首轮完整离线回归实际输出：`1 failed, 1961 passed, 8 deselected in 213.83s (0:03:33)`；唯一失败为 STATUS 旧计数 1927 与实际收集 1962 不符，其余通过。此时不把数量相加冒称已全量全绿。

追加三个生命周期反证：worker 忽略 SIGTERM 时其 setsid 子进程不得继续运行；中断先保存工作区；批次中断补齐未启动记录后再向外抛出。
初次 `3 failed, 16 deselected in 1.90s`（含沙箱禁止 ps 的环境失败）；实现兜底后沙箱内 `2 failed, 1 passed, 16 deselected in 1.88s`，两处仍由 ps 不可执行导致。
获准沙箱外复跑实际 `3 passed, 16 deselected in 1.86s`。不能把沙箱红声称成全部三条都证明了行为错误，强杀反证另做旧逻辑注入核验。

补强范围：仅 eval runner；强杀前取子孙进程图，优雅退出失败后回收其独立组；无法验证进程清理时标设施异常。用户中断保存当前工件、补齐剩余未启动记录后传播 KeyboardInterrupt。
汇总增加显式完整成功率/产物通过率，先补现有断言跑红 `1 failed, 8 deselected in 0.61s`（缺字段），再实现。
真跑前明确 baseline 的 pytest 只把 harness_error 当设施失败；provider/protocol error 是被记录的实测失败结果，不能为凑测试绿而隐藏或修改 pai 运行时代码。尚未调用真实 API。

## 2026-10-22 · 最终离线组合与强杀注入反证

生命周期沙箱外绿之后，用显式 pytest 插件临时注入旧的「只杀 worker 进程组」策略，不改仓库源码；真实断言红为 `1 failed, 8 deselected in 2.73s`，失败明确是独立子进程仍在运行。插件源码和命令与原始输出归档，测试 finally 自行收割进程。
恢复正常调用（未改源码，无需 git checkout）后的完整新增组合已实测 `38 passed in 20.29s`。当前真实收集数 `1965/1973 tests collected (8 deselected) in 1.77s`。
STATUS 先明确写收集口径的全量目标（不冒称实际全绿），完整回归成功后再换成原始输出。

## 2026-10-22 · 标准完整离线回归通过

命令：`PATH=<pai虚拟环境>/bin:$PATH PYTHONDONTWRITEBYTECODE=1 ./test.sh -p no:cacheprovider --basetemp=/private/tmp/pai56-full-final -q`，实际 Python 3.9.6。
原始输出：`1965 passed, 8 deselected in 205.72s (0:03:25)`。STATUS 已由明确标注的收集目标换成该实际结果；没有把旧基线加新增数当全量实测。
可迁移的配置/pytest/JUnit 边界沉淀至 knowledge/engineering/evaluation-isolation.md 并登记索引。
此时实现代码冻结；接下来核对默认回放与显式任务入口，再按已授权预算跑真实基线。尚未产生真实 API 费用。

## 2026-10-22 · 两个离线 eval 入口与真跑前冻结

原有默认入口：`1 passed, 5 deselected in 2.14s`；新 --tasks 离线入口：`1 passed, 1 deselected in 2.13s`。
两者都未调用真实模型。源码/案例哈希、已选权限与预算保存为 evidence/pre-live-freeze.json。
真实入口固定 deepseek-flash，SDK 重试 0；温度/thinking 不额外覆盖，provider 实际后端修订号仍 unknown。
下一步仅执行本轮已授权 9 次试验；不根据首次结果改题、改提示词或补跑。

## 2026-10-22 · T5 首轮真实基线与交付收口

按已授权的 deepseek-flash 三题各三次执行，没有额外补跑、没有改题或调提示词。真实入口实际输出：`2 passed in 69.12s (0:01:09)`（含离线预检）。九次均 completed/final，外部产物全部通过，完整成功 9/9；43 条主请求 usage 合计 107291 token，工具尝试 48 / 执行 43 / bash 拒绝 5，模型均恢复；真人弹窗不适用。

原现场 pai_playground/task-evals/20261022T124706Z-5be434f3，152 个原始工件共 360129 字节复制入 evidence/20261022-deepseek-flash-baseline，逐字节哈希一致；所有源码/案例哈希与预冻结记录相同，API key 检查 0 命中。
核对九个会话均只有一条 user 任务且与冻结 prompt 一致，usage model 均为请求配置 deepseek-flash；后端修订号不从此推断。真实结果没有触发步数/token/期限上限。

写复盘后将档案/索引改为已交付；新增 D#82 及索引，更新 README/evals 入口/扩展地图/STATUS/roadmap/需求池，核销本轮与旧「整条轨迹无测量手段」两条 TODO。
案例代表性/保留集、旧单步套件的案例哈希提醒和提示词收益条目仍开放；本次 5 次拒绝是观察，不冒认其因果或旧回归已修。

本轮没有 commit、合并或推送；没有改 agent 主循环、工具引导和 provider 默认采样参数，没有做 A/B 或真人弹窗。收口文档/可视化数据检查实际输出：`40 passed, 1 skipped in 0.71s`；跳过项为仅标准全量入口适用的用例数量对账，完整 ./test.sh 中已通过。

## 2026-10-22 · 类型签名与最终记录核对

按项目类型注解规则补齐四个新增测试文件及显式 eval 套件的签名，逐函数 AST 核对函数体未变；没有添加新测试或改判据。
签名生成脚本漏映射 eval_artifact_dir，在完成四个测试文件后中止；随后单独补齐套件签名，模块 docstring 保持原位置。
新增离线组合复跑实际输出：`38 passed in 20.31s`。本步是类型/记录收口，无行为实现红阶段；不是新的模型试验。
真跑时套件原稿保存为 evidence/measured-task-suite.py.txt；当前与其差异为类型签名/from-future 元数据。四个 src 运行模块和题目哈希再次与冻结记录一致，真实模型没有补跑。
文档/数据检查与 git diff --check 均通过，尚未 commit、合并或推送；本轮约定交付项均已完成。

## 2026-10-22 · 用户请求测试验收：启动与证据核对

用户原话：「帮我进行测试验收」。在原 feat/56-task-evals 分支验收当前工作区，不修改 src/tests 或覆盖首轮真实基线。
先启动标准 ./test.sh 完整离线回归（排除真实 LLM），使用 Python 3.9.6 / pytest 8.4.2，并输出 JUnit 以单独核对新增 38 项覆盖。
可选付费重跑已通过异步选项提问，问答原文在 evidence/20261022-acceptance-133734/request.md；回答前只推进离线工作。

已完成独立核查：152 个原始工件哈希全部一致；当前 src/案例哈希与真跑前冻结相同；从九个原始会话/事件重新计算指标与汇总，与既有结果逐项一致；用户 prompt、预算、权限与允许改动集合匹配。
当前 eval 套件与实测原稿的函数体 AST 一致（仅类型签名元数据不同）。本步没有新增模型调用。详细结果见该验收目录 baseline-audit.json。
完整离线回归与独立产物重判仍在推进，尚未提前宣告本轮验收通过。

## 2026-10-22 · 本轮验收：完整离线回归通过

标准 ./test.sh 本轮实际输出：`1965 passed, 8 deselected in 203.74s (0:03:23)`，未执行 --llm 入口。
解析新生成 JUnit 核对选中用例：1965 项全部通过、0 failure/error/skip；其中新增评测 38 项全部包含在本轮完整回归内（入口 10、评分 10、指标 9、进程 9），不重复单独跑同一组以充测试数字。
已归档原始输出、JUnit 和分类计数；本轮默认回放入口也通过，原始输出：1 passed, 5 deselected in 2.11s。
接下来完成新任务离线入口与九份既有真实产物的独立重判；不把旧报告自述当本轮重判结果。

## 2026-10-22 · 本轮验收：入口与独立重判

用户明确选择：「复用已有真实记录，本轮只重跑离线验收（推荐）」。本轮不新增真实模型调用，完整选择记录见验收目录 request.md。
新任务离线入口实际输出：`1 passed, 1 deselected in 2.13s`。旧默认回放入口实际输出为 `1 passed, 5 deselected in 2.11s`。
随后用当前冻结评分器独立重判归档九份真实产物，当前脚本运行结果以 regrade-output.txt / regrade-results.json 为准；不将该重判称为九次新模型运行。

## 2026-10-22 · 本轮验收：九份历史产物重判通过与结论

独立重判实际摘要：`{"regraded": 9, "passed": 9, "newModelCalls": 0}`。原始报告、逐次 JSON、新生成的 JUnit/输出及可复核脚本已存入 evidence/20261022-acceptance-133734。
归档前确认全量 1965、评测新增 38、两个离线入口、152 个原始工件哈希、九份会话指标重算及九份产物重判均通过；本轮没有 src/tests 修改、测试判据改动、额外模型采样或提交推送。
验收范围严格遵照用户明确选择；将 feature 56 档案与索引改为已验收，STATUS 更新为本轮实际完整输出，TODO 添加验收出处。
该状态不扩大为全项目真人交互验收或真实项目泛化结论；既有案例/保留集与提示词收益边界保持。
验收记录的一致性检查完成后再作本轮最终回复。

## 2026-10-22 · 本轮验收记录收口

状态/索引/STATUS 更新后的文档与可视化数据检查实际输出：`40 passed, 1 skipped in 0.74s`（原始摘要见 docs-output.txt；跳过项仅适用标准完整入口，已在本轮全量中通过）。
再次核对当前运行源码哈希与冻结值一致，首轮 152 个工件未被重判改写；git diff --check 无输出。
本轮按用户选择完成自动化/原始证据验收，无源码与测试判据修改，无新增模型调用，无提交/推送。

## 2026-10-23 · 本地整合启动与观察措辞澄清

用户在“先收口 feature 56：已验收，但尚未提交、合并；再做真实项目任务评测”的优先顺序之后回复原话：“可以继续做吧”。据此执行 56 的本地提交与合并收口；不将 55 的既往远端推送授权移用到 56，不调用真实模型。原有未跟踪 .codex/hooks.json 不纳入功能提交。

核对首轮原始轨迹：5 次 bash 拒绝后任务均最终完成，但仅 locate-2 与 tests-3 随后继续调用工具；fix-1/2/3 被拒的是额外 Python 检查，此后直接收尾，这些额外检查实际未执行。旧“均恢复”仅表示任务最终成功，不能解读为每条被拒命令都通过替代工具完成；当前 STATUS 已改为明确表述，历史数字与原始工件保持。

首次文档写入未执行成功：shell 内嵌中文脚本触发编码错误；apply_patch 又被会话缓存的旧 hook 路径 /guards/design_gate.py 拦截，当前 .codex/hooks.json 已为正确回落路径。后续写入前显式调用仓库 design_gate.decide 校验，不修改 hook 配置或放宽门禁。

已存在的完整验收为 1965 passed、8 deselected；本轮收口仅复核当前运行源码/案例与冻结哈希，以及相关回归和文档一致性，不重复模型采样。实际检查结果随后追加。

## 2026-10-23 · 本地提交前复核通过

首次检查命令误写不存在的 tests/test_viz.py，实际结果 no tests ran，原输出保留 initial-command-output.txt 与初次 JUnit。改为真实文件 tests/test_viz_collect.py 后，四组任务测试、文档一致性与可视化数据检查得到 78 passed、1 skipped in 20.45s；跳过项仅在标准完整入口适用，本次不是新的全量回归。原始输出与 JUnit 在 evidence/20261023-local-integration。

沿用已入库的验收审计脚本另存本轮结果：152 个原始工件哈希一致、运行源码与案例仍匹配冻结记录、九次会话指标与汇总重算一致，newModelCalls=0。本轮没有重新判九份产物，独立重判仍引用 2026-10-22 的 9/9 验收证据。未发现新的运行实现改动，复用既有完整离线验收 1965 passed、8 deselected。

按用户同意的优先顺序把 56 功能实现、文档和证据提交到 feat/56-task-evals，再以保留分支记录的方式整合进本地 main。提交与合并是否完成须以 Git 实际输出为准；不推送远端。下一项真实项目任务评测另建 57 档案和分支，旧任务判据与证据冻结。

提交前暂存区复核共 256 个文件，真实 key 扫描 0 命中，.codex/hooks.json 未暂存。git diff --cached --check 首次纳入原来未跟踪的 evidence/tdd-output.md，发现原始 pytest 输出自带行尾空格；保留原始证据，不清洗测试输出。排除此单一原始输出文件后检查其余暂存内容；此前仅 unstaged diff --check 通过不能说明未跟踪文件也无空白告警。
