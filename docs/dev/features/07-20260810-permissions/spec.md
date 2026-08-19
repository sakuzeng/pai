# 07-20260810-permissions · spec

2026-08-10 brainstorm 定稿（四问拍板记录见 [README](README.md)「候选方案与确认」）。

## 背景与问题

pai 现在没有任何权限层：模型说跑 `rm -rf /` 就跑 `rm -rf /`。唯一的防线是
`guards/design_gate.py`，但那是给开发者的（Claude Code 改 pai 源码时拦一下），
不是给 pai 自己跑起来时用的。阶段 4 要把这层补上，并且长在代码挂点上而不是提示词里
——官方原话：权限由 harness 强制，不由模型强制（K permissions-hooks.md 第八节）。

## 目标（做什么）

### 1. `core/permissions.py` —— 规则与三态求值

- `Rule`：`tool`（工具名，支持裸名与 `*` glob）、`specifier`（可选）、`source`（`user` / `project`）。
  解析 `"Bash(git push *)"` 这种字符串形式。
- `RuleSet`：`deny` / `ask` / `allow` 三桶。
- `decide(tool, args, ruleset) -> Decision(kind, reason, rule)`：
  求值顺序 deny → ask → allow，第一个匹配决定，特异性不改变顺序。
  必须有测试钉死：`deny=["Bash(aws *)"]` + `allow=["Bash(aws s3 ls)"]` → deny。
  这是最容易被「优化成按特异性排序」的地方，改了会静默放开一个洞。
- 没有任何规则命中 → `default_decision`（默认 `allow`，见 README 的自主判断）。

### 2. 匹配语义下放给工具（拍板问 2）

- `Tool` 增字段 `matcher: Optional[Callable[[str, dict, bool], bool]]`，
  签名 `(specifier, args, require_all) -> bool`；没有 matcher 时用默认实现
  （对工具的第一个参数值做通配符匹配）。
- 新增 `matcher_for(tool_func)` 装饰器，把匹配函数挂到已注册的 `Tool` 上——
  不改 `@tool` 本身（它只负责 schema 与代码同源这一件事）。
- `require_all` 参数捕获一条真实的不对称性：
  - allow 判定：复合命令的每个子命令都必须匹配才放行（官方语义）；
  - deny / ask 判定：任一子命令匹配即命中。
  与官方符号链接规则的不对称（allow 要两头都干净、deny 一头脏即拦）是同一个思想。

### 3. bash 的匹配器（四个坑逐条实现）

1. 复合命令拆分：分隔符 `&&`、`||`、`;`、`|`、`|&`、`&`、换行。
2. 进程包装器剥离：`timeout`、`time`、`nice`、`nohup`、`stdbuf`，以及不带标志的 `xargs`。
   明确不剥离 `npx` / `docker exec` / `devbox run` 这类环境运行器——官方明说
   `Bash(devbox run *)` 会把 `devbox run rm -rf .` 一起放行，pai 照抄这个保守取舍并在注释写明。
3. 词边界：`Bash(ls *)` 匹配 `ls -la` 但不匹配 `lsof`；`Bash(ls*)` 两者都匹配；
   `:*` 后缀等价于尾部 ` *`（仅在模式末尾识别）。
4. 不做：`watch`/`setsid`/`flock` 的「永远提示」名单、只读命令内置集合——
   pai 的默认决策是 allow，没有「只读免提示」这个概念的位置（真需要时再加）。

### 4. fs 工具的匹配器（路径锚点）

- `//path` = 文件系统根绝对路径；`~/path` = 主目录；`path` / `./path` = 相对 cwd。
- `/path` 锚定「定义规则的设置文件」（官方最大的坑）：项目设置里的 `/src/**` 是
  `<项目根>/src/**`，用户设置里的 `/secrets/**` 是 `~/.pai/secrets/**`。
  所以 `Rule` 必须带 `source` 与其锚点目录——这也是问 4 选「按 source 分桶」的另一个理由。
- 裸文件名按 gitignore 语义在任意深度匹配：`Read(.env)` ≡ `Read(**/.env)`。
- 不做：符号链接的双路径检查（要 `realpath` 且与沙箱边界纠缠）——如实记 TODO，
  这是本轮已知的一个洞。

### 5. 配置加载（拍板问 4）

- `~/.pai/settings.json` → `./.pai/settings.json`，合并成一个 `RuleSet`，每条规则记 `source`。
- 任一层 deny 都不能被另一层 allow 翻掉——这是求值顺序的自然结果（deny 桶先查），
  但要有测试专门钉死跨层的情形。
- 裸工具名 deny → 工具从模型视野里消失：`get_tools()` 已有子集能力
  （`INTERACTIVE_ONLY` 就是这么做的），把被裸名 deny 的工具摘掉即可，几乎不用新代码。
  带 specifier 的 deny 则保留工具、拦调用（官方明确区分这两种）。

### 6. `core/hooks.py` —— 外部命令 hook（拍板问 3）

- 配置：`settings.json` 的 `hooks.PreToolUse: [{matcher, command, timeout}]`。
- 三种退出码：`0` = 解析 stdout 的 JSON（`permissionDecision` ∈ allow/deny/ask）；
  `2` = 阻断，stderr 作为给模型的理由；其他 = 非阻断错误，只告警继续。
- 多个 hook 决策冲突时：deny > ask > allow（官方还有 `defer`，pai 不做）。
- 两条边界必须有测试（否则 hook 会被当成万能开关）：
  - hook 返回 `allow` 绕不过 deny/ask 规则；
  - hook 的阻断（退出码 2）优先于 allow 规则。
- hook 自身异常/超时绝不阻断工作（anna 铁律，`design_gate.py` 已有先例）。

### 7. 接线进 loop 与两个模式

- `run_agent` 新增 keyword-only `before_tool_call: Callable[[str, dict], Decision] | None`
  （默认 None = 行为与接线前逐字相同）。权限层是它的一个实现，不是唯一实现。
- 判定位置：工具循环里、`ToolStart` 事件之前。
- `deny` → 不执行工具，把理由当作工具结果回填（`tool_call_id` 配对是硬约束，D#41 同款）。
- `ask` → REPL 里走 `ask_user_question` 的真人通道；无真人时降级为 deny + 说明（问 1）。
- 新事件 `PermissionDecided(tool, decision, reason)`；REPL 加 `/permissions` 列规则与来源。

## 非目标（明确不做）

- 官方六种权限模式里只取 `default` 语义；`acceptEdits` / `plan` / `auto`（要分类器模型）/
  `dontAsk` / `bypassPermissions` 都不做（默认决策可配置已覆盖大部分需求）。
- 托管策略层、工作区信任对话框、`claudeMdExcludes` 之类的组织部署功能。
- 沙箱（OS 级强制）、符号链接双路径检查（如实记 TODO）。
- 只读命令内置免提示集合；`watch`/`flock` 永远提示名单。
- hook 的 `defer` 决策、`updatedInput`（改写工具入参）、HTTP/MCP/prompt/agent 四种 hook 类型。

## 验收标准

- 求值顺序：`deny=["Bash(aws *)"]` + `allow=["Bash(aws s3 ls)"]` → deny，有测试。
- 复合命令：`allow=["Bash(ls *)"]` 时 `ls && rm -rf /` 不放行，有测试。
  这条要是漏了，整个权限系统等于零。
- 包装器：`allow=["Bash(npm test *)"]` 匹配 `timeout 30 npm test`；
  `allow=["Bash(devbox run *)"]` 确实会放行 `devbox run rm -rf .`（把官方承认的这个洞
  写成测试固定下来，而不是假装没有）。
- 词边界：`Bash(ls *)` 不匹配 `lsof`。
- 裸名 deny：被裸名 deny 的工具不出现在发给模型的 tool schema 里。
- hook 两条边界各有测试；hook 崩溃/超时不阻断工作。
- ask 降级：once 模式命中 ask → deny 且理由回填，`tool_call_id` 配对不破。
- 门禁必须带测试（roadmap 硬要求）：注入一条已知会被拦的调用，断言真的被拦；
  再把判定函数改错，断言测试变红（注入反证写进 devlog，抄 task 4 与 design_gate 的做法）。
- `./test.sh` 全绿全离线；每步红→绿真实数字进本目录 devlog.md；遗留逐条进 TODO。
