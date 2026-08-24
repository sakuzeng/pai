# fixtures —— 签入版本库的真实会话轨迹

规矩出处：AGENTS「测试」节——真跑产生的轨迹一旦被当作测试夹具，须复制进
版本库，否则夹具的溯源链断在不入库的 pai_playground/ 里。

## 20260824-greeting-file.jsonl

- 铸造：2026-08-24，feature 32 T2。真 DeepSeek（`deepseek-v4-flash`，
  OpenAI 兼容协议）在 `pai_playground/eval_fixture_mint/proj`（git init 的
  沙盒项目、隔离 HOME）真跑：
  `pai --dangerously-skip-permissions --max-steps 8 "在当前目录创建文件
  问候.txt，内容只有一行：你好，评测夹具。写完后用 read_file 读回确认内容，
  然后只回答：完成"`。
- 内容：会话格式 v1（id `60389d9b…`），3 轮 assistant——`write_file`
  （中文文件名 + 中文内容）→ `read_file` 确认 → 文本收尾「完成」。
  选这个任务是刻意的：产物可程序判定（外部世界断言）、带中文路径与内容
  （编的字符串测不出的坑）、覆盖写与读两类工具。
- 消费方：`tests/test_evals_replay.py`（派生器单测，真实轨迹输入规约）、
  `evals/test_replay.py`（回放评测）。
- 原始产物（含 events.jsonl 与 问候.txt）留在 pai_playground 的铸造目录，
  不入库；本文件是入库的那份复制，两边内容 2026-08-24 起即不再保证同步
  ——以入库这份为准。
