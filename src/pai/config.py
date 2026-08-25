"""env 加载与 LLM client 工厂。走 OpenAI 兼容协议，默认指向 DeepSeek。"""

import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

# 用户级配置目录，与 core.memory.USER_DIR 是同一个位置（~/.pai）——
# 那里已经住着 PAI.md 与 projects/<key>/memory/，阶段 4 还会加 settings.json。
# 两处常量必须一致，tests/test_config.py 有一条测试专门防漂。
USER_DIR = ".pai"


def _load_env() -> None:
    """项目 .env → 用户 ~/.pai/.env，两级都读。

    优先级：真实环境变量 > 项目 .env > 用户 .env（`load_dotenv` 默认 override=False，
    所以先加载的赢，顺序即优先级）。与 PAI.md 的分层同一个方向：越靠近项目越优先。

    `usecwd=True` 不能省（2026-08-10 实测）：`find_dotenv` 默认从**调用方所在文件**的
    目录向上找，也就是 `src/pai/`——于是「项目级 .env」实际解析成了 **pai 仓库自己那份**，
    在别的项目里跑读到的是错的那个，装成 wheel 之后更是直接找不到。
    它现在能工作纯粹是 editable 安装让 config.py 恰好躺在仓库里，是个巧合不是设计。

    用户级兜底则是 pai 立意的必需品：它就是要**在别的项目里跑**，
    而那些目录没有 .env（`~/.pai/.env` 与 `~/.pai/PAI.md` 同一个家，语义一致）。
    """
    load_dotenv(find_dotenv(usecwd=True))           # 项目级：从**当前目录**向上找
    load_dotenv(Path.home() / USER_DIR / ".env")    # 兜底：用户级


def make_client() -> OpenAI:
    _load_env()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key or api_key.startswith("sk-在这里"):
        sys.exit(
            "没找到有效的 DEEPSEEK_API_KEY。放在以下任一处：\n"
            "  1) 环境变量：export DEEPSEEK_API_KEY=sk-...\n"
            f"  2) 用户级（在任何目录都生效）：~/{USER_DIR}/.env\n"
            "  3) 项目级：当前项目或其上级目录的 .env"
        )
    return OpenAI(api_key=api_key, base_url=os.environ.get("PAI_BASE_URL", DEFAULT_BASE_URL))


def model_name() -> str:
    # 幂等。不放这里的话，.env 里的 PAI_MODEL 生效与否取决于
    # 「client 是否恰好先被构造」这种求值顺序巧合（R3#7）
    _load_env()
    return os.environ.get("PAI_MODEL", DEFAULT_MODEL)


def recall_model() -> str:
    """记忆召回的侧查询模型（feature 10）。

    CC 用的是便宜档（`getDefaultSonnetModel()`），pai 只有一个模型档——这个 env 就是那个口子。
    不设就回落主模型：召回是每轮一次的小请求，宁可默认可用，也不要因为没配就静默不生效。
    """
    _load_env()
    return os.environ.get("PAI_RECALL_MODEL") or model_name()


def context_window() -> int:
    """上下文窗口大小。非法值不裸抛 ValueError——`invalid literal for int()`
    说不出是哪个 env 配错了（02 终审 Minor#7，对齐 make_client 的报错先例）。

    非正数同样挡在门口：语法合法但会让阈值公式 `window - reserve` 算出负预算，
    于是每轮都判「该压缩」，比当场崩溃难查得多。
    """
    _load_env()
    raw = os.environ.get("PAI_CONTEXT_WINDOW")
    if raw is None or raw == "":
        return 1_000_000
    try:
        value = int(raw)
    except ValueError:
        sys.exit(f"PAI_CONTEXT_WINDOW 不是整数：{raw!r}。"
                 "它是上下文窗口的 token 数，例如 PAI_CONTEXT_WINDOW=1000000")
    if value <= 0:
        sys.exit(f"PAI_CONTEXT_WINDOW 必须是正整数：{raw!r}。"
                 "非正数会让压缩阈值算出负预算，于是每轮都触发压缩")
    return value
