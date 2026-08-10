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
- docs/dev/需求池.md ——「用户想要什么」。用户提的想法先落这里（**记原话不转述**——转述会丢掉决定性细节），再决定出路：升格立档案 / 降格进 TODO / 划掉不做（保留理由）。与 TODO 的分工是硬的：那边是**已确认要做**的，这边是**还没评估**的。
- docs/dev/TODO.md ——「下一件该做什么」。**唯一的待办入口**，带优先级，每条注明出处。devlog 里新写的待办必须同步登记到这里，否则等于没记（曾经散在 8 条 devlog 里，记了但不可用）。显式例外仅一处：roadmap 各阶段的「前置精读」清单按阶段就地维护，不进本文件（R2#6 裁决）。
- docs/dev/features/\<NN\>-\<YYYYMMDD\>-\<名称\>/（日期=立项日）——「一个需求的一切文档」（需求/方案/问题/测试/日志/总结；拍板问答完整存档、evidence/ 按需归档，规矩见 features/README.md，机器可判部分由 tests/test_docs_consistency.py 强制）。**自 2026-08-09 起**：功能开发的详细日志写该目录 devlog.md，全局 devlog 只记里程碑一行 + 链接（既有历史条目冻结不迁移）；decisions 仍全局（编号体系不破，功能内选择写档案，够格的升格）；档案「遗留问题」每条必须同步一行登记 TODO。路线图模块与中等改动都立档案，小修不立。规矩与模板见 features/README.md。**此规矩有硬约束**：档案未拍板时 guards/design_gate.py（PreToolUse）会拒绝修改 src/tests——被拦时按提示补齐过程产物，不要代替用户拍板。

规矩：
- **交付即复盘**：需求做完、测试全绿之后写 `features/<NN>/复盘.md` 再宣告交付（模板四问）。
  其中「我现在质疑什么」必答——**允许也鼓励质疑已拍板的做法**，交付后掌握的信息比拍板时多，
  「早知道」得有个落点。写下疑问不等于推翻，够格的升格成 decisions 复议或 TODO。
- 一步一条，不攒着最后补。一次交付里若跨了多步，devlog 就写多条。
- 数字要真实：贴实际 pytest 输出（`18 passed`），不写"测试都过了"。
- 已知缺陷必须写进 devlog，不能只活在对话里——对话会丢，文件不会。
- 交付回复里也要说清：改了哪些文件、测试结果、以及哪些是刻意没做的。

## 知识沉淀

- 学习笔记（官方文档精读、源码走读、概念整理、方法论回流、**开发中撞出的可迁移工程知识**）进 knowledge/，须带统一头部（含 pai 锚点），并登记进 knowledge/README.md 的登记表。目录按**来源**分（官方文档 / 别人的源码 / 无单一外部原文），选哪个见 knowledge/README.md「结构」。开发知识分两种：只关于 pai 的（为什么这么设计、踩了什么坑）进 docs/dev/，换个项目仍成立的（POSIX 语义、Unicode 宽度这类）才进 knowledge/concepts/。写不出 pai 锚点的内容不进本仓库（去面试准备仓库）——唯一豁免是 knowledge/inbox.md：待消化的新工具/想法一行一项收留，升格成笔记时才须锚点。
- 路线图阶段动工前（superpowers brainstorm 之前），先核对 docs/dev/roadmap.md 该阶段「前置精读」清单：笔记缺失先读先记，再动工。诚实边界：勾选与登记只保证笔记文件存在且链接可达（tests/test_docs_consistency.py 机械校验），「人是否真读了」判不了——这是提示词层约束，别当成有保证。

## 架构约束

- schema 与代码同源：工具 schema 一律由 @tool 装饰器从函数签名 + Annotated 注解生成，禁止手写 schema 字典。
- 工具错误不 throw：工具内部异常必须转成字符串结果回填给模型（tool_call_id 严格配对），loop 不因单个工具失败而崩。
- 模块边界按学习阶段切：一个阶段一个模块，不要把多个阶段的逻辑塞进 loop.py。
- 依赖注入优先：loop 的 client / model / tools 都可注入，保证离线可测。

## 测试

- 不依赖网络的测试用 tests/fake_llm.py 的假 provider，禁止在单测里调真实 API。
- **测试绝不许写进真实 $HOME 或任何固定共享位置**：自动化测试一律用 pytest 的 `tmp_path`，`tests/conftest.py` 的 autouse fixture 已把 `$HOME` 结构性地隔离到临时目录（2026-08-10 教训：20 处调用点漏传路径，把测试数据写进了用户真实的 `~/.pai/history`，687 行里只有 3 行是用户自己的；这类污染不会让任何测试变红）。
- **手工冒烟/真跑 pai 在 `pai_playground/` 里做**（已 gitignore），需要事后翻看产物。真跑产生的轨迹一旦被当作测试夹具，须复制进版本库——否则夹具的溯源链断在一个不入库的目录里。
- 需要真实 LLM 的测试打 @pytest.mark.llm 标记，无 DEEPSEEK_API_KEY 时自动跳过。
- 新增或修改工具必须带对应单测（至少覆盖：正常路径 + 一个错误路径）。
- 新增阶段模块同样必须带单测，且至少一条测试拿真实会话轨迹（pai_playground/sessions/*.jsonl，抄进测试时剥掉 SessionLog 加的 ts 字段）当输入——编的字符串测不出中文、tool_calls.arguments 这类真实坑。

## 代码

- 类型注解必写；不用 Any 除非确有必要。注意：目标运行期是 Python 3.9.6（`pyproject` 写 >=3.9；本项目环境用 mkvirtualenv 的 `~/.virtualenvs/pai`，不激活时系统 `python3` 也是 3.9.6）。`./test.sh` 用**当前激活的** python3，pytest 头一行会打印实际版本，跑之前扫一眼。`dict[str, X]`、`list[int]` 这类内置泛型在 3.9 运行期就合法（PEP 585），可直接用；真正需要 `from __future__ import annotations` 的是 `int | None` 这类联合类型语法（PEP 604，3.10 才进运行期）。
- 中文注释只写"代码本身说不出的约束"，不写"下一行在干什么"。
- 提交信息格式：`{feat,fix,docs,test}(module): message`。永远不要未经要求就 commit。
