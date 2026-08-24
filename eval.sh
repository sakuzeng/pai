#!/usr/bin/env bash
# 评测入口（feature 32，对位 test.sh）。评测不进 ./test.sh 的收集范围
# （pyproject testpaths=["tests"] 不动），只从这里跑。
# 默认**不打真实 API**——花钱的副作用不能是默认行为（D#23，与 test.sh 同款）。
#
#   ./eval.sh              无密钥评测（回放评测；确定性、零费用）
#   ./eval.sh --llm        追加真模型评测（会产生费用，需 DEEPSEEK_API_KEY）
#   ./eval.sh -k xxx       其余参数原样透传给 pytest
#
# 工件：每次运行在 evals/.eval/<UTC时间戳>/ 落 runs.jsonl（逐 case 一行）
# 与被评测进程的会话 JSONL 快照（gitignore，含 prompt 与工具输出）。
set -euo pipefail

if [[ "${1:-}" == "--llm" ]]; then
    shift
    echo "⚠️  将打真实 API，会产生费用"
    PAI_RUN_LLM_TESTS=1 exec python3 -m pytest evals "$@"
fi

exec python3 -m pytest evals -m "not llm" "$@"
