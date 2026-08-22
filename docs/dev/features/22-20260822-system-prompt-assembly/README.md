# 22-system-prompt-assembly
状态：已交付（2026-08-22）
分支：`feat/r4-e2-e3-extensibility`（与 feature 23 同批）
流程：中等改动（候选拍板后直做 + TDD，不走完整 spec/plan——改动集中在
      loop 的一个参数 + 一个纯函数，缝的形状拍板即是全部设计决策）

## 需求

出处：R4#E2（P1）。`loop.py` 的 `SYSTEM_PROMPT` 是常量，硬编码
「你有这些工具：bash、read_file、write_file、edit_file」——而真实装配下这句话
已经在说谎：REPL 显式加 `ask_user_question`、`visible_tools` 会按 deny 规则
删减工具，模型拿到的工具清单与 prompt 里宣称的对不上。skills 阶段必然要往
prompt 注入 skill 目录，这个缝现在不开、届时就是打补丁。

验收标准：
1. `run_agent` 不传新参数时行为逐字不变（既有测试一条不改就全绿）；
2. 装配层（once / interactive）传入按实际 tools 生成的 prompt，
   工具增减后 prompt 里的清单跟着变（有测试钉「REPL 的 prompt 含
   ask_user_question、once 的不含」）；
3. 生成是纯函数，可离线测；
4. 全绿，数字进 STATUS。

## 候选方案与确认

### 方案 A · 装配层生成字符串，loop 收 `system_prompt: Optional[str]`

新纯函数 `build_system_prompt(tools)` 按实际工具字典生成完整 prompt
（工具清单部分从 `Tool` 的名字与描述拼）；`run_agent` 加 keyword-only
参数 `system_prompt=None`，None 时用现常量逐字不变；once / interactive
装配时传生成结果。skills 阶段在装配层拼接 skill 目录即可，loop 不再动。
- 优点：与 `instructions`（装配层闭包、loop 只认回调/值）同款先例；
  loop 零新概念；顺手修掉「prompt 谎报工具集」这个已知谎言。
- 代价：CLI 真实路径的 system prompt 内容会变（provider 前缀缓存 miss 一次，
  一次性成本）；直接调 `run_agent` 的老调用方仍拿旧常量（刻意的兼容）。

### 方案 B · loop 收 builder 回调 `Callable[[dict], str]`

loop 在建 system 消息时调 `builder(tools)`。
- 优点：单一事实源（用 loop 手里的 tools，装配层不用先算好）。
- 代价：loop 多认识一种回调形状；与 instructions 先例不同
  （它是无参回调）；测起来要多绕一层。实际上装配层本来就持有 tools，
  「先算好再传」并不丢信息。

### 方案 C · 只开缝不修谎

加参数但 once / interactive 也不传，等 skills 阶段再用。
- 优点：真实路径零变化。
- 代价：已知的「prompt 谎报工具集」再留一程；缝没有真实使用者，
  形状对不对要到 skills 阶段才知道。

### 确认

问 1（2026-08-22，AskUserQuestion）：缝开成什么形状（候选 A/B/C 如上）？
用户答（原话）：「cc是怎样做的呢，参照它的实现」。
CC 实证（反编译源码，检索符号名）：`src/constants/prompts.ts` 的
`getSystemPrompt(tools, model, additionalWorkingDirectories, mcpClients)`——
装配层 async 函数收实际 tools，返回分段数组；段内按
`enabledTools = new Set(tools.map(_.name))` 条件化（`hasAskUserQuestionTool`
才加「不理解拒绝原因就去问」那条、`hasAgentTool` 才加子代理指导）；
`SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 把静态前缀与会话相关段分开，注释明说
动态位放前面会把缓存前缀哈希裂成 2^N 变体（PR #24490/#24171 同类 bug）。
调用方（QueryEngine 经 `fetchSystemPromptParts`）算好后传给 query——
即「装配层算好、loop 收成品」，与候选 A 同形。
选择：A，带两条 CC 修正——① 工具段按「有没有这个工具」条件化生成
（不是干列名字；schema 本来就走 API 的 tools 参数）；
② 生成结果在会话内稳定（装配期算一次），护住 pai 实测 84~91% 的缓存命中。
不抄的：分段数组（Anthropic system 收块数组，OpenAI 兼容协议是单字符串，
pai 用 join）；MCP/skills 段（届时在装配层加段即可，这正是开缝的目的）。

## 结果与总结

已交付：`build_system_prompt(tools)` 纯函数（loop.py，形状照 CC——只列名字、
指导按工具条件化、同工具集生成逐字稳定护缓存）+ `run_agent(system_prompt=None)`
兼容缝（不传逐字不变，有守卫测试）。三个装配点全部接线：once、`_run_turn`、
`_run_shell`（首个动作是 `!命令` 时由它建 system，不接线会建出常量且整会话
换不掉）。REPL 的 prompt 从此承认 ask_user_question、once 的按过滤后工具集说话。
测试 4（loop）+ 2（装配，含「once 不再发常量」判别断言）。

## 遗留问题

<!-- 每条必须同步一行登记 ../../TODO.md -->

- CC 的 env 段（cwd/日期/模型进 prompt）未抄——本轮只开缝修谎；skills 阶段
  加段时一并评估（已并进 TODO E 系列条目追记，不单独立项）。

## 用到的知识

- K [loop/cc-prompt-and-transcript.md](../../../../knowledge/loop/cc-prompt-and-transcript.md)（本轮走读沉淀）。
