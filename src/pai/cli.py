"""命令行入口：只管参数解析与分发到 modes/，不含业务逻辑。

学 pi 的 cli.ts —— 交互形态各自住在 modes/ 下，cli 只挑一个进去。
将来加 REPL 就是这里多一个分支 + modes/interactive.py，core 不动。
"""

import argparse

from pai.modes.once import run_once


def main() -> None:
    parser = argparse.ArgumentParser(prog="pai", description="最小编码 agent")
    parser.add_argument("task", help="用自然语言描述任务")
    parser.add_argument("--max-steps", type=int, default=20)
    # 默认给一道烧钱熔断。20 万 token 在 v4-flash 上最坏约 0.4 元（全部未命中缓存的输入价）；
    # 平台侧没有消费限额可用，这是唯一的自动防线。0 表示不限。
    parser.add_argument(
        "--max-tokens", type=int, default=200_000,
        help="本次任务的累计 token 预算，超过即停（默认 200000，0 = 不限）",
    )
    parser.add_argument("--no-session", action="store_true", help="不落盘会话 JSONL")
    args = parser.parse_args()

    answer = run_once(
        args.task,
        max_steps=args.max_steps,
        max_total_tokens=args.max_tokens or None,
        no_session=args.no_session,
    )
    print(f"\n🤖 {answer}")


if __name__ == "__main__":
    main()
