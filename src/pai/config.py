"""env 加载与 LLM client 工厂。走 OpenAI 兼容协议，默认指向 DeepSeek。"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


def make_client() -> OpenAI:
    load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key or api_key.startswith("sk-在这里"):
        sys.exit("没找到有效的 DEEPSEEK_API_KEY，请检查 .env")
    return OpenAI(api_key=api_key, base_url=os.environ.get("PAI_BASE_URL", DEFAULT_BASE_URL))


def model_name() -> str:
    # 幂等。不放这里的话，.env 里的 PAI_MODEL 生效与否取决于
    # 「client 是否恰好先被构造」这种求值顺序巧合（R3#7）
    load_dotenv()
    return os.environ.get("PAI_MODEL", DEFAULT_MODEL)
