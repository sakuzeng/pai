# 52-word-wrap 开发日志

## 立档与拍板（2026-09-13）

用户问「接下来做什么呢」→ 我给三个方向，用户选「把真跑撞到的摩擦收掉」→ 立档案列了六条、四问待拍板
→ 用户「做一个最关键的功能」，于是收窄成一条：英文折行劈单词。挑选理由写在 README（每屏可见、
伤的是读回答这个每轮动作、45 九条里唯一标「比一般遗留严重」、已推迟三轮）。

## TDD（2026-09-13）

红（新测试按宽度 24..80 区间跑）：

```
35 failed, 125 passed in 0.65s
E  AssertionError: 宽度 42：`rules` 被折行劈开了
```

第一版实现（词回退）跑完还剩 3 条红，而且是我没预料到的宽度。加调试打印跑了一遍断点：

```
break at '.' used=42 tail='截断；规则在 rules' word_branch=False nolinestart=True
```

**断点根本不在 `s` 上，而在 `.` 上**——`.` 在 44 加的 `NO_LINE_START`（ASCII 标点避头表）里，
于是走避头分支「把上一个字挤下来陪它」，被挤下来的正是 `s`，劈开的是 `rules`。
44 复盘写过「用一条排版规则去补我自己的折行算法造成的问题」，这就是那条规则的反噬，
而我第一版只在「断点自己是词字符」时补词，正好漏掉它。

改法：换行时统一算「本行留几个字」，两条规则依次作用——先避头（keep -= 1），
再看被挤下去的第一个字符是不是词字符，是就把整个词带上。顺序不能反。

绿：

```
tests/test_markdown_wordwrap.py + tests/test_tui_markdown.py: 188 passed in 0.80s
全量（STATUS 更新前）: 1 failed, 1898 passed, 8 deselected in 195.82s（红的是测试数校验）
```

注入反证：拿掉补词那个条件 → `34 failed, 126 passed`，恢复后 `160 passed`。

改动：`src/pai/tui/markdown.py` 的 `_wrap_spans` 换行分支重写 + 新增 `_is_word_char`；
顺带剥掉折行留下的行尾空格（选区复制会把它带出来）。`_hard_wrap`（代码块）刻意不动——
注释里写着「代码里没有词，找边界只会折在更怪的地方」。

对账一条：45-C4「模型不知道自己 cwd」早在 feature 46 就做了（`_project_overview` 注入
「当前工作目录：<root>」，注释里写着 45-C4），TODO 漏勾，本次核销。

效果（同一段文本，宽度 42）：

```
用 read_file 读 src/pai/tui/markdown.py，
注意 MAX_OUTPUT_CHARS 的截断；规则在
rules.py 里，状态见 docs/dev/STATUS.md。
```
