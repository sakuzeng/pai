"""评测子进程：复用公开 once 装配，不另造 agent loop。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys
from typing import Optional

from openai import OpenAI, OpenAIError

from pai.core.permissions import ACCEPT_EDITS, RuleSet
from pai.core.protocols import ChatClient
from pai.core.tools.shell import reap_spawned
from pai.core.trace import EventTrace
from pai.modes.once import run_once


def run_worker(config: dict, *, client: Optional[ChatClient] = None) -> int:
    status: dict = {"execution": "completed"}
    code = 0
    try:
        if client is None:
            # 测试工具会继承环境，key 在构造 client 后立即从环境移除。
            key = os.environ.pop("DEEPSEEK_API_KEY")
            client = OpenAI(api_key=key, base_url=os.environ["PAI_BASE_URL"],
                            max_retries=0, timeout=config.get("seconds", 180))
        answer = run_once(config["prompt"], client=client, model=config["model"],
                          max_steps=config["max_steps"], max_total_tokens=config["max_tokens"],
                          mode=ACCEPT_EDITS, rules=RuleSet(),
                          on_event=EventTrace(Path(config["trace"])))
        print(answer)
    except OpenAIError as exc:
        status = {"execution": "provider_error", "errorType": type(exc).__name__,
                  "statusCode": getattr(exc, "status_code", None)}
        code = 1
    except SystemExit as exc:
        status = {"execution": "timeout" if exc.code == 124 else "interrupted",
                  "errorType": type(exc).__name__}
        code = 1
    except Exception as exc:
        status = {"execution": "protocol_error" if isinstance(exc, ValueError) else "harness_error",
                  "errorType": type(exc).__name__}
        code = 1
    finally:
        reap_spawned()
        Path(config["result"]).write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    return code


def main() -> None:
    def stop(_signum: int, _frame: object) -> None:
        reap_spawned()
        raise SystemExit(124)
    signal.signal(signal.SIGTERM, stop)
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    raise SystemExit(run_worker(config))


if __name__ == "__main__":
    main()
