# features —— 功能档案

自 2026-08-09 起，一个需求一个目录 `<NN>-<YYYYMMDD>-<名称>/`（日期=立项日），
该需求的一切文档都落在目录内：需求、方案、问题、测试结果、开发日志、总结。
既有的全局 devlog/decisions 历史条目冻结原样，不迁移（D#36 及其注记）。

档案的上游是 [需求池](../需求池.md)：用户的想法先在那里按原话记下，
评估后才决定要不要立档案（升格）、还是降格成 TODO 一行、或划掉不做。

全局文件从此只当索引与骨架：

- devlog.md（全局）：只记里程碑一行（开工/合并/验收 + 档案链接），详细日志在功能目录。
- decisions.md（全局）：不拆。功能内的选择过程写档案「候选方案与确认」节；
  够格全局复用的取舍（有 pi/CC 对照意义的）升格进 decisions.md 并互链，编号体系不破。
- TODO.md（全局）：仍是唯一待办入口。功能的「问题」详情住目录，但每条必须
  一行登记进 TODO（注明出处），否则等于没记。
- STATUS.md（全局）：模块状态快照照旧；功能生命周期状态只在档案头部维护一份。

## 目录内文件

| 文件 | 何时有 | 内容 |
|---|---|---|
| `README.md` | 必有 | 档案：状态 + 需求 + 候选方案与确认 + 结果与总结 + 遗留问题 + 用到的知识 |
| `spec.md` / `plan.md` | 走 superpowers 全链路时 | brainstorm/writing-plans 的产物 |
| `devlog.md` | 动工后 | 该功能的开发日志（目标/改动/红→绿真实数字/遗留），格式同全局 devlog 老规矩 |
| `复盘.md` | 必有（交付时，测试全绿之后） | 四问：学到什么 / 哪里走了弯路 / 我现在质疑什么 / 下次怎么做更好 |

## 规矩

1. 路线图级模块与中等改动都立档案；小修小补不立（直改 + 全局 devlog 一行）。
2. 状态取值：`讨论中 → 已拍板 → 实现中 → 已交付 → 已验收`，只在档案头部维护。
2.5 档案头部必有「分支：」字段（2026-08-10 用户提出）。一个需求跨多条分支是常态：
   05-repl 的 8 个 task 在 `feat/repl`、五个补漏在 `feat/memory`、conftest 回归修在 `main`——
   而当时档案里只写着「分支 feat/repl」，是错的。每条分支注明它承担了什么；
   已合并的分支照留（`git branch --contains` 因为分支线性叠会把所有分支都列出来，
   答不出「在哪条上做的」，所以这个字段不能靠事后 git 推断，必须当时写）。
   分支命名规约见 AGENTS.md「代码」一节：`<类型>/<NN>-<描述>`，类型复用提交类型
   （`feat`/`fix`/`docs`/`refactor`/`chore`），`<NN>` 是本档案编号——
   于是分支名指回档案、档案的「分支：」字段指回分支，两头可查。
   `tests/test_docs_consistency.py::test_declared_branches_follow_the_naming_convention` 强制前缀。
3. 候选方案 ≥2 个 + 「确认」记录用户选择（收编 anna 方案门禁的过程产物要求）。
4. 指针优先：能一行链接（D#n、TODO、knowledge 笔记）的绝不抄正文。
5. 硬约束：`.active` 写当前需求的目录名；其档案状态未到「已拍板」时，
   `guards/design_gate.py`（PreToolUse）拒绝修改 src/tests。小修显式放行：
   `.active` 写 `!<理由>`（如 `!小修:修 typo`），理由留档可查。
6. 拍板问答完整存档（借鉴 anna REQ 的完整性，2026-08-09 用户裁决）：每次拍板
   须原样记录——问题原文、每个候选及其取舍描述、选择、理由，不许压成一行。
   落点就是档案「候选方案与确认」节；不拆 需求.md/方案.md 等文件（README 节
   承载，长方案进 spec.md；讨论特别长时才单独建 讨论.md）。
7. 档案按「一次交付」切，不按「模块」切（2026-08-10 用户提问「改 session 存放位置
   是新建需求还是纳入已有」引出）。判据一句话：
   「这次改动是在*完成*那次交付，还是在*改变*那次交付的结果？」
   - 完成 → 留在原档案（今天五个补漏留在 05 是对的：同一轮交付的连锁）；
   - 改变 → 新建档案，在新档案里链接回旧档案；旧档案冻结——它记录的是
     「那次交付做了什么」，回头改它会让历史失真。
   所以「session 落盘位置」新建 08，尽管它动的是 00（session）与 06（memory）的产物。
8. 交付即复盘（2026-08-10 用户裁决）：一个需求做完、`./test.sh` 全绿之后，
   必须写 `复盘.md` 再宣告交付。四问见模板，其中「我现在质疑什么」是必答——
   允许也鼓励质疑已经拍板的做法（包括用户拍的板与自己写进 spec 的取舍）：
   交付之后掌握的信息比拍板时多，那些「早知道」必须有个落点，否则只能靠下次重犯来重新发现。
   写下疑问不等于推翻决定，够格的升格成 decisions 复议或 TODO。
   机器可判的部分（状态到「已交付」而无复盘、复盘仍是模板占位）由
   tests/test_docs_consistency.py 强制；立项日早于 2026-08-10 的既有档案不追溯
   （与「既有历史条目冻结不迁移」同一处理）。
9. 档案头部必有「流程：」字段（2026-08-11 用户问「15 这个没有 plan 吗」引出）。
   spec/plan 本来就只在走全链路时才有，中等改动可以省——但省了要说是省的，
   否则读者分不清是「选了中等改动通道」还是「漏了」。写清走哪条 + 一句话理由。
   `tests/test_docs_consistency.py::test_feature_archives_declare_their_process` 强制
   （立项日早于 2026-08-11 的不追溯，同复盘/分支两条规矩的处理）。

   附带的教训（来自 15）：中等改动通道没有承载「验收项」的地方。
   15 的「每条 e2e 必须配一条能还原原 bug 的注入反证」是写完才临时起意做的，
   结果 2/3 假绿。走中等改动通道时，把验收项写进档案的「需求」节——
   不写 plan 不等于不需要说清「怎么算做完」。

10. evidence/ 按需归档：实测/量测的原始数据（请求响应、成本数字、量测输出）进
   `evidence/<YYYYMMDD-主题>/`，让 decisions 引用的是可查证的原件；按需建，禁止空占位。

规矩怎么被遵守：机器可判的部分（目录命名、档案与状态行、分支字段、确认节存在、无空目录、交付即复盘）
由 tests/test_docs_consistency.py 每次 `./test.sh` 强制；改代码前另有 design_gate 按
`.active` 查岗；判不了的（讨论是否真的完整）靠 _template 结构引导 + 评审兜底——边界如实声明。

## 交付总览（结果导向的一眼汇报；状态以各档案头部为准）

| 功能 | 状态 | 一句话结果 |
|---|---|---|
| [32-20260824-evals](32-20260824-evals/README.md) | 已交付 | 阶段 7 evals 第一梯队（方案 C 最小合体，roadmap 阶段 1-7 至此全有交付）：`./eval.sh` 独立入口 + 工件索引（runs.jsonl + 会话快照，pi 形态）；回放纵切（真 DeepSeek 铸造 v1 轨迹入库、`derive_replay` 派生 fake_provider 脚本、真 pai 子进程重放、外部世界断言——dsh llm-replay 形态）+ 真模型冒烟纵切（--llm 双门槛）。注入反证双层各红；比较机器/模型 judge 等真实压力（spec 非目标）。1365 passed |
| [31-20260824-assembly-convergence](31-20260824-assembly-convergence/README.md) | 已交付 | 装配收敛（refactor，需求池拍板 A）：once/interactive 各自手抄的装配序列（25/28/29 三轮同步增补的重复面）合一进 `modes/assembly.py`，两模式只注入差异点；MCP 关闭 atexit→单出口 finally（29 遗留 7 销账，2 条新测试修前红）。行为逐字不变：既有测试零改动全绿 + 功能测试 28 冒烟场景复跑全过，1353 passed |
| [29-20260823-mcp-client](29-20260823-mcp-client/README.md) | 已交付 | 阶段 6 后半程 MCP client（阶段 6 全部完成）：手写 stdio JSON-RPC（Tools only，不引 SDK——dsh D4 教训）、`mcp__<server>__<tool>` 桥接（清洗/截断/预算，D#74）、settings 两层配置 + 28 式信任门禁、权限零引擎改动（默认 ask + `mcp__s__*` 白拿，补掉 dsh 的空头期权缺口）。前置精读四篇 + 两轮反向对照（真探针三场景 + 真 DeepSeek 一跑即成），31 单测 + pty e2e，1339 passed |
| [28-20260823-skills-trust-and-write-guard](28-20260823-skills-trust-and-write-guard/README.md) | 已交付 | skills 持久化位点与信任门槛三合一（25 复核中 2 条 + 25 遗留 1）：`.pai/skills` 段进危险写名单（写 skills 永远 ask，acceptEdits/bypass 翻不过）；项目级 skills CC 式信任门禁（interactive 真人确认持久化到项目身份目录、once 未信任不加载+warn，pty e2e 钉对话框全链）；用户级软链真身进边界、项目级刻意不解（恶意软链任意读洞）。注入反证两处各红各的 |
| [27-20260823-skill-boundary-exempt](27-20260823-skill-boundary-exempt/README.md) | 已交付 | 修 25 复核高 2（子目录启动 skill 被边界拦）：CC 反编译走读证实「读 SKILL.md 路径」建模是三家孤例（CC 的 SkillTool 无 getPath、dsh 门在 isModelInvocable），skill 工具退出路径边界改走 `Tool.boundary_exempt` 显式豁免位（D#73，只作用兜底、deny/ask 规则在前），「未知名回 cwd」绕法连带删除；软链正文顺带修好，子目录场景进回归测试 |
| [26-20260823-reattach-test-fix](26-20260823-reattach-test-fix/README.md) | 已交付 | 修 25 复核发现的假绿：压缩重挂锚测试场景两锚改三锚（从 find_cut_point 机制推出刀位）让正文真被摘掉 + 双向断言（token 不在 tool 消息、在指令消息），注入反证掐断重挂必红；顺带补 /skill 通道对 disable-model-invocation 的覆盖缺口。只动 tests，1292 passed |
| [25-20260822-skills](25-20260822-skills/README.md) | 已交付 | 阶段 6 skills 子阶段：SKILL.md 两级目录扫描（项目赢 D#72）→ 目录索引进 system prompt（渐进式披露带预算）→ 专用 skill 工具加载（D#71，动工前反向对照证实「零新增工具」只是 pi 一家）→ 压缩后重挂（搭 D#42 的车零 loop 改动，REAL_TRAJECTORY 真轨迹钉死）→ /skill 命令。7 task TDD，1291 passed；交付前真 API 回合模型不点名自主调了 skill |
| [18-20260813-steering-input](18-20260813-steering-input/README.md) | 已交付 | 排队消息通电：干活时打的字本轮就注入（改 12 的默认值，照 CC「人说话默认优先」），followUp 队列删掉、pai 只剩一条队列 + 两个注入出口；`/`、`!` 混装同队列靠谓词滤出、轮末逐条执行；注入发 `SteeringInjected`（TUI/观测流/viz 都看得见）。七问拍板（其中两问用户要求先核实 CC 源码，各改写一条结论），5+1 task TDD，1111 passed；顺带修掉一条前置缺陷（模型不调工具那轮队列永久卡死）并做了注入反证 |
| [17-20260812-viz-flow](17-20260812-viz-flow/README.md) | 已验收 | viz v2 运行时流转可视化：新增观测流落盘（`core/trace.py`，14 种事件并排落 `.events.jsonl`）+ 回合时间线（分组配对、2s 游标轮询、跨项目回放）+ 每处标代码位置可跳编辑器。8 task，1069 passed；每个 task 真数据/真浏览器复验各抓出问题，含两个只有 pty e2e 与肉眼能发现的 bug |
| [00-20260802-harness-skeleton](00-20260802-harness-skeleton/README.md) | 已验收 | `pai "任务"` 可真跑：loop/4 工具/JSONL 落盘/once 模式，冷眼评审严重项清零 |
| [01-20260803-viz](01-20260803-viz/README.md) | 已验收 | `pai-viz` 本地网页：结构图自动自省 + 阶段路线图，14 条测试 |
| [02-20260803-compaction](02-20260803-compaction/README.md) | 已交付 | 压缩闭环全链接进 loop（触发/切/摘/重建/熔断），SDD 6 task+终审修复波，115 passed；实测裁决默认拍平（D#37） |
| [03-20260809-design-gate](03-20260809-design-gate/README.md) | 已交付 | 档案未拍板不许改 src/tests 的 PreToolUse 门禁，注入验证真会拦 |
| [04-20260809-review-fixes](04-20260809-review-fixes/README.md) | 已交付 | 全量代码梳理（R3，15 条 finding）后修掉 10 条防御缺口，TDD 7 红转绿 |
| [10-20260811-memory-recall](10-20260811-memory-recall/README.md) | 已交付 | 记忆召回层：一事一文件 + frontmatter、索引改投影、相对时间与陈旧警告、每轮侧查询选 ≤5 篇注入，458 passed |
| [15-20260811-fake-provider](15-20260811-fake-provider/README.md) | 已交付 | 本地假 provider（真 HTTP + OpenAI 兼容协议）+ 真 pty e2e：「需要模型开口」的功能也能自动测了，用户打回的三条 bug 各钉一条，769 passed |
| [14-20260811-session-capture](14-20260811-session-capture/README.md) | 已交付 | `PAI_TUI_RECORD` 录终端字节 + `pai-replay` 回放成 PNG——让 AI 自己看得见界面，不必每次让用户截图；终端模拟器升为一等公民，回放与测试共用同一份，756 passed |
| [16-20260811-mouse-and-selection](16-20260811-mouse-and-selection/README.md) | 实现中 | 接管鼠标：滚轮滚自己的 transcript、拖选复制、点击展开、输入框选区。9 task 全实现，剩一条「从后往前拖选不复制」未修故不标已交付 |
| [13-20260811-alt-screen](13-20260811-alt-screen/README.md) | 已交付 | 让 pai 拥有整屏（备用屏 DECSET 1049）：像新开一个窗口 ✅、transcript 键盘可滚 ✅、不接管鼠标（保住终端原生拖选复制）故「可点」留下一轮。阶段 2 原则 2 被拆开而非推翻 |
| [12-20260811-tui](12-20260811-tui/README.md) | 已交付 | 阶段 2 后半程 TUI：scrollback + dock、输入归属仲裁（关掉 08 那条真实事故）、`/mode` + shift+tab、干活时打字排队、并发可见，8 task TDD，680 passed |
| [11-20260811-streaming](11-20260811-streaming/README.md) | 已交付 | 阶段 5 流式：逐字上屏 + 工具能力标志 + 保序并发调度 + 权限按批前置；反向对照推翻了「usage 重复累加」那条必修前提，509 passed |

## 模板

新开需求：`cp -r _template <NN>-<YYYYMMDD>-<名称>`（日期=立项日），用不到的文件
删掉（如中等改动无 spec/plan）。各文件骨架见 [_template/](_template/)：
README（档案）/ devlog / spec / plan / 复盘；evidence/ 有实测数据时再建。
