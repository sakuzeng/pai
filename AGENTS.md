# pai 开发规则

本文件给在此仓库工作的 AI agent（含 Claude Code）与人类协作者。风格学 pi 的 AGENTS.md：短、直接、可执行。

## 项目定位约束

- pai 是学习驱动的从零实现，但走 AI coding：路线图里的阶段模块（compaction / permissions / streaming / skills / memory / mcp_client / evals）可以直接由 AI 实现，不必等用户先写。代价是留痕——见「留痕」一节，做了什么必须可回溯，否则代码写完了人没学到。
- 实现阶段模块一律走 TDD：先写测试跑红（红的输出要贴出来），再写实现跑绿（绿的数字要贴出来）。不允许"先写实现，再补测试"。
- 不引入 pi 或 Claude Code 的任何代码。参照的是设计思想，实现必须独立；每个与它们不同的取舍记入 docs/dev/decisions.md。

## 留痕

开发记录一律进 docs/dev/（docs/ 根目录留给面向用户的文档，学 pi 的分法）。四个文件分工不同，都不许省：

- docs/dev/devlog.md ——「做了什么」的时间线。每完成一步追加一条，含：目标、动了哪些文件、红→绿的实际测试数字、留下的已知缺陷/待办。这是用户回看 AI 干了什么的唯一入口。
- docs/dev/decisions.md ——「为什么这么选」。只记有取舍的地方（pi/CC 怎么做 → pai 怎么做 → 理由），不记流水账。
- docs/dev/STATUS.md ——「现在到哪了」。一页的当前状态快照，给接手者（人或 AI）看的：模块状态、实测数据、已知缺陷、下一步。阶段性节点更新，不必每步动。
- docs/dev/TODO.md ——「下一件该做什么」。**唯一的待办入口**，带优先级，每条注明出处。devlog 里新写的待办必须同步登记到这里，否则等于没记（曾经散在 8 条 devlog 里，记了但不可用）。

规矩：
- 一步一条，不攒着最后补。一次交付里若跨了多步，devlog 就写多条。
- 数字要真实：贴实际 pytest 输出（`18 passed`），不写"测试都过了"。
- 已知缺陷必须写进 devlog，不能只活在对话里——对话会丢，文件不会。
- 交付回复里也要说清：改了哪些文件、测试结果、以及哪些是刻意没做的。

## 架构约束

- schema 与代码同源：工具 schema 一律由 @tool 装饰器从函数签名 + Annotated 注解生成，禁止手写 schema 字典。
- 工具错误不 throw：工具内部异常必须转成字符串结果回填给模型（tool_call_id 严格配对），loop 不因单个工具失败而崩。
- 模块边界按学习阶段切：一个阶段一个模块，不要把多个阶段的逻辑塞进 loop.py。
- 依赖注入优先：loop 的 client / model / tools 都可注入，保证离线可测。

## 测试

- 不依赖网络的测试用 tests/fake_llm.py 的假 provider，禁止在单测里调真实 API。
- 需要真实 LLM 的测试打 @pytest.mark.llm 标记，无 DEEPSEEK_API_KEY 时自动跳过。
- 新增或修改工具必须带对应单测（至少覆盖：正常路径 + 一个错误路径）。
- 新增阶段模块同样必须带单测，且至少一条测试拿真实会话轨迹（pai_playground/sessions/*.jsonl，抄进测试时剥掉 SessionLog 加的 ts 字段）当输入——编的字符串测不出中文、tool_calls.arguments 这类真实坑。

## 代码

- 类型注解必写；不用 Any 除非确有必要。注意：当前 venv 实跑 Python 3.9.6（pyproject 写的是 >=3.9）。`dict[str, X]`、`list[int]` 这类内置泛型在 3.9 运行期就合法（PEP 585），可直接用；真正需要 `from __future__ import annotations` 的是 `int | None` 这类联合类型语法（PEP 604，3.10 才进运行期）。
- 中文注释只写"代码本身说不出的约束"，不写"下一行在干什么"。
- 提交信息格式：`{feat,fix,docs,test}(module): message`。永远不要未经要求就 commit。
