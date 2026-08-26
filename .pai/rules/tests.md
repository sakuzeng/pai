---
paths: tests/**
---

# 写这个仓库的测试时才需要记住的

（这份规则是 feature 36 的第一个真实用户，只在碰 `tests/**` 时才进上下文。
常驻规约在 AGENTS.md，不要把内容往这里搬——那边是 Claude Code 的唯一入口。）

- 测试跑的是 `./test.sh`（venv `~/.virtualenvs/pai`），不要直接 `pytest`：
  系统 python3 没装 pytest，会得到一个与代码无关的 `No module named pytest`。
  快循环 `./test.sh --fast` 跳过 pty e2e。
- 新测试写完先问一句：被断言的那一行，在这条测试里真的会被执行吗？
  答不上来就把实现改坏一次，确认它会红（本仓库的假测试出过好几批：
  R4#T1/T2/T3，以及 feature 37 自己又造了一个）。
- 任何会落盘的测试都用 `tmp_path`；需要 cwd 的用 `monkeypatch.chdir(tmp_path)`。
  仓库根有 `AGENTS.md`，不 chdir 的话它会被当成项目指令捡进上下文（feature 35
  当场炸出过两条这样的测试）。
- 断言中文宽度/屏幕内容时，别比 emoji 的字节形状：源码里是 `🗜️`（带变体选择符），
  屏幕模型里是 `🗜`（feature 38 撞到）。
- 假 provider（`tests/fake_provider.py`）是别人的测量仪器：改它之前先想清楚
  「它与真 provider 的偏离会不会让某条被测路径结构上走不到」——
  固定 usage 就这么把压缩链路堵了十几天（feature 38）。
