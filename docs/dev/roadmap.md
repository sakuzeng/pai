# 路线图

阶段级地图，低频更新。只回答三件事：**阶段顺序、每阶段参照什么、开工前必读什么**。
细粒度待办在 [TODO.md](TODO.md)，当前进度在 [STATUS.md](STATUS.md)，取舍在 [decisions.md](decisions.md)，
功能级完整故事线（需求→方案→结果→测试→问题）在 [features/](features/README.md)。
「前置精读」的笔记落 [../../knowledge/](../../knowledge/README.md)；勾选只代表笔记文件已存在
（tests/test_docs_consistency.py 校验链接可达），不能证明人真的读了——这条判不了，如实声明。
官方文档全景归属见 [knowledge/claude-docs/map.md](../../knowledge/claude-docs/map.md)。

每阶段五要素：目标 / 范围 / 参照 / 前置精读 / 流程级别（superpowers 全链路 or 简述直做）。

---

## 阶段 1 · 上下文压缩收尾（已交付 2026-08-09，tag `compaction-v1`）

- **目标**：`find_cut_point` → `summarize` → `compact`（带熔断器）接进 loop，压缩闭环在真实会话轨迹上跑通。
- **范围**：做——三函数 + `should_compact` 接线 + 锚点列表（D#32）+ 压缩后首次真实 usage 裁决（D#34）+ 并行 tool_calls 测试补齐（R#11，有真实 400 复现）。不做——microcompact（阶段 1 完成后单独评估，见 cc-compaction 笔记）、流式下的 usage 归一化（阶段 5 前置）。
- **参照**：pi `packages/agent/src/harness/compaction/`（findValidCutPoints 只排除 toolResult、允许劈开单轮 isSplitTurn；CompactionEntry）；CC `src/services/compact/`（策略：四级递进）。注意 pai 的「只切轮次边界」是比 pi 更强的约束（D#32 注记）。
- **前置精读**：
  - [x] [knowledge/claude-docs/context-management.md](../../knowledge/claude-docs/context-management.md)（官方 compact 行为与摘要保留清单）
  - [x] [knowledge/source-walks/cc-compaction.md](../../knowledge/source-walks/cc-compaction.md)
- **流程**：superpowers 全链路（brainstorm → spec → plan → SDD → 合并 → tag `compaction-v1`）。
- **完成定义**：压缩在真实轨迹夹具上跑通；锚定退化空窗有测试钉死；`./test.sh` 全绿。
- **档案**：[features/02-20260803-compaction/](features/02-20260803-compaction/README.md)。
  ⚠️ **诚实边界（2026-08-10 用户实测暴露）**：压缩链路在**真实使用中一次都没被走到过**——
  `keep_recent_tokens`（默认 20000）没有环境变量可调，小会话里切点条件永远不成立，
  连 REPL 的 `/compact` 也压不动。离线测试全绿是因为测试直接传了 `keep_recent_tokens=1`
  把这道坎绕过去了。三条已记 TODO「压缩链路的可验证性」。

## 阶段 2 · REPL → TUI（REPL 已交付 2026-08-10，TUI 未开始）

- **目标**：`modes/interactive.py` 纯 REPL 先行，随后 TUI。
  ⚠️ 原文的「core 不动」**已作废**（D#38）：事件流定型必须改 `loop.on_event`，
  中断做到工具执行中途必须改 `tools/shell.py`。改为「core 可动但只加不改语义」。
- **范围**：做——事件流定型（参照 pi 三层生命周期）、steering/followUp 双队列、REPL；TUI 后半程动工。不做——alt-screen、主题系统、鼠标。
- **TUI 设计原则**（现在拍板，实现时不再议）：
  1. `Component.render(width) -> list[str]` 纯函数契约，组件不持终端句柄；
  2. 只做 main-screen 模式（渲染进主屏 + scrollback，滚动交给终端），不给 main-screen 假装 sticky 语义——理由见 pi-mono `tui-plan.md`；
  3. CURSOR_MARKER 零宽标记定位硬件光标（中文 IME 候选框位置正确的关键）；
  4. 差量重绘等性能优化后置，先正确后快。
- **参照**：pi `packages/tui/src/tui.ts`（Component 契约）、pi-mono 根目录 `tui-plan.md`（36KB 设计文档，动工前通读）、`packages/agent/src/agent.ts`（PendingMessageQueue）。
- **前置精读**：
  - [x] [knowledge/source-walks/pi-agentloop.md](../../knowledge/source-walks/pi-agentloop.md)
  - [x] [knowledge/claude-docs/interactive-mode.md](../../knowledge/claude-docs/interactive-mode.md)（官方交互契约：中断两级 / 干活时输入 / `!` shell 模式 / 历史三细节）
- **顺带工具**：AskUserQuestion（REPL 才有真人可问）。
- **流程**：REPL 与 TUI 各走一次 superpowers 全链路。
  REPL 档案：[features/05-20260810-repl/](features/05-20260810-repl/README.md)（8 task TDD，193 passed）。

## 阶段 3 · 记忆（已交付 2026-08-10）

- **目标**：分层记忆文件加载（项目/用户级）+ 会话学得的东西写回。
- **档案**：[features/06-20260810-memory/](features/06-20260810-memory/README.md)（7 task TDD，235 passed）。
  两条裁决：指令进第一条 user 消息（D#42，代价是必须自己实现压缩后重注入）、
  只读 PAI.md 三层不读 AGENTS.md（D#43）。
- **参照**：CC `src/memdir/`（findRelevantMemories/memoryScan）；面试准备 `12_记忆系统/深度_CC记忆系统.md`（外部参照）。
- **前置精读**：
  - [x] [knowledge/claude-docs/memory.md](../../knowledge/claude-docs/memory.md)（两套记忆的加载算法；**读出一条 pai 未来的 bug**：压缩会摘掉指令文件，官方靠重注入兜）
- **流程**：superpowers 全链路。

## 阶段 4 · 权限（已交付 2026-08-10）

- **目标**：`before_tool_call` 挂点上的权限层：allow/ask/deny 三态规则 + 规则语义下放给工具解释。
- **档案**：[features/07-20260810-permissions/](features/07-20260810-permissions/README.md)
  （7 task TDD + 补一根 spec 漏接的线，329 passed）。
  五条裁决：求值顺序不按特异性排（D#46）、默认 allow 及其交付后自我复议（D#47）、
  ask 无真人时降级为 deny（D#48）、matcher 签名加 MatchContext（D#49，**偏离已拍板 spec，待复议**）、
  hook 崩溃不阻断（D#50）。
  **门禁必须带测试**这条 anna 回流已兑现：三条注入反证（翻求值顺序 / require_all 恒 False /
  不拆复合命令）各自打红了不同的测试集，且**自举跑通了 pai 自己的 `guards/design_gate.py`**。
- **补课档案**：[features/09-20260810-working-dir-boundary/](features/09-20260810-working-dir-boundary/README.md)
  （2026-08-11，用户实测质疑「上级目录照理不能看」引出）。
  阶段 4 交付的是**引擎**，策略是空的——默认兜底是常量 `allow`，不配置就等于没有权限层。
  09 补上策略：工作目录边界（D#51 推翻 D#47）、符号链接双路径、危险路径 bypass 免疫、
  权限模式四态（D#53）、hook fail-closed（D#54 复议 D#50）。7 task TDD，385 passed。
  **教训**：本阶段前置精读的 `permissions-hooks.md` 里「工作目录/cwd/边界」grep 零命中，
  pi 侧只有一句「参照 beforeToolCall」——精读覆盖了文档每一节，却漏掉一整层机制。
  补 [cc-pi-permission-boundaries.md](../../knowledge/source-walks/cc-pi-permission-boundaries.md)。
- **范围**：做——三态规则、按 source 分桶（user/project）、bash 前缀匹配与路径匹配。anna 门禁思想回流：ask 只用在必须真人拍板的节点、门禁三种退出码、**门禁必须带测试**（注入已知错误断言真会拦——这是对 anna 短板的修正）。不做——LLM 分类命令危险度、配置硬编码。
- **参照**：CC `src/utils/permissions/`（规则三态 + 语义下放）；anna `guards/`。
- **前置精读**：
  - [x] [knowledge/anna/gates.md](../../knowledge/anna/gates.md)（**本地不入库**，R2#1 裁决——克隆者无此文件，测试对 gitignored 目标放行）
  - [x] [knowledge/claude-docs/permissions-hooks.md](../../knowledge/claude-docs/permissions-hooks.md)（求值顺序 deny→ask→allow、Bash 复合命令/包装器/词边界四坑、「语义下放给工具」的原文、hook 决策优先级）
- **流程**：superpowers 全链路。

## 阶段 5 · 流式（已交付 2026-08-11）

- **目标**：流式输出 + 工具执行中断。
- **范围**：必修前置（TODO 已记）——并行工具调用的 usage 重复累加问题
  （⚠️ **2026-08-11 实测：这条的前提不成立**——它是 Anthropic 协议下「一个 content block 一条
  assistant 记录」的后果，OpenAI 兼容协议下一次响应只有一份 usage。范围待 brainstorm 重定，
  见 [features/11](features/11-20260811-streaming/README.md)）。中断参照子 AbortController 思路：工具出错杀兄弟任务但不向上传播取消。工具能力标志（is_read_only / is_concurrency_safe）在此阶段进 `@tool` 装饰器——调度靠标志，不靠 if-else 判工具名。
- **参照**：CC `src/services/tools/StreamingToolExecutor.ts`；CC `src/Tool.ts` 的 `isConcurrencySafe` / `isReadOnly`（能力标志，默认保守全 false。反编译源码行号会漂，检索符号名）。
- **前置精读**：
  - [x] [knowledge/concepts/streaming-tool-calls.md](../../knowledge/concepts/streaming-tool-calls.md)（OpenAI 兼容协议的流式：tool_calls 按 index 归并、usage 在哪、中断没有 usage。**含 6 个真实探针**）
  - [x] [knowledge/source-walks/cc-streaming-tools.md](../../knowledge/source-walks/cc-streaming-tools.md)（CC `StreamingToolExecutor` + `Tool.ts` 能力标志 + 保序分批 + 兄弟取消）
  - ~~官方 streaming 相关章节 → 届时落 knowledge/claude-docs/~~ —— **2026-08-11 改写，理由留档**：
    官方 Claude Code 文档**没有 streaming 章节**（见 [claude-docs/map.md](../../knowledge/claude-docs/map.md) 的覆盖图），
    而 pai 走的是 **OpenAI 兼容协议打 DeepSeek**，真正约束 pai 的是 DeepSeek 的
    `stream` / `stream_options` 语义。所以这条落到 `concepts/`（无单一外部原文可链）而非 `claude-docs/`。
    **且实测与 DeepSeek 官方文档不符**——`include_usage` 是空操作、没有文档说的那个「choices 为空」的额外块，
    证据见 [features/11 evidence](features/11-20260811-streaming/evidence/20260811-流式探针/说明.md)。
- **顺带工具**：WebFetch / WebSearch（长耗时工具最受益于流式与中断；单独立项走「中等改动」流程亦可提前）。**未做**，仍在随做清单里。
- **流程**：superpowers 全链路。
- **档案**：[features/11-20260811-streaming/](features/11-20260811-streaming/README.md)（6 task TDD，509 passed）。
  交付形态是**方案 B**：做了流式输出 + 能力标志 + 保序并发；**没做**边流边派发与兄弟取消
  （实测边流边派发最多抢 16% 流时间，而 CC 那套复杂度全为它付）。
  三条升格的取舍见 [D#57](decisions.md)（一次响应一条消息）、[D#58](decisions.md)（usage 每块都看）、
  [D#59](decisions.md)（权限按批前置）。

## 阶段 6 · skills / MCP client

- **目标**：按需加载的能力扩展。两个子阶段，skills 先行。
- **参照**：CC `src/skills/`；官方 skills / MCP 章节。
- **前置精读**：
  - [ ] 官方 skills 章节（https://code.claude.com/docs/zh-CN/skills）
  - [ ] 官方 MCP 章节（https://code.claude.com/docs/zh-CN/mcp）
- **顺带工具**：ToolSearch（工具多了才需要延迟加载与检索——在此之前是过度设计）。
- **流程**：superpowers 全链路，两个子阶段各一轮。

## 阶段 7 · evals

- **目标**：真实会话轨迹回放评测 + 跑批（evals/ 目录已预留）。
- **参照**：pi `packages/evals/`（vitest-evals 驱动）；面试准备 `07_评测与可观测性`（外部参照）。
- **前置精读**：
  - [ ] 届时定（评测无单一官方章节，以面试准备专题为索引）。
- **流程**：superpowers 全链路。

---

## 随做清单（不占阶段，条件成熟即做）

- ~~AskUserQuestion~~ → 归阶段 2（REPL 才有真人可问）
- ~~ToolSearch~~ → 归阶段 6（工具少时是过度设计）
- WebFetch / WebSearch → 独立小工具，走「中等改动」流程（简述方案获认可后分支 + TDD 直做），阶段 5 前后做性价比最高
- **用户级配置**（2026-08-10 用户提出）→ **归阶段 4**：api key / 模型 / 上下文窗口这些
  「跟人走而不是跟项目走」的配置该有个用户级的家。`~/.pai/.env` 的兜底已先修掉（当天小修），
  但完整形态是 `~/.pai/settings.json`——**而阶段 4 权限本来就要引入这个文件**
  （用户层 + 项目层两级规则），两件事共用同一套加载与合并逻辑，一起做最省。
  归属确定前不要另起炉灶。
- microcompact（清可重放工具的旧结果）→ 阶段 1 完成后评估，见 [cc-compaction 笔记](../../knowledge/source-walks/cc-compaction.md)
