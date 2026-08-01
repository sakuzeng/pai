"""命令行入口：pai "任务描述" """

import argparse

from pai.config import make_client, model_name
from pai.loop import run_agent
from pai.session import SessionLog
from pai.tools import get_tools


def main() -> None:
    parser = argparse.ArgumentParser(prog="pai", description="最小编码 agent")
    parser.add_argument("task", help="用自然语言描述任务")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--no-session", action="store_true", help="不落盘会话 JSONL")
    args = parser.parse_args()

    answer = run_agent(
        args.task,
        client=make_client(),
        model=model_name(),
        tools=get_tools(),
        max_steps=args.max_steps,
        session=None if args.no_session else SessionLog(),
    )
    print(f"\n🤖 {answer}")


if __name__ == "__main__":
    main()
