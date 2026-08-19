# 08-20260810-storage-layout · spec

2026-08-10 定稿（两问拍板见 [README](README.md)）。

## 背景与问题

pai 的用户级数据现在散在三处，且有一处会污染用户的项目：

```
./sessions/20260810-212123.jsonl          ← 当前工作目录！在别人项目里跑就是拉一坨
~/.pai/projects/2b0a92ef14633a56/memory/  ← 哈希目录名，不可读
~/.pai/history/e4887ef95b86e3ee           ← 同样是哈希
```

## 目标（做什么）

### 1. 新建 `core/paths.py` —— pai 用户级路径的唯一事实源

现在「`~/.pai` 在哪、项目目录怎么算」这套逻辑散在 `memory.py`（`memory_dir`、`_git_root`）、
`config.py`（`USER_DIR` 常量）、`interactive.py`（`history_path_for`）三处，各写各的。
抽成一个模块：

```python
USER_DIR = ".pai"

def user_dir(home=None) -> Path                 # ~/.pai
def project_slug(cwd=None) -> str               # -Users-sakuzeng-improve-...
def project_dir(cwd=None, home=None) -> Path    # ~/.pai/projects/<slug>
def memory_dir(...) -> Path                     # <project_dir>/memory
def sessions_dir(...) -> Path                   # <project_dir>/sessions
```

为什么不放进 `memory.py`：`session.py` 也要用，而 session 不该依赖 memory
（层次上它更底层）；放 `config.py` 则会让 `config` 从「env 与 client 工厂」变成杂物间。

### 2. `project_slug`：完全照 CC

- 取git 仓库根（保持官方语义：同仓库的子目录与 worktree 共享一份数据），
  不在 git 仓库里就取当前目录本身；
- 绝对路径 → 把路径分隔符换成 `-`：`/Users/sakuzeng/improve/.../pai`
  → `-Users-sakuzeng-improve-coding-agent-projects-pai`；
- 中文路径原样保留（文件系统支持，转义反而不可读）。

已知碰撞（如实记，不假装没有）：`/a-b/c` 与 `/a/b-c` 都会变成 `-a-b-c`。
CC 也有同样的问题（它就是这么拼的）。真实概率极低，登记 TODO 而不是提前设计转义——
一旦转义，目录名就不再和 CC 长得一样，反而丢掉本次需求的核心诉求（可读、一致）。

### 3. `SessionLog` 默认落 `<project_dir>/sessions/`

- 默认参数从 `"sessions"`（相对当前目录）改为 `sessions_dir()`；
- 保留 `directory=` 参数：测试要用，将来做 `--session-dir` 也从这儿接；
- 文件名改为 `%Y%m%d-%H%M%S-<短 id>.jsonl`，顺带关掉 R#15（同秒建两个 SessionLog
  会写同一文件）。与 CC 不同的取舍：CC 直接用 `<sessionId>.jsonl`，可读性让位于唯一性；
  pai 保留时间戳前缀，于是 `ls` 仍按时间排序——集中存放之后一个目录里会有几十个会话，
  能按时间排比 uuid 好认。记 decisions。

### 3.5 顺带加两个字段（`sessionId` + `cwd`）——只此两个

用户提议「session 的 json 字段借鉴 CC」，实地对照后只把这两个并进本轮
（完整对照与分档见[需求池](../../需求池.md)）：

- `sessionId`：整个会话一个 uuid，每条记录都带。它同时是文件名里那个短 id 的来源。
- `cwd`：08 之后不加就是净信息丢失——会话集中存到 `~/.pai/projects/<slug>/` 后，
  同一仓库的不同子目录写进同一个目录，不记 cwd 就再也分不出「这次是在哪跑的」。

其余字段（`uuid`/`parentUuid` 父子链、ISO 时间戳、统一顶层判别字段）不在本轮：
那是「换格式」，影响阶段 7 的回放与旧文件兼容，会把本轮「搬家」的验收搞模糊。待立独立档案。

### 4. `memory_dir` 改用新 slug；`history` 暂不动

- `memory.memory_dir` 转调 `paths.memory_dir`，对外 API 不变（`build_context` 等不用改）；
- 输入历史仍用哈希文件名（`~/.pai/history/<hash>`）——它是扁平的一堆文件，
  换成长 slug 会让 `ls ~/.pai/history` 更难看，而它本来就不需要人去认。
  这条与「目录要可读」不矛盾：可读性的价值在目录树里，不在一堆同级文件名里。
  如实登记 TODO，若日后觉得别扭再统一。

### 5. 装配层与可见性

- `once` / `interactive` 不再传相对目录，走 `paths`；
- REPL 的 `/memory` 已显示记忆目录，顺带显示会话目录——用户得知道东西写哪去了
  （这次问题的起点正是「我不知道这些文件是什么」）。

## 非目标（明确不做）

- 任何迁移代码（用户已裁决：老数据直接删）。旧的 `~/.pai/projects/<hash>/` 与
  散落的 `./sessions/` 由用户自行删除。
- slug 碰撞的转义方案（见上，登记 TODO）。
- `--session-dir` 参数（问 2 的候选 C 已被否）。
- 输入历史改名（见 4）。
- 会话的检索/回放/`--resume`（阶段 7 evals 或单独立项）。
- 会话记录的完整字段改造（`uuid`/`parentUuid`、ISO 时间戳、统一判别字段）——见 3.5，待独立立项。

## 验收标准

- `project_slug` 的四条各有测试：git 根归并、非 git 回退、中文路径、碰撞如实暴露
  （断言 `/a-b/c` 与 `/a/b-c` 确实撞在一起——把已知缺陷钉成测试，而不是留在嘴上）。
- 跑一次 pai 之后，当前工作目录里不再出现 `sessions/`（e2e 断言）。
- memory 与 sessions 落在同一个 `<project_dir>` 下。
- 同一 git 仓库的两个子目录 → 同一个 `project_dir`，且两次会话的记录里 `cwd` 不同
  （证明信息没丢）。
- 同一秒建两个 `SessionLog` → 两个不同文件（关掉 R#15），且各自 `sessionId` 不同。
- `/memory` 同时显示记忆目录与会话目录。
- `./test.sh` 全绿全离线；`tests/conftest.py` 的 `$HOME` 隔离保证不碰真实家目录。
- 每步红→绿真实数字进本目录 devlog.md；遗留逐条进 TODO；交付前写复盘（规矩 8）。
