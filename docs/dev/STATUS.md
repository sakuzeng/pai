# 当前状态快照

最后核对：2026-10-23。feature 57 的完整历史任务离线设施已交付，尚未进行新模型评测。上次固定文档基线涵盖 [54 文档对齐](features/54-20261022-current-docs-alignment/README.md)与[55 审计收口](features/55-20261022-baseline-consistency/README.md)；feature 56 已验收，本地整合基线由 main 引用定位，agent 主循环与工具沿用原实现。
版本定位：文档与校验内容基线为 `585ac97`；默认开发主线为 `main`，远端为 `origin/main`。54/55 的远端同步授权见 55 档案；56/57 的主线整合与远端同步结果见 57 日志，最新整合版本用 `git log -1 --format=%H main` 查询。

阶段 1—7 均已有交付：压缩、REPL/TUI、记忆、权限、流式、skills/MCP 与基础 evals。
当前重点是实际使用验收、效果测量与参数校准；交付不等于全部真人验收完成。
历史过程见 [devlog](devlog.md) 和 [功能档案](features/README.md)，取舍见 [decisions](decisions.md)，开放项只在 [TODO](TODO.md) 维护。
本文件原有详细叙述可用 `git show 6f6d055:docs/dev/STATUS.md` 查看；旧测试数字、缓存比例与价格不作为当前实测重复列出。

## 模块现状

以下表格由 `pai-viz` 读取；「可用」表示已有实现与离线验证，具体范围及未验证项见后文。

| 模块 | 状态 | 说明 |
|---|---|---|
| `cli.py` / `config.py` | 可用 | 参数分发与 OpenAI 兼容 client；CLI 默认每轮任务 50 万 token、20 步，预算在下一次请求前检查 |
| `core/loop.py` / `core/scheduler.py` | 可用 | 流式循环、保序分批调度、工具结果配对、预算与压缩接线；client/model/tools 可注入 |
| `core/tools/` | 可用 | 签名生成 schema；读写编辑、搜索、目录、测试、只读 git、shell，以及按装配条件提供的记忆/提问/skill 工具 |
| `core/compaction.py` | 可用 | 真实 usage 锚定、触发/切点/摘要/重建/熔断；摘要与保留预算未实测校准 |
| `core/permissions.py` / `core/boundary.py` / `core/hooks.py` / `core/gate.py` | 可用 | deny→ask→allow、四模式、目录边界、危险写与 PreToolUse；bash 不参与路径边界 |
| `core/memory.py` / `core/recall.py` / `core/rules.py` / `core/paths.py` | 可用 | 分层指令、记忆索引与侧查询召回、路径规则、用户级路径；上下文改写后清理注入去重状态 |
| `core/session.py` | 可用 | 格式 v1、append-only、压缩重建、默认恢复到原文件；旧 v0 明确拒读 |
| `core/streaming.py` | 可用 | SSE 装配、tool_call id 归一与 usage 收集；摘要和召回侧查询仍非流式 |
| `core/skills.py` / `core/tools/skill.py` | 可用 | 两级目录与信任、按需正文加载、压缩重挂、显式 /skill；运行中增删 skill 不重新扫描 |
| `core/mcp.py` | 可用 | stdio JSON-RPC、工具桥接、信任与权限接线、失败隔离；无 HTTP/OAuth/自动重连 |
| `core/events.py` / `core/trace.py` / `core/queue.py` / `core/interrupt.py` / `core/heartbeat.py` / `core/protocols.py` | 可用 | 事件、观测落盘、用户插话、中断、工具阻塞期心跳与客户端协议类型 |
| `core/settings.py` | 可用 | 用户/项目两层设置、权限规则合并、通用信任标记 |
| `modes/assembly.py` / `modes/once.py` / `modes/interactive.py` / `modes/commands.py` / `modes/resume.py` | 可用 | 共用装配；once、REPL、TUI；/命令与 !shell；恢复回放、会话内切换与 fork |
| `tui/app.py` / `tui/driver.py` / `tui/dock.py` / `tui/editor.py` | 可用 | 输入与对话框仲裁、折行、忙时输入、等人暂停计时、footer 路径压缩 |
| `tui/transcript.py` / `tui/groups.py` / `tui/markdown.py` / `tui/altscreen.py` | 可用 | transcript、连续工具分组、编辑 diff 默认展开、Markdown 与英文词边界折行、整屏重绘 |
| `tui/mouse.py` / `tui/selection.py` / `tui/clipboard.py` / `tui/record.py` / `tui/replay.py` | 可用 | 鼠标与选区、剪贴板、终端字节录制及 PNG 回放；真机体验仍有待验收项 |
| `viz/` | 可用 | 本地结构图、事件时间线与代码跳转；页面纯观察 |
| `evals` | 可用 | 回放/原有真模型入口、三固定任务重复测量；57 增加六题完整历史快照、分组离线参考契约与冻结，未新增真实模型结果 |

本地已验收：[56 任务级评测](features/56-20261022-task-evals/README.md)，分支 `feat/56-task-evals`；用户指定复用原始真实记录，完整离线与九份产物独立重判通过；本地提交 c473de0、合并 main 为 861cec7；这段历史已随 57 整合并推送 main；57 的合并提交为 2b9b9c0，最新主线版本由 main/origin/main 引用定位，不另推送 56 同名分支。

## 最近交付

- [57：真实项目任务离线设施](features/57-20261023-project-task-evals/README.md)：六题完整历史快照、独立评分与哈希冻结；默认三开发题，显式三保留题。参考契约通过不算模型成绩，真实 once 适配与模型基线仍待后续；57 的交付分支为 feat/57-project-task-evals，包含 56 的提交历史；合并前整体复核已通过，已按用户要求合并并推送 main（合并提交 2b9b9c0），最终主线版本用 main/origin/main 核对。

- [56：任务级评测](features/56-20261022-task-evals/README.md)：真实 once 三任务各三次，外部判分完整成功 9/9；主请求 107291 token、5 次 bash 请求被拒后任务仍完整成功，其中修 bug 三次的额外检查未执行；真人弹窗不适用。固定小题结果不外推实际项目能力。

- [55：审计基线收口](features/55-20261022-baseline-consistency/README.md)：81 条决策与 55 个档案索引对齐；核销、拆分和合并有证据的 TODO，开放 217 条；加强索引、生命周期和唯一当前测试数字校验。

- [48：恢复历史上屏](features/48-20260910-resume-transcript-replay/README.md)、[49：原文件追加与 /resume](features/49-20260911-resume-same-file-and-slash-resume/README.md)：模型历史与屏幕回放接通，当前环境重装配；fork 另建文件。
- [50：工具分组](features/50-20260912-tool-group-collapse/README.md)：连续读/搜/看/跑折成摘要，写改默认展示 diff；界面保持中文，组摘要按用户指定用英文。
- [52：英文折行](features/52-20260913-word-wrap/README.md)：保住 ASCII 单词，长路径与代码块仍有刻意保留的硬断行为。
- [53：四项真用摩擦](features/53-20260913-four-frictions/README.md)：预算 50 万及撞顶提示、等人暂停计时、长 cwd footer、权限理由文案。

## 实测基线与验证边界

- 2026-10-23，Python 3.9.6，本轮标准 ./test.sh 完整离线实际输出：`1997 passed, 8 deselected in 221.76s (0:03:41)`。本轮为 ba56d19 的合并前整体复核，包含 57 的 32 项、56 的 38 项及 36 项 pty e2e，选中项 failure/error/skip 均为 0；8 项为真实 LLM 排除。见 [合并前报告](features/57-20261023-project-task-evals/evidence/20261023020449-premerge/README.md)，交付时的历史失败输出也保留。
- 运行命令为 `PATH=<项目虚拟环境>/bin:$PATH PYTHONDONTWRITEBYTECODE=1 ./test.sh -p no:cacheprovider --basetemp=<临时目录> -q`，实际解释器为 Python 3.9.6，临时产物位于 `/private/tmp`。
- 完整离线回归获准在沙箱外执行，以支持 localhost 假 provider、pty 和 ps 进程图反证；本轮未做真人交互验收或新增真实模型调用。
- 56 上轮验收重跑两个离线入口、重判九份原始产物；完整输出与范围见 [56 验收报告](features/56-20261022-task-evals/evidence/20261022-acceptance-133734/README.md)。
- 首次交付时，默认回放、新任务离线入口与真实基线均已执行；原始输出见 [56 证据](features/56-20261022-task-evals/evidence/20261022-deepseek-flash-baseline/README.md)。真实入口含预检共 69.12 秒；没有额外补跑或原有 LLM 套件跑批。

## 重要边界与未完成验证

- 权限是工具调用策略：bash 不声明路径语义，allow 白名单或 bypass 不构成系统级文件隔离。危险写保护只覆盖能声明并判定路径的工具调用。
- [feature 16](features/16-20260811-mouse-and-selection/README.md) 已交付；拖选卡顿成因仍未确诊。pty e2e 偶发挂死有超时与回收硬化，根因仍待复现证据。
- [真人手工清单](features/45-20260827-first-real-use/evidence/手工清单-收紧版.md) 未有完整验收记录：中文 IME、resize、主题、真鼠标与权限文案体验仍需真人确认。
- 压缩 reserve/keep_recent、skills/MCP 预算及默认任务预算缺少充分校准数据；离线压缩链路跑通不代表实际触发频率合理。
- resume 后 system 在内存重装配，磁盘仍保留首次 system；!命令的活轮次与回放展示仍有差异。细项与范围限制见 TODO 的 feature 48—53 小节。

## 下一步

1. 按 TODO 的近期阅读入口安排真人验收；有复现证据再处理交互问题。
2. 57 的六题历史任务已做离线冻结，后续真实 once 执行与模型预算仍须另定；改工具/提示词前先在开发集重复对照，不把参考解通过或 56 的 9/9 当泛化收益。
3. 用真实使用数据校准预算；MCP 新传输、ToolSearch、代码重构等按既有触发条件评估。
