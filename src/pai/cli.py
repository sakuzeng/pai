"""命令行入口：只管参数解析与分发到 modes/，不含业务逻辑。

学 pi 的 cli.ts —— 交互形态各自住在 modes/ 下，cli 只挑一个进去。
带 task 走 once（跑完即退），不带 task 进 REPL——这就是 pi 的 print-mode 与
interactive 的分岔点。
"""

import argparse

from pai.core.tools import shell
from pai.core.permissions import BYPASS, MODES
from pai.modes.interactive import run_interactive
from pai.modes.once import run_once


def main() -> None:
    parser = argparse.ArgumentParser(prog="pai", description="最小编码 agent")
    parser.add_argument("task", nargs="?", default=None,
                        help="用自然语言描述任务；不给就进交互模式（REPL）")
    parser.add_argument("--max-steps", type=int, default=20)
    # 默认给一道烧钱熔断。20 万 token 在 v4-flash 上最坏约 0.4 元（全部未命中缓存的输入价）；
    # 平台侧没有消费限额可用，这是唯一的自动防线。0 表示不限。
    parser.add_argument(
        "--max-tokens", type=int, default=200_000,
        help="本次任务的累计 token 预算，超过即停（默认 200000，0 = 不限）",
    )
    parser.add_argument("--no-session", action="store_true", help="不落盘会话 JSONL")
    parser.add_argument(
        "--permission-mode", choices=MODES, default=None,
        help=f"权限模式（默认读 settings.json 的 defaultMode）：{'/'.join(MODES)}",
    )
    # 名字里带 dangerously 是**故意的**（照 CC 同名 flag）：这是一条要让人打字时
    # 就犹豫一下的路。它等价于 --permission-mode=bypassPermissions。
    parser.add_argument(
        "--dangerously-skip-permissions", action="store_true",
        help="跳过权限确认（等价 --permission-mode=bypassPermissions）；deny 规则、"
             "显式 ask 规则与危险路径仍然生效",
    )
    args = parser.parse_args()
    if args.max_tokens < 0:
        parser.error("--max-tokens 不能为负（0 = 不限）")
    if args.dangerously_skip_permissions and args.permission_mode not in (None, BYPASS):
        parser.error(
            f"--dangerously-skip-permissions 与 --permission-mode={args.permission_mode} 冲突")
    mode = BYPASS if args.dangerously_skip_permissions else args.permission_mode

    try:
        if args.task is None:
            run_interactive(
                max_steps=args.max_steps,
                max_total_tokens=args.max_tokens or None,
                no_session=args.no_session,
                mode=mode,
            )
            return

        answer = run_once(
            args.task,
            max_steps=args.max_steps,
            max_total_tokens=args.max_tokens or None,
            no_session=args.no_session,
            mode=mode,
        )
        print(f"\n🤖 {answer}")
    finally:
        # 关掉 pai 就该停掉它起过的一切（官方语义：退出时后台任务自动清理）。
        # 放在 cli 出口而不是各 mode 里：两种模式共用一条出路，异常路径也覆盖到。
        shell.reap_spawned()


if __name__ == "__main__":
    main()
