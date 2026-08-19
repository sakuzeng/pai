# CC 的目录边界 vs pi 的零内置权限

- 来源：CC 反编译源码 `src/utils/permissions/filesystem.ts`（本机，见 knowledge/README 外部参照）；
  pi 侧经由外部参照 4 `13_安全与权限/深度_权限与安全.md`（该笔记直接走读了
  pi `packages/coding-agent/docs/security.md`、`src/core/extensions/runner.ts`、
  `examples/extensions/{permission-gate,confirm-destructive,protected-paths}.ts`）
- 精读日期：2026-08-10
- pai 锚点：`src/pai/core/permissions.py`、docs/dev/decisions.md #47 #50、features/09

为什么补这一篇：阶段 4 的前置精读 `permissions/claude-permissions-hooks.md` 里
「工作目录 / cwd / 目录边界」grep 零命中，pi 侧则整个阶段只有一句
「参照 pi 的 `beforeToolCall`」。结果是 pai 把 CC 的引擎照抄了，
策略一条没抄，而 pi 的免责声明也没抄——交付出一个看着像 CC 的不设防 agent。
本篇补的就是这个缺口，由用户 2026-08-10 的质疑逼出来。

## 一、CC 的默认不是常量，是一个函数

pai 的 `decide()` 兜底是 `rules.default_decision`（一个常量，默认 `allow`）。
CC 没有这个东西。`checkReadPermissionForTool` 的完整求值链（`filesystem.ts:1030-1193`）：

| 步 | 检查 | 结果 |
|---|---|---|
| 1 | UNC 路径（`\\` / `//`） | ask |
| 2 | 可疑 Windows 路径（ADS、短名、`...`） | ask |
| 3 | read deny 规则 | deny |
| 4 | read ask 规则 | ask |
| 5 | 写权限蕴含读权限 | 若 allow 则 allow |
| 6 | `pathInAllowedWorkingPath` | 在工作目录内 → allow |
| 7 | 内部 harness 路径（session-memory、plans） | allow |
| 8 | allow 规则 | allow |
| 12 | 兜底 | ask，`decisionReason.type = 'workingDir'` |

第 12 步的源码注释把话说死了：

```
// 12. Default to asking for permission
// At this point, isInWorkingDir is false (from step #6), so path is outside working directories
  decisionReason: { type: 'workingDir', reason: 'Path is outside allowed working directories' }
```

即：CC 的「默认」= `in_working_dir ? allow : ask`。
写路径（`checkWritePermissionForTool`）的兜底同样是第 5 步 `Default to asking`，
且没有第 6 步那个目录放行——所以默认模式下写文件一律要确认，与用户描述一致。

⚠️ 修正我先前的说法：我在对话里说「CC 是两层、pai 是一层」。
方向对，但结构上不准确——目录边界不是独立的一层，它是同一条求值链里的第 6 步与第 12 步。
准确说法是：CC 的链更长，且末端是目录判定而非常量。

## 二、工作目录集合怎么来的

```ts
export function allWorkingDirectories(context): Set<string> {
  return new Set([getOriginalCwd(), ...context.additionalWorkingDirectories.keys()])
}
```

- 起点是 `getOriginalCwd()`——启动时的 cwd，不是当前 cwd（防中途 `cd` 出去把边界带跑）。
- 扩展靠 `additionalDirectories` 设置项 + 运行期 `PermissionUpdate` 增删。
- `pathInAllowedWorkingPath` 用 `.every(...)`：所有待查路径都必须在允许目录内，
  任一个在外就算越界。

## 三、符号链接：CC 一次算两条路径，全链共用

```ts
// Get paths to check (includes both original and resolved symlinks).
// Computed once here and threaded through checkWritePermissionForTool →
// checkPathSafetyForAutoEdit → pathInAllowedWorkingPath to avoid redundant
// existsSync/lstatSync/realpathSync syscalls (previously 6× = 30 syscalls per check).
const pathsToCheck = getPathsForPermissionCheck(path)
```

deny/ask 规则对两条路径分别查，`pathInAllowedWorkingPath` 要求两条都在界内。
工作目录本身也用同一个函数解析（`getResolvedWorkingDirPaths`），注释写明理由：
不这么做的话 macOS 上 `/System/Volumes/Data/...` 的解析结果匹配不上未解析的工作目录，
会造成误拒。

→ 这正是 pai TODO 里那条「符号链接双路径检查未做」的现成答案，
连性能陷阱（每次检查 30 次 syscall）和对称解析的坑都标好了。

## 四、pi：明确不做，并且把话说在文档里

pi 的态度与 CC 相反，且是自觉的（`packages/coding-agent/docs/security.md:31-37`）：

- pi 不带沙箱，内置工具以 pi 进程权限读写文件、跑 shell；
- 原话：「部分进程内沙箱容易被误解为安全边界」——半吊子的进程内权限
  制造虚假安全感，不如不做；
- 唯一内置守卫是 project trust：只管「要不要加载项目本地的 settings/extensions/skills」，
  防的是「clone 一个仓库，它的 `.pi/extensions` 静默改掉你的 agent」——
  这是输入加载防护，不是运行时权限；
- prompt injection 被明文划为边界外风险，隔离交给 OS/容器/微VM。

机制侧 pi 只给一个 `beforeToolCall` 挂点，策略全是用户态扩展，
官方示例三个：`permission-gate`、`confirm-destructive`、`protected-paths`。

外部参照 4 的总结（原话）：

CC 是 policy shipped in product，pi 是 mechanism shipped in library；
前者优化「默认安全」，后者优化「可组合、可审计（策略代码就在你自己的仓库里）」。
mini-pi 学的是 pi 的机制 + CC 的策略内容。

## 五、钩子失败语义：两个独立实现选了同一个默认，pai 选了反的

这条是本篇最该让 pai 回头看的：

- pi：`emitToolCall` 不捕获异常，上层转为拦截（`runner.ts:862`、`agent-session.ts:432`）；
  外部参照 4 把「钩子异常被吞、默认放行」列为踩坑清单第 1 条。
- CC：分类器解析失败就 block。
- 外部参照 4 的原话：「工具层永远 fail-closed——CC 分类器解析失败就 block，
  pi 的 tool_call 钩子抛异常就 block，两个独立实现选了同一个默认值。」

pai 的 D#50 选的是 fail-open（hook 崩溃/超时不阻断），
理由写的是「`design_gate.py` 已有先例」——但 `design_gate.py` 是开发期自律门禁
（挡的是 AI 改自己源码），不是运行期安全门禁（挡的是 agent 动用户的机器）。
拿前者的失败语义去定后者，是一次场景错配。
D#50 该复议（已登记 TODO）。

## 六、CC 还有而 pai 完全没有的

- `DANGEROUS_FILES` / `DANGEROUS_DIRECTORIES`：`.bashrc`、`.git/hooks` 这类持久化位点
  写不进去，且 bypass 模式免疫（再怎么放行也拦）。
- `denialTracking`：3 连拒 / 20 总拒回落人工——防自动化决策失控。
- `decisionReason` 结构化审计：哪条规则、哪个来源、哪个模式、分类器什么理由。
  pai 的 `Decision.reason` 是一句人话字符串，机器读不了。
- SSRF 守卫（DNS 解析层钉死 IP 防 rebinding）、路径 TOCTOU 拒绝（`$ % ~user`）。

## 六点五、权限模式：不是开关，是求值链上的插入点

（2026-08-11 追加，由用户问「auto 模式下就不会弹 ask，这个怎么弄呢」引出）

CC 的模式清单（`src/types/permissions.ts:16`）：

```
EXTERNAL（用户可选）: acceptEdits | bypassPermissions | default | dontAsk | plan
INTERNAL（额外）    : auto | bubble
```

关键结论一：模式不是「全局开关」，是插在求值链特定位置的放行条件，且都有免疫项。

`acceptEdits` 的生效点（`filesystem.ts:1366`）：

```ts
// 3. If in acceptEdits or sandboxBashMode mode, allow all writes in original cwd
if (toolPermissionContext.mode === 'acceptEdits' && isInWorkingDir) { ... allow }
```

注意 `&& isInWorkingDir`——acceptEdits 仍然受工作目录边界约束，它只免掉「写一律 ask」那条，不免边界。

关键结论二：`bypassPermissions` 也不是无条件放行。 它在 `permissions.ts:2a` 才生效，
而 1a–1g 全部先跑，其中三条bypass 免疫：

- `1d` deny 规则；
- `1f` 用户显式配的内容相关 ask 规则（如 `Bash(npm publish:*)`）——
  CC 注释：「must be respected even in bypass mode, just as deny rules are respected at step 1d」；
- `1g` 安全检查（`.git/`、`.claude/`、`.vscode/`、shell 配置）——
  「bypass-immune — they must prompt even in bypassPermissions mode」。

即：再怎么 bypass，用户自己写下的 ask 规则和持久化位点仍然要问。

关键结论三：`auto` 是唯一需要模型的模式，pai 做不了。
它挂在 `TRANSCRIPT_CLASSIFIER` feature flag 上，要 `isAutoModeGateEnabled()`
+ 启动期 `verifyAutoModeGateAccess` + 熔断器（`getNextPermissionMode.ts` 的注释说
两者会 diverge，live check 是为了防 shift+tab 处理器静默崩掉）。
用户想要的「不弹 ask」效果，由 acceptEdits / bypassPermissions / dontAsk 覆盖，
这三个都不需要模型。

关键结论四（对 pai 最有用的一条）：pai 已经无意中实现了 `dontAsk`。
D#48「ask 在 once 模式无真人时降级为 deny」——这正是 CC `dontAsk`
（未预批准即拒，不问）的语义，只是当时没起这个名字，也没意识到它是一个模式
而不是一个特例。把它显式化，once 的默认模式就是 `dontAsk`，整件事自洽了。

## 七、给 pai 的结论

pai 现在的位置很尴尬：学了 pi 的机制（`before_tool_call`）+ CC 的引擎形状
（三态、求值顺序、匹配下放），但既没搬 CC 的策略内容，也没写 pi 那句免责声明。
两家的安全性都来自它们各自完整的一半，而 pai 取了两个"上半身"。

要走出这个状态只有两条路，且必须选一条（features/09 的拍板点）：

1. 补 CC 的策略：目录边界（默认 `in_working_dir ? allow : ask`）+ 危险路径清单
   + 符号链接双路径；
2. 抄 pi 的诚实：明确宣告"pai 不提供运行期安全边界，请上容器"，
   写进 README 与首启提示，`default_decision` 保持 allow。

最糟的是维持现状——STATUS 写着「permissions 可用」而实际全放行，
恰好就是 pi 那句「进程内权限容易被误解为安全边界」警告的东西。
