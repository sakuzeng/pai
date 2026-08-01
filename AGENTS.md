# pai 开发规则

本文件给在此仓库工作的 AI agent（含 Claude Code）与人类协作者。风格学 pi 的 AGENTS.md：短、直接、可执行。

## 项目定位约束

- pai 是学习驱动的从零实现。除非用户明确要求，不要替用户实现学习路线图里标记为阶段任务的模块（compaction / permissions / streaming / skills / memory / mcp_client / evals）——这些是用户的作业。review 与讲解随时可以。
- 不引入 pi 或 Claude Code 的任何代码。参照的是设计思想，实现必须独立；每个与它们不同的取舍记入 docs/decisions.md。

## 架构约束

- schema 与代码同源：工具 schema 一律由 @tool 装饰器从函数签名 + Annotated 注解生成，禁止手写 schema 字典。
- 工具错误不 throw：工具内部异常必须转成字符串结果回填给模型（tool_call_id 严格配对），loop 不因单个工具失败而崩。
- 模块边界按学习阶段切：一个阶段一个模块，不要把多个阶段的逻辑塞进 loop.py。
- 依赖注入优先：loop 的 client / model / tools 都可注入，保证离线可测。

## 测试

- 不依赖网络的测试用 tests/fake_llm.py 的假 provider，禁止在单测里调真实 API。
- 需要真实 LLM 的测试打 @pytest.mark.llm 标记，无 DEEPSEEK_API_KEY 时自动跳过。
- 新增或修改工具必须带对应单测（至少覆盖：正常路径 + 一个错误路径）。

## 代码

- Python >= 3.10，类型注解必写；不用 Any 除非确有必要。
- 中文注释只写"代码本身说不出的约束"，不写"下一行在干什么"。
- 提交信息格式：`{feat,fix,docs,test}(module): message`。永远不要未经要求就 commit。
