# 53-four-frictions 开发日志

## 立档与拍板（2026-09-13）

feature 52 交付后用户说「做吧」= 把 45 清单剩下的四条做完。四处的候选与建议在 52 立项时已写过
一轮（52 收窄时删掉了三问），本档案重记并按建议执行。

## TDD（2026-09-13）

红：`13 failed, 2 passed`（新测试 15 条，两条是「反向守卫」类的先天绿）。

改动：

- 预算：`cli.py` 默认 500_000；`loop.py` 撞顶文案说三件事，`run_agent` 加 `interactive` 参数，
  `once.py` 传 False（没有下一轮，不许诺「再说一句就接着做」）。
- 计时：`Dock._paused_at` / `_waited` / `pause_clock` / `resume_clock` / `_elapsed()`，
  三处读数（活动区、状态行、轮末摘要）全走 `_elapsed()`；`AgentStart` 与 `_finish` 归零；
  `interactive._run_tui` 的 `ask_human` 用 try/finally 包住 `await_dialog_answer`
  （Esc 撤框与异常两条路也要恢复计时）。
- footer：`_ellipsize_path`（中间省略、保住最后一段）；`footer_lines` 先压路径再牺牲右边。
- 权限文案：`permissions.py` 四处 ask 的 `reason` 重写；`commands.py` 的 `/permissions` 同步。

跑完剩四条红，都是我自己的测试写错，不是实现错：

1. 预算两条：`max_total_tokens=1` 但预算检查在**发下一次请求之前**（D#22），第一步 `spent_tokens`
   还是 0。要跑到第二步才触发——脚本改成第一轮调工具并回一个超上限的 usage。
2. 接线断言红得对：我当时确实还没把 `pause_clock` 接进 `ask_human`，补上。
3. footer 的 `~` 断言：`conftest` 把 `$HOME` 隔离到 tmp，测试里写死的 `/Users/sakuzeng/...`
   不再是家目录，`_short_path` 不缩。改用 `os.path.expanduser`。

改文案连带红的既有测试 5 条，都是判据跟着文案走：

- `test_dangerous_write_reason_names_the_path`、`test_boundary` 两处、`test_skills` 两处
  断言的是「『持久化位点』这个词在不在」→ 改成断言说没说清三件事。
- `test_slash_permissions_tells_the_whole_truth` 断言「『边界』二字在不在」→ 改成断言
  说没说出后果（「任意路径」）。
- `test_boundary` 里还有一条 `assert "持久化位点" not in d_exec.reason`——文案改掉后它变成
  永远成立的空断言，换成新文案的特征词。

绿：

```
tests/test_four_frictions.py: 15 passed in 0.57s
全量（STATUS 更新前）: 1 failed, 1913 passed, 8 deselected in 201.04s（红的是测试数校验）
```

注入反证（都红、都恢复）：

```
拿掉 pause_clock 的实现：  1 failed, 2 passed
拿掉 footer 压路径那一支：  2 failed, 1 passed
```

效果：

```
宽 60： ~/…/pai · default             deepseek-v4-flash · 12.0%/1.0M
bash： pai 看不出 `bash` 这次会碰哪些文件，所以每次都问；允许之后它能读写任意路径。
       要免问：在 .pai/settings.json 的 permissions.allow 里加一条（如 `Bash(git status *)`）
界外读：`/elsewhere/x.py` 不在工作目录 `/work` 里，允许之后 pai 才读得到。
       要长期放行：settings.json 的 permissions.additionalDirectories 加上它所在的目录
写文件：写 `/work/x.py` 会改掉磁盘上的内容，所以默认每次都问。
       要少问：shift+tab 切到 acceptEdits，工作目录内的写就不再问
```
