# pi agent 分层与钩子（指针）

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）`packages/agent/src/`（types.ts 是全部契约所在，437 行，值得通读）；深度对照见外部参照 2（本文不重复）
- 精读日期：2026-08-09
- pai 锚点：`src/pai/core/loop.py`、`src/pai/modes/`（roadmap 阶段 2）

## pai 阶段 2（REPL/TUI）直接要用的结论

**pi 把 agent 拆成四层，每层可单独用：**

1. `agentLoop()` —— 无状态纯循环函数（792 行，不含任何业务）
2. `Agent` 类 —— 有状态 + 事件订阅
3. `AgentHarness` —— 会话/技能/压缩/工具
4. `AgentSession` —— 应用层编排（interactive / print / rpc 三种模式共用它——解耦成功的证明）

pai 现状对应第 1 层（`run_agent`）+ 半个第 4 层（modes/once）。REPL 需要的增量主要是：

- **事件流**：pi 的 `AgentEvent` 三层生命周期（agent_start/end、turn_start/end、
  message_start/update/end、tool_execution_start/update/end），扁平 discriminated union。
  pai 的 `on_event` 已是雏形，REPL 前需把事件类型定齐。
- **steering / followUp 双队列**（`agent.ts` 的 `PendingMessageQueue`）：steering 在
  工具执行完后注入（中途转向），followUp 在 agent 本该停下时注入（排队续问）。
  这是「用户在 agent 干活时打字」的完整解法，代码量极小。REPL 的核心体验就靠它。
- **所有可变性通过钩子注入**（`AgentLoopConfig`）：`convertToLlm`（UI-only 消息过滤）、
  `transformContext`（压缩挂点）、`beforeToolCall`（权限挂点，返回 block+reason 即拦截）、
  `afterToolCall`、`getSteeringMessages`、`getFollowUpMessages`。
  pai 阶段 2/4 的功能都应长在这类挂点上，不进 loop 本体。

**TUI 侧的 pi 事实**（pai 的取舍在 roadmap 阶段 2，此处只记 pi 怎么做）：

- `Component.render(width) -> list[str]` 是唯一必须实现的契约；不用 React/Ink，
  pi-tui 运行时依赖只有 marked + get-east-asian-width。
- CURSOR_MARKER 技巧：焦点组件在光标位置吐零宽 APC 序列，TUI 扫描剥离后把硬件光标
  定位过去——IME（中文输入）候选框位置正确的关键。
- pi 有 main-screen（渲染进主屏+scrollback，滚动交给终端）与 alt-screen（自带受限
  布局系统）**两种**渲染模式；`tui-plan.md`（仓库根目录，36KB 设计文档）明写
  「不要给 main-screen 假装有 sticky/nested-scroll 语义」。
  另注：AgentSession 在 `packages/coding-agent/src/core/agent-session.ts`，
  不在本文来源行的 packages/agent/src/ 下。
