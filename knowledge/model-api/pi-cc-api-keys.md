# pi / CC 的 API key 解析走读

对照两家源码，回答一个问题：一个 coding agent 该怎么找到它的 API key。

- 来源：pi-mono（[外部参照 5](../README.md#外部参照本机路径对外部读者是死链笔记正文以外部参照-n引用)）
  `packages/ai/src/env-api-keys.ts`、`packages/ai/src/compat.ts`、`packages/agent/src/agent.ts`；
  CC 反编译源码（外部参照 6）`src/utils/auth.ts`
- 精读日期：2026-08-10
- pai 锚点：`src/pai/config.py`、roadmap 阶段 4（用户级配置归在那里）

起因：2026-08-10 修 `~/.pai/.env` 兜底时，用户问「pi 和 CC 怎么做的，能借鉴吗」。
（本篇初版误放在 `concepts/`——那里是「不专属某家源码」的横切概念，
而这是实打实的两家源码走读，用户指出后迁至此，并顺带补齐了对照类走读的命名规约。）

## 一、pi：一张映射表 + 一个注入钩子，core 不碰环境

`env-api-keys.ts` 是一张 provider → 环境变量名 的表，不是散落的 `process.env.XXX`：

```ts
deepseek: "DEEPSEEK_API_KEY",  openai: "OPENAI_API_KEY",  groq: "GROQ_API_KEY", …
// anthropic 特殊：三个候选按序试
[ANTHROPIC_AUTH_TOKEN_ENV, ANTHROPIC_OAUTH_TOKEN_ENV, ANTHROPIC_API_KEY_ENV]
```

对外是 `findEnvKeys(provider) -> string[] | undefined`（候选变量名列表）与
`getEnvApiKey(provider, env) -> string | undefined`（取值）。

三个细节值得抄：

1. `env` 是参数不是全局：签名收 `ProviderEnv`，不直接读 `process.env`——所以可注入、可测。
2. 显式 > 环境（`compat.ts`）：调用方显式传了 `apiKey` 就用它，否则才回落环境变量。
   判据是 `hasExplicitApiKey()`（非空字符串），不是 `!= null`——空串不算数。
3. `AMBIENT_AUTH_MARKER`：有些 provider 的凭证不是 key，而是「环境里存在某个文件」
   （如 Vertex 的 ADC 凭证文件）。pi 用一个哨兵值表达「这里有认证但不是 key」，
   而不是硬塞个假 key。

Agent 层是依赖注入（`agent.ts:102`）：

```ts
getApiKey?: (provider: string) => Promise<string | undefined> | string | undefined;
```

即 agent core 根本不知道 key 从哪来，由应用层提供。pi 没有「把 key 写进自己的
配置文件」这条路——只有环境变量与注入回调。

## 二、CC：key 带「来源」，外加一条可执行的 `apiKeyHelper`

核心函数是 `getAnthropicApiKeyWithSource()`（`auth.ts:225`），返回 `{key, source}`。
`source` 的取值枚举出了全部合法来源：

`ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `CLAUDE_CODE_OAUTH_TOKEN` /
`CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR` / `CCR_OAUTH_TOKEN_FILE` /
`apiKeyHelper` / `claude.ai` / `/login managed key` / `none`

来源不只是调试信息，它参与决策：`statusNoticeDefinitions.tsx` 用
`authTokenInfo.source === 'ANTHROPIC_AUTH_TOKEN' || === 'apiKeyHelper'` 来判断该给用户
看哪条状态提示。

`apiKeyHelper`：settings 里配一条命令，CC 执行它拿 key。配套机制不小：

- TTL 缓存（`calculateApiKeyHelperTTL()`）；
- stale-while-revalidate：过期了先返回旧值、后台刷新，不阻塞请求；
- 并发去重：`_apiKeyHelperInflight` 一个 promise，冷缓存时并发调用共享它。

用途是密钥轮转与企业网关——key 不是静态字符串而是「一条能生成 key 的命令」。

`--bare` 模式是另一条值得记的设计：hermetic auth，只认 `ANTHROPIC_API_KEY` 或
`--settings` 里的 `apiKeyHelper`，绝不碰 keychain、配置文件、审批列表。
即「可复现的最小认证路径」被做成了显式模式。

配置文件分两处：`~/.claude/settings.json`（设置）与 `~/.claude.json`（全局配置）。
`auth.ts:1952` 有一句注释直白得值得抄进 pai：

`~/.claude.json` 是 user-writable 的，不可信。

## 三、给 pai 的结论

### 直接借鉴（成本低、收益明确）

1. provider → env 变量名映射表（学 pi）。pai 现在把 `DEEPSEEK_API_KEY` 硬编码在
   `config.py` 里，换 provider 就得改代码。一张表 + `find_env_keys(provider)` 即可，
   与「schema 与代码同源」是同一种品味：配置数据不写死在逻辑里。
2. key 带来源（学 CC）。`resolve_api_key() -> (key, source)`，`source` ∈
   `环境变量 / 项目 .env / 用户 .env`。REPL 的 `/status` 能显示「这次用的是哪来的 key」——
   排查「为什么用了错的那把 key」时，这是唯一有用的信息，而实现成本几乎为零。
   （2026-08-10 那次误诊断就是栽在「不知道 .env 到底从哪儿加载的」。）
3. key 解析可注入（学 pi 的 `getApiKey` 钩子）。`make_client()` 现在直接读 env；
   改成收一个可选的 `get_api_key` 回调，与 pai 既有的依赖注入约束一致。

### 值得做但排后面

4. `apiKeyHelper`（key 来自一条命令）：真正的价值在密钥轮转/企业网关，pai 现在没有
   这个场景；而且它会带出 TTL 缓存 + stale-while-revalidate + 并发去重一整套复杂度。
   等真有轮转需求再做，登记 TODO。

### 明确不借鉴

5. CC 的 keychain / OAuth / `/login`、多 provider 凭证（Bedrock/Vertex/Foundry）——
   产品面与企业面功能。
6. CC 的「settings.json 与 `.claude.json` 两个配置文件」——pai 只要一个
   `~/.pai/settings.json`（阶段 4 引入），不重蹈分裂。

### 一条直接影响阶段 4 设计的结论

key 留在 `.env`，不要放进 `~/.pai/settings.json`。

理由是两家的共同点：pi 压根不把 key 存进自己的配置文件；CC 存了但在源码注释里明说
那个文件不可信。而 pai 阶段 4 要引入的 `~/.pai/settings.json` 是放权限规则的——
那种文件天然会被分享、被贴进 issue、被提交进仓库（项目级那份更是直接进版本控制）。
把密钥和「想被人看见的配置」放同一个文件，早晚会有人 `cat` 出来给别人看。

所以 pai 的分工定死：`.env` 管密钥（本机、gitignore），`settings.json` 管配置（可分享）。
