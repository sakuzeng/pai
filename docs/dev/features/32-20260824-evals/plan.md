# feature 32 · plan（六个 task，TDD）

顺序有依赖：T2 铸造的夹具是 T3 派生器 TDD 的输入，先铸后派。

- T1 公共件：`eval.sh`（双开关，文案对齐 test.sh）+ `evals/conftest.py`
  工件 fixture（session 级时间戳目录 + 每条 eval 追加 runs.jsonl 一行）+
  `.eval/` 进 .gitignore + evals/README.md 重写（旧「阶段 6 任务」计划收编
  进真模型纵切）。工件记录形状由 tests/ 下单测钉（离线，红→绿）。
- T2 夹具铸造：pai_playground 真跑一个可程序判定的小任务（真 DeepSeek，
  费用分级别提示），产出 v1 会话 JSONL 复制进 `evals/fixtures/`，
  溯源记 `evals/fixtures/README.md`。无自动化测试（是数据不是代码），
  铸造命令与产物校验记 devlog。
- T3 派生器 `src/pai/evals/replay.py`：TDD——先写红测试
  `tests/test_evals_replay.py`（拿 T2 真轨迹当输入：assistant 序列 /
  tool_calls arguments / 中文逐项断言；v0、坏文件、含 compaction 三类
  拒绝），再实现 `derive_provider_script`。
- T4 回放 eval：`evals/test_replay.py`——FakeProvider 装载派生脚本、
  临时 git 项目 + 隔离 HOME、真 pai 子进程 once 跑录制会话的首条 user
  消息，外部世界断言。跑 `./eval.sh` 全绿数字进 devlog。
- T5 真模型冒烟 eval：`evals/test_llm_smoke.py`（双开关 + 外部世界判定）。
  有钥手工跑一次留数字；无钥确认 skip。
- T6 收尾：注入反证（派生器丢 tool_calls → T4 必红，输出进 devlog）、
  `./test.sh` 全绿对账 STATUS、TODO/roadmap/STATUS/features 总览同步、
  复盘.md 四问、合并。
