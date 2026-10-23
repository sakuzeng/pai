# 57-project-task-evals · devlog

## 2026-10-23 · 立项与范围拍板

用户同意先收口 56 再做真实项目任务评测。56 功能提交 c473de0，本地合并 main 为 861cec7；当前新分支 feat/57-project-task-evals，无远端推送。原有 .codex/hooks.json 保持未跟踪，未纳入提交。

四项真实选择已原样存档：完整历史快照、六题开发/保留各三、仅离线、相关回归与独立判分、默认开发集而保留集显式。按确认定稿 spec 与 TDD plan；本轮没有将旧真实 API 预算延续过来。

前置核对阶段 7 的 pi-evals 与 dsh-testing 笔记存在并重读关键隔离/外部判分约束；反向真实场景对照仍未完成，不提前勾选 roadmap。只读 Git 历史已定位两个真实修复及父提交，非 fix 题使用 9937c02 的完整历史树。候选尚未经过离线评分，不能提前称作冻结成功。

## 2026-10-23 · T1 历史快照契约

先写 tests/test_project_tasks.py，实际红为 ModuleNotFoundError、1 error during collection（evidence/t1-red.txt）；再实现 src/pai/evals/project_tasks.py 的完整提交快照、过滤记录、split/family 校验与 archive 路径/链接拒绝。实际绿 8 passed in 0.96s（t1-green.txt）。运行源码/旧测试保留，dirty 工作区不污染历史材料。T2 将在此基础上先新增评分与 conftest 隔离反证，再实现评分器。

## 2026-10-23 · T2 外部评分与隔离

先新增八条评分反证，实际红 8 failed、8 passed in 1.49s（t2-red.txt）；实现三类评分、独立副本、历史 src 导入断言与复制的外部测试目录后，实际绿 16 passed in 6.05s（t2-green.txt）。每个合成完整仓库均包含会立即报错的 tests/conftest.py，参考评分仍过，证明评分未加载目标测试配置。新增测试杀错只计算新增测试，不借用既有回归；空/全跳过/导入错误、删受保护测试和软链均拒绝。使用 56 的 JUnit/期限能力，未修改旧评分函数。

T3 先加入六个真实历史案例的参数化契约，再建立各题材料；不会用离线参考解结果冒充模型成绩。

## 2026-10-23 · T3 六个历史案例的红→绿

六题材料不存在时实际红 6 failed、16 passed in 6.17s（t3-red.txt）。加入完整起点、两条真实修复文件与六个评分错误探针后，第一次实际结果 2 failed、20 passed in 11.77s：历史回归导入 fake_llm/trajectories 失败，证明仅把源码放到 PYTHONPATH 不足以重放原测试。

补上历史 tests helper 的导入路径但仍不加载其 conftest；resume 的相关回归显式选既有 id/路径与错误报告两条函数（AST 仅去掉其他 test_ 函数，导入/辅助函数保留），避免把原本假 header 的旧“最近一次”测试当新契约。外部测试对旧签名作兼容调用，使原始红来自行为断言而非缺少 cwd 参数。最终实际绿 22 passed in 12.49s（t3-second-material-check.txt）。两份参考修复逐字对照原历史提交，评分探针明确是人为变体，未改实际生产代码。

两次生成编辑参数的 JavaScript 语法错误发生在执行前，没有写入；修正数组闭合后才执行。候选题没有因模型成绩修改，本轮仍无模型调用。T4 接着先添加冻结/入口/默认分组反证。

## 2026-10-23 · T4 分组入口、冻结与边界验证

先补六项入口/冻结测试，实际红 6 failed、22 passed in 15.17s（t4-red.txt），包括旧 eval 意外收集新评分材料的真实失败。实现 --project-tasks 离线 CLI、默认 development/显式 holdout、拒绝 --llm、显式 --freeze --split all、逐材料/历史树/源码/Python依赖哈希，且将 project_tasks 从旧 pytest 收集中隔离后，实际绿 28 passed in 14.75s（t4-green.txt）。

继续补路径越界、到期不可用与快照指纹漂移三条反证；路径项确实跑红：1 failed、30 passed in 14.91s（t4-boundary-red.txt）。首次替换脚本对反斜杠匹配断言失败，未执行写入，随后重复检查仍 1 failed、30 passed in 14.74s；修正为显式 grading 路径校验并完成新写参考/评分文件的类型注解后，最终 31 passed in 14.85s（t4-boundary-green.txt）。只调用本地 Python/pytest/Git，没有模型请求。

标准入口预收集实际为 1996/2004 tests collected（8 deselected），并非已通过结果。下一步实际冻结六题并执行新旧离线入口与全量；STATUS 当前完整通过数仍为上一轮真实输出，待本轮全量结果更新。

## 2026-10-23 · T5 首次 CLI 冻结发现相对路径缺口

首次真实离线入口 --split all --freeze --output pai_playground/... 没有写冻结清单，四道运行 pytest 的题均因相对 --confcutdir 失效而失败；报告保存为 evidence/relative-cli-failed-report.json，原始 stderr 为 freeze-output.txt。此前单测均用绝对 tmp_path，没有覆盖入口相对输出。

先补真实模块子进程与相对输出的回归，实际红 1 failed in 1.54s（relative-cli-red.txt）；再把评分工作目录/产物目录和 preflight 输出入口统一 resolve。没有降低判分或忽略失败，修后另用新运行目录重新冻结。另有一次文档更新因 D#82 索引文字不完全匹配中止，前面八个文档已写入、decisions 未写；随后按实际索引原文补录 D#83，不重复追加前面文档。

## 2026-10-23 · 六题冻结与新旧入口验证

相对目录回归修复后，新功能实际 32 passed in 15.97s；文档/可视化数据检查 40 passed、1 skipped in 0.81s。完整冻结 CLI 使用新的 feature57-final-freeze 目录，六个原始反证/参考解均通过后写入 evals/project_tasks/freeze.json；默认入口实际只验证开发组三题，显式 --split holdout 只验证保留组三题，报告均为 reference_contract、newModelCalls=0。

冻结保留源码/原测试/构建文件：早期路径键序题 143 个文件（移除 190）；resume 题 198（移除 329）；其他四题各 202（移除 351）。实际排除清单在 freeze.json，完整运行工作区留 pai_playground；必要报告、JUnit 和评分输出共 62 个文件复制到 evidence/{freeze,development,holdout}，archive-index.json 记录哈希。

两个旧入口实际输出：默认回放 1 passed、5 deselected in 2.20s；--tasks 离线 1 passed、1 deselected in 2.15s。原来的三题真实基线没有补跑，agent loop/工具/提示词/模型默认值没有改动。本轮完整离线正在执行，唯一通过数尚未冒写。

## 2026-10-23 · 首轮标准完整离线回归

实际输出 1 failed、1996 passed、8 deselected in 223.30s（full-first-output.txt / full-first.junit.xml）。唯一失败为 test_status_reports_the_current_test_count：STATUS 仍是上一轮真实 1965，而本轮选中 1997 项；其余全量用例与新增 32 项均通过。未把首次结果写成“全绿”。

现在把 STATUS 当前回归目标明确记为 1997、注明仍待实际完成，保留首次完整失败记录；改状态数量后重跑标准完整入口，获得全绿输出才写最终实测与交付复盘。不修改测试断言或降级验收范围。

## 2026-10-23 · 最终完整回归全绿与交付复盘

第二轮标准 ./test.sh 实际输出 1997 passed、8 deselected in 224.05s（full-final-output.txt / full-final.junit.xml）。解析 JUnit：选中 1997，failure/error/skip 均为 0，其中新增 test_project_tasks 32 项全部包含，见 full-suite-audit.json。运行源码未再改变，六题冻结与 62 份归档文件哈希复核一致；新增源码/材料/证据真实 key 扫描 0 命中。

在上述全绿之后写四问复盘，再将档案/索引标为已交付，更新 STATUS 为实际完整输出、登记 D#83、路线图与扩展地图；本轮已确认任务勾选，真实 once 适配与模型基线明确登记后续 TODO。未修改旧任务成功口径、agent loop/工具/提示词或模型配置，没有新增模型调用。

57 没有 commit、合并或推送；56 的本地功能提交 c473de0、合并 861cec7 与原有未跟踪 .codex/hooks.json 保持。本轮交付只包含离线设施，不能外推实际项目模型成功率或全历史套件兼容。

## 2026-10-23 · 交付文档收口检查

复盘、状态与后续待办写入之后，文档/可视化数据实际检查 40 passed、1 skipped in 0.75s（docs-final-output.txt）；跳过项仅适用于标准完整入口，已在本轮全量通过。补充遍历新档案/材料 Markdown 的相对链接，发现证据 README 的 freeze.json 链接多退一级，修正后再次校验；没有更改运行代码或判据，不重复全量回归。

## 2026-10-23 · 用户授权提交与远端推送

用户原话：「推送到远端吧」。据此将已交付 57 的实现、题目、证据与文档提交到 feat/57-project-task-evals，并同步 origin 的 main、feat/56-task-evals 与 feat/57-project-task-evals；57 保持独立分支，不把推送解释为合并 57。原有未跟踪 .codex/hooks.json 与忽略的 .env/运行副本不纳入提交。

推送前 git fetch origin --prune 成功；main 相对 origin/main 为 ahead 2、behind 0，57 尚无远端同名分支。目标 origin 为 github.com/sakuzeng/pai。直接沙箱内 ls-remote 因 DNS 限制失败，网络读写使用授权的沙箱外 Git 命令，不把该错误归为仓库缺陷。

复核六题冻结、62 个归档文件哈希及完整 JUnit 1997 通过均一致，本轮没有改变运行源码、题目或判据，不重跑完整回归或调用模型。同步文档状态后复核文档检查及暂存内容，执行普通快进推送，实际是否完成以 push/ls-remote 的远端引用为准，不使用 force。

本轮状态同步后的文档/可视化数据检查实际输出 40 passed、1 skipped in 0.75s；跳过项仅标准完整入口适用，已在交付全量通过。完整验收沿用刚完成的 1997 passed、8 deselected，运行实现与冻结材料未变。

提交前核对 132 个暂存文件，真实 key 扫描 0 命中，.codex/.env/pai_playground 均未暂存。暂存区 whitespace 告警仅来自原始 pytest/JUnit 证据；保留这些原始字节与既有哈希，不为消除告警清洗证据。排除 evidence 后其余暂存内容的 git diff --cached --check 通过。

## 2026-10-23 · 自动审批拦截与缩小范围后推送成功

57 功能提交为 0d2de04f5f98be25a018e49ad2c0c903ca4426d7。首次计划的 main/56/57 三分支原子推送被自动审批拒绝，原因原文摘要：origin 归属未验证，且用户“推送到远端”未明确列出三个分支。该次命令未执行，前述三分支同步计划不代表用户逐条明确授权。

随后通过 GitHub 连接的 get_profile/get_repo 只读验证：认证用户与仓库 owner 同为 sakuzeng、id 同为 75898519；目标仓库 public，账号 push/admin 权限为 true，与 origin URL 一致。基于新的归属证据，将范围严格缩小为仅当前 feat/57-project-task-evals 的普通推送；未改用其他写入路径绕过审批。

缩小后的 git push --set-upstream origin feat/57-project-task-evals 成功，跟踪关系建立。随后的 git ls-remote 实际核对：57 为 0d2de04f5f98be25a018e49ad2c0c903ca4426d7，main 仍为 9937c0288b731f5ae3fd333a7e422642c1e045d9，未有 origin 的 56 同名分支。57 历史已包含 c473de0/861cec7，因此 56 内容也已上传；这不等于更新 main 引用或合并 57。

本次追加同步状态记录，再以文档提交推送同一 57 分支；最终最新 SHA 以远端引用为准，不改运行实现/冻结材料或重新调用模型。原有 .codex/hooks.json 仍仅本地未跟踪。

## 2026-10-23 · 合并前整体离线测试启动

用户原话：「在合并到main之前可以先做一下整体的测试吗」。本轮只测试与归档，不合并、不提交、不推送，不新增真实模型调用。测试起点为已推送 ba56d1914434673f279a5da731f84e30d2e48b01，分支 feat/57-project-task-evals，原有未跟踪 .codex/hooks.json 保持。

fetch 后确认 origin/main=9937c02、本地 main=861cec7 均为测试提交祖先（分别落后 4/2 条提交），没有分叉；因此当前树可快进整合，不需要先制造合并提交来测试。Python 3.9.6、pytest 8.4.2。启动标准完整 ./test.sh、两个旧 eval 离线入口、默认开发/显式保留入口，另核对六题冻结与归档并重判九份旧真实产物；后者不是新模型运行。

测试命令、运行源码/测试材料逐文件哈希及原始结果保存到 20261023020449-premerge 对应的 evidence 目录；当前尚未宣告测试通过。

## 2026-10-23 · 合并前整体复核通过

标准完整 ./test.sh 本轮实际输出 1997 passed、8 deselected in 221.76s；JUnit 独立统计 1997 选中，failure/error/skip 均为 0，包含 57 新增 32、56 新增 38 与 36 项 pty e2e。两个旧 eval 入口分别 1 passed、5 deselected（2.57s）和 1 passed、1 deselected（2.12s），默认开发/显式保留各三题参考契约全部通过。

六题冻结及原有 62 个归档文件哈希一致；56 首轮真实记录的 152 个工件与九次指标/汇总一致，当前评分器独立重判九份历史产物 9/9，本轮 newModelCalls=0。197 个 Python 文件在内存编译和两份 shell 语法检查通过，pip check 无损坏依赖、pai --help 通过。pip 缓存因不可写自动禁用；pytest/评分沿用 HOME 隔离，未安装依赖或修改用户缓存权限。新生成评分目录的 21 个空目录已清理，不修改输出/判据。

本轮运行实现、测试/任务材料前后哈希一致，测试提交仍为 ba56d19；归档并更新 STATUS/报告，未做代码更改、合并、commit 或 push。完整证据见 evidence/20261023020449-premerge/README.md。36 项 pty e2e 不等于真人 IME/鼠标/主题验收，八项在线 LLM 排除不等于服务在线验证；没有新增问题需要登记 TODO。

本轮报告/状态写入后的文档与可视化数据检查实际 40 passed、1 skipped in 0.78s；仅标准完整入口适用的数量对账在全量已通过。报告链接、98 个本轮证据文件的 key 扫描（0 命中）、运行源码与测试材料哈希均再核对通过。原有 .codex/hooks.json 不动，本轮记录仍未提交或推送。

## 2026-10-23 · 用户明确授权合并 main 并推送

用户在整体测试报告之后原话：「那合并并推送吧」。本轮据此将合并前测试记录先提交到 feat/57-project-task-evals，再保留合并记录整合到本地 main，普通推送 origin/main 并核对远端 SHA；同步 57 分支用于保留完整过程，不另创建/推送 56 同名分支。此次明确 main 的授权与此前笼统“推送”的范围不同。

重新 fetch 成功：本地 main 相对 origin/main ahead 2/behind 0，57 与同名远端无差异，origin/main 是 57 的祖先，无需解冲突。测试起点 ba56d19 的源码/测试/题目逐文件哈希与当前一致；98 个新证据文件的哈希及真实 key 扫描（0 命中）复核通过。完整离线复核沿用实际 1997 passed、8 deselected in 221.76s，运行实现未改，不重复模型调用或全量测试。

GitHub get_profile/get_repo 再次验证认证用户与 origin 仓库 owner 同为 sakuzeng、id 75898519，目标 public 且 push/admin 权限为 true；URL 为 github.com/sakuzeng/pai。原有 .codex/hooks.json 与本地 .env/运行副本继续排除。合并/推送是否完成，以后续 Git 命令与 origin/main 引用核对为准；本条记录授权与执行前检查，不预先冒称成功。

整合前文档/可视化数据检查实际 40 passed、1 skipped in 0.77s，原始输出另存 evidence/main-integration-docs-output.txt；跳过项在标准全量中已通过。此次仅文档与测试证据新增，git diff 的 src/tests/evals/两个入口及 pyproject 均为空。

## 2026-10-23 · main 合并与推送完成

先在 57 分支提交测试证据与整合授权，提交 dbe6fbb6d203559667362eeb7ab5299956e03686；再切 main，以 --no-ff 合并得到 2b9b9c078041a94ef44264d5b641622f3b100597。无冲突；main 与 57 功能端的 Git 树相同，且相对已实测 ba56d19 的 src/tests/evals、eval.sh/test.sh/pyproject 无差异，因此未重复完整回归。

git push origin main 实际成功：origin/main 从 9937c02 更新到 2b9b9c0。没有 force，没有模型调用，也未推送 56 同名分支。随后将 57 分支快进到该已合并 main，补写本条真实结果及当前 STATUS，再以文档提交快进回 main 并同步远端；最终最新文档提交由 Git 引用定位，2b9b9c0 仍为实际功能合并提交。

原有未跟踪 .codex/hooks.json 保持，不纳入任何提交；测试阶段 summary.json 的 merged/committed/pushed=false 是当时未整合的历史快照，不回写该证据。

最终同步文档检查实际 40 passed、1 skipped in 0.78s，git diff --check 通过；仅四个状态/日志文档有变化，运行实现、题目与测试材料保持原完整实测版本。
