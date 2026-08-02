#!/usr/bin/env bash
# 统一测试入口（学 pi 的 test.sh）。
# 默认**不打真实 API**——花钱的副作用不能是默认行为（docs/dev/decisions.md 第 23 条）。
#
#   ./test.sh              离线测试（默认）
#   ./test.sh --llm        额外跑打真实 API 的冒烟测试（会产生费用，需 DEEPSEEK_API_KEY）
#   ./test.sh -k xxx       其余参数原样透传给 pytest
set -euo pipefail

if [[ "${1:-}" == "--llm" ]]; then
    shift
    echo "⚠️  将打真实 API，会产生费用"
    PAI_RUN_LLM_TESTS=1 exec python3 -m pytest "$@"
fi

exec python3 -m pytest -m "not llm" "$@"
