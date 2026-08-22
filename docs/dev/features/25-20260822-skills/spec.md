# feature 25 · skills — spec

拍板依据：README「候选方案与确认」四问（B 工具形态 / A 重挂正文 / A 两层+项目赢 /
A 带 /skill 命令）。参照笔记：knowledge/skills/ 四篇；动工前反向对照 evidence 三条。

## 1. 数据与扫描（`core/skills.py`，新模块）

新模块只依赖 `core/memory.py` 的 `parse_frontmatter`（复用，用户约束 3）与标准库；
不 import loop 内部（AGENTS 架构约束）。

- `Skill`（frozen dataclass）：`name`、`description`、`path`（SKILL.md 绝对路径）、
  `base_dir`、`source`（`"user" | "project"`）、`model_invocable: bool`。
- 目录（拍板问 3）：用户级 `~/.pai/skills/`、项目级 `<cwd>/.pai/skills/`，
  路径函数进 `core/paths.py`（路径规则只此一处，feature 08 规矩）。
- `scan_skills(*, cwd=None, home=None, warn=None) -> list[Skill]`：
  - 每个根下的直接子项：目录含 `SKILL.md` → 一个 skill（name=目录名）；
    扁平 `<name>.md` → 一个 skill（name=文件名去后缀）。同根内同名时目录包赢
    （更具体）。不递归更深层（dsh 同款，pi 的递归发现记遗留）。
  - 同名跨根冲突：项目级赢（拍板问 3，dsh 语义）。
  - description 取自 frontmatter；缺失或 frontmatter 损坏 → 跳过并 warn 一行
    （fail loud）。刻意不抄 CC 的「回退正文首段」：动工前反向对照证实那条回退
    会把写坏的 frontmatter 伪装成正常 skill（evidence P1）。
  - `disable-model-invocation: true` → `model_invocable=False`（仍可被 /skill 调）。
  - name 合法性（kebab-case，agentskills.io）只 warn 不拒载（pi 宽松语义）；
    路径永远来自扫描结果而非由 name 反推，结构上无路径穿越面。
  - 名字来源照三家共识：目录名/文件名就是名字，frontmatter `name` 忽略
    （evidence P2/P3：CC 实测命令名来自目录名）。
- 扫描时机：装配期一次（pi 同款）。会话中途增删 skill 不生效，记遗留
  （CC 的实时变更检测不做）。

## 2. 索引注入（装配层加段，用户约束 1——loop 不动）

- `render_catalog(skills, *, max_desc_chars=500, max_bytes=8000) -> str`：
  只含 `model_invocable` 的 skill，按名排序，`<available_skills>` 内每条
  `<skill><name/><description/></skill>`，XML 转义；不含路径（工具形态下模型
  不需要路径——dsh 同款配对，见 K skills/dsh-skills.md「两个决定是绑定的」）。
  每条 description 截 500（dsh `catalogDescriptionMaxLength` 默认值）；
  总量超 8000 字节（CC 无窗口信息时的兜底预算）截断并留提示行
  （memory `render_index` 的双上限模式）。空列表返回空串。
- `build_system_prompt(tools, skills_catalog=None)` 加可选参数：
  `skills_catalog` 非空且 `"skill" in tools` 时追加一段指导语 + 目录。
  不传时输出逐字节不变（护缓存前缀 + 老路径不动，feature 22 既有不变量）。
- once 与 interactive 的装配点把 `scan_skills` 结果接进
  `build_system_prompt` 与 skill 工具注入点。

## 3. skill 工具（`core/tools/skill.py`，拍板问 1·B）

- `skill(name: str)`：从注入的目录表查 → 不在表中或 `model_invocable=False` →
  返回「未知或不可用」错误串并列出可用名字（不区分两种情况，不泄露被隐藏者——
  dsh 同款）。命中 → 当场重读磁盘（dsh：注册表不缓存正文），剥 frontmatter，
  返回 `<skill_content name="…">正文</skill_content>` + 一行相对路径基准说明
  （附属文件用 read_file/bash 从 base_dir 解析）。
- 成功加载记入注入的已加载追踪器（供压缩重挂）。
- 能力声明：`capabilities_for(read_only=True, concurrency_safe=True)`。
- 边界声明：`path_access_for(READ)`，getter 按 name 从目录表解析 SKILL.md 路径；
  未知名字返回 cwd——让判定放行、错误由工具自己报「未知 skill」，
  不让幻觉名字撞出权限话术（R4#10 同款教训）。
- 装配层把用户级 skills 根加进 `WorkingDirs.additional`（once 与 interactive
  都传 `working_dirs`）：否则 once 下用户级 skill 的正文与附属文件
  （read_file）全被边界兜底拦死，功能结构性不可用。代价如实声明：
  `~/.pai/skills/` 下任何文件的读取从此免问。
- 注入点模式照 memory_tool：`set_catalog(...)`、`set_tracker(...)`
  （装配期写、执行期只读，feature 11 已核实此模式线程安全）。

## 4. 压缩后重挂（拍板问 2·A，机制搭 D#42 的车——loop 不动）

- `core/skills.py` 提供 `LoadedSkills`（有序记录：name → 最近加载时刻）与
  `render_loaded_skills(loaded, catalog, *, per_skill_chars=20_000,
  total_chars=100_000) -> str`：最近加载优先，正文从磁盘重读（文件没了跳过），
  单个超限截头部保留（CC：setup/usage 在头部），总预算装不下整条丢弃。
  预算取 CC 的 5k/25k token × 4 字符换算，常量旁注明来源与「未实测校准」。
- 装配层把 `instructions=build_context` 换成组合 loader：
  `build_context() + render_loaded_skills(...)`。首次注入时追踪器为空、行为不变；
  压缩后 loop 既有的重注入路径（loop.py 压缩块调 `_inject_instructions`）
  自动带上已加载正文——「压缩后已加载 skill 仍有效」由此成立，零 loop 改动。
- 已知边界（如实写）：压缩发生前，中途加载的 skill 正文只活在 tool_result 里，
  指令消息不更新（`_has_instructions` 短路，与「REPL 中途改 PAI.md 不生效」
  同一条既有行为）；重挂只在压缩重建时兑现——这恰好就是需要它的时刻。

## 5. /skill 命令（拍板问 4·A）

- REPL 与 TUI 的命令表加 `/skill <name> [args]`：查目录表（用户通道不看
  `model_invocable`——它只限模型），读盘展开成
  `<skill name="…">正文</skill>`（+ 参数追加块后，pi 形态），作为本轮任务
  跑一次正常模型轮次；同时记入已加载追踪器。
- 裸 `/skill` 列出可用 skills（名字 + description 截断）。未知名字给一行错误
  与可用列表。`/help` 更新。

## 6. 验收标准（对 README 的细化）

1. 扫描：两层目录、项目赢、目录包/扁平两形、缺 description 跳过且有提示——单测钉死；
2. 索引：description 进 system prompt、正文不进；预算截断留提示；
   `disable-model-invocation` 不进模型目录但 /skill 可调；
3. 加载：skill 工具返回正文与基准说明；未知名报「未知」而非权限话术；
   once 模式下用户级 skill 全链可用（边界测试钉死）；
4. 压缩后仍有效：离线测试构造真实压缩（含真实轨迹夹具做底），压缩重建后
   上下文中仍有已加载 skill 正文；
5. /skill 展开注入并跑通一轮（fake client）；
6. `./test.sh` 全绿；交付前反向对照真跑一个完整回合（真 API，模型自主调 skill）。

## 7. 非目标（v1 明确不做，逐条记遗留）

- frontmatter 扩展字段：`allowed-tools` / `model` / `context: fork` / `hooks` /
  `paths` / 参数替换（`$ARGUMENTS` 等）——CC 完整形态，等真实需要；
- 会话中途的 skills 实时变更检测（CC watcher / dsh Chokidar）；
- 嵌套目录递归发现（pi 形态）与外部目录兼容（`~/.claude/skills` 挂载）——
  后者做成 settings 配置项的路留着；
- 列表按「调用频率」排预算优先级（CC）——pai 无调用统计；
- ToolSearch（roadmap 顺带工具：工具多了才需要，现在 5 个）。
